# Jarvis Usability Reality Check

Generated: 2026-06-29 17:49 CST

This file is a blunt engineering snapshot of why Jarvis is still slow to make
usable, what is known to be broken or risky, and how hard the remaining work
really is. It is based on the current repo state, `JARVIS_BUG_BACKLOG.md`,
`.memory.md`, and the latest `scripts/morning_status.py` output.

## Bottom Line

Jarvis is not currently a dependable daily-driver assistant. It is a serious
prototype with many useful subsystems, but the remaining gaps are not simple
polish bugs. They are hard integration problems across macOS permissions,
speech input, speech output, browser automation, app control, model/tool
routing, safety, and proof.

The project is moving slowly because Jarvis is trying to be several products at
once:

- a voice assistant
- a macOS app
- a tool-calling AI agent
- a browser/app automation layer
- an email/calendar/system summarizer
- a music controller
- a Codex controller
- a safety-critical automation harness
- a testable product that can prove what it did

Each of those is hard alone. The hard part is making all of them work together
without lying, freezing the Mac, speaking private/internal text, opening random
Chrome tabs, or claiming success when the external app did not actually change.

## Current State On 2026-06-29

- Current repo root: `/Users/leoxu/Library/CloudStorage/OneDrive-YKPaoSchool上海民办包玉刚实验学校/developer/Jarvis`
- Current bundle reported by status: `output/Jarvis.app`, Jarvis `0.1.501` build `501`
- Current worker status: offline at `http://127.0.0.1:8765` when checked on 2026-06-29
- Latest safe verifier: `106/106` passed, but stale by about 82 hours
- Latest pre-build gate: `3/4`, failed because Teams assignment inspection is still incomplete
- Latest Teams status: `not_inspected`; browser actions were suppressed; safe Teams route exists but was not exercised
- Latest Chrome safety status: cleanup ok, no Jarvis/Codex test tab targets
- Latest physical audio loop status: missing; strict speaker/microphone proof fails closed

This means the latest proof is useful, but not fresh enough to call the live
product currently verified. Before claiming a release-quality state, we need to
relaunch Jarvis and rerun the verifier/gate from current HEAD.

## What "Actually Usable" Means

Jarvis should not be called actually usable until it can reliably:

1. Hear Leo say "Hey Jarvis" and then a command.
2. Transcribe the command correctly enough under normal room noise.
3. Decide whether a tool is needed without fake-looking keyword tricks.
4. Execute the tool or app action.
5. Prove the external result happened.
6. Show everything important it said and did in the app.
7. Speak only user-safe final text.
8. Stop speaking immediately when muted, interrupted, or told to shut up.
9. Leave Chrome, Music, Teams, Codex, and the Mac in a safe state after tests.
10. Pass a real end-to-end test suite before build/release.

Jarvis has partial implementations of many of these. It does not yet have a
stable, trustworthy full loop across the main real-world prompts.

## Difficulty Scale

- `1/5`: small code cleanup
- `2/5`: contained feature or normal bug
- `3/5`: cross-file feature with tests
- `4/5`: multi-system integration with real app proof
- `5/5`: product-level reliability problem involving external apps, OS
  permissions, safety, model behavior, and real-world testing

## Main Blockers

### 1. Teams/browser assignment workflow

Difficulty: `5/5`

Known problem: Jarvis still cannot reliably go into Teams, find the newest Music
assignment, inspect it, and ask Leo the right follow-up questions. It can route
toward Teams and it has bookmark/deep-link groundwork, but current proof says
`not_inspected`.

Why this is hard:

- Teams is authenticated and tied to Leo's Chrome session.
- Chrome Automation can be blocked by macOS permissions and Chrome settings.
- Teams is a complex dynamic web app, not a simple static page.
- OCR can capture the wrong Space/window under Stage Manager.
- Prior live browser attempts created dangerous Chrome tab/window pileups.
- A false success here is unacceptable because Jarvis could act on the wrong
  school assignment.

Current safety guardrails:

- Live Chrome navigation is suppressed by default in the full-loop harness.
- Chrome memory and tab/window count preflights exist.
- Fresh Chrome window creation is disabled unless explicitly enabled.
- Cleanup targets only Codex/Jarvis-created test surfaces.

What remains:

- Design a controlled awake-time live Teams run.
- Use the safe imported Teams route without creating tab explosions.
- Prove Jarvis can inspect the actual Music assignment, not a random visible
  assignment.
- Convert the result into follow-up questions.

### 2. Real speech-in/action-out/speech-back loop

Difficulty: `5/5`

Known problem: Much of the current "voice loop" proof is suppressed or
synthetic. It proves useful routing and speech-payload hygiene, but it is not the
same as Leo speaking into the Mac, Jarvis acting, Jarvis speaking out loud, and a
loopback STT confirming exactly what was spoken.

Why this is hard:

- The physical audio loop is not available.
- macOS microphone/speech permissions are fragile.
- Jarvis must distinguish Leo's voice from Jarvis's own speech.
- Barge-in needs to stop current speech without permanently muting Jarvis.
- Noisy public environments make STT harder.
- TTS must be pleasant, fast, interruptible, and faithful to visible text.

