//! Builds the `/oauth/authorize` URL. Pure and side-effect-free: it takes the
//! redirect URI, PKCE challenge, and `state`, and returns a fully-encoded URL.
//! Opening the browser lives in `lib.rs` so this stays unit-testable.
//!
//! Every constant here is a *protocol fact* confirmed in the design doc (§2)
//! against `openai/codex`'s real Rust source, not a Jarvis-specific choice.

use reqwest::Url;

/// The public, non-configurable "Sign in with ChatGPT" client id reused by every
/// third-party tool (Codex CLI, OpenClaw, Hermes). There is no per-app
/// registration; this is what makes the flow possible without an OpenAI dev
/// account. See design doc §0/§2.
pub const CLIENT_ID: &str = "app_EMoamEEZ73f0CkXaXp7hrann";

/// Authorize endpoint (issuer `https://auth.openai.com`).
pub const AUTHORIZE_ENDPOINT: &str = "https://auth.openai.com/oauth/authorize";

/// Space-delimited scopes. `offline_access` is what yields a refresh token.
pub const SCOPES: &str =
    "openid profile email offline_access api.connectors.read api.connectors.invoke";

/// The inputs needed to build one authorize URL.
pub struct AuthorizeRequest {
    /// Loopback redirect URI. Must byte-match the one later sent to the token
    /// endpoint.
    pub redirect_uri: String,
    /// PKCE S256 `code_challenge`.
    pub code_challenge: String,
    /// Anti-CSRF `state`, echoed back on the callback.
    pub state: String,
}

impl AuthorizeRequest {
    /// Builds the fully percent-encoded authorize URL. The parameter set mirrors
    /// what Codex sends: `response_type`, `client_id`, `redirect_uri`, `scope`,
    /// PKCE pair, `state`, plus the two Codex flow flags.
    pub fn url(&self) -> Url {
        Url::parse_with_params(
            AUTHORIZE_ENDPOINT,
            &[
                ("response_type", "code"),
                ("client_id", CLIENT_ID),
                ("redirect_uri", self.redirect_uri.as_str()),
                ("scope", SCOPES),
                ("code_challenge", self.code_challenge.as_str()),
                ("code_challenge_method", "S256"),
                ("state", self.state.as_str()),
                ("id_token_add_organizations", "true"),
                ("codex_cli_simplified_flow", "true"),
            ],
        )
        // The base endpoint is a compile-time constant known-good URL; the only
        // dynamic parts are values, which `parse_with_params` percent-encodes.
        .expect("authorize endpoint constant is a valid base URL")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    fn params_of(req: &AuthorizeRequest) -> HashMap<String, String> {
        req.url()
            .query_pairs()
            .map(|(k, v)| (k.into_owned(), v.into_owned()))
            .collect()
    }

    fn sample() -> AuthorizeRequest {
        AuthorizeRequest {
            redirect_uri: "http://localhost:1717/auth/callback".to_string(),
            code_challenge: "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM".to_string(),
            state: "state-token-abc".to_string(),
        }
    }

    #[test]
    fn url_targets_the_authorize_endpoint() {
        let url = sample().url();
        assert_eq!(url.scheme(), "https");
        assert_eq!(url.host_str(), Some("auth.openai.com"));
        assert_eq!(url.path(), "/oauth/authorize");
    }

    #[test]
    fn url_carries_every_required_param() {
        let p = params_of(&sample());
        assert_eq!(p["response_type"], "code");
        assert_eq!(p["client_id"], CLIENT_ID);
        assert_eq!(p["redirect_uri"], "http://localhost:1717/auth/callback");
        assert_eq!(p["scope"], SCOPES);
        assert_eq!(
            p["code_challenge"],
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        );
        assert_eq!(p["code_challenge_method"], "S256");
        assert_eq!(p["state"], "state-token-abc");
        assert_eq!(p["id_token_add_organizations"], "true");
        assert_eq!(p["codex_cli_simplified_flow"], "true");
    }

    #[test]
    fn redirect_uri_and_state_are_percent_encoded_in_the_raw_query() {
        // The raw query must not contain a bare ':' or '/' from the redirect_uri,
        // proving encoding happened (so authorize/token byte-matching is safe).
        let raw = sample().url().to_string();
        assert!(raw.contains("redirect_uri=http%3A%2F%2Flocalhost%3A1717%2Fauth%2Fcallback"));
    }

    #[test]
    fn scopes_include_offline_access_for_refresh_tokens() {
        assert!(SCOPES.split(' ').any(|s| s == "offline_access"));
    }
}
