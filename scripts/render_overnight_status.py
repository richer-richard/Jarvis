#!/usr/bin/env python3
"""Render the local Jarvis overnight workboard and master report."""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "runtime" / "overnight_status"
BEIJING = ZoneInfo("Asia/Shanghai")


SHIPPED_ITEMS = [
    "Jarvis 0.1.366 fixes a LocalOS Chrome-direct false-accepted path: if Chrome rejects or fails playback, Jarvis no longer lets a delayed status update overwrite that failure as `accepted`.",
    "Jarvis 0.1.365 hardens speech interruption: the wake listener now ignores tiny transcript noise, captured-command echoes, and Jarvis's own spoken output before it calls Stop Speaking.",
    "Jarvis 0.1.364 fixes the spoken Calendar route: `check my calendar for my schedule today` now reads the Calendar schedule path instead of opening the Calendar app.",
    "Jarvis 0.1.363 speeds up stale LocalOS music recovery: Chrome-direct playback attempts are now bounded to a 4-second script window with a shorter new-tab wait instead of a long-feeling 7-second AppleEvent stall.",
    "Jarvis 0.1.362 closes the LocalOS music false-queue gap: a library snapshot is no longer enough; Jarvis now requires a live control heartbeat or Chrome-direct LocalOS confirmation before it claims playback was sent.",
    "Jarvis 0.1.361 keeps ambiguous contact candidate names out of the spoken email summary; names stay in diagnostics while Jarvis simply asks Leo to confirm the contact.",
    "Jarvis 0.1.360 stops ambiguous sender aliases before slow mailbox scans: prompts like `emails from Ms. Sharpay` now ask for contact confirmation instead of searching for the nickname as a literal sender.",
    "Jarvis 0.1.359 fixes closed-loop voice QA report collisions: simultaneous spoken-command probes now write unique run folders instead of overwriting each other's synthesized command audio.",
    "Jarvis 0.1.358 makes the Chrome-authenticated browsing boundary explicit: existing Chrome logins are not migrated into WebKit; signed-in sites use a visible Chrome handoff while Jarvis keeps its browser/status panel open.",
    "Jarvis 0.1.357 routes explicit contact-inference prompts such as `who is Ms. Sharpay from email` directly to the bounded local sender-metadata tool, avoiding a slow model-router detour.",
    "Jarvis 0.1.356 keeps contact-alias inference responsive: unknown names such as Ms. Sharpay now default to a bounded 50-message sender-metadata scan instead of a slow 250-message scan.",
    "Jarvis 0.1.355 makes LocalOS music alias matches honest: if `Waving Through a Window` maps to the broader `Dear Evan Hansen | 2017 Tony Awards` MP3, Jarvis now says it found the closest Local OS file instead of implying an exact song title exists.",
    "Jarvis 0.1.354 fixes a streaming-only voice bug: lowercase STT text like `test the gemma 3 4b model for me` now routes to `models.test_plan` before fast chat can answer casually.",
    "Jarvis 0.1.353 makes MacBook Air offload diagnostics fast and honest: before waiting on SSH, it checks the local Tailscale transport and reports `Tailscale is stopped` without changing network settings.",
    "Jarvis 0.1.352 carries bounded email date ranges such as `past_month` from the user's prompt into the Apple Mail read path, so `emails from Ms. Sharpay in the past month` no longer becomes an unbounded recent-inbox search.",
    "Jarvis 0.1.351 makes Calendar failures actionable: it distinguishes a missing cache, a permission/open failure, an empty cache, and a Calendar schema parse drift instead of only saying the cache is unavailable.",
    "Jarvis 0.1.350 routes obvious named music-play requests through LocalOS before fast chat in both preview and streaming execution, so voice-loop commands like `Play Waving Through a Window` no longer get echoed back as conversation.",
    "Jarvis 0.1.349 stamps each Python worker with the launching app's bundle identity and restarts stale workers after a rebuild, so the UI cannot quietly show a new version while the backend is old.",
    "Jarvis 0.1.348 adds a per-request quiet-audio guard for automation: closed-loop voice QA can test `Play Waving Through a Window` routing without starting LocalOS music or Jarvis speech.",
    "Jarvis 0.1.347 gives LocalOS music a second control lane: if the polling bridge is stale, Jarvis can ask the real LocalOS music page in Chrome to run `LocalOSMusicPlayer.playTrackById(...)`, and it still only claims playback after LocalOS-side confirmation.",
    "Jarvis 0.1.346 lets actual email execution try contact-alias inference from recent Mail sender metadata before searching message bodies, while `/api/plan` stays preview-only and does not read Mail metadata.",
    "Jarvis 0.1.345 resolves `today` for Calendar preview plans before execution, so `Check my calendar for my schedule today` no longer shows a vague `date_iso: null` plan.",
    "Jarvis 0.1.344 makes the Chrome-login handoff explicit in the app: authenticated sites still open in Leo's signed-in Chrome, the Jarvis browser panel stays visible for supervision, and the status now says `Opened in signed-in Chrome` instead of implying cookies were migrated.",
    "Jarvis 0.1.343 connects email sender planning to local contact memory: known aliases resolve before mailbox search, and unknown aliases such as Ms. Sharpay surface a safe `contacts.infer` next step without reading email bodies.",
    "Jarvis 0.1.342 refuses to queue LocalOS music playback when the LocalOS Music Player heartbeat is stale, so it no longer claims a song is playing when the player is not connected.",
    "Jarvis 0.1.341 fixes the overnight voice-loop routing gaps: natural `look in Teams...newest Music assignment` prompts now route to the safe Teams plan, Activity Monitor RAM prompts route to memory usage, and dictated `Gemma 3-4 B-model` is repaired to `Gemma 3 4B`.",
    "Jarvis 0.1.340 tightens the browser/session boundary: Chrome login migration routes to `browser.session_strategy`, authenticated URLs are marked as Chrome-session lanes in the Swift browser panel, and Jarvis keeps WebKit for ordinary pages.",
    "The model comparison script now matches the live Jarvis Groq request headers and scores answer quality, so fast-but-wrong model replies no longer look successful just because they returned text.",
    "LocalOS music bridge recovery now returns exact player/shell recovery metadata while keeping the spoken reply simple and path-free.",
    "Jarvis 0.1.339 preserves dictated model handles such as `Gemma 3 4B` instead of turning them into misleading names like `Gemma 3.4B`.",
    "Codex action requests such as `open Codex and send a prompt called test in the Default chat` now require strong confirmation instead of being downgraded to harmless Codex chat-status diagnostics.",
    "Jarvis 0.1.337 makes dictated Chrome bookmark requests more forgiving: if STT hears `my team's bookmark` as `my team s bookmark`, Jarvis still finds the Teams bookmark instead of saying no match.",
    "Closed-loop voice QA no longer mistakes real domains such as `teams.microsoft.com` for leaked internal tool names, so spoken-output checks fail for real backend leaks, not normal website addresses.",
    "LocalOS music playback now reports `Local OS did not pick up the command` when the LocalOS player bridge snapshot is stale, instead of claiming playback worked just because Jarvis queued a command.",
    "Jarvis 0.1.336 adds an authenticated-browser lane: Teams, Outlook, school portals, and similar imported Chrome bookmarks now ask Chrome to reuse Leo's existing login instead of pretending WebKit inherited it.",
    "Browser URL and bookmark plans now expose `preferred_open_lane`, `visible_browser_lane`, `requires_chrome_login`, and `open_chrome_to_reuse_login` so the macOS app can choose the right surface.",
    "The Swift browser panel now keeps the in-app WebKit view available for context while opening Chrome too when a signed-in page requires Leo's Chrome session.",
    "Bookmark progress wording now says `Opening that bookmark now` instead of claiming every bookmark opens only inside Jarvis.",
    "Jarvis 0.1.335 adds an in-app WebKit browser panel that can open planned URLs, searches, and imported Chrome bookmarks while keeping logged-in sites in Chrome.",
    "Chrome session migration is now explicitly refused: Jarvis uses Chrome for authenticated pages and does not copy Chrome cookies, passwords, local storage, or session stores into WebKit.",
    "The Teams assignment plan is now bookmark-first: it refreshes/imports Chrome bookmarks, opens the Teams bookmark path, uses Chrome for login state, and only treats the Teams app as a fallback.",
    "Calendar checks now fail fast when the app identity cannot read the local Calendar cache, avoiding the old 12-second AppleScript hang.",
    "Calendar has a local SQLite cache reader for environments where the Jarvis app has permission to read `group.com.apple.calendar/Calendar.sqlitedb`.",
    "GPT-OSS 120B Cloud now gets a larger visible-output budget in the Jarvis Ollama adapter, preventing empty spoken replies after hidden thinking consumes the short fast budget.",
    "The model comparison script now tests the same Ollama `/api/generate` path Jarvis actually uses and marks empty visible replies as failures.",
    "Speech diagnostics now include the full intended spoken text, not only a short preview, so echo/barge-in checks stop interrupting Jarvis's own longer answers.",
    "The bundled app build now deletes stale Python `__pycache__` files, preventing the live app from running old worker bytecode after a rebuild.",
    "LocalOS music playback confirmation now waits for LocalOS bridge playback state and distinguishes playing, accepted, failed, and unconfirmed instead of pretending queued means audible.",
    "Jarvis now has read-only prototypes for RAM usage, Calendar, browser/session strategy, model test planning, contact aliases, contact inference, and Jarvis-Codex daily memory status.",
    "A top-right Jarvis summon popout now appears for the Hey Jarvis flow and moves through listening, transcribing, thinking, answering, and speaking states.",
    "The summon popout was refined into a smaller 386x118 glass capsule instead of the oversized grey block, with transparent AppKit host layers and the stray bottom progress line removed.",
    "Experimental native Hey Jarvis listener in the macOS app, using Speech and AVAudioEngine.",
    "Wake-audition lab at /wake-audition/ for recording samples, scoring transcripts, running noise trials, and copying JSON.",
    "Wake scoring now accepts close transcripts such as hey jervis while still rejecting unrelated speech.",
    "Wake scoring now uses a stricter 0.86 fuzzy threshold so short near-misses such as hey jars are rejected.",
    "Wake status now says the current fuzzy threshold in the visible/spoken reply.",
    "Typed wake simulation now uses the same fuzzy wake tolerance, so Hey Jervis please check status is understood as check status.",
    "One-breath commands like Hey Jarvis check my email now go straight to command capture instead of also speaking the wake-only Yes sir? prompt.",
    "If the listener is already awake and hears Hey Jarvis again without a command, it keeps listening instead of submitting hey jarvis as the command.",
    "The typed voice-loop simulator now records repeated wake-only phrases as ignored before the real follow-up command.",
    "After Jarvis says the wake-only Yes sir? prompt, the command listener ignores that speaker echo instead of submitting yes sir as Leo's command.",
    "Typed wake simulation now ignores the wake greeting echo too, so the wake lab matches the native listener before the real follow-up command arrives.",
    "Copy Chat JSON now includes recent wake events so Leo can paste back what Jarvis heard and captured.",
    "Copy Chat JSON now records ignored repeated wake phrases and ignored speaker-echo events from the native listener.",
    "Native Copy Chat JSON wake events now include detector score, threshold, matched phrase, window, mode, and normalized transcript.",
    "Jarvis can now analyze pasted Copy Chat JSON wake logs with voice.wake_debug.",
    "Copy Chat JSON now includes the filtered history payload preview Jarvis would send with the current command.",
    "A conversation-context smoke script now checks whether Jarvis can answer a follow-up using prior chat history.",
    "A wake-threshold smoke script now proves exact, fuzzy, and near-miss wake phrases without recording audio.",
    "The wake-audition lab now has clickable threshold corpus phrases for exact, fuzzy, and near-miss sanity checks.",
    "Wake-lab Copy JSON now includes the selected threshold corpus case when Leo clicks one.",
    "Normal Dock-app behavior is preserved, with a menu-bar item enabled for quick controls.",
    "Menu-bar Shut Up toggle mutes Jarvis, interrupts current speech, and switches to Keep Blabbering for unmute.",
    "The Shut Up menu action now marks the Swift UI muted immediately before the backend round trip, reducing speech-race windows.",
    "The Shut Up menu action now sends the mute request directly to the worker before any worker-start fallback can delay it.",
    "No-prompt verification now restores Jarvis to the exact speech mute state it found, so checks do not undo Shut Up.",
    "Menu-bar Start Hey Jarvis / Stop Hey Jarvis controls make the wake listener reachable without opening the panel.",
    "Menu-bar Open Wake Test jumps straight to the local wake-audition page.",
    "Menu-bar Open Overnight Report jumps straight to the master report route.",
    "The Jarvis panel now shows speech mute state and uses Wake Lab for the new audition route.",
    "The Jarvis panel now has a Perms quick action for microphone, speech, screen, accessibility, and notification readiness.",
    "The wake lab now summarizes runs into detected count, best noisy pass, and a suggested next step.",
    "Wake-lab Copy JSON now includes the current transcript, current score, and recommendation even before a run is saved.",
    "Wake-lab buttons now separate numbered saved-sample steps from the disposable Live Transcript Only check.",
    "Mac/device-status requests now go through the first model's tool call before reading local device facts.",
    "App list/status/running/focus/open requests now give the first model the tool choice before local app parsing runs.",
    "Model-context diagnostics now expose the exact input-source policy for typed text and speech dictation.",
    "Streaming app working lines now include the app name when Jarvis already knows it, such as Yes sir, checking Safari now.",
    "Final answers with normal reply text now auto-speak by default instead of leaving only the working line audible.",
    "Streaming status updates can no longer overwrite an answer that has already started appearing on screen.",
    "Synthetic Still working progress rows are removed when the task finishes, so they do not remain below a completed answer.",
    "Typed submissions now refuse overlapping turns while Jarvis is busy, which prevents orphaned progress nudges from a second command race.",
    "Speech diagnostics now include a short sanitized text preview, so Copy Chat JSON can show what TTS was asked to say.",
    "Copy Chat JSON turn traces now include speech-alignment diagnostics that flag tiny TTS previews such as Hello against longer visible answers.",
    "Live command endpoints now accept suppress_speech=true or speak=false for quiet verification without muting the whole app.",
    "Groq 429 rate-limit responses now retry Groq first before falling through to GPT-OSS 120B Cloud, keeping the smart fallback while improving first-visible latency.",
    "Hey Jarvis now spaces out Apple Speech restarts and stops after the third close restart, reducing the menu-bar dictation flicker loop.",
    "Hey Jarvis now also stops after the fourth restart in one activation, catching slower flicker loops that are not rapid enough for the storm guard.",
    "Hey Jarvis now de-duplicates identical listener snapshots before publishing them to the SwiftUI panel.",
    "The native audio tap now uses a non-actor sink so Core Audio's realtime callback does not inherit MainActor isolation.",
    "Hey Jarvis now pauses after immediate silent Apple Speech endings instead of repeatedly flashing the menu bar while it restarts.",
    "When Hey Jarvis pauses itself for stability, the app now adds a visible chat line explaining what happened.",
    "Start Hey Jarvis now preflights Microphone and Speech Recognition readiness and refuses with a visible Jarvis message instead of triggering permission prompts when either is missing.",
    "The master report and workboard now have read-only loopback URLs at /overnight-report/ and /overnight-workboard/.",
]

