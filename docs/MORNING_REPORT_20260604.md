# Jarvis Morning Report - 2026-06-04

Updated: 2026-06-04 09:22 CST

## Current Build

- App: `output/Jarvis.app`
- Version/build: 0.1.106 / 106
- Open command:
  ```bash
  open "/Users/leoxu/Library/CloudStorage/OneDrive-YKPaoSchool上海民办包玉刚实验学校/developer/Jarvis/output/Jarvis.app"
  ```
- Short launcher:
  ```bash
  scripts/open_jarvis.sh
  ```
- Worker: bundled app worker on `http://127.0.0.1:8765`
- Fast model: Groq `llama-3.3-70b-versatile`
- Fast fallback: Ollama `qwen3:0.6b`
- Latest full verifier: `runtime/verification/verify-safe-20260604-092211.json`, 89/89 passed
- Full target/test matrix: `docs/CAPABILITY_TEST_MATRIX.md`
- Fast-model decision note: `runtime/model_benchmarks/model-selection-decision-20260603.md`
- Latest localhost fast-latency smoke: `runtime/model_benchmarks/localhost-fast-latency-20260604-054221.md`

## At A Glance

- You can open and use Jarvis now from `output/Jarvis.app`; `scripts/open_jarvis.sh` is the short launcher.
- Normal chat is fast enough for the current prototype: latest max first visible text is 0.795s, and follow-on output is faster than normal speaking speed.
- Best safe first tests: `hello Jarvis`, `latency status`, `model status`, `elevation status`, `memory status`, `remote worker status`, `what time is it`, `what date is it`, `battery status`, `permissions status`, `screen status`, and `Copy Tests`.
- Best private test when you are awake: `check my email and summarize the newest email in my inbox`.
- Still not solved: real microphone wake word, real speech-to-text, always-speaking replies, guaranteed full-mailbox email, automatic memory sync, automatic remote-worker jobs, and broad computer control.
- Current verifier is clean: 89/89 passed on Jarvis 106.

## What Works Now

