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

The wake listener should run locally and continuously.

Candidate approaches:

- Apple Speech stack for simple prototypes.
- Picovoice Porcupine for production-grade wake-word detection.
- openWakeWord for a Python-friendly local wake-word path.
- Push-to-talk mode for the first prototype.

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

Wake-word support should be worked on early, but not faked. The first prototype
can document and simulate command entry while the actual local wake listener is
built separately.
