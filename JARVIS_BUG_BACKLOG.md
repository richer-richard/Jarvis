# Jarvis Bug Backlog From Leo's Chat Reports

Generated: 2026-06-18 20:25 CST

Purpose: this is Codex's working bug memory for Jarvis. It is not a polished user
report. Read this before major Jarvis work so the same bug classes do not come
back under a new name.

Status legend:

- Fixed/proved: a patch and some proof were reported in the thread.
- Partially fixed/risky: there is a patch, but Leo or the proof surface still
  showed real-world caveats.
- Open/unknown: Leo identified the problem, and no durable proof in this chat
  guarantees it is gone.

## Highest Priority Bug Classes

1. Partially fixed/proved: Jarvis should not leave stale "Still working" rows
   after a task has completed.
   - Examples: music "playing" while LocalOS did not actually start audio;
     Outlook opened but UI still said Still working; Teams opened but Jarvis had
     not inspected the assignment.
   - 2026-06-19 proof update: Swift progress nudges are tied to an active turn
     ID, removed before final answer display and in the defer cleanup path, and
     excluded from future model history. Regression tests cover the stale row
     lifecycle.
   - 2026-06-19 proof update: native Outlook/screen status rows and streaming
     status rows are now assigned to the replaceable answer placeholder instead
     of being appended as permanent "Working" rows. Regression tests guard the
     placeholder assignment.
   - Remaining task-honesty subcases still need app-side state confirmation and
     stay tracked in their own music/Teams/tool sections below.

2. Partially fixed/risky: Jarvis music playback ownership has been confused.
   - Leo wants LocalOS to own all normal music playback.
   - Jarvis must not start hidden `afplay`, hidden browser audio, mystery audio,
     or another playback source that the media keys cannot pause.
   - Stop Music should be an emergency brake from the Jarvis menu bar.
   - 2026-06-19 proof update: the full-loop music case now uses the native Music
     app bridge as the proven playback owner and fails if cleanup does not verify
     playback stopped. Broader product risk remains for ad-hoc music commands and
     legacy LocalOS/Chrome fallback paths.
   - 2026-06-19 proof update: `localos.music_play` now exposes
     `preferred_playback_owner`, `native_music_bridge_enabled`, and
     `legacy_localos_fallback_allowed`; when the native bridge is active and does
     not confirm playback, the result is `played_by=none` and explicitly refuses
     legacy LocalOS/Chrome/hidden-player fallback.
   - 2026-06-19 proof update: the tool registry now marks music playback
     available when the native Music bridge app exists, even if no LocalOS
     snapshot has been written yet, so Jarvis does not hide the preferred music
     tool behind stale LocalOS state.

3. Partially fixed/risky: Jarvis speech/mute can become unsafe or annoying.
   - Leo reported Jarvis speaking when it should not, being impossible to mute,
     disappearing from the menu bar while talking, only saying "hello", reading
     internal/debug/model text aloud, or stopping speech after a few seconds.
   - Rule: if Jarvis can make sound, the menu-bar Shut Up control must be visible
     and working.
   - 2026-06-19 proof update: the status helper remains the normal single menu
     head, but the main app now creates a fallback emergency status item if the
     helper executable is missing or fails to launch; the fallback is removed
     again when the helper starts successfully to avoid duplicate heads.

4. Open/unknown: full speech-in/action-out/speech-back loop is not yet proved
   across Leo's real target prompts.
   - Leo wants Codex to feed audio into Jarvis, verify the action happened, and
     transcribe Jarvis's audio back to compare with the visible reply.
   - Existing harnesses help, but real app/browser/Teams/music proof remains
     uneven.
   - 2026-06-19 proof update: voice-loop QA now scores live speech against the
     exact spoken payload when visible and spoken text intentionally differ, and
     a live Calendar speech check passed with `reply_similarity_target:
     spoken_payload`. This improves the harness, but the broader real-world
     prompt set is still not fully proven with physical speaker/microphone
     capture.
   - 2026-06-19 proof update: the pre-build gate now publishes an explicit
     speech proof contract. Quiet default runs are labeled
     `suppressed_for_probe`; opt-in live playback runs are labeled
     `live_playback_exercised`; `--require-live-speech` fails closed if live
     playback proof is required but not enabled.
   - 2026-06-19 proof update: `scripts/full_loop_regression.py --case all`
     passed `8/8` in 130.873s with zero warnings and every latency budget
     passing. Covered Music playback, RAM/Activity Monitor, Calendar, Magic
     Keyboard yuan conversion, Gemma model plan, Codex Default routing, Teams
     assignment honesty, and Ms. Sharpay email summary.
   - 2026-06-19 proof update: `scripts/pre_build_gate.py --skip-python-tests`
     passed `3/3` in 128.093s, including full-loop regression, Chrome cleanup,
     and report refresh. The summary explicitly records
     `speech_mode: suppressed_for_probe` and no physical speaker/microphone
     capture.

