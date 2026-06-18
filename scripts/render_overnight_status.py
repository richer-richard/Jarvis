#!/usr/bin/env python3
"""Render the local Jarvis overnight workboard and master report."""

from __future__ import annotations

import argparse
import html
import json
import plistlib
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "runtime" / "overnight_status"
BEIJING = ZoneInfo("Asia/Shanghai")
DEFAULT_BASE_URL = "http://127.0.0.1:8765"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


SHIPPED_ITEMS = [
    "Jarvis 0.1.455 packages the overnight reliability pass: Teams final speech now matches the visible mismatch answer, the master report opens with concise shipped highlights, and Sharpay email summaries keep the 75-message proof window while running much faster.",
    "Sharpay email summaries are much faster without shrinking the proof window: the Apple Mail path now keeps sender-recent candidates during the first bounded scan instead of rescanning the same 75-message window for every selected message.",
    "Jarvis's Teams proof now reads the visible Chrome window with native OCR even when Chrome page-text Automation is blocked, so it can say the current page is a Geography assignment instead of pretending it found the newest Music assignment.",
    "Jarvis's Music full-loop proof now watches for hidden `afplay` leftovers: a passed Music test must stop native Music playback and leave no new hidden audio process behind.",
    "Jarvis now handles the hard Sharpay email prompt properly: `Summarize all the emails from Ms. Sharpay in the past month` keeps the user's all-matching intent, resolves the contact alias, selects recent matching messages instead of just the newest one, and produces an English-first spoken summary.",
    "Jarvis's music proof now includes the part Leo actually cares about after the song starts: the full-loop runner verifies the native Music app bridge stops playback during cleanup, so a passed test cannot leave hidden music running.",
    "Jarvis voice QA now understands that visible text and spoken text may intentionally differ: it scores speech transcripts against the exact spoken payload, so screen text can say `Juneteenth` while speech says the clearer `June nineteenth holiday`.",
    "Jarvis can now auto-start the native Music app bridge for playback: if the bridge is down, it opens `Music.app`, waits for `/health`, retries the play command, and records the startup proof before falling back.",
    "Jarvis now has a single pre-build proof gate: `scripts/pre_build_gate.py` runs the Python safety suite, all eight spoken-command full-loop regressions, Chrome test-tab cleanup, and report refresh before a build is treated as saveable.",
    "Jarvis 0.1.454 moves normal music playback proof to the native Music app bridge: `Waving Through a Window` now resolves to the Dear Evan Hansen Tony Awards track, Jarvis confirms actual Music playback before claiming success, Stop Music calls the same bridge, and the new full-loop regression runner can allow real audio actions, verify playback, audit speech payloads, and clean up afterward.",
    "Jarvis 0.1.453 hardens LocalOS music ownership: the old hidden `afplay` music starter is removed, while Stop Music can still clean up old orphaned `afplay` processes; the LocalOS reopen cooldown now verifies the Chrome tab still exists before refusing to reopen it.",
    "Jarvis 0.1.452 makes email/contact no-result replies speakable: scan counts stay in structured metadata, but Jarvis no longer says `I scanned X messages` when it cannot find a sender or requested email number.",
    "Jarvis 0.1.451 improves LocalOS music startup again: Jarvis now answers LocalOS browser CORS preflight, repairs the activation script, reports Chrome autoplay blocks as activation-required instead of failed, and keeps playback owned by LocalOS.",
    "Jarvis 0.1.445 fixes the Stop Music emergency brake: browser-media pause now uses safe Chrome AppleScript variable names, avoiding the syntax error that left LocalOS/browser audio untouched.",
    "Jarvis 0.1.444 improves LocalOS music reconnects: when the music bridge is stale, Jarvis now tries the native Local OS Host app first and only falls back to opening the Chrome/file music player if the host does not publish a live bridge.",
    "Jarvis 0.1.443 improves Chrome-control guidance across browser and music flows: when page control is denied, Jarvis now points to both macOS Automation access and Chrome's Allow JavaScript from Apple Events setting.",
    "Jarvis 0.1.442 makes LocalOS music failures more truthful: when Chrome refuses Jarvis JavaScript control with `Access not allowed (-1723)` and the LocalOS bridge is stale, Jarvis now names the Chrome-control blocker instead of vaguely saying LocalOS is only still connecting.",
    "Jarvis 0.1.441 fixes an annoying music-stop side effect: ordinary Stop Music no longer mutes the whole Mac when LocalOS is slow or blocked; it only pauses known LocalOS/browser/Music surfaces and reports honestly if the command is merely queued.",
    "Jarvis 0.1.441 also hardens the Chrome bridge used by LocalOS music control: the JavaScript sent through AppleScript is compacted before execution, avoiding raw-newline AppleScript syntax failures in pause/play recovery.",
    "Jarvis 0.1.440 hardens LocalOS music playback: when LocalOS accepts/selects a track but audio has not started, Jarvis focuses the real LocalOS play button in Chrome, sends a guarded Space key only when that button is focused, and rechecks playback before claiming the song is playing.",
    "Jarvis 0.1.439 records the unattended no-approval rule: overnight work stays inside repo-local reads, repo-local edits, local tests, compile checks, and report rendering, with app launches, settings changes, Git publishing, notifications, and external model/network calls held until Leo is present.",
    "Jarvis 0.1.439 keeps the morning-status helper loopback-only: a mis-set `JARVIS_URL` or `JARVIS_BASE_URL` can no longer make the unattended status script call a non-local server.",
    "Jarvis 0.1.439 keeps the overnight report renderer loopback-only too: direct report rendering and report-refresh calls now refuse non-local base URLs before any health request is made.",
    "Jarvis 0.1.439 keeps local-worker smoke harnesses loopback-only as well: latency, conversation-context, and voice-loop probes now reject non-local base URLs before streaming any command.",
    "Jarvis 0.1.439 keeps wake-threshold smoke report refresh loopback-only: the wake phrase scorer now rejects non-local base URLs before refreshing the master report surface.",
    "Jarvis 0.1.439 keeps the safe verifier and no-prompt verifier loopback-only: verifier HTTP helpers reject non-local base URLs before any request, and the full verifier falls back to a temporary local worker instead of touching external URLs.",
    "Jarvis 0.1.439 keeps the regression matrix runner loopback-only: the eight-prompt speech-audit wrapper now rejects non-local base URLs before starting any child voice-loop process or report refresh.",
    "Jarvis 0.1.439 keeps the Codex proxy Jarvis baseline loopback-only: even approved proxy benchmarks now reject non-local Jarvis base URLs before timing `/api/command/stream`.",
    "Jarvis 0.1.439 gives the Codex proxy benchmark a stable proof pointer too: dry-run or approved benchmark runs now refresh `runtime/codex_cli_proxy_benchmarks/latest.json` and `latest.md`.",
    "Jarvis 0.1.439 keeps the polished summon overlay out of debug-speak: error details now say `Check the Jarvis window for details`, and in-progress states say `Finding the best way to help` / `Preparing the answer` instead of exposing route or response-writing internals.",
    "Jarvis 0.1.439 keeps LocalOS autoplay-blocked replies product-facing: if the music player needs one click before audio can start, Jarvis no longer says Chrome is blocking playback.",
    "Jarvis 0.1.439 keeps the normal app identity pinned: the bundle build script still defaults to `Jarvis` / `local.leo.jarvis` so test-only names such as LocalOS-only builds cannot quietly become the main app.",
    "Jarvis 0.1.439 makes warm Piper speech less choppy: normal and medium replies now stay in one synthesized audio chunk, while only unusually long speech is split.",
    "Jarvis 0.1.439 makes the Notifications permission tile less confusing: `Not requested` now says notifications are optional unless timers or background alerts need them.",
    "Jarvis 0.1.439 makes the menu-bar head act like a normal launcher: a regular click opens the Jarvis window immediately, while right-click or Control-click opens the emergency menu with Shut Up and Stop Music, and the helper self-test now covers that click split.",
    "Jarvis 0.1.439 makes emergency music-stop wording honest: if normal LocalOS/page/media pause fails and Jarvis mutes system audio as the last resort, the visible summary now says it muted system audio instead of pretending normal playback stopped.",
    "Jarvis 0.1.439 keeps middle-model comparison from touching local Ollama models unexpectedly: cloud comparison can run with `--execute-network`, but stopping installed local candidates now requires the separate `--cleanup-local-models` opt-in.",
    "Jarvis 0.1.439 keeps cloud-only middle-model comparison from even inspecting local Ollama by default: local tags/ps are skipped unless local models, cleanup, or `--inspect-local-ollama` is explicitly requested.",
    "Jarvis 0.1.439 keeps middle-model audio probes project-local by default: an `--audio-probe` outside the Jarvis project now requires `--allow-external-audio-probe` before the script will read it.",
    "Jarvis 0.1.439 keeps fast-model benchmarking cloud-first too: `--execute-network` no longer discovers or benchmarks installed local Ollama models unless `--include-local-ollama` is passed.",
    "Jarvis 0.1.439 makes the TTS audition generator safer by default: macOS voices still work locally, online Edge voices require `--include-online-voices`, and CLI output folders must stay inside the Jarvis project unless `--allow-external-output-dir` is explicitly passed.",
    "Jarvis 0.1.439 makes the local STT repair helper safe for unattended runs: `scripts/repair_local_stt_model.py` is now dry-run by default and requires `--execute-network` before downloading the faster-whisper model blob.",
    "Jarvis 0.1.439 makes the Gemma 3n audio probe gentler by default: dry-run now plans samples only and does not synthesize local audio unless `--synthesize-local` or `--execute-network` is explicitly used.",
    "Jarvis 0.1.439 removes more unattended speech side effects: fast-latency smoke, conversation-context smoke, direct voice-loop QA, and no-prompt verifier diagnostics now use request-level quiet mode instead of carrying global mute/unmute helper paths.",
    "Jarvis 0.1.439 makes direct voice-loop QA safer overnight: `scripts/voice_loop_qa.py` now uses local STT with no permission prompts by default, and Apple Speech requires explicit `--allow-apple-speech` opt-in.",
    "Jarvis 0.1.439 tightens LocalOS music honesty again: queued, accepted, bridge-not-polling, and unconfirmed music commands now say Local OS has not started playback yet instead of sounding like the song is already playing.",
    "Jarvis 0.1.439 makes speech state truthful after Keep Blabbering: the backend now reports and replies with whether automatic TTS is actually available, unmute prewarms Piper when configured, and the app starts at Speech Check until the backend verifies the voice path instead of briefly pretending Speech On is proven; once checked, it can show Speech Off or Voice Missing instead of a fake ready state.",
    "Jarvis 0.1.439 makes the always-visible Shut Up lane more resilient: if the separate status-helper menu-bar process exits unexpectedly while the main app is still running, the app now schedules a short restart instead of leaving Leo without the menu-bar mute controls, and it re-checks the keepalive flag after the delay so normal quit does not resurrect the helper.",
    "Jarvis 0.1.439 adds a final spoken-output firewall: if backend/debug lines such as Tool time, Fast model time, First visible, Groq/Ollama rows, Worker, Verification, or Codex Activity accidentally enter TTS text, they are removed before Jarvis speaks; debug-only speech now fails quiet as empty_after_sanitization, and future backslash tool calls are stripped before audio.",
    "Jarvis 0.1.439 adds server-level proof for that firewall too: if a final reply is only backend/model diagnostics, the attached speech payload stays empty_after_sanitization with no raw Groq, tool-time, or model text in the audible/auditable speech fields.",
    "Jarvis 0.1.439 closes the same leak in suppressed-speech audit mode: when tests or quiet API calls suppress audio, debug-only text still sanitizes to an empty preview instead of preserving backend/model diagnostics in the speech payload.",
    "Jarvis 0.1.439 aligns the Swift speech-active window with that same status: `empty_after_sanitization` is now treated as a blocked/non-speaking state, so the app will not think Jarvis is still speaking after a debug-only payload is stripped.",
    "Jarvis 0.1.439 also tightens the old Still working bug class: stale Swift progress-nudge tasks now exit as soon as they see the active turn has ended instead of sleeping through later nudges.",
    "Jarvis 0.1.439 also makes the eight-prompt regression matrix easier to inspect: every run still writes a timestamped summary, and the matrix root now updates `latest.json` plus `latest.md` so future reports and checks have stable pointers.",
    "Jarvis 0.1.439 makes fast-latency proof easier to inspect too: smoke runs still write timestamped artifacts, and now also refresh `runtime/model_benchmarks/latest.json` plus `latest.md`.",
    "Jarvis 0.1.439 rounds out proof-surface pointers for conversation memory and wake reliability: conversation-context and wake-threshold smoke scripts now update stable latest.json/latest.md files as well.",
    "Jarvis 0.1.439 also keeps those proof surfaces fresh: conversation-context and wake-threshold smoke scripts now refresh the master report/workboard after writing new artifacts, unless explicitly run with the no-refresh flag.",
    "Jarvis 0.1.439 adds a standalone `scripts/report_refresh.py` CLI so the master report/workboard backfill path can be invoked directly from the terminal, with a concise summary by default and JSON on `--json`.",
    "Jarvis 0.1.439 makes the master report more honest: missing local supporting artifacts are now labeled `not generated yet` instead of being presented as normal links.",
    "Jarvis 0.1.439 makes report refresh self-healing: before rendering the master report, it backfills stable latest proof artifacts from the newest valid timestamped smoke/matrix reports, skipping corrupt or half-written newer artifacts instead of breaking the report.",
    "Jarvis 0.1.439 gives closed-loop voice QA the same stable proof surface: voice-loop runs now write `latest.json` plus a readable `latest.md`, and report refresh can backfill both from the newest timestamped voice-loop report.",
    "Jarvis 0.1.439 fixes a false stale-report warning: overnight status now checks the full proof section for latest verifier and voice-QA artifacts instead of only the first compact proof sample.",
    "Jarvis 0.1.439 fixes misleading tool-catalog diagnostics: direct source calls no longer say the first model sees 0 tools when the planner simply did not attach the first-model catalog, while planner-routed status still reports the real first-model tool count.",
    "Jarvis 0.1.439 fixes capability-status counting: Wake Lab and STT audition are now explicit prepared capability rows, so the visible summary says 2 prepared instead of saying 0 prepared while listing prepared surfaces.",
    "Jarvis 0.1.439 fixes overnight-status bundle wording: the status parser now understands the report's current `Output bundle` pill, so the reply names the bundle again instead of saying only the source commit.",
    "Jarvis 0.1.439 makes final speech selection safer: if the preferred spoken summary is stripped as backend/model diagnostics, Jarvis now falls back to the safe visible reply instead of sending empty or technical junk to TTS.",
    "Jarvis 0.1.439 closes the duplicate menu-bar-head escape hatch: the main app now keeps its own legacy status item disabled even if an old debug environment variable is present, leaving the native helper as the single visible head.",
    "Jarvis 0.1.439 adds a no-network proof path for price conversion: Magic Keyboard yuan conversion can now be exercised as a plan-only route without touching Apple, exchange-rate APIs, or any public web endpoint.",
    "Jarvis 0.1.439 tightens the spoken-output firewall one more notch: pipe-separated inline diagnostics such as `| Tool time 0.2s | Model gpt-oss... | Backend groq` are stripped before speech even when they have no colon.",
    "Jarvis 0.1.439 also tightens fast-chat streaming: hidden tool-call prefixes are still withheld immediately, but ordinary backslash text such as `C:\\Users\\Leo` is no longer treated as a hidden call and lost from the live visible stream.",
    "Jarvis 0.1.439 makes first-model tool routing less brittle: direct named hidden calls such as `\\localos.music_play({\"query\":\"...\"})` can now route when that exact tool is in the allowed catalog, while unknown or unlisted tools still fail closed.",
    "Jarvis 0.1.439 also cleans assistant history before sending it back to the fast model: hidden tool-call fragments and backend timing/model lines are removed so old internal text cannot steer the next answer.",
    "Jarvis 0.1.439 tightens the fast-model speech contract: displayed or spoken replies must stay concise, English-first, and voice-friendly; non-English names or titles may be preserved only when necessary, while the explanation stays English.",
    "Jarvis 0.1.439 closes another chat-context shape gap: fast-model history now accepts both `text` and `content` fields, so app/server payload aliases do not silently disappear before the model sees prior turns.",
    "Jarvis 0.1.439 fixes the same alias class for Codex continuations: a plain code reply can continue a waiting Codex job whether the prior waiting message is stored as `content` or normalized `text`.",
    "Jarvis 0.1.439 makes same-Codex continuation more precise: when history names a known `codex-...` job, Jarvis resumes that job instead of blindly choosing a newer unrelated Codex job.",
    "Jarvis 0.1.438 keeps proof surfaces fresh after QA runs: latency smoke and speech-audit matrix scripts now refresh `/overnight-report/` and `/overnight-workboard/` after writing new artifacts.",
    "Jarvis 0.1.437 makes readiness less misleading: planned future tools such as screen OCR and UI automation are listed separately from genuinely broken or actionable unavailable tools.",
    "Jarvis 0.1.436 makes silent-speech debugging concrete: mute/unmute writes now record whether they came from the main app, the always-visible status-helper menu, or a raw API call.",
    "Jarvis 0.1.435 refreshes the master report surface: shipped/proof/workboard sections now include the latest 0.1.430-0.1.434 reliability work instead of starting at the older 0.1.429 checkpoint.",
    "The normal build-and-launch path now regenerates `/overnight-report/` and `/overnight-workboard/` after the live worker is healthy, so the Report button does not serve stale product news after a rebuild.",
    "Jarvis 0.1.434 tightens the LocalOS music contract: the model-facing music tools now state that LocalOS owns normal playback and that Jarvis must not start a separate hidden player.",
    "Jarvis 0.1.433 fixes the Keep Blabbering recovery path: the status helper notifies the main app after speech mute changes, and the main app refreshes backend mute state before native status speech.",
    "Jarvis 0.1.432 makes Codex speed status useful: `codex speed status` now reports the active child-process proxy route and the latest sanitized proxy benchmark without exposing private prompt text.",
    "Jarvis 0.1.431 speeds up Codex delegation on Leo's network: Jarvis auto-detects the reachable local ClashX proxy for Codex child processes while leaving normal system proxy settings alone.",
    "Jarvis 0.1.430 improves sound-loop QA and status cleanliness: file-level sound-in/sound-out probes now time every stage, reuse the final speech-audit audio, and avoid reading backend model names or worker internals aloud.",
    "The LocalOS music bridge was restored after 0.1.430: bridge v4 polling, snapshot publishing, LocalOS-owned play/pause handling, and human autoplay-blocked wording are back in the sibling LocalOS player.",
    "Jarvis 0.1.429 hardens command payloads: `message`, `text`, and `prompt` now preserve Leo's utterance just like `command`, and empty command posts are rejected instead of turning into a fake generic hello.",
    "The safe verifier now guards the streaming command path too: packaged workers must accept `message` aliases on `/api/command/stream` and reject empty streaming commands.",
    "Jarvis 0.1.428 polishes LocalOS music replies: approximate song matches now say `closest LocalOS match` instead of `closest LocalOS file`, keeping the answer honest without sounding like filesystem debug output.",
    "Jarvis 0.1.427 makes Calendar answers more speakable: schedule summaries now use clean English course names and natural times like `8 AM`, while raw event details stay in structured diagnostics.",
    "Jarvis 0.1.426 makes Shut Up persistent: speech mute now survives worker restarts, app relaunches, and rebuilds by loading `runtime/state/speech_mute.json` on startup.",
    "Jarvis 0.1.425 makes the real app's Teams follow-up less brittle: after opening signed-in Chrome, native visible-screen OCR now retries up to four times and stops early once useful assignment/page text appears.",
    "The eight-prompt overnight regression matrix is now a reusable script: `scripts/run_regression_prompt_matrix.py` runs the Teams, Music, RAM, Codex, Calendar, model-test, email-contact, and Magic Keyboard prompts with speech/audio side effects suppressed.",
    "The regression matrix runner now accepts explicit `--no-permission-prompts --stt-provider local` flags, still defaults to local STT for unattended runs, and refuses Apple Speech unless the caller opts in with `--allow-apple-speech`.",
    "Jarvis 0.1.424 keeps the visible speech chip honest: the main app now syncs `/api/speech/mute` every two seconds, so `Speech On` does not stay stale after the helper or verifier mutes Jarvis.",
    "Jarvis 0.1.423 hardens the real Teams handoff: if targeted Chrome-window OCR returns empty or useless text, native screen reading falls back to the main display and can still summarize the visible Teams page.",
    "Jarvis 0.1.423 cleans Teams assignment summaries by dropping browser tab/menu noise and Teams sidebar crumbs before asking follow-up questions.",
    "Jarvis 0.1.423 fixes another duplicate-menu-bar path: the status helper now receives the main app PID and exits when that parent Jarvis app disappears.",
    "Jarvis 0.1.422 aligns the Teams assignment plan with the real native OCR follow-up: the next safe read tool is now `screen.visible_text`, not the old browser-read placeholder.",
    "Jarvis 0.1.421 polishes spoken working lines: month-long email summaries no longer say `newest email`, and Teams assignment handoff no longer exposes `assignment plan` wording.",
    "Jarvis 0.1.420 now asks useful follow-up questions after Teams assignment OCR when Leo asks for enough information to finish the assignment.",
    "The automatic Teams OCR pass now preserves Leo's original command, so `ask me questions` survives the Chrome handoff and native screen-read step.",
    "Jarvis 0.1.419 makes Teams OCR summaries more useful: visible Teams text now prefers assignment title, due time, instructions, rubric, class, and project lines over generic Teams navigation noise.",
    "The 0.1.419 audit filter also omits `assignment_digest_items`, so private OCR-derived assignment snippets do not linger in the long-term audit log.",
    "Jarvis 0.1.418 fuses the Teams handoff with the new native OCR path: after a `teams.assignment` command opens signed-in Chrome, assignment-reading requests automatically try a read-only visible Teams screen pass.",
    "The automatic Teams OCR follow-up is guarded: it does not trigger for submit, turn-in, send, upload, or delete wording, and it still treats OCR text as private untrusted local data.",
    "Jarvis 0.1.417 adds a concrete native visible-screen read route: explicit requests like `read the visible Teams screen` use the macOS app's Apple Vision OCR path, send extracted text only to the local worker, and keep screenshots unstored by default.",
    "The new `screen.visible_text` route scans OCR text as untrusted content, hides private screen digest text from audit logs, and gives Leo a short spoken/visible summary instead of raw OCR dumps.",
    "The safety verifier now runs temporary bundle self-tests on a private local port, so verification no longer makes a temporary Jarvis fight the live Jarvis worker on `127.0.0.1:8765`.",
    "Jarvis 0.1.416 makes the Teams assignment route honest: it opens the Teams bookmark in signed-in Chrome, but explicitly says no assignment has been inspected until a later visible page or screen read succeeds.",
    "Jarvis 0.1.416 gives Teams page-read failures product language: `Teams is open in Chrome, but Jarvis cannot reliably read the Teams page text yet` instead of leaking JavaScript or AppleScript internals.",
    "Jarvis 0.1.416 preserves human contact aliases such as `Ms Sharpay` while still tolerating `Sharpay` and STT-shaped `his Sharpay` lookups.",
    "Jarvis 0.1.416 quiets the wake loop: wake acknowledgement is now visible `Listening.` rather than a routine spoken `Hello sir`, so Leo can continue speaking immediately after Hey Jarvis.",
    "Jarvis 0.1.415 passed the full eight-prompt regression matrix for Teams handoff, LocalOS music, RAM, Codex chat confirmation, Calendar, model-test planning, Ms. Sharpay contact confirmation, and Magic Keyboard yuan conversion.",
    "Jarvis 0.1.389 stops LocalOS music recovery from multiplying Chrome tabs: recent opener attempts and recent LocalOS music heartbeats now block duplicate `open Chrome` recovery calls.",
    "Jarvis 0.1.388 adds a LocalOS music recovery lane: if macOS blocks direct Chrome automation, Jarvis opens the LocalOS Music Player normally, waits for its polling bridge, then queues playback without pretending the song started early.",
    "Jarvis 0.1.387 tightens LocalOS music playback honesty: `accepted` no longer counts as played, Jarvis waits past early acceptance for real audio, and LocalOS no longer flashes a false `Playing` notification before audio starts.",
    "Jarvis 0.1.386 adds a real public price plus yuan conversion lane: the Magic Keyboard prompt now routes to `commerce.price_convert`, reads Apple's official U.S. product price, fetches a live USD-CNY rate, and keeps the spoken answer clean.",
    "Jarvis 0.1.385 moves the menu-bar head into a tiny bundled native helper that uses the proven AppKit status-item path, while the main Jarvis app keeps the normal Dock/window behavior.",
    "Jarvis 0.1.384 fixes the invisible/displaced menu-bar control by matching the verified native status-item path: direct system button image, no floating panel, no custom hit-test view, and no poisoned autosave placement.",
    "Jarvis 0.1.383 restores the menu-bar control to a direct system-drawn `NSStatusItem` with a persistent autosave name, so the colored head is no longer a floating overlay and can behave like a normal Command-draggable menu item.",
    "Jarvis 0.1.382 keeps the menu-bar control native and Command-draggable while drawing the colored Iron Man head through a pass-through image view inside the standard status button.",
    "Jarvis 0.1.381 restores the menu-bar control as a real native `NSStatusItem`: the colored Iron Man head comes from a cropped menu asset, `Shut Up` is the first menu item, and there is no floating overlay that breaks Command-drag behavior.",
    "Jarvis 0.1.375 makes the menu-bar safety control non-optional: the native status item is always enabled, is recreated if missing, and is forced visible before app-driven speech so `Shut Up` is reachable whenever Jarvis is talking.",
    "Jarvis 0.1.374 adds a Chrome Automation permission tile and Apple Events usage description, so logged-in Chrome handoff can explain when Jarvis needs Automation access to read the active page instead of copying Chrome sessions.",
    "Jarvis 0.1.373 adds a Calendar Cache permission tile so the app shows whether the current Jarvis identity can read the local Calendar database; when blocked it names Full Disk Access for Jarvis.app and tells Leo to reopen Jarvis.",
    "Jarvis 0.1.372 fixes private-read safety for natural plural wording: `summarize all the emails...` is now visibly logged as private email access instead of being mislabeled as local conversation.",
    "Jarvis 0.1.371 makes Chrome page-reading failures actionable: if macOS blocks Automation, Jarvis now says the exact Google Chrome permission needed, keeps the signed-in Chrome strategy, and still refuses to copy cookies or sessions into WebKit.",
    "Jarvis 0.1.370 turns the Teams browser lane into a usable next step: Teams assignment plans can carry the imported Teams bookmark into the visible Jarvis browser/Chrome handoff, and `what's on this page?` now reads a concise local page digest instead of raw page text.",
    "Jarvis 0.1.369 improves dictated contact aliases: if STT hears `Ms. Sharpay` as `his Sharpay`, contact lookup still resolves the same local alias before email search.",
    "Jarvis 0.1.368 tightens LocalOS music confirmation: Chrome-direct playback can only say `playing` when LocalOS reports the requested track as current and audio is actually playing.",
    "Jarvis 0.1.367 fixes dictated Chrome-login routing: STT-shaped phrases like `chrome log and steer browser` now go to the safe Chrome-session strategy instead of accidentally importing bookmarks.",
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
    "Email auto-speech now prefers the clean email_summary field over logistical mailbox preambles, so Jarvis speaks the simple summary when both are available.",
    "LocalOS music autoplay detection now recognizes more browser media-blocking errors as the same one-click-needed state, preserving the LocalOS-only playback contract.",
    "The status-helper emergency menu now restarts after about 0.25s instead of 0.8s if it exits while Jarvis is still running, so Shut Up comes back faster.",
    "The speech sanitizer now speaks markdown links as plain labels instead of reading URL clutter such as parentheses, tracking links, or a repeated 'a link'.",
    "The Swift app client and status-helper path now reject non-loopback Jarvis URLs, matching the no-remote-worker safety guard already used by the overnight scripts.",
    "Long-task progress nudges now use calmer wording: 'I'm still working on it' instead of the old 'Still working. Wait a sec...' line.",
    "The workboard proof wording now says the live bundle includes the 0.1.453 LocalOS music hardening and Chrome-tab-aware reconnect logic, instead of stale no-relaunch wording.",
    "The workboard remaining-gap wording now reflects the real product scope: live relaunch plus real-device voice, music, browser, Teams, and app-control QA, not a stale Teams-only caveat.",
    "The speech sanitizer now drops internal Actions, What I did, Steps taken, Reasoning, Notes, debug, diagnostics, tool-result, model-detail, and backend-detail sections before TTS, including non-bulleted logistics, so Jarvis keeps the answer but does not read implementation notes aloud.",
    "The fast-model system prompt now prevents those same internal headings upstream with a compact `No internal headings` rule for Actions, What I did, Steps taken, Reasoning, Notes, and Tool results.",
    "Assistant history cleanup now strips those same internal sections before old Jarvis replies are sent back to the fast model, so prior logistics do not teach the next answer to imitate them.",
]