PROOF_ITEMS = [
    "Current verification: focused Chrome-session handoff tests pass; full safety, Swift, no-prompt, and live-app checks are rerun after each bundle rebuild.",
    "Focused LocalOS Chrome-direct regression now requires the injected control script to preserve `failed` playback status instead of rewriting it to `accepted` after the delayed snapshot publish.",
    "Swift self-test and Python source regression now prove short listener fragments, Calendar-answer echoes, and captured wake-command echoes do not stop Jarvis speech, while an intentional `wait stop for a second` interruption still does.",
    "Focused contact inference timing on this Mac showed preview is instant and 50 recent Mail sender records completed in about 2.7s, while larger scans are now explicit instead of default.",
    "Live quiet voice-loop QA passed for `Hey Jarvis, who is Ms. Sharpay from email?`, routing to `contacts.infer` with spoken-output similarity 0.988.",
    "Focused LocalOS check now reports `closest Local OS file` for the Waving Through a Window alias and still keeps audio actions suppressed in automation.",
    "Focused streaming regression now proves `test the gemma 3 4b model for me` bypasses fast chat, emits `Planning the model test now`, and returns the safe MacBook Air/local-fallback plan.",
    "Live quiet voice-loop QA passed after the fix for model offload, Chrome-login migration, Teams assignment planning, and suppressed `Play Waving Through a Window` playback.",
    "Live remote-worker probe now returns in about 0.1s with `tailnet_stopped` when Tailscale is stopped, and model-test planning tells Leo the real reason before asking for any local fallback.",
    "Voice-loop QA now sends `suppress_audio_actions: true`, and server/tool tests prove this suppresses LocalOS music side effects for automation while normal user play commands remain executable.",
    "Focused LocalOS tests now prove stale or heartbeat-missing player snapshots still refuse when Chrome-direct LocalOS control is unavailable, bound Chrome-direct automation to 4 seconds, and succeed only when the LocalOS page confirms the direct `playTrackById` command.",
    "Closed-loop Calendar voice QA exposed a real bug where `check my calendar for my schedule today` opened Calendar; Jarvis 0.1.364 adds tests for that phrase and keeps plain `open Calendar` as app-open behavior.",
    "Overnight no-permission voice suite passed for Teams assignment planning, Waving Through a Window recovery, Activity Monitor RAM, Codex strong-confirmation, Gemma 3 4B model-test planning, and Chrome-session migration.",
    "Live closed-loop voice QA now passes for the safe example prompts: natural Teams Music assignment planning, Activity Monitor RAM, Codex strong-confirmation, Teams bookmark, browser session strategy, and Gemma 3 4B model-test planning.",
    "The Gemma model-test voice loop now survives local STT hearing `Gemma 3-4 B-model`, repairs the visible reply to `Gemma 3 4B`, routes to `models.test_plan`, and matches spoken output with 1.0 similarity.",
    "The Codex Default-chat prompt voice loop now routes to `policy.strong_confirmation` and says `Command requires strong confirmation and was not executed` instead of sending anything or showing chat-status diagnostics.",
    "Live closed-loop voice QA passed for `Hey Jarvis, open my Teams bookmark`: local STT heard `my team's bookmark`, Jarvis routed `open my team s bookmark`, selected `browser.bookmark_open`, and the spoken reply matched the visible reply with 0.995 similarity.",
    "Focused LocalOS tests now prove stale player snapshots return `bridge_not_polling` and tell Leo to open or refresh the Local OS Music Player instead of making a false audible-playback claim.",
    "Live suppressed `Play Waving Through a Window` now returns `Local OS Music is not connected right now` and leaves the LocalOS command queue expired instead of starting or claiming audio.",
    "Focused browser-lane tests now prove Teams URLs choose `chrome_authenticated`, ordinary URLs choose `jarvis_webkit`, and the Swift shell opens Chrome when `open_chrome_to_reuse_login` is set.",
    "Real Chrome session proof: opening `https://teams.microsoft.com/v2/` in Leo's Chrome reused the existing Microsoft login and landed on `Teams and Channels | General | Microsoft Teams` at `https://teams.cloud.microsoft/`, not a login screen.",
    "Live suppressed Teams-assignment probe returned `teams.assignment` with `preferred_browser_lane=chrome_authenticated`, `visible_browser_lane=jarvis_webkit_panel`, and `copied_chrome_cookies=false`.",
    "Live suppressed Calendar probe returned in 0.0s with `cache_unavailable`, replacing the previous 12-second timeout behavior.",
    "Latest scored cloud-first model comparison: GPT-OSS 120B Cloud scored 5/5, Gemma4 31B Cloud scored 5/5 and was fastest on text, GPT-OSS 20B Cloud returned empty visible replies, and bare Groq Llama 70B was fast but failed safety/math/tool-shape checks without Jarvis's wrapper.",
    "Gemma4 31B Cloud did not confirm audio input through Ollama on `/Users/leoxu/Desktop/Hello.mp3`; it answered `CANNOT_HEAR_AUDIO` through the audio field and rejected the MP3 through the image field.",
    "Live closed-loop voice QA passed for the Ms. Sharpay email prompt: STT heard `his Sharpay`, Jarvis still routed to email, skipped mailbox scanning, asked for contact confirmation, and matched spoken output with 0.992 similarity.",
    "Live closed-loop voice QA passed for natural Teams assignment planning after the reply cleanup: Jarvis now says it can start through the Teams bookmark and will ask Leo questions, instead of reading a long internal safety checklist aloud.",
    "Jarvis's own GPT-OSS 120B Cloud adapter produced the 少先队 email-style spoken summary in 3.9s after the visible-output budget change.",
    "Voice-loop QA passed for natural Teams assignment planning, RAM usage, model-test planning, browser session strategy, and Calendar fast-fail behavior with speech suppressed.",
    "Chrome bookmark snapshot has 23 imported links from 3 profiles, including `teams.microsoft.com`.",
    "Sharpay-style email previews now include `contact_alias_lookup`, `resolved_sender_query`, and `recommended_tool: contacts.infer` when the alias is not known, while remaining planned-only; actual email execution can now infer a confident alias from recent sender metadata before searching messages.",
    "Latest local checkpoint commits record the browser/session, music-recovery, model-scoring, report-proof, voice-loop routing, LocalOS stale-bridge hardening, and contact-aware email planning; the branch has not been pushed while Leo is asleep.",
    "Python safety suite: 562/562 passed after the wake, mute, final-speech, report-route, speech-alignment, barge-in filtering, model-selected device/app-routing, app-specific status-line, fuzzy-wake, stale-progress, anti-flicker, muted-latency, local-STT repair, overlapping-turn, crash-monitor, fallback-hardening, quiet-command, quiet-audio automation, summon-popout, hidden-tool-call sanitization, model-scoring, browser-session, music-bridge, contact-memory, contact-inference, calendar-preview, LocalOS Chrome-direct control, and voice-QA work.",
    "Swift build passed for the Jarvis menu-bar app.",
    "Swift self-tests passed, including menu-bar routing labels, native wake detection, and worker checks.",
    "Swift permission-readiness self-test passed without requesting permissions; it currently reports Microphone ready and Speech Recognition not requested.",
    "Live safe verifier passed 97/97 after the speech-mute, wake-audition, wake-lab corpus, model-context, wake-debug, repeated-wake, voice-loop echo, and report-route endpoints were added.",
    "After Leo asked for no more permission prompts, the overnight checks stayed to no-prompt paths: Python suite, Swift self-test, live report route, wake lab route, speech mute alignment, model-context diagnostic, voice-loop echo, and wake-start preflight source contracts.",
    "Live verifier now checks that muted final speech preserves a substantial prefix of the final visible reply.",
    "Live Jarvis health showed the rebuilt app running from bundled app resources.",
    "Live UI inspection showed the Jarvis panel with Email, Status, Report, Wake Lab, Hey Jarvis, Perms, Screen, and Codex actions visible.",
    "A muted live TTS probe returned the exact sanitized text_preview that Jarvis was asked to speak.",
    "A muted live hello stream matched visible text, final reply, and TTS text_preview.",
    "A muted live Mac-status probe returned diagnostics.device with routing.source=model_tool_call.",
    "Muted live app-status and app-running probes returned app.status/app.running with routing.source=model_tool_call and did not launch or focus apps.",
    "Model-context tests now require the diagnostic to show that first and middle models treat Leo's latest message as possibly dictated speech.",
    "Live verifier now probes diagnostics.model_context and requires the speech-dictation input policy without calling models.",
    "Swift source-contract tests now require Copy Chat JSON to expose the filtered conversation-history payload preview.",
    "Conversation-context smoke tests now suppress speech per request and detect whether a follow-up used prior history without changing global mute state.",
    "Fast-latency smoke tests now suppress speech per request before timing live prompts, count direct final-only replies as visible, and read the model-result status so a busy placeholder cannot masquerade as a completed answer.",
    "Live latency smoke now passes on Jarvis 0.1.315 with max first visible 2.855s, max total 3.111s, and first visible text as low as 0.214s.",
    "Wake-threshold smoke tests now verify hey jervis passes while hey jars and hey charvis reject at the 0.86 threshold.",
    "Static wake-lab tests now require the threshold corpus panel, corpus buttons, and below-threshold charvis case.",
    "Static and verifier wake-lab tests now require the self-explanatory Live Transcript Only and Copy Codex JSON labels.",
    "Static wake-lab tests now require Copy JSON to include the selected corpus case.",
    "Swift source tests now require Shut Up to apply the target mute state immediately, call the mute endpoint before worker-start fallback, and still roll back on backend failure.",
    "Live verifier now checks that the bundled wake-audition page, JavaScript, and CSS expose the threshold corpus route.",
    "A muted live streaming app-status probe displayed Yes sir, checking Safari now before the final answer.",
    "A muted live wake probe understood Hey Jervis please check status as check status, and wake scoring reported fuzzy_window score 0.916667 instead of a fake exact match.",
    "Python and Swift wake tests now keep hey jervis working while rejecting the short near-miss hey jars.",
    "A muted live wake-status probe confirmed the visible reply includes the 0.86 threshold.",
    "Native one-breath wake commands now skip the separate wake-only Yes sir? prompt, reducing overlapping speech between the wake greeting and the working line.",
    "Native awaiting-command handling now ignores repeated wake-only phrases instead of routing them as user commands.",
    "Native awaiting-command handling now ignores the wake greeting echo, reducing accidental yes sir command captures from Jarvis's own speaker.",
    "Python wake-session tests now cover the same wake greeting echo path before a real follow-up command.",
    "Python wake-session and voice-loop tests now cover repeated wake-only phrases before a real follow-up command.",
    "Live verifier now probes voice loop: Hey Jarvis | Yes sir? | status and requires status to be captured after the ignored echo.",
    "Swift source contract now requires ignored repeated-wake and wake-greeting-echo events to be present in Copy Chat JSON.",
    "Swift self-tests now require fuzzy matching for okay jervis as well as hey jervis, with detector diagnostics exposed for pasted JSON.",
    "Live verifier now probes voice.wake_debug with pasted Copy Chat JSON and requires no audio recording.",
    "Closed-loop voice QA now synthesizes a command with Piper, transcribes it, routes it through Jarvis while muted, synthesizes the visible reply, and compares the spoken transcript back to the screen text.",
    "Closed-loop voice QA now uses per-command speech suppression instead of globally muting Jarvis while it routes the recognized command.",
    "Closed-loop voice QA now has a no-permission-prompts mode that skips Apple Speech and fails closed through local STT only.",
    "Local faster-whisper tiny.en now has a complete checked model cache from the mirror endpoint, so no-permission voice QA can run without Apple Speech.",
    "Latest voice-loop QA passed with Hey Jarvis status routed to status and 0.94 reply similarity.",
    "A 35-second app-bundle Hey Jarvis soak on Jarvis 0.1.279 returned successfully without a new crash report.",
    "Native Hey Jarvis now pauses itself if Apple Speech enters a rapid microphone restart loop, preventing the menu-bar flicker from becoming a crash spiral.",
    "Native Hey Jarvis also pauses if Apple Speech ends immediately without hearing speech, so a broken listener fails quiet instead of flickering.",
    "Copy Chat JSON now records listener_paused wake events when the app stops Hey Jarvis for stability.",
    "Local-only voice QA now fails closed: if STT returns an empty transcript, it does not route a fake status command.",
    "Swift self-tests now reject a tiny Hello TTS preview when the visible final answer is longer.",
    "Voice-loop QA tests now prove no-permission mode does not call the Apple Speech app path.",
    "Local-only voice QA now passes end to end with faster-whisper tiny.en: Hey Jarvis status routed to status and reply similarity cleared 0.90.",
    "Swift self-tests now require less frantic wake restart timing, fourth-activation-restart pause behavior, third-close-restart pause behavior, and duplicate wake snapshot suppression.",
    "Static safety tests and the no-prompt verifier now require the wake audio tap to capture a non-actor sink instead of appending to Speech from a MainActor-inherited closure.",
    "The current live build launched cleanly after the anti-flicker cleanup.",
    "Jarvis 0.1.308 build 308 launched cleanly after the summon-popout glass refinement.",
]

