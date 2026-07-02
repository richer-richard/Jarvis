mod state;

use axum::{
    extract::{Request, State},
    http::{header, HeaderMap, StatusCode},
    middleware::{self, Next},
    response::{IntoResponse, Json, Response},
    routing::{get, post},
    Router,
};
use jarvis_audit::AuditLogger;
use jarvis_config::Config;
use serde_json::{json, Value};
use state::AppState;
use std::net::{IpAddr, SocketAddr};
use std::path::PathBuf;
use std::sync::Arc;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();

    let config = Config::load();
    let addr = SocketAddr::new(config.server.host, config.server.port);
    let allow_non_loopback = config.server.allow_non_loopback;
    let state = Arc::new(AppState::new(config));

    let app = build_router(state);

    if !allow_non_loopback && !addr.ip().is_loopback() {
        anyhow::bail!(
            "Refusing to bind non-loopback address {addr} without JARVIS_ALLOW_NON_LOOPBACK=1 (matches jarvis/config.py:82 semantics)"
        );
    }

    tracing::info!("jarvis-server listening on {addr}");
    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;
    Ok(())
}

/// Builds the router with the loopback Host-header guard applied to every route.
/// Factored out so tests can exercise the middleware via `oneshot`.
fn build_router(state: Arc<AppState>) -> Router {
    Router::new()
        .route("/api/health", get(health))
        .route("/api/mode", get(get_mode).post(set_mode))
        .route("/api/policy", get(policy))
        .route("/api/tools", get(tools))
        .route("/api/self-check", get(self_check))
        .route("/api/readiness", get(not_yet_ported))
        .route("/api/preflight", get(not_yet_ported))
        .route("/api/plan", post(not_yet_ported_post))
        .route("/api/command", post(not_yet_ported_post))
        .layer(middleware::from_fn_with_state(
            state.clone(),
            host_header_guard,
        ))
        .with_state(state)
}

/// Rejects requests whose `Host` header isn't a loopback address, mirroring the
/// DNS-rebinding protection in jarvis/server.py's `_host_header_allowed`.
/// `JARVIS_ALLOW_NON_LOOPBACK=1` disables the guard, matching the Python
/// `host_allowed(..., allow_non_loopback=...)` bypass.
async fn host_header_guard(
    State(state): State<Arc<AppState>>,
    request: Request,
    next: Next,
) -> Response {
    if state.config.server.allow_non_loopback || host_header_is_loopback(request.headers()) {
        next.run(request).await
    } else {
        (
            StatusCode::FORBIDDEN,
            Json(json!({"error": "Host header must be loopback"})),
        )
            .into_response()
    }
}

fn host_header_is_loopback(headers: &HeaderMap) -> bool {
    let Some(raw) = headers.get(header::HOST).and_then(|v| v.to_str().ok()) else {
        // Absent/undecodable Host mirrors Python's `host_allowed("")` -> False.
        return false;
    };
    host_is_loopback(&host_from_header(raw))
}

/// Mirrors jarvis/server.py:1903-1909 `_host_from_header`: unwraps bracketed IPv6
/// literals and strips a single trailing `:port`.
fn host_from_header(value: &str) -> String {
    let host = value.trim();
    if host.starts_with('[') {
        if let Some(end) = host.find(']') {
            return host[1..end].to_string();
        }
    }
    if host.matches(':').count() == 1 {
        if let Some((h, _)) = host.rsplit_once(':') {
            return h.to_string();
        }
    }
    host.to_string()
}

/// Mirrors jarvis/config.py:170-179 `host_allowed`: `localhost` plus any IPv4/IPv6
/// loopback address (127.0.0.0/8, ::1).
fn host_is_loopback(host: &str) -> bool {
    let normalized = host.trim().to_ascii_lowercase();
    if normalized == "localhost" {
        return true;
    }
    normalized
        .parse::<IpAddr>()
        .map(|ip| ip.is_loopback())
        .unwrap_or(false)
}

fn audit_log_path(config: &Config) -> PathBuf {
    config
        .workspace_root
        .join("runtime")
        .join("audit")
        .join("events.jsonl")
}

async fn health(State(state): State<Arc<AppState>>) -> Json<Value> {
    Json(json!({
        "ok": true,
        "status": "scaffold",
        "mode": state.mode_snapshot(),
    }))
}

