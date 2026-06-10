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
    "Speech diagnostics now include a short sanitized text preview, so Copy Chat JSON can show what TTS was asked to say.",
    "Copy Chat JSON turn traces now include speech-alignment diagnostics that flag tiny TTS previews such as Hello against longer visible answers.",
    "Hey Jarvis now pauses after immediate silent Apple Speech endings instead of repeatedly flashing the menu bar while it restarts.",
    "When Hey Jarvis pauses itself for stability, the app now adds a visible chat line explaining what happened.",
    "The master report and workboard now have read-only loopback URLs at /overnight-report/ and /overnight-workboard/.",
]

PROOF_ITEMS = [
    "Python safety suite: 423/423 passed after the wake, mute, final-speech, report-route, speech-alignment, model-selected device/app-routing, app-specific status-line, fuzzy-wake, stale-progress, anti-flicker, and voice-QA work.",
    "Swift build passed for the Jarvis menu-bar app.",
    "Swift self-tests passed, including menu-bar routing labels, native wake detection, and worker checks.",
    "Live safe verifier passed 97/97 after the speech-mute, wake-audition, wake-lab corpus, model-context, wake-debug, repeated-wake, voice-loop echo, and report-route endpoints were added.",
    "After Leo asked for no more permission prompts, the overnight checks stayed to no-prompt paths: Python suite, Swift self-test, live report route, wake lab route, speech mute alignment, model-context diagnostic, and voice-loop echo.",
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
    "Conversation-context smoke tests now verify the script mutes speech, restores the previous mute state, and detects whether a follow-up used prior history.",
    "Wake-threshold smoke tests now verify hey jervis passes while hey jars and hey charvis reject at the 0.86 threshold.",
    "Static wake-lab tests now require the threshold corpus panel, corpus buttons, and below-threshold charvis case.",
    "Static and verifier wake-lab tests now require the self-explanatory Live Transcript Only and Copy Codex JSON labels.",
    "Static wake-lab tests now require Copy JSON to include the selected corpus case.",
    "Swift source tests now require Shut Up to apply the target mute state immediately and still roll back on backend failure.",
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
    "Closed-loop voice QA now has a no-permission-prompts mode that skips Apple Speech and fails closed through local STT only.",
    "Latest voice-loop QA passed with Hey Jarvis status routed to status and 0.94 reply similarity.",
    "A 35-second app-bundle Hey Jarvis soak on Jarvis 0.1.279 returned successfully without a new crash report.",
    "Native Hey Jarvis now pauses itself if Apple Speech enters a rapid microphone restart loop, preventing the menu-bar flicker from becoming a crash spiral.",
    "Native Hey Jarvis also pauses if Apple Speech ends immediately without hearing speech, so a broken listener fails quiet instead of flickering.",
    "Copy Chat JSON now records listener_paused wake events when the app stops Hey Jarvis for stability.",
    "Local-only voice QA now fails closed: if STT returns an empty transcript, it does not route a fake status command.",
    "Swift self-tests now reject a tiny Hello TTS preview when the visible final answer is longer.",
    "Voice-loop QA tests now prove no-permission mode does not call the Apple Speech app path.",
    "The current live build launched cleanly after the anti-flicker cleanup.",
]

TRY_ITEMS = [
    "Open Jarvis from the Dock; it should be a normal app window, not an always-front overlay.",
    "Use the menu-bar item to click Start Hey Jarvis, then say Hey Jarvis followed by a short command.",
    "Try a one-breath command such as Hey Jarvis wake status; Jarvis should avoid a separate Yes sir? prompt and go straight into the task response.",
    "Use Shut Up if Jarvis is talking too much; use Keep Blabbering to restore speech.",
    "Ask for wake status or overnight status; Jarvis should speak the final answer, not only the Yes sir working line.",
    "Click Perms if Hey Jarvis does not listen; it should show which macOS permission is blocking the loop.",
    "Open the wake lab and record several Hey Jarvis samples in quiet and noisy conditions.",
    "Use the wake lab Copy JSON button if recognition feels wrong, then paste the JSON back to Codex.",
    "Use Copy Chat JSON after a failed wake attempt; it now includes wake detected and command captured events.",
]