TRY_ITEMS = [
    "Ask Jarvis to open the Teams bookmark or search imported Chrome bookmarks for Teams; the Jarvis browser panel should appear, and Chrome remains the lane for already-logged-in pages.",
    "If Jarvis says Local OS did not pick up a music command, open or refresh the Local OS Music Player once; that means Jarvis found the song but the page has not consumed the bridge command yet.",
    "Ask Jarvis about Chrome login migration; it should say it will use Chrome for authenticated sites and should not copy cookies or session stores.",
    "Ask Jarvis to check Calendar; it should answer quickly. If it says the cache is unavailable, the remaining work is macOS permission/app-identity access, not a slow planner hang.",
    "Ask Jarvis to test a model; if the MacBook Air worker is unreachable, it should ask before running the model locally on the 16 GB MacBook Pro.",
    "Open Jarvis from the Dock; it should be a normal app window, not an always-front overlay.",
    "Use the Popout button in the debug panel to preview the new top-right glass summon surface without starting the microphone listener.",
    "Click Perms first and read the permission tiles; if Microphone and Speech Recognition are ready, use Start Hey Jarvis from the menu bar, then say Hey Jarvis followed by a short command.",
    "Try a one-breath command such as Hey Jarvis wake status; Jarvis should avoid a separate Yes sir? prompt and go straight into the task response.",
    "Use Shut Up if Jarvis is talking too much; use Keep Blabbering to restore speech.",
    "Ask for wake status or overnight status; Jarvis should speak the final answer, not only the Yes sir working line.",
    "If Start Hey Jarvis refuses, read the visible Jarvis message; it should name the missing macOS permission instead of opening a permission prompt.",
    "Open the wake lab and record several Hey Jarvis samples in quiet and noisy conditions.",
    "Use the wake lab Copy JSON button if recognition feels wrong, then paste the JSON back to Codex.",
    "Use Copy Chat JSON after a failed wake attempt; it now includes wake detected and command captured events.",
]

