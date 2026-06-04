# Jarvis Capability And Test Matrix

Updated: 2026-06-04 07:15 CST

This file tracks the full Jarvis target, not only the current prototype.

| Capability | Target Behavior | Current Status | Codex Can Test Alone | Needs Leo |
|---|---|---|---|---|
| Stable macOS app | One signed `output/Jarvis.app` with stable permissions identity. | Working; `scripts/open_jarvis.sh` launcher and app reopen hook added. | Build, sign, launch, health/readiness, bundle version, worker source, process-count check, close-panel/reopen smoke. | Re-grant macOS permissions if TCC resets. |
| Typed chat | Leo types; Jarvis answers in the app. | Working. | UI smoke with Mac Control, API command tests, JSON export. | Judge answer quality. |
| Paste into command field | Leo can paste test prompts or debug JSON into the command field. | Working through Paste button and `Edit > Paste` / `Command+V` fallback. | Mac Control clipboard/menu smoke. | Try Leo's normal paste habit. |
| Capability status | Jarvis can explain what works, what is partial, and what is not ready without reading private content. | Working; Jarvis 103 includes elevation routing, remote helper diagnostics, and memory design in the no-content capability snapshot. | Unit tests, bundled API smoke, Mac Control UI smoke, Copy Tests smoke. | Judge whether the product wording is useful. |
| Test status | Jarvis can tell Leo how to get the current smoke-test list from inside the app. | Working; Jarvis 103 Copy Tests currently has 43 prompts. | Swift self-test, Mac Control UI smoke, Copy Tests clipboard count. | Use the copied prompts after new builds. |
| Safety status | Jarvis can explain confirmation gates, private-read logging, prompt-injection scanning, shell limits, and capture storage. | Working; Jarvis 94 answers `safety status` with no private reads. | Unit tests, bundled API smoke, Mac Control UI smoke, full verifier. | Judge whether the safety wording is clear enough. |
| Fast casual model | Normal replies should show first useful visible text in the 1-3s target zone; after that, token output only needs to outpace normal speech. A silent wait followed by an instant dump is not good enough. | Working with Groq `llama-3.3-70b-versatile`. Latest Jarvis 99 localhost smoke: 0.611-0.795s first visible text across three safe prompts, max total 1.014s, slowest after-first output 150.5 chars/s; `latency status` reads the latest report locally. | `scripts/smoke_fast_latency.py`, `latency status`, streaming API first-visible-text and after-first output-rate benchmarks, and UI smoke. | Provide more real prompts. |
| Fast model status | Jarvis can explain the active fast-model backend, fallback, timeout, output cap, and latest latency evidence without calling a model. | Working; Jarvis 96 answers `model status` with Groq `llama-3.3-70b-versatile`, Ollama `qwen3:0.6b` fallback, 5s timeout, 80 output-token cap, and the latest first-visible smoke metrics. | Unit tests, bundled API smoke, Mac Control UI smoke, Copy Tests smoke. | Decide later whether to add more providers/keys. |
| Deterministic quick commands | Time, date/day, battery, storage, timers, timer status, cancel timers, media, volume/sound, brightness, explicit speech route without Codex. | Mostly working; Jarvis 103 routes media commands to system media-key equivalents, and live smoke correctly reports Accessibility is needed when macOS blocks synthetic keystrokes. Jarvis 78 supports percentage controls such as `set volume to 42%` and `set brightness to 65%`; Jarvis 80 adds `timer status`; Jarvis 99 adds `what date is it` / `what day is it`; Jarvis 100 adds `battery status`; Jarvis 101 adds `storage status`. | API tests for time/date/battery/storage, `sound up/down`, `play current/play current song/play next/play previous`; plan-only percentage control probes; timer status live smoke; no-op brightness read/set; media-key blocked-permission live smoke; non-audio speech plan; Swift build/verifier for UI timer mirror. | Grant Accessibility to the stable app and confirm media/brightness/speech/timer completion behavior while awake. |
| Codex delegation | Deep project/code/review work goes to Codex CLI. | Async jobs working for broad requests; exact smoke tests stay synchronous; UI now polls started jobs and appends finished results; health/export diagnostics show job counts. Real persistence smoke: job id returned in 0.170s, Codex completed in 1m 57.6s, and the completed summary survived an app/worker restart. Mac Control also verified UI auto-posting with job `codex-52dc2f64`. | Timed exact Codex smoke tests, async preview/status route tests, health-count tests, Swift build/verifier, real small async worker smoke, restart persistence check, Mac Control UI monitor smoke. | Judge whether Codex's actual project answers are useful enough. |
| Codex speed status | Summarize persisted Codex timing without starting another slow Codex job. | Working; Jarvis 95 answers `codex speed status` from local persisted job summaries: 2 completed jobs, average 1m 56.3s, fastest 1m 55.0s, slowest 1m 57.6s, 0 running. | Unit tests, bundled API smoke, Mac Control UI smoke, Copy Tests smoke. | Judge whether the wording helps explain why casual chat avoids Codex. |
| Email summary | Read newest inbox email, including read messages, locally. | Partly working; Jarvis 103 tries Apple Mail metadata first for normal email, then structured Outlook metadata/database. Normal email no longer falls back to visible Outlook OCR because Leo's Outlook start view does not expose the newest email body; explicit visible OCR remains available. `email backend status` currently sees `apple_mail_applescript` for normal email. | Route tests, Apple Mail/Outlook mocks, newest-read-vs-older-unread regression, AppleScript-permission-to-SQLite fallback regression, safe explicit-OCR tests, synthetic injection smoke, no-content backend-status smoke, Mac Control UI smoke. | Grant Automation if needed; test against real Apple Mail content. |
| Native OCR | Jarvis app captures visible Outlook window and uses Apple Vision OCR. | Working when Screen Recording is granted. | Permission preflight, native route self-tests, visible OCR mock paths. | Put real inbox/front window in the right state. |
| Screen status | Jarvis can explain screen/OCR readiness without taking a screenshot. | Working; Jarvis 98 answers `screen status` natively in the app and through the worker API. It reports Screen Recording state, permission target path, bundle id, native OCR readiness, and confirms no capture/OCR/storage occurred. | Unit tests, bundled API smoke, Mac Control UI smoke, Copy Tests smoke, full verifier. | Use this before private visible-OCR tests if permissions look confusing. |
| Copy debug JSON | Copy complete chat/debug context for Codex. | Working; export includes app version/build, permission summary, per-permission diagnostics, and persisted Codex job counts. | Mac Control copy button plus clipboard schema parse. | Paste JSON back when a real failure includes private context. |
| Launch diagnostics | Jarvis can tell Leo exactly how to reopen the stable app. | Working; Jarvis 83+ answers `Jarvis launch status` with the stable app path, open command, short launcher, version/build, and bundle id. | Unit tests, bundled API smoke, Mac Control UI smoke. | Use the command if Dock/menu-bar launch feels broken. |
| Permissions panel | Show Microphone, Speech, Screen Recording, Accessibility, Notifications. | Working as readiness display; Jarvis 77+ answers `permissions status` locally in chat; Jarvis 86 includes exact permission target path and bundle id. | Snapshot and self-tests; Mac Control UI smoke for `permissions status`. | Grant missing permissions to the stable `output/Jarvis.app` identity. |
| Keyboard shortcut wake | Reliable keyboard wake/focus path before true voice wake. | Working with `Command+Option+J`; Jarvis 82 also answers `hotkey status` locally and says real microphone wake is not active yet. | Swift hotkey self-test, native route self-test, Mac Control UI smoke. | Try the shortcut on Leo's keyboard. |
| Wake phrase | Background "Hey Jarvis" activation. | Text simulation only; Jarvis 84 answers `wake status` and clearly says real microphone wake is not active yet. | Wake text parser, false-positive text tests, bundled API smoke, Mac Control UI smoke. | Real voice samples, microphone permission, false-wake tuning. |
| Voice status | Explain microphone, Speech Recognition, keyboard wake, typed wake, TTS, and not-yet-active STT/wake-word state without recording audio. | Working; Jarvis 91 answers `voice status` natively from the Swift app. | Swift self-test, Mac Control UI smoke, Copy Tests smoke. | Judge wording and later grant microphone/speech permissions. |
| Speech-to-text | Convert Leo's voice into commands. | Not built; `voice status` now says this directly. | Synthetic audio only if a local STT path is chosen. | Real microphone permission and Leo voice tests. |
| TTS status | Jarvis can explain speech-output readiness without playing audio. | Working; Jarvis 97 answers `tts status` natively in the app and through the worker API, reporting macOS `say`, explicit speech commands, automatic spoken replies off, detected voices, and no audio playback. | Unit tests, bundled API smoke, Mac Control UI smoke, Copy Tests smoke, full verifier. | Pick voice, volume, interruption behavior later. |
| Text-to-speech | Jarvis speaks replies naturally. | Explicit-command local `say` route built; automatic spoken replies not built. | Mocked macOS `say` tests and bundled non-audio plan smoke. | Test actual audio while awake. |
| Always-on background mode | Listen while Mac is open without annoying prompts. | Not built. | Launch-at-login and idle worker tests. | Battery/privacy preference decisions. |
| Accessibility computer control | Click/type/read UI across apps safely. | Not granted. | Policy/plan tests and Mac Control outside Jarvis. | Grant Accessibility to Jarvis and approve real workflows. |
| Browser control | Open/read webpages and act safely. | Planning route only. | URL plan tests, injection scan tests. | Browser session/account-specific tasks. |
| File/project work | Read/search project files and hand complex edits to Codex. | Read-only shell/search working; edits stay gated. | Unit tests and safe shell policy tests. | Approve write/destructive actions. |
| Safety confirmations | Private reads logged; sends/deletes/settings require confirmation. | Working. | Policy tests and verifier gates. | Confirm intentional risky actions. |
| Audit log | Local audit with retention/size cap; no raw screenshots/audio by default. | Working. | Audit status and redaction tests, including private email/injection excerpt omission. | Decide retention changes later. |
| Model comparison | Benchmark actual available models instead of guessing. | Working for Groq/Ollama fast lane; chat bubbles now display backend/model/timing so Leo can see when Groq or Ollama answered. | Repeat benchmark scripts and first-token probes; UI smoke for visible model detail. | Supply extra API keys if desired. |
| Elevating router | Route simple tasks instantly, normal chat/email to fast model, ambiguous harder tasks to a smarter middle planner, and code/project work to async Codex. | Partly designed; Jarvis 103 adds `elevation status` without calling a model. Deterministic, fast chat, and async Codex layers exist; smarter middle planner is next. | Unit tests, bundled API smoke, model/timing UI smoke. | Decide which model/API to use for the smarter middle layer. |
| Memory | Build a model memory about Leo from daily Jarvis summaries, with optional MacBook Air sync and a growing MEMORY.md-style profile. | Designed, not enabled; Jarvis 103 adds `memory status` and explicitly does not read or sync chat history. | Unit tests and no-content API smoke. | Approve retention, deletion, privacy, and whether raw chat is ever synced. |
| Remote Mac helper | Use MacBook Air over Tailscale SSH for helper tasks. | Reachable and surfaced in Jarvis 103. `remote worker status` reached `Hongyis-MacBook-Air.local` at `hongyi@100.72.212.85`, macOS 26.5, Apple M3, 8 GB RAM, in about 0.2s, reading only system identity metadata. Automatic remote jobs are not enabled. | Bounded SSH read-only probes, remote status route tests, remote helper design tests. | Approve any real remote-worker execution scope and safety model. |
| Shopping-list APIs | Add keys only when a feature needs them. | Groq key configured. | Env-file parsing and provider availability checks. | Provide keys for future STT/TTS/OpenAI/general model providers. |

