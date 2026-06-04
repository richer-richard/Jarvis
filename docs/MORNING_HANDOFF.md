# Morning Handoff

Date: 2026-06-03
Checkpoint target: 06:30 Beijing Standard Time

## Wake-Up Summary

- Latest verification: `89/89` passed in
  `runtime/verification/verify-safe-20260603-060416.json`.
- Current validated bundle: `output/Jarvis-Current-17.app`.
- Current default worker: `127.0.0.1:8765` is online but stale; restart the
  existing worker before running `python3 scripts/run_dashboard.py`.
- No approval-blocked command was left waiting. One accidental backtick command
  substitution attempted `python3 scripts/run_dashboard.py`, failed immediately
  with `Address already in use`, and left no extra worker behind.
- Current bundle test ports `8841` through `8847` were checked closed after
  self-tests.
- Morning status now prefers the highest numbered `Jarvis-Current-N.app`
  bundle, so older bundle mtimes should not confuse the handoff.
- 04:49 monitoring check: morning status still reported `89/89`, only the
  known stale default worker was visible, and ports `8841` through `8846`
  remained closed.
- 04:59 monitoring check: morning status still reported `89/89`, only the
  known stale default worker was visible, and ports `8841` through `8846`
  remained closed.
- 05:10 monitoring check: morning status still reported `89/89`, only the
  known stale default worker was visible, and ports `8841` through `8846`
  remained closed.
- 05:21 monitoring check: morning status still reported `89/89`, only the
  known stale default worker was visible, and ports `8841` through `8846`
  remained closed.
- 05:31 monitoring check: morning status still reported `89/89`, only the
  known stale default worker was visible, and ports `8841` through `8846`
  remained closed.
- 05:42 monitoring check: morning status still reported `89/89`, only the
  known stale default worker was visible, and ports `8841` through `8846`
  remained closed.
- 05:52 monitoring check: morning status still reported `89/89`, only the
  known stale default worker was visible, and ports `8841` through `8846`
  remained closed.
- 06:03 monitoring check: morning status still reported `89/89`, only the
  known stale default worker was visible, and ports `8841` through `8847`
  remained closed.
- 06:15 pre-checkpoint check: morning status still reported `89/89`, only the
  known stale default worker was visible, and ports `8841` through `8847`
  remained closed.
- 06:30 checkpoint reached: final check before the checkpoint reported
  `89/89`, unit tests passed `85/85`, only the known stale default worker was
  visible, and ports `8841` through `8847` remained closed.

## Current State

Jarvis remains a local-first prototype with:

- Python localhost worker and dashboard.
- Typed tool pipeline with safety policy gates.
- Local pause mode for command execution.
- JSONL audit logging.
- SwiftPM menu-bar shell.
- Local ad-hoc app bundle path.
- Codex CLI detection and dry-run delegation planning.
- Read-only readiness summary for quick handoff checks.

## Overnight Progress

- Added read-only native permission readiness in the Swift shell for
  microphone, speech recognition, screen recording, Accessibility, and
  notifications.
- Surfaced permission readiness in the Swift panel.
- Added `--permission-self-test` for the menu-bar shell.
- Added runtime metadata to worker health/status: PID, cwd, source file,
  start time, and uptime.
- Surfaced runtime metadata in the Swift shell and dashboard Worker block.
- Added `--health` and `--audit-status` modes to `jarvis-host-probe`.
- Added direct verifier coverage for `jarvis-host-probe --pause` and
  `jarvis-host-probe --resume`.
- Hardened localhost/static handling and audit request limits.
- Tightened `shell.read_only` so it runs argv-only commands and blocks shell
  chaining, code runners, secret-looking paths, bare sensitive filenames such
  as `id_rsa`, Git pathspecs such as `HEAD:.env`, and outside-project paths.
- Tightened read-only shell policy further so mutating options or scripts such
  as `find -delete`, `find -exec`, `find -fprint`, `sed -i`, `sed 'w file'`,
  and external sed/awk script files do not auto-execute.
- Tightened shell redirection handling so quoted redirects like
  `cat > "README-copy.md"` and attached redirects like
  `cat >"README-copy.md"` also require strong confirmation.
