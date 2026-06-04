# Prototype Completion Audit

Date: 2026-06-02

Scope: first Python worker plus localhost dashboard prototype. This audit does
not claim the full Jarvis product is complete.

## Requirement Status

| Requirement | Evidence | Status |
| --- | --- | --- |
| Preserve/update project docs | `README.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/SAFETY_MODEL.md`, `docs/DECISIONS.md`, `docs/DEFERRED_FEATURES.md` | Done for first prototype |
| Keep Leo's answered requirements intact | `docs/OPEN_QUESTIONS.md` remains present with responses and follow-up note | Done |
| Track deferred features | `docs/DEFERRED_FEATURES.md` | Done |
| Standard-library local Python app | `jarvis/`, `scripts/run_dashboard.py`; no third-party runtime dependency | Done |
| Swift bridge toward future shell | `swift-shell/Package.swift`, `swift-shell/Sources/JarvisClient/`, `swift-shell/Sources/JarvisHostProbe/main.swift`, `swift run --package-path swift-shell jarvis-host-probe status` | Done for command-line bridge |
| Swift menu-bar shell | `swift-shell/Sources/JarvisMenuBar/`, `swift run --package-path swift-shell jarvis-menu-bar --self-test` | Done for SwiftPM prototype shell; local `.app` packaging also implemented |
| Swift worker startup and recovery supervision | `swift-shell/Sources/JarvisMenuBar/Support/JarvisWorkerSupervisor.swift`, `swift run --package-path swift-shell jarvis-menu-bar --self-test`, `swift run --package-path swift-shell jarvis-menu-bar --worker-monitor-self-test`, `swift run --package-path swift-shell jarvis-menu-bar --worker-concurrency-self-test`, `swift run --package-path swift-shell jarvis-menu-bar --worker-autostart-disabled-self-test`, autostart opt-out via `JARVIS_DISABLE_WORKER_AUTOSTART=1` | Done for local startup plus serialized concurrent startup, basic health monitor/recovery, autostart opt-out, and app-quit cleanup for started workers; advanced crash policy controls deferred |
| Native shell hotkey | `swift-shell/Sources/JarvisMenuBar/Support/JarvisHotKeyService.swift`, `swift run --package-path swift-shell jarvis-menu-bar --hotkey-self-test` | Done for default `Command+Option+J`; configuration deferred |
| Native permission readiness | `swift-shell/Sources/JarvisMenuBar/Support/JarvisPermissionService.swift`, `swift run --package-path swift-shell jarvis-menu-bar --permission-self-test` | Done for read-only status checks; permission request/onboarding flows deferred |
| Local app bundle packaging | `swift-shell/scripts/build_app_bundle.sh`, `output/Jarvis.app`, `output/Jarvis-Current-17.app`, `codesign --verify --deep --strict --verbose=2 output/Jarvis-Current-17.app`, bundled executable self-tests | Done for local ad-hoc-signed bundle with XML-escaped plist values; Developer ID/notarization deferred |
| Safe verification harness | `scripts/verify_safe.py`, `runtime/verification/verify-safe-20260603-060416.json` | Done; latest run passed 89/89 checks |
| Audit redaction and truncation | `jarvis/audit.py`, `tests/test_safety.py`, `jarvis/self_check.py` | Done; obvious password, token, API key, secret, credential, bearer values, env/header-style secret labels, sensitive structured detail keys, standalone OpenAI/GitHub-looking key shapes, and JSON-unsafe detail values are redacted or normalized before JSONL writes, and long strings are capped |
| Readiness summary endpoint | `GET /api/readiness`, dashboard Readiness block, `swift run --package-path swift-shell jarvis-host-probe --readiness`, `scripts/verify_safe.py` | Done; aggregates mode, worker, tool availability, self-check counts, audit status, and notes |
| Verification freshness | `scripts/verify_safe.py`, `GET /api/readiness`, `GET /api/preflight`, dashboard Readiness/Preflight blocks, `scripts/morning_status.py`, `jarvis-host-probe --readiness` | Done; latest report age is visible in handoff surfaces |
| Local preflight summary | `GET /api/preflight`, dashboard Preflight block, `swift run --package-path swift-shell jarvis-host-probe --preflight`, `scripts/verify_safe.py` | Done; reports required and recommended local action-readiness checks without requesting permissions; safe verification must be passing and no older than 12 hours |
| Plan-only command preview | `POST /api/plan`, dashboard Preview button, `swift run --package-path swift-shell jarvis-host-probe --plan 'shell: pwd'`, `scripts/verify_safe.py` | Done; previews routing and confirmation requirements without executing tools, including while paused |
| Scanner preview coverage | `POST /api/plan`, `scripts/verify_safe.py` | Done; verifier checks scanner preview stays non-executing |
| Text wake phrase simulation | `jarvis/wake.py`, `voice.wake_simulation`, `wake: Hey Jarvis status`, `scripts/verify_safe.py` | Done; tests wake detection and follow-up capture without microphone access or background listening, and returns a safety assessment for extracted commands |
| Prompt-injection scanner | `jarvis/injection.py`, `safety.injection_scan`, `scan untrusted: ...`, `scripts/verify_safe.py` | Done; flags suspicious instructions, common `disregard`/`leak` variants, and authority impersonation in untrusted text without following them |
| Scanner preflight gate | `GET /api/preflight`, `tests/test_safety.py` | Done; scanner is required in the policy/tool route readiness check |
| Loopback bind guard | `jarvis/config.py`, `jarvis/server.py`, `python3 scripts/run_dashboard.py --host 0.0.0.0 --port 8784`, `scripts/verify_safe.py` | Done; dashboard rejects non-loopback binds unless explicitly opted in |
| JSON POST guard | `jarvis/server.py`, manual `text/plain` smoke test, `scripts/verify_safe.py` | Done; command and mode POST endpoints require `application/json` bodies |
| Malformed JSON POST guard | `jarvis/server.py`, harness `isolated_malformed_json_post_rejected` | Done; malformed command/plan/mode JSON returns `400 Invalid JSON` before routing |
| Dashboard CSP hardening | `jarvis/server.py`, Browser QA on `http://127.0.0.1:8786`, `scripts/verify_safe.py` | Done; responses include `nosniff`, `no-store`, and restrictive same-origin CSP |
| Host-header guard | `jarvis/server.py`, manual Host-header smoke test, `scripts/verify_safe.py` | Done; non-loopback Host headers return 403 |
| Generated artifact hygiene | `.gitignore` | Done; generated caches, Playwright CLI cache, runtime artifacts, local bundles, and SwiftPM output are ignored for future Git setup |
| Mutating shell option policy | `jarvis/safety.py`, `jarvis/self_check.py`, `tests/test_safety.py`, `scripts/verify_safe.py` | Done; `find -delete`, `find -exec`, `find -fprint`, `sed -i`, sed write scripts, and external sed/awk script files require strong confirmation |
| Natural-language high-risk classification | `jarvis/safety.py`, `jarvis/self_check.py`, `tests/test_safety.py`, `scripts/verify_safe.py` | Done; obvious requests to download, install, uninstall, delete, remove, overwrite, change important settings, expose credentials, read cookies, or access Keychain require confirmation gates with categorized reasons |
| Morning status summary | `scripts/morning_status.py`, harness `morning_status_base_url_command`, `docs/MORNING_HANDOFF.md` | Done; read-only check reports worker freshness, latest verification, current bundle, and accepts base or `/api/command` endpoint URLs |
| Threaded audit reliability | `jarvis/audit.py`, `tests/test_safety.py` | Done; audit writes, bounded recent reads, and retention use a re-entrant lock |
| Localhost response headers | `jarvis/server.py`, `scripts/verify_safe.py` | Done; fresh-worker verification asserts `nosniff` and `no-store` |
| Swift URL environment handling | `swift-shell/Sources/JarvisClient/JarvisClient.swift`, harness `swift_host_probe_jarvis_url_base`, `swift_host_probe_jarvis_url_command`, `swift_host_probe_jarvis_base_url_command` | Done; both `JARVIS_URL` and `JARVIS_BASE_URL` accept base or `/api/command` endpoint forms |
| Config environment fallback | `jarvis/config.py`, `tests/test_safety.py` | Done; invalid integer env vars fall back safely |
| Clean dashboard shutdown/failure | `scripts/run_dashboard.py`, Ctrl+C smoke test, duplicate-port verifier check | Done |
| Dashboard launcher flags | `scripts/run_dashboard.py --host`, `scripts/run_dashboard.py --port`, `python3 scripts/run_dashboard.py --help` | Done |
| Swift cold-start cleanup | `JarvisWorkerSupervisor.stopStartedWorker()`, `JarvisMenuBarSelfTest`, `scripts/verify_safe.py` | Done; harness confirms autostarted self-test worker stops |
| Swift host-probe health/audit/mode controls | `swift-shell/Sources/JarvisHostProbe/main.swift`, `swift run --package-path swift-shell jarvis-host-probe --help`, `swift run --package-path swift-shell jarvis-host-probe --health`, `swift run --package-path swift-shell jarvis-host-probe --audit-status`, harness `swift_host_probe_pause`, `swift_host_probe_resume` | Done |
| Local pause mode | `GET /api/mode`, `POST /api/mode`, `policy.pause`, dashboard Pause/Resume, Swift shell Pause/Resume, `swift run --package-path swift-shell jarvis-host-probe --mode` | Done for local command-execution pause; full persistent kill switch deferred |
| Start-paused launch | `JARVIS_START_PAUSED=1`, `python3 scripts/run_dashboard.py --paused`, `scripts/verify_safe.py` | Done for cautious local worker launches; help output is verified |
| Localhost hardening | `jarvis/server.py`, `jarvis/safety.py`, `jarvis/tools.py`, `tests/test_safety.py`, isolated harness checks | Done for static traversal, audit limit bounds, request size cap, chained-shell blocking, code-runner blocking, and outside-project path confirmation |
| Explicit safety policy reporting | `jarvis/safety.py`, `GET /api/policy`, `tests/test_safety.py` | Done; policy endpoint now reports shell constraints and opt-in start-paused launch |
| Shell execution error handling | `jarvis/tools.py`, `tests/test_safety.py` | Done; read-only shell timeouts and missing executables return structured results |
| Runtime metadata | `jarvis/tools.py`, `swift-shell/Sources/JarvisClient/JarvisResponses.swift`, `swift-shell/Sources/JarvisMenuBar/Models/JarvisShellModel.swift` | Done; fresh-worker harness verifies PID/source metadata |
| Dashboard worker metadata | `jarvis/static/index.html`, `jarvis/static/app.js`, `jarvis/static/styles.css`, `output/playwright/jarvis-dashboard-worker-runtime.png`, `output/playwright/jarvis-dashboard-worker-runtime-mobile.png` | Done; Playwright desktop/mobile snapshots and screenshots verified clean Worker block |
| Localhost dashboard | `jarvis/server.py`, `jarvis/static/index.html`, `jarvis/static/app.js`, verified at `http://127.0.0.1:8765` | Done |
| Typed command entry | Dashboard command input and `POST /api/command` | Done |
| Keyboard-shortcut simulation | Dashboard `Cmd+K` / `Ctrl+K` wake shortcut focuses command input and updates wake state | Done for localhost prototype |
| Status display | `GET /api/health`, dashboard connection pill | Done |
| Audit log viewing | `GET /api/audit`, dashboard audit panel | Done |
| Audit retention status | `GET /api/audit/status`, dashboard audit status strip | Done |
| Safety-policy inspection | `GET /api/policy`, dashboard policy panel | Done |
| Tool catalog inspection | `GET /api/tools`, dashboard tool catalog panel | Done |
| Local self-checks | `GET /api/self-check`, `python3 -m jarvis.self_check` | Done |
| Early tool route self-checks | Self-checks now include file search, app check, screenshot capability, browser plan, Outlook plan, and Codex delegation | Done |
| Tool registry self-checks | Self-checks verify required registered tools and the policy execution boundary | Done |
| Safe command pipeline | `jarvis/planner.py`, `jarvis/safety.py`, `jarvis/server.py`, audit entries | Done for prototype tools |
| Model/planner cannot directly control computer | Planner routes through typed tool functions only | Done for prototype |
| Shell-like planner routing | `jarvis/planner.py`, `tests/test_safety.py`, `jarvis/self_check.py` | Done; explicit shell commands such as `git status`, `grep`, and `date` route to `shell.read_only` before broader natural-language shortcuts |
| Health/status tool | `system.status` tool | Done |
| App availability checks | `app.availability` tool, `tests/test_safety.py` | Done; searches common macOS app folders and matches names case-insensitively |
| Natural app-check routing | `jarvis/planner.py`, `jarvis/self_check.py`, `tests/test_safety.py` | Done; `open app ...` and `check app ...` route to app availability |
| Safe shell read-only commands | `shell.read_only`, allowlist in `jarvis/safety.py` | Done |
| File search within selected folders | `files.search` by filename with scoped project-root fallback | Done; generated/build folders are skipped, outside roots fall back to the project |
| Screenshot capability detection | `screenshot.capability` tool | Done |
| Browser/open-url planning | `browser.open_url` plan-only tool | Done; includes untrusted-content prompt-injection scan guard |
| Outlook/email read-only planning | `outlook.visible_summary` plan-only tool | Done; includes untrusted-content prompt-injection scan guard |
| Codex CLI delegation planning | `codex.delegate` dry-run plan with detected Codex path/version | Done |
| Dangerous/external actions blocked or confirmed | Strong confirmation policy, confirmation objects, visible dashboard confirmation panel | Done for prototype; execution remains disabled |
| Detect Codex CLI and version | Self-check and health output show `/Applications/Codex.app/Contents/Resources/codex`, `codex-cli 0.136.0-alpha.2` | Done |
| Avoid secrets/session scraping | No browser-cookie, hidden-token, or private endpoint integration in code | Done |
| Audit logs with required fields | `runtime/audit/events.jsonl` records command, risk, tool, decision, result summary, details | Done |
| No raw audio/screenshots by default | Screenshot tool is capability-only; docs specify no raw media storage by default | Done |
| 90-day plus size-cap design | `jarvis/config.py`, `jarvis/audit.py`, `docs/SAFETY_MODEL.md` | Done |
| Wake-word/voice planned early without faking | `docs/ROADMAP.md`, `docs/DECISIONS.md`, `docs/DEFERRED_FEATURES.md` | Done |
| MacBook Air remote-worker idea included | `docs/REMOTE_WORKER.md`, `docs/ARCHITECTURE.md` | Done |
| Local self-checks and browser inspection | Unit tests, self-checks, curl probes, browser interaction, screenshot artifact | Done |