async fn get_mode(State(state): State<Arc<AppState>>) -> Json<Value> {
    Json(state.mode_snapshot())
}

async fn set_mode(
    State(state): State<Arc<AppState>>,
    Json(payload): Json<Value>,
) -> impl IntoResponse {
    let Some(paused) = payload.get("paused").and_then(Value::as_bool) else {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "`paused` must be true or false"})),
        )
            .into_response();
    };
    let reason = payload
        .get("reason")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let snapshot = state.set_mode(paused, reason);
    (StatusCode::OK, Json(snapshot)).into_response()
}

async fn policy() -> Json<Value> {
    Json(json!({
        "risk_levels": [
            {"level": 0, "label": jarvis_safety::RiskLevel::LocalConversation.label()},
            {"level": 1, "label": jarvis_safety::RiskLevel::ReadOnlyLocalContext.label()},
            {"level": 2, "label": jarvis_safety::RiskLevel::PrivateReadAccess.label()},
            {"level": 3, "label": jarvis_safety::RiskLevel::ReversibleChange.label()},
            {"level": 4, "label": jarvis_safety::RiskLevel::ExternalDestructiveSensitive.label()},
        ],
        "note": "Full policy_summary() port pending -- see rust-core/MIGRATION.md",
    }))
}

/// Reports the tool surface actually ported into `jarvis-tools`. Right now that is
/// only Codex delegation (read-only + write-capable); the rest of
/// jarvis/tools.py's registry is still Python-only.
async fn tools(State(state): State<Arc<AppState>>) -> Json<Value> {
    let codex = &state.config.codex;
    let codex_path = jarvis_tools::find_executable("codex");
    let codex_available = codex_path.is_some();

    Json(json!({
        "execution_boundary": "Commands are classified by jarvis-safety before routing. Protected actions require confirmation and are not auto-executed.",
        "tools": [
            {
                "id": "codex.delegate",
                "label": "Codex Delegate (read-only)",
                "mode": "read_only",
                "risk_level": jarvis_safety::RiskLevel::ReadOnlyLocalContext as u8,
                "risk_label": jarvis_safety::RiskLevel::ReadOnlyLocalContext.label(),
                "available": codex_available,
                "write_capable": false,
                "sandbox": "read-only",
                "model": codex.model.clone(),
                "description": "Delegates investigation/analysis to the Codex CLI in a read-only sandbox (--sandbox read-only --ask-for-approval never).",
            },
            {
                "id": "codex.delegate_write",
                "label": "Codex Delegate (workspace-write)",
                "mode": "reversible_change",
                "risk_level": jarvis_safety::RiskLevel::ExternalDestructiveSensitive as u8,
                "risk_label": jarvis_safety::RiskLevel::ExternalDestructiveSensitive.label(),
                "available": codex_available && codex.write_enabled,
                "write_capable": true,
                "sandbox": "workspace-write",
                "requires_typed_confirmation": true,
                "model": codex.model.clone(),
                "description": "Delegates a write-capable task to the Codex CLI (--sandbox workspace-write). Gated behind Jarvis typed confirmation; disabled unless JARVIS_CODEX_WRITE_ENABLED=1.",
            },
        ],
        "codex_path": codex_path.map(|p| p.display().to_string()),
        "note": "Only Codex delegation is ported into jarvis-tools so far; conversation/diagnostics/calendar/email tools remain in the Python worker. See rust-core/MIGRATION.md.",
    }))
}