- Typed chat with immediate in-chat working bubble.
- Pasting into Jarvis is improved. The app now has a standard `Edit` menu, and `Edit > Paste` / `Command+V` has a Jarvis fallback that pastes clipboard text into the command field even if the AppKit field editor does not become first responder. Mac Control verified both the Paste button and menu Paste path in Jarvis 64.
- Streaming fast chat for ordinary conversation. Jarvis now treats first useful visible text as the main speed metric, not total dump time. Jarvis 66 live localhost smoke for `hello Jarvis`: first visible text 1.18s, final about 1.24s.
- Joke/casual replies are tightened. Jarvis 67 live localhost smoke for `tell me a short joke`: first visible text 0.88s, final about 0.92s, one direct short joke.
- Jarvis 68 live localhost smoke for `Write five short bullets about making Jarvis feel fast.`: first visible text 0.65s, final about 0.96s, exactly five non-empty lines.
- Added `scripts/smoke_fast_latency.py` so first-visible-text can be checked against the actual running Jarvis localhost stream, including Jarvis routing overhead. Fresh Jarvis 70 smoke at 02:05 CST: `hello Jarvis` first visible 0.679s / total 0.857s; `tell me a short joke` first visible 0.669s / total 0.779s; five-bullet prompt first visible 0.627s / total 1.019s.
- Jarvis 72 adds a local `latency status` command. It reads the latest smoke report without calling a model. Latest Jarvis 72 smoke at 02:21 CST: `hello Jarvis` first visible 0.650s / total 0.761s; `tell me a short joke` first visible 0.679s / total 0.779s; five-bullet prompt first visible 0.667s / total 0.883s.
- Latest Jarvis 75 localhost smoke at 02:46 CST: `hello Jarvis` first visible 0.778s / total 0.884s; `tell me a short joke` first visible 0.568s / total 0.661s; five-bullet prompt first visible 0.738s / total 0.944s. Mac Control also verified `latency status` through the actual app UI.
- Latest Jarvis 76 localhost smoke at 02:55 CST: `hello Jarvis` first visible 0.583s / total 0.782s; `tell me a short joke` first visible 0.623s / total 0.720s; five-bullet prompt first visible 0.681s / total 0.972s.
- Latest Jarvis 77 localhost smoke at 03:01 CST: `hello Jarvis` first visible 0.638s / total 0.743s; `tell me a short joke` first visible 0.650s / total 0.744s; five-bullet prompt first visible 0.724s / total 0.971s.
- Latest Jarvis 78 localhost smoke at 03:07 CST: `hello Jarvis` first visible 0.953s / total 1.047s; `tell me a short joke` first visible 0.670s / total 0.783s; five-bullet prompt first visible 0.765s / total 1.111s.
- Latest Jarvis 80 localhost smoke at 03:15 CST: `hello Jarvis` first visible 0.665s / total 0.886s; `tell me a short joke` first visible 0.726s / total 0.837s; five-bullet prompt first visible 0.757s / total 1.002s.
- Latest Jarvis 81 localhost smoke at 03:20 CST: `hello Jarvis` first visible 0.701s / total 0.868s; `tell me a short joke` first visible 0.649s / total 0.754s; five-bullet prompt first visible 0.664s / total 0.902s.
- Latest Jarvis 82 localhost smoke at 03:28 CST: `hello Jarvis` first visible 0.682s / total 0.857s; `tell me a short joke` first visible 0.713s / total 0.815s; five-bullet prompt first visible 0.655s / total 0.924s.
- Latest Jarvis 83 localhost smoke at 03:36 CST: `hello Jarvis` first visible 0.846s / total 1.044s; `tell me a short joke` first visible 0.686s / total 0.787s; five-bullet prompt first visible 0.761s / total 1.056s. Still inside the 1-3s first-visible target.
- Latest Jarvis 84 localhost smoke at 03:43 CST: `hello Jarvis` first visible 0.577s / total 0.701s; `tell me a short joke` first visible 0.702s / total 0.878s; five-bullet prompt first visible 0.591s / total 0.908s.
- Jarvis 85 improves the latency smoke to track after-first output speed, because first visible text is what makes the answer feel immediate and subsequent output only needs to outpace normal speech. Latest Jarvis 99 smoke at 05:42 CST: max first visible 0.795s, max total 1.014s, and slowest after-first output 150.5 chars/s.
- Groq remains the primary fast chat model, but Jarvis now has an Ollama fallback if Groq is missing, unreachable, times out, errors, or returns empty text. Results record the primary backend/status so exports stay honest.
- Deterministic quick commands: time, timers, timer status, cancel timers, pause/resume/status, volume, brightness, and media controls. Jarvis 103 routes `play current`, `play current song`, `play next`, and `play previous` directly to system media-key equivalents instead of Music-only AppleScript. Live smoke shows macOS blocks those synthetic media keys until Accessibility permission is granted, and Jarvis now says that clearly. Brightness uses local CoreDisplay APIs. Jarvis 78 also understands `set volume to 42%` and `set brightness to 65%`; I verified these through `/api/plan` only so Leo's actual settings were not changed overnight. Jarvis 80 adds `timer status`, and a live bundled API smoke returned `No active timers.`
- Tests now explicitly cover Leo's quick-control wording: `sound up`, `sound down`, `play current`, `play next`, and `play previous`.
- Timer completion is more visible in the app. When Leo sets a timer from the Jarvis UI, Swift now schedules a matching local chat completion message; `cancel timers` cancels those UI timer mirrors. I did not fire a real timer completion overnight to avoid a possible macOS notification banner.
- Explicit local speech commands are now routed locally through macOS `say`: `speak ...`, `say out loud ...`, and `read ... loud ...`. I only tested this through plan/mock paths overnight, so no audio played while Leo was asleep.
- Codex CLI delegation still works for explicit code/project/review requests, but it is intentionally not used for casual chat. Broad code/project/review requests now start an async `codex.job` instead of blocking the chat; check them with `codex jobs` or `codex job <id>`.
- The Jarvis UI now watches started async Codex jobs and appends the finished result to the chat when the job stops running. Mac Control verified this in the real Jarvis 84 window with job `codex-52dc2f64`: the job completed in 1m 55.0s and the app appended `Jarvis UI async monitor is OK.`
- Real async Codex smoke was run after Jarvis 72. Jarvis returned the job id in 0.148s, then `codex-e5b4e479` completed in 1m 55.5s with the reply: "Jarvis is a local Mac assistant prototype with a Swift app and a Python worker." Morning status now shows `0 running, 1 tracked`.
- Jarvis 75 persists Codex job summaries across worker/app restarts. A real async persistence smoke returned job id `codex-2451a9b1` in 0.170s, completed in 1m 57.6s, wrote a bounded `runtime/codex_jobs.json` summary without the huge planned command, and was still visible after restarting the app. `codex jobs` and `codex job codex-2451a9b1` are now correctly labeled as local read-only status checks.
- Codex requests now show a clearer in-chat working message: `Handing this to Codex. This can take a while...`
- Exact-output smoke tests stay local unless Leo explicitly asks Codex.
- Copy Chat JSON now includes app version/build, base URL, fast model/backend/fallback, timer count, worker runtime/source, readiness/verifier details, structured last response, and first-token timing when available. Mac Control verified the Jarvis 84 clipboard JSON after the async Codex monitor smoke; it parsed as `jarvis.chat.debug.v1`, showed version/build 0.1.84/84, 5 permission rows, latest completed job `codex-52dc2f64`, and 6 non-private messages.
- Generic read-only email requests now try Apple Mail metadata first, then structured Outlook metadata/database routes. Jarvis 103 no longer falls back to visible Outlook OCR for normal `check my email` requests, because Leo's Outlook start view does not expose the newest email body. Explicit `read the visible Outlook screen with OCR` still uses native Apple Vision OCR.
- Structured Apple Mail/Outlook email replies now explicitly say they selected the newest inbox email including read messages, and the JSON result includes `selection_rule: newest_received_any_read_state`.
- Jarvis 76 improves Outlook fallback behavior: if Outlook AppleScript is blocked by Automation permission, the worker now continues to the local Outlook SQLite route and OCR fallback before giving up. If every route fails, the response keeps the AppleScript/SQLite/OCR failure diagnostics instead of pretending only one permission is the problem.
- Explicit visible/screen/OCR email requests go straight to native Apple Vision OCR.
- Local email/OCR snippets now run through the prompt-injection scanner. If suspicious text is found, Jarvis shows a label-only warning and treats the text as untrusted content. Audit logs store only scan status/counts, not private excerpts.
- Natural text starting with `Hey Jarvis`, `OK Jarvis`, or `Okay Jarvis` now routes through text wake simulation and reports the extracted command's risk.
- `python3 scripts/morning_status.py` now prints fast model/backend/fallback, bundled-worker source, app version/build, bundle id, verification age, and the exact open command.
- `python3 scripts/morning_status.py` also prints the short launcher and whether multiple Jarvis app processes are running.
- `python3 scripts/morning_status.py` now prints the latest localhost fast-latency smoke result, including max first visible text and max total time.
- Worker health, morning status, and Copy Chat JSON now include Codex job counts. Idle state shows `Codex jobs: 0 running, 0 tracked`.
- Mac Control verified Jarvis 70 `Copy Chat JSON`; the copied JSON includes `diagnostics.health.codex_jobs` and timer count.
- Mac Control verified Jarvis 73 `Copy Chat JSON`; the copied JSON now includes `app.permission_summary` and `diagnostics.permissions`, including Screen Recording/Accessibility/Microphone/Speech/Notifications states. Clipboard was restored to `Copy Tests` afterward.
- Mac Control verified Jarvis 75 `Copy Chat JSON`; the copied JSON reports version/build 0.1.75/75, `diagnostics.health.codex_jobs` with the persisted completed job, and five permission rows. Clipboard was restored to `Copy Tests` afterward.
- Jarvis 77 adds a native local `permissions status` command. Mac Control verified the actual app replies with the current 1/5 permission breakdown without calling the worker or a model.
- Jarvis 86 improves `permissions status` with the exact macOS permission target: the stable app path `.../output/Jarvis.app` and bundle id `local.leo.jarvis`. Mac Control verified the real app response, so Leo can compare System Settings against the running binary instead of guessing from the friendly app row.
- Jarvis 82 adds a native local `hotkey status` command. Mac Control verified the actual app replies with `Command+Option+J`, and clearly distinguishes keyboard wake/focus from the not-yet-built microphone wake-word listener.
- Jarvis 83 adds `Jarvis launch status`. It answers with the exact stable `open ".../output/Jarvis.app"` command, short launcher, version/build, and bundle id from the bundled worker. Mac Control verified the real app response.
- Jarvis 84 adds `wake status`. It reports that keyboard wake/focus and typed wake simulation are available, while real background microphone wake-word listening is not active yet. Mac Control verified the real app response.
- Jarvis 85 updates `latency status` to report the after-first output-rate metric. Mac Control verified the actual app shows `min after-first output 209.3 chars/s`.
- Jarvis 88 improves `email backend status`, a no-content diagnostic that explains the current Mail/Outlook route order without reading email. Mac Control verified the real app response says it did not read email content, names the disabled `JARVIS_OUTLOOK_USE_APPLESCRIPT` and `JARVIS_OUTLOOK_USE_LEGACY_SQLITE` settings, and currently sees `visible_ocr` from the worker route.
- Jarvis 93 corrects `email backend status`: Apple Mail metadata is reported separately from the disabled Outlook AppleScript flag. Mac Control verified the real app response now lists `apple_mail_applescript` and `visible_ocr` as available routes without reading email content.
- Jarvis 90 adds `capabilities status`, a no-content product diagnostic that says what is working, partial, and not ready. Mac Control verified the real app response reports 5 working, 5 partial, and 1 not ready, and explicitly says it did not read email, screenshots, microphone audio, or files.
- Jarvis 91 adds native `voice status`. Mac Control verified the real app response reads the current Microphone and Speech Recognition permission rows, says keyboard wake and typed wake are available, and clearly says background microphone wake-word listening and real speech-to-text command transcription are not active yet. It does not record or transcribe audio.
- Jarvis 92 adds native `test status`. Mac Control verified the real app response says Copy Tests currently has 31 prompts and points Leo to the Copy Tests and Copy Chat JSON buttons.
- Jarvis 94 adds `safety status`. Mac Control verified the real app response summarizes confirmation gates, private-read logging, prompt-injection scanning, shell restrictions, and no raw audio/screenshot storage without reading private content.
- Jarvis 95 adds `codex speed status`, a no-content local diagnostic that reads persisted Codex job timings without starting another Codex job. Mac Control verified the real app response summarizes 2 completed jobs, average 1m 56.3s, fastest 1m 55.0s, slowest 1m 57.6s, and reminds that normal chat should not wait for Codex.
- Jarvis 96 adds `model status`, a no-content local diagnostic for the active fast-model route. Mac Control verified the real app response shows Groq `llama-3.3-70b-versatile`, Ollama fallback `qwen3:0.6b`, 5s timeout, 80 output-token cap, and the latest first-visible latency smoke numbers.
- Jarvis 97 adds `tts status`, a no-audio speech-output diagnostic. The worker route and native app route both report macOS `say` availability, explicit speech commands, automatic spoken replies off, voice count, and that no audio was played or recorded. Mac Control verified the real app response and Copy Tests includes it.
- Jarvis 98 adds `screen status`, a no-capture screen/OCR readiness diagnostic. The worker route reports `screencapture` availability without taking a screenshot, and the native app route reports Screen Recording permission, the stable permission target path, bundle id, native OCR readiness, and that no screen capture/OCR/storage occurred. Mac Control verified the real app response.
- Jarvis 99 adds deterministic `what date is it` / `what day is it` handling. It bypasses Groq/Codex and replies locally with the Beijing-date context; Mac Control verified the real app response `Today is Thursday, June 4, 2026.`
- Jarvis 100 adds deterministic `battery status` handling through the quick local route. It reads `pmset -g batt`, bypasses Groq/Codex, and Mac Control verified the real app response `Battery status: 100%, charged.`
- Jarvis 101 adds deterministic `storage status` handling through the quick local route. It uses Python disk usage, bypasses Groq/Codex, and Mac Control verified the real app response `Storage status: 181.1 GB free of 460.4 GB total (60.7% used).`
- Jarvis 103 adds three no-content product diagnostics: `elevation status`, `memory status`, and `remote worker status`. Live API smoke verified the MacBook Air helper is reachable over Tailscale SSH at `hongyi@100.72.212.85` as `Hongyis-MacBook-Air.local`, macOS 26.5, Apple M3, 8 GB RAM, in about 0.2s; the probe read only system identity metadata.
- Jarvis 103 chat bubbles now display the model backend, model name, total model time, and first-visible timing when available. Mac Control verified the real app shows `Groq llama-3.3-70b-versatile | Fast model time: 0.8s | First visible: 0.7s` under a `hello Jarvis` reply.
- Jarvis 104 changes normal direct address to `Sir` while preserving Leo as the known real name for profile/memory context. API smoke verified `hello Jarvis` replied `Hello Sir, what would you like done?` through Groq in 0.9s.
- Jarvis 105 removes routine direct address entirely because Leo said both `Leo` and `Sir` felt weird. The model still knows the real name for profile context, but normal replies should not call him Leo, Sir, or a title. API smoke verified `hello Jarvis` replied `Hello, what do you want done?` through Groq in 0.7s, and the app user bubble label is now `You`.
- Jarvis 106 fixes the Apple Mail pull blocker from Leo's exported chat JSON. The real failure was `Mail got an error: Can't continue cleanText (-1708)`: inside `tell application "Mail"`, AppleScript was sending `cleanText(...)` to Mail instead of calling Jarvis's local handler. Both Apple Mail and Outlook scripts now use `my cleanText(...)`, and zero-message structured-route failures no longer report as successful `checked` Outlook reads. I did not run a private live email read; Leo should test `check my email and summarize it` in Jarvis.
- The app now has a `Copy Tests` button. The current list has 43 prompts, including `latency status`, `model status`, `elevation status`, `memory status`, `remote worker status`, `capabilities status`, `voice status`, `tts status`, `test status`, `safety status`, `what date is it`, `battery status`, `storage status`, `codex speed status`, `timer status`, `permissions status`, `screen status`, `hotkey status`, `wake status`, `Jarvis launch status`, `email backend status`, the joke canary, quick-control aliases, email/OCR checks, and async Codex job prompts.
- There is now a project-local launcher script: `scripts/open_jarvis.sh`. It uses normal `open`, so it should bring up the stable app without intentionally creating duplicate instances.
- Reopening is fixed for the closed-window case. Mac Control verified: close the Jarvis panel, run `scripts/open_jarvis.sh`, and the panel returns while the app stays single-instance.
- Logo check: the bundled app uses the Iron Man head image. `JarvisLogo.png` is 512x512 and `Jarvis.icns` reports 1024x1024.

## Still Not Good Enough

- Email is not yet a guaranteed full-mailbox newest-email system. If macOS Automation blocks Apple Mail/Outlook metadata, normal email now stops with a structured failure instead of pretending visible Outlook OCR can see the newest message body.
- Apple Mail structured reading may require Automation permission for Jarvis or the worker process.
- Wake word, microphone input, speech recognition, and TTS are not yet built as a real background listener.
- Always-speaking replies are not enabled. TTS is currently explicit-command only.
- Accessibility permission is still not granted, so real app-control workflows are limited.
- System media-key commands need Accessibility permission because macOS blocks synthetic keystrokes without it.
- Brightness control is implemented through local CoreDisplay APIs, but I only tested no-op read/set and plan routing overnight to avoid changing Leo's display while he was asleep.
- Codex CLI can still be slow; it is now reserved for deeper work, not normal conversation.
- Async Codex job worker lifecycle, restart persistence, and UI auto-posting are verified.

## Recommended Next Build Order

1. Make email reliable first: structured Apple Mail metadata, then Outlook metadata, then explicit visible OCR only as an honest fallback.
2. Build the smarter middle elevation route between fast chat and Codex.
3. Add local daily memory summaries, then optional approved MacBook Air sync.
4. Add real speech-to-text as a push-to-talk or keyboard-triggered mode before always-on wake word.
5. Add spoken replies behind an obvious toggle, using macOS voices first.
6. Add Accessibility-based computer control one workflow at a time, starting with safe read-only app inspection and media-key confirmation.

## Leo Test Prompts

Paste these into Jarvis:

1. `hello Jarvis`
2. `tell me a short joke`
3. `Write five short bullets about making Jarvis feel fast.`
4. `latency status`
5. `model status`
6. `elevation status`
7. `memory status`
8. `remote worker status`
9. `capabilities status`
10. `voice status`
11. `tts status`
12. `test status`
13. `safety status`
14. `what time is it`
15. `what date is it`
16. `battery status`
17. `storage status`
18. `set a timer for 5 seconds`
19. `timer status`
20. `cancel timers`
21. `volume up`
22. `sound down`
23. `play current`
24. `play current song`
25. `play next`
26. `play previous`
27. `brightness up`
28. `say exactly: Jarvis local exact route OK`
29. `Hey Jarvis, check the time`
30. `Hey Jarvis run sudo whoami`
31. `ask Codex to say exactly: Jarvis Codex smoke test OK`
32. `ask Codex to review this project`
33. `codex jobs`
34. `codex speed status`
35. `permissions status`
36. `screen status`
37. `hotkey status`
38. `wake status`
39. `Jarvis launch status`
40. `email backend status`
41. `check my email and summarize the newest email in my inbox`
42. `read the visible Outlook screen with OCR`
43. Click `Copy Chat JSON`, then paste the JSON back to Codex if anything looks wrong.

Shortcut: click `Copy Tests` in Jarvis to copy this smoke-test set from the app itself.

## Notes For Leo

- For email, test privately because the copied chat may include message snippets.
- If an email contains text like "ignore previous instructions", Jarvis should warn about prompt injection instead of treating it as a command.
- If Apple Mail is quit, the structured Apple Mail route attempts to launch it through AppleScript. It still needs macOS Automation permission to read inbox metadata.
- The first useful visible token is now the speed metric, not just total answer time.
- A model that stays silent for 2 seconds and then dumps everything instantly is still considered too slow for normal Jarvis conversation. After first visible text appears, token output only needs to outpace normal human speech.
- MacBook Air Tailnet probe: a bounded read-only SSH check now works from Jarvis and this Codex context. `remote worker status` reports `Hongyis-MacBook-Air.local`, currently macOS 26.5.1, arm64, Apple M3, 8 GB RAM. This proves reachability, not a finished remote-worker safety model.

## API Key Shopping List

- Already useful now: Groq API key, configured.
- Useful later: OpenAI API key for non-Codex model calls if you want OpenAI models outside the Codex CLI login.
- Useful later: STT provider key only if local/macOS speech recognition is not good enough.
- Useful later: TTS provider key only if macOS voices are not good enough.
- Not needed tonight: more model keys. The current fastest usable chat lane is already under the 1-3 second target zone.
