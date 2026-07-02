//! `jarvis-oauth` — an independent "Sign in with ChatGPT" OAuth client so Jarvis
//! can call the user's ChatGPT subscription directly, without shelling out to the
//! `codex` CLI per turn.
//!
//! This crate is a clean-room implementation of the protocol facts documented in
//! `docs/DIRECT_MODEL_OAUTH_DESIGN.md` (which verified them against
//! `openai/codex`'s real Rust source). It is deliberately **independent** of
//! Codex's own credentials:
//!
//! - It stores its own file at `~/.jarvis/auth/openai_oauth.json` (mode `0600`)
//!   and NEVER reads or writes `~/.codex/auth.json`.
//! - It binds its own dedicated loopback callback port (default
//!   [`DEFAULT_CALLBACK_PORT`], NOT Codex's `1455`) so a Jarvis login can't
//!   collide with a concurrent `codex login`.
//!
//! ## Public API
//! - [`login`] — run the full interactive browser flow and persist credentials.
//! - [`load`] — read the stored credentials (if any) without refreshing.
//! - [`access_token`] — return a valid bearer token, transparently refreshing per
//!   the 5-minute / ~8-day rules, or an error the caller can present as
//!   "please re-link your ChatGPT account".
//! - [`logout`] — delete the stored credentials.
//!
//! ## Testability
//! The deterministic pieces (PKCE math, authorize-URL construction, callback
//! request parsing, JWT `account_id` extraction, storage round-trip + file
//! permissions, and the refresh-window math in [`needs_refresh`]) are covered by
//! unit tests. The live network round trip (`/authorize` in a real browser +
//! `/token` exchange against `auth.openai.com`) can only be verified by an actual
//! ChatGPT login and is intentionally NOT mocked.

pub mod account;
pub mod authorize;
pub mod callback;
pub mod error;
pub mod pkce;
pub mod storage;
pub mod token;

use std::time::Duration;

use chrono::{DateTime, Duration as ChronoDuration, Utc};

pub use authorize::{AuthorizeRequest, CLIENT_ID, SCOPES};
pub use callback::CallbackParams;
pub use error::{OAuthError, Result};
pub use storage::{Storage, StoredCredentials};

/// Jarvis's dedicated loopback callback port. Deliberately NOT Codex's default
/// `1455` (nor its `1457` fallback) so a Jarvis login never contends with a
/// concurrent `codex login`. Per RFC 8252's loopback exception, the authorization
/// server accepts any localhost port for a native-app redirect; if OpenAI ever
/// tightens that, override via [`callback_port`]'s env var.
pub const DEFAULT_CALLBACK_PORT: u16 = 1717;

/// The callback path. Matches the path shape Codex registers (`/auth/callback`),
/// which the authorize endpoint is known to accept.
pub const CALLBACK_PATH: &str = "/auth/callback";

/// Env var to override the callback port (e.g. if the default is ever taken).
pub const CALLBACK_PORT_ENV: &str = "JARVIS_OAUTH_CALLBACK_PORT";

/// Eagerly refresh when the access token is within this many minutes of expiry.
/// Mirrors Codex's `CHATGPT_ACCESS_TOKEN_REFRESH_WINDOW_MINUTES = 5`.
const REFRESH_WINDOW_MINUTES: i64 = 5;

/// Proactively refresh when the tokens were last minted more than this many days
/// ago, even if not yet near expiry (design doc §3, "~8 days").
const PROACTIVE_REFRESH_DAYS: i64 = 8;

/// Default access-token lifetime if the token response omits `expires_in`.
const DEFAULT_TOKEN_TTL_SECONDS: i64 = 3600;

/// Upper bound applied to a token response's `expires_in` before it is used in
/// `chrono` duration/date arithmetic. `ChronoDuration::seconds` and the
/// subsequent `DateTime + Duration` both panic on values near `i64::MAX`, so a
/// malformed/hostile response must be clamped rather than trusted. 365 days is
/// far beyond any legitimate access-token TTL yet comfortably within chrono's
/// representable range.
const MAX_SAFE_TTL_SECONDS: i64 = 365 * 24 * 60 * 60;

/// How long [`login`] waits for the browser to redirect back before giving up.
const CALLBACK_TIMEOUT: Duration = Duration::from_secs(300);

/// The HTTP request timeout for token-endpoint calls.
const HTTP_TIMEOUT: Duration = Duration::from_secs(30);

/// Resolves the callback port: the [`CALLBACK_PORT_ENV`] override if set and
/// valid, otherwise [`DEFAULT_CALLBACK_PORT`].
pub fn callback_port() -> u16 {
    resolve_callback_port(std::env::var(CALLBACK_PORT_ENV).ok())
}