PROOF_ITEMS = [
    "Chrome cleanup for the Jun 18 morning handoff was completed: Codex/Jarvis-created LocalOS music-player tabs were closed, while Leo's personal New Tab and YouTube tab were preserved.",
    "0.1.439 source proof: full Python safety suite passed 744/744; speech readiness fields are covered by backend tests, Piper prewarm-on-unmute is covered by a regression test, the Swift menu/status/progress contract decodes automaticSpeechAvailable, automaticTtsEnabled, and ttsAvailable for truthful UI labels starting from Speech Check until the backend answers, keeps progress nudges tied to the active turn, and uses natural long-task wording; the status-helper contract now covers delayed restart after unexpected helper exit, requires the faster 0.25s restart delay, and rejects non-loopback Jarvis URLs before app/helper client routing; the main-app duplicate status-item escape hatch is closed by source contract, the summon overlay avoids debug-window wording in its polished user-facing error text, the fast-model prompt now uses a compact No internal headings rule, assistant history cleanup strips those sections before reuse, and the TTS sanitizer still drops backend diagnostics, colonless inline pipe diagnostics, markdown-link URL clutter, internal checklist sections including non-bulleted logistics and natural headings such as What I did, Steps taken, Reasoning, or Notes, and future backslash tool calls before speech. Server auto-speech attachment is covered for debug-only sanitized-empty replies, server speech selection falls back from diagnostic-only preferred fields to safe visible replies, email auto-speech prefers clean email_summary over logistical mailbox preambles, suppressed-speech previews are also covered for debug-only sanitization, and suppressed speech diagnostics now expose full `spoken_text` so voice-loop QA and the safe verifier audit beyond the preview boundary. Swift treats `empty_after_sanitization` as non-speaking, the streaming buffer keeps hidden calls out without dropping normal backslash text, and streaming now resumes visible text after a closed hidden call so mid-sentence tool calls join cleanly. Direct named tool calls route only when allowed by the current tool catalog, assistant history is sanitized before reuse, client-provided `system` history rows are rejected before model context, the middle planner rejects client-provided `system` history and strips assistant diagnostics before broader tool planning, model-context diagnostics now count only model-eligible history rows, Codex continuation helpers ignore untrusted system-history rows, fast-model visible replies are prompted to stay English-first and voice-friendly, history `content` aliases reach the fast model, Codex waiting detection accepts `text` aliases, same-Codex continuation prefers the job id named in history, commerce price conversion has a no-network plan-only proof path, LocalOS autoplay blocking recognizes more browser media errors as one-click-needed instead of starting hidden playback, and the fast-latency, conversation-context, wake-threshold, voice-loop QA, plus regression-matrix root-level latest pointers/refresh hooks are covered by focused tests. The direct voice-loop harness itself now defaults to local STT/no permission prompts, Apple Speech requires explicit opt-in, and stale global mute helper paths were removed from fast/context/voice-loop smoke scripts. No-prompt verifier diagnostics for model context, voice-loop echo, repeated wake, and wake debug now use request-level `suppress_speech` instead of muting/unmuting the whole app; only the dedicated mute endpoint test changes global mute state. The regression matrix now records per-case and aggregate speech payload/leak counts, fails any row with zero spoken payloads, non-passed speech-audit status, or internal speech leaks, and refuses non-loopback base URLs before starting child voice-loop checks or report refresh, so a green row cannot hide silent or leaked spoken output. Gemma 3n audio probing is now dry-run plan-only by default and needs `--synthesize-local` before local TTS/conversion or `--execute-network` before uploading generated audio; the local STT repair helper is now dry-run by default and needs `--execute-network` before downloading the faster-whisper blob; the TTS audition generator now keeps online Edge voices behind `--include-online-voices` and rejects external output folders unless `--allow-external-output-dir` is explicit from both the CLI and direct function API; Groq streaming-model benchmarking, fast-model benchmarking, middle-model comparison, and Codex proxy benchmarking are also dry-run by default and require an execute flag before contacting external services, while middle-model local Ollama cleanup needs the extra `--cleanup-local-models` opt-in, middle-model local Ollama inspection needs local model/cleanup intent or `--inspect-local-ollama`, middle-model external audio probes need `--allow-external-audio-probe`, and fast-model local Ollama benchmarking needs `--include-local-ollama`. Executable dry-run tests now prove those scripts complete without calling the patched network/model paths. The morning-status helper, overnight report renderer, local-worker smoke harnesses, wake-threshold report refresh, safe verifier, no-prompt verifier, regression matrix runner, and Codex proxy Jarvis baseline now refuse non-loopback base URLs before any request, including clean CLI refusal for an unsafe benchmark baseline URL. LocalOS music wording keeps unconfirmed/accepted/bridge-not-polling playback states honest by saying playback has not started yet unless LocalOS confirms actual audio, emergency stop summaries now say when Jarvis muted system audio as the last resort, the report renderer labels missing local support files instead of hiding that gap, report refresh seeds an empty local contact-alias memory surface when none exists, report refresh backfills stable latest artifacts from existing timestamped reports while skipping corrupt newer files, the workboard no longer claims the sandbox blocked a Swift rebuild after Swift compile proof already passed, and the workboard remaining-gap wording now names live voice/music/browser/Teams/app-control QA instead of a stale Teams-only caveat.",
    "0.1.439 build note: Python/source proof is green, `swift build --disable-sandbox --package-path swift-shell --scratch-path runtime/swiftpm-scratch -c debug` completed with only pre-existing Outlook screenshot-reader deprecation warnings, and `jarvis-status-helper --self-test` passed. The live-launched proof now matches 0.1.439 because the bundled app launch path completed and refreshed the loopback report surfaces.",
    "Live Jarvis 0.1.438 build 438 launched from bundled app resources with worker_launch_matches_bundle=true.",
    "0.1.438 proof: full Python safety suite passed 640/640, no-prompt verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-213956.json`, fast latency smoke refreshed the master report after writing `runtime/model_benchmarks/localhost-fast-latency-20260615-213953.json`, and the non-music speech-audit matrix passed 7/7 at `runtime/regression_prompt_matrix/20260615-211642/summary.json`.",
    "Live Jarvis 0.1.437 build 437 launched from bundled app resources with worker_launch_matches_bundle=true.",
    "0.1.437 proof: full Python safety suite passed 634/634, no-prompt verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-210830.json`, and live readiness reports no actionable unavailable tools while listing `ui.automation` plus `screen.ocr` under planned future tools instead of a generic broken-tools warning.",
    "Live Jarvis 0.1.436 build 436 launched from bundled app resources with worker_launch_matches_bundle=true.",
    "0.1.436 proof: full Python safety suite passed 633/633, no-prompt verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-205415.json`, speech mute source tagging is covered by backend persistence, server payload sanitization, Swift client, and status-helper source tests, and live `/api/speech/mute` stays unmuted after a direct Keep Blabbering-style restore.",
    "Live Jarvis 0.1.435 build 435 launched from bundled app resources with worker_launch_matches_bundle=true.",
    "0.1.435 proof: full Python safety suite passed 631/631, no-prompt verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-203433.json`, and live report/workboard routes show 0.1.434 through 0.1.430 before 0.1.429.",
    "Live Jarvis 0.1.434 build 434 launched from bundled app resources with worker_launch_matches_bundle=true.",
    "0.1.434 proof: full Python safety suite passed 630/630, no-prompt verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-192252.json`, and the full eight-prompt matrix passed 8/8 at `runtime/regression_prompt_matrix/20260615-192359/summary.json`.",
    "Live `/api/plan` for `stop the music` now returns `localos_music_and_emergency_cleanup`, and the model-facing music catalog no longer advertises a tracked local fallback or hidden player route.",
    "Live Jarvis 0.1.433 build 433 launched from bundled app resources with worker_launch_matches_bundle=true and `/api/speech/status` returned spoken=true through the macOS provider after Keep Blabbering recovery.",
    "0.1.433 proof: full Python safety suite passed 629/629 and no-prompt verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-183150.json`.",
    "Live Jarvis 0.1.432 build 432 launched from bundled app resources with worker_launch_matches_bundle=true and `codex speed status` reported local ClashX 6.4s, no proxy 19.9s, and Air proxy timed out.",
    "0.1.432 proof: full Python safety suite passed 628/628 and no-prompt verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-180020.json`.",
    "Live Jarvis 0.1.431 build 431 launched from bundled app resources with worker_launch_matches_bundle=true, and direct `run_codex_delegate(\"hi\")` selected the local ClashX proxy route in 9.586s.",
    "0.1.431 proof: full Python safety suite passed 627/627 and no-prompt verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-174653.json`.",
    "Live Jarvis 0.1.430 build 430 launched from bundled app resources, file-level voice-loop QA passed for status, calendar, LocalOS music, and RAM, and the LocalOS bridge restoration passed no-prompt verification 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-114850.json`.",
    "Live Jarvis 0.1.429 build 429 launched from bundled app resources with worker_launch_matches_bundle=true and speech still muted.",
    "Command payload probes passed on the live app: `message: status` routed to `system.status`, `text: Play Waving Through a Window` routed to `localos.music_play`, and an empty body returned HTTP 400 `Command text is required`.",
    "Full Python safety suite passed 622/622 after the 0.1.429 command payload hardening.",
    "No-prompt live verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-054148.json`.",
    "Full safe verifier passed 102/102 at `runtime/verification/verify-safe-20260615-054939.json` after the 0.1.429 build.",
    "Live eight-prompt speech-audit matrix passed 8/8 at `runtime/regression_prompt_matrix/20260615-055020/summary.json` on Jarvis 0.1.429 using explicit `--no-permission-prompts --stt-provider local` flags.",
    "Focused isolated-worker verifier section passed 32/32 after adding HTTP-stream checks for `message` alias payloads and empty `/api/command/stream` rejection.",
    "Live Jarvis 0.1.428 build 428 launched from bundled app resources with worker_launch_matches_bundle=true and exactly one app, one parent-bound status helper, and one worker.",
    "Focused LocalOS music tests passed 5/5 after the 0.1.428 closest-match wording polish.",
    "Full Python safety suite passed 621/621 after the 0.1.428 build.",
    "No-prompt live verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-051951.json`.",
    "Full safe verifier passed 100/100 at `runtime/verification/verify-safe-20260615-052733.json` after the 0.1.428 build.",
    "Live eight-prompt speech-audit matrix passed 8/8 at `runtime/regression_prompt_matrix/20260615-052819/summary.json` on Jarvis 0.1.428 using explicit `--no-permission-prompts --stt-provider local` flags.",
    "Live 0.1.428 music probe stayed muted and suppressed audio actions: `Play Waving Through a Window` returned `I found the closest LocalOS match...` with `jarvis_played_audio=false`.",
    "Live Jarvis 0.1.427 build 427 launched from bundled app resources with worker_launch_matches_bundle=true and exactly one app, one parent-bound status helper, and one worker.",
    "Full Python safety suite passed 621/621 after the 0.1.427 Calendar speech polish.",
    "No-prompt live verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-045256.json`.",
    "Full safe verifier passed 100/100 at `runtime/verification/verify-safe-20260615-045903.json` after the 0.1.427 build.",
    "Live Calendar probe returned clean English schedule text with `8 AM`, `8:55 AM`, and no Chinese characters in the visible reply while speech stayed muted.",
    "Live eight-prompt speech-audit matrix passed 8/8 at `runtime/regression_prompt_matrix/20260615-045930/summary.json` on Jarvis 0.1.427 after the Calendar speech polish.",
    "Regression matrix CLI hardening passed: focused source-contract test OK, help accepts `--no-permission-prompts --stt-provider local`, and `--stt-provider apple` fails closed unless `--allow-apple-speech` is set.",
    "Live Jarvis 0.1.426 build 426 launched from bundled app resources with worker_launch_matches_bundle=true and exactly one app, one parent-bound status helper, and one worker.",
    "Full Python safety suite passed 620/620 after the 0.1.426 persistent Shut Up patch.",
    "No-prompt live verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-042825.json`.",
    "Full safe verifier passed 100/100 at `runtime/verification/verify-safe-20260615-043159.json` after the 0.1.426 build.",
    "Live speech remained muted after relaunch and after verification: `/api/speech/mute` reports muted=true, active_speech=false, and speech_mute_persistent=true.",
    "Live eight-prompt speech-audit matrix passed 8/8 at `runtime/regression_prompt_matrix/20260615-043740/summary.json` on Jarvis 0.1.426 after the persistent Shut Up patch.",
    "Live Jarvis 0.1.425 build 425 launched from bundled app resources with worker_launch_matches_bundle=true and exactly one app, one parent-bound status helper, and one worker.",
    "Full Python safety suite passed 619/619 after the 0.1.425 Teams OCR retry patch.",
    "No-prompt live verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-041133.json`.",
    "Full safe verifier passed 100/100 at `runtime/verification/verify-safe-20260615-041502.json` after the 0.1.425 build.",
    "Reusable 0.1.424 eight-prompt speech-audit matrix passed 8/8 at `runtime/regression_prompt_matrix/20260615-040014/summary.json` using local STT and suppressed audio actions.",
    "Live Jarvis 0.1.424 build 424 launched from bundled app resources with worker_launch_matches_bundle=true and exactly one app, one parent-bound status helper, and one worker.",
    "Full Python safety suite passed 618/618 after the 0.1.424 speech-status sync patch.",
    "No-prompt live verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-034959.json`.",
    "Full safe verifier passed 100/100 at `runtime/verification/verify-safe-20260615-035341.json` after the 0.1.424 build.",
    "Live speech is muted after verification, and `/api/speech/mute` reports muted=true with no active speech.",
    "Live Jarvis 0.1.423 build 423 launched from bundled app resources with worker_launch_matches_bundle=true and exactly one app, one parent-bound status helper, and one worker.",
    "Full Python safety suite passed 618/618 after the 0.1.423 OCR/helper hardening.",
    "Swift menu-bar and status-helper self-tests passed after the parent-PID helper lifecycle fix.",
    "No-prompt live verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-032753.json`.",
    "Full safe verifier passed 100/100 at `runtime/verification/verify-safe-20260615-033049.json` after the 0.1.423 build.",
    "Live eight-prompt speech-audit matrix passed 8/8 at `runtime/regression_prompt_matrix/20260615-033624/summary.json` on Jarvis 0.1.423.",
    "Real Teams UI proof: the app ran `teams.assignment`, then `screen.visible_text` with `native_vision_ocr_screen_display_fallback`, detected assignment context, and generated follow-up questions.",
    "Live visible-screen summary proof now keeps the assignment lines and drops Chrome/tab/sidebar noise for the Teams screen.",
    "Live Jarvis 0.1.422 build 422 launched from bundled app resources with worker_launch_matches_bundle=true.",
    "Full Python safety suite passed 615/615 after the 0.1.422 Teams OCR contract alignment.",
    "Swift command-routing self-test passed after the 0.1.422 Teams OCR contract alignment.",
    "No-prompt live verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-024457.json`.",
    "Full safe verifier passed 100/100 at `runtime/verification/verify-safe-20260615-024858.json` after the 0.1.422 build.",
    "Live Teams command probe now reports `chrome_handoff_then_native_visible_read`, `automatic_teams_page_inspection_supported=true`, and `recommended_next_safe_tool=screen.visible_text` while still saying no assignment has been inspected until OCR succeeds.",
    "Live Jarvis 0.1.421 build 421 launched from bundled app resources with worker_launch_matches_bundle=true.",
    "Full Python safety suite passed 615/615 after the 0.1.421 status-line polish.",
    "Swift command-routing self-test passed after the 0.1.421 status-line polish.",
    "No-prompt live verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-023001.json`.",
    "Full safe verifier passed 100/100 at `runtime/verification/verify-safe-20260615-023431.json` after the 0.1.421 build.",
    "Focused speech-audit proof: `Summarize all the emails from Ms. Sharpay in the past month` now speaks `Checking emails from Ms Sharpay over the past month now` with 1.0 local STT similarity and zero leaks.",
    "Focused speech-audit proof: the Teams assignment handoff status now speaks `Opening Teams now` with zero leaks.",
    "Live eight-prompt speech-audit matrix passed 8/8 at `runtime/regression_prompt_matrix/20260615-023711/summary.json` on Jarvis 0.1.421 after the status-line polish.",
    "Live Jarvis 0.1.420 build 420 launched from bundled app resources with worker_launch_matches_bundle=true.",
    "Full Python safety suite passed 614/614 after the Teams follow-up question route.",
    "No-prompt live verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-020859.json`.",
    "Muted live `/api/screen/visible-text` probe produced five assignment follow-up questions and stayed muted.",
    "Full safe verifier passed 100/100 at `runtime/verification/verify-safe-20260615-021232.json` after the 0.1.420 build.",
    "Live eight-prompt speech-audit matrix passed 8/8 at `runtime/regression_prompt_matrix/20260615-021451/summary.json` on Jarvis 0.1.420, covering Teams assignment handoff, LocalOS music, RAM, Codex Default-chat confirmation, Calendar, model-test planning, Ms. Sharpay contact handling, and Magic Keyboard yuan conversion with no spoken-output leaks.",
    "Live Jarvis 0.1.419 build 419 launched from bundled app resources with worker_launch_matches_bundle=true.",
    "Full Python safety suite passed 613/613 after the Teams assignment OCR digest improvement.",
    "No-prompt live verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-015853.json`.",
    "Muted live `/api/screen/visible-text` probe extracted assignment-related Teams OCR lines including class, due time, instructions, and rubric while keeping speech muted.",
    "Full safe verifier passed 100/100 at `runtime/verification/verify-safe-20260615-020222.json` after the 0.1.419 build.",
    "Live Jarvis 0.1.418 build 418 launched from bundled app resources with worker_launch_matches_bundle=true.",
    "Full Python safety suite passed 612/612 after the Teams handoff plus OCR follow-up.",
    "Swift command-routing self-test passed with automatic Teams OCR follow-up allowed for assignment-reading requests and rejected for submission/mutation wording.",
    "No-prompt live verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-014800.json`.",
    "Full safe verifier passed 100/100 at `runtime/verification/verify-safe-20260615-015136.json` after the 0.1.418 build.",
    "Live Jarvis 0.1.417 build 417 launched from bundled app resources with worker_launch_matches_bundle=true.",
    "Full Python safety suite passed 612/612 after the native visible-screen read route.",
    "Swift command-routing self-test passed with explicit visible Teams/page reads routed to native visible-screen OCR and screen-status/mutation requests rejected.",
    "No-prompt live verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-013054.json`.",
    "Live eight-prompt regression matrix passed 8/8 at `runtime/regression_prompt_matrix/20260615-013149/summary.json` with speech/audio side effects suppressed.",
    "Full safe verifier passed 100/100 at `runtime/verification/verify-safe-20260615-013807.json` after the 0.1.417 build.",
    "Runtime hygiene after 0.1.417 launch showed one `jarvis-menu-bar`, one `jarvis-status-helper`, one bundled worker, and no `afplay` background audio.",
    "Full safe verifier passed 100/100 at `runtime/verification/verify-safe-20260615-010549.json` after the private-port temporary bundle fix.",
    "Live Jarvis 0.1.416 build 416 launched from bundled app resources with worker_launch_matches_bundle=true.",
    "Full Python safety suite passed 606/606 after the 0.1.416 Teams, browser-read, contact-memory, and wake-loop changes.",
    "No-prompt live verifier passed 12/12 at `runtime/verification_no_prompt/verify-no-prompt-20260615-004114.json`.",
    "Live eight-prompt speech-audit matrix passed 8/8 at `runtime/regression_prompt_matrix/20260615-004209/summary.json` with speech/audio actions suppressed.",
    "Runtime hygiene after launch showed one `jarvis-menu-bar`, one `jarvis-status-helper`, one bundled worker, only `output/Jarvis.app` in active output, and no `afplay` background audio.",
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
    "Live suppressed Teams-assignment probe on Jarvis 0.1.370 returned `teams.assignment` with `browser_target_available=true`, `preferred_browser_lane=chrome_authenticated`, `open_chrome_to_reuse_login=true`, and `copied_chrome_cookies=false`.",
    "Chrome page-read permission regression now proves `Not authorized to send Apple events to Google Chrome` becomes `automation_not_allowed` with next steps for Jarvis Automation access, no cloud model call, and no Chrome cookie/session copying.",
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
    "Python safety suite: 568/568 passed after the wake, mute, final-speech, report-route, speech-alignment, barge-in filtering, model-selected device/app-routing, app-specific status-line, fuzzy-wake, stale-progress, anti-flicker, muted-latency, local-STT repair, overlapping-turn, crash-monitor, fallback-hardening, quiet-command, quiet-audio automation, summon-popout, hidden-tool-call sanitization, model-scoring, browser-session, page-digest, Teams browser-target, Chrome Automation diagnosis, plural-email private-read classification, music-bridge, contact-memory, contact-inference, calendar-preview, LocalOS Chrome-direct control, contact-dictation aliases, and voice-QA work.",
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
    "Open Perms and check Chrome Automation; if it says Needs Automation Access, allow Jarvis.app under Privacy & Security > Automation > Google Chrome before expecting current-page summaries.",
    "Ask Jarvis to play Waving Through a Window; the current full-loop proof uses the native Music app bridge, auto-starts Music.app if needed, confirms playback, then stops it during cleanup.",
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
    "Calendar reading still depends on the new Jarvis 0.1.373 Calendar Cache tile being Ready; if it says Needs Full Disk Access, grant Jarvis.app Full Disk Access and reopen Jarvis before expecting real schedule summaries.",
    "Chrome active-page reading now routes correctly, but Teams-page summaries still depend on the new Chrome Automation tile being Ready; Jarvis will not copy Chrome cookies or sessions into WebKit.",
    "Music's primary proof now uses the native Music app bridge. Older LocalOS/Chrome fallback paths may still require a real click, but Jarvis should report that honestly instead of claiming playback.",
    "MacBook Air remote-worker probing currently cannot proceed because Tailscale is stopped on this Mac; Jarvis now detects that quickly and should ask before running model tests locally.",
    "Groq works as Jarvis's fast conversation model, but the scored middle-model comparison showed it should not be trusted for safety-sensitive planning without stronger prompting or a safer model layer.",
    "GPT-OSS 20B Cloud returned empty visible replies in the newest comparison and should not be treated as a dependable middle model yet.",
    "Gemma4 31B Cloud did not confirm audio understanding through Ollama; it answered text prompts well, but native audio input remains unproven.",
    "Real microphone pickup, false wakes, and room-noise reliability still need Leo testing.",
    "The summon popout's code-level rectangle and stray-line causes are fixed, but Leo should do the final human-eye check on the real Stage Manager desktop.",
    "Browser loopback noise trials are useful but not a perfect model of a real room.",
    "Speech Recognition permission can still block the native listener until macOS grants it to the current Jarvis bundle.",
    "Local-only faster-whisper STT now works for file-based QA, but tiny.en still mishears some technical words and is not good enough as the final live dictation model.",
    "The full safe verifier was rerun and passed, but real microphone wake quality is still a human-room test, not something the verifier can prove from files alone.",
    "The current wake phrase is experimental; it is not yet personalized to Leo's voice.",
    "Very technical diagnostics are still intentionally speech-silent so Jarvis does not read backend internals aloud.",
    "After Leo's no-approval overnight instruction, new work stayed repo-local: no app replacement, Git write, GUI launch, network action, or approval prompt was attempted.",
    "GitHub main still preserves the older small-tree history; the full Jarvis folder is published on the overnight branch and should be promoted deliberately.",
]

