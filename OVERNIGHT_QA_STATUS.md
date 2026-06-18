# Jarvis Overnight QA Status

Started: 2026-06-18 22:26 CST

Goal: build and use a full-loop pre-build regression system for Jarvis. Each
important test should synthesize a spoken command, route it through Jarvis,
verify the real external action, inspect the visible reply, audit/transcribe the
spoken reply, time every stage, and clean up any app/browser state it created.

## Current Task Stack

- Top-level goal: Jarvis passes Leo-style real-world tests before a build.
- Current branch: full-loop QA harness plus canonical Jarvis prompt coverage.
- Immediate subtask: expand the full-loop matrix across Leo's overnight prompt
  list while keeping every external action verified and cleaned up.
- Why this matters: recent bugs were false successes, hidden playback, stale UI
  claims, STT mishearings, silent tool sends, and weak cleanup.
- Done proof for current subtask:
  - A script can generate a spoken-command audio artifact.
  - The script can send the command to Jarvis.
  - The script can verify external proofs for Music, RAM, Calendar, commerce,
    model-test planning, and Codex Default-chat routing.
  - The script can stop playback and close/minimize the Music window after any
    Music test.
  - The script writes JSON/Markdown evidence with timings and any failure.
- Return point: expand the same full-loop harness to Teams and email-contact
  prompts, then tighten visible/spoken reply comparison.

## Rules For Tonight

- Read `JARVIS_BUG_BACKLOG.md` before choosing the next test.
- Log every discovered bug here and add a dedicated regression check for it.
- Do not use hidden music playback as proof.
- Do not leave Chrome tabs or Music windows open from tests.
- Keep edits inside Git repositories.
- Commit only after a meaningful test pass proves the current version is worth
  saving.
- Do not call a task finished unless real external state was verified.

## Bugs Found Tonight

- 2026-06-18 22:27 CST - Music App bridge false match:
  `play/search "Waving Through a Window"` selected and played
  `Through The Fire And Flames` by DragonForce. This is a false-success bug:
  the bridge can prove playback, but it proved the wrong song. Dedicated test
  needed before fix: Music App bridge search/play must either resolve the Dear
  Evan Hansen/Tony Awards alias for Waving Through a Window or fail safely
  instead of choosing a different "through" song.
- 2026-06-19 00:01 CST - Teams assignment false success:
  Jarvis read the visible Teams screen, but the visible assignment was
  `Lesson 2: The Geography of Greece Group Assignment` while the command asked
  for the newest Music assignment. Dedicated fix: subject-aware Teams summaries
  must refuse a wrong-subject assignment instead of asking follow-up questions
  as if it found the Music task.

## Tests Added Tonight

- Music App bridge contract now includes `waving-through-window-alias`, proving
  the top result is `Dear Evan Hansen | 2017 Tony Awards`, includes an alias
  match field, and does not include `Through The Fire And Flames` in the top
  three results.
- Jarvis safety tests now prove `localos_music_play` prefers a confirmed native
  Music app bridge playback result, disables the live bridge when test paths are
  patched, and sends Stop Music through the Music app bridge.
- `scripts/full_loop_regression.py` now runs a real-action Music case: synthesize
  "Hey Jarvis, play Waving Through a Window", route it through Jarvis, verify
  native Music reports real playback of the Dear Evan Hansen Tony Awards track,
  audit the Jarvis speech payload, then stop playback and close the Music window.
- `scripts/full_loop_regression.py` now also covers Activity Monitor-style RAM,
  Calendar today, Magic Keyboard price-to-yuan, Gemma 3 4B remote-first model
  planning, and Codex Default-chat planning without sending.
- Jarvis planner tests now cover common STT mishearings where Codex becomes
  "Cortex" or "Kodak"; those still route to the Codex chat plan and still require
  typed confirmation before any send.
- Teams visible-screen tests now reject wrong-subject assignment reads: a Music
  assignment request cannot pass against a Geography assignment page.

## Cleanup Obligations

- Stop Music App playback after any music test.
- Close or minimize the Music App window after any music test.
- Close Chrome tabs opened by Jarvis/Codex tests.
- Verify no hidden `afplay` or stray `/usr/bin/say` process is left behind.

## Latest Checkpoint

- 2026-06-18 22:26 CST: created this tracker after reading the bug backlog and
  confirming Jarvis and Music App are both Git repositories.
- 2026-06-18 22:47 CST: Music App bridge contract passed after adding the alias
  fix.
- 2026-06-18 22:48 CST: launched Jarvis 0.1.454 build 454 from bundled app
  resources.
- 2026-06-18 22:52 CST: full-loop real-action Music regression passed in 16.835s
  at `runtime/full_loop_regression/20260618-225159/summary.json`; it selected
  `Dear Evan Hansen | 2017 Tony Awards`, confirmed Music playback, stopped it,
  and closed the Music window.
- 2026-06-18 23:13 CST: combined full-loop regression passed 2/2 at
  `runtime/full_loop_regression/20260618-231308/summary.json`, covering native
  Music playback plus Activity Monitor-style RAM usage. Full Python safety suite
  then passed 837/837.
- 2026-06-18 23:24 CST: combined full-loop regression passed 3/3 at
  `runtime/full_loop_regression/20260618-232344/summary.json`, adding read-only
  Calendar schedule proof. Full Python safety suite then passed 839/839.
- 2026-06-18 23:33 CST: combined full-loop regression passed 4/4 at
  `runtime/full_loop_regression/20260618-233216/summary.json`, adding the Magic
  Keyboard official-price-to-yuan public web case. Full Python safety suite then
  passed 841/841.
- 2026-06-18 23:39 CST: combined full-loop regression passed 5/5 at
  `runtime/full_loop_regression/20260618-233912/summary.json`, adding the Gemma
  3 4B model-test planning case with a remote-first/no-local-model-run guardrail.
  Full Python safety suite then passed 843/843.
- 2026-06-18 23:55 CST: focused Codex Default-chat full-loop regression passed at
  `runtime/full_loop_regression/20260618-235441/summary.json`, proving Jarvis can
  plan the Default Codex chat route without silently sending the prompt.
- 2026-06-18 23:56 CST: combined full-loop regression passed 6/6 at
  `runtime/full_loop_regression/20260618-235500/summary.json`, covering native
  Music playback, RAM, Calendar, Magic Keyboard yuan conversion, Gemma 3 4B model
  planning, and Codex Default-chat safety planning. Full Python safety suite then
  passed 846/846.
- 2026-06-19 00:13 CST: focused Teams assignment honesty regression passed at
  `runtime/full_loop_regression/20260619-001315/summary.json`, after a live
  probe exposed that wrong-page Chrome OCR could still look like a completed
  Teams read.
- 2026-06-19 00:22 CST: combined full-loop regression passed 7/7 at
  `runtime/full_loop_regression/20260619-002159/summary.json`, adding Teams
  assignment honesty to Music playback, RAM, Calendar, Magic Keyboard yuan
  conversion, Gemma 3 4B planning, and Codex Default-chat safety planning. Full
  Python safety suite then passed 850/850.