## Verification Commands

```bash
python3 -m unittest discover -s tests
python3 -m jarvis.self_check
python3 -m py_compile jarvis/*.py scripts/run_dashboard.py scripts/verify_safe.py
python3 scripts/run_dashboard.py --help
python3 scripts/run_dashboard.py --host 0.0.0.0 --port 8784
python3 scripts/run_dashboard.py --paused
python3 scripts/morning_status.py
python3 scripts/morning_status.py --base-url http://127.0.0.1:8765/api/command
python3 scripts/verify_safe.py
swift build --package-path swift-shell
swift run --package-path swift-shell jarvis-host-probe --help
swift run --package-path swift-shell jarvis-host-probe status
swift run --package-path swift-shell jarvis-host-probe --health
swift run --package-path swift-shell jarvis-host-probe --audit-status
swift run --package-path swift-shell jarvis-host-probe --readiness
swift run --package-path swift-shell jarvis-host-probe --preflight
swift run --package-path swift-shell jarvis-host-probe --plan 'shell: pwd'
swift run --package-path swift-shell jarvis-host-probe --mode
swift run --package-path swift-shell jarvis-host-probe 'shell: rm -rf /tmp/example'
swift run --package-path swift-shell jarvis-menu-bar --self-test
swift run --package-path swift-shell jarvis-menu-bar --hotkey-self-test
swift run --package-path swift-shell jarvis-menu-bar --permission-self-test
swift run --package-path swift-shell jarvis-menu-bar --worker-monitor-self-test
swift run --package-path swift-shell jarvis-menu-bar --worker-concurrency-self-test
swift-shell/scripts/build_app_bundle.sh
plutil -lint output/Jarvis.app/Contents/Info.plist
codesign --verify --deep --strict --verbose=2 output/Jarvis.app
output/Jarvis.app/Contents/MacOS/jarvis-menu-bar --self-test
output/Jarvis.app/Contents/MacOS/jarvis-menu-bar --hotkey-self-test
output/Jarvis.app/Contents/MacOS/jarvis-menu-bar --permission-self-test
APP_NAME=Jarvis-Current swift-shell/scripts/build_app_bundle.sh
plutil -lint output/Jarvis-Current-17.app/Contents/Info.plist
codesign --verify --deep --strict --verbose=2 output/Jarvis-Current-17.app
output/Jarvis-Current-17.app/Contents/MacOS/jarvis-menu-bar --permission-self-test
output/Jarvis-Current-17.app/Contents/MacOS/jarvis-menu-bar --hotkey-self-test
JARVIS_BASE_URL=http://127.0.0.1:8847 output/Jarvis-Current-17.app/Contents/MacOS/jarvis-menu-bar --self-test
JARVIS_BASE_URL=http://127.0.0.1:8842 output/Jarvis-Current-17.app/Contents/MacOS/jarvis-menu-bar --worker-monitor-self-test
JARVIS_BASE_URL=http://127.0.0.1:8843 output/Jarvis-Current-17.app/Contents/MacOS/jarvis-menu-bar --worker-concurrency-self-test
JARVIS_BASE_URL=http://127.0.0.1:8844 JARVIS_DISABLE_WORKER_AUTOSTART=1 output/Jarvis-Current-17.app/Contents/MacOS/jarvis-menu-bar --worker-autostart-disabled-self-test
curl -sS http://127.0.0.1:8765/api/health
curl -sS http://127.0.0.1:8765/api/tools
curl -sS http://127.0.0.1:8765/api/readiness
curl -sS http://127.0.0.1:8765/api/self-check
curl -sS http://127.0.0.1:8765/api/audit/status
curl -sS -X POST http://127.0.0.1:8765/api/command \
  -H 'Content-Type: application/json' \
  -d '{"command":"shell: rm -rf /tmp/example"}'
```