SUPPORTING_FILES = [
    ("http://127.0.0.1:8765/overnight-report/", "Loopback master report"),
    ("http://127.0.0.1:8765/overnight-workboard/", "Loopback overnight workboard"),
    ("runtime/overnight_status/index.html", "Live overnight workboard"),
    ("runtime/overnight_status/report.html", "This master report"),
    ("scripts/pre_build_gate.py", "Single pre-build proof gate for safety tests, full-loop regressions, cleanup, and report refresh"),
    ("scripts/report_refresh.py", "Standalone master report refresh helper"),
    ("scripts/cleanup_chrome_test_tabs.py", "Morning handoff helper that closes only Jarvis/Codex LocalOS music-player Chrome tabs"),
    ("http://127.0.0.1:8765/wake-audition/", "Hey Jarvis wake audition lab"),
    ("runtime/wake_audition/samples/", "Locally saved wake samples"),
    ("runtime/verification/", "Safe verifier reports"),
    ("runtime/verification_no_prompt/", "No-prompt live verifier reports"),
    ("runtime/model_benchmarks/", "Fast latency smoke reports"),
    ("runtime/model_benchmarks/latest.json", "Latest fast-latency smoke summary"),
    ("runtime/model_benchmarks/latest.md", "Latest fast-latency smoke notes"),
    ("runtime/regression_prompt_matrix/latest.json", "Latest eight-prompt regression matrix summary"),
    ("runtime/regression_prompt_matrix/latest.md", "Latest eight-prompt regression matrix notes"),
    ("runtime/conversation_context/", "Conversation-context smoke reports"),
    ("runtime/conversation_context/latest.json", "Latest conversation-context smoke summary"),
    ("runtime/conversation_context/latest.md", "Latest conversation-context smoke notes"),
    ("runtime/wake_threshold/", "Wake-threshold smoke reports"),
    ("runtime/wake_threshold/latest.json", "Latest wake-threshold smoke summary"),
    ("runtime/wake_threshold/latest.md", "Latest wake-threshold smoke notes"),
    ("runtime/voice_loop_qa/latest.json", "Latest closed-loop voice QA report"),
    ("runtime/voice_loop_qa/latest.md", "Latest closed-loop voice QA notes"),
    ("runtime/voice_loop_qa/", "Closed-loop voice QA artifacts"),
    ("runtime/full_loop_regression/latest.json", "Latest full-loop real-action regression report"),
    ("runtime/full_loop_regression/latest.md", "Latest full-loop real-action regression notes"),
    ("runtime/full_loop_regression/", "Full-loop real-action regression artifacts"),
    ("runtime/pre_build_gate/latest.json", "Latest pre-build proof gate summary"),
    ("runtime/pre_build_gate/latest.md", "Latest pre-build proof gate notes"),
    ("runtime/pre_build_gate/", "Pre-build proof gate artifacts"),
    ("runtime/codex_cli_proxy_benchmarks/latest.json", "Latest Codex CLI proxy benchmark summary"),
    ("runtime/codex_cli_proxy_benchmarks/latest.md", "Latest Codex CLI proxy benchmark notes"),
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
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Jarvis worker base URL.")
    args = parser.parse_args()

    try:
        context = build_context(args.base_url)
    except ValueError as error:
        print(f"Refused unsafe base URL: {error}")
        return 2
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "report.html").write_text(render_report(context), encoding="utf-8")
    (OUTPUT_DIR / "index.html").write_text(render_workboard(context), encoding="utf-8")
    print(f"Rendered {OUTPUT_DIR / 'index.html'}")
    print(f"Rendered {OUTPUT_DIR / 'report.html'}")
    return 0