RISK_ITEMS = [
    "Jarvis 0.1.346 cannot yet read Calendar from the live app identity; it now fails fast, but Leo may need to grant the current Jarvis/Python app identity Calendar or Full Disk access for actual schedules.",
    "The LocalOS music page likely needs a reload or active Chrome tab to pick up the playback-state bridge; Jarvis now reports missing/stale bridge status honestly, but live audible playback was not triggered while Leo was asleep.",
    "MacBook Air remote-worker probing currently cannot proceed because Tailscale is stopped on this Mac; Jarvis now detects that quickly and should ask before running model tests locally.",
    "Groq works as Jarvis's fast conversation model, but the scored middle-model comparison showed it should not be trusted for safety-sensitive planning without stronger prompting or a safer model layer.",
    "GPT-OSS 20B Cloud returned empty visible replies in the newest comparison and should not be treated as a dependable middle model yet.",
    "Gemma4 31B Cloud did not confirm audio understanding through Ollama; it answered text prompts well, but native audio input remains unproven.",
    "Real microphone pickup, false wakes, and room-noise reliability still need Leo testing.",
    "The summon popout's code-level rectangle and stray-line causes are fixed, but Leo should do the final human-eye check on the real Stage Manager desktop.",
    "Browser loopback noise trials are useful but not a perfect model of a real room.",
    "Speech Recognition permission can still block the native listener until macOS grants it to the current Jarvis bundle.",
    "Local-only faster-whisper STT now works for file-based QA, but tiny.en still mishears some technical words and is not good enough as the final live dictation model.",
    "The full safe verifier was not rerun after the no-permission instruction because some verifier paths can touch microphone or Speech permission; the report keeps the latest 97/97 artifact and the safer live subset separate.",
    "The current wake phrase is experimental; it is not yet personalized to Leo's voice.",
    "Very technical diagnostics are still intentionally speech-silent so Jarvis does not read backend internals aloud.",
    "GitHub main still preserves the older small-tree history; the full Jarvis folder is published on the overnight branch and should be promoted deliberately.",
]

