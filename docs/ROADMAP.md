# Roadmap

## Milestone 0: Project Foundation

Status: started.

Deliverables:

- Product overview.
- Architecture document.
- Safety model.
- Open questions.
- Decision log.

## Milestone 1: Manual Command Prototype

Goal: prove the agent loop without always-on listening.

Status: working prototype.

Deliverables:

- Localhost dashboard that accepts typed commands.
- Backend kept pluggable; fast Groq chat plus local Ollama fallback configured.
- Tool registry.
- Risk classifier.
- Audit log.
- Screenshot capability check.
- Confirmation prompt for sensitive actions.
- Local pause mode for command execution.
- Read-only readiness and preflight summaries.
- Plan-only command preview.
- Text-only wake phrase simulation.
- Prompt-injection scan for untrusted text.
- Verification freshness display in handoff surfaces.
- Safe shell read-only command handling.
- File search by name.
- App availability checks.
- Mail/Outlook read-only workflow with structured Apple Mail first, native OCR fallback, and prompt-injection scanning for local snippets.
- Codex CLI delegation planning.

## Milestone 1.5: Wake and Shortcut Prep

Goal: bring "Hey Jarvis" work forward without faking it.

Deliverables:

- Keyboard-shortcut simulation in the local UI.
- Wake-word implementation options.
- Voice identity stages documented.
- Clear separation of wake-word listening and command transcription.

Status: local dashboard shortcut simulation implemented with `Cmd+K` / `Ctrl+K`.
Text-only wake phrase simulation is also implemented through
`voice.wake_simulation` for transcript tests, including extracted-command
safety assessment, but real microphone wake-word listening remains deferred.

## Milestone 2: Push-to-Talk Voice Prototype

Goal: voice input without wake-word complexity.

Deliverables:

- Record one voice command.
- Transcribe command.
- Send transcript to agent core.
- Speak or display response.
- Keep a visible recording indicator.

## Milestone 3: Wake-Word Prototype

Goal: local "Hey Jarvis" trigger.

Deliverables:

- Local wake-word listener.
- False-positive testing.
- Wake sound or menu bar state change.
- Command timeout.
- Privacy indicator.

## Milestone 3.5: Remote Worker Design

Goal: design the MacBook Air worker path safely.

Deliverables:

- Worker authentication model.
- Tailnet/SSH connection plan.
- Remote audit format.
- Remote approval flow.
- Read-only screen preview plan.

## Milestone 4: Outlook Read-Only Demo

Goal: one impressive but bounded workflow.

Deliverables:

- Open/focus Outlook for explicit visible OCR requests.
- Capture screen inside the native Jarvis app process.
- Summarize visible inbox state with Apple Vision OCR.
- Try structured Apple Mail/Outlook metadata before OCR for generic email requests.
- Ask before opening messages.
- Audit all actions.

Status: partial working demo. It is still not a guaranteed full-mailbox newest-email system because macOS Automation permissions and app data access can block structured reads.

## Milestone 5: App Control Layer

Goal: typed capabilities instead of raw model control.

Deliverables:

- App open/focus tool.
- Browser open/search tool.
- File search tool.
- Shortcuts integration.
- AppleScript integration.
- Optional mouse/keyboard control with strict confirmation.

## Milestone 6: Background macOS App

Goal: a real daily-use shell.

Deliverables:

- Swift command-line host probe.
- Menu bar app.
- Permission readiness checks.
- Launch at login.
- Permission request/onboarding flows.
- Kill switch.
- Keychain storage.
- Settings UI.

Status: SwiftPM menu-bar shell and stable local `output/Jarvis.app` bundle are
implemented. The shell starts the bundled Python worker, registers
`Command+Option+J`, reopens the panel when the app is opened again, exposes
copyable debug/test exports, monitors async Codex jobs, mirrors UI timers, and
reads microphone, speech recognition, screen recording, Accessibility, and
notification permission readiness without requesting permissions. The host
probe can report status, health/runtime, audit status, command mode, and
dangerous-command policy gates. The shell also has self-tests for worker
recovery, concurrent startup, and autostart opt-out. The Python worker and
dashboard expose runtime metadata, local pause mode, readiness/preflight
summaries, plan-only preview, prompt-injection scanning, verification
freshness, a safe verification harness, and tighter localhost/shell hardening.
Configurable shortcut, advanced crash policy controls, launch-at-login,
permission request/onboarding flows, full persistent kill switch beyond local
pause mode, Keychain, settings UI, Developer ID signing, and notarization remain
deferred.

## Milestone 7: Computer Use and Advanced Automation

Goal: broader computer control with guardrails.

Deliverables:

- Screenshot-action loop.
- Computer Use API experiments.
- Sandboxed browser environment.
- Protected local desktop mode.
- Strong approval for high-risk actions.