## Current Safe Test Set

Use these when checking a new build without exposing private content:

1. `status`
2. `hello Jarvis`
3. `tell me a short joke`
4. `Write five short bullets about making Jarvis feel fast.`
5. `latency status`
6. `model status`
7. `elevation status`
8. `memory status`
9. `remote worker status`
10. `capabilities status`
11. `voice status`
12. `tts status`
13. `test status`
14. `safety status`
15. `what time is it`
16. `what date is it`
17. `battery status`
18. `storage status`
19. `set a timer for 5 seconds`
20. `timer status`
21. `cancel timers`
22. `volume up`
23. `sound down`
24. `play current`
25. `play current song`
26. `play next`
27. `play previous`
28. `brightness up`
29. `say exactly: Jarvis local exact route OK`
30. `Hey Jarvis, check the time`
31. `Hey Jarvis run sudo whoami`
32. `ask Codex to say exactly: Jarvis Codex smoke test OK`
33. `ask Codex to review this project`
34. `codex jobs`
35. `codex speed status`
36. `permissions status`
37. `screen status`
38. `hotkey status`
39. `wake status`
40. `Jarvis launch status`
41. `email backend status`
42. Click `Copy Chat JSON`.

## Private Tests For Leo Only

Use these when Leo is ready to expose the result locally in Jarvis:

1. `check my email and summarize the newest email in my inbox`
2. `read the visible Outlook screen with OCR`
3. Real microphone/wake-word tests after microphone and speech permissions are granted.
