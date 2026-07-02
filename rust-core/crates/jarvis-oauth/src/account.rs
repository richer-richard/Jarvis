//! Extracts `chatgpt_account_id` from the `id_token` JWT.
//!
//! We only DECODE the JWT (base64url the payload segment + parse JSON); we do NOT
//! verify its signature. That is deliberate and safe here: the id_token arrives
//! over TLS directly from OpenAI's token endpoint in response to our own PKCE
//! exchange, so we already trust the channel -- signature verification would only
//! matter if the token were relayed by an untrusted third party. See design doc
//! §3/§6 (the doc explicitly calls this "decode-only").

use crate::error::{OAuthError, Result};
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine as _;

/// The JWT claim namespace OpenAI nests its ChatGPT auth claims under.
const AUTH_CLAIM_NAMESPACE: &str = "https://api.openai.com/auth";

/// Decodes the JWT payload segment into a JSON value. Rejects anything that is
/// not a three-segment `header.payload.signature` token, and any payload that is
/// not valid base64url-encoded JSON -- with an error, never a panic.
pub fn decode_claims(jwt: &str) -> Result<serde_json::Value> {
    let mut segments = jwt.split('.');
    let _header = segments.next().ok_or(OAuthError::MalformedJwt)?;
    let payload = segments.next().ok_or(OAuthError::MalformedJwt)?;
    let _signature = segments.next().ok_or(OAuthError::MalformedJwt)?;
    if segments.next().is_some() {
        // More than three segments -> not a JWT.
        return Err(OAuthError::MalformedJwt);
    }
    if payload.is_empty() {
        return Err(OAuthError::MalformedJwt);
    }

    // JWTs use base64url without padding, but tolerate stray '=' just in case.
    let trimmed = payload.trim_end_matches('=');
    let bytes = URL_SAFE_NO_PAD
        .decode(trimmed)
        .map_err(|_| OAuthError::MalformedJwt)?;
    serde_json::from_slice(&bytes).map_err(|_| OAuthError::MalformedJwt)
}

/// Pulls `chatgpt_account_id` out of the id_token's
/// `"https://api.openai.com/auth"` claim object. Returns
/// [`OAuthError::MissingAccountId`] if the claim namespace or the field is absent
/// or not a string.
pub fn account_id_from_id_token(id_token: &str) -> Result<String> {
    let claims = decode_claims(id_token)?;
    claims
        .get(AUTH_CLAIM_NAMESPACE)
        .and_then(|ns| ns.get("chatgpt_account_id"))
        .and_then(|v| v.as_str())
        .map(str::to_string)
        .ok_or(OAuthError::MissingAccountId)
}

#[cfg(test)]
mod tests {
    use super::*;
    use base64::engine::general_purpose::URL_SAFE_NO_PAD;

    /// Builds a minimal, valid-shaped JWT (`header.payload.signature`) whose
    /// payload is the given JSON. The signature is a throwaway string because we
    /// never verify it.
    fn fake_jwt(payload_json: &str) -> String {
        let header = URL_SAFE_NO_PAD.encode(br#"{"alg":"none","typ":"JWT"}"#);
        let payload = URL_SAFE_NO_PAD.encode(payload_json.as_bytes());
        format!("{header}.{payload}.sig-not-verified")
    }

    #[test]
    fn extracts_account_id_from_nested_claim() {
        let jwt = fake_jwt(
            r#"{"sub":"user-1","https://api.openai.com/auth":{"chatgpt_account_id":"acc_ABC123"}}"#,
        );
        assert_eq!(account_id_from_id_token(&jwt).unwrap(), "acc_ABC123");
    }

    #[test]
    fn missing_claim_namespace_errors_without_panic() {
        let jwt = fake_jwt(r#"{"sub":"user-1","email":"a@b.com"}"#);
        assert!(matches!(
            account_id_from_id_token(&jwt),
            Err(OAuthError::MissingAccountId)
        ));
    }

    #[test]
    fn present_namespace_missing_field_errors() {
        let jwt = fake_jwt(r#"{"https://api.openai.com/auth":{"other":"x"}}"#);
        assert!(matches!(
            account_id_from_id_token(&jwt),
            Err(OAuthError::MissingAccountId)
        ));
    }

    #[test]
    fn non_jwt_string_errors_without_panic() {
        assert!(matches!(
            account_id_from_id_token("not-a-jwt"),
            Err(OAuthError::MalformedJwt)
        ));
        assert!(matches!(
            account_id_from_id_token("only.two"),
            Err(OAuthError::MalformedJwt)
        ));
        assert!(matches!(
            account_id_from_id_token(""),
            Err(OAuthError::MalformedJwt)
        ));
    }

    #[test]
    fn payload_that_is_not_base64_errors() {
        // Middle segment contains characters outside the base64url alphabet.
        assert!(matches!(
            account_id_from_id_token("aaa.!!not-base64!!.sig"),
            Err(OAuthError::MalformedJwt)
        ));
    }

    #[test]
    fn payload_that_is_not_json_errors() {
        let payload = URL_SAFE_NO_PAD.encode(b"this is not json");
        let jwt = format!("aaa.{payload}.sig");
        assert!(matches!(
            account_id_from_id_token(&jwt),
            Err(OAuthError::MalformedJwt)
        ));
    }
}