/// Pure port-resolution logic, split out so it's testable without mutating the
/// process environment (which is unsound under parallel tests).
fn resolve_callback_port(raw: Option<String>) -> u16 {
    raw.and_then(|v| v.trim().parse::<u16>().ok())
        .filter(|p| *p != 0)
        .unwrap_or(DEFAULT_CALLBACK_PORT)
}

/// The loopback redirect URI for a given port. This exact string is sent to BOTH
/// `/authorize` and `/token`; they must byte-match.
pub fn redirect_uri(port: u16) -> String {
    format!("http://localhost:{port}{CALLBACK_PATH}")
}

/// Whether an anti-CSRF `state` echoed back on the callback matches what we sent.
pub fn state_matches(expected: &str, received: &str) -> bool {
    // Simple constant-length compare; `state` is our own random token, not a
    // secret an attacker is trying to guess byte-by-byte, so plain `==` is fine.
    expected == received
}

/// Decides whether stored credentials should be refreshed *now*: either the
/// access token is within [`REFRESH_WINDOW_MINUTES`] of expiry (or already
/// expired), or the tokens are older than [`PROACTIVE_REFRESH_DAYS`].
pub fn needs_refresh(creds: &StoredCredentials, now: DateTime<Utc>) -> bool {
    let within_expiry_window =
        creds.expires_at - now <= ChronoDuration::minutes(REFRESH_WINDOW_MINUTES);
    let proactively_stale =
        now - creds.last_refresh >= ChronoDuration::days(PROACTIVE_REFRESH_DAYS);
    within_expiry_window || proactively_stale
}

/// Runs the full interactive login and persists credentials to the default
/// location (`~/.jarvis/auth/openai_oauth.json`).
///
/// Steps: generate PKCE + `state`, bind the loopback listener *before* opening
/// the browser (closing the redirect race), open the authorize URL, wait for the
/// callback, verify `state`, exchange the code for tokens, derive `account_id`
/// and expiry, and atomically write the credential file.
///
/// If `open_browser` is false, the authorize URL is logged/returned instead of
/// opened — useful for headless environments and for driving the flow manually.
pub async fn login(open_browser: bool) -> Result<StoredCredentials> {
    let port = callback_port();
    let storage = Storage::default_location()?;
    login_with(port, open_browser, &storage).await
}

/// Same as [`login`] but with an explicit port and storage handle. Kept public so
/// callers (and tests) can point the flow at a scratch location.
pub async fn login_with(
    port: u16,
    open_browser: bool,
    storage: &Storage,
) -> Result<StoredCredentials> {
    let pkce = pkce::Pkce::generate();
    let state = pkce::random_urlsafe(32);
    let redirect = redirect_uri(port);

    // Bind the listener FIRST so the browser can't redirect before we're ready.
    let server = callback::CallbackServer::bind(port).await?;

    let authorize_url = AuthorizeRequest {
        redirect_uri: redirect.clone(),
        code_challenge: pkce.challenge.clone(),
        state: state.clone(),
    }
    .url();

    if open_browser {
        open_in_browser(authorize_url.as_str());
    } else {
        tracing::info!("Open this URL to link ChatGPT:\n{authorize_url}");
    }

    let params = server.wait(CALLBACK_TIMEOUT).await?;
    if !state_matches(&state, &params.state) {
        return Err(OAuthError::StateMismatch);
    }

    let client = http_client()?;
    let token = token::exchange_code(&client, &params.code, &redirect, &pkce.verifier).await?;
    let creds = credentials_from_token(token, None, None)?;
    storage.save(&creds)?;
    Ok(creds)
}

/// Reads the stored credentials without refreshing. `Ok(None)` means the user has
/// not linked their account yet.
pub fn load() -> Result<Option<StoredCredentials>> {
    Storage::default_location()?.load()
}

/// Returns a valid bearer access token, transparently refreshing if needed and
/// persisting the rotated credentials. Errors with [`OAuthError::NotAuthenticated`]
/// if there are no stored credentials, or [`OAuthError::RefreshRejected`] if the
/// refresh token is no longer accepted (the "please re-link" state).
pub async fn access_token() -> Result<String> {
    let storage = Storage::default_location()?;
    let creds = storage.load()?.ok_or(OAuthError::NotAuthenticated)?;
    let fresh = ensure_fresh(&storage, creds).await?;
    Ok(fresh.access_token)
}

/// Deletes the stored credentials (logout). Absent file is treated as success.
pub fn logout() -> Result<()> {
    Storage::default_location()?.delete()
}