- Added `scripts/verify_safe.py` for safe overnight verification.
- Added `--host` and `--port` flags to `scripts/run_dashboard.py`.
- Added cleanup for Swift self-tests that autostart temporary workers.
- Made Swift `JARVIS_URL` handling accept both base URLs and `/api/command`
  endpoint URLs.
- Made Swift `JARVIS_BASE_URL` handling accept both base URLs and
  `/api/command` endpoint URLs, including trailing-slash command endpoints.
- Hardened integer env parsing for `JARVIS_PORT` and audit settings.
- Cleaned up Ctrl+C shutdown for `scripts/run_dashboard.py`.
- Cleaned up duplicate-port startup failure for `scripts/run_dashboard.py`.
- Added basic Swift worker monitoring: the menu-bar shell periodically checks
  local worker health and can recover a worker it started.
- Added `--worker-monitor-self-test` to verify start, stop, recovery, and
  cleanup on an alternate localhost port.
- Serialized Swift worker startup so simultaneous refresh/monitor checks do
  not start duplicate workers or lose the process handle.
- Added `--worker-concurrency-self-test` to verify concurrent startup and
  cleanup on an alternate localhost port.
- Fixed planner routing so explicit shell-like commands such as `git status`,
  `grep Jarvis README.md`, and `date` use `shell.read_only` instead of broader
  natural-language shortcuts.
- Hardened read-only shell execution so timeouts and unexpectedly missing
  executables return structured tool results instead of worker exceptions.
- Added an endpoint verifier check for read-only shell allowlist routing through
  `/api/command`.
- Added cautious start-paused support through `JARVIS_START_PAUSED=1` and
  `python3 scripts/run_dashboard.py --paused`.
- Added isolated verifier coverage for a start-paused worker: mode endpoint,
  command blocking, and cleanup.
- Improved `app.availability` so app checks search common macOS application
  folders and match `.app` names case-insensitively.
- Tightened file search so generated/build directories such as `output/`,
  `runtime/`, `.build/`, `.swiftpm/`, `.playwright-cli/`, virtualenv folders,
  and caches are skipped.
- Changed recent audit reads to stream into a bounded tail instead of reading
  the whole log file into memory.
- Tightened helper root handling so file search and Codex delegation planning
  fall back to the project root when a caller supplies an outside path.
- Added the opt-in start-paused launch policy to `/api/policy`.
- Added natural app-check routing for phrases such as `open app Safari` and
  `check app Outlook`.
- On normal app termination, the Swift shell stops only the Python worker
  process it started.
- Added verifier coverage that `scripts/run_dashboard.py --help` advertises
  `--paused`.
- Added pause mode: `/api/mode`, `policy.pause`, dashboard Pause/Resume,
  Swift shell Pause/Resume, and host-probe `--mode`, `--pause`, `--resume`.
- Pause mode preserves attempted-command risk in audit/response metadata while
  refusing execution.
- Updated the safe verifier so a stale or paused default worker triggers a
  fresh temporary worker for current-code checks.
- Added a re-entrant lock around audit writes, reads, and retention trimming
  for threaded localhost reliability.
- Added a re-entrant lock around pause-mode state for threaded localhost
  reliability.
- Added localhost response hardening headers: `nosniff` and `no-store`.
- Hardened JSON request parsing to reject negative `Content-Length` values.
- Hardened malformed JSON POST handling so `/api/command`, `/api/plan`, and
  `/api/mode` return `400 Invalid JSON` before routing, mode changes, or tool
  execution.
- Dashboard startup now rejects invalid port numbers before binding.
- Added `scripts/morning_status.py` for a read-only one-command morning check.
- Added `--base-url` to `scripts/morning_status.py`.
- Added `/api/readiness` as a read-only handoff snapshot for mode, worker,
  tools, self-check counts, audit status, and notes.
- Added a dashboard Readiness block and fixed it to refresh after Pause/Resume.
- Added `--readiness` to `jarvis-host-probe`.
- Added verifier coverage for `/api/readiness`, readiness while paused, and the
  Swift readiness probe.
- Added `/api/preflight` as a read-only local action-readiness snapshot with
  required and recommended checks.