SUPPORTING_FILES = [
    ("http://127.0.0.1:8765/overnight-report/", "Loopback master report"),
    ("http://127.0.0.1:8765/overnight-workboard/", "Loopback overnight workboard"),
    ("runtime/overnight_status/index.html", "Live overnight workboard"),
    ("runtime/overnight_status/report.html", "This master report"),
    ("http://127.0.0.1:8765/wake-audition/", "Hey Jarvis wake audition lab"),
    ("runtime/wake_audition/samples/", "Locally saved wake samples"),
    ("runtime/verification/", "Safe verifier reports"),
    ("runtime/verification_no_prompt/", "No-prompt live verifier reports"),
    ("runtime/model_benchmarks/", "Fast latency smoke reports"),
    ("runtime/conversation_context/", "Conversation-context smoke reports"),
    ("runtime/wake_threshold/", "Wake-threshold smoke reports"),
    ("runtime/voice_loop_qa/latest.json", "Latest closed-loop voice QA report"),
    ("runtime/voice_loop_qa/", "Closed-loop voice QA artifacts"),
    ("runtime/model_comparison/", "Cloud-first middle model comparison reports"),
    ("runtime/integrations/chrome_bookmarks.json", "Imported Chrome bookmark snapshot"),
    ("runtime/integrations/localos_music_snapshot.json", "Latest LocalOS music bridge snapshot"),
    ("runtime/codex_daily_memory.json", "Local Jarvis-to-Codex daily memory"),
    ("runtime/memory/contact_aliases.json", "Local contact alias memory"),
    ("scripts/repair_local_stt_model.py", "Local faster-whisper model repair helper"),
    ("output/playwright/", "Visual QA screenshots"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the Jarvis overnight report surfaces.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765", help="Jarvis worker base URL.")
    args = parser.parse_args()

    context = build_context(args.base_url.rstrip("/"))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "report.html").write_text(render_report(context), encoding="utf-8")
    (OUTPUT_DIR / "index.html").write_text(render_workboard(context), encoding="utf-8")
    print(f"Rendered {OUTPUT_DIR / 'index.html'}")
    print(f"Rendered {OUTPUT_DIR / 'report.html'}")
    return 0


def build_context(base_url: str) -> dict[str, Any]:
    health = get_json(f"{base_url}/api/health")
    app = nested(health, "status", "app")
    runtime = nested(health, "status", "runtime")
    fast_model = nested(health, "status", "fast_model")
    verification = latest_verification()
    no_prompt_verification = latest_no_prompt_verification()
    latency = latest_latency_smoke()
    context_smoke = latest_context_smoke()
    wake_threshold = latest_wake_threshold_smoke()
    voice_loop = latest_voice_loop_qa()
    crash = latest_jarvis_crash_report()
    now = datetime.now(BEIJING)
    version = str(app.get("version") or "unknown")
    build = str(app.get("build") or "unknown")
    commit = git(["rev-parse", "--short", "HEAD"]) or "unknown"
    branch = git(["branch", "--show-current"]) or "unknown"
    upstream = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    git_sync = git_sync_label(upstream)
    return {
        "base_url": base_url,
        "now": now,
        "updated": now.strftime("%Y-%m-%d %H:%M CST"),
        "version": version,
        "build": build,
        "bundle": f"Jarvis {version} build {build}",
        "commit": commit,
        "branch": branch,
        "upstream": upstream,
        "git_sync": git_sync,
        "verification": verification,
        "no_prompt_verification": no_prompt_verification,
        "latency": latency,
        "context_smoke": context_smoke,
        "wake_threshold": wake_threshold,
        "voice_loop": voice_loop,
        "worker_source_kind": app.get("worker_source_kind") or "unknown",
        "launch_mode": app.get("launch_mode") or "unknown",
        "runtime_pid": runtime.get("pid") or "unknown",
        "fast_model": fast_model,
        "shipped": SHIPPED_ITEMS,
        "proof": proof_items_with_verification(
            verification,
            no_prompt_verification,
            latency,
            context_smoke,
            wake_threshold,
            voice_loop,
            crash,
            version,
            build,
        ),
        "try": TRY_ITEMS,
        "risks": RISK_ITEMS,
        "supporting": SUPPORTING_FILES,
        "crash": crash,
    }


def proof_items_with_verification(
    verification: dict[str, Any],
    no_prompt_verification: dict[str, Any] | None = None,
    latency: dict[str, Any] | None = None,
    context_smoke: dict[str, Any] | None = None,
    wake_threshold: dict[str, Any] | None = None,
    voice_loop: dict[str, Any] | None = None,
    crash: dict[str, Any] | None = None,
    current_version: str = "",
    current_build: str = "",
) -> list[str]:
    items = list(PROOF_ITEMS)
    if verification.get("path"):
        items.append(
            f"Latest verifier artifact: {verification['path']} with {verification['passed']}/{verification['total']} checks."
        )
    if no_prompt_verification and no_prompt_verification.get("path"):
        items.append(
            "Latest no-prompt live verifier: "
            f"{no_prompt_verification['path']} with {no_prompt_verification['passed']}/{no_prompt_verification['total']} checks, "
            "covering only routes and source checks that do not request microphone, Speech Recognition, Screen Recording, Accessibility, app launch, or GitHub push."
        )
    if latency and latency.get("path"):
        items.append(
            "Latest fast-latency smoke: "
            f"{latency['label']}, max first visible {latency['max_first_visible_seconds']:.3f}s, "
            f"max total {latency['max_total_seconds']:.3f}s, "
            f"min after-first {latency['min_after_first_chars_per_second']:.1f} chars/s "
            f"({latency['path']})."
        )
    if context_smoke and context_smoke.get("path"):
        items.append(
            "Latest conversation-context smoke: "
            f"{context_smoke['label']}, total {context_smoke['total_seconds']:.3f}s "
            f"({context_smoke['path']})."
        )
    if wake_threshold and wake_threshold.get("path"):
        items.append(
            "Latest wake-threshold smoke: "
            f"{wake_threshold['label']}, {wake_threshold['passed']}/{wake_threshold['total']} cases, "
            f"closest reject {wake_threshold['closest_reject_label']} at {wake_threshold['closest_reject_score']:.6f} "
            f"({wake_threshold['path']})."
        )
    if voice_loop and voice_loop.get("path"):
        if voice_loop.get("speech_audit_only"):
            items.append(
                "Latest voice speech audit: "
                f"{voice_loop['label']}, payloads {voice_loop['speech_payload_count']}, "
                f"leaks {voice_loop['speech_leak_count']}, tool {voice_loop['command_response_tool']!r} "
                f"({voice_loop['path']})."
            )
        else:
            items.append(
                "Latest closed-loop voice QA: "
                f"{voice_loop['label']}, command transcript {voice_loop['command_transcript']!r}, "
                f"routed command {voice_loop['routed_command']!r}, reply similarity {voice_loop['reply_similarity']:.3f} "
                f"({voice_loop['path']})."
            )
        latest_path = str(voice_loop.get("latest_path") or "")
        if latest_path and latest_path != voice_loop.get("path"):
            latest_error = str(voice_loop.get("latest_command_stt_error") or "")
            if latest_error:
                latest_error = f", error {shorten(latest_error, 96)}"
            items.append(
                "Newest closed-loop voice QA run: "
                f"{voice_loop['latest_label']}, provider {voice_loop['latest_stt_provider']}, "
                f"command STT {voice_loop['latest_command_stt_status']}, "
                f"routed command {voice_loop['latest_routed_command']!r}{latest_error} "
                f"({latest_path})."
            )
    if crash and crash.get("path"):
        crash_version = str(crash.get("version") or "unknown")
        crash_build = str(crash.get("build") or "unknown")
        crash_time = str(crash.get("timestamp") or "unknown time")
        if crash_version == current_version and crash_build == current_build:
            items.append(
                "Newest local crash report is from the current live build "
                f"{crash_version} build {crash_build} at {crash_time}: {crash['path']}."
            )
        else:
            items.append(
                "Newest local crash report is from older build "
                f"{crash_version} build {crash_build} at {crash_time}; no current-build crash report is present."
            )
    return items


def get_json(url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data if isinstance(data, dict) else {}
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return {}


def latest_jarvis_crash_report(log_dir: Path | None = None) -> dict[str, Any]:
    directory = log_dir or (Path.home() / "Library" / "Logs" / "DiagnosticReports")
    try:
        reports = sorted(
            directory.glob("jarvis-menu-bar-*.ips"),
            key=lambda path: path.stat().st_mtime,
        )
    except OSError:
        return {"path": "", "label": "unavailable", "version": "", "build": "", "timestamp": ""}
    if not reports:
        return {"path": "", "label": "none", "version": "", "build": "", "timestamp": ""}
    latest = reports[-1]
    try:
        first_line = latest.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        metadata = json.loads(first_line)
    except (OSError, IndexError, json.JSONDecodeError):
        return {
            "path": str(latest),
            "label": "unreadable",
            "version": "",
            "build": "",
            "timestamp": "",
        }
    if not isinstance(metadata, dict):
        metadata = {}
    return {
        "path": str(latest),
        "label": "readable",
        "version": str(metadata.get("app_version") or ""),
        "build": str(metadata.get("build_version") or ""),
        "timestamp": str(metadata.get("timestamp") or ""),
    }


def latest_verification() -> dict[str, Any]:
    reports = sorted((PROJECT_ROOT / "runtime" / "verification").glob("verify-safe-*.json"))
    if not reports:
        return {"ok": False, "path": "", "passed": 0, "total": 0, "label": "none"}
    latest = reports[-1]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "path": str(latest), "passed": 0, "total": 0, "label": "unreadable"}
    results = data.get("results") if isinstance(data.get("results"), list) else []
    passed = sum(1 for item in results if isinstance(item, dict) and item.get("passed"))
    total = len(results)
    relative = str(latest.relative_to(PROJECT_ROOT))
    return {
        "ok": bool(data.get("ok")) and total > 0 and passed == total,
        "path": relative,
        "passed": passed,
        "total": total,
        "label": f"{passed}/{total} passed" if total else "empty",
    }


def latest_no_prompt_verification() -> dict[str, Any]:
    reports = sorted((PROJECT_ROOT / "runtime" / "verification_no_prompt").glob("verify-no-prompt-*.json"))
    if not reports:
        return {"ok": False, "path": "", "passed": 0, "total": 0, "label": "none"}
    latest = reports[-1]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "path": str(latest), "passed": 0, "total": 0, "label": "unreadable"}
    results = data.get("results") if isinstance(data.get("results"), list) else []
    passed = sum(1 for item in results if isinstance(item, dict) and item.get("passed"))
    total = len(results)
    policy = data.get("policy") if isinstance(data.get("policy"), dict) else {}
    policy_safe = not any(
        bool(policy.get(key))
        for key in (
            "opens_apps",
            "requests_microphone",
            "requests_speech_recognition",
            "uses_screen_capture",
            "uses_accessibility",
            "pushes_to_network_repo",
        )
    )
    relative = str(latest.relative_to(PROJECT_ROOT))
    return {
        "ok": bool(data.get("ok")) and policy_safe and total > 0 and passed == total,
        "path": relative,
        "passed": passed,
        "total": total,
        "policy_safe": policy_safe,
        "label": f"{passed}/{total} passed" if total else "empty",
    }


