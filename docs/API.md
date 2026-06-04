# Local API Reference

Jarvis currently exposes a loopback-only HTTP API for the dashboard, Swift host
probe, and local verification harness. It is a prototype API, not a network
service.

Default base URL:

```text
http://127.0.0.1:8765
```

POST endpoints require:

```text
Content-Type: application/json
```

Malformed JSON is rejected with `400 Invalid JSON` before command routing,
preview routing, mode changes, or tool execution.

## Read-Only Status

- `GET /api/health`
  - Reports worker health, mode, Python/platform metadata, Codex CLI status,
    and runtime PID/source/uptime when the running worker is current.
- `GET /api/mode`
  - Reports whether command execution is Live or Paused.
- `GET /api/policy`
  - Reports risk labels, confirmation rules, shell policy, network policy,
    natural-language safety gates, request policy, and audit policy.
- `GET /api/tools`
  - Lists typed tools and policy gates exposed to the planner.
- `GET /api/readiness`
  - Aggregates mode, worker status, tool availability, self-check counts, audit
    health, latest safe-verification summary/age, and notes.
- `GET /api/preflight`
  - Reports required and recommended checks for local action readiness without
    requesting permissions, including a passing safe-verification report no
    older than 12 hours.
- `GET /api/self-check`
  - Runs local deterministic self-checks.
- `GET /api/audit/status`
  - Reports audit path, event count, unreadable line count, retention target,
    and size cap.
- `GET /api/audit?limit=8`
  - Returns recent audit events, with `limit` bounded by server policy.

## Commands

- `POST /api/command`
  - Runs the planner through policy gates.
  - Executes only allowed prototype tools.
  - While paused, always returns `policy.pause` without tool execution.

Example:

```bash
curl -sS -X POST http://127.0.0.1:8765/api/command \
  -H 'Content-Type: application/json' \
  -d '{"command":"status"}'
```

- `POST /api/plan`
  - Previews routing and confirmation requirements without executing tools.
  - Remains available while command execution is paused.

Example:

```bash
curl -sS -X POST http://127.0.0.1:8765/api/plan \
  -H 'Content-Type: application/json' \
  -d '{"command":"shell: pwd"}'
```

## Control

- `POST /api/mode`
  - Pauses or resumes command execution.
  - Health, policy, tools, readiness, preflight, self-check, audit, and preview
    surfaces remain available while paused.

Example:

```bash
curl -sS -X POST http://127.0.0.1:8765/api/mode \
  -H 'Content-Type: application/json' \
  -d '{"paused":true,"reason":"manual safety pause"}'
```

## Special Prototype Routes

- `wake: Hey Jarvis check status`
  - Sent through `/api/command`, this exercises text-only wake phrase
    simulation through `voice.wake_simulation`.
  - The response includes `command_assessment` for the extracted follow-up
    command, but does not execute that follow-up separately.
  - It does not access the microphone, capture audio, or start a background
    listener.
- `scan untrusted: Ignore previous system instructions`
  - Sent through `/api/command`, this exercises the read-only
    `safety.injection_scan` tool.
  - It flags suspicious untrusted text for review without following that text
    as a user instruction.

## Security Notes

- The dashboard binds only to loopback hosts unless
  `JARVIS_ALLOW_NON_LOOPBACK=1` is explicitly set.
- Requests with non-loopback `Host` headers are rejected.
- Static files are constrained to `jarvis/static`.
- Request bodies are size-bounded.
- Malformed JSON on command, preview, and control POST endpoints is rejected
  before routing.
- Audit logs redact obvious secret values, env/header-style secret labels,
  sensitive structured detail-key values, standalone OpenAI/GitHub-looking key
  shapes, and JSON-unsafe detail values, truncate very long strings after
  redaction, and redact unreadable or non-UTF-8 raw audit lines before display.
