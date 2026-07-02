# Direct-Model OAuth Design — ChatGPT/Codex Subscription for Jarvis FAST Chat

**Status:** Research / design only (no code written for this doc).
**Author:** research pass, 2026-07-02.
**Scope:** Design an *independent* OAuth client so Jarvis's everyday FAST
conversational path can call the user's ChatGPT Plus/Pro subscription directly,
**without** spawning the `codex` CLI subprocess per turn.

> This doc does **not** touch the existing `codex exec ...` delegation
> (`rust-core/crates/jarvis-tools/src/codex.rs`). That shell-out path stays
> exactly as-is and keeps reading `~/.codex/auth.json`. This design is a
> *separate* credential + caller that must not collide with it.

---

## 0. TL;DR recommendation

- **Feasible without OpenAI developer registration.** The "Sign in with ChatGPT"
  OAuth flow uses a single **public, non-configurable client_id**
  (`app_EMoamEEZ73f0CkXaXp7hrann`) that every third-party tool reuses (OpenCode,
  OpenClaw, Hermes). There is no third-party app-registration mechanism, so
  Jarvis reuses the same public client_id. This is the crux, and it checks out.
- **Build it in Rust** (`rust-core/`), as a new `jarvis-oauth` crate. No
  OAuth/crypto maturity gap in the Rust ecosystem for this.
- **Store credentials at `~/.jarvis/auth/openai_oauth.json` (mode 0600)** — a
  path that cannot collide with `~/.codex/auth.json`. Mirrors how Hermes keeps
  `~/.hermes/auth.json` independent of `codex login`.
- **Do NOT depend on the `hermes` or `openclaw` binaries at runtime.** Reimplement
  the ~200 lines of OAuth logic from the (public, non-copyrightable) protocol
  facts below, citing Codex as reference. All three reference repos are
  permissively licensed if verbatim porting is ever preferred.
- **Compliance is calibrated-yellow, not green.** Personal BYO-subscription use
  is established practice and OpenAI has *not* banned it (unlike Anthropic). But
  OpenAI has never *explicitly blessed* programmatic third-party subscription
  use, and routing a chatty voice loop through Codex 5-hour quota windows carries
  real exhaustion + latency risk. Details in §8.

---

## 1. License verification (fetched from raw LICENSE files, not badges)

| Repo | License | Copyright line (verbatim) | Verified from |
|---|---|---|---|
| `openai/codex` | **Apache License 2.0** | (standard Apache 2.0 header) | `raw.githubusercontent.com/openai/codex/main/LICENSE` |
| `NousResearch/hermes-agent` | **MIT** | `Copyright (c) 2025 Nous Research` | `raw.githubusercontent.com/NousResearch/hermes-agent/main/LICENSE` |
| `openclaw/openclaw` | **MIT** | `Copyright (c) 2026 OpenClaw Foundation` | `raw.githubusercontent.com/openclaw/openclaw/main/LICENSE` |

**What this permits for Jarvis** (a private project likely to be made public per
the roadmap):

- **Apache-2.0 (Codex):** May reproduce/modify/port, including into a
  proprietary/private project, and later relicense the *combined* work under
  Jarvis's own terms **provided** you (a) retain the Apache-2.0 license text and
  any `NOTICE` file contents for the ported portion, (b) preserve copyright/
  attribution notices, and (c) state significant modifications. Apache-2.0 also
  grants an explicit patent license. A maintainer confirmed in
  `openai/codex` Discussion #8338 that forking/modifying is "welcome" under the
  permissive license.
- **MIT (Hermes, OpenClaw):** May reuse/port with only the requirement to retain
  the copyright notice + MIT license text for the ported portion.
- **Practical guidance for the implementer:** The OAuth *endpoints, client_id,
  scopes, PKCE method, and JWT claim paths documented below are protocol facts,
  not copyrightable expression.* The lowest-risk path is a **clean-room
  reimplementation** from this doc (no license obligation triggered at all),
  citing Codex as the reference. If any non-trivial code is copied verbatim from
  a reference repo, add a `docs/THIRD_PARTY_NOTICES.md` (or `NOTICE`) entry
  naming the repo, its license, and copyright line before Jarvis goes public.

---

## 2. OAuth mechanics (confirmed against `codex-rs/login/` source)

All values below were read from the real Rust source
(`openai/codex` @ `main`, `codex-rs/login/src/…`).

**Endpoints (issuer `https://auth.openai.com`):**
- Authorize: `https://auth.openai.com/oauth/authorize`
- Token: `https://auth.openai.com/oauth/token`
  (constant `REFRESH_TOKEN_URL`; both authorize+token derive from
  `DEFAULT_ISSUER = "https://auth.openai.com"`).

