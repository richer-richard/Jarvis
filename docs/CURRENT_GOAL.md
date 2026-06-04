# Current Goal

Updated: 2026-06-03 04:33 CST
Target checkpoint: 2026-06-03 06:30 Beijing Standard Time

## Operating Rule

Keep working autonomously on Jarvis until the current native-readiness phase is
implemented, documented, and verified, or until the 06:30 checkpoint arrives.
If unfinished at that checkpoint, stop making new changes and leave a clear
status note here with what passed, what failed, and what should happen next.

## Active Phase

Advance the verified local prototype into a stronger macOS assistant foundation
without restarting from scratch.

## Current Scope

- Preserve the Python localhost worker, dashboard, typed tool pipeline, audit
  log, safety policy, SwiftPM menu-bar shell, app bundle, Codex CLI detection,
  docs, and tests.
- Add and verify read-only native permission readiness for microphone, speech
  recognition, screen recording, Accessibility, and notifications.
- Surface native readiness in the Swift panel.
- Add terminal self-test coverage for permission readiness.
- Keep all risky computer-control features behind typed tools and policy gates.
- Update docs and the prototype audit honestly.
- Run local verification before marking the phase complete.

## In Progress

- Native permission readiness phase is implemented, documented, and verified.
- Completion readiness: the native-readiness objective is satisfied; continue
  only low-risk monitoring and handoff cleanup until the 06:30 checkpoint.
- Safe all-in-one verification harness has been added.
- Localhost and shell safety hardening has been implemented and verified.
- Runtime metadata has been added to health/status and surfaced in the Swift
  shell when available.
- Runtime metadata has also been surfaced in the localhost dashboard Worker
  block.
- Local pause mode has been added at the server boundary: `/api/command`
  returns `policy.pause` while paused, and health, mode, policy, tools,
  self-check, and audit endpoints remain available.
- Pause mode still classifies attempted commands for audit risk before refusing
  execution.
- Pause mode is surfaced in the dashboard and Swift shell, and
  `jarvis-host-probe` now supports `--mode`, `--pause`, and `--resume`.
- Audit logging is now protected by a re-entrant lock for threaded localhost
  writes and retention trimming.
- Pause-mode state is now protected by a re-entrant lock for threaded localhost
  reads and writes.
- Localhost responses now include `X-Content-Type-Options: nosniff` and
  `Cache-Control: no-store`.
- JSON request parsing now rejects negative `Content-Length` values.
- Malformed JSON POST bodies now return `400 Invalid JSON` before command
  routing, preview routing, mode changes, or tool execution.
- Dashboard startup now rejects invalid port numbers before binding.
- `scripts/morning_status.py` now prints a read-only morning summary: worker
  freshness/mode, latest verification report, and current app bundle.
- `scripts/morning_status.py` now accepts `--base-url`.
- `.gitignore` now excludes generated Python caches, SwiftPM build output,
  Playwright CLI cache, runtime logs/reports, local app bundles, and OS
  metadata.
- Current ad-hoc app bundle has been rebuilt again as
  `output/Jarvis-Current-17.app` and passed plist, signature, permission,
  worker, and hotkey self-tests.
- App-bundle plist generation now XML-escapes configurable app name and bundle
  identifier values; the verifier builds a temporary app whose name contains
  spaces, `&`, an apostrophe, and angle brackets, then checks the decoded
  display name.
- Shell read-only policy has been tightened for code runners and
  outside-project paths.
- Shell read-only policy has also been tightened for mutating options or
  scripts on otherwise read-only tools, including `find -delete`, `find -exec`,
  `find -fprint`, `sed -i`, `sed 'w file'`, and external sed/awk script files.
- Shell redirection tokens such as `>`, `>>`, `<`, and `2>` now stop at strong
  confirmation even when filenames are quoted.
- `/api/policy` now explicitly reports the shell policy constraints.
- Swift host probe now has `--health`, `--audit-status`, and `--readiness`
  modes.
