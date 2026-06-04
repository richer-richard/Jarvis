# Swift Shell Plan

The first working prototype is Python plus localhost. The Swift shell should be
added after the core pipeline is stable.

## Shell Responsibilities

- Menu bar icon.
- Floating Jarvis panel.
- Configurable keyboard shortcut.
- Visible states: listening, transcribing, thinking, asking approval, acting.
- Microphone permission.
- Screen recording permission.
- Accessibility permission.
- Notifications.
- Keychain storage.
- Launch at login.
- Local IPC with the Python worker.

## Build Constraint

Leo does not currently have full Xcode installed. The project should avoid
requiring full Xcode for the first pass. If the final shell needs Xcode-only
work later, call that out explicitly before depending on it.

## IPC Direction

The Python worker already exposes localhost HTTP endpoints. The first Swift
shell can call those endpoints locally while development continues. Later, the
IPC can be tightened to a local Unix socket or app-internal process channel.

## First Swift Milestone

1. Start or connect to the Python worker.
2. Show a compact floating command panel.
3. Send typed commands to `/api/command`.
4. Render result and confirmation states.
5. Show audit/log status.

## Current Swift Package

`swift-shell/` now contains:

- `JarvisClient`: shared Swift localhost API client.
- `jarvis-host-probe`: command-line probe for quick worker, health/runtime,
  audit, readiness, preflight, preview, mode, and policy checks.
- `jarvis-menu-bar`: SwiftPM-built macOS menu-bar shell with an AppKit status
  item and SwiftUI command panel.
- `swift-shell/scripts/build_app_bundle.sh`: local `.app` bundler for
  `output/Jarvis.app`.

The generated bundle is ad-hoc signed for local development. It is not a
Developer ID signed or notarized distribution artifact.

Commands:

```bash
swift build --package-path swift-shell
python3 scripts/verify_safe.py
swift run --package-path swift-shell jarvis-host-probe --help
swift run --package-path swift-shell jarvis-host-probe status
swift run --package-path swift-shell jarvis-host-probe --health
swift run --package-path swift-shell jarvis-host-probe --audit-status
swift run --package-path swift-shell jarvis-host-probe --readiness
swift run --package-path swift-shell jarvis-host-probe --preflight
swift run --package-path swift-shell jarvis-host-probe --plan 'shell: pwd'
swift run --package-path swift-shell jarvis-host-probe --mode
swift run --package-path swift-shell jarvis-host-probe --pause 'manual pause'
swift run --package-path swift-shell jarvis-host-probe --resume
swift run --package-path swift-shell jarvis-host-probe 'shell: rm -rf /tmp/example'
swift run --package-path swift-shell jarvis-menu-bar --self-test
swift run --package-path swift-shell jarvis-menu-bar --hotkey-self-test
swift run --package-path swift-shell jarvis-menu-bar --permission-self-test
swift run --package-path swift-shell jarvis-menu-bar --worker-monitor-self-test
swift run --package-path swift-shell jarvis-menu-bar --worker-concurrency-self-test
JARVIS_BASE_URL=http://127.0.0.1:8840 JARVIS_DISABLE_WORKER_AUTOSTART=1 swift run --package-path swift-shell jarvis-menu-bar --worker-autostart-disabled-self-test
swift run --package-path swift-shell jarvis-menu-bar
swift-shell/scripts/build_app_bundle.sh
output/Jarvis.app/Contents/MacOS/jarvis-menu-bar --self-test
output/Jarvis.app/Contents/MacOS/jarvis-menu-bar --permission-self-test
```

Swift clients accept `JARVIS_URL` and `JARVIS_BASE_URL` as either a base URL or
the `/api/command` endpoint.

## Implemented Shell Behavior

- Shows a menu-bar item labeled `Jarvis`.
- Provides menu actions for opening the panel, running a status check, opening
  the localhost dashboard, and quitting.
- Opens the dashboard at the configured worker base URL instead of assuming
  port 8765.
- Registers `Command+Option+J` as a runtime macOS hotkey to open the panel.
- Shows a SwiftUI command panel with typed input, quick actions, worker state,
  routed tool, confirmation state, audit summary, and Codex CLI status.
- Starts the local Python worker from `scripts/run_dashboard.py` when localhost
  health fails and `JARVIS_DISABLE_WORKER_AUTOSTART` is not set.
- Runs a local worker monitor loop during app launch and can recover a worker
  it started if health goes offline.
- Serializes worker startup so simultaneous refresh and monitor checks share
  one in-flight startup instead of racing to launch duplicate workers.
- Self-tests stop only the worker they autostart, so cold-start checks do not
  leave stray localhost workers behind.
- Worker monitor self-test verifies start, stop, recovery, and cleanup on an
  alternate localhost port.
- Worker concurrency self-test verifies simultaneous startup calls and cleanup
  on an alternate localhost port.
- Worker autostart-disabled self-test verifies the Swift shell respects
  `JARVIS_DISABLE_WORKER_AUTOSTART=1` and does not start a worker on an unused
  localhost port.
- On normal app termination, stops only the worker process that this shell
  started.
- Calls the Python worker through local HTTP only.
- Accepts either base or command-endpoint forms of `JARVIS_URL` and
  `JARVIS_BASE_URL`.
- Normalizes trailing slashes in both URL environment variables, including
  command endpoint URLs.
- Host-probe readiness output includes the latest safe-verification result,
  report path, and age when the worker reports it.
- Host probe can inspect worker health/runtime metadata and audit status
  directly from Terminal.
- Host probe can inspect the read-only readiness summary from Terminal.
- Host probe can inspect the read-only preflight summary from Terminal.
- Host probe can preview command routing without executing tools.
- Host probe can inspect command mode and request local pause/resume.
- Shows Live/Paused command mode in the panel and exposes a local Pause/Resume
  button.
- Reads microphone, speech recognition, screen recording, Accessibility, and
  notification permission readiness without requesting permissions or changing
  settings.
- Shows native permission readiness in the panel.
- Self-test verifies `status`, dangerous-command strong confirmation, health,
  worker startup supervision, and audit retention status.
- Permission self-test verifies that all five readiness checks are present,
  unique, and have non-empty labels, states, and details.
- Builds a local ad-hoc-signed `Jarvis.app` bundle under `output/`.
- `scripts/verify_safe.py` validates the Swift shell, localhost worker, safety
  policy path, pause mode, isolated fresh-worker hardening checks, and a
  temporary app bundle, including worker monitor recovery and startup
  concurrency, SwiftPM and bundled autostart opt-out, and readiness,
  preflight, and preview endpoints and probes, without requiring system-setting
  changes or permission prompts.

## Remaining Shell Work

- Advanced crash policy controls beyond the basic worker monitor.
- Configurable global shortcut beyond the default `Command+Option+J`.
- Permission request/onboarding flows for microphone, speech recognition,
  screen recording, Accessibility, notifications, and Keychain.
- Launch-at-login setting.
- Full persistent kill switch beyond local pause mode.
- Real wake-word and transcription integration.
- Developer ID signing, hardened runtime, notarization, and distribution path.