5. Partially fixed/risky: Jarvis must use model/tool choice, not fake keyword
   hacks, except where Leo explicitly allows a primitive tool.
   - Leo objected strongly to email/music behavior that smelled like keyword
     shortcuts pretending to be intelligence.
   - Exception granted later: a primitive `play ...` music lookup tool is allowed
     for direct song playback.
   - 2026-06-19 proof update: first-model prompt now explicitly rejects
     keyword-only routing and requires intent/history/tool-description based
     selection; direct named music playback previews label themselves as the
     user-approved `direct_music_play` primitive exception.
   - 2026-06-19 proof update: executed direct music playback results now carry
     a visible `routing.source: user_approved_primitive_exception` audit block,
     while model-selected music playback is labeled `model_tool_call`.

## Email And Summarization Bugs

1. Fixed/proved at least once: email summaries were too verbose and read raw
   links or technical details.
   - Leo wanted simple spoken summaries such as: "there's a link from 少先队 that
     may need you to fill out."
   - URLs should not be read aloud unless specifically useful.

2. Fixed/proved at least once: email summary language should be English-first.
   - Chinese names or essential phrases such as 少先队 / 慈善义卖 may remain, but
     the explanation should be in English.

3. Partially fixed/risky: Jarvis initially did not actually read/summarize email
   reliably.
   - Leo said pulling newest emails worked; the model was not reading and
     summarizing them correctly.
   - Desired behavior: check unread emails; if none unread, summarize the newest
     email. Usually latest 5 is enough.
   - 2026-06-19 proof update: normal structured email checks now default to
     scanning the latest 5 messages, while explicit sender/date requests use a
     wider but bounded 25-message scan and explicit overrides remain bounded.
   - 2026-06-19 proof update: explicit ordinal requests such as "second email"
     now stay ordinal across Apple Mail, Outlook AppleScript, and SQLite
     fallback routes. Outlook and SQLite request recent messages before applying
     `index:2`, so Jarvis does not summarize the newest email when Leo asks for
     the second newest.

4. Partially fixed/risky: Jarvis must first say a natural working line, then
   return with the summary.
   - Good: "Sure. Let me check your email..."
   - Bad: "Let me identify the task", "finding email skill", or exposing "skill".
   - 2026-06-19 proof update: fast-chat tool requests now naturalize
     model-provided status text before it can be shown or spoken. Bad lines such
     as "Finding the email skill" or "Let me identify the task" are replaced
     with tool-specific natural lines like "Checking your email now."

5. Fixed/proved at least once: no-result email replies should not say scan-count
   internals aloud.
   - Bad: "I checked Apple Mail, scanned 250 recent messages..."
   - Good: a concise result or a contact clarification.

6. Fixed/proved: contacts from email need memory.
   - Example: "Ms. Sharpay" may be a nickname/phonetic label; Jarvis should infer
     the real sender name from local mail metadata and remember the alias.
   - 2026-06-19 proof update: contact alias memory is stored locally in
     `runtime/memory/contact_aliases.json`; email-based inference explicitly
     reports `read_private_metadata=true` and `read_email_content=false`.

7. Fixed/proved: bounded date/sender email searches need real proof.
   - Example target prompt: "Summarize all the emails from Ms. Sharpay in the
     past month."
   - 2026-06-19 proof update: this prompt now resolves `Ms. Sharpay` to
     `Sharpay Cao 曹宗悦`, preserves the "all emails" intent as `all_matching`,
     selects `sender_recent`, verifies 12 matching messages with 5 summarized
     recent messages, and passes the live full-loop email case.

## Model Routing And Prompting Bugs

1. Fixed/proved at least once: Jarvis had no chat context.
   - Leo asked for a math problem, answered it, and Jarvis forgot the previous
     problem.
   - Jarvis should feed relevant previous conversation, user prompt, date/time,
     and dictation context to the model.

2. Fixed/proved at least once: Jarvis wasted time saying "let me think" when no
   tool was needed.
   - Rule: only go into tool-search/working mode if a skill/tool is actually
     needed.

3. Fixed/proved at least once: the first model/tool system must know what it can
   call.
   - Leo proposed model-visible tool definitions with speech-safe text plus a
     hidden call.
   - Tool calls must be stripped from visible/spoken output wherever they appear.

4. Partially fixed/risky: model outputs must be clean for speech.
   - The model should know its reply may be spoken.
   - It should avoid URLs, backend details, long diagnostics, and non-English
     explanations unless needed.
   - 2026-06-19 proof update: automatic speech now strips inline backend/model
     timing fragments and leaked JSON/tool entities before TTS, and server
     speech selection passes the sanitized payload rather than the original
     reply text.
   - 2026-06-19 proof update: the visible reply sanitizer now also removes
     markdown/raw URLs and email addresses from app-visible reply fields before
     they reach the Jarvis window or Copy Chat JSON.

5. Partially fixed/risky: cloud/local model routing is still a product risk.
   - Candidate lanes mentioned: Groq Llama 70B, GPT OSS 120B cloud, GPT OSS 20B,
     Gemma 3/4 variants, Qwen models, Ollama fallback.
   - Leo wants cloud where possible to avoid RAM/GPU pressure on his 16 GB Mac.