**Client ID:** `app_EMoamEEZ73f0CkXaXp7hrann`
- Public, hard-coded default; overridable only via env
  `CODEX_APP_SERVER_LOGIN_CLIENT_ID`. **No third-party registration exists** —
  reused as-is by OpenCode and (per their docs) OpenClaw/Hermes. Jarvis reuses
  it too. This is what makes the whole feature possible without an OpenAI dev
  account.

**Redirect URI (loopback, confirmed):**
`http://localhost:1455/auth/callback` (default port **1455**, fallback **1457**).
Confirms the assumption: a **local loopback HTTP listener on a fixed port**
receives the callback — no public HTTPS endpoint needed. The app opens the
system browser to the authorize URL; the browser redirects back to the local
listener with `?code=…&state=…`.

> **Collision note:** the codex CLI binds :1455 during *its* login only. If a
> Jarvis login and a `codex login` ever overlap, the second binder fails. Jarvis
> should prefer the fallback port or its own dedicated port and set the matching
> `redirect_uri` (the redirect_uri sent to `/authorize` must byte-match the one
> sent to `/token`).

**PKCE:** required. `code_challenge_method = "S256"` (SHA-256 of a
base64url random verifier). Verifier/challenge generated in
`codex-rs/login/src/pkce.rs`.

**Scopes:** `openid profile email offline_access api.connectors.read api.connectors.invoke`
(`offline_access` is what yields the refresh token).

**Extra authorize params observed:** `response_type=code`,
`id_token_add_organizations=true`, `codex_cli_simplified_flow=true`,
plus `code_challenge`, `code_challenge_method=S256`, `client_id`, `redirect_uri`,
`scope`, `state`.

**Auth-code → token exchange:** POST `https://auth.openai.com/oauth/token` with
`grant_type=authorization_code`, `code`, `redirect_uri`, `client_id`,
`code_verifier`. Response yields `id_token`, `access_token`, `refresh_token`.

---

## 3. Token storage format & refresh (from `codex-rs/login/src/auth/storage.rs` + `manager.rs`)

**Codex's own on-disk shape (`AuthDotJson`, at `$CODEX_HOME/auth.json`, mode `0o600`):**
```
AuthDotJson {
  auth_mode,                       // optional
  OPENAI_API_KEY,                  // serde rename of openai_api_key; null for OAuth
  tokens: TokenData {
    id_token,                      // IdTokenInfo (parsed JWT)
    access_token,                  // bearer used on API calls
    refresh_token,
    account_id,                    // Option<String>
  },
  last_refresh,                    // timestamp; drives proactive refresh
  agent_identity, personal_access_token, bedrock_api_key   // not relevant to Jarvis
}
```

**`account_id` derivation:** parsed from the **id_token JWT** claim namespace
`"https://api.openai.com/auth"` → field `"chatgpt_account_id"`. Jarvis needs this
value because the ChatGPT backend scopes requests by account (see §4).

**Refresh flow:**
- POST `https://auth.openai.com/oauth/token` with
  `grant_type=refresh_token`, `client_id=app_EMoamEEZ73f0CkXaXp7hrann`,
  `refresh_token=<stored>`.
- **When to refresh:** eagerly when the access token is within
  **5 minutes** of expiry (`CHATGPT_ACCESS_TOKEN_REFRESH_WINDOW_MINUTES = 5`),
  and proactively if `last_refresh` is older than **~8 days**.
- Refresh-token failures are terminal (expired / reused / revoked / account
  mismatch) and require a fresh interactive login. Jarvis should surface a clear
  "please re-link your ChatGPT account" state rather than silently degrading.

> Jarvis will define its **own** struct (it does not need `bedrock_api_key`
> etc.) — see §5 for the recommended minimal shape. It should NOT read or write
> Codex's `AuthDotJson`.

---

## 4. API endpoint & model routing once authenticated

- Authenticated calls do **not** go to `api.openai.com/v1`. They go to the
  **ChatGPT backend**: base `https://chatgpt.com/backend-api/` (Codex config key
  `chatgpt_base_url`), using the **Responses API** endpoint `/responses`
  (constant `RESPONSES_ENDPOINT = "/responses"` in `codex-rs/core/src/client.rs`;
  Codex composes the account/codex path segment there). Confirm the exact
  concatenated path (`…/backend-api/codex/responses`) against `client.rs` at
  implementation time.
- **Request auth:** `Authorization: Bearer <access_token>` plus an account-scoping
  header carrying the `chatgpt_account_id` extracted in §3.