## Browser Evidence

- Dashboard title: `Jarvis Prototype`
- Dashboard URL: `http://127.0.0.1:8765/`
- Dashboard wake simulation: `Cmd+K` / `Ctrl+K` focuses command input and changes wake state
- Quick Shell action returned `shell.read_only`
- Typed dangerous command `shell: rm -rf /tmp/example` returned `policy.strong_confirmation`
- Dangerous command was not executed
- Audit list updated after actions
- Audit status shows event count, log size, retention days, and 1 GB cap
- Screenshot artifact: `output/playwright/jarvis-dashboard.png`
- Swift host probe can call `status`, report worker health/runtime, report
  audit status, and receives confirmation metadata for dangerous commands
- Swift menu-bar shell self-test supervises worker startup, can call `status`, receives strong confirmation for dangerous commands, and reads audit retention status
- Swift hotkey self-test registers `Command+Option+J` successfully
- Swift permission self-test verifies microphone, speech recognition, screen
  recording, Accessibility, and notification readiness checks without
  requesting permissions, and now asserts exactly five complete readiness rows
- Python unit tests passed 85/85 after pause-mode, readiness/preflight/preview
  summary, loopback
  bind guard, Host-header parsing, audit redaction, concurrent audit,
  standalone key-shape, env-style label, and sensitive detail-key redaction,
  morning-status URL normalization,
  verification-age formatting/freshness gating, stale-verification action
  messaging, prompt-injection scanning, mutating shell option/script coverage,
  secret filename/pathspec coverage, unreadable and non-UTF-8 audit-line
  redaction, JSON-unsafe audit detail normalization, and natural-language
  high-risk classification
