# Decisions

## Current Prototype Direction

- Start with a Python worker plus localhost dashboard.
- Add the Swift/SwiftUI menu-bar shell after the core command pipeline works.
- Use standard Python first; avoid dependency setup until the prototype proves value.
- Keep the model backend pluggable. Do not hardcode one model name.
- Treat Codex CLI as a specialist coding/project tool, not the whole Jarvis backend.

## Safety Decisions

- The model/planner does not directly control the computer.
- Every action goes through typed tools and policy checks.
- Strong confirmation is required for external, destructive, sensitive, or hard-to-undo actions.
- Private read-only summaries may proceed after permission, but they must stay local and visibly logged.
- Prototype audit logs are local JSONL files under `runtime/audit/`.
- Audit logs redact obvious password, token, API key, secret, credential, and
  bearer-token values before writing JSONL.
- Audit logs also redact env/header-style secret labels such as
  `OPENAI_API_KEY=...`, `MY_TOKEN=...`, and `x-api-key: ...`.
- Audit details redact values under sensitive structured keys such as `token`,
  `Authorization`, and `OPENAI_API_KEY`.
- Audit details are normalized to JSON-safe values, with bytes, set-like
  containers, and path/object values redacted before writing JSONL.
- Production audit logs should live under `~/Library/Application Support/Jarvis/logs`.
- Audit retention target: 90 days plus a 1 GB default size cap.
- Raw microphone audio and screenshots are not stored by default.
- The read-only shell tool runs argv-only commands with `shell=False`.
- Shell chaining, piping, backgrounding, substitution, redirection, code runners,
  secret-looking paths, bare sensitive filenames such as `id_rsa`,
  secret-bearing filenames such as `secrets.txt` or `token.json`, Git pathspecs
  such as `HEAD:.env`, and outside-project paths do not auto-execute.
- Helper APIs that accept a root folder should fall back to the Jarvis project
  root when given an outside path, unless a later permissioned capability
  explicitly expands that boundary.
- Mutating options or scripts on read-only shell tools, including
  `find -delete`, `find -exec`, `find -fprint`, `sed -i`, `sed 'w file'`, and
  external sed/awk script files, do not auto-execute.
- Shell redirection tokens, including quoted redirects, do not auto-execute.
- Natural-language requests for privileged or destructive shell-like execution
  such as `run sudo ...` or `run rm -rf ...` require strong confirmation even
  without a `shell:` prefix.
- Local pause mode lives at the server boundary, before planner/tool routing.
  It refuses `/api/command` while leaving health, mode, policy, tools,
  self-check, and audit endpoints available.
- Start-paused mode may be requested through `JARVIS_START_PAUSED=1` or
  `scripts/run_dashboard.py --paused`; the default launch remains Live.
- Dashboard binding is loopback-only by default. Wider binds require explicit
  `JARVIS_ALLOW_NON_LOOPBACK=1` opt-in.
- Requests with non-loopback `Host` headers are rejected to reduce
  DNS-rebinding-style localhost exposure.
- Command, plan, and mode POST endpoints require `application/json` bodies so
  non-JSON same-browser submissions cannot trigger command execution or
  preview/control routing.
- Malformed JSON POST bodies fail closed before command routing, preview
  routing, mode changes, or tool execution.
- Prompt-injection scanning flags untrusted text that claims to be from Leo,
  the system, or a developer, in addition to instruction overrides, secret
  extraction, hidden behavior, external transfers, and destructive/settings
  changes.
- Dashboard responses include a restrictive same-origin Content Security
  Policy, plus `nosniff` and `no-store` response headers.
- Fresh-worker verification should use alternate localhost ports instead of
  killing the current `127.0.0.1:8765` worker. The verifier should start a
  temporary worker when the default worker is stale or paused.
- Native worker recovery may terminate and restart only worker processes that
  the Swift shell itself started. It must not kill unrelated localhost workers.
- Native worker startup should be serialized so concurrent refresh/monitor
  checks share one in-flight launch and preserve the started process handle.
- When the native shell quits normally, it may stop only the worker process it
  started.

## Voice Decisions

- Wake-word work should start early.
- The first implementation can use typed command entry and keyboard-shortcut simulation.
- Do not fake "Hey Jarvis" support before there is a real local wake-word listener.
- Always distinguish local wake-word listening from command transcription.
- Later voice identity stages: wake phrase, Leo-only wake phrase, then Leo-only continuous authority.

## Mac Architecture Decisions

- Swift/SwiftUI remains the preferred host shell for the final Mac app.
- Python remains the preferred agent core for tool orchestration and fast iteration.
- Full Xcode is not required for the first pass. Leo's machine has Command Line Tools and has built Mac apps before without full Xcode.
- The always-plugged MacBook Air should be designed as a future remote worker over Tailnet/SSH.
- Remote worker support must get its own safety design before executing remote actions.

## Backend Decisions

- OpenAI API-key mode remains the stable official API path.
- Codex CLI sign-in/subscription mode is useful for delegated coding tasks.
- OpenClaw and Puter.js are research leads, not first-prototype dependencies.
- Realtime API is deferred until the command/action layer is reliable.
