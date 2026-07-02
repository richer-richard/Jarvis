//! Loopback HTTP listener that receives the browser redirect
//! (`GET /auth/callback?code=...&state=...`).
//!
//! Design choice: this is a hand-rolled one-shot `tokio::net::TcpListener` rather
//! than an `axum` route. The team lead flagged axum as the consistency-preferred
//! option, but a single-request callback wants exactly-one-connection-then-stop
//! semantics, which with axum means a graceful-shutdown oneshot dance; the raw
//! listener expresses "accept, parse the request line, reply, return" directly
//! and keeps the query-parsing logic a pure, unit-testable function
//! ([`parse_callback_target`]). This is the same first-line-only approach used by
//! most OAuth CLIs. The browser only ever issues a well-formed loopback GET here.

use crate::error::{OAuthError, Result};
use std::net::SocketAddr;
use std::time::Duration;
use tokio::io::{AsyncReadExt as _, AsyncWriteExt as _};
use tokio::net::TcpListener;

/// The `code` + `state` extracted from the redirect.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CallbackParams {
    pub code: String,
    pub state: String,
}

/// Extracts the request target (second whitespace-delimited token) from an HTTP
/// request line like `GET /auth/callback?code=X&state=Y HTTP/1.1`.
pub fn request_target(request_line: &str) -> Option<&str> {
    let mut parts = request_line.split_whitespace();
    let _method = parts.next()?;
    parts.next()
}

/// Parses `code`/`state` out of a request target such as
/// `/auth/callback?code=X&state=Y`. Percent-decoding is delegated to the `url`
/// crate (via `reqwest::Url`) by resolving the target against a dummy loopback
/// base, so `%XX` and `+` are handled correctly.
///
/// Returns [`OAuthError::AuthorizationDenied`] if the provider redirected with an
/// `error=...` param, and [`OAuthError::CallbackMissingParams`] if either `code`
/// or `state` is absent/empty.
pub fn parse_callback_target(target: &str) -> Result<CallbackParams> {
    let url = reqwest::Url::parse(&format!("http://localhost{target}"))
        .map_err(|_| OAuthError::CallbackMissingParams)?;

    let mut code = None;
    let mut state = None;
    let mut error = None;
    for (key, value) in url.query_pairs() {
        match key.as_ref() {
            "code" => code = Some(value.into_owned()),
            "state" => state = Some(value.into_owned()),
            "error" => error = Some(value.into_owned()),
            _ => {}
        }
    }

    if let Some(err) = error {
        return Err(OAuthError::AuthorizationDenied(err));
    }
    match (code, state) {
        (Some(code), Some(state)) if !code.is_empty() && !state.is_empty() => {
            Ok(CallbackParams { code, state })
        }
        _ => Err(OAuthError::CallbackMissingParams),
    }
}

/// A bound loopback listener, split from [`CallbackServer::wait`] so a caller can
/// bind the port *before* opening the browser (closing the redirect race) and
/// then await the callback.
pub struct CallbackServer {
    listener: TcpListener,
}

impl CallbackServer {
    /// Binds `127.0.0.1:<port>` for the callback.
    pub async fn bind(port: u16) -> Result<Self> {
        let addr = SocketAddr::from(([127, 0, 0, 1], port));
        let listener = TcpListener::bind(addr)
            .await
            .map_err(|source| OAuthError::CallbackBind { port, source })?;
        Ok(Self { listener })
    }

    /// Waits (up to `timeout`) for the browser to hit the callback path, replies
    /// with a small human-facing page, and returns the parsed params.
    ///
    /// Non-callback probes the browser sometimes issues first (e.g.
    /// `/favicon.ico`) get a 204 and are ignored; the loop keeps waiting for the
    /// real `code`/`state` request.
    pub async fn wait(self, timeout: Duration) -> Result<CallbackParams> {
        let accept = async {
            loop {
                let (mut stream, _peer) = self.listener.accept().await.map_err(OAuthError::Io)?;

                let mut buf = [0u8; 8192];
                let n = stream.read(&mut buf).await.map_err(OAuthError::Io)?;
                let head = String::from_utf8_lossy(&buf[..n]);
                let first_line = head.lines().next().unwrap_or("");
                let target = request_target(first_line).unwrap_or("");

                // Ignore incidental non-callback requests (favicon, etc.) but
                // still service the socket so the browser isn't left hanging.
                if target == "/favicon.ico" || target.is_empty() {
                    write_response(&mut stream, 204, "No Content", "").await;
                    continue;
                }

                let parsed = parse_callback_target(target);
                match &parsed {
                    Ok(_) => write_response(&mut stream, 200, "OK", SUCCESS_BODY).await,
                    Err(_) => write_response(&mut stream, 400, "Bad Request", FAILURE_BODY).await,
                }
                return parsed;
            }
        };

        tokio::time::timeout(timeout, accept)
            .await
            .map_err(|_| OAuthError::CallbackTimeout)?
    }
}

