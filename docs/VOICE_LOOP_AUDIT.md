# Local Voice Loop Audit + Barge-In Design

Author: research teammate (autonomous run), 2026-07-02
Status: audit + design only — no code changed, no file touched except this one.
Scope: (1) what Jarvis's local STT+TTS voice loop actually does today, end to end,
and (2) how to design microphone barge-in / interruption so a user can cut Jarvis
off mid-speech without re-saying "Hey Jarvis" — the one thing the discrete local
pipeline lacks versus OpenAI's Realtime API, which Richard and Leo have decided
against on cost grounds (see `docs/OPEN_QUESTIONS.md` "Voice" / "Model Backend").

> **Bottom line up front.** The local loop is real and mostly on-device: a single
> continuous **Apple `SFSpeechRecognizer`** session (on-device when available)
> does *both* wake detection *and* the command transcription that follows — there
> is **no hand-off to faster-whisper** on the live path. faster-whisper tiny.en
> exists only as a **no-prompt fallback for unattended *file* QA**, never on the
> live mic. TTS is **Piper (local neural) as primary**, via a persistent warm
> worker, with macOS `say` as fallback. **Barge-in is already ~70% built** and far
> more mature than the brief assumed: `JarvisShellModel` keeps the recognizer live
> during playback, has two-tier (explicit-phrase / substantial-utterance)
> interruption detection, a text-level self-echo filter, and a post-command grace
> window — and it already calls `stopSpeaking()` when it fires. **Two real gaps
> remain:** (a) barge-in is armed off an *estimated* speech-duration timer, not a
> real "audio is playing" signal, and (b) when it fires it only **stops** Jarvis —
> it does **not route the interrupting utterance as the next command**, so the user
> still must re-say "Hey Jarvis." The honest blocker under all of this: **no part
> of the live mic path has ever been verified against real human speech through a
> real microphone** — every existing "STT/wake works" claim comes from synthetic
> transcript strings or synthesized-TTS audio files. Recommended MVP: promote the
> timer to a real playback signal, add utterance-capture-on-barge-in, and — before
> trusting any of it — run the *first real live-mic session* to measure command
> STT and acoustic self-echo. Do **not** ship an aggressive always-on barge-in
> until that measurement exists.

I read the live source, not just the docs (the docs have been stale before). All
claims below are cited to `file:line`.

---

## Part 1 — What the voice loop actually does today

### 1a. Wake-word path — on-device Apple Speech, continuous

`swift-shell/Sources/JarvisMenuBar/Support/JarvisWakeListener.swift` is a
`@MainActor` state machine driven by one `SFSpeechRecognizer(locale: en-US)`
(`:92`). On start it requests mic + Speech authorization (`:164-185`), installs an
`AVAudioEngine` input tap that streams PCM buffers into an
`SFSpeechAudioBufferRecognitionRequest` (`:20-29`, `:219-247`), and — when the OS
supports it — forces **on-device** recognition: `request.requiresOnDeviceRecognition
= true`, labelled "Apple Speech on-device" (`:221-226`). Partial results are on
(`:220`), so it reacts to speech as it streams.

Wake matching is local and fuzzy. `detectWake` (`:593-662`) first tries exact
prefixes for `"hey jarvis" / "okay jarvis" / "ok jarvis"`, then a sliding-window
Levenshtein similarity (`bestFuzzyWakeMatch`, `:664-694`) against a **0.86**
threshold (`wakeSimilarityThreshold`, `:42`). So "hey jervis status" still fires.
This matches the "if Siri can do it locally, so can we" decision in
`OPEN_QUESTIONS.md` Voice Q2. Robustness plumbing around it: restart-storm damping
(`:569-577`), silent-session recovery (`:579-587`), and generation counters that
invalidate stale recognizer callbacks (`:283-284`).

### 1b. Post-wake command transcription — the key question — SAME session, no faster-whisper

**The command that follows "Hey Jarvis" is transcribed by the very same
`SFSpeechRecognizer` session, not a separate engine.** The state machine has phases
`waitingForWake → awaitingCommand → restarting` (`:56-74`). Every recognition
callback lands in `handleRecognition` (`:282-319`), which routes the *same*
transcript by phase (`:289-296`):