6. Fixed/proved at least once: offline fallback model policy has a safe
   product contract.
   - Desired: not too stupid, not too slow, not RAM/GPU heavy. Gemma 3n/e4b or
     similar was investigated but not settled as a finished product lane.
   - 2026-06-19 proof update: `models.test_plan` now returns a plan-only
     offline fallback policy that stays cloud/remote-first, recommends
     `gemma3n:e4b` as the default lightweight local candidate, allows Qwen 0.6B
     only as a tiny simple fallback, blocks heavy local candidates such as
     `gpt-oss:20b`/DeepSeek-class models, and requires user confirmation before
     any local run.
   - 2026-06-19 proof update: focused regressions cover remote MacBook Air
     preference for heavy models, ask-before-local when the remote is
     unavailable, Tailscale-stopped wording, and Qwen 0.6B being treated as a
     tiny fallback rather than the smarter middle lane. This does not prove live
     model quality; it proves Jarvis will not burn Leo's Mac by silently loading
     a heavy local model.
   - 2026-06-19 proof update: the middle-model comparison script now has a
     second heavy-local latch. Passing `--allow-local-heavy` alone is not enough
     to run `gpt-oss:20b`; the script also requires an explicit
     `JARVIS_ALLOW_HEAVY_LOCAL_MODELS` unlock value, and the report records both
     requested and effective heavy-local state.

7. Open/unknown: GPT OSS 120B low-thinking plus browser/tool access is still a
   future capability, not a proved product.

## Speech, TTS, STT, And Wake Bugs

1. Partially fixed/risky: chosen voices sounded unnatural or slow.
   - Edge Andrew was best natural audition but online/Microsoft-dependent.
   - Piper Ryan high American male was chosen temporarily but had quality issues.
   - macOS `say` sounded better to Leo than the app's speech path for the same
     sentence.

2. Partially fixed/risky: Piper playback had huge pauses, skipped phrases,
   repeated phrases, and sometimes stopped after 3-5 seconds.
   - Any future Piper use needs exact audio loopback tests.

3. Fixed/proved at least once: Jarvis spoke only the working line ("Yes sir...")
   and did not speak the final answer.

4. Fixed/proved at least once: Jarvis visible text and spoken text diverged.
   - Example: visible reply was longer, audio only said "Hello".
   - Required proof: compare TTS/STT transcript with visible final reply.

5. Fixed/proved: Jarvis can speak internal tool/model/debug data.
   - Leo heard model names/technical stuff.
   - Speech firewall must strip Tool time, Fast model time, Groq/Ollama/backend
     rows, worker/audit/verification lines, hidden calls, and links unless needed.
   - 2026-06-19 proof update: the TTS sanitizer drops backend/model timing,
     hidden tool calls, Worker/Audit/Verification/App perms/Codex Activity/CLI
     status rows, and debug-only replies fail quiet as `empty_after_sanitization`.
     Voice-loop QA now flags those internal status phrases if they appear in
     spoken transcripts.

6. Fixed/proved at least once: "Shut Up" did not actually mute, and later
   "Keep Blabbering" did not restore speech.

7. Fixed/proved at least once: Jarvis kept talking after Leo pressed Shut Up.
   - 2026-06-19 proof update: both the helper-owned menu-bar Shut Up action and
     the main-window mute action now send `stop talking` before setting the mute
     flag, so current audio is interrupted instead of only preventing future
     speech.

8. Fixed/proved at least once: Jarvis was talking while not in the menu bar, so
   Leo could not shut it up.

9. Partially fixed/risky: menu-bar head must remain present whenever speech can
   happen.
   - It should be the colored Jarvis head, not text, not a test "T", not
     duplicated, not displaced, and not a floating overlay that cannot be
     Command-dragged.
   - 2026-06-19 proof update: status-helper and disabled main-app status item
     no longer fall back to text glyphs when the icon image is missing; the
     helper self-test now fails if a text fallback returns, focused Python
     source checks pass, and `jarvis-status-helper --self-test` builds/runs.
   - 2026-06-19 proof update: Swift speech-activity tracking now treats
     backend `suppressed_by_request` and `deferred_to_follow_up` speech payloads
     as non-speaking states, so muted/suppressed/deferred responses cannot
     falsely extend Jarvis's active speech window.
   - 2026-06-19 proof update: native status-speech and streaming-command paths
     now reassert the status-helper before possible audio starts, so the menu
     bar emergency controls are restarted before Jarvis can blabber.
   - 2026-06-19 proof update: the main app now terminates stale duplicate
     Jarvis app/status-helper processes at launch, so older `Jarvis LocalOS
     Only`/alternate-bundle helpers cannot leave a second colored head or
     emergency menu alive beside the canonical app. The Swift self-test covers
     keeping the current canonical process while targeting only stale duplicate
     Jarvis app/helper processes.
   - 2026-06-19 proof update: `scripts/morning_status.py` now reports both
     `jarvis-menu-bar` and `jarvis-status-helper` processes and checks
     `/api/speech/mute`. If speech is unmuted/available while no emergency menu
     process exists, it prints `Speech emergency: missing menu helper while
     speech is unmuted` and points to `scripts/open_jarvis.sh`.