What remains:

- Establish a real loopback route or a reliable physical-audio test method.
- Run all canonical prompts through audio input and audio output.
- Compare spoken transcript with visible reply.
- Fail builds if visible/spoken replies diverge in user-important ways.

### 3. Hey Jarvis reliability

Difficulty: `4/5`

Known problem: Hey Jarvis has had crashes, menu-bar flicker, restart churn, and
cases where it stopped hearing Leo. Some restart and idempotency bugs have been
patched, but the live long-run microphone behavior is still risky.

Why this is hard:

- Apple's Speech framework can end sessions unexpectedly.
- Background always-listening behavior must not become a menu-bar flicker loop.
- Wake acknowledgement should usually be visual/quiet.
- If Jarvis listens forever, it must not capture or act on accidental speech.
- If it stops listening, Leo loses the product's main interface.

What remains:

- Long-duration soak tests.
- False wake tests.
- Noisy-room tests.
- Proof that Start Hey Jarvis stays listening until Stop Hey Jarvis.
- Proof that Stop cancels pending restarts every time.

### 4. Speech safety and "Shut Up"

Difficulty: `4/5`

Known problem: Jarvis has previously spoken when it should not, read internal
technical content aloud, spoken only part of a reply, kept talking after Shut Up,
or had no menu-bar control available while making sound.

Why this is hard:

- Speech can be triggered by multiple paths: status updates, final replies,
  explicit speech commands, wake acknowledgements, and tool results.
- The visible reply and spoken payload may intentionally differ.
- Sanitizers must remove tool/model/debug content without destroying useful
  answers.
- The emergency mute control must exist whenever sound can happen.

What remains:

- Keep expanding speech leak tests.
- Prove no internal tool/model text can reach TTS.
- Test long replies, Chinese/English mixed replies, links, and code blocks.
- Make the menu-bar emergency control impossible to lose in normal use.

### 5. Music playback ownership

Difficulty: `4/5`

Known problem: Music has been one of the most confusing parts of Jarvis. There
were cases where Jarvis claimed playback, LocalOS selected something but did not
play, hidden/mystery audio played, and the media keys could not clearly control
the result.

Why this is hard:

- Browser-based playback has autoplay restrictions.
- LocalOS, Chrome, native Music, and hidden audio helpers can all become
  possible playback owners.
- Jarvis must know whether audio actually started, not just whether a command
  was queued.
- Cleanup must stop playback and prove it stopped.

Current direction:

- Preferred path is the native Music app bridge.
- Hidden `afplay` should not be used for normal playback.
- A future separate native Music app is probably the right final product path.

What remains:

- Finish/verify the native Music app bridge as the only normal owner.
- Remove or keep fail-closed all legacy LocalOS/Chrome fallback paths.
- Add reliable media-owner inventory before and after every music test.

### 6. Model/tool routing at scale

Difficulty: `4/5`

Known problem: Leo has repeatedly caught behavior that looked like brittle
keyword matching pretending to be intelligence. Jarvis now has more honest
tool-routing labels and model-router guardrails, but scaling this to many skills
is still hard.

Why this is hard:

- The fast model must answer directly when no tool is needed.
- The model must call tools when tools are needed.
- Tool calls must be invisible to the spoken/user-facing answer.
- Fallbacks must be labeled honestly, not disguised.
- Adding many skills can make prompt/tool catalogs slow and confusing.

What remains:

- Keep the tool catalog compact and model-readable.
- Add a real middle-model strategy for more complex tasks.
- Keep deterministic shortcuts only where explicitly approved or clearly
  labeled as fallback.
- Add regression prompts designed to defeat fake keyword hacks.

### 7. Browser and computer control safety

Difficulty: `5/5`

Known problem: Jarvis's dream tasks require reading and controlling real apps:
Teams, Chrome, Codex, Activity Monitor, Calendar, possibly school portals and
Office apps. That is powerful enough to be dangerous.

Why this is hard:

- Actions like submit, send, delete, upload, purchase, or edit schoolwork must
  be gated.
- macOS Accessibility and Screen Recording permissions change what is possible.
- Browser state is private and authenticated.
- The app must expose what Jarvis did without leaking private content.
- The automation must not create runaway windows/tabs or memory pressure.

What remains:

- Build a permission-aware action policy.
- Separate read-only inspection from state-changing actions.
- Require confirmation for destructive or schoolwork-changing steps.
- Prove cleanup after every app/browser test.

### 8. UI and product trust

Difficulty: `3/5` to `4/5`

Known problem: The main Jarvis app still feels like a debug panel, while the
summon bubble/popout has had visible design bugs. Leo wants the popout to look
excellent and the app to show everything Jarvis says and does.

Why this is hard:

- The app has to be both a consumer product and a debugging/proof surface.
- Action transparency can easily become noisy.
- The popout must be beautiful, compact, non-obtrusive, and robust in fullscreen
  or Stage Manager.
- Liquid Glass design needs real visual testing, not only code changes.

