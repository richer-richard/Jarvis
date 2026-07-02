# Rust Core Migration

`rust-core/` is a from-scratch Rust replacement for the Python worker
(`jarvis/*.py`), intended to eventually run alongside the existing Swift menu-bar
shell as the second half of a two-compiled-binary native macOS app, replacing
the Python interpreter + `~/.jarvis.env`/Ollama/Groq environment-variable
plumbing with a single statically-typed, notarizable binary.

This is a phased migration, not a rewrite done in one pass. `jarvis/*.py`
remains the source of truth and stays running in production until each ported
slice reaches parity and is verified.

## Status as of 2026-07-02

**Ported (real logic, faithfully mirrors the Python source):**
- `jarvis-config`: `~/.jarvis.env` loading, core env vars (host/port/loopback,
  Groq, Codex incl. the new write-tier toggle/user-name/bundle-id knobs).
  Mirrors `jarvis/config.py`.
- `jarvis-safety`: full `classify_command`/`classify_shell_command` decision
  tree ported to `rust-core/crates/jarvis-safety/src/lib.rs` -- pattern lists,
  shell tokenization (hand-rolled `shlex`-equivalent; no external regex/shlex
  crate was pulled in for this crate), dangerous-token detection, read-only
  allowlists, private-read/reversible-change/external-sensitive
  classification, wake-phrase and codex-status short circuits. 24 tests.
  **Deliberate deviation from `jarvis/safety.py`:** `awk`, `sed`, and `find`
  require typed confirmation (risk level 4) here, even though the current
  Python source still auto-allows them as read-only. This closes a known
  RCE-adjacent gap (these interpreters can run arbitrary code via
  `awk 'BEGIN{system(...)}'`, `find -exec`, GNU `sed` extensions) that was
  found and fixed-then-reverted in an earlier session on this same repo. See
  the deviation note at the top of `jarvis-safety/src/lib.rs`.
- `jarvis-audit`: full redaction port (`SENSITIVE_TEXT_PATTERNS`,
  `STANDALONE_SECRET_PATTERNS`, `SENSITIVE_DETAIL_KEY_PATTERN` via the `regex`
  crate) plus age/byte-cap retention trimming. Mirrors `jarvis/audit.py`.
  `write()` (renamed from the old `write_unredacted()` placeholder) actually
  redacts before appending. 11 tests.
