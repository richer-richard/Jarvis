//! Auth-code -> token exchange and refresh-token exchange against
//! `https://auth.openai.com/oauth/token`.
//!
//! The request *bodies* are built by pure functions ([`auth_code_form`],
//! [`refresh_form`]) so their exact shape is unit-testable without sending
//! anything; the `async` senders ([`exchange_code`], [`refresh`]) just serialize
//! those forms and POST them.

use crate::authorize::{CLIENT_ID, SCOPES};
use crate::error::{OAuthError, Result};
use serde::Deserialize;

/// Token endpoint (constant `REFRESH_TOKEN_URL` in Codex; both grants POST here).
pub const TOKEN_ENDPOINT: &str = "https://auth.openai.com/oauth/token";

/// The subset of the token response Jarvis consumes. Unknown fields are ignored;
/// `refresh_token`/`expires_in` are optional because a refresh response may omit
/// the rotating refresh token and providers vary on `expires_in`.
#[derive(Debug, Clone, Deserialize)]
pub struct TokenResponse {
    pub id_token: String,
    pub access_token: String,
    #[serde(default)]
    pub refresh_token: Option<String>,
    #[serde(default)]
    pub expires_in: Option<i64>,
    #[serde(default)]
    pub token_type: Option<String>,
    #[serde(default)]
    pub scope: Option<String>,
}

/// Body for `grant_type=authorization_code`. `redirect_uri` MUST byte-match the
/// one sent to `/authorize`.
pub fn auth_code_form<'a>(
    code: &'a str,
    redirect_uri: &'a str,
    code_verifier: &'a str,
) -> Vec<(&'static str, &'a str)> {
    vec![
        ("grant_type", "authorization_code"),
        ("code", code),
        ("redirect_uri", redirect_uri),
        ("client_id", CLIENT_ID),
        ("code_verifier", code_verifier),
    ]
}

/// Body for `grant_type=refresh_token`. Includes `scope` to preserve the granted
/// scopes across rotation (harmless if the provider ignores it).
pub fn refresh_form(refresh_token: &str) -> Vec<(&'static str, &str)> {
    vec![
        ("grant_type", "refresh_token"),
        ("client_id", CLIENT_ID),
        ("refresh_token", refresh_token),
        ("scope", SCOPES),
    ]
}

/// Exchanges an authorization code for tokens.
pub async fn exchange_code(
    client: &reqwest::Client,
    code: &str,
    redirect_uri: &str,
    code_verifier: &str,
) -> Result<TokenResponse> {
    send_token_request(client, &auth_code_form(code, redirect_uri, code_verifier)).await
}

/// Exchanges a refresh token for a fresh access token (and possibly a rotated
/// refresh token).
pub async fn refresh(client: &reqwest::Client, refresh_token: &str) -> Result<TokenResponse> {
    send_token_request(client, &refresh_form(refresh_token)).await
}

async fn send_token_request(
    client: &reqwest::Client,
    form: &[(&'static str, &str)],
) -> Result<TokenResponse> {
    let response = client
        .post(TOKEN_ENDPOINT)
        .form(form)
        .send()
        .await
        .map_err(OAuthError::Http)?;

    let status = response.status();
    let body = response.text().await.map_err(OAuthError::Http)?;

    if !status.is_success() {
        return Err(OAuthError::TokenEndpoint {
            status: status.as_u16(),
            body: truncate(&body, 500),
        });
    }

    serde_json::from_str(&body).map_err(OAuthError::Decode)
}

fn truncate(text: &str, max: usize) -> String {
    if text.chars().count() <= max {
        return text.to_string();
    }
    text.chars().take(max).collect::<String>() + "...[truncated]"
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    fn map_of(form: &[(&'static str, &str)]) -> HashMap<&'static str, String> {
        form.iter().map(|(k, v)| (*k, v.to_string())).collect()
    }

    #[test]
    fn auth_code_form_has_all_required_fields() {
        let form = auth_code_form(
            "the-code",
            "http://localhost:1717/auth/callback",
            "the-verifier",
        );
        let m = map_of(&form);
        assert_eq!(m["grant_type"], "authorization_code");
        assert_eq!(m["code"], "the-code");
        assert_eq!(m["redirect_uri"], "http://localhost:1717/auth/callback");
        assert_eq!(m["client_id"], CLIENT_ID);
        assert_eq!(m["code_verifier"], "the-verifier");
        // No client secret is ever sent (public client + PKCE).
        assert!(!m.contains_key("client_secret"));
    }

    #[test]
    fn refresh_form_has_all_required_fields() {
        let form = refresh_form("the-refresh-token");
        let m = map_of(&form);
        assert_eq!(m["grant_type"], "refresh_token");
        assert_eq!(m["client_id"], CLIENT_ID);
        assert_eq!(m["refresh_token"], "the-refresh-token");
        assert!(!m.contains_key("code"));
    }

    #[test]
    fn token_response_deserializes_full_payload() {
        let json = r#"{
            "id_token": "a.b.c",
            "access_token": "at-123",
            "refresh_token": "rt-456",
            "expires_in": 3600,
            "token_type": "Bearer"
        }"#;
        let parsed: TokenResponse = serde_json::from_str(json).unwrap();
        assert_eq!(parsed.access_token, "at-123");
        assert_eq!(parsed.refresh_token.as_deref(), Some("rt-456"));
        assert_eq!(parsed.expires_in, Some(3600));
    }

    #[test]
    fn token_response_tolerates_missing_optional_fields() {
        // A refresh response can legitimately omit refresh_token.
        let json = r#"{"id_token":"a.b.c","access_token":"at-only"}"#;
        let parsed: TokenResponse = serde_json::from_str(json).unwrap();
        assert_eq!(parsed.access_token, "at-only");
        assert!(parsed.refresh_token.is_none());
        assert!(parsed.expires_in.is_none());
    }
}