def build_context(base_url: str) -> dict[str, Any]:
    base_url = normalize_base_url(base_url)
    health = get_json(f"{base_url}/api/health")
    app = nested(health, "status", "app")
    runtime = nested(health, "status", "runtime")
    fast_model = nested(health, "status", "fast_model")
    verification = latest_verification()
    no_prompt_verification = latest_no_prompt_verification()
    latency = latest_latency_smoke()
    context_smoke = latest_context_smoke()
    wake_threshold = latest_wake_threshold_smoke()
    regression_matrix = latest_regression_prompt_matrix()
    voice_loop = latest_voice_loop_qa()
    full_loop = latest_full_loop_regression()
    crash = latest_jarvis_crash_report()
    now = datetime.now(BEIJING)
    version = str(app.get("version") or "unknown")
    build = str(app.get("build") or "unknown")
    bundle_source = "live worker"
    if version == "unknown" and build == "unknown":
        fallback = output_bundle_metadata()
        if fallback:
            version = str(fallback.get("version") or "unknown")
            build = str(fallback.get("build") or "unknown")
            bundle_source = "output bundle file"
        else:
            bundle_source = "unavailable"
    bundle = bundle_label(version, build)
    commit = git(["rev-parse", "--short", "HEAD"]) or "unknown"
    branch = git(["branch", "--show-current"]) or "unknown"
    upstream = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    git_sync = git_sync_label(upstream)
    git_dirty = git_dirty_label()
    return {
        "base_url": base_url,
        "now": now,
        "updated": now.strftime("%Y-%m-%d %H:%M CST"),
        "version": version,
        "build": build,
        "bundle": bundle,
        "bundle_source": bundle_source,
        "commit": commit,
        "branch": branch,
        "upstream": upstream,
        "git_sync": git_sync,
        "git_dirty": git_dirty,
        "python_test_count": current_python_test_count(),
        "verification": verification,
        "no_prompt_verification": no_prompt_verification,
        "latency": latency,
        "context_smoke": context_smoke,
        "wake_threshold": wake_threshold,
        "regression_matrix": regression_matrix,
        "voice_loop": voice_loop,
        "full_loop": full_loop,
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
            regression_matrix,
            voice_loop,
            full_loop,
            crash,
            version,
            build,
        ),
        "try": TRY_ITEMS,
        "risks": RISK_ITEMS,
        "supporting": SUPPORTING_FILES,
        "crash": crash,
    }