10. Partially fixed/risky: Hey Jarvis crashed or flickered.
    - Leo reported crashes after Start Hey Jarvis.
    - Later build flickered badly in the menu bar.
    - It also said "Yes sir" after wake, then dictation/menu-bar flickered and
      stopped hearing him.
    - 2026-06-19 proof update: final/error recognition callbacks now stop the
      current audio engine and recognition task before waiting to restart, so
      old Apple Speech sessions are not left active during the restart delay.
      Focused source-contract tests and the Swift menu-bar self-test cover this
      restart-churn guard. Remaining risk: live macOS Speech behavior still
      needs longer real microphone soak testing.

11. Partially fixed/proved: Hey Jarvis should always listen after Start Hey
    Jarvis until Leo stops it.
    - It should not require repeatedly starting/listening.
    - 2026-06-19 proof update: the wake listener keeps `shouldKeepRunning` true
      after Start, schedules recovery restarts after silent recognizer endings,
      restarts after captured commands with `postCommandRestartDelaySeconds`, and
      gates restart tasks on `self.shouldKeepRunning` so Stop Hey Jarvis remains
      the explicit off switch. Regression coverage checks restart storms,
      silent endings, post-command restart delay, and source-level restart paths.
    - Remaining risk: live macOS Speech/AVAudioEngine availability can still
      interrupt listening if permissions or the speech service fail.

12. Partially fixed/risky: wake acknowledgement should usually be quiet.
    - Leo decided not to say "Yes Sir" after wake because he will start speaking
      right after "Hey Jarvis".
    - 2026-06-19 proof update: text-only voice-loop tool descriptions and wake
      debug next steps now say visual acknowledgement / wake acknowledgement
      echo instead of implying Jarvis normally speaks its own greeting.

13. Partially fixed/proved: STT punctuation is poor.
    - All tested STT options heard words but missed punctuation.
    - Decision: do not add a slow punctuation layer; tell Llama/GPT OSS that
      incoming text may be dictation without punctuation.
    - 2026-06-19 proof update: the real fast-chat system prompt and middle
      planner prompt both tell the model that Leo's latest message may be raw
      speech dictation with missing punctuation/capitalization/homophones and
      to infer intended wording without adding meaning. `diagnostics.model_context`
      exposes this policy, and tests assert it for the actual model messages.

14. Partially fixed/proved: detect when Leo starts speaking and stop current
    Jarvis speech.
    - Not permanent Shut Up; just interrupt current reading because an answer is
      expected.
    - 2026-06-19 proof update: wake-listener transcript snapshots feed
      `handleSpeechBargeInIfNeeded`, which stops active speech through
      `client.stopSpeaking()` when the transcript looks like Leo intentionally
      interrupting. Self-tests cover the positive interruption case and false
      positives from tiny fragments, Jarvis speech echo, and captured wake
      command echo.
    - Remaining risk: this depends on Hey Jarvis/wake listening being active and
      macOS speech recognition hearing the interruption.

15. Open/unknown: Gemma/Qwen/audio-native model direct speech understanding was
    investigated but not converted into a final Jarvis STT path.
    - 2026-06-19 proof update: `models.test_plan` now exposes
      `offline_fallback.audio_input_status` with `status: research_only` and
      `final_stt_path: false`, plus explicit requirements for bounded audio
      probes, latency/resource comparison, and full-loop tests before any
      audio-native model can become part of live Jarvis dictation.

## App UX, Windowing, And Overlay Bugs

1. Fixed/proved at least once: Jarvis behaved like a weird persistent overlay
   instead of a normal macOS app.
   - Leo wanted it in the Dock, normal window open on icon click, not always in
     his face, and usable with Stage Manager.

2. Fixed/proved at least once: Cmd-W did not close the Jarvis window.

3. Fixed/proved at least once: duplicate apps appeared.
   - There was both `Jarvis` and `Jarvis LocalOS Only`; Leo only wants normal
     `Jarvis`.
   - Duplicate Jarvis heads/icons in menu bar and Dock are unacceptable.

4. Partially fixed/risky: Jarvis summon bubble/liquid-glass overlay needed major
   visual correction.
   - Reported bugs: weird block around it, too big, not liquid glass, weird white
     line near bottom right, big hunk in fullscreen, taking space over content.
   - Desired: beautiful compact top-right liquid-glass blob, transcribes, spins,
     shows answer, stays 5 seconds after Leo or Jarvis speaks, visual wave based
     on audio.

5. Open/unknown: app/debug UI can look rough, but the popout must be polished.

6. Partially fixed/risky: workboard/report paths were sometimes not provided,
   or reports were late/stale.

7. Partially fixed/risky: time management failed.
   - Leo explicitly called out missing the overnight deadline.
   - Future overnight work must check time repeatedly and prepare the report by
     the promised time, not after.