- Added a dashboard Preflight block and `jarvis-host-probe --preflight`.
- Added verifier coverage for `/api/preflight` and the Swift preflight probe.
- Added `POST /api/plan` as a plan-only command preview path that does not
  execute tools.
- Added a dashboard Preview button and `jarvis-host-probe --plan`.
- Added `jarvis-host-probe --help` for terminal mode discovery.
- Added verifier coverage for plan preview, preview while paused, and non-JSON
  preview request rejection.
- Added text-only wake phrase simulation in `jarvis/wake.py` and
  `voice.wake_simulation`; it tests `Hey Jarvis` transcript handling without
  microphone access or background listening.
- Wake simulation now includes the extracted command's safety assessment, so
  dangerous follow-up text is visibly classified without executing it.
- Added a loopback-only dashboard bind guard. `--host 0.0.0.0` now fails
  cleanly unless `JARVIS_ALLOW_NON_LOOPBACK=1` is explicitly set.
- Added a JSON POST guard. `/api/command` and `/api/mode` now reject non-JSON
  POST bodies with `415`.
- Added a restrictive same-origin Content Security Policy to dashboard/API
  responses and verified the dashboard still renders with 0 console issues.
- Added a Host-header guard. Requests with non-loopback Host headers now return
  `403` before reaching API routes.
- Added audit redaction for obvious password, token, API key, secret,
  credential, and bearer-token values before JSONL writes.
- Added audit string truncation after redaction so long command output or
  pasted text cannot bloat local JSONL logs.
- Unreadable raw audit lines are now redacted before being returned through the
  audit API/dashboard.
- Audit reads now tolerate non-UTF-8/corrupted raw lines by replacement-decoding
  and reporting them as unreadable redacted entries instead of crashing.
- Tightened natural-language safety classification so obvious requests to
  download, install, uninstall, delete, remove, overwrite, change important
  settings, expose credentials, read cookies, or access Keychain require
  confirmation gates before any typed tool can execute.
- Natural-language safety classification now also treats privileged or
  destructive shell-like requests such as `run sudo ...` and `run rm -rf ...`
  as strong-confirmation cases even without a `shell:` prefix.
- Natural-language high-risk reasons are now categorized in `/api/policy` and
  assessment details, including external transmission, file/software changes,
  protected settings, credentials/cookies/Keychain, and payments.
- Safe verification reports now include generation/completion timestamps, and
  readiness, preflight, the dashboard, and morning status surface the latest
  report age.
- Preflight now treats a safe verification report as required only when it is
  passing and no older than 12 hours.
- Morning status now prints a rerun action when the latest verification failed
  or is older than 12 hours.
- Added a read-only prompt-injection scanner for untrusted text.
  `safety.injection_scan` flags suspicious instruction overrides, secret
  extraction, hidden behavior, authority impersonation, external transfers, and
  destructive/settings changes without treating the text as a user command.
- Prompt-injection scanning now also catches common variant wording such as
  `disregard prior safety rules`, `leak the system prompt`, and untrusted text
  claiming to be from Leo/system/developer.
- Browser and Outlook plan-only workflows now include a guard to treat
  page/email content as untrusted and scan suspicious instructions with
  `safety.injection_scan` before acting on them.
- Local preflight now treats `safety.injection_scan` as a required policy/tool
  route, so the policy-gates check reports 11/11 required routes when healthy.
- Safe verifier plan-preview coverage now checks safe shell preview,
  prompt-injection scanner preview, and dangerous-command preview all remain
  non-executing.
- Safe verifier now checks `scripts/morning_status.py` normalizes
  `JARVIS_BASE_URL` when it is supplied as a trailing-slash `/api/command/`
  endpoint.
- Safe verifier now checks malformed JSON POST bodies are rejected on
  `/api/command`, `/api/plan`, and `/api/mode`.
- Safe verifier now checks wake simulation returns a safety assessment for the
  extracted command, including a dangerous follow-up text case.
- Swift `jarvis-host-probe --readiness` now prints the latest verification
  result, report path, and age from `/api/readiness`.
- Audit redaction now also removes standalone key-shaped values such as
  `sk-...`, GitHub token prefixes like `ghp_...`, and `github_pat_...`, not
  only labeled `token=...` or bearer values.