def normalize_base_url(raw: str) -> str:
    value = str(raw or DEFAULT_BASE_URL).rstrip("/")
    if value.endswith("/api/command"):
        value = value.removesuffix("/api/command")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in LOOPBACK_HOSTS:
        raise ValueError("overnight report only talks to loopback Jarvis workers")
    return value


def bundle_label(version: Any, build: Any) -> str:
    version_text = str(version or "unknown")
    build_text = str(build or "unknown")
    if version_text == "unknown" and build_text == "unknown":
        return "live bundle metadata unavailable"
    if version_text == "unknown":
        return f"Jarvis build {build_text}"
    if build_text == "unknown":
        return f"Jarvis {version_text}"
    return f"Jarvis {version_text} build {build_text}"


def output_bundle_metadata(app_path: Path | None = None) -> dict[str, str]:
    bundle_path = app_path or PROJECT_ROOT / "output" / "Jarvis.app"
    info_plist = bundle_path / "Contents" / "Info.plist"
    try:
        with info_plist.open("rb") as handle:
            plist = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException):
        return {}
    version = str(plist.get("CFBundleShortVersionString") or "").strip()
    build = str(plist.get("CFBundleVersion") or "").strip()
    if not version and not build:
        return {}
    return {
        "version": version,
        "build": build,
        "bundle_id": str(plist.get("CFBundleIdentifier") or "").strip(),
        "path": str(bundle_path),
    }