## LocalOS Music Bugs

1. Partially fixed/risky: Jarvis could not find songs beyond the first library
   item.

2. Partially fixed/risky: Jarvis searched keywords itself instead of listing
   Your Pick songs and letting the model/tool choose.
   - Leo later allowed a primitive direct song lookup for "play X" commands.

3. Partially fixed/risky: "Waving Through a Window" was not found or mapped
   confusingly to a broader Dear Evan Hansen/Tony Awards file.
   - Jarvis must be honest about closest matches.

4. Fixed/proved for the preferred native Music path: Jarvis said LocalOS was not
   connected instead of automatically opening/connecting LocalOS.
   - Leo expects Jarvis to recover automatically when safe.
   - 2026-06-19 proof update: normal music playback now prefers the native Music
     app bridge. If the bridge is down, Jarvis opens `Music.app`, waits for
     `/health`, retries the play request, and confirms playback before claiming
     success. A second regression covers the case where the bridge is alive but
     the control token is missing until Music.app opens.
   - Remaining risk: older LocalOS/Chrome fallback lanes can still require a
     real click or Chrome Automation permission; those stay tracked in rows 5
     and 6.

5. Partially fixed/risky: LocalOS opened and selected a song but did not play.
   - Browser autoplay/user-gesture rule caused "play() failed because the user
     didn't interact with the document first."
   - 2026-06-19 proof update: native Music bridge failures now preserve exact
     playback confirmation such as `wrong_track_playing` instead of flattening
     everything into generic not-playing; results include `permission_issue`,
     `next_steps`, and `spoken_summary` while still refusing hidden fallback
     audio.
   - 2026-06-19 proof update: when the native Music bridge selects the requested
     song but `/playback-state` reports it is paused, Jarvis now calls the
     bridge `/resume` endpoint, waits briefly, and only claims success if the
     refreshed playback state confirms the requested song is playing.

6. Partially fixed/risky: Chrome/LocalOS refused connection or JavaScript
   control.
   - Jarvis should report this honestly and guide the right permission/action.
   - 2026-06-19 proof update: LocalOS music `not_queued` bridge failures now
     include structured `permission_issue`, `requires_user_action`,
     `next_steps`, and `spoken_summary` fields for Chrome Automation denial,
     LocalOS bridge not polling, and LocalOS player unavailable states. Focused
     regressions cover each branch.

7. Fixed/proved at least once: hidden playback via native fallback was removed.
   - Jarvis must not use hidden `afplay` as normal music playback.

8. Partially fixed/risky: mystery audio kept playing after Jarvis quit or tabs
   closed.
   - Future music tests must inventory active media owners.
   - 2026-06-19 proof update: the Music full-loop case now snapshots `afplay`
     before and after playback cleanup and fails if a new hidden `afplay`
     process survives. Live focused proof at
     `runtime/full_loop_regression/20260619-034949/summary.json` passed with
     `new_afplay_processes_after: []`.
   - 2026-06-19 proof update: live `scripts/full_loop_regression.py --case
     music` passed in 10.505s, selected `Dear Evan Hansen | 2017 Tony Awards`,
     verified the native Music bridge reported playing, stopped playback, closed
     the Music window, and left `new_afplay_processes_after: []`.
   - 2026-06-19 proof update: after tightening hidden `afplay` detection, a
     second live Music proof at
     `runtime/full_loop_regression/20260619-222618/summary.json` passed in
     11.942s with `afplay_processes_after: []`,
     `new_afplay_processes_after: []`, and `verified_stopped: true`.
   - 2026-06-19 proof update: hidden `afplay` process detection now checks the
     executable name, so the Piper worker's `--afplay /usr/bin/afplay` argument
     is not misreported as hidden playback while real `/usr/bin/afplay ...`
     processes still fail the Music cleanup proof.

9. Fixed/proved: Stop Music from the menu bar should stop Jarvis-started music
   and leave visible evidence in Jarvis.
   - 2026-06-19 proof update: both the helper-owned menu-bar head and the main
     app expose Stop Music. The helper sends the backend stop command and posts
     a main-app notification so the visible Jarvis window records the result.
     The backend stop path stops the native Music bridge, old LocalOS/browser
     lanes, system media sources, and tracked old `afplay` leftovers without
     muting system output as a normal stop action.

10. Open/unknown: final solution should likely be a separate native Music app.
    - Swift/SwiftUI, Apple Music-like, MP3 folder alias, YouTube audio import,
      smart picker, metadata/source URL, and Jarvis tools for search/play/import.

## Browser, Chrome, Teams, And Computer Control Bugs

1. Partially fixed/risky: Jarvis needs browser access that uses Leo's logged-in
   Chrome sessions.
   - Copying/migrating cookies into an in-app browser is not the preferred path.
   - Visible Chrome handoff or embedded controllable browser needs clear design.

2. Partially fixed/risky: Jarvis/Chrome control can be blocked by macOS
   Automation or Chrome "Allow JavaScript from Apple Events".