- Python self-checks passed 49/49 after adding shell allowlist, natural app
  routing, readiness, preview, text wake simulation, loopback bind checks, and
  audit redaction/truncation including standalone key shapes, plus natural
  high-risk, secret-access, prompt-injection, authority impersonation, sed/awk
  script, secret filename, bare secret filename, and JSON-unsafe audit detail
  checks
- Safe verification harness passed 89/89 checks after runtime metadata,
  readiness/preflight/preview summary, text wake simulation command
  assessment, prompt-injection scan, loopback bind guard, dashboard port guard,
  Host-header guard, JSON POST guard, malformed JSON guard, CSP hardening,
  shell hardening, Swift host-probe pause/resume, SwiftPM and bundled worker
  autostart opt-out, and pause-mode coverage, and wrote
  `runtime/verification/verify-safe-20260603-060416.json`
- Audit logger concurrent-write test verified 20 parallel writes with 0
  unreadable lines
- Audit logger redaction tests verified obvious token/password/API-key/bearer
  values, env/header-style secret labels, sensitive structured detail-key
  values, and standalone key-shaped values are not written verbatim to recent
  audit output
- Audit logger normalization tests verified bytes, set-like containers, and
  path/object values are converted into JSON-safe redacted audit details
- Audit logger truncation test verified long nested strings are capped after
  redaction