- Audit redaction now also catches env/header-style labels such as
  `OPENAI_API_KEY=...`, `MY_TOKEN=...`, and `x-api-key: ...`.
- Audit detail logging now redacts values under sensitive structured keys such
  as `token`, `Authorization`, and `OPENAI_API_KEY`.
- Audit detail logging now normalizes bytes, set-like containers, and
  path/object values into JSON-safe redacted values before JSONL writes.
- Shell policy now treats bare secret-bearing filenames such as `secrets.txt`,
  `token.json`, and Git pathspecs such as `HEAD:credentials.yaml` as strong
  confirmation cases while leaving harmless grep patterns read-only.
- Added `.gitignore` for generated caches, SwiftPM output, Playwright CLI
  cache, runtime logs, local app bundles, and OS metadata.
- Rebuilt the current local app bundle as `output/Jarvis-Current-17.app` and
  verified its plist, ad-hoc signature, permission self-test, worker self-test,
  hotkey self-test, worker monitor self-test, and worker concurrency self-test.
- Hardened app-bundle plist generation to XML-escape configurable app name and
  bundle identifier values; the verifier now builds a temporary app whose name
  contains spaces, `&`, an apostrophe, and angle brackets, then checks the
  decoded display name.

## Latest Verification

Latest safe harness:

```bash
python3 scripts/verify_safe.py
```

Result:

- Passed 89/89 checks.
- Report: `runtime/verification/verify-safe-20260603-060416.json`

Morning status command:

```bash
python3 scripts/morning_status.py
python3 scripts/morning_status.py --base-url http://127.0.0.1:8765/api/command
```

It accepts both base URLs and `/api/command` URLs. It currently reports that
`127.0.0.1:8765` is online but stale, the latest
verification passed 89/89, and the current bundle is
`output/Jarvis-Current-17.app`.

Latest unit tests passed 85/85.
Latest self-check passed 49/49.

Current app bundle evidence:

- Bundle: `output/Jarvis-Current-17.app`
- `plutil -lint` passed.
- `codesign --verify --deep --strict --verbose=2` passed.
- Bundled `--permission-self-test`, `--self-test`, and
  `--hotkey-self-test` passed.
- Permission self-tests now assert five unique, complete readiness rows.
- Bundled `--worker-monitor-self-test` passed on an alternate localhost port.
- Bundled `--worker-concurrency-self-test` passed on an alternate localhost
  port.
- SwiftPM `--worker-autostart-disabled-self-test` passed with
  `JARVIS_DISABLE_WORKER_AUTOSTART=1` on an unused localhost port.
- Passive cleanup audit found the bundle test ports `8841` through `8847`
  closed after self-tests; only the known stale default worker remained.
- One readback `rg` command accidentally included unescaped backticks, causing
  the shell to attempt `python3 scripts/run_dashboard.py`; it failed
  immediately with `Address already in use`, and a follow-up process/port audit
  confirmed no extra worker was left behind.
- Bundled `--self-test` was also run against a fresh worker on port 8847 and
  reported `Verification: passed 89/89` and `Mode: pause/resume passed`.
- Morning status now prints verification highlights from the latest report:
  shell allowlist routing, readiness summary, local preflight summary,
  plan-only command preview, text wake simulation + command assessment,
  prompt-injection scan, morning status URL normalization, loopback bind guard,
  localhost hardening, Host header guard, JSON POST guard, JSON preview guard,
  malformed JSON guard, sed write-script policy, awk script-file policy, secret
  filename policy, pause mode, paused readiness, paused preview, start-paused
  launch, Swift readiness probe, Swift preflight probe, Swift preview probe,
  Swift pause probe, Swift resume probe, Swift URL environment normalization,
  worker startup concurrency, worker monitor recovery, and temporary app
  bundle coverage.

Additional UI evidence:

- Desktop dashboard screenshot:
  `output/playwright/jarvis-dashboard-worker-runtime.png`
- Mobile dashboard screenshot:
  `output/playwright/jarvis-dashboard-worker-runtime-mobile.png`