3. Fixed/proved: if Jarvis opens a browser, Leo can see and interact with it in
   the Jarvis app window for ordinary WebKit-safe pages.
   - The Swift app includes `JarvisBrowserPanelView` with a `WKWebView`, address
     field, back/forward/reload controls, a Go action, status text, loading
     indicator, Hide Browser, and an Open Chrome / Open Signed-In Chrome button.
   - Authenticated pages still use signed-in Chrome for the real login session;
     the Jarvis panel remains the visible control/status surface and does not
     copy Chrome cookies or sessions.
   - Regression tests cover `browser.status`, ordinary URL WebKit lane,
     authenticated Chrome handoff, and the Swift browser-panel/Chrome-handoff
     source contract.

4. Fixed/proved: Chrome bookmarks import exists for Jarvis browser/task routing.
   - Jarvis has local tools `browser.bookmarks_import`,
     `browser.bookmarks_search`, and `browser.bookmark_open`.
   - The imported snapshot currently exists at
     `runtime/integrations/chrome_bookmarks.json` with 23 links from 3 Chrome
     profiles.
   - Regression tests prove import/search/open-plan behavior is local,
     bookmark-opening is planned-only, Teams/authenticated links choose the
     signed-in Chrome lane, and Chrome cookies/session state are not migrated
     into WebKit.

5. Open/unknown: Teams assignment target prompt remains a high bar.
   - "Look in Teams for my newest Music assignment and ask me a list of
     questions..."
   - Must verify it actually inspected the newest assignment, not just opened
     Teams.
   - 2026-06-19 live probe found a concrete false success: Jarvis read visible
     Teams assignment text, but it was `Lesson 2: The Geography of Greece Group
     Assignment` while Leo asked for the newest Music assignment. Jarvis must
     either navigate to Music or say the visible assignment does not match Music.
   - 2026-06-19 proof update: the full-loop Teams case now tries native
     visible-screen OCR once even when Chrome page text is blocked by
     Automation permission, preserves `assignment_subject_mismatch`, and proved
     live that the visible page is `Lesson 2: The Geography of Greece Group
     Assignment`, not the requested Music assignment.

6. Partially fixed/risky: Jarvis should not open random extra Chrome tabs during
   tests and leave them for Leo.
   - Future overnight runs must close Codex/Jarvis-created tabs before morning.
   - 2026-06-19 proof update: Chrome cleanup now targets Jarvis/Codex-created
     local report, workboard, wake-audition, and old LocalOS music-player tabs,
     while preserving personal YouTube/new-tab/other-localhost pages. Focused
     tests cover target selection and dry-run/execute AppleScript behavior.

7. Open/unknown: in full-screen apps, the overlay/browser behavior can take too
   much visible space.

## Calendar, System, And App-Control Bugs

1. Partially fixed/risky: Calendar access was blocked or unclear until Full Disk
   Access/Calendar cache handling improved.
   - Need clear permission language: Full Disk Access vs Accessibility vs
     Notifications.

2. Fixed/proved: "Check my calendar for my schedule today" has live spoken
   proof.
   - 2026-06-19 proof update: official gate
     `runtime/pre_build_gate/20260619-171659/summary.json` passed the
     `calendar_today_schedule` full-loop case in 13.223s. The action proof used
     the local Calendar SQLite cache, found 1 event, and reported
     `changed_calendar=false`.

3. Fixed/proved: "Check Activity Monitor how much RAM my computer is using."
   uses reliable system diagnostics and speaks a concise result.
   - 2026-06-19 proof update: official gate
     `runtime/pre_build_gate/20260619-171659/summary.json` passed the
     `ram_activity_monitor` full-loop case in 10.985s with normal memory
     pressure and no app-opening requirement.

4. Fixed/proved: "Test the Gemma 3 4B model for me."
   - Jarvis should understand this may be heavy and prefer offloading to the
     MacBook Air via SSH/Tailscale before using Leo's 16 GB machine.
   - 2026-06-19 proof update: official gate
     `runtime/pre_build_gate/20260619-171659/summary.json` passed the
     `gemma_model_plan` full-loop case in 27.462s. The action proof preserved
     `Gemma 3 4B`, did not run a model locally, changed no system state, and
     selected `ask_before_local` because the MacBook Air was unreachable.

5. Partially fixed/risky: Accessibility permission is required for computer
   control, but Jarvis must explain exactly why and what it enables.
   - 2026-06-19 proof update: native and backend permission surfaces now explain
     that Accessibility is only for controlled clicking, typing, and app
     navigation; normal chat, email summaries, calendar reads, and status checks
     do not need it. Focused permissions tests and SwiftPM build passed.

6. Fixed/proved: Notifications permission has not been requested by the app but
   is mentioned in readiness. It should be optional unless timers/background
   alerts need it.
   - 2026-06-19 proof update: the native permission summary already counted only
     blocking rows, and now the detailed `Missing:` line also filters to
     `!isReady && isBlocking`, so optional Notifications stay visible without
     being listed as a required missing permission.

## Codex Integration Bugs