- `jarvis-server`: `/api/health`, `/api/mode` (GET+POST), `/api/policy`,
  `/api/tools` (real registry reflecting what's actually implemented in
  `jarvis-tools`), `/api/self-check` (runtime-provable subset: host-header
  guard active, audit log writable, codex binary on PATH). Loopback
  Host-header middleware wired as real `axum::middleware::from_fn_with_state`
  on every route (DNS-rebinding protection, mirrors
  `jarvis/server.py`'s `_host_header_allowed`). 8 tests.
- `jarvis-tools::codex`: real async subprocess execution via
  `tokio::process::Command` for both the read-only and write-capable Codex CLI
  tiers, plus a separate always-read-only `chat()` path (mirrors
  `run_codex_delegate`/`start_codex_delegate_job`/`run_codex_chat` in
  `jarvis/tools.py`). Timeout-enforced via `tokio::time::timeout`,
  `--output-last-message` file read back, stdout/stderr truncation matching
  Python's ballpark. The write-capable tier requires a `ConfirmationToken`
  folded into a `DelegateMode::WriteCapable(token)` enum variant -- the illegal
  state (write-capable with no proof of confirmation) is unrepresentable at
  the type level. 17 tests.
- `jarvis-oauth`: NEW crate (not a Python port -- there is no Python source for
  this; it's a clean-room implementation of `docs/DIRECT_MODEL_OAUTH_DESIGN.md`).
  An independent "Sign in with ChatGPT" OAuth client so Jarvis's FAST path can
  eventually call the user's ChatGPT subscription directly instead of spawning
  `codex exec` per turn. Modules: `pkce` (S256 verifier/challenge), `authorize`
  (authorize-URL builder + the shared public `client_id`/scopes/endpoints),
  `callback` (loopback listener + pure request-line/query parser), `token`
  (code->token + refresh exchanges, request bodies built by pure functions),
  `account` (decode-only `chatgpt_account_id` extraction from the id_token JWT --
  no signature verification, since the token arrives over TLS from OpenAI's own
  token endpoint), `storage` (atomic write to `~/.jarvis/auth/openai_oauth.json`,
  file `0600` / dir `0700`), and the `lib.rs` orchestration (`login`/`load`/
  `access_token`/`logout` + the 5-minute/8-day refresh-window math). Uses `reqwest`
  (json feature, native-tls -> macOS Security.framework, no OpenSSL), `sha2`,
  `base64`, `rand`. **Deliberately independent of Codex:** never reads/writes
  `~/.codex/auth.json`, and binds its own dedicated callback port (default 1717,
  env `JARVIS_OAUTH_CALLBACK_PORT`) instead of Codex's `1455`, to avoid login
  collisions. Callback listener is a hand-rolled one-shot `tokio` TCP listener
  rather than an `axum` route -- chosen for clean accept-parse-reply-return
  semantics and to keep the query parser a pure unit-testable function (see the
  module doc for the rationale). 41 tests.

  **What is genuinely verified vs. what needs a live login:** All the
  deterministic logic is unit-tested and passing -- PKCE S256 (incl. the RFC 7636
  test vector), authorize-URL construction (every required param + percent
  encoding + byte-stable redirect_uri), callback request parsing (code/state
  extraction, percent-decoding, missing-param and provider-`error=` handling,
  loopback timeout), JWT `account_id` extraction (nested-claim happy path +
  malformed/missing-claim errors with no panics), storage round-trip with an
  actual `0600`/`0700` permission assertion via `std::fs::metadata`, and the
  refresh-window math (3-min-to-expiry -> refresh, 2-hr -> no, 9-days-stale ->
  proactive refresh). The token-endpoint *request bodies* are unit-tested as pure
  functions, but the **live network round trip cannot be verified in this
  sandbox** (no browser, no real ChatGPT session): the actual `/authorize`
  browser redirect and the `/token` code-exchange + refresh against
  `auth.openai.com` need Richard to run one real interactive login once to
  confirm end-to-end (and to confirm OpenAI accepts the port-1717 loopback
  redirect_uri for the public `client_id`). No Responses-API caller is built yet
  -- this crate only mints and maintains the credential; the FAST-path adapter
  that consumes `access_token()` + `account_id` is a separate future piece.

**Not yet ported (explicitly out of scope for this pass):**
- `/api/readiness`, `/api/preflight`, `/api/plan`, `/api/command` -- the
  actual planner/tool-execution loop. This is the single biggest remaining
  piece; it needs `jarvis/planner.py` (5.4k lines) ported first.
- `jarvis/planner.py` (5.4k lines, intent routing) -- no Rust equivalent yet.
- The remaining ~22k lines of `jarvis/tools.py` beyond Codex delegation
  (email, calendar, Teams, Music, browser automation, diagnostics, etc.).
- Async Codex job tracking (`start_codex_delegate_job`'s fire-and-forget
  `CODEX_JOBS` registry + persistence) -- `jarvis-tools::codex` only has the
  synchronous execute path so far.
- Codex proxy env plumbing (`_codex_child_env`) and prompt shaping
  (`_clean_codex_prompt`/`_codex_fast_prompt`) -- prompts pass through
  `jarvis-tools::codex` verbatim today.
- `jarvis/wake.py` (text-only wake-phrase simulation; the real wake-word
  listener lives in Swift and needs no Rust port).
- `jarvis/injection.py` (prompt-injection scanner).
- `jarvis/piper_speaker.py` / `piper_warm_worker.py` (local TTS).

## Running

```
cd rust-core
cargo build
cargo test --workspace
cargo run -p jarvis-server
```

The server binds `127.0.0.1:8765` by default (same as the Python worker) --
do not run both simultaneously against the same port.

## Verification gates (all green as of this writing)

```
cargo fmt --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace   # 103 passed, 0 failed across 6 crates
```