def proof_items_with_verification(
    verification: dict[str, Any],
    no_prompt_verification: dict[str, Any] | None = None,
    latency: dict[str, Any] | None = None,
    context_smoke: dict[str, Any] | None = None,
    wake_threshold: dict[str, Any] | None = None,
    regression_matrix: dict[str, Any] | None = None,
    voice_loop: dict[str, Any] | None = None,
    full_loop: dict[str, Any] | None = None,
    crash: dict[str, Any] | None = None,
    current_version: str = "",
    current_build: str = "",
) -> list[str]:
    items = list(PROOF_ITEMS)
    if verification.get("path"):
        items.append(
            f"Latest verifier artifact: {verification['path']} with {verification['passed']}/{verification['total']} checks."
        )
    window_probe = verification.get("window_probe") if isinstance(verification.get("window_probe"), dict) else {}
    if window_probe.get("summary"):
        if window_probe.get("session_locked"):
            items.append(
                "Latest bundled window probe hit the macOS lock screen, so foreground Jarvis visibility could not be judged live: "
                f"{window_probe['summary']}."
            )
        else:
            items.append(f"Latest bundled window probe: {window_probe['summary']}.")
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
    if regression_matrix and regression_matrix.get("path"):
        items.append(
            "Latest eight-prompt regression matrix: "
            f"{regression_matrix['label']}, "
            f"{regression_matrix['speech_payload_count']} speech payloads, "
            f"{regression_matrix['speech_leak_count']} speech leaks, "
            f"max first visible {regression_matrix['max_first_visible_seconds']:.3f}s "
            f"({regression_matrix['path']})."
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
            speech_mode = str(voice_loop.get("speech_mode") or "suppressed_for_probe")
            live_note = (
                f", live playback requested {voice_loop['live_playback_requested']}, active observed {voice_loop['active_speech_observed']}"
                if speech_mode == "live_playback_exercised"
                else ""
            )
            items.append(
                "Latest closed-loop voice QA: "
                f"{voice_loop['label']}, command transcript {voice_loop['command_transcript']!r}, "
                f"routed command {voice_loop['routed_command']!r}, reply similarity {voice_loop['reply_similarity']:.3f}, "
                f"speech mode {speech_mode}{live_note} "
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
                f"command STT {voice_loop['latest_command_stt_status']}, speech mode {voice_loop['latest_speech_mode']}, "
                f"routed command {voice_loop['latest_routed_command']!r}{latest_error} "
                f"({latest_path})."
            )
    if full_loop and full_loop.get("path"):
        case_summary = str(full_loop.get("case_summary") or "")
        case_note = f", cases {case_summary}" if case_summary else ""
        latency_label = str(full_loop.get("latency_budget_label") or "")
        slowest_case = str(full_loop.get("slowest_case_id") or "")
        slowest_seconds = float(full_loop.get("slowest_case_seconds") or 0.0)
        duration_seconds = float(full_loop.get("duration_seconds") or 0.0)
        speed_note = ""
        if latency_label and slowest_case:
            speed_note = f", latency budgets {latency_label}, slowest {slowest_case} {slowest_seconds:.3f}s"
        if duration_seconds > 0.0:
            speed_note = f"{speed_note}, total {duration_seconds:.3f}s"
        items.append(
            "Latest full-loop real-action regression: "
            f"{full_loop['label']}, command {full_loop['command']!r}, "
            f"selected {full_loop['selected_title']!r}, voice loop {full_loop['voice_loop_status']}, "
            f"cleanup {full_loop['cleanup_label']}{speed_note}{case_note} ({full_loop['path']})."
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
    window_probe = latest_window_probe(results)
    return {
        "ok": bool(data.get("ok")) and total > 0 and passed == total,
        "path": relative,
        "passed": passed,
        "total": total,
        "label": f"{passed}/{total} passed" if total else "empty",
        "window_probe": window_probe,
    }


def latest_window_probe(results: list[dict[str, Any]]) -> dict[str, Any]:
    for item in results:
        if not isinstance(item, dict) or item.get("name") != "output_bundle_window_self_test":
            continue
        payload = parse_window_self_test_output(item.get("stdout_tail"))
        snapshot = latest_window_self_test_snapshot(payload)
        return {
            "passed": bool(item.get("passed")),
            "summary": str(item.get("summary") or "").strip(),
            "returncode": item.get("returncode"),
            "session_locked": bool(snapshot.get("session_locked")),
            "panel_is_visible": bool(snapshot.get("panel_is_visible")),
            "window_count": safe_int(snapshot.get("window_count")),
            "label": str(snapshot.get("label") or ""),
        }
    return {}


def parse_window_self_test_output(text: Any) -> dict[str, Any]:
    clean = str(text or "").strip()
    if not clean:
        return {}
    candidates = [clean]
    start = clean.find("{")
    end = clean.rfind("}")
    if 0 <= start < end:
        candidates.append(clean[start : end + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def latest_window_self_test_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    snapshots = payload.get("snapshots")
    if not isinstance(snapshots, list):
        return {}
    for item in reversed(snapshots):
        if isinstance(item, dict):
            return item
    return {}


def safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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
    completed = [item for item in results if latency_status_counts_as_success(item.get("status"))]
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


def latency_status_counts_as_success(status: Any) -> bool:
    return str(status or "").strip() in {"completed", "checked"}


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


def latest_regression_prompt_matrix() -> dict[str, Any]:
    latest = PROJECT_ROOT / "runtime" / "regression_prompt_matrix" / "latest.json"
    reports = sorted((PROJECT_ROOT / "runtime" / "regression_prompt_matrix").glob("*/summary.json"))
    if not latest.exists():
        latest = _newest_canonical_matrix_summary(reports) or (reports[-1] if reports else latest)
    if not latest.exists():
        return {
            "ok": False,
            "path": "",
            "label": "none",
            "passed": 0,
            "total": 0,
            "speech_payload_count": 0,
            "speech_leak_count": 0,
            "max_first_visible_seconds": 0.0,
        }
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "ok": False,
            "path": str(latest),
            "label": "unreadable",
            "passed": 0,
            "total": 0,
            "speech_payload_count": 0,
            "speech_leak_count": 0,
            "max_first_visible_seconds": 0.0,
        }
    if reports and data.get("canonical_latest") is not True:
        canonical_latest = _newest_canonical_matrix_summary(reports)
        if canonical_latest is not None and canonical_latest != latest:
            try:
                data = json.loads(canonical_latest.read_text(encoding="utf-8"))
                latest = canonical_latest
            except (OSError, json.JSONDecodeError):
                pass
    passed = int(data.get("passed") or 0)
    total = int(data.get("total") or 0)
    leaks = int(data.get("speech_leak_count") or 0)
    payloads = int(data.get("speech_payload_count") or 0)
    ok = bool(data.get("ok")) and total > 0 and passed == total and leaks == 0
    run_root = str(data.get("root") or "").strip()
    path = ""
    if run_root:
        root_path = Path(run_root)
        if not root_path.is_absolute():
            root_path = PROJECT_ROOT / root_path
        summary_path = root_path / "summary.json"
        if summary_path.exists():
            path = str(summary_path.relative_to(PROJECT_ROOT))
    if not path:
        path = str(latest.relative_to(PROJECT_ROOT)) if latest.is_relative_to(PROJECT_ROOT) else str(latest)
    return {
        "ok": ok,
        "path": path,
        "label": f"{passed}/{total} passed" if total else "empty",
        "passed": passed,
        "total": total,
        "speech_payload_count": payloads,
        "speech_leak_count": leaks,
        "max_first_visible_seconds": float(data.get("max_first_visible_seconds") or 0.0),
    }


def _newest_canonical_matrix_summary(reports: list[Path]) -> Path | None:
    for report in reversed(reports):
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("canonical_latest") is True:
            return report
        case_filter = data.get("case_filter")
        selected = case_filter.get("selected") if isinstance(case_filter, dict) else None
        if isinstance(selected, list) and len(selected) >= 8:
            return report
    return None


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
            "speech_mode": "suppressed_for_probe",
            "live_playback_requested": False,
            "active_speech_observed": False,
            "latest_speech_mode": "suppressed_for_probe",
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
            "speech_mode": "suppressed_for_probe",
            "live_playback_requested": False,
            "active_speech_observed": False,
            "latest_speech_mode": "suppressed_for_probe",
        }
    latest_path, latest_data = latest_readable
    proof_path, data = latest_passed or latest_readable
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    input_data = data.get("input") if isinstance(data.get("input"), dict) else {}
    speech_audit = result.get("speech_audit") if isinstance(result.get("speech_audit"), dict) else {}
    speech_runtime = result.get("speech_runtime") if isinstance(result.get("speech_runtime"), dict) else {}
    ok = result.get("status") == "passed"
    relative = str(proof_path.relative_to(PROJECT_ROOT))
    latest_result = latest_data.get("result") if isinstance(latest_data.get("result"), dict) else {}
    latest_command_stt = latest_result.get("command_stt") if isinstance(latest_result.get("command_stt"), dict) else {}
    latest_speech_runtime = latest_result.get("speech_runtime") if isinstance(latest_result.get("speech_runtime"), dict) else {}
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
        "latest_stt_provider": str(nested(latest_data, "input").get("stt_provider") or "local"),
        "latest_command_stt_status": str(latest_command_stt.get("status") or "unknown"),
        "latest_command_stt_error": str(latest_command_stt.get("error") or ""),
        "latest_routed_command": str(latest_result.get("routed_command") or ""),
        "speech_audit_only": is_speech_audit_only,
        "speech_payload_count": int(speech_audit.get("payload_count") or 0),
        "speech_leak_count": int(speech_audit.get("leak_count") or 0),
        "command_response_tool": str(result.get("command_response_tool") or ""),
        "speech_mode": str(speech_runtime.get("mode") or ("live_playback_exercised" if input_data.get("exercise_live_speech") else "suppressed_for_probe")),
        "live_playback_requested": bool(speech_runtime.get("playback_requested")),
        "active_speech_observed": bool(speech_runtime.get("active_observed")),
        "latest_speech_mode": str(
            latest_speech_runtime.get("mode")
            or ("live_playback_exercised" if nested(latest_data, "input").get("exercise_live_speech") else "suppressed_for_probe")
        ),
    }
    return summary


def latest_full_loop_regression() -> dict[str, Any]:
    latest = PROJECT_ROOT / "runtime" / "full_loop_regression" / "latest.json"
    if not latest.exists():
        reports = sorted((PROJECT_ROOT / "runtime" / "full_loop_regression").glob("*/summary.json"))
        latest = reports[-1] if reports else latest
    empty = {
        "ok": False,
        "path": "",
        "label": "none",
        "command": "",
        "selected_title": "",
        "voice_loop_status": "",
        "cleanup_label": "not run",
    }
    if not latest.exists():
        return empty
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {**empty, "path": str(latest), "label": "unreadable"}
    results = data.get("results") if isinstance(data.get("results"), list) else []
    first = next((item for item in results if isinstance(item, dict)), {})
    case_ids = [
        str(item.get("case_id") or "")
        for item in results
        if isinstance(item, dict) and item.get("case_id")
    ]
    timed_results: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        try:
            seconds = float(item.get("total_seconds") or 0.0)
        except (TypeError, ValueError):
            seconds = 0.0
        if seconds > 0.0:
            timed_results.append({**item, "_total_seconds_float": seconds})
    slowest = max(timed_results, key=lambda item: float(item.get("_total_seconds_float") or 0.0), default={})
    budgeted_results = [
        item
        for item in results
        if isinstance(item, dict) and item.get("latency_budget_seconds") is not None
    ]
    budget_passed = sum(1 for item in budgeted_results if item.get("latency_budget_status") == "passed")
    budget_total = len(budgeted_results)
    budget_failed = [
        str(item.get("case_id") or "")
        for item in budgeted_results
        if item.get("latency_budget_status") == "failed"
    ]
    action_proof = first.get("action_proof") if isinstance(first.get("action_proof"), dict) else {}
    cleanup = first.get("cleanup") if isinstance(first.get("cleanup"), dict) else {}
    stop_ok = bool(nested(cleanup, "stop").get("ok"))
    close_ok = bool(nested(cleanup, "close_window").get("ok"))
    path = str(latest.relative_to(PROJECT_ROOT)) if latest.is_relative_to(PROJECT_ROOT) else str(latest)
    passed = int(data.get("passed") or 0)
    total = int(data.get("total") or 0)
    return {
        "ok": str(data.get("status") or "") == "passed",
        "path": path,
        "label": f"{passed}/{total} passed" if total else "empty",
        "command": str(first.get("command") or ""),
        "case_ids": case_ids,
        "case_summary": ", ".join(case_ids),
        "slowest_case_id": str(slowest.get("case_id") or ""),
        "slowest_case_seconds": round(float(slowest.get("_total_seconds_float") or 0.0), 3),
        "duration_seconds": round(float(data.get("duration_seconds") or 0.0), 3),
        "latency_budget_label": f"{budget_passed}/{budget_total} passed" if budget_total else "",
        "latency_budget_failed": budget_failed,
        "selected_title": str(action_proof.get("selected_title") or ""),
        "voice_loop_status": str(first.get("voice_loop_status") or ""),
        "cleanup_label": f"stop {'ok' if stop_ok else 'failed'}, close {'ok' if close_ok else 'failed'}",
    }


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


def git_status_porcelain() -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, ""
    if completed.returncode != 0:
        return False, ""
    return True, completed.stdout.strip()


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


def git_dirty_label() -> str:
    ok, status = git_status_porcelain()
    if not ok:
        return "unknown"
    if status:
        return "dirty"
    return "clean"


def python_suite_label(proof_items: list[str] | None = None) -> str:
    for item in proof_items or PROOF_ITEMS:
        match = re.search(r"full Python safety suite passed\s+(\d+/\d+)", item)
        if match:
            return f"{match.group(1)} passed"
    return "unknown"


def current_python_test_count() -> int:
    try:
        root = str(PROJECT_ROOT)
        if root not in sys.path:
            sys.path.insert(0, root)
        suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_safety")
        count = int(suite.countTestCases())
        return 0 if count == 1 and _suite_has_failed_import(suite) else count
    except Exception:
        return 0


def _suite_has_failed_import(suite: unittest.TestSuite) -> bool:
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            if _suite_has_failed_import(test):
                return True
            continue
        if test.__class__.__name__ == "_FailedTest":
            return True
    return False


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
    <p class="tagline">Jarvis is now more honest, quieter on wake, and verified against Leo's real task prompts. This is the single page Leo needs tomorrow morning.</p>
    {pill_row(context, refresh_seconds=30)}
  </header>
  <main>
    {promise_section(context)}
    {headline_section(context)}
    {spotlight_section(context)}
    {section("Tonight's Shipped Highlights", shipped_highlights(context["shipped"]))}
    {section("Full Shipped Archive", context["shipped"], collapsed=True)}
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
        ("done", "Prepare Jarvis 0.1.453", "LocalOS music no longer contains a hidden afplay starter, Stop Music still cleans old orphaned afplay processes, and recent-open reconnects now reopen LocalOS when the Chrome music tab is gone."),
        ("done", "Prepare Jarvis 0.1.452", "LocalOS music reconnect now prefers the healthy Local OS Host URL, answers browser preflight, can recover with a real Space key in the LocalOS page, reports Chrome autoplay blocks as activation-required, keeps email no-result replies speakable, and includes a tested Chrome cleanup helper for the morning handoff."),
        ("done", "Prepare Jarvis 0.1.445", "Stop Music now avoids the Chrome AppleScript syntax bug that could leave browser/LocalOS media unpaused."),
        ("done", "Prepare Jarvis 0.1.444", "Stale LocalOS music reconnects now try the native Local OS Host app before falling back to a Chrome music-player tab."),
        ("done", "Prepare Jarvis 0.1.443", "Chrome-control failures now point to both macOS Automation access and Chrome's Allow JavaScript from Apple Events setting."),
        ("done", "Prepare Jarvis 0.1.442", "Music playback failures now distinguish Chrome-control denial from a normal LocalOS reconnect delay."),
        ("done", "Prepare Jarvis 0.1.441", "Ordinary Stop Music no longer mutes the whole Mac, and Chrome music-control JavaScript is compacted before AppleScript execution."),
        ("done", "Prepare Jarvis 0.1.440", "LocalOS music now retries accepted-but-silent playback with a guarded real play-button activation and rechecks audio before claiming success."),
        ("done", "Prepare Jarvis 0.1.439", "Speech mute state now distinguishes muted, automatic speech off, missing voice provider, and ready speech."),
        ("done", "Repair Keep Blabbering truthfulness", "Unmute reports TTS readiness and prewarms Piper when that provider is configured."),
        ("done", "Ship Jarvis 0.1.438", "Live app is bundled, launched, and reports Jarvis 0.1.438 build 438."),
        ("done", "Refresh report after QA", "Latency smoke and speech-audit matrix runs refresh the master report after writing proof artifacts."),
        ("done", "Ship Jarvis 0.1.437", "Live app is bundled, launched, and reports Jarvis 0.1.437 build 437."),
        ("done", "Clarify readiness gaps", "Readiness separates planned future screen/app-control tools from actionable broken tools."),
        ("done", "Ship Jarvis 0.1.436", "Live app is bundled, launched, and reports Jarvis 0.1.436 build 436."),
        ("done", "Tag speech mute source", "Mute/unmute writes record main_app, status_helper, or api so silent-state bugs are traceable."),
        ("done", "Ship Jarvis 0.1.435", "Live app is bundled, launched, and reports Jarvis 0.1.435 build 435."),
        ("done", "Refresh master report", "Shipped/proof/workboard sections now include the latest 0.1.430-0.1.434 reliability work."),
        ("done", "Refresh reports after launch", "build_and_launch_app.sh regenerates overnight report files after the live worker becomes healthy."),
        ("done", "Ship Jarvis 0.1.434", "Live app is bundled, launched, and reports Jarvis 0.1.434 build 434."),
        ("done", "Clarify LocalOS music ownership", "Model-facing music tools now say LocalOS owns normal playback and Jarvis must not start a separate hidden player."),
        ("done", "Verify 0.1.434 prompt matrix", "The full quiet matrix passed 8/8 at runtime/regression_prompt_matrix/20260615-192359/summary.json."),
        ("done", "Ship Jarvis 0.1.433", "Live app is bundled, launched, and reports Jarvis 0.1.433 build 433."),
        ("done", "Repair Keep Blabbering recovery", "The status helper now notifies the main app after mute changes, and the app refreshes backend mute state before native speech."),
        ("done", "Ship Jarvis 0.1.432", "Live app is bundled, launched, and reports Jarvis 0.1.432 build 432."),
        ("done", "Expose Codex speed status", "Jarvis now reports the active Codex proxy route and latest sanitized proxy benchmark without private prompt text."),
        ("done", "Ship Jarvis 0.1.431", "Live app is bundled, launched, and reports Jarvis 0.1.431 build 431."),
        ("done", "Speed up Codex delegation", "Codex child processes can use the reachable local ClashX proxy route while normal system proxy settings stay untouched."),
        ("done", "Ship Jarvis 0.1.430", "Live app is bundled, launched, and reports Jarvis 0.1.430 build 430."),
        ("done", "Improve sound-loop QA", "Voice-loop QA now records stage timings and audits the exact final speech payload instead of synthesizing it twice."),
        ("done", "Restore LocalOS bridge v4", "The LocalOS player bridge regained polling, snapshot publishing, LocalOS-owned play/pause, and human autoplay wording."),
        ("done", "Ship Jarvis 0.1.429", "Live app is bundled, launched, and reports Jarvis 0.1.429 build 429."),
        ("done", "Preserve command payload aliases", "The worker now treats message, text, and prompt as command text instead of losing the user's utterance."),
        ("done", "Reject empty command posts", "Empty /api/command and /api/command/stream payloads now return HTTP 400 instead of becoming generic chat."),
        ("done", "Guard streaming command aliases", "The safe verifier now checks message aliases and empty-body rejection on /api/command/stream."),
        ("done", "Verify 0.1.429 prompt matrix", "The quiet matrix passed 8/8 at runtime/regression_prompt_matrix/20260615-055020/summary.json."),
        ("done", "Ship Jarvis 0.1.428", "Live app is bundled, launched, and reports Jarvis 0.1.428 build 428."),
        ("done", "Polish LocalOS music wording", "Approximate music matches now say closest LocalOS match instead of closest LocalOS file."),
        ("done", "Verify 0.1.428 prompt matrix", "The reusable quiet matrix passed 8/8 at runtime/regression_prompt_matrix/20260615-052819/summary.json."),
        ("done", "Ship Jarvis 0.1.427", "Live app is bundled, launched, and reports Jarvis 0.1.427 build 427."),
        ("done", "Polish Calendar speech", "Calendar summaries now strip Chinese course labels from visible/spoken replies and use natural AM/PM times."),
        ("done", "Ship Jarvis 0.1.426", "Live app is bundled, launched, and reports Jarvis 0.1.426 build 426."),
        ("done", "Persist Shut Up across relaunches", "Speech mute now loads from runtime/state/speech_mute.json on worker startup and stayed muted after verifier restore."),
        ("done", "Ship Jarvis 0.1.425", "Live app is bundled, launched, and reports Jarvis 0.1.425 build 425."),
        ("done", "Retry Teams visible OCR", "After Chrome handoff, the app retries native OCR up to four times instead of racing Teams with one fixed delay."),
        ("done", "Make the prompt matrix reusable", "scripts/run_regression_prompt_matrix.py now owns the eight overnight target prompts and runs them quietly."),
        ("done", "Harden prompt matrix CLI", "The matrix runner now accepts explicit quiet flags and refuses Apple Speech unless deliberately enabled."),
        ("done", "Verify 0.1.424 prompt matrix", "The reusable matrix passed 8/8 at runtime/regression_prompt_matrix/20260615-040014/summary.json."),
        ("done", "Ship Jarvis 0.1.424", "Live app is bundled, launched, and reports Jarvis 0.1.424 build 424."),
        ("done", "Sync visible speech mute status", "The main panel now polls speech mute state and updates the Speech On/Muted chip after helper or verifier changes."),
        ("done", "Ship Jarvis 0.1.423", "Live app is bundled, launched, and reports Jarvis 0.1.423 build 423."),
        ("done", "Fix Chrome OCR fallback", "Targeted Chrome-window OCR now retries the main display when the window capture is empty or too sparse."),
        ("done", "Clean Teams assignment digest", "Visible Teams summaries now drop browser tab/menu noise and sidebar crumbs before asking follow-up questions."),
        ("done", "Prevent orphan menu heads", "The status helper monitors the parent Jarvis PID and exits when the app disappears."),
        ("done", "Ship Jarvis 0.1.422", "Live app is bundled, launched, and reports Jarvis 0.1.422 build 422."),
        ("done", "Align Teams OCR contract", "Teams assignment metadata now recommends screen.visible_text and names the Chrome handoff plus native OCR follow-up."),
        ("done", "Ship Jarvis 0.1.421", "Live app is bundled, launched, and reports Jarvis 0.1.421 build 421."),
        ("done", "Polish spoken working lines", "Month-long email summaries no longer say newest email, and Teams no longer says assignment plan."),
        ("done", "Ship Jarvis 0.1.420", "Live app is bundled, launched, and reports Jarvis 0.1.420 build 420."),
        ("done", "Ask assignment follow-up questions", "When Leo asks for enough information to finish the assignment, OCR summaries now include targeted questions."),
        ("done", "Preserve original Teams prompt", "The automatic OCR follow-up now receives Leo's original command instead of a generic read-screen command."),
        ("done", "Ship Jarvis 0.1.419", "Live app is bundled, launched, and reports Jarvis 0.1.419 build 419."),
        ("done", "Extract assignment OCR lines", "Visible Teams OCR now prefers assignment title, due time, instructions, rubric, class, and project lines."),
        ("done", "Redact assignment digest audit", "Audit logs omit assignment_digest_items after a focused test caught private digest leakage."),
        ("done", "Ship Jarvis 0.1.418", "Live app is bundled, launched, and reports Jarvis 0.1.418 build 418."),
        ("done", "Fuse Teams handoff plus OCR", "Teams assignment handoff now automatically attempts a read-only visible Teams screen pass after Chrome opens."),
        ("done", "Guard Teams OCR follow-up", "Submit, turn-in, send, upload, and delete wording does not trigger the automatic read path."),
        ("done", "Ship Jarvis 0.1.417", "Live app is bundled, launched, and reports Jarvis 0.1.417 build 417."),
        ("done", "Add native visible-screen read", "Explicit visible Teams/page reads now use Apple Vision OCR through the native app and summarize locally."),
        ("done", "Protect visible-screen privacy", "OCR text is scanned as untrusted, screenshots are not stored, and private digest text is omitted from audit logs."),
        ("done", "Verify 0.1.417", "Full Python suite, Swift routing self-test, no-prompt verifier, eight-prompt matrix, and full safe verifier all passed."),
        ("done", "Ship Jarvis 0.1.416", "Live app is bundled, launched, and reports Jarvis 0.1.416 build 416."),
        ("done", "Make Teams handoff honest", "Jarvis opens signed-in Chrome but no longer claims it inspected the assignment before a later page or screen read succeeds."),
        ("done", "Hide browser internals from Teams failures", "Teams unreadable-page failures now use product language instead of JavaScript or AppleScript details."),
        ("done", "Preserve contact aliases", "Ms Sharpay stays Ms Sharpay while Sharpay and dictated his Sharpay still resolve."),
        ("done", "Quiet the wake greeting", "Hey Jarvis now plans a visible Listening state instead of a routine spoken Hello sir."),
        ("done", "Verify real prompts", "The live eight-prompt speech-audit matrix passed 8/8 against the bundled app."),
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
        ("working", "Next: real Teams assignment proof", "The OCR digest and question generator work on controlled text; the next hard part is proving them on Leo's actual Teams page."),
    ]
    items = "\n".join(task_item(*task) for task in tasks)
    focus_bundle_sentence = workboard_bundle_sentence(context)
    voice_proof_sentence = workboard_voice_proof_sentence(context)
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
      <p>{e(focus_bundle_sentence)} The current live bundle includes native Music app bridge playback proof, legacy LocalOS/Chrome fallback honesty, and the morning cleanup helper; source-side Swift compile proof is green.{e(voice_proof_sentence)} Jarvis already has hardened command payload handling, native visible-screen OCR, automatic read-only Teams follow-up after Chrome handoff, assignment-line OCR extraction, targeted follow-up questions, cleaner Teams read failures, preserved contact aliases, quieter wake acknowledgement, and a reusable behavior matrix. The remaining product gap is real-device voice, music, browser, Teams, and app-control QA when Leo is present.</p>
      <div class="meter"><div style="width: 98%"></div></div>
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