/// Whether a token-endpoint HTTP status on a refresh attempt means the refresh
/// token itself was rejected (expired/revoked/reused) rather than a transient
/// server-side failure. Only 4xx client errors are terminal; a 5xx (outage,
/// maintenance, rate limiting) must be retried, not treated as "please
/// re-link your account".
fn is_terminal_refresh_rejection(status: u16) -> bool {
    (400..500).contains(&status)
}

/// Refreshes `creds` if [`needs_refresh`] says so, persisting the result; returns
/// the credentials that should be used now.
async fn ensure_fresh(storage: &Storage, creds: StoredCredentials) -> Result<StoredCredentials> {
    if !needs_refresh(&creds, Utc::now()) {
        return Ok(creds);
    }
    let client = http_client()?;
    let token = match token::refresh(&client, &creds.refresh_token).await {
        Ok(token) => token,
        // A 4xx from the token endpoint on refresh is terminal (expired / revoked
        // / reused). Surface the distinct "re-link" state rather than a raw HTTP
        // error so the caller can prompt a fresh interactive login. A 5xx is a
        // temporary server-side failure (or an outage) and must NOT be treated
        // as rejection — that would force a needless re-link every time the
        // auth server hiccups. Propagate it as-is so the caller can retry.
        Err(OAuthError::TokenEndpoint { status, .. }) if is_terminal_refresh_rejection(status) => {
            return Err(OAuthError::RefreshRejected);
        }
        Err(other) => return Err(other),
    };
    // A refresh response may omit a rotated refresh_token or re-derivable
    // account_id; keep the prior values rather than dropping them.
    let refreshed = credentials_from_token(
        token,
        Some(creds.refresh_token.clone()),
        creds.account_id.clone(),
    )?;
    storage.save(&refreshed)?;
    Ok(refreshed)
}

/// Builds [`StoredCredentials`] from a token response: derives `account_id` from
/// the id_token, computes absolute `expires_at`, stamps `last_refresh`, and
/// carries over `prior_refresh_token`/`prior_account_id` when the response omits
/// or cannot re-derive one.
fn credentials_from_token(
    token: token::TokenResponse,
    prior_refresh_token: Option<String>,
    prior_account_id: Option<String>,
) -> Result<StoredCredentials> {
    let now = Utc::now();
    // Clamp before any chrono arithmetic: a negative TTL means "already expired,
    // refresh immediately" (not an underflow), and an absurdly large one from a
    // malformed/hostile response must not be allowed to panic `ChronoDuration`.
    let ttl = token
        .expires_in
        .unwrap_or(DEFAULT_TOKEN_TTL_SECONDS)
        .clamp(0, MAX_SAFE_TTL_SECONDS);
    let expires_at = now + ChronoDuration::seconds(ttl);

    // account_id is best-effort: store it when present, but a missing claim does
    // not fail login (the token is still usable; the claim is only needed for the
    // not-yet-built Responses-API caller). We log so it's visible if absent. On a
    // refresh whose id_token drops the claim, fall back to the prior value rather
    // than clobbering a previously-known-good account_id with None.
    let account_id = match account::account_id_from_id_token(&token.id_token) {
        Ok(id) => Some(id),
        Err(e) => {
            tracing::warn!("id_token has no chatgpt_account_id claim: {e}");
            prior_account_id
        }
    };

    let refresh_token = token
        .refresh_token
        .or(prior_refresh_token)
        .ok_or(OAuthError::MissingRefreshToken)?;

    Ok(StoredCredentials {
        access_token: token.access_token,
        refresh_token,
        id_token: token.id_token,
        account_id,
        expires_at,
        last_refresh: now,
        client_id: CLIENT_ID.to_string(),
        scopes: SCOPES.to_string(),
    })
}

fn http_client() -> Result<reqwest::Client> {
    reqwest::Client::builder()
        .timeout(HTTP_TIMEOUT)
        .build()
        .map_err(OAuthError::Http)
}