def latest_latency_smoke() -> dict[str, Any]:
    reports = sorted((PROJECT_ROOT / "runtime" / "model_benchmarks").glob("localhost-fast-latency-*.json"))
    if not reports:
        return {"ok": False, "path": "", "label": "none"}
    latest = reports[-1]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "path": str(latest), "label": "unreadable"}
    results = [item for item in data.get("results", []) if isinstance(item, dict)]
    completed = [item for item in results if item.get("status") == "completed"]
    max_first = max((float(item.get("first_visible_seconds") or 0) for item in completed), default=0.0)
    max_total = max((float(item.get("total_seconds") or 0) for item in completed), default=0.0)
    min_rate_chars = int(data.get("min_rate_visible_chars") or 20)
    rate_candidates = [
        float(item.get("chars_per_second_after_first_visible") or 0)
        for item in completed
        if int(item.get("visible_chars") or 0) >= min_rate_chars
    ]
    min_cps = min(rate_candidates, default=0.0)
    first_limit = float(data.get("max_first_visible_seconds") or 3.0)
    total_limit = float(data.get("max_total_seconds") or 5.0)
    cps_limit = float(data.get("min_after_first_chars_per_second") or 20.0)
    ok = bool(results) and len(completed) == len(results) and max_first <= first_limit and max_total <= total_limit
    if rate_candidates:
        ok = ok and min_cps >= cps_limit
    relative = str(latest.relative_to(PROJECT_ROOT))
    return {
        "ok": ok,
        "path": relative,
        "completed": len(completed),
        "total": len(results),
        "label": f"{'passed' if ok else 'needs attention'} {len(completed)}/{len(results)}",
        "max_first_visible_seconds": max_first,
        "max_total_seconds": max_total,
        "min_after_first_chars_per_second": min_cps,
    }


def latest_context_smoke() -> dict[str, Any]:
    reports = sorted((PROJECT_ROOT / "runtime" / "conversation_context").glob("conversation-context-*.json"))
    if not reports:
        return {"ok": False, "path": "", "label": "none", "total_seconds": 0.0}
    latest = reports[-1]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "path": str(latest), "label": "unreadable", "total_seconds": 0.0}
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    ok = result.get("status") == "passed" and result.get("used_history") is True
    relative = str(latest.relative_to(PROJECT_ROOT))
    return {
        "ok": ok,
        "path": relative,
        "label": "passed" if ok else "needs attention",
        "total_seconds": float(result.get("total_seconds") or 0.0),
    }


def latest_wake_threshold_smoke() -> dict[str, Any]:
    reports = sorted((PROJECT_ROOT / "runtime" / "wake_threshold").glob("wake-threshold-*.json"))
    if not reports:
        return {
            "ok": False,
            "path": "",
            "label": "none",
            "passed": 0,
            "total": 0,
            "closest_reject_label": "",
            "closest_reject_score": 0.0,
        }
    latest = reports[-1]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "ok": False,
            "path": str(latest),
            "label": "unreadable",
            "passed": 0,
            "total": 0,
            "closest_reject_label": "",
            "closest_reject_score": 0.0,
        }
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    passed = int(summary.get("passed") or 0)
    total = int(summary.get("total") or 0)
    ok = summary.get("status") == "passed" and total > 0 and passed == total
    relative = str(latest.relative_to(PROJECT_ROOT))
    return {
        "ok": ok,
        "path": relative,
        "label": "passed" if ok else "needs attention",
        "passed": passed,
        "total": total,
        "closest_reject_label": str(summary.get("closest_reject_label") or ""),
        "closest_reject_score": float(summary.get("closest_reject_score") or 0.0),
    }