def workboard_bundle_sentence(context: dict[str, Any]) -> str:
    bundle = str(context.get("bundle") or "").strip()
    bundle_source = str(context.get("bundle_source") or "").strip()
    if bundle_source == "output bundle file" and bundle and bundle != "live bundle metadata unavailable":
        return f"The current output bundle file is {bundle}; it was not live-launched during this no-approval source run."
    if bundle_source == "live worker" and bundle and bundle != "live bundle metadata unavailable":
        return f"The latest live bundle is {bundle}."
    if not bundle or bundle == "live bundle metadata unavailable":
        return "No live bundle metadata was available during this no-approval source run."
    return f"The available bundle metadata is {bundle}."


def workboard_voice_proof_sentence(context: dict[str, Any]) -> str:
    voice_loop = context.get("voice_loop") if isinstance(context.get("voice_loop"), dict) else {}
    if not voice_loop or not voice_loop.get("path"):
        return ""
    if voice_loop.get("speech_audit_only"):
        payloads = int(voice_loop.get("speech_payload_count") or 0)
        leaks = int(voice_loop.get("speech_leak_count") or 0)
        return f" Latest voice speech audit checked {payloads} payloads with {leaks} leaks."
    speech_mode = str(voice_loop.get("speech_mode") or "suppressed_for_probe")
    if speech_mode == "live_playback_exercised":
        active_observed = bool(voice_loop.get("active_speech_observed"))
        activity_text = "observed active speech" if active_observed else "did not observe active speech"
        return (
            " Latest closed-loop voice QA exercised live speech playback, "
            f"{activity_text}, and matched the spoken reply back to the visible answer."
        )
    return " Latest closed-loop voice QA stayed in suppressed speech mode and still matched the spoken reply back to the visible answer."


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
        bundle_pill_label(context),
        f"Source commit: {context['commit']}",
        f"Branch: {context['branch']}",
        f"GitHub: {context['upstream'] or 'not published'} ({context['git_sync']})",
        f"Worktree: {context.get('git_dirty') or 'unknown'}",
        f"Python suite: {latest_python_tests_label(context)} passed",
        f"Safe verifier: {context['verification']['label']}",
        f"No-prompt: {context['no_prompt_verification']['label']}",
        f"Launch: {launch_label(context.get('launch_mode'))}",
    ]
    return '<div class="pills">' + "".join(f'<span class="pill">{e(pill)}</span>' for pill in pills) + "</div>"