What remains:

- Design a cleaner activity timeline.
- Keep debug details collapsible.
- Make the summon surface polished enough to be the primary interaction.
- Screenshot-test normal, fullscreen, Stage Manager, listening, thinking, and
  speaking states.

### 9. Proof and release discipline

Difficulty: `4/5`

Known problem: Jarvis has often looked better in reports than in Leo's real
tests. Some proof is stale, synthetic, or suppressed. Today, the worker is
offline and the latest verifier/gate artifacts are about 82 hours old.

Why this is hard:

- Real tests can open apps, tabs, and audio; they can disturb Leo's Mac.
- Synthetic tests are safe but can hide real integration failures.
- Overnight runs need time management and cleanup discipline.
- A green unit suite does not mean Jarvis is usable.

What remains:

- Define a release gate that includes fresh live app launch proof.
- Keep synthetic tests, but label them honestly.
- Require selected real app/audio/browser tests before claiming "usable".
- Make the report short and truthful enough that Leo can actually read it.

## Known Bug Areas By Product Surface

### Email

Status: partially usable, but still needs real live checks.

Known bugs/risk:

- Summaries were too verbose.
- URLs and technical details were spoken.
- Email language should be English-first, preserving only necessary Chinese
  names/phrases.
- Ordinal requests like "second email" previously selected the newest email.
- Model routing can still punt a real email request into generic chat unless
  guarded.

### Calendar and RAM/system status

Status: among the more stable surfaces.

Known bugs/risk:

- Calendar cache access depends on permissions and local macOS data format.
- Permission messaging must stay clear: Full Disk Access, Accessibility, and
  Notifications are different.
- These are read-only surfaces and should remain that way unless explicitly
  extended.

### Codex integration

Status: plan-only/confirmation-gated for meaningful actions.

Known bugs/risk:

- Jarvis previously created a new Codex chat instead of continuing the right
  one.
- STT can hear "Codex" as "Kodak".
- Jarvis needs context about available Codex chats.
- Sending prompts into Codex can expose sensitive instructions and should stay
  confirmation-gated.

### Models

Status: not settled.

Known bugs/risk:

- Groq/Llama is useful but cloud/network dependent.
- GPT OSS 120B cloud is promising but not a finished routed product lane.
- Local heavy models can nearly crash a 16 GB Mac.
- Gemma/Qwen/audio-native models remain research-only for speech input.
- The model must know that replies may be spoken.

### Repo/build/release

Status: better than before, but needs fresh verification.

Known bugs/risk:

- Repo root confusion was real; current root is the full `developer/Jarvis`
  folder.
- GitHub Desktop/push state has been confusing historically.
- Alternate/stale app bundles caused confusion.
- Current app bundle is `Jarvis 0.1.501`, but the worker was offline during the
  2026-06-29 status check.

## What Is Probably A Month-Scale Problem

If "usable" means a reliable typed assistant with some safe tools, the remaining
work is probably a few focused weeks.

If "usable" means the actual dream assistant - always listening, clean speech,
safe app/browser control, Teams assignment navigation, Music playback, Codex
handoff, and reliable proof - this is more like a multi-month engineering
project. The hard part is not writing more code. The hard part is making
external reality match what Jarvis says.

The most expensive pieces are:

1. Teams/browser live execution.
2. Full physical audio loop proof.
3. Hey Jarvis long-run reliability.
4. Music ownership through a native Music app.
5. A scalable model/tool router.
6. A safety policy for real computer control.
7. A release gate that catches real integration failures before Leo does.

## Recommended Next Milestones

1. Relaunch Jarvis and rerun fresh `scripts/verify_safe.py`.
2. Rerun `scripts/pre_build_gate.py` from current HEAD.
3. Do one controlled awake-time Teams/browser run with Chrome surface guards on.
4. Make the Teams test either inspect the actual Music assignment or fail with a
   precise reason.
5. Establish a real audio loopback path or pick a reliable physical-audio test
   method.
6. Freeze music playback to one owner: native Music app bridge or the future
   native Music app.
7. Create a "Jarvis usable" release checklist that cannot pass on stale,
   suppressed, or synthetic proof alone.

## Acceptance Criteria For Calling Jarvis Usable

Jarvis should not be called usable until the following all pass on fresh proof:

- Worker launches from the current bundled app.
- Menu-bar Shut Up is visible whenever speech is possible.
- Hey Jarvis can run for a long session without crashing or flickering.
- Physical or equivalent audio loop proves speech input and speech output.
- Music playback starts, is audible through the intended owner, and stops.
- Teams newest Music assignment inspection is either completed or honestly
  blocked with exact cause.
- Email, Calendar, RAM, Magic Keyboard price conversion, model test planning,
  and Codex planning still pass.
- Chrome cleanup shows zero Codex/Jarvis-created tabs/windows left behind.
- No spoken output contains tool calls, backend details, URLs, model internals,
  or debug text unless explicitly requested.

Until then, Jarvis is best described as a promising but brittle local assistant
prototype with strong safety/test scaffolding and several unresolved
product-critical blockers.