1. Fixed/proved at least once: Codex continuation mishandled Leo's secret code.
   - Jarvis created a new chat instead of continuing the current chat with the
     code/prompt.

2. Partially fixed/risky: Jarvis should choose a Codex chat, type into it, and
   label prompts as Jarvis-generated.
   - Default chat ID was provided historically, but IDs must be treated as
     internal context, not spoken aloud.

3. Open/unknown: Jarvis should know context about Codex chats and choose a target
   chat intelligently, probably using a smarter middle model.

4. Partially fixed/risky: Codex CLI was slow; proxy hypotheses via ClashX were
   tested/should be kept in mind.

5. Partially fixed/proved: "Open Codex and send a prompt called test in the
   Default chat" remains a hard target prompt, especially because STT may hear
   Codex as Kodak.
   - 2026-06-19 proof update: the route plans `codex.chat_plan` with typed
     confirmation required, extracts the prepared prompt text `test`, selects
     the requested chat including `in the Music chat` style phrasing, includes a
     Jarvis-generated prompt preview with the marker and original request tail,
     hides session IDs, and still does not send or start Codex without approval.

## Git, Repo, Build, And Release Bugs

1. Partially fixed/risky: repo root confusion.
   - Leo intended the whole Jarvis folder to be the Git repo, not a small
     subfolder.

2. Partially fixed/risky: GitHub Desktop push/fetch loop.
   - GitHub Desktop claimed newer commits on remote; Fetch did not resolve it.
   - 2026-06-19 proof update: current CLI state on
     `codex/jarvis-overnight-20260608` reports `ahead 126, behind 0`; remote
     ref `origin/codex/jarvis-overnight-20260608` is older than local HEAD, and
     `git fetch --dry-run origin codex/jarvis-overnight-20260608` reported no
     incoming updates. No push was attempted.

3. Fixed/proved at least once: dirty/untracked files are now visible to Jarvis
   before release or GitHub troubleshooting.
   - Commits should still be scoped and safe, and unrelated user changes must
     not be reverted.
   - 2026-06-19 proof update: `diagnostics.git` now includes a read-only
     `worktree` section with `clean`, dirty/modified/untracked counts, a
     bounded `git status --short` preview, and reply text that says whether the
     worktree is clean. Regression tests cover both clean unrelated-remote
     diagnostics and a dirty worktree with one modified plus one untracked file.

4. Fixed/proved at least once: app version must be visible in the app, e.g.
   "Jarvis 0.1.xxx".

5. Fixed/proved at least once: final user-facing replies should end with the
   Jarvis version number.

6. Partially fixed/risky: build output sometimes created alternate bundles or
   stale worker/runtime resources. Health must prove the live app is running
   bundled current resources.
   - 2026-06-19 proof update: the real `output/` build now refuses accidental
     non-canonical app names/bundle IDs and numbered replacement bundles unless
     an explicit experiment override is set; morning status now ignores legacy
     `Jarvis-Current*.app` bundles and reports only `output/Jarvis.app`.
   - 2026-06-19 proof update: user-facing docs/README/current-goal guidance now
     references only the canonical `output/Jarvis.app`; a regression rejects
     legacy `Jarvis-Current` and `Jarvis LocalOS Only` instructions.

## Safety, Privacy, And Product-Quality Bugs

1. Fixed/proved at least once: Jarvis should not read private screen/email text
   into audit logs or reports.

2. Partially fixed/risky: tool/model internals must stay out of user-visible and
   spoken output.
   - 2026-06-19 proof update: TTS sanitizer covers mixed useful text plus
     leaked `selected_tool`/`entities` JSON and inline `Tool time`/Groq model
     diagnostics.
   - 2026-06-19 proof update: server final results now sanitize user-visible
     `reply`, `email_summary`, and `spoken_summary` fields before returning
     them to the app or passing them to TTS. Regressions cover debug-only
     replies and mixed useful text plus backend/model diagnostics in both normal
     and streaming command paths.
   - 2026-06-19 proof update: the same firewall now sanitizes top-level
     user-visible `summary` text before audit/display/speech attachment, and
     debug-only sanitized-away replies still leave an explicit zero-length
     speech status instead of disappearing from copied JSON.

3. Open/unknown: stronger browser/computer-control tools must avoid destructive
   actions unless confirmed.
   - 2026-06-19 proof update: planned future `ui.automation` and `screen.ocr`
     tool status now includes machine-readable permission gates and a
     destructive-action block list covering send, submit, post, upload, delete,
     purchase, settings changes, credentials, and schoolwork changes. These
     tools still do not execute, open apps, capture screens, or read private
     content.

4. Partially fixed/risky: overnight work must not block on user approvals.
   - If a command requires approval, avoid it or defer it; Leo may be asleep.

5. Partially fixed/proved: Jarvis should build personal memory from daily chats
   and refresh it the next morning.
   - Must preserve safety boundaries and not treat untrusted text as
     instructions.
   - 2026-06-19 proof update: Jarvis now has a local `jarvis_daily_memory.json`
     surface with day rollover, compact-entry summaries, raw-chat/read/sync/model
     safety flags, report-refresh seeding, and tests proving the diagnostic does
     not read raw chat history or sync remotely. Remaining work is the
     review/delete UI plus the opt-in summarizer that writes entries into this
     surface.