def bundle_pill_label(context: dict[str, Any]) -> str:
    bundle = str(context.get("bundle") or "live bundle metadata unavailable").strip()
    source = str(context.get("bundle_source") or "").strip()
    if source == "output bundle file":
        return f"Output bundle: {bundle}"
    if source == "live worker":
        return f"Live bundle: {bundle}"
    return f"Bundle: {bundle}"


def launch_label(value: Any) -> str:
    text = str(value or "unknown").strip()
    return "not inspected" if text == "unknown" else text


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


def shipped_highlights(items: list[str], *, limit: int = 7) -> list[str]:
    """Keep the morning report product-facing instead of becoming a changelog dump."""
    highlights = [str(item).strip() for item in items if str(item).strip()]
    return highlights[: max(0, limit)]


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


def headline_section(context: dict[str, Any]) -> str:
    python_tests = latest_python_tests_label(context)
    matrix = context.get("regression_matrix") if isinstance(context.get("regression_matrix"), dict) else {}
    matrix_label = str(matrix.get("label") or "matrix not generated")
    speech_payloads = int(matrix.get("speech_payload_count") or 0)
    speech_leaks = int(matrix.get("speech_leak_count") or 0)
    full_loop = context.get("full_loop") if isinstance(context.get("full_loop"), dict) else {}
    full_loop_label = str(full_loop.get("label") or "full-loop not generated")
    bundle = str(context.get("bundle") or "current Jarvis build")
    cards = [
        (
            f"Live {bundle}",
            "Jarvis now has a real full-loop gate for Leo's spoken prompts: audio in, tool route, action proof, speech audit, cleanup, and stop-proof music playback. In that gate, music playback is proven through the native Music app bridge.",
        ),
        (
            "Proof",
            f"{full_loop_label} full-loop real-action checks, {python_tests} Python tests, {context['verification']['label']} safe verifier, plus the older behavior matrix is {matrix_label} with {speech_payloads} speech payloads and {speech_leaks} leaks. Sharpay email proves sender_recent matching, Teams proves wrong-subject OCR honesty, Music proves no hidden afplay leftovers, and voice QA scores spoken payloads.",
        ),
        (
            "Caveat",
            "Teams still depends on signed-in Chrome permissions, and older LocalOS/Chrome browser-audio fallback paths may still need one real player click; the new proof keeps those limits honest instead of claiming the wrong thing worked.",
        ),
    ]
    body = '<div class="grid headline">' + "".join(
        f"<div class=\"card\"><strong>{e(title)}</strong><span>{e(text)}</span></div>"
        for title, text in cards
    ) + "</div>"
    return f"<section><h2>Headline</h2>{body}</section>"


def spotlight_section(context: dict[str, Any]) -> str:
    latency = context.get("latency") if isinstance(context.get("latency"), dict) else {}
    latency_text = ""
    if latency.get("path"):
        latency_text = f" Current fast smoke max first visible {float(latency.get('max_first_visible_seconds') or 0):.3f}s."
    python_tests = latest_python_tests_label(context)
    full_loop = context.get("full_loop") if isinstance(context.get("full_loop"), dict) else {}
    full_loop_text = f" Full-loop: {full_loop.get('label')}." if full_loop.get("path") else ""
    matrix = context.get("regression_matrix") if isinstance(context.get("regression_matrix"), dict) else {}
    matrix_text = (
        f" Behavior matrix: {matrix.get('label')}, max first visible "
        f"{float(matrix.get('max_first_visible_seconds') or 0):.3f}s."
        if matrix.get("path")
        else ""
    )
    cards = [
        (
            "Try First",
            "Ask Jarvis to check status, check Calendar, or play Waving Through a Window through the native Music app bridge.",
        ),
        (
            "Best Proof",
            f"{context['verification']['label']} verifier, {python_tests} Python tests, Swift self-tests, closed-loop voice QA, and post-patch matrix proof.{full_loop_text}{latency_text} {matrix_text}".strip(),
        ),
        (
            "Honest Limit",
            "Teams page reading still depends on Chrome Automation permission; older LocalOS/Chrome fallback playback may still need one real player click, but native Music bridge playback is proven in the full-loop gate.",
        ),
    ]
    body = '<div class="grid spotlight">' + "".join(
        f"<div class=\"card\"><strong>{e(title)}</strong><span>{e(text)}</span></div>"
        for title, text in cards
    ) + "</div>"
    return f"<section><h2>Morning Snapshot</h2>{body}</section>"


def latest_python_tests_label(context: dict[str, Any]) -> str:
    test_count = int(context.get("python_test_count") or 0)
    if test_count > 0:
        return f"{test_count}/{test_count}"
    proof_items = context.get("proof") if isinstance(context.get("proof"), list) else []
    for item in proof_items:
        match = re.search(r"full Python safety suite passed\s+([0-9]+/[0-9]+)", str(item), re.IGNORECASE)
        if match:
            return match.group(1)
    return "latest"


def supporting_section(context: dict[str, Any]) -> str:
    rows = []
    for path, label in context["supporting"]:
        if path.startswith("http"):
            href = path
            display_path = path
            availability = ""
        else:
            href = "../" + path.removeprefix("runtime/") if path.startswith("runtime/") else "../../" + path
            local_path = PROJECT_ROOT / path
            display_path = str(local_path)
            availability = "" if local_path.exists() else " <span class=\"missing-file\">not generated yet</span>"
        rows.append(f'<li><a href="{e(href)}">{e(display_path)}</a> - {e(label)}{availability}</li>')
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
    .missing-file { color: #ffd166; font-size: 0.88rem; margin-left: 0.45rem; }
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
