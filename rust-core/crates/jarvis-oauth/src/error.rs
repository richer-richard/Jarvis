//! Error type shared across the crate. Refresh-token failures and missing
//! credentials are surfaced as distinct variants so a caller can render the
//! "please re-link your ChatGPT account" state the design doc (§3) calls for
//! instead of silently degrading.

/// Errors returned by the OAuth flow, token storage, and refresh path.
#[derive(Debug, thiserror::Error)]
pub enum OAuthError {
    #[error("no stored ChatGPT credentials; run `login` first")]
    NotAuthenticated,

    #[error("authorization was denied by the provider: {0}")]
    AuthorizationDenied(String),

    #[error("callback request did not carry both `code` and `state`")]
    CallbackMissingParams,

    #[error("OAuth `state` mismatch (possible CSRF or a stale browser tab); login aborted")]
    StateMismatch,

    #[error("timed out waiting for the browser to redirect back to the loopback listener")]
    CallbackTimeout,

    #[error("could not bind the loopback callback listener on 127.0.0.1:{port}: {source}")]
    CallbackBind { port: u16, source: std::io::Error },

    #[error("loopback callback listener I/O error: {0}")]
    Io(std::io::Error),

    #[error("token endpoint returned HTTP {status}: {body}")]
    TokenEndpoint { status: u16, body: String },

    #[error("HTTP request to the OpenAI auth endpoint failed: {0}")]
    Http(reqwest::Error),

    #[error("could not decode the token endpoint response as JSON: {0}")]
    Decode(serde_json::Error),

    #[error("id_token is not a well-formed JWT")]
    MalformedJwt,

    #[error("id_token JWT is missing the chatgpt_account_id claim")]
    MissingAccountId,

    #[error("token endpoint response did not include a refresh_token")]
    MissingRefreshToken,

    #[error(
        "refresh token was rejected (expired/revoked/reused); please re-link your ChatGPT account"
    )]
    RefreshRejected,

    #[error("credential store I/O error: {0}")]
    Storage(std::io::Error),

    #[error("could not (de)serialize stored credentials: {0}")]
    Serde(serde_json::Error),

    #[error("HOME environment variable is not set; cannot locate ~/.jarvis/auth")]
    NoHome,
}

/// Crate-wide result alias.
pub type Result<T> = std::result::Result<T, OAuthError>;