6. Partially fixed/proved: contact data has durable local storage and explicit
   privacy flags.
   - Contact aliases are local-only and distinguish normal lookup/status from
     Mail sender-metadata inference. Broader daily personal context memory is
     still intentionally unresolved.

## Report, Workboard, And Testing Bugs

1. Fixed/proved at least once: Leo needs paths/URLs to workboard, STT audition,
   and master report files; reports must not omit them.

2. Partially fixed/risky: live regression matrix terminology was unclear to Leo.
   - Future reports should explain testing terms in product language.
   - 2026-06-19 proof update: master-report proof copy now calls the user-facing
     artifact an eight-prompt behavior check, while keeping the internal file
     path stable for scripts and artifacts.
   - 2026-06-19 follow-up: the workboard intro now says reusable eight-prompt
     behavior check instead of reusable behavior matrix.

3. Partially fixed/risky: tests can be too synthetic.
   - Leo repeatedly asked for real spoken input, real app output, and real action
     confirmation.

4. Partially fixed/risky: report HTML should be concise/product-announcement-like
   because Leo will not read a boring long report.
   - 2026-06-19 proof update: the master report's shipped archive now opens
     with current 0.1.468 product highlights for the `8/8` full-loop target
     prompt pass, precise native Music hidden-audio proof, explicit speech-proof
     modes, Chrome/Jarvis test-tab cleanup, and speech emergency status. Focused
     render tests pin the wording so new proof is not buried behind older
     history.

5. Fixed/proved at least once: created Chrome tabs must be cleaned before Leo
   wakes.

6. Fixed/proved: a robust overnight checklist should keep time, current goal,
   current subtask, proof needed, and return point visible.
   - 2026-06-19 proof update: the overnight workboard now renders an Operator
     Checkpoint section with Current goal, Current subtask, Proof needed, Time
     checkpoint, and Return point. The return point explicitly names
     `JARVIS_BUG_BACKLOG.md` plus `.memory.md`, and regression tests pin the
     rendered contract.

## Canonical Real-World Target Prompts To Keep Testing

1. "Look in Teams for my newest Music assignment and ask me a list of questions
   to answer so that you have enough information to finish the assignment."

2. "Play Waving Through a Window."

3. "Check in Activity Monitor how much RAM my computer is using."

4. "Open Codex and send a prompt called 'test' in the Default chat."

5. "Check my calendar for my schedule today."

6. "Test the Gemma 3 4B model for me."

7. "Summarize all the emails from Ms. Sharpay in the past month."

8. "Jarvis, could you search up the price of the Magic Keyboard and tell me its
   price converted to yuan?"

## Working Rules Derived From These Bugs

1. Do not claim success until the external state proves success.

2. If Jarvis can speak, Shut Up must be reachable.

3. Speech output must be filtered through a user-facing, voice-safe contract.

4. The model/tool route must be inspectable and honest. No fake intelligence by
   hiding brittle keyword hacks, except for explicitly approved primitive tools.

5. Music belongs to LocalOS or the future native Music app, not hidden playback.

6. Browser and app-control failures must name the real permission or blocker in
   product language.

7. Every overnight run needs time checks, a concise final HTML report, and Chrome
   test-tab cleanup before Leo wakes.

8. Keep bugs as tests wherever possible. If Leo reports a bug twice, add a
   regression test or a live-harness check before calling it fixed.

## 2026-06-19 Fixes Added To Regression Coverage

1. Fixed/proved: Teams assignment honesty no longer audits only the first
   "Opening Teams now" line. When Chrome page-read permission is blocked but
   native visible-screen OCR finds a wrong-subject assignment, the
   `assignment_subject_mismatch` response is kept as the final auditable speech
   payload.
   - Test: `test_voice_loop_qa_run_speech_audit_uses_assignment_mismatch_followup_as_final_payload`.
   - Live proof: `runtime/full_loop_regression/20260619-040451/summary.json`.

2. Fixed/proved: wrong-subject Teams summaries now have a short voice-safe
   spoken form, avoiding long technical readouts that sound like internals.
   - Test: `test_visible_screen_text_summary_refuses_wrong_subject_assignment`.
   - Live proof: the Teams voice-loop report under the focused run above
     recorded two speech payloads, ending with the concise visible-screen
     mismatch summary.

3. Fixed/proved: music playback status summaries no longer sound successful when
   LocalOS or Music only accepted/queued a request without proving audio started.
   - Tests:
     `test_localos_music_play_summary_does_not_sound_successful_when_audio_not_started`
     and
     `test_localos_music_play_summary_keeps_queued_as_unconfirmed_not_started`.
   - Product rule: only confirmed `playing` may become "Started Local OS Music
     playback"; `accepted`, `bridge_not_polling`, and generic failures must say
     playback did not start or is not confirmed yet.