const SUCCESS_BODY: &str = "<!doctype html><html><body style=\"font-family:system-ui;padding:2rem\">\
<h2>Jarvis is linked to ChatGPT.</h2><p>You can close this tab and return to Jarvis.</p></body></html>";

const FAILURE_BODY: &str =
    "<!doctype html><html><body style=\"font-family:system-ui;padding:2rem\">\
<h2>Sign-in did not complete.</h2><p>Return to Jarvis and try linking again.</p></body></html>";

/// Best-effort write of a tiny HTTP/1.1 response; the connection is closed after.
/// Failures here are non-fatal (the credential exchange has what it needs).
async fn write_response(stream: &mut tokio::net::TcpStream, status: u16, reason: &str, body: &str) {
    let response = format!(
        "HTTP/1.1 {status} {reason}\r\nContent-Type: text/html; charset=utf-8\r\n\
Content-Length: {len}\r\nConnection: close\r\n\r\n{body}",
        len = body.len(),
    );
    let _ = stream.write_all(response.as_bytes()).await;
    let _ = stream.flush().await;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn request_target_extracts_path_and_query() {
        assert_eq!(
            request_target("GET /auth/callback?code=X&state=Y HTTP/1.1"),
            Some("/auth/callback?code=X&state=Y")
        );
    }

    #[test]
    fn request_target_handles_garbage() {
        assert_eq!(request_target(""), None);
        assert_eq!(request_target("GET"), None);
    }

    #[test]
    fn parses_code_and_state() {
        let params = parse_callback_target("/auth/callback?code=abc123&state=xyz789").unwrap();
        assert_eq!(params.code, "abc123");
        assert_eq!(params.state, "xyz789");
    }

    #[test]
    fn parses_percent_encoded_values() {
        // A code containing a '/' and '+' arrives percent-encoded.
        let params = parse_callback_target("/auth/callback?code=a%2Fb%2Bc&state=s1").unwrap();
        assert_eq!(params.code, "a/b+c");
        assert_eq!(params.state, "s1");
    }

    #[test]
    fn missing_state_is_rejected() {
        let err = parse_callback_target("/auth/callback?code=abc").unwrap_err();
        assert!(matches!(err, OAuthError::CallbackMissingParams));
    }

    #[test]
    fn missing_code_is_rejected() {
        let err = parse_callback_target("/auth/callback?state=abc").unwrap_err();
        assert!(matches!(err, OAuthError::CallbackMissingParams));
    }

    #[test]
    fn empty_values_are_rejected() {
        let err = parse_callback_target("/auth/callback?code=&state=").unwrap_err();
        assert!(matches!(err, OAuthError::CallbackMissingParams));
    }

    #[test]
    fn provider_error_is_surfaced() {
        let err = parse_callback_target("/auth/callback?error=access_denied&state=s").unwrap_err();
        match err {
            OAuthError::AuthorizationDenied(reason) => assert_eq!(reason, "access_denied"),
            other => panic!("expected AuthorizationDenied, got {other:?}"),
        }
    }

    #[tokio::test]
    async fn wait_times_out_when_no_callback_arrives() {
        // Bind an ephemeral port and confirm the timeout path fires promptly
        // rather than hanging or panicking.
        let server = CallbackServer::bind(0).await;
        // Port 0 asks the OS for a free port; bind must succeed.
        let server = server.expect("bind ephemeral port");
        let result = server.wait(Duration::from_millis(50)).await;
        assert!(matches!(result, Err(OAuthError::CallbackTimeout)));
    }
}