- **Model routing / the important caveat:** you get the **ChatGPT/Codex-exposed
  models**, not arbitrary raw API models. This matches the earlier finding that
  subscription OAuth maps to the Codex-tuned variants (e.g. `gpt-5.x-codex`)
  rather than a raw `gpt-5.x` API model, and is metered under the **Codex plan
  rate limits** (message/task windows per 5 hours), not pay-per-token API
  billing. Effective limits are tighter than the ChatGPT app itself and are
  shared with the user's own `codex` CLI usage (same subscription).
- **Wire format consequence:** the Responses API request/response shape differs
  from the Chat Completions shape Groq uses. Jarvis's FAST path adapter must
  translate turn history → Responses input and parse streamed Responses events,
  not reuse the Groq/OpenAI-chat serializer verbatim.

---

## 5. Collision avoidance (hard requirement)

Jarvis's existing codex-delegate feature depends on `~/.codex/auth.json`. The new
OAuth session must be **fully independent**, exactly as Hermes deliberately keeps
`hermes auth login codex` (→ `~/.hermes/auth.json`) separate from `codex login`
"to avoid token-refresh races," and as OpenClaw stores ChatGPT/Codex OAuth under
its own provider id `openai`.

**Recommended path:** `~/.jarvis/auth/openai_oauth.json`, file mode `0o600`,
parent dir `0o700`. (For in-repo dev, a gitignored `runtime/auth/…` mirror is
fine — confirm `runtime/` is gitignored before writing secrets there.)

**Recommended minimal on-disk struct (Jarvis's own, not Codex's):**
```
JarvisOpenAiOAuth {
  access_token,
  refresh_token,
  id_token,             // keep raw; re-parse account_id on load
  account_id,           // chatgpt_account_id from the id_token
  expires_at,           // absolute; drives the 5-min refresh window
  last_refresh,         // drives the ~8-day proactive refresh
  client_id,            // record which client_id minted it, for forward-compat
  scopes,
}
```

Never write to `~/.codex/`. Never bind :1455 while a `codex login` might be
running (prefer a dedicated Jarvis callback port).

---

## 6. Where this lives in Jarvis's architecture

**Recommendation: Rust core (`rust-core/`), new crate `jarvis-oauth`.** The Rust
core is the intended-primary path, its async runtime (tokio) and HTTP stack are
already present, and the conversational routing that will consume this belongs
there. There is **no OAuth/crypto maturity gap** in Rust for this job.