- Audit recent-read test verifies bounded tail reads preserve newest-event order
- Pause-mode state uses a re-entrant lock for threaded localhost reads/writes
- Paused dangerous command verification preserved risk level 4 while refusing
  execution at `policy.pause`
- Fresh-worker response-header check verified `nosniff` and `no-store`
- Fresh-worker response-header check now also verifies restrictive same-origin
  Content Security Policy
- JSON request parser rejects negative `Content-Length` values
- Malformed JSON command/plan/mode POSTs return `400 Invalid JSON`
- Dashboard startup rejects invalid port numbers before binding
- Duplicate-port dashboard startup prints a clean `Address already in use`
  failure instead of a traceback
- Morning status summary reported stale default worker, latest verification,
  and current bundle
- Morning status summary reports verification highlights from the latest report
- Morning status summary now includes readiness summary, paused readiness, and
  Swift readiness probe verification highlights
- Morning status summary now includes the loopback bind guard verification
  highlight
- Morning status summary now includes the JSON POST guard verification
  highlight
- Morning status summary now includes the Host-header guard verification
  highlight
- Morning status accepts both base and `/api/command` `JARVIS_URL` and
  `JARVIS_BASE_URL` forms
- Morning status also accepts an explicit `--base-url`
- Swift menu Open Dashboard uses the configured worker base URL
- Swift client accepts trailing-slash command endpoint URLs such as
  `JARVIS_URL=http://127.0.0.1:8765/api/command/`