- Swift host-probe `--pause` and `--resume` are now directly covered by the
  safe verifier against a temporary worker.
- Dashboard launcher now supports `--host` and `--port` flags.
- Morning handoff has been added at `docs/MORNING_HANDOFF.md`.
- Swift self-tests now clean up workers they autostart.
- Swift client now accepts `JARVIS_URL` as either base URL or command endpoint.
- Swift client now normalizes trailing slashes in `JARVIS_URL`, including
  `.../api/command/`.
- Swift client now also accepts `JARVIS_BASE_URL` as either base URL or command
  endpoint, including `.../api/command/`.
- Config integer environment parsing now falls back safely on invalid values.
- Decision log now records argv-only shell execution, shell non-auto-execute
  categories, and fresh-worker verification on alternate ports.
- Dashboard launcher now stops cleanly on Ctrl+C.
- Dashboard launcher now reports a clean non-traceback error when the requested
  port is already in use.
- Swift shell now starts a local worker monitor loop during app launch and can
  recover a worker it started if health goes offline.
- `jarvis-menu-bar --worker-monitor-self-test` verifies start, stop, recovery,
  and cleanup on an alternate localhost port.
- `scripts/morning_status.py` now prints verification highlights from the
  latest report, including readiness, hardening, pause mode, worker monitor
  recovery, and temporary app bundle coverage.
- Planner routing now lets explicit shell-like commands such as `git status`,
  `grep Jarvis README.md`, and `date` reach `shell.read_only` before broader
  natural-language shortcuts.
- Read-only shell execution now returns structured timeout and missing
  executable results instead of throwing through the worker.
- Safe verifier now checks the HTTP `/api/command` route for read-only shell
  allowlist routing with `grep Jarvis README.md`.
- Swift worker startup is now serialized so simultaneous app refresh/monitor
  checks cannot start duplicate workers or lose the process handle.
- `jarvis-menu-bar --worker-concurrency-self-test` verifies concurrent startup
  and cleanup on an alternate localhost port.
- Dashboard startup now supports `JARVIS_START_PAUSED=1` and
  `python3 scripts/run_dashboard.py --paused` for cautious local launches.
- Safe verifier starts an isolated paused worker and verifies `/api/mode`,
  command blocking, and cleanup.
- App availability checks now search common macOS application folders and
  match `.app` names case-insensitively.
- File search now skips generated/build directories including `output/`,
  `runtime/`, `.build/`, `.swiftpm/`, `.playwright-cli/`, virtualenv folders,
  and caches.
- Audit recent-event reads now stream the log into a bounded tail instead of
  reading the whole audit file into memory.
- Helper roots for file search and Codex delegation planning now fall back to
  the project root if a caller supplies a path outside the project.
- `/api/policy` now reports the opt-in start-paused launch policy.
- Planner now routes natural app-check phrases such as `open app Safari` and
  `check app Outlook` to `app.availability`.
- On normal app termination, the Swift shell now stops only the Python worker
  process it started.
- Safe verifier now checks `scripts/run_dashboard.py --help` advertises
  `--paused`.
- Read-only `/api/readiness` endpoint now aggregates mode, worker runtime,
  tool availability, self-check counts, audit status, and notes.
- Dashboard now has a Readiness block, and Browser QA fixed/verified refresh
  after Pause/Resume.
- `jarvis-host-probe --readiness` now prints the readiness summary from
  Terminal.
- Safe verifier now covers `/api/readiness`, readiness while paused, and the
  Swift readiness probe.
- Dashboard binding is now loopback-only by default. Non-loopback hosts such as
  `0.0.0.0` fail cleanly unless `JARVIS_ALLOW_NON_LOOPBACK=1` is explicitly
  set.
- Safe verifier now covers the non-loopback bind rejection.
- `/api/command` and `/api/mode` now reject non-JSON POST bodies with `415`.
- Safe verifier now covers the JSON POST guard with a `text/plain`
  `/api/command` request.