Note: today the FAST/conversational routing is still **only in Python**
(`jarvis/planner.py`, `jarvis/tools.py`); the Rust server currently marks
`/api/plan` and `/api/command` as `not_yet_ported`
(`rust-core/crates/jarvis-server/src/main.rs`). So this OAuth crate lands *ahead*
of the ported chat router and gives it a native provider to call. (If the FAST
path must ship in Python first, the same protocol can be implemented there with
`httpx` + `authlib`/`cryptography`; but that duplicates work the Rust port will
redo, so prefer Rust unless there's schedule pressure.)

**Rust crates that cover every primitive (all mature):**
- HTTP client + browser POST: `reqwest` (add to workspace; not yet a dep).
- Loopback callback listener: a tiny `axum`/`hyper` one-route server (axum is
  already a workspace dep) or `tiny_http`.
- PKCE: `sha2` + `base64` (`base64url` no-pad) + `rand`.
- JWT `account_id` extraction: decode-only — `base64` the middle segment +
  `serde_json`; `jsonwebtoken` if signature verification is ever wanted (not
  required to *read* a claim from a token we just received over TLS).
- Expiry math: `chrono` (already a workspace dep).
- Optional at-rest hardening: `keyring` (macOS Keychain) instead of a plaintext
  0600 file — Codex itself offers the OS keychain as an alternative.

**Module shape sketch (no code):**
```
rust-core/crates/jarvis-oauth/
  Cargo.toml                 # + reqwest, sha2, base64, rand
  src/lib.rs                 # public API: login(), load(), access_token(), logout()
  src/pkce.rs                # verifier/challenge (S256)
  src/authorize.rs           # build authorize URL, open browser, hold `state`
  src/callback.rs            # loopback listener on Jarvis's own port
  src/token.rs               # code→token + refresh_token exchange
  src/storage.rs             # ~/.jarvis/auth/openai_oauth.json, 0600, atomic write
  src/account.rs             # parse chatgpt_account_id from id_token JWT

rust-core/crates/jarvis-tools/  (or the future chat-router crate)
  src/openai_direct.rs       # Responses-API caller: base url + /responses,
                             # Bearer + account header, streaming adapter,
                             # asks jarvis-oauth for a fresh access_token per call
```

The chat router selects provider (Groq vs `openai_direct`) behind the existing
FAST-path interface; `jarvis-oauth::access_token()` transparently refreshes
using the §3 rules so callers never see an expired token.

---

## 7. How the precedents do it (for reference + attribution)

- **Hermes Agent (MIT):** exposes `hermes proxy`, a local OpenAI-compatible HTTP
  endpoint backed by the subscription; authenticates via a **device-code** flow
  and stores creds in its **own** `~/.hermes/auth.json`, explicitly independent
  of `codex login` to avoid refresh races. Good model for Jarvis's independence
  requirement.
- **OpenClaw (MIT):** docs state "OpenAI Codex OAuth is explicitly supported for
  use outside the Codex CLI, including OpenClaw workflows." Stores under provider
  id `openai`; supports `--profile-id openai:<name>` for multiple accounts.
  Confirms the reuse-the-public-client_id approach is accepted practice.
- **Device-code alternative:** Codex also ships a device-code flow
  (`codex-rs/login/src/device_code_auth.rs`) for headless machines. Jarvis's
  primary UX is a desktop app with a browser available, so the **loopback
  browser flow (§2) is the right default**; keep device-code as a documented
  fallback for headless/remote-worker setups.

---

## 8. Risk / compliance summary (calibrated, not cheerleading)

**Terms of service — the key asymmetry:** On 2026-02-20 Anthropic changed its
terms to *prohibit* subscription OAuth tokens in third-party tools, with billing
enforcement from 2026-04-04. **OpenAI has not made an equivalent change** — Codex
OAuth in third-party apps still works and is what OpenClaw's current OpenAI
provider relies on. So the specific thing Jarvis wants to do is *not* known to be
prohibited today.

**But the residual ambiguity is real:**
- In `openai/codex` Discussion #8338, an OpenAI maintainer confirmed the CLI is
  Apache-2.0 and forking is welcome, but **declined to explicitly confirm** that
  programmatic third-party ChatGPT-subscription usage (or *commercial*
  BYO-subscription distribution) is sanctioned, and pointed commercial users to
  legal counsel. Treat personal use as low-risk; treat any future public/
  commercial Jarvis release as needing a fresh ToS review + likely a clear
  "bring your own subscription, at your own risk" disclosure.
- The public client_id is not contractually guaranteed to third parties. OpenAI
  could rotate it, tighten redirect/consent, or add attestation at any time
  (Codex already has an `attestation.rs`), which would break Jarvis's login until
  updated. Design for graceful "re-link your account" failure.

**Quota / rate-limit risk (arguably the bigger practical concern):**
- Subscription routing meters against **Codex plan windows** (order-of-magnitude
  hundreds–low-thousands of messages per 5 hours, tighter than the ChatGPT app),
  **shared with the user's own `codex` CLI usage.** A chatty always-on voice
  assistant firing a turn per utterance can exhaust that quota far faster than a
  human coder, and could starve the user's real Codex coding sessions.
  Mitigation: keep Groq as the default FAST path and make direct-model
  **opt-in**; add a per-hour turn budget; fall back to Groq on 429.
- **Latency:** the ChatGPT backend Responses API is tuned for coding agents, not
  sub-second conversational turns — it may not beat Groq for short replies (the
  whole reason to avoid the 2-minute `codex exec` path). **Benchmark round-trip
  latency before committing the FAST path to it**; it may be better suited to a
  "smarter but slower" tier than to the latency-critical default.
- **No usage/cost visibility:** unlike metered API billing, subscription usage
  gives no per-call cost signal; Jarvis can only infer remaining quota from 429s.

**Bottom line:** technically clean and consistent with established third-party
practice for *personal* use; keep it opt-in, quota-guarded, Groq-fallback, and
revisit ToS before any public/commercial launch.

---

## 9. Sources

- `openai/codex` source (`main`): `codex-rs/login/src/{server.rs,pkce.rs,token_data.rs,device_code_auth.rs,auth/storage.rs,auth/manager.rs}`, `codex-rs/core/src/{client.rs,config/mod.rs}`; LICENSE (Apache-2.0).
- `NousResearch/hermes-agent` LICENSE (MIT) + provider/proxy docs.
- `openclaw/openclaw` LICENSE (MIT) + `docs/concepts/oauth.md`, `docs/providers/openai.md`.
- `openai/codex` Discussion #8338 (ToS / forking).
- OpenAI Codex auth + rate-card help articles; reports on the 2026-02/04 Anthropic subscription-OAuth policy change (for the OpenAI-vs-Anthropic contrast).
