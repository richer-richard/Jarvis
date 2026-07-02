# Architecture

## Goals

Jarvis should feel like a real Mac assistant:

- Always available while the computer is awake.
- Local wake-word detection before sending audio to any model.
- Fast voice-to-action loop for simple commands.
- Reliable permissions and visible user control.
- A hard boundary between model suggestions and actual computer actions.

## Proposed Components

### 1. macOS Host App

Best implemented in Swift or SwiftUI.

Responsibilities:

- Menu bar presence.
- Microphone permission.
- Accessibility permission.
- Screen recording permission.
- Notifications and confirmation prompts.
- Secure credential storage in Keychain.
- Launch at login.
- Local IPC with the agent core.

### 2. Wake Listener

The wake listener runs locally and continuously. A real implementation exists in
`swift-shell/Sources/JarvisMenuBar/Support/JarvisWakeListener.swift`: it uses
Apple's on-device `SFSpeechRecognizer` + `AVAudioEngine` to detect "Hey Jarvis"
(plus "OK/Okay Jarvis"), with fuzzy phrase matching and command extraction. It
has had real bug-fix iteration — restart-storm protection, idempotent start,
silent-session recovery, and barge-in handling. The user's enable/disable choice
is persisted in `UserDefaults` (`JarvisWakeListenerEnabled`) and auto-resumes on
launch once opted in; a first-ever launch does not auto-start, so the microphone
and speech-recognition permission prompts are never forced before the user opts
in at least once.

Verification gap: the listener has only ever been exercised through synthetic
transcript / TTS-file tests (`scripts/smoke_wake_threshold.py`,
`scripts/physical_audio_preflight.py`, and the `--wake-*-self-test` binary
flags). It has **not** been verified against a real human voice through a real
microphone. Treat live-microphone wake reliability as an open, unverified item.

Other candidate approaches considered (not currently used):

- Picovoice Porcupine for production-grade wake-word detection.
- openWakeWord for a Python-friendly local wake-word path.
- Push-to-talk mode as a simpler fallback.

Privacy rule: do not stream always-on room audio to a cloud service. Only the
post-wake command audio should be transcribed.

### 3. Speech Recognition

Candidate approaches:

- Apple Speech framework for native macOS transcription.
- Whisper/local transcription for privacy-first mode.
- OpenAI transcription for quality and speed if the user accepts cloud audio.
- Realtime API for low-latency voice agents later.

Start simple: push-to-talk or wake-word trigger, record one command, transcribe,
then pass text into the agent core.

### 4. Agent Core

The agent core turns a user request into a plan and tool calls.

Responsibilities:

- Maintain the current conversation/task state.
- Classify action risk.
- Choose tools from a capability registry.
- Produce a user-visible plan for sensitive work.
- Request confirmation before protected actions.
- Store an audit trail of decisions and actions.

Implementation candidates:

- Python core for Leo-friendly development and quick automation.
- TypeScript core if using OpenAI Agents SDK heavily.
- Hybrid: Swift shell plus Python worker.

Current prototype:

- Python worker.
- Localhost HTTP dashboard.
- Swift command-line host probe.
- SwiftPM-built menu-bar shell with a SwiftUI command panel.
- Local ad-hoc app bundle packaging for development.
- Read-only native permission readiness checks for microphone, speech
  recognition, screen recording, Accessibility, and notifications.
- Basic local worker monitor/recovery loop in the Swift shell.
- Serialized worker startup so refresh and monitor checks do not launch
  duplicate local workers.
- Heuristic planner.
- Typed tools.
- Safety policy gate.
- JSONL audit log.
- Runtime metadata in health/status for worker PID, source path, and uptime.
- Read-only readiness snapshot that aggregates mode, worker status, tool
  availability, self-check counts, audit status, latest safe-verification
  status, and short notes.
- Read-only preflight snapshot for local action readiness.
- Plan-only command preview endpoint that routes commands without executing
  tools.
- Text-only wake phrase simulation for testing `Hey Jarvis` command extraction
  and extracted-command safety assessment without microphone access.
- Read-only prompt-injection scanner for untrusted webpage/email/document text,
  including authority-impersonation detection.
- Loopback-only dashboard binding by default, with explicit opt-in required for
  non-loopback hosts.
- Host-header, JSON content-type, malformed JSON, request-size, static-path,
  and response-header hardening for the localhost surface.
- Local pause mode that blocks `/api/command` at the server boundary while
  keeping health, mode, policy, tool, readiness, self-check, and audit
  endpoints live.

### 5. Tool Layer

The model should never directly control the computer. It should request actions
through typed tools.

Initial tools:

- `system.status`
- `app.availability`
- `outlook.visible_summary`
- `browser.open_url`
- `files.search`
- `shell.read_only`
- `voice.wake_simulation`
- `safety.injection_scan`
- `planner.preview`
- `screenshot.capability`
- `policy.pause`
- `control.pause`
- `control.resume`

Later tools:

- `mouse.click`
- `keyboard.type`
- `apple_script.run`
- `shortcuts.run`
- `shell.run`
- `email.reply_draft`

### 6. Model Backend

Preferred stable backend:

- OpenAI Responses API for text, screenshots, and tool orchestration.
- Realtime API or Agents SDK for low-latency voice once the basics work.
- Computer Use API only inside strict boundaries and with safety gates.

Possible local-client backend:

- Codex CLI authenticated via official sign-in.
- Jarvis invokes the CLI as a subprocess for coding or filesystem tasks.

Do not depend on private ChatGPT browser sessions or copied auth tokens.

### 7. Remote Worker

Leo's always-plugged MacBook Air is a future worker target. The MacBook Pro can
remain the front-end/controller while the MacBook Air runs long tasks over
Tailnet/SSH. This is not implemented in the first prototype because remote
execution needs a separate safety and authentication design.

## Suggested First Prototype

Do not start with full "always listening plus full computer control."

Start with:

1. Python worker.
2. Localhost dashboard.
3. SwiftPM menu-bar shell that connects to the worker.
4. Typed command entry and keyboard-shortcut simulation.
5. Risk classification.
6. Tool registry.
7. Audit log.
8. Read-only shell/status/file-search/app-check tools.
9. Screenshot capability check.
10. Outlook read-only workflow planning.
11. Codex CLI delegation planning.

That validates the core loop while avoiding the riskiest parts.

Wake-word support was worked on early and not faked. Alongside the text-only
`voice.wake_simulation` route (for transcript tests), a real local wake listener
now ships in `JarvisWakeListener.swift` (Apple Speech, on-device). It persists
the user's enable/disable choice and auto-resumes on launch once opted in. The
one honest caveat is that it still has not been verified against live microphone
audio — only synthetic transcript / TTS-file tests — so live-mic reliability
remains an open item.