- Dashboard/API responses now include a restrictive same-origin Content
  Security Policy, and Browser QA verified the dashboard still renders.
- Requests with non-loopback `Host` headers now return `403` before reaching
  API routes, reducing DNS-rebinding-style localhost exposure.
- Swift native readiness now also includes Speech Recognition authorization
  status without requesting permission or recording audio.
- Audit logging now redacts obvious password, token, API key, secret,
  credential, and bearer-token values before JSONL writes.
- Audit logging now caps very long strings after redaction to keep JSONL logs
  bounded and readable.
- Audit reads now redact unreadable raw JSONL lines before returning them to
  API/dashboard surfaces.
- Audit reads now tolerate non-UTF-8/corrupted raw lines by replacement-decoding
  and reporting them as unreadable redacted entries instead of crashing.
- `/api/readiness` and the dashboard Readiness block now surface the latest
  safe-verification report count/path.
- Read-only `/api/preflight` now reports required and recommended local
  action-readiness checks: worker metadata, live command mode, audit health,
  policy gates, loopback-only binding, JSON POST guard, a passing safe
  verification report no older than 12 hours, Codex CLI, and screenshot
  tooling.
- Dashboard now has a Preflight block, and `jarvis-host-probe --preflight`
  prints the same summary from Terminal.
- Safe verifier now covers `/api/preflight` and the Swift preflight probe.
- Plan-only preview has been added at `POST /api/plan`; it classifies and
  routes commands without executing even safe tools.
- Dashboard now has a Preview button that remains available while command
  execution is paused.
- `jarvis-host-probe --plan` now prints a non-executing command preview from
  Terminal.
- Safe verifier now covers endpoint preview, Swift preview, preview while
  paused, and non-JSON preview request rejection.
- Safe verifier now checks wake simulation returns a safety assessment for the
  extracted command, including a dangerous follow-up text case.
- Text-only wake phrase simulation now lives in `jarvis/wake.py`; it detects
  `Hey Jarvis` transcripts and follow-up commands without microphone access.
- Planner route `voice.wake_simulation` lets `wake: Hey Jarvis status` exercise
  the wake flow through the typed tool pipeline.
- Wake simulation now includes the extracted command's safety assessment, so
  dangerous follow-up text is visibly classified without executing it.
- Local API reference added at `docs/API.md` and linked from the README.
- `jarvis-host-probe --help` now documents the available terminal modes.
- Current bundle concurrency self-test output now labels shared startup
  results clearly.
- Natural-language safety classification now treats requests to download,
  install, uninstall, delete, remove, overwrite, change important settings,
  expose credentials, read cookies, or access Keychain as confirmation-gated
  high-risk actions even when the command does not use a `shell:` prefix.
- Natural-language safety classification now also treats privileged or
  destructive shell-like requests such as `run sudo ...` and `run rm -rf ...`
  as strong-confirmation cases even without a `shell:` prefix.
- Natural-language high-risk reasons are now categorized in policy output and
  assessment details, including external transmission, file/software changes,
  protected settings, credentials/cookies/Keychain, and payments.
- Safe verification reports now include generation/completion timestamps, and
  readiness, preflight, the dashboard, and morning status surface the latest
  report age.
- Morning status now prints a rerun action when the latest verification failed
  or is older than 12 hours.
- Added a read-only prompt-injection scanner for untrusted text. The
  `safety.injection_scan` tool flags suspicious instructions such as
  instruction overrides, secret extraction, hidden behavior, external
  transfers, and destructive/settings changes without treating the text as a
  user command.
- Prompt-injection scanning now also catches common variant wording such as
  `disregard prior safety rules` and `leak the system prompt`.
- Prompt-injection scanning now flags authority impersonation in untrusted text,
  such as text claiming to be from Leo, the system, or a developer.
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
- Next overnight-safe work: improve local reliability and developer handoff
  without risky permissions, installs, destructive file actions, or system
  setting changes.

## Verification Queue