- Fresh-worker policy check verified `shell: find . -delete` stops at
  `policy.strong_confirmation`
- Fresh-worker policy check verified quoted shell redirection stops at
  `policy.strong_confirmation`
- Unit coverage verifies read-only shell timeout and missing-executable results
  stay structured instead of throwing worker exceptions
- Endpoint verification checks read-only shell allowlist routing through
  `/api/command`
- Unit and self-check coverage include attached redirection without a space
- Harness endpoint checks now assert health `ok=true`, required tools, self-check
  `ok=true`, audit retention, and strong-confirmation semantics
- Isolated fresh-worker checks blocked static path traversal, handled invalid
  audit limits, rejected oversized command bodies, and stopped chained shell at
  `policy.strong_confirmation`
- Isolated fresh-worker checks verified runtime PID/source metadata
- Isolated fresh-worker checks stopped code-runner shell commands at
  `policy.strong_confirmation` and outside-project shell paths at
  `policy.confirmation`
- Policy endpoint reports argv execution, auto-execute constraints,
  confirmation cases, and strong-confirmation shell cases
- Swift host probe reports health/runtime, audit status, and command mode from
  Terminal
- Swift host probe pause/resume flags are verified against a temporary worker
- Swift host probe reports the read-only readiness summary from Terminal
- Pause mode endpoint starts live, blocks `/api/command` at `policy.pause`
  while paused, and resumes `system.status` execution afterward
- Isolated start-paused worker starts with commands disabled, blocks `status`
  at `policy.pause`, and cleans up afterward
- Isolated paused-worker check verified `/api/readiness` remains available and
  reports paused mode plus self-check counts while commands are blocked
- Non-loopback dashboard bind smoke test verified `--host 0.0.0.0` exits with
  a one-line loopback-only failure instead of starting a network-exposed server
- Manual and verifier smoke tests verified a `text/plain` `/api/command` POST
  returns `415 Content-Type must be application/json`
- Manual and verifier smoke tests verified `Host: example.com` on
  `/api/health` returns `403 Host header must be loopback`, while normal
  loopback health still works
- In-app Browser QA on `http://127.0.0.1:8786` verified the dashboard still
  renders with the CSP header and reports 0 console warnings/errors
- The safe harness starts a fresh temporary worker if the default worker is
  stale or paused