/// Best-effort open of the authorize URL in the system browser. Non-fatal: if it
/// fails, the URL was already logged and the user can paste it manually.
fn open_in_browser(url: &str) {
    #[cfg(target_os = "macos")]
    let launcher = ("open", &[url][..]);
    #[cfg(all(unix, not(target_os = "macos")))]
    let launcher = ("xdg-open", &[url][..]);
    #[cfg(windows)]
    let launcher = ("cmd", &["/C", "start", "", url][..]);

    #[cfg(any(unix, windows))]
    if let Err(e) = std::process::Command::new(launcher.0)
        .args(launcher.1)
        .spawn()
    {
        tracing::warn!(
            "could not open browser ({}): {e}; open the URL manually",
            launcher.0
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use base64::engine::general_purpose::URL_SAFE_NO_PAD;
    use base64::Engine as _;

    /// Builds a minimal, valid-shaped id_token JWT whose payload is the given
    /// JSON. The signature is a throwaway string because the crate decodes but
    /// never verifies id_tokens (see `account.rs`).
    fn fake_id_token(payload_json: &str) -> String {
        let header = URL_SAFE_NO_PAD.encode(br#"{"alg":"none","typ":"JWT"}"#);
        let payload = URL_SAFE_NO_PAD.encode(payload_json.as_bytes());
        format!("{header}.{payload}.sig-not-verified")
    }

    fn token_response(
        id_token: String,
        refresh_token: Option<String>,
        expires_in: Option<i64>,
    ) -> token::TokenResponse {
        token::TokenResponse {
            id_token,
            access_token: "fresh-at".to_string(),
            refresh_token,
            expires_in,
            token_type: Some("Bearer".to_string()),
            scope: None,
        }
    }

    const ID_TOKEN_NO_CLAIM: &str = r#"{"sub":"user-1"}"#;

    fn creds_expiring_in(minutes: i64, last_refresh_days_ago: i64) -> StoredCredentials {
        let now = Utc::now();
        StoredCredentials {
            access_token: "at".to_string(),
            refresh_token: "rt".to_string(),
            id_token: "a.b.c".to_string(),
            account_id: Some("acc".to_string()),
            expires_at: now + ChronoDuration::minutes(minutes),
            last_refresh: now - ChronoDuration::days(last_refresh_days_ago),
            client_id: CLIENT_ID.to_string(),
            scopes: SCOPES.to_string(),
        }
    }

    #[test]
    fn token_expiring_within_window_needs_refresh() {
        // Expires in 3 minutes -> inside the 5-minute window.
        assert!(needs_refresh(&creds_expiring_in(3, 0), Utc::now()));
    }

    #[test]
    fn token_with_ample_life_does_not_need_refresh() {
        // Expires in 2 hours, freshly minted -> no refresh.
        assert!(!needs_refresh(&creds_expiring_in(120, 0), Utc::now()));
    }

    #[test]
    fn already_expired_token_needs_refresh() {
        assert!(needs_refresh(&creds_expiring_in(-10, 0), Utc::now()));
    }

    #[test]
    fn stale_last_refresh_forces_proactive_refresh() {
        // Still valid for 2 hours, but last refreshed 9 days ago.
        assert!(needs_refresh(&creds_expiring_in(120, 9), Utc::now()));
    }

    #[test]
    fn boundary_just_outside_window_does_not_refresh() {
        // Expires in 6 minutes, refreshed 7 days ago -> neither trigger fires.
        assert!(!needs_refresh(&creds_expiring_in(6, 7), Utc::now()));
    }

    #[test]
    fn only_4xx_token_endpoint_statuses_are_terminal_refresh_rejections() {
        // Gemini Code Assist finding on PR #3: a 5xx from the token endpoint
        // (outage, maintenance, rate limiting) must be retried, not treated
        // as "the refresh token was rejected, please re-link your account".
        assert!(!is_terminal_refresh_rejection(399));
        assert!(is_terminal_refresh_rejection(400));
        assert!(is_terminal_refresh_rejection(401));
        assert!(is_terminal_refresh_rejection(499));
        assert!(!is_terminal_refresh_rejection(500));
        assert!(!is_terminal_refresh_rejection(502));
        assert!(!is_terminal_refresh_rejection(503));
    }

    #[test]
    fn redirect_uri_is_well_formed_and_byte_stable() {
        assert_eq!(redirect_uri(1717), "http://localhost:1717/auth/callback");
    }

    #[test]
    fn state_comparison() {
        assert!(state_matches("abc", "abc"));
        assert!(!state_matches("abc", "abd"));
        assert!(!state_matches("abc", ""));
    }

    #[test]
    fn default_callback_port_is_not_codex_ports() {
        assert_ne!(DEFAULT_CALLBACK_PORT, 1455);
        assert_ne!(DEFAULT_CALLBACK_PORT, 1457);
    }

    #[test]
    fn callback_port_resolution() {
        assert_eq!(resolve_callback_port(Some("2020".to_string())), 2020);
        assert_eq!(resolve_callback_port(Some("  2021 ".to_string())), 2021);
        // Invalid / out-of-range / zero fall back to the default.
        assert_eq!(
            resolve_callback_port(Some("not-a-port".to_string())),
            DEFAULT_CALLBACK_PORT
        );
        assert_eq!(
            resolve_callback_port(Some("0".to_string())),
            DEFAULT_CALLBACK_PORT
        );
        assert_eq!(resolve_callback_port(None), DEFAULT_CALLBACK_PORT);
    }

    #[test]
    fn refresh_without_account_claim_retains_prior_account_id() {
        // The refreshed id_token drops the chatgpt_account_id claim.
        let token = token_response(
            fake_id_token(ID_TOKEN_NO_CLAIM),
            Some("rt-new".to_string()),
            Some(3600),
        );
        let creds = credentials_from_token(
            token,
            Some("rt-prior".to_string()),
            Some("acc-prior".to_string()),
        )
        .unwrap();
        // The previously-known-good account_id survives instead of becoming None.
        assert_eq!(creds.account_id.as_deref(), Some("acc-prior"));
    }

    #[test]
    fn refresh_with_account_claim_replaces_account_id() {
        let token = token_response(
            fake_id_token(r#"{"https://api.openai.com/auth":{"chatgpt_account_id":"acc-new"}}"#),
            None,
            Some(3600),
        );
        let creds = credentials_from_token(
            token,
            Some("rt-prior".to_string()),
            Some("acc-prior".to_string()),
        )
        .unwrap();
        // A real claim on the response replaces the prior value.
        assert_eq!(creds.account_id.as_deref(), Some("acc-new"));
    }

    #[test]
    fn fresh_login_without_account_claim_yields_none() {
        // Fresh login has no prior account_id to fall back to.
        let token = token_response(
            fake_id_token(ID_TOKEN_NO_CLAIM),
            Some("rt".to_string()),
            Some(3600),
        );
        let creds = credentials_from_token(token, None, None).unwrap();
        assert!(creds.account_id.is_none());
    }

    #[test]
    fn refresh_response_omitting_refresh_token_carries_prior() {
        let token = token_response(fake_id_token(ID_TOKEN_NO_CLAIM), None, Some(3600));
        let creds =
            credentials_from_token(token, Some("rt-prior".to_string()), Some("acc".to_string()))
                .unwrap();
        assert_eq!(creds.refresh_token, "rt-prior");
    }

    #[test]
    fn rotated_refresh_token_supersedes_prior() {
        let token = token_response(
            fake_id_token(ID_TOKEN_NO_CLAIM),
            Some("rt-new".to_string()),
            Some(3600),
        );
        let creds =
            credentials_from_token(token, Some("rt-prior".to_string()), Some("acc".to_string()))
                .unwrap();
        assert_eq!(creds.refresh_token, "rt-new");
    }

    #[test]
    fn absurd_expires_in_does_not_panic_and_clamps() {
        // i64::MAX would previously overflow ChronoDuration::seconds / the
        // DateTime addition and panic; it must now clamp to MAX_SAFE_TTL_SECONDS.
        let before = Utc::now();
        let token = token_response(
            fake_id_token(ID_TOKEN_NO_CLAIM),
            Some("rt".to_string()),
            Some(i64::MAX),
        );
        let creds = credentials_from_token(token, None, None).unwrap();
        let after = Utc::now();
        let expected_low = before + ChronoDuration::seconds(MAX_SAFE_TTL_SECONDS);
        let expected_high = after + ChronoDuration::seconds(MAX_SAFE_TTL_SECONDS);
        assert!(creds.expires_at >= expected_low && creds.expires_at <= expected_high);
    }

    #[test]
    fn negative_expires_in_clamps_to_already_expired() {
        // A negative TTL means "already expired, refresh now", not an underflow.
        let before = Utc::now();
        let token = token_response(
            fake_id_token(ID_TOKEN_NO_CLAIM),
            Some("rt".to_string()),
            Some(-100),
        );
        let creds = credentials_from_token(token, None, None).unwrap();
        let after = Utc::now();
        assert!(creds.expires_at >= before && creds.expires_at <= after);
    }

    #[test]
    fn normal_expires_in_is_preserved() {
        let before = Utc::now();
        let token = token_response(
            fake_id_token(ID_TOKEN_NO_CLAIM),
            Some("rt".to_string()),
            Some(3600),
        );
        let creds = credentials_from_token(token, None, None).unwrap();
        let after = Utc::now();
        let expected_low = before + ChronoDuration::seconds(3600);
        let expected_high = after + ChronoDuration::seconds(3600);
        assert!(creds.expires_at >= expected_low && creds.expires_at <= expected_high);
    }
}
