# Deferred Features

These ideas are important, but they are not part of the first localhost prototype.

## Voice

- Speaker verification so only the owner's voice can wake Jarvis (still deferred).
- Owner-only continuous voice authority (still deferred).
- Cloud or local speech-to-text selection.
- Spoken responses and voice settings.

Note: the real local "Hey Jarvis" wake-word listener is **no longer deferred** —
it ships in `swift-shell/Sources/JarvisMenuBar/Support/JarvisWakeListener.swift`
(Apple on-device Speech), persists the user's enable/disable choice, and
auto-resumes on launch once opted in. Its one open gap is that it has only been
verified against synthetic transcript / TTS-file tests, never a live human voice
through a real microphone. Speaker verification (above) remains genuinely
deferred.

## macOS Shell

- Developer ID signing, notarization, and distribution-ready `.app` bundle.
- Advanced crash policy controls beyond the basic native worker monitor.
- Floating Siri-like popup.
- Configurable keyboard shortcut beyond the default `Command+Option+J`.
- Launch at login.
- Permission request/onboarding flows for microphone, speech recognition,
  screen recording, Accessibility, and notifications.
- Keychain credential storage.
- Menu-bar kill switch.

## Computer Control

- Full-mailbox guaranteed Outlook/Mail newest-message access.
- Production-grade Apple Mail integration with onboarding and permission recovery.
- Accessibility-based app control.
- AppleScript and Shortcuts integrations.
- Mouse and keyboard control.
- Actual browser automation from Jarvis tools.
- Screenshot capture and image understanding.

## Model Backend

- OpenAI API calls.
- Realtime API voice sessions.
- OpenClaw-style Codex subscription OAuth research spike.
- Puter.js fallback research spike.
- Dynamic model routing with cost and intelligence tiers.
- Live Codex CLI task execution.

## Remote Worker

- MacBook Air worker app.
- Tailnet/SSH worker protocol.
- Remote screen thumbnail or live preview.
- Remote task queue.
- Remote approval flow.
- Remote audit sync.

## Product Polish

- Settings UI.
- Onboarding flow.
- Persistent app permissions.
- Log retention controls.
- Project-folder detection improvements.
- Packaging and signed app distribution.