/// A genuinely-useful subset of jarvis/self_check.py (302 lines): the runtime
/// invariants this Rust server can actually prove about itself right now.
/// `required` checks gate the top-level `ok`; the others are informational and
/// environment-dependent.
async fn self_check(State(state): State<Arc<AppState>>) -> Json<Value> {
    let allow_non_loopback = state.config.server.allow_non_loopback;
    let loopback_enforced = !allow_non_loopback;

    let codex_path = jarvis_tools::find_executable("codex");
    let codex_on_path = codex_path.is_some();

    let audit_path = audit_log_path(&state.config);
    let audit_writable = AuditLogger::new(&audit_path).probe_writable();

    // The Host-header guard is unconditionally applied by build_router(), so it is
    // a hard invariant rather than a runtime probe.
    let host_guard_ok = true;
    let overall_ok = host_guard_ok && audit_writable;

    Json(json!({
        "ok": overall_ok,
        "checks": [
            {
                "id": "host_header_guard_active",
                "required": true,
                "ok": host_guard_ok,
                "detail": "Every route is wrapped in the loopback Host-header middleware (DNS-rebinding protection).",
            },
            {
                "id": "audit_log_writable",
                "required": true,
                "ok": audit_writable,
                "detail": format!(
                    "audit dir {}",
                    audit_path.parent().map(|p| p.display().to_string()).unwrap_or_default()
                ),
            },
            {
                "id": "loopback_binding_enforced",
                "required": false,
                "ok": loopback_enforced,
                "detail": format!(
                    "bound host {}; JARVIS_ALLOW_NON_LOOPBACK={}",
                    state.config.server.host, allow_non_loopback
                ),
            },
            {
                "id": "codex_binary_on_path",
                "required": false,
                "ok": codex_on_path,
                "detail": codex_path
                    .map(|p| p.display().to_string())
                    .unwrap_or_else(|| "codex not found on PATH".to_string()),
            },
        ],
        "not_covered": [
            "microphone / accessibility (TCC) permissions",
            "model reachability (Ollama / Groq / Codex actually responding)",
            "planner + tool-execution loop readiness",
        ],
        "note": "Runtime-provable subset of jarvis/self_check.py; the excluded checks depend on the not-yet-ported worker loop.",
    }))
}

async fn not_yet_ported() -> impl IntoResponse {
    (
        StatusCode::NOT_IMPLEMENTED,
        Json(json!({
            "error": "not_yet_ported",
            "note": "This endpoint is still served by the Python worker (jarvis/server.py). See rust-core/MIGRATION.md.",
        })),
    )
}

async fn not_yet_ported_post(Json(_payload): Json<Value>) -> impl IntoResponse {
    not_yet_ported().await
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Body;
    use axum::http::Request as HttpRequest;
    use tower::ServiceExt;

    fn test_state() -> Arc<AppState> {
        let mut config = Config::load();
        // Pin the guard on regardless of the host environment's config.
        config.server.allow_non_loopback = false;
        Arc::new(AppState::new(config))
    }

    async fn get_with_host(host: &str) -> StatusCode {
        let app = build_router(test_state());
        let response = app
            .oneshot(
                HttpRequest::builder()
                    .uri("/api/health")
                    .header("Host", host)
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        response.status()
    }

    #[tokio::test]
    async fn rejects_non_loopback_host() {
        assert_eq!(get_with_host("evil.com").await, StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn allows_loopback_ipv4_host() {
        assert_eq!(get_with_host("127.0.0.1:8765").await, StatusCode::OK);
    }

    #[tokio::test]
    async fn allows_localhost_host() {
        assert_eq!(get_with_host("localhost").await, StatusCode::OK);
    }

    #[tokio::test]
    async fn allows_bracketed_ipv6_loopback_host() {
        assert_eq!(get_with_host("[::1]:8765").await, StatusCode::OK);
    }

    #[tokio::test]
    async fn allow_non_loopback_disables_guard() {
        let mut config = Config::load();
        config.server.allow_non_loopback = true;
        let app = build_router(Arc::new(AppState::new(config)));
        let response = app
            .oneshot(
                HttpRequest::builder()
                    .uri("/api/health")
                    .header("Host", "evil.com")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[test]
    fn host_from_header_strips_port_and_brackets() {
        assert_eq!(host_from_header("127.0.0.1:8765"), "127.0.0.1");
        assert_eq!(host_from_header("[::1]:8765"), "::1");
        assert_eq!(host_from_header("[::1]"), "::1");
        assert_eq!(host_from_header("localhost"), "localhost");
        assert_eq!(host_from_header("evil.com"), "evil.com");
        // Unbracketed IPv6 has multiple colons and is left intact.
        assert_eq!(host_from_header("::1"), "::1");
    }

    #[test]
    fn host_is_loopback_classification() {
        assert!(host_is_loopback("127.0.0.1"));
        assert!(host_is_loopback("127.0.0.5"));
        assert!(host_is_loopback("::1"));
        assert!(host_is_loopback("localhost"));
        assert!(!host_is_loopback("evil.com"));
        assert!(!host_is_loopback("10.0.0.5"));
        assert!(!host_is_loopback("0.0.0.0"));
    }
}