- `python3 -m unittest discover -s tests` passed with 85/85 tests.
- `python3 -m jarvis.self_check` passed with 49/49 checks.
- `python3 -m py_compile jarvis/*.py scripts/run_dashboard.py scripts/verify_safe.py`
  passed.
- `swift build --package-path swift-shell` passed.
- `swift run --package-path swift-shell jarvis-menu-bar --permission-self-test`
  passed.
- `swift run --package-path swift-shell jarvis-menu-bar --self-test` passed.
- `swift run --package-path swift-shell jarvis-menu-bar --hotkey-self-test`
  passed.
- `swift run --package-path swift-shell jarvis-host-probe status` passed.
- `swift run --package-path swift-shell jarvis-host-probe 'shell: rm -rf /tmp/example'`
  passed and stopped at `policy.strong_confirmation`.
- Localhost endpoint checks passed.
- Temporary app-bundle plist, codesign, and bundled executable checks passed.
- `python3 scripts/morning_status.py` passed and detected the stale default
  `127.0.0.1:8765` worker while reporting the latest bundle.
- `python3 scripts/verify_safe.py` passed 89/89 checks and wrote
  `runtime/verification/verify-safe-20260603-060416.json`.
- `APP_NAME=Jarvis-Current swift-shell/scripts/build_app_bundle.sh` built
  `output/Jarvis-Current-17.app`.
- `plutil -lint output/Jarvis-Current-17.app/Contents/Info.plist` passed.
- `codesign --verify --deep --strict --verbose=2 output/Jarvis-Current-17.app`
  passed.
- `output/Jarvis-Current-17.app/Contents/MacOS/jarvis-menu-bar
  --permission-self-test` passed.
- `output/Jarvis-Current-17.app/Contents/MacOS/jarvis-menu-bar
  --hotkey-self-test` passed.
- `JARVIS_BASE_URL=http://127.0.0.1:8847
  output/Jarvis-Current-17.app/Contents/MacOS/jarvis-menu-bar --self-test`
  passed with `Verification: passed 89/89` and `Mode: pause/resume passed`.
- `JARVIS_BASE_URL=http://127.0.0.1:8842
  output/Jarvis-Current-17.app/Contents/MacOS/jarvis-menu-bar
  --worker-monitor-self-test` passed.
- `JARVIS_BASE_URL=http://127.0.0.1:8843
  output/Jarvis-Current-17.app/Contents/MacOS/jarvis-menu-bar
  --worker-concurrency-self-test` passed.
- `JARVIS_BASE_URL=http://127.0.0.1:8844 JARVIS_DISABLE_WORKER_AUTOSTART=1
  output/Jarvis-Current-17.app/Contents/MacOS/jarvis-menu-bar
  --worker-autostart-disabled-self-test` passed.

## Latest Notes

- Main `127.0.0.1:8765` worker was started before runtime metadata existed, so
  it may show metadata unavailable until restarted normally.
- SwiftPM notification readiness needed a bundle guard because
  `UNUserNotificationCenter.current()` can crash outside an app bundle.
- SwiftPM permission self-test now reports notification readiness as
  `Bundle needed` instead of crashing.
- Temporary bundled app permission self-test reads real notification status and
  reported `Notifications: Not requested`.
- Current bundled app permission self-test reports microphone, speech
  recognition, screen recording, Accessibility, and notification readiness
  without requesting permission.
- Permission self-tests now also assert exactly five unique readiness rows with
  non-empty labels, states, and details, plus a five-row summary.
- Swift worker autostart opt-out now has direct verifier coverage and confirms
  no worker starts on the unused test port.
- Passive process/port audit found the bundle test ports `8841` through `8847`
  closed after self-tests; the only `run_dashboard.py` process visible was the
  known stale default worker.
- One readback `rg` command accidentally used an unescaped backtick pattern,
  which made the shell attempt `python3 scripts/run_dashboard.py`; it failed
  immediately with `Address already in use`, and follow-up process/port audit
  confirmed no extra worker was left behind.
- Morning status now chooses the highest numbered `Jarvis-Current-N.app`
  bundle instead of relying only on modification time.