RISK_ITEMS = [
    "Real microphone pickup, false wakes, and room-noise reliability still need Leo testing.",
    "Browser loopback noise trials are useful but not a perfect model of a real room.",
    "Speech Recognition permission can still block the native listener until macOS grants it to the current Jarvis bundle.",
    "Local-only faster-whisper STT is installed as a no-permission fallback path, but the tiny-model weight fetch still fails with connection reset and needs a stable retry before it can replace Apple Speech in overnight QA.",
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
        ),
        "try": TRY_ITEMS,
        "risks": RISK_ITEMS,
        "supporting": SUPPORTING_FILES,
    }


def proof_items_with_verification(
    verification: dict[str, Any],
    no_prompt_verification: dict[str, Any] | None = None,
    latency: dict[str, Any] | None = None,
    context_smoke: dict[str, Any] | None = None,
    wake_threshold: dict[str, Any] | None = None,
    voice_loop: dict[str, Any] | None = None,
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
            "covering only routes that do not request microphone, Speech Recognition, Screen Recording, Accessibility, app launch, or GitHub push."
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
    return items


def get_json(url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data if isinstance(data, dict) else {}
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return {}


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
    reports = sorted(report_root.glob("*/report.json"))
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
        }
    latest_path, latest_data = latest_readable
    proof_path, data = latest_passed or latest_readable
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    ok = result.get("status") == "passed"
    relative = str(proof_path.relative_to(PROJECT_ROOT))
    latest_result = latest_data.get("result") if isinstance(latest_data.get("result"), dict) else {}
    latest_command_stt = latest_result.get("command_stt") if isinstance(latest_result.get("command_stt"), dict) else {}
    summary = {
        "ok": ok,
        "path": relative,
        "label": "passed" if ok else "needs attention",
        "command_transcript": str(result.get("command_transcript") or ""),
        "routed_command": str(result.get("routed_command") or ""),
        "reply_similarity": float(result.get("reply_similarity") or 0.0),
        "latest_path": str(latest_path.relative_to(PROJECT_ROOT)),
        "latest_label": str(latest_result.get("status") or "unknown"),
        "latest_stt_provider": str(nested(latest_data, "input").get("stt_provider") or "auto"),
        "latest_command_stt_status": str(latest_command_stt.get("status") or "unknown"),
        "latest_command_stt_error": str(latest_command_stt.get("error") or ""),
        "latest_routed_command": str(latest_result.get("routed_command") or ""),
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
        ("done", "Add speech preview diagnostics", "Speech JSON now records the sanitized text_preview requested from TTS."),
        ("done", "Add speech-alignment trace", "Copy Chat JSON now flags when TTS preview text is too short to match the visible answer."),
        ("done", "Add closed-loop voice QA", "The harness compares Piper audio, STT transcript, Jarvis reply text, and spoken reply transcript."),
        ("done", "Add no-prompt voice QA mode", "Overnight runs can skip Apple Speech and fail closed through local STT only."),
        ("done", "Add local STT fallback hook", "faster-whisper is installed; the tiny model-weight fetch still hits a connection reset."),
        ("done", "Fail closed on empty local STT", "If local STT returns no transcript, the QA harness stops instead of routing a fake status command."),
        ("done", "Soak-test wake listener", "Jarvis 0.1.279 completed a 35-second app-bundle wake soak without a new crash report."),
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
            "Open Jarvis from the Dock, use Start Hey Jarvis from the menu bar, then try a short command.",
        ),
        (
            "Best Proof",
            f"{context['verification']['label']} verifier, 423/423 Python tests, Swift self-tests, and closed-loop voice QA.{latency_text}",
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