def latest_voice_loop_qa() -> dict[str, Any]:
    report_root = PROJECT_ROOT / "runtime" / "voice_loop_qa"
    reports = sorted(
        report_root.rglob("report.json"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0.0,
    )
    if not reports:
        return {
            "ok": False,
            "path": "",
            "label": "none",
            "command_transcript": "",
            "routed_command": "",
            "reply_similarity": 0.0,
            "latest_path": "",
            "latest_label": "none",
            "latest_stt_provider": "",
            "latest_command_stt_status": "",
            "latest_command_stt_error": "",
            "latest_routed_command": "",
            "speech_audit_only": False,
            "speech_payload_count": 0,
            "speech_leak_count": 0,
            "command_response_tool": "",
        }
    latest_readable: tuple[Path, dict[str, Any]] | None = None
    latest_passed: tuple[Path, dict[str, Any]] | None = None
    for candidate in reversed(reports):
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        result = data.get("result") if isinstance(data.get("result"), dict) else {}
        if latest_readable is None:
            latest_readable = (candidate, data)
        if result.get("status") == "passed":
            latest_passed = (candidate, data)
            break
    if latest_readable is None:
        return {
            "ok": False,
            "path": str(reports[-1]),
            "label": "unreadable",
            "command_transcript": "",
            "routed_command": "",
            "reply_similarity": 0.0,
            "latest_path": str(reports[-1]),
            "latest_label": "unreadable",
            "latest_stt_provider": "",
            "latest_command_stt_status": "",
            "latest_command_stt_error": "",
            "latest_routed_command": "",
            "speech_audit_only": False,
            "speech_payload_count": 0,
            "speech_leak_count": 0,
            "command_response_tool": "",
        }
    latest_path, latest_data = latest_readable
    proof_path, data = latest_passed or latest_readable
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    input_data = data.get("input") if isinstance(data.get("input"), dict) else {}
    speech_audit = result.get("speech_audit") if isinstance(result.get("speech_audit"), dict) else {}
    ok = result.get("status") == "passed"
    relative = str(proof_path.relative_to(PROJECT_ROOT))
    latest_result = latest_data.get("result") if isinstance(latest_data.get("result"), dict) else {}
    latest_command_stt = latest_result.get("command_stt") if isinstance(latest_result.get("command_stt"), dict) else {}
    is_speech_audit_only = bool(input_data.get("speech_audit_only"))
    summary = {
        "ok": ok,
        "path": relative,
        "label": "passed" if ok else "needs attention",
        "command_transcript": str(result.get("command_transcript") or input_data.get("command_text") or ""),
        "routed_command": str(result.get("routed_command") or result.get("command_response_tool") or ""),
        "reply_similarity": float(result.get("reply_similarity") or 0.0),
        "latest_path": str(latest_path.relative_to(PROJECT_ROOT)),
        "latest_label": str(latest_result.get("status") or "unknown"),
        "latest_stt_provider": str(nested(latest_data, "input").get("stt_provider") or "auto"),
        "latest_command_stt_status": str(latest_command_stt.get("status") or "unknown"),
        "latest_command_stt_error": str(latest_command_stt.get("error") or ""),
        "latest_routed_command": str(latest_result.get("routed_command") or ""),
        "speech_audit_only": is_speech_audit_only,
        "speech_payload_count": int(speech_audit.get("payload_count") or 0),
        "speech_leak_count": int(speech_audit.get("leak_count") or 0),
        "command_response_tool": str(result.get("command_response_tool") or ""),
    }
    return summary


def shorten(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip() + "..."


def nested(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def git(args: list[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def git_sync_label(upstream: str) -> str:
    if not upstream:
        return "not published"
    counts = git(["rev-list", "--left-right", "--count", f"{upstream}...HEAD"])
    try:
        behind, ahead = [int(part) for part in counts.split()]
    except (ValueError, TypeError):
        return "published"
    if ahead == 0 and behind == 0:
        return "up to date"
    parts = []
    if ahead:
        parts.append(f"{ahead} ahead")
    if behind:
        parts.append(f"{behind} behind")
    return ", ".join(parts)


def render_report(context: dict[str, Any]) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="30">
  <link rel="icon" href="data:,">
  <title>Jarvis Master Report</title>
  {style_block()}
</head>
<body>
  <header>
    <h1>Jarvis Overnight Launch Report</h1>
    <p class="tagline">The voice loop moved from promise to first real test surface. This is the single page Leo needs tomorrow morning.</p>
    {pill_row(context, refresh_seconds=30)}
  </header>
  <main>
    {promise_section(context)}
    {spotlight_section(context)}
    {section("Shipped Since The Last Proven Build", context["shipped"], collapsed=True)}
    {section("Proof So Far", context["proof"], collapsed=True)}
    {section("What You Should Be Able To Do Tomorrow", context["try"])}
    {section("Still Risky Or Unfinished", context["risks"], risk=True, collapsed=True)}
    {supporting_section(context)}
  </main>
</body>
</html>
"""


def render_workboard(context: dict[str, Any]) -> str:
    tasks = [
        ("done", "Ship Hey Jarvis native listener", "Experimental app toggle and Speech framework pipeline are in place."),
        ("done", "Tighten fuzzy wake threshold", "Hey jervis still works, while short near-misses such as hey jars are rejected."),
        ("done", "Explain wake threshold", "Wake status now says the current 0.86 fuzzy threshold in the reply."),
        ("done", "Avoid wake-command double speech", "Direct Hey Jarvis commands now skip the wake-only prompt and go straight to capture."),
        ("done", "Ignore repeated wake-only phrases", "When already awake, Hey Jarvis alone keeps listening instead of becoming the command."),
        ("done", "Ignore wake-greeting echo", "The command listener ignores Jarvis's own Yes sir? prompt if the microphone hears it."),
        ("done", "Align typed echo simulation", "The wake lab ignores the same wake greeting echo before a real follow-up command."),
        ("done", "Add wake debug trace to chat export", "Copy Chat JSON includes the recent wake events and captured command text."),
        ("done", "Trace ignored wake events", "Copy Chat JSON records ignored repeated wake phrases and wake-greeting echoes."),
        ("done", "Expose wake detector scores", "Copy Chat JSON now includes score, threshold, phrase, window, and mode for wake events."),
        ("done", "Expose history payload preview", "Copy Chat JSON shows the filtered history Jarvis would send with the current command."),
        ("done", "Add context smoke", "A muted smoke script checks that Jarvis can use prior chat history for follow-ups."),
        ("done", "Add wake-threshold smoke", "An offline corpus proves fuzzy wake passes and near misses reject before mic testing."),
        ("done", "Add wake-lab corpus", "The wake lab has one-click exact, fuzzy, wake-only, and reject phrase checks."),
        ("done", "Ship wake audition lab", "Local page records samples, scores transcripts, and saves samples under runtime."),
        ("done", "Add menu-bar silence control", "Shut Up interrupts and mutes; Keep Blabbering unmutes."),
        ("done", "Mute optimistically", "The UI now treats Shut Up as active immediately while the backend confirms."),
        ("done", "Send mute first", "Shut Up now calls the mute endpoint before worker startup fallback can slow it down."),
        ("done", "Add menu-bar wake controls", "Start/Stop Hey Jarvis and Open Wake Test are reachable without the panel."),
        ("done", "Add permission quick action", "The panel has a Perms button for the exact macOS readiness check."),
        ("done", "Add wake-lab decision summary", "Runs now summarize detected count, best noisy pass, and next step."),
        ("done", "Clarify wake-lab controls", "Saved recordings use numbered steps; disposable recognition is labeled Live Transcript Only."),
        ("done", "Route Mac status through first model", "Device facts are read only after the first model selects diagnostics.device."),
        ("done", "Route app status through first model", "App list/status/running/focus/open requests now record model_tool_call routing."),
        ("done", "Expose dictation input policy", "Model-context diagnostics show how typed and speech-recognition text is fed to the models."),
        ("done", "Make app working lines specific", "Streaming app status says the app name when preview already has it."),
        ("done", "Fix final-answer speech coverage", "Normal final replies speak after the working line instead of staying silent."),
        ("done", "Protect streaming answer text", "Late status events can no longer replace visible answer text."),
        ("done", "Remove stale progress rows", "Synthetic Still working rows are removed as soon as the final answer is displayed."),
        ("done", "Reject overlapping typed turns", "If Jarvis is busy, a second typed command is not accepted into a competing turn."),
        ("done", "Add speech preview diagnostics", "Speech JSON now records the sanitized text_preview requested from TTS."),
        ("done", "Add speech-alignment trace", "Copy Chat JSON now flags when TTS preview text is too short to match the visible answer."),
        ("done", "Add closed-loop voice QA", "The harness compares Piper audio, STT transcript, Jarvis reply text, and spoken reply transcript."),
        ("done", "Add no-prompt voice QA mode", "Overnight runs can skip Apple Speech and fail closed through local STT only."),
        ("done", "Complete local STT model cache", "faster-whisper tiny.en now has model.bin and passes no-permission voice QA."),
        ("done", "Fail closed on empty local STT", "If local STT returns no transcript, the QA harness stops instead of routing a fake status command."),
        ("done", "Soak-test wake listener", "Jarvis 0.1.279 completed a 35-second app-bundle wake soak without a new crash report."),
        ("done", "Slow wake restart flicker", "Apple Speech restarts are spaced out and the third close restart pauses Hey Jarvis."),
        ("done", "De-duplicate wake UI snapshots", "Identical listener states no longer republish to the SwiftUI panel."),
        ("done", "Harden wake audio tap", "The Core Audio callback now writes through a non-actor sink to avoid the old concurrency trap."),
        ("done", "Pause wake restart storms", "If Apple Speech rapidly restarts the microphone engine, Jarvis pauses Hey Jarvis instead of flickering until it crashes."),
        ("done", "Pause silent Speech endings", "If Apple Speech ends immediately without hearing speech, Jarvis stops wake listening instead of restarting in the menu bar."),
        ("done", "Explain wake pauses visibly", "The chat now shows why Hey Jarvis paused instead of silently stopping."),
        ("done", "Add report loopback URLs", "The master report and workboard are reachable from the running Jarvis worker."),
        ("done", "Add menu report shortcut", "The menu bar can open the overnight report route directly."),
        ("working", "Next: real-world Leo testing", "Needs actual microphone, room noise, and false-wake feedback."),
    ]
    items = "\n".join(task_item(*task) for task in tasks)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="12">
  <link rel="icon" href="data:,">
  <title>Jarvis Overnight Workboard</title>
  {style_block()}
</head>
<body>
  <header>
    <h1>Jarvis Overnight Workboard</h1>
    {pill_row(context, refresh_seconds=12)}
  </header>
  <main>
    <section>
      <h2>Current Focus</h2>
      <p>Jarvis {e(context["version"])} is live with experimental Hey Jarvis, menu-bar mute, menu-bar wake controls, a refreshed wake lab, broader final-answer speech, and closed-loop voice QA. The remaining work is real-world listening quality.</p>
      <div class="meter"><div style="width: 91%"></div></div>
    </section>
    <section>
      <h2>Checklist</h2>
      <ul class="tasks">{items}</ul>
    </section>
    {supporting_section(context)}
  </main>
</body>
</html>
"""


def task_item(status: str, title: str, detail: str) -> str:
    checked = " checked" if status == "done" else ""
    badge = "Done" if status == "done" else "Working"
    spinner = '<span class="spin"></span>' if status == "working" else ""
    return (
        f'<li class="{e(status)}"><input type="checkbox" disabled{checked}>'
        f"<span><strong>{spinner}{e(title)}</strong><small>{e(detail)}</small></span>"
        f'<span class="badge">{badge}</span></li>'
    )


def pill_row(context: dict[str, Any], *, refresh_seconds: int) -> str:
    pills = [
        f"Auto-refresh: {refresh_seconds}s",
        f"Last updated: {context['updated']}",
        f"Live bundle: {context['bundle']}",
        f"Source commit: {context['commit']}",
        f"Branch: {context['branch']}",
        f"GitHub: {context['upstream'] or 'not published'} ({context['git_sync']})",
        f"Verification: {context['verification']['label']}",
        f"No-prompt: {context['no_prompt_verification']['label']}",
        f"Launch: {context['launch_mode']}",
    ]
    return '<div class="pills">' + "".join(f'<span class="pill">{e(pill)}</span>' for pill in pills) + "</div>"


def section(title: str, items: list[str], *, cards: bool = False, risk: bool = False, collapsed: bool = False) -> str:
    if cards:
        body = '<div class="grid">' + "".join(f'<div class="card">{e(item)}</div>' for item in items) + "</div>"
    else:
        cls = ' class="risk-list"' if risk else ""
        body = f"<ul{cls}>" + "".join(f"<li>{e(item)}</li>" for item in items) + "</ul>"
    if collapsed:
        return (
            f'<section class="collapsed-section"><details>'
            f'<summary><h2>{e(title)}</h2><span>{len(items)} items</span></summary>'
            f"{body}</details></section>"
        )
    return f"<section><h2>{e(title)}</h2>{body}</section>"


def promise_section(context: dict[str, Any]) -> str:
    promises = [
        ("Wakeable", "Hey Jarvis is now a real app-side test surface, not just a plan."),
        ("Interruptible", "Shut Up stops speech, and one-breath commands no longer double-speak the wake prompt."),
        ("Inspectable", "The report, workboard, wake lab, verifier, closed-loop voice QA, and chat JSON give us usable evidence."),
    ]
    cards = "".join(
        f"<div class=\"promise\"><strong>{e(title)}</strong><span>{e(body)}</span></div>"
        for title, body in promises
    )
    return f"<section><h2>Tonight's Product Promise</h2><div class=\"promise-grid\">{cards}</div></section>"


def spotlight_section(context: dict[str, Any]) -> str:
    latency = context.get("latency") if isinstance(context.get("latency"), dict) else {}
    latency_text = ""
    if latency.get("path"):
        latency_text = f" Current fast smoke max first visible {float(latency.get('max_first_visible_seconds') or 0):.3f}s."
    cards = [
        (
            "Try First",
            "Open Jarvis from the Dock, click Perms, read the permission tiles, then start Hey Jarvis only after Microphone and Speech Recognition are ready.",
        ),
        (
            "Best Proof",
            f"{context['verification']['label']} verifier, 445/445 Python tests, Swift self-tests, and closed-loop voice QA.{latency_text}",
        ),
        (
            "Honest Limit",
            "Room-noise wake reliability still needs Leo's microphone tests; the wake lab is ready for that data.",
        ),
    ]
    body = '<div class="grid spotlight">' + "".join(
        f"<div class=\"card\"><strong>{e(title)}</strong><span>{e(text)}</span></div>"
        for title, text in cards
    ) + "</div>"
    return f"<section><h2>Morning Snapshot</h2>{body}</section>"


def supporting_section(context: dict[str, Any]) -> str:
    rows = []
    for path, label in context["supporting"]:
        if path.startswith("http"):
            href = path
            display_path = path
        else:
            href = "../" + path.removeprefix("runtime/") if path.startswith("runtime/") else "../../" + path
            display_path = str(PROJECT_ROOT / path)
        rows.append(f'<li><a href="{e(href)}">{e(display_path)}</a> - {e(label)}</li>')
    return "<section><h2>Supporting Files</h2><ul>" + "".join(rows) + "</ul></section>"


def style_block() -> str:
    return """<style>
    :root {
      color-scheme: dark;
      --bg: #101216;
      --panel: #181c22;
      --panel-2: #202631;
      --text: #eef3f8;
      --muted: #aab5c4;
      --line: #313a47;
      --green: #55d68f;
      --blue: #7bbcff;
      --gold: #ffd166;
      --red: #ff8080;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.45 -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
    }
    header {
      padding: 26px 22px 18px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(180deg, #171b22, #101216);
    }
    main {
      width: min(1040px, calc(100vw - 28px));
      margin: 0 auto;
      padding: 18px 0 28px;
      display: grid;
      gap: 14px;
    }
    h1 {
      max-width: 1040px;
      margin: 0 auto 8px;
      font-size: clamp(28px, 4vw, 44px);
      line-height: 1.05;
      letter-spacing: 0;
    }
    .tagline {
      max-width: 1040px;
      margin: 0 auto;
      color: var(--muted);
      font-size: 17px;
    }
    .pills {
      max-width: 1040px;
      margin: 15px auto 0;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .pill, .badge {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 999px;
      padding: 5px 9px;
      color: var(--muted);
      white-space: nowrap;
    }
    section {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 15px;
      min-width: 0;
    }
    details { min-width: 0; }
    summary {
      cursor: pointer;
      list-style: none;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    summary::-webkit-details-marker { display: none; }
    summary::after {
      content: "Open";
      border: 1px solid rgba(123, 188, 255, 0.45);
      border-radius: 999px;
      padding: 4px 9px;
      color: var(--blue);
      font-size: 13px;
      flex: 0 0 auto;
    }
    details[open] summary::after { content: "Close"; }
    summary h2 { margin: 0; }
    summary span {
      color: var(--muted);
      margin-left: auto;
      white-space: nowrap;
    }
    details > ul {
      margin-top: 10px;
    }
    h2 { margin: 0 0 10px; font-size: 18px; letter-spacing: 0; }
    .promise-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }
    .promise {
      display: grid;
      gap: 7px;
      border: 1px solid rgba(123, 188, 255, 0.35);
      background: linear-gradient(180deg, #202836, #1a202a);
      border-radius: 8px;
      padding: 13px;
      min-height: 118px;
    }
    .promise strong,
    .spotlight strong {
      display: block;
      font-size: 17px;
    }
    .promise span,
    .spotlight span {
      color: var(--muted);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }
    .card {
      border: 1px solid var(--line);
      background: var(--panel-2);
      border-radius: 8px;
      padding: 12px;
      min-height: 112px;
      overflow-wrap: anywhere;
    }
    ul { margin: 0; padding-left: 19px; }
    li { margin: 6px 0; overflow-wrap: anywhere; }
    a { color: var(--blue); }
    .risk-list li { color: #ffd6d6; }
    .meter {
      height: 10px;
      border: 1px solid var(--line);
      background: #11151b;
      border-radius: 999px;
      overflow: hidden;
      margin-top: 12px;
    }
    .meter > div {
      height: 100%;
      background: linear-gradient(90deg, var(--green), var(--blue));
    }
    .tasks {
      list-style: none;
      padding: 0;
      display: grid;
      gap: 8px;
    }
    .tasks li {
      display: grid;
      grid-template-columns: 22px minmax(0, 1fr) auto;
      gap: 10px;
      align-items: start;
      border: 1px solid var(--line);
      background: var(--panel-2);
      border-radius: 8px;
      padding: 9px;
    }
    input[type="checkbox"] {
      width: 16px;
      height: 16px;
      accent-color: var(--green);
      margin-top: 2px;
    }
    small { display: block; color: var(--muted); margin-top: 2px; }
    .done .badge { color: var(--green); border-color: rgba(85, 214, 143, 0.45); }
    .working .badge { color: var(--gold); border-color: rgba(255, 209, 102, 0.45); }
    .spin {
      width: 14px;
      height: 14px;
      border: 2px solid rgba(123, 188, 255, 0.25);
      border-top-color: var(--blue);
      border-radius: 50%;
      animation: spin 0.9s linear infinite;
      display: inline-block;
      vertical-align: -2px;
      margin-right: 6px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    @media (max-width: 840px) { .grid, .promise-grid { grid-template-columns: 1fr; } }
  </style>"""


def e(value: Any) -> str:
    return html.escape(str(value), quote=True)


if __name__ == "__main__":
    raise SystemExit(main())