- 04:49 monitoring check: morning status still reported `89/89`, only the
  known stale default worker was visible, and bundle test ports `8841` through
  `8846` remained closed.
- 04:59 monitoring check: morning status still reported `89/89`, only the
  known stale default worker was visible, and bundle test ports `8841` through
  `8846` remained closed.
- 05:10 monitoring check: morning status still reported `89/89`, only the
  known stale default worker was visible, and bundle test ports `8841` through
  `8846` remained closed.
- 05:21 monitoring check: morning status still reported `89/89`, only the
  known stale default worker was visible, and bundle test ports `8841` through
  `8846` remained closed.
- 05:31 monitoring check: morning status still reported `89/89`, only the
  known stale default worker was visible, and bundle test ports `8841` through
  `8846` remained closed.
- 05:42 monitoring check: morning status still reported `89/89`, only the
  known stale default worker was visible, and bundle test ports `8841` through
  `8846` remained closed.
- 05:52 monitoring check: morning status still reported `89/89`, only the
  known stale default worker was visible, and bundle test ports `8841` through
  `8846` remained closed.
- 06:03 monitoring check: morning status still reported `89/89`, only the
  known stale default worker was visible, and bundle test ports `8841` through
  `8847` remained closed.
- 06:15 pre-checkpoint check: morning status still reported `89/89`, only the
  known stale default worker was visible, and bundle test ports `8841` through
  `8847` remained closed.
- 06:30 checkpoint reached: final check before the checkpoint reported
  `89/89`, unit tests passed `85/85`, only the known stale default worker was
  visible, and bundle test ports `8841` through `8847` remained closed.
- Pause mode verified in the in-app Browser at `http://127.0.0.1:8767`:
  Paused mode disabled Run and quick actions, backend `status` returned
  `policy.pause` with `executed=false`, Resume restored `system.status`
  execution, and desktop/mobile console warnings/errors were 0.
- Readiness block verified in the in-app Browser at `http://127.0.0.1:8780`:
  initial Live render was console-clean, Pause disabled command controls,
  a stale readiness refresh bug was fixed, and retest showed Paused/Live
  readiness text with 0 console warnings/errors.
- Preflight block verified in the in-app Browser at `http://127.0.0.1:8793`:
  initial Live render showed 7/7 required checks, Pause changed it to 6/7,
  Resume restored 7/7, command controls toggled correctly, and console
  warnings/errors were 0.
- Preview button verified in the in-app Browser at `http://127.0.0.1:8800`:
  live preview returned `executed=false`, Preview remained enabled while
  paused, paused preview returned `system.status` with `executed=false`, and
  console warnings/errors were 0.
- Verification freshness and scanner-tool display verified in the in-app
  Browser at `http://127.0.0.1:8813`: Readiness verified the then-current
  self-check count, 18/18 tools, and the then-current verification count with
  an age; Preflight showed latest-report freshness and `11/11` required
  policy/tool routes; the tool list included `Prompt-Injection Scan`; and
  console warnings/errors were 0.
- Safe verifier now includes endpoint coverage for `safety.injection_scan`, and
  morning status highlights prompt-injection scan coverage in the latest
  report.
- Safe verifier now checks `safety.injection_scan` flags authority
  impersonation in untrusted text.
- Safe harness now avoids trusting a stale default worker; if the default
  worker lacks current runtime/mode metadata or is paused, it starts a fresh
  temporary worker for verification.
- Concurrent audit-write unit coverage verifies 20 parallel writes remain
  readable with no unreadable JSONL lines.
- Fresh-worker verification asserts the localhost response headers are present.
- Temporary app-bundle verification now points bundled `--self-test` at the
  verifier's fresh worker and expects `Mode: pause/resume passed`.
- Safe verifier now includes Swift worker monitor recovery and cleanup checks.
- Safe verifier now compiles every Python file in `scripts/` and includes the
  morning status summary check.