- In `waitingForWake`, `handleWakeCandidate` (`:321-336`) checks for the wake word.
  If the wake phrase arrives *with* an inline command ("hey jarvis what time is
  it"), it captures immediately; if it's the bare wake phrase, it flips to
  `awaitingCommand` and keeps the **same** session running.
- In `awaitingCommand`, subsequent partial transcripts from that same session go to
  `handleCommandCandidate` (`:338-365`), which normalizes the text, strips a
  re-heard wake phrase / "yes sir" greeting echo, and after a ~0.95 s debounce
  (`:358-364`) calls `captureCommand`.
- `captureCommand` (`:367-385`) cleans the text, stops the session, fires
  `onCommandCaptured`, then returns to `waitingForWake` after a 4 s delay (`:383`).

So: **audio capture → wake trigger → command capture → transcript** is *one*
Apple-Speech recognition lane end to end. On the Swift side, `onCommandCaptured`
(`JarvisShellModel.swift:579-611`) simply calls `submit(command)` into the normal
text pipeline. A repo-wide grep for `faster.whisper|WhisperModel` returns **zero
hits in any `.swift` file** — the live command path never touches faster-whisper.

One design consequence worth flagging: because `captureCommand` always returns to
`waitingForWake` (`:383`), **there is no "conversation-mode follow-up window"** in
which a second command can be given without the wake word — even though
`OPEN_QUESTIONS.md` Voice Q4 explicitly calls for one ("follow-up questions can
continue without saying Hey Jarvis again"). That un-built follow-up window is the
same capability barge-in needs (Part 2), so the two should be designed together.

### 1c. What faster-whisper is actually for (so no one over-trusts it)

`voice.stt_candidates` (`jarvis/tools.py:380-430`, `:8841-8969`) is a **selection /
comparison catalogue**, not a live router. It declares Apple Speech native as the
preferred live-dictation lane once authorized, and **faster-whisper tiny.en as the
"unattended no-prompt fallback"** (`:8969`, `:9038`) so headless QA can transcribe
*without* triggering a TCC permission prompt. faster-whisper is invoked only from
Python test harnesses (`scripts/voice_loop_qa.py:164`,
`scripts/probe_apple_speech_stt.py:153-171`) against **audio files**, and
`render_overnight_status.py:561` already records the honest caveat that "tiny.en
still mishears some technical words and is not good enough as the final live
dictation model." Net: on the real live loop, STT = Apple on-device Speech;
faster-whisper is a file-QA convenience only.

### 1d. TTS output — Piper primary (warm worker), macOS `say` fallback

TTS is **local neural Piper first**. `speak_text_async` → `_start_piper_speech_async`
(`jarvis/tools.py:2639-2724`) tries, in order:

1. **Piper warm worker** (`jarvis/piper_warm_worker.py`) when `TTS_PIPER_WARM_WORKER`
   is on (`tools.py:2646`). This is a persistent process that loads `PiperVoice`
   once, primes it with "Ready." (`piper_warm_worker.py:293-310`), then for each
   request **chunks** the text (`_chunk_text`, `:41-91`), pipelines
   synth-of-next-chunk against playback-of-current via a 1-worker executor
   (`:206-261`), plays each chunk WAV with `afplay`, and emits a `first_audio`
   latency event on the first chunk (`:241-250`). Crucially it also handles a
   `"stop"` message that terminates the live `afplay` mid-utterance
   (`:112-124`, `:321-323`) — this is what makes barge-in's `stopSpeaking()`
   near-instant.
2. **One-shot `piper_speaker.py`** (synth whole WAV, then `afplay`) if the warm
   worker is unavailable (`tools.py:2655-2724`).
3. **macOS `say`** exists as the OS-native fallback path (`tools.py:2525`,
   `:2941`, `:2809`).

**Latency profile:** the warm worker is *instrumented* for first-audio latency
(`first_audio_seconds`, `piper_warm_worker.py:243-250`) but **no persisted Piper
first-audio benchmark exists** in `runtime/` or `docs/`. The only committed latency
numbers are for the **text model** (`docs/MORNING_REPORT_20260604.md:41-52`:
first-visible-text ~0.6–0.8 s), which is a different stage. So "Piper feels fast" is
plausible-by-design (persistent voice + chunked prebuffer) but **not measured on
record**.

### 1e. The live-mic verification gap (applies to command transcription too)

**No committed harness has ever run real human speech through a real microphone —
for wake *or* command transcription.** All three "voice works" harnesses are
synthetic:

- `scripts/smoke_wake_threshold.py` — its own docstring says "without recording
  audio" (`:2`); it feeds **hardcoded transcript strings** (`:26-35`) to the fuzzy
  matcher. It tests the *matcher*, not STT.
- `scripts/voice_loop_qa.py` — **synthesizes** the user command with Piper
  (`:121-142`) and transcribes that synthetic WAV with faster-whisper (`:164-166`).
  It explicitly **refuses** physical capture: `--require-physical-capture is not
  supported yet; this harness verifies generated audio/STT, not physical speaker or
  microphone capture` (`:289`), and surfaces `physical_microphone_capture` /
  `physical_speaker_capture` as false in its contract (`:376`, `:432`).
- `scripts/probe_apple_speech_stt.py` — uses macOS `say` to render text to AIFF
  (`:76-83`), converts with ffmpeg (`:93-100`), and feeds the **file** to Apple
  Speech via `--stt-file-self-test` (`:111-127`). Real Apple Speech engine, but
  synthetic file input, not a live mic stream.

The production lane in 1a/1b — `AVAudioEngine` tap → streaming
`SFSpeechRecognizer` on a real human voice — is exercised by **none** of them.
Every "wake threshold passed N/N" and "reply similarity ≥ 0.90" claim is therefore
about synthetic audio or strings. This is not a knock on the code; the harnesses are
honestly labelled. It is a calibration fact: **we do not actually know how well
command STT works on Richard's real voice, in Richard's real room, yet.**

---

## Part 2 — Barge-in / interruption design

### 2a. Big finding: barge-in is already substantially built

The brief assumed barge-in doesn't exist. It mostly does. `JarvisShellModel`
already keeps the recognizer live during playback and reacts to it:

- **Every** wake-listener transcript update flows into
  `handleSpeechBargeInIfNeeded` via the `onStateChange` callback
  (`JarvisShellModel.swift:545-553`). The wake listener is **never suspended during
  TTS** — playback happens in a *separate* Python/`afplay` process, so the Swift mic
  tap keeps streaming and keeps being evaluated for interruptions.
- `handleSpeechBargeInIfNeeded` (`:717-757`) only acts while a speech window is
  "active" (`:722`), applies a post-command **grace window** so the tail of the
  user's own command doesn't self-trigger (`:725-731`, `bargeInGraceUntil` set to
  now+3.5 s on capture, `:588`), and de-dupes repeats (`:741-745`). When it decides
  to fire it clears the window and calls `client.stopSpeaking()` (`:748-756`).
- The decision core `shouldStopSpeechForBargeIn` (`:3127-3148`) is a three-filter
  gate: reject if the transcript looks like the wake phrase / the just-captured
  command being re-heard (`looksLikeWakeOrCapturedCommand`, `:3137`); reject if it
  looks like **Jarvis's own speech echoed back** (`looksLikeCurrentJarvisSpeechEcho`
  against the spoken text, `:3144`); otherwise require it to look like an
  intentional interruption.
- Two trigger tiers (`:3161-3199`): **explicit** stop-words — `stop, stop talking,
  shut up, be quiet, quiet, pause, cancel, wait, hold on, one second` — which fire
  even inside the grace window; and **implicit** "substantial new utterance" — ≥4
  tokens, ≥14 chars, ≥3 non-filler content words (`speechBargeInMinimumTokenCount`,
  `:85`, `:3169-3177`).

So the "echo-avoidance logic already in the codebase" the brief hoped for is real,
and it's the right thing to build on rather than replace.

### 2b. Gap 1 — barge-in is armed off an *estimated* timer, not a real audio signal

The active-window gate is `latestSpeechLikelyActiveUntil` (`:722`), and that value
is set from a **text-length estimate**: `estimatedSpeechPlaybackSeconds =
clamp(2…24, chars/14 + 1.2)` (`:1198-1204`), computed when a reply is noted
(`notePotentialSpeech`, `:694-706`). Nothing feeds *actual* playback state back
from the Piper worker into this window. Consequences:

- If Piper's first-audio latency is non-trivial, the window opens **before** sound
  actually starts, so an early "stop" can be dropped as "nothing is playing."
- If the estimate under-shoots (Piper `length_scale` 0.85 speeds speech up;
  chunking adds gaps), the window can **close while Jarvis is still talking**, and a
  late interruption is ignored.
- The barge-in fires `stopSpeaking()` even in cases where the worker already
  finished — harmless, but it means the feature's correctness rides on a guess.

The worker already **knows** the truth: it emits `first_audio`, `done`, and
`stopped` events with real timings (`piper_warm_worker.py:243-268`). Those events
just aren't propagated to the Swift active-window logic today.

### 2c. Gap 2 — barge-in stops speech but doesn't capture the new command

When barge-in fires it calls `stopSpeaking()` and clears the window (`:748-756`) —
and that's all. The interrupting utterance is **not** routed into `submit()` as the
next command. The recognizer is in `waitingForWake` during playback, so unless the
interruption literally begins with "hey jarvis …" (in which case the normal wake
path handles it), the user must re-say the wake word. That is exactly the
Realtime-API-parity behavior the brief wants and it is the missing piece: *interrupt
+ immediately issue a new command, no re-wake.*

### 2d. Gap 3 — echo suppression is **text-level**, not acoustic — the core risk

`looksLikeCurrentJarvisSpeechEcho` (used at `:3144`) compares the *transcript* of
what the mic heard against the *text* Jarvis is speaking. That defends against the
clean case: mic picks up Piper's voice, Apple Speech transcribes it accurately, the
strings match, barge-in is suppressed. **But there is no acoustic echo cancellation
(AEC).** The failure mode is: speaker output is picked up by the mic, Apple Speech
transcribes it *imperfectly* (partial/mangled — very likely for a neural TTS voice
over laptop speakers), the mangled transcript does **not** string-match the spoken
text, clears the ≥4-token/≥3-content bar, and **falsely triggers a barge-in that
cuts Jarvis off mid-sentence in a loop.** Whether this happens at all, and how
often, is **completely unknown** because — per 1e — the acoustic self-echo path has
never been run with real speakers + real mic. This is the single most important
thing to measure before making implicit barge-in aggressive.

### 2e. Proposed mechanism (concrete, builds on what exists)

1. **Replace the estimated window with a real playback signal.** Propagate the warm
   worker's `first_audio` / `done` / `stopped` events (`piper_warm_worker.py:243-268`)
   up through `tools.py`/`server.py` to a backend "speaking now: true/false + speech
   id" state the Swift model polls or is pushed. Gate `handleSpeechBargeInIfNeeded`
   on *that* instead of `latestSpeechLikelyActiveUntil`. This removes the guess and
   fixes both early-stop-dropped and late-interruption-ignored.
2. **Capture-and-route on interruption.** When barge-in fires: (a) `stopSpeaking()`
   as today; (b) flip the wake listener into a short **`awaitingCommand`
   conversation window** (reuse the exact `awaitingCommand` machinery and the ~0.95 s
   debounce, `JarvisWakeListener.swift:338-365`) so the *continuation* of the
   interrupting utterance is transcribed and `submit()`-ted as the next command —
   no re-wake. This is also the un-built `OPEN_QUESTIONS.md` Voice-Q4 follow-up
   window, so build them as one feature. Keep it time-boxed (e.g. 8–10 s) and
   fail-safe back to `waitingForWake`.
3. **Keep the two-tier detector, tune with real data.** Ship explicit stop-words as
   the *only* always-on trigger initially; keep implicit substantial-utterance
   barge-in **behind a setting, default off**, until 2d is measured. The thresholds
   (`speechBargeInMinimumTokenCount`, char/content minimums) are the right knobs to
   tune from a real session, not from synthetic strings.

### 2f. Phased recommendation (MVP-but-mature, not half-finished)

**Phase 0 — measure first (do this before any barge-in tuning).** Run the *first
real live-mic session*: Hey-Jarvis + a dozen real spoken commands through the real
microphone, and — separately — let Piper speak while the mic is live to observe
whether self-echo produces spurious transcripts. This is the missing input to every
threshold decision and directly closes the 1e gap. Record it honestly (it will be
the first non-synthetic voice datapoint in the repo).

**Phase 1 — MVP barge-in (mature, shippable).** (a) Real playback-state signal from
the warm worker replacing the estimated timer (2e-1); (b) explicit stop-words
barge-in on always, using that real signal; (c) capture-and-route so an
interruption that *contains* a command becomes the next command without re-wake
(2e-2), reusing the existing `awaitingCommand` path. Ship implicit/substantial-
utterance barge-in **off by default** (setting-gated) pending Phase 0 echo data.
This is a coherent, complete feature — not a stub — because explicit-phrase
interruption + real playback state + command re-routing is genuinely useful on its
own and can't false-trigger from garbled echo (stop-words are short and distinctive).

**Phase 2 — implicit barge-in + AEC, only if Phase 0 warrants.** Turn on
substantial-utterance barge-in with thresholds tuned from real data. If self-echo
proves to cause false triggers, add real acoustic echo cancellation (e.g. an AEC
stage on the input, or reference-signal subtraction using the known Piper output)
rather than leaning harder on the text-level filter — text matching cannot fix a
fundamentally acoustic problem.

**Defer:** speaker-identification ("only listen to Richard's voice", the
`OPEN_QUESTIONS.md` Voice-Q1 stretch goal) and any move to streaming
speech-to-speech. Both are real wants but orthogonal to getting reliable barge-in on
the existing local stack.

---

## Testing honesty

I did not run the app, speak to a microphone, or play Piper audio during this audit;
it is a source read. That is also precisely the point of §1e/§2d: the repo *itself*
has never done a live-mic run either, and its harnesses say so in their own code
(`smoke_wake_threshold.py:2`, `voice_loop_qa.py:289`). Every "STT/wake works" and
"reply similarity" number in the project today is synthetic-audio or
synthetic-string derived. Treat existing STT-quality confidence as **unverified for
real speech**, and treat Phase 0 above as a hard prerequisite before trusting
implicit barge-in. One minor code note in passing: the barge-in audit-log string is
hardcoded to "Leo started speaking" (`JarvisShellModel.swift:751`), a leftover of
the pre-generalization naming — cosmetic, but worth folding into the existing
de-Leo work.

## Sources (all in-repo)

- Wake + command STT: `swift-shell/Sources/JarvisMenuBar/Support/JarvisWakeListener.swift`
  (`:92` recognizer, `:221` on-device, `:282-385` phase routing + capture, `:593-694`
  fuzzy wake).
- Command → pipeline + barge-in: `swift-shell/Sources/JarvisMenuBar/Models/JarvisShellModel.swift`
  (`:544-611` wiring, `:694-757` speech window + barge-in, `:1198-1204` estimate,
  `:3127-3199` decision core).
- TTS: `jarvis/piper_warm_worker.py`, `jarvis/piper_speaker.py`,
  `jarvis/tools.py:2525`/`:2639-2724`/`:8841-9038`.
- Verification harnesses (all synthetic): `scripts/smoke_wake_threshold.py:2`,
  `scripts/voice_loop_qa.py:121-166`/`:289`, `scripts/probe_apple_speech_stt.py:76-171`.
- Decisions/context: `docs/OPEN_QUESTIONS.md` Voice Q1-Q4 + Model-Backend Q3;
  `docs/CUA_DRIVER_EVAL.md` (format/tone reference).
</content>
</invoke>