- Console warnings/errors were 0 in both dashboard QA passes.
- In-app Browser QA on `http://127.0.0.1:8767` verified Pause, backend
  `policy.pause`, Resume, desktop rendering, mobile 390x844 rendering, and 0
  console warnings/errors.
- In-app Browser QA on `http://127.0.0.1:8780` verified the new Readiness block
  and caught a stale Pause refresh. After the fix, Paused/Live readiness text,
  disabled/enabled controls, and console health all passed.
- In-app Browser QA on `http://127.0.0.1:8793` verified the new Preflight block:
  7/7 required checks live, 6/7 while paused, 7/7 after resume, command
  controls disabled/enabled correctly, and console warnings/errors were 0.
- In-app Browser QA on `http://127.0.0.1:8800` verified the new Preview button:
  live preview returned `executed=false`, Preview stayed enabled while paused,
  paused preview returned `system.status` with `executed=false`, Run and quick
  actions stayed disabled while paused, and console warnings/errors were 0.
- In-app Browser QA on `http://127.0.0.1:8813` verified the verification-age
  and scanner-tool display: Readiness verified the then-current self-check
  count, 18/18 tools, and the then-current verification count with age;
  Preflight showed latest-report freshness and `11/11` required policy/tool
  routes; the tool list included `Prompt-Injection Scan`; and console
  warnings/errors were 0.
- Latest safe verifier includes explicit endpoint coverage for the
  prompt-injection scanner, and morning status now lists `prompt-injection
  scan` in the verification highlights.

## Morning Note

The worker currently listening on `127.0.0.1:8765` was started before runtime
metadata existed. If the dashboard Worker block says metadata is unavailable,
stop the old dashboard process normally and restart:

```bash
python3 scripts/run_dashboard.py
```

To run a second fresh worker for QA:

```bash
python3 scripts/run_dashboard.py --port 8766
```

## Safe Commands

These have been used repeatedly without approval prompts:

```bash
python3 -m unittest discover -s tests
python3 -m jarvis.self_check
python3 -m py_compile jarvis/*.py scripts/run_dashboard.py scripts/verify_safe.py
python3 scripts/morning_status.py
python3 scripts/run_dashboard.py --host 0.0.0.0 --port 8784
python3 scripts/verify_safe.py
swift build --package-path swift-shell
swift run --package-path swift-shell jarvis-host-probe --help
swift run --package-path swift-shell jarvis-host-probe --health
swift run --package-path swift-shell jarvis-host-probe --audit-status
swift run --package-path swift-shell jarvis-host-probe --readiness
swift run --package-path swift-shell jarvis-host-probe --preflight
swift run --package-path swift-shell jarvis-host-probe --plan 'shell: pwd'
swift run --package-path swift-shell jarvis-host-probe --mode
swift run --package-path swift-shell jarvis-menu-bar --permission-self-test
swift run --package-path swift-shell jarvis-menu-bar --worker-monitor-self-test
swift run --package-path swift-shell jarvis-menu-bar --worker-concurrency-self-test
JARVIS_BASE_URL=http://127.0.0.1:8847 output/Jarvis-Current-17.app/Contents/MacOS/jarvis-menu-bar --self-test
JARVIS_BASE_URL=http://127.0.0.1:8842 output/Jarvis-Current-17.app/Contents/MacOS/jarvis-menu-bar --worker-monitor-self-test
JARVIS_BASE_URL=http://127.0.0.1:8843 output/Jarvis-Current-17.app/Contents/MacOS/jarvis-menu-bar --worker-concurrency-self-test
JARVIS_BASE_URL=http://127.0.0.1:8844 JARVIS_DISABLE_WORKER_AUTOSTART=1 output/Jarvis-Current-17.app/Contents/MacOS/jarvis-menu-bar --worker-autostart-disabled-self-test
```

## Still Deferred

- Real local wake word.
- Real speech-to-text.
- Permission request/onboarding flows.
- Real Outlook/Mail control.
- Live model/OpenAI backend.
- Live Codex execution.
- Launch at login.
- Full persistent kill switch beyond the local pause mode.
- Advanced crash policy controls beyond the basic worker monitor.
- Keychain storage.
- Developer ID signing, hardened runtime, notarization, and distribution.