- Safe verifier now includes `/api/readiness`, readiness while paused, and
  Swift readiness probe checks.
- Morning status accepts both `JARVIS_URL=http://host:port` and
  `JARVIS_URL=http://host:port/api/command`, matching Swift client behavior.
- Morning status and Swift client also accept `JARVIS_BASE_URL` as either a
  base URL or `/api/command` endpoint URL.
- Swift menu's Open Dashboard action now opens the configured worker base URL
  instead of hardcoded port 8765.
- Unit coverage now verifies morning status URL normalization for
  `/api/command` endpoint URLs.
- Unit and fresh-worker coverage now verify mutating shell options and scripts
  stop at `policy.strong_confirmation`.
- Unit, self-check, and fresh-worker coverage now verify bare secret-bearing
  filenames such as `secrets.txt` stop at `policy.strong_confirmation`.
- Unit coverage now verifies readiness summary counts and paused-mode notes.
- Fresh-worker coverage now verifies the readiness endpoint and
  `jarvis-host-probe --readiness`.
- Unit and self-check coverage now verify the dashboard host guard allows
  loopback and blocks non-loopback by default.
- Full verifier coverage now checks `scripts/run_dashboard.py --host 0.0.0.0`
  exits with the loopback-only failure instead of binding.
- Full verifier coverage now checks `text/plain` command POSTs are rejected
  with `415`.
- Full verifier coverage now checks the response hardening headers include
  `nosniff`, `no-store`, and CSP.
- Full verifier coverage now checks bad Host headers return `403`.
- Unit and self-check coverage now verify obvious secret values are redacted in
  audit text before JSONL writes.
- Unit and self-check coverage now verify JSON-unsafe audit details are
  normalized and redacted before JSONL writes.
- Unit, self-check, and fresh-worker coverage now verify shell redirection
  stops at `policy.strong_confirmation`.
- Redirection coverage includes attached redirects like `cat >"README-copy.md"`.
- Commands safe for overnight use include Python tests, SwiftPM build/run,
  localhost curl/API checks, temporary app-bundle creation, `plutil`, and
  `codesign --verify`.
- Avoid overnight commands that may require user approval: `sudo`, installs,
  system-setting writes, permission-request prompts, destructive file actions,
  VPN/network/browser/security changes, and privacy-sensitive reads.
- New hardening blocks static path traversal, handles invalid audit limits,
  rejects oversized command bodies, and prevents chained shell from running as
  read-only.
- Shell hardening prevents code runners from auto-executing as read-only and
  stops outside-project paths for confirmation.
- Policy endpoint now makes those shell constraints visible to the dashboard.
- Host probe health/audit modes verified, including fresh-worker runtime
  metadata via `JARVIS_BASE_URL`.
- `python3 scripts/run_dashboard.py --help` passed and documented the new
  launcher flags.
- Swift cold-start self-test verified worker autostart on a temporary port and
  cleanup afterward.
- Safe harness endpoint checks now assert expected semantics, not just that JSON
  was returned.
- Safe harness verifies both `JARVIS_URL=http://127.0.0.1:8765` and
  `JARVIS_URL=http://127.0.0.1:8765/api/command`.
- Invalid `JARVIS_PORT`, `JARVIS_AUDIT_RETENTION_DAYS`, and
  `JARVIS_AUDIT_MAX_BYTES` no longer crash config import.
- Ctrl+C shutdown smoke test printed `Jarvis dashboard stopped.` without a
  traceback.
- Health/status now includes worker PID, cwd, source file, start time, and
  uptime. The Swift shell shows PID/uptime when the worker reports it.
- Dashboard Worker block verified with Playwright fallback on
  `http://127.0.0.1:8766`; screenshot saved to
  `output/playwright/jarvis-dashboard-worker-runtime.png`; console warnings and
  errors were 0.
- Mobile dashboard Worker block verified at 390x844; screenshot saved to
  `output/playwright/jarvis-dashboard-worker-runtime-mobile.png`; console
  warnings/errors were 0.