- Swift self-test cold-start path starts a worker on a temporary port and then
  cleans it up; harness confirmed the port was no longer listening
- Swift worker monitor self-test starts a worker on a temporary port, terminates
  only that worker, verifies recovery, and confirms cleanup
- Swift worker concurrency self-test verifies simultaneous startup calls share
  one started worker handle and cleanup stops it
- Swift worker autostart-disabled self-test verifies the shell respects
  `JARVIS_DISABLE_WORKER_AUTOSTART=1` without starting a worker
- Swift client accepts both `JARVIS_URL` and `JARVIS_BASE_URL` as either a base
  URL or `/api/command` endpoint; harness verifies both forms
- Invalid integer env vars for port and audit settings fall back safely instead
  of crashing import
- `scripts/run_dashboard.py --port 8766` stops cleanly on Ctrl+C without a
  traceback
- Dashboard launcher supports `--host` and `--port` flags for clean alternate
  localhost QA workers
- Dashboard Worker block shows PID, uptime, start time, source, and cwd when
  runtime metadata is available
- Playwright fallback was used because the in-app browser route was unavailable;
  snapshot verified the Worker block, screenshot saved to
  `output/playwright/jarvis-dashboard-worker-runtime.png`, and console reported
  0 warnings/errors
- Mobile Playwright QA at 390x844 verified stacked layout and saved
  `output/playwright/jarvis-dashboard-worker-runtime-mobile.png`; console
  warnings/errors remained 0
- Local `output/Jarvis.app` bundle has valid plist, verifies with ad-hoc signature, launches as a long-running menu-bar process, and its bundled executable can cold-start the Python worker from outside the project directory
- Current `output/Jarvis-Current-17.app` bundle has valid plist, verifies with
  ad-hoc signature, and its bundled permission, worker, and hotkey self-tests
  passed
- Temporary bundle verification now builds an app name containing spaces, `&`,
  an apostrophe, and angle brackets, proving plist XML escaping and decoded
  display-name round trip for configurable bundle values
- Current bundle self-test against a fresh worker reported
  `Verification: passed 89/89` and `Mode: pause/resume passed`
- Current bundle worker monitor self-test reported restart recovery passed
- Current bundle worker concurrency self-test reported concurrent startup
  cleanup passed
- In-app Browser QA on `http://127.0.0.1:8767` verified desktop Pause/Resume,
  backend `policy.pause`, restored `system.status`, mobile 390x844 layout, and
  0 console warnings/errors
- In-app Browser QA on `http://127.0.0.1:8780` caught and fixed a stale
  dashboard Readiness refresh after Pause; retest verified Paused/Live
  readiness text, disabled/enabled command controls, and 0 console
  warnings/errors
- In-app Browser QA on `http://127.0.0.1:8793` verified the dashboard
  Preflight block shows 7/7 required checks while live, drops to 6/7 while
  paused, returns to 7/7 after resume, and reports 0 console warnings/errors
- In-app Browser QA on `http://127.0.0.1:8800` verified the dashboard Preview
  button returns `executed=false`, stays enabled while paused, leaves Run and
  quick actions disabled while paused, and reports 0 console warnings/errors
- In-app Browser QA on `http://127.0.0.1:8813` verified the dashboard
  verification freshness display and scanner tool in Readiness, Preflight, and
  the tool list, including `11/11` required policy/tool routes, with 0 console
  warnings/errors
- Dashboard result header displays the routed tool name after commands
- Dashboard tool catalog lists executable, plan-only, dry-run, capability-only, and policy-gate tools

## Remaining Product Scope

The full Jarvis product is not complete because these are still deferred:

- Real local "Hey Jarvis" wake-word listener.
- Configurable keyboard shortcut beyond the default native `Command+Option+J`.
- Developer ID signing, hardened runtime, notarization, and distribution beyond the local ad-hoc-signed `Jarvis.app`.
- Permission request/onboarding flows.
- Live OpenAI or model backend.
- Live Codex CLI execution with approval.
- Real Outlook/Mail control and summarization.
- Accessibility/AppleScript/Shortcuts control.
- MacBook Air remote worker implementation.
- Packaging, signing, settings, onboarding, full persistent kill switch beyond
  local pause mode, and advanced crash-policy controls.
