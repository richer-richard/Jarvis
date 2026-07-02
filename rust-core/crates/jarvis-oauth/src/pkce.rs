//! PKCE (RFC 7636) verifier/challenge generation with `code_challenge_method=S256`,
//! plus a small helper for the random `state` value. The design doc (§2) confirms
//! S256 against the real `codex-rs/login/src/pkce.rs`.
//!
//! The verifier is 32 random bytes rendered as base64url-no-pad (43 chars, well
//! within RFC 7636's 43..=128 range). The challenge is the base64url-no-pad
//! SHA-256 of the *ASCII verifier string* (not the raw bytes) -- that is the
//! detail that must match what OpenAI recomputes at the token endpoint.

use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine as _;
use rand::RngCore as _;
use sha2::{Digest as _, Sha256};

/// A generated PKCE pair. `verifier` is sent to the token endpoint; `challenge`
/// is sent to the authorize endpoint.
#[derive(Debug, Clone)]
pub struct Pkce {
    pub verifier: String,
    pub challenge: String,
}

impl Pkce {
    /// Generates a fresh verifier and its S256 challenge.
    pub fn generate() -> Self {
        let verifier = random_urlsafe(32);
        let challenge = challenge_for(&verifier);
        Pkce {
            verifier,
            challenge,
        }
    }
}

/// Computes the S256 `code_challenge` for a given verifier: base64url-no-pad of
/// `SHA256(verifier_ascii)`.
pub fn challenge_for(verifier: &str) -> String {
    let digest = Sha256::digest(verifier.as_bytes());
    URL_SAFE_NO_PAD.encode(digest)
}

/// Returns `n` cryptographically-random bytes rendered as base64url-no-pad.
/// Used for both the PKCE verifier and the anti-CSRF `state`.
pub fn random_urlsafe(n: usize) -> String {
    let mut bytes = vec![0u8; n];
    rand::rng().fill_bytes(&mut bytes);
    URL_SAFE_NO_PAD.encode(&bytes)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn challenge_matches_rfc7636_test_vector() {
        // RFC 7636 Appendix B worked example.
        let verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
        let expected = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM";
        assert_eq!(challenge_for(verifier), expected);
    }

    #[test]
    fn generated_verifier_is_urlsafe_and_right_length() {
        let pkce = Pkce::generate();
        // 32 bytes base64url-no-pad -> 43 chars.
        assert_eq!(pkce.verifier.len(), 43);
        assert!(pkce
            .verifier
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_'));
        // No padding leaked in.
        assert!(!pkce.verifier.contains('='));
        assert!(!pkce.challenge.contains('='));
    }

    #[test]
    fn generate_produces_distinct_verifiers() {
        assert_ne!(Pkce::generate().verifier, Pkce::generate().verifier);
    }

    #[test]
    fn challenge_is_deterministic_for_a_verifier() {
        let pkce = Pkce::generate();
        assert_eq!(challenge_for(&pkce.verifier), pkce.challenge);
    }
}
