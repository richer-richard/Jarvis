#!/usr/bin/env python3
"""Run Jarvis full-loop regressions with external action proof and cleanup."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.tools import (  # noqa: E402
    calendar_today_schedule,
    commerce_price_convert,
    contact_data_lookup,
    memory_usage_status,
    model_test_plan,
    outlook_read_only_check,
)
from jarvis.tools import codex_chat_plan  # noqa: E402
from scripts import voice_loop_qa  # noqa: E402
from scripts.render_overnight_status import normalize_base_url  # noqa: E402


REPORT_DIR = PROJECT_ROOT / "runtime" / "full_loop_regression"
DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_MUSIC_BRIDGE_URL = "http://127.0.0.1:47879"
DEFAULT_MUSIC_APP_BUNDLE_PATH = PROJECT_ROOT.parent / "Music App" / "dist" / "Music.app"


MUSIC_WAVING_CASE = {
    "id": "music_play_waving_through_window",
    "command": "Hey Jarvis, play Waving Through a Window.",
    "expect_tool": ["localos.music_play"],
    "expect_visible_contains": ["Music", "Dear Evan Hansen"],
    "expect_routed_contains": ["play", "Waving"],
    "latency_budget_seconds": 30.0,
}
RAM_ACTIVITY_CASE = {
    "id": "ram_activity_monitor",
    "command": "Hey Jarvis, check in Activity Monitor how much RAM my computer is using.",
    "expect_tool": ["diagnostics.memory_usage"],
    "expect_visible_contains": ["Memory", "GB"],
    "expect_routed_contains": ["Activity Monitor", "RAM"],
    "latency_budget_seconds": 30.0,
}
CALENDAR_TODAY_CASE = {
    "id": "calendar_today_schedule",
    "command": "Hey Jarvis, check my calendar for my schedule today.",
    "expect_tool": ["calendar.today_schedule"],
    "expect_visible_contains": ["Calendar"],
    "expect_routed_contains": ["calendar", "schedule"],
    "latency_budget_seconds": 30.0,
}
MAGIC_KEYBOARD_YUAN_CASE = {
    "id": "magic_keyboard_yuan",
    "command": "Hey Jarvis, search up the price of the Magic Keyboard and tell me its price converted to yuan.",
    "expect_tool": ["commerce.price_convert"],
    "expect_visible_contains": ["Magic Keyboard", "yuan"],
    "expect_routed_contains": ["Magic Keyboard"],
    "latency_budget_seconds": 45.0,
}
GEMMA_MODEL_PLAN_CASE = {
    "id": "gemma_model_plan",
    "command": "Hey Jarvis, test the Gemma 3 4B model for me.",
    "expect_tool": ["models.test_plan"],
    "expect_visible_contains": ["Gemma 3 4B"],
    "expect_routed_contains": ["Gemma", "4B"],
    "latency_budget_seconds": 35.0,
}
CODEX_DEFAULT_PLAN_CASE = {
    "id": "codex_default_plan",
    "command": "Hey Jarvis, open Codex and send a prompt called test in the Default chat.",
    "expect_tool": ["codex.chat_plan"],
    "expect_visible_contains": ["Default", "confirmation"],
    "expect_routed_contains": ["prompt", "test", "default"],
    "latency_budget_seconds": 35.0,
}
TEAMS_ASSIGNMENT_CASE = {
    "id": "teams_music_assignment_honesty",
    "command": (
        "Hey Jarvis, look in Teams for my newest Music assignment and ask me a list of questions "
        "to answer so that you have enough information to finish the assignment."
    ),
    "expect_tool": ["teams.assignment"],
    "expect_routed_contains": ["Teams", "Music"],
    "latency_budget_seconds": 45.0,
}
EMAIL_SHARPAY_CASE = {
    "id": "email_sharpay_month",
    "command": "Hey Jarvis, summarize all the emails from Ms. Sharpay in the past month.",
    "expect_tool": ["outlook.visible_summary"],
    "expect_routed_contains": ["Sharpay"],
    "latency_budget_seconds": 75.0,
}

FULL_LOOP_CASES: tuple[tuple[str, dict[str, Any]], ...] = (
    ("music", MUSIC_WAVING_CASE),
    ("ram", RAM_ACTIVITY_CASE),
    ("calendar", CALENDAR_TODAY_CASE),
    ("magic", MAGIC_KEYBOARD_YUAN_CASE),
    ("gemma", GEMMA_MODEL_PLAN_CASE),
    ("codex", CODEX_DEFAULT_PLAN_CASE),
    ("teams", TEAMS_ASSIGNMENT_CASE),
    ("email", EMAIL_SHARPAY_CASE),
)


def select_full_loop_cases(case_selection: str) -> list[dict[str, Any]]:
    if case_selection == "all":
        return [case for _, case in FULL_LOOP_CASES]
    return [case for key, case in FULL_LOOP_CASES if key == case_selection]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--music-bridge-url", default=DEFAULT_MUSIC_BRIDGE_URL)
    parser.add_argument("--output-dir", default=str(REPORT_DIR))
    parser.add_argument(
        "--case",
        choices=("music", "ram", "calendar", "magic", "gemma", "codex", "teams", "email", "all"),
        default="all",
    )
    parser.add_argument("--timeout", type=float, default=75.0)
    parser.add_argument("--exercise-live-speech", action="store_true")
    parser.add_argument(
        "--exercise-visible-navigation",
        action="store_true",
        help="Allow explicit UI navigation inside supported full-loop cases. Live clicks still require JARVIS_ALLOW_LIVE_UI_NAVIGATION=1.",
    )
    parser.add_argument("--no-report-refresh", action="store_true")
    args = parser.parse_args()

    base_url = normalize_base_url(args.base_url)
    run_dir = allocate_run_dir(Path(args.output_dir).resolve())
    suite_started = time.monotonic()
    cases = select_full_loop_cases(args.case)
    results = []
    for case in cases:
        if case["id"] == MUSIC_WAVING_CASE["id"]:
            results.append(
                run_music_waving_case(
                    case,
                    base_url=base_url,
                    music_bridge_url=args.music_bridge_url.rstrip("/"),
                    run_dir=run_dir / case["id"],
                    timeout=args.timeout,
                    exercise_live_speech=args.exercise_live_speech,
                )
            )
        elif case["id"] == RAM_ACTIVITY_CASE["id"]:
            results.append(
                run_ram_activity_case(
                    case,
                    base_url=base_url,
                    run_dir=run_dir / case["id"],
                    timeout=args.timeout,
                    exercise_live_speech=args.exercise_live_speech,
                )
            )
        elif case["id"] == CALENDAR_TODAY_CASE["id"]:
            results.append(
                run_calendar_today_case(
                    case,
                    base_url=base_url,
                    run_dir=run_dir / case["id"],
                    timeout=args.timeout,
                    exercise_live_speech=args.exercise_live_speech,
                )
            )
        elif case["id"] == MAGIC_KEYBOARD_YUAN_CASE["id"]:
            results.append(
                run_magic_keyboard_case(
                    case,
                    base_url=base_url,
                    run_dir=run_dir / case["id"],
                    timeout=args.timeout,
                    exercise_live_speech=args.exercise_live_speech,
                )
            )
        elif case["id"] == GEMMA_MODEL_PLAN_CASE["id"]:
            results.append(
                run_gemma_model_plan_case(
                    case,
                    base_url=base_url,
                    run_dir=run_dir / case["id"],
                    timeout=args.timeout,
                    exercise_live_speech=args.exercise_live_speech,
                )
            )
        elif case["id"] == CODEX_DEFAULT_PLAN_CASE["id"]:
            results.append(
                run_codex_default_plan_case(
                    case,
                    base_url=base_url,
                    run_dir=run_dir / case["id"],
                    timeout=args.timeout,
                    exercise_live_speech=args.exercise_live_speech,
                )
            )
        elif case["id"] == TEAMS_ASSIGNMENT_CASE["id"]:
            results.append(
                run_teams_assignment_case(
                    case,
                    base_url=base_url,
                    run_dir=run_dir / case["id"],
                    timeout=args.timeout,
                    exercise_live_speech=args.exercise_live_speech,
                    exercise_visible_navigation=args.exercise_visible_navigation,
                )
            )
        elif case["id"] == EMAIL_SHARPAY_CASE["id"]:
            results.append(
                run_email_sharpay_case(
                    case,
                    base_url=base_url,
                    run_dir=run_dir / case["id"],
                    timeout=args.timeout,
                    exercise_live_speech=args.exercise_live_speech,
                )
            )

    apply_latency_budgets(results, cases)
    passed = sum(1 for result in results if result.get("status") == "passed")
    failed = sum(1 for result in results if result.get("status") == "failed")
    warnings = sum(1 for result in results if result.get("status") == "warning")
    summary = make_suite_summary(
        base_url=base_url,
        run_dir=run_dir,
        case_selection=args.case,
        results=results,
        started=suite_started,
    )
    write_summary(summary, run_dir, Path(args.output_dir).resolve(), update_latest=bool(summary["canonical_latest"]))
    if not args.no_report_refresh:
        try:
            from scripts.report_refresh import refresh_report_surfaces_quietly

            summary["report_refresh"] = refresh_report_surfaces_quietly(base_url)
            write_summary(summary, run_dir, Path(args.output_dir).resolve(), update_latest=bool(summary["canonical_latest"]))
        except Exception as error:  # pragma: no cover - defensive live-only path.
            summary["report_refresh"] = {"ok": False, "error": f"{type(error).__name__}: {error}"}
            write_summary(summary, run_dir, Path(args.output_dir).resolve(), update_latest=bool(summary["canonical_latest"]))

    print(f"Report: {run_dir / 'summary.json'}")
    for result in results:
        print(f"{result['case_id']}: {result['status']} ({result.get('total_seconds')}s)")
    return 0 if summary["status"] == "passed" else 1


def make_suite_summary(
    *,
    base_url: str,
    run_dir: Path,
    case_selection: str,
    results: list[dict[str, Any]],
    started: float,
) -> dict[str, Any]:
    passed = sum(1 for result in results if result.get("status") == "passed")
    failed = sum(1 for result in results if result.get("status") == "failed")
    warnings = sum(1 for result in results if result.get("status") == "warning")
    return {
        "schema": "jarvis.full_loop_regression.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source_commit": git_commit_short(),
        "base_url": base_url,
        "run_dir": str(run_dir),
        "case_selection": case_selection,
        "canonical_latest": case_selection == "all",
        "status": "passed" if failed == 0 and warnings == 0 else "warning" if failed == 0 else "failed",
        "passed": passed,
        "warning": warnings,
        "failed": failed,
        "total": len(results),
        "duration_seconds": round(time.monotonic() - started, 3),
        "results": results,
    }


def git_commit_short() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def allocate_run_dir(output_dir: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    for suffix in ["", *[f"-{index:02d}" for index in range(2, 100)]]:
        candidate = output_dir / f"{stamp}{suffix}"
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue
    fallback = output_dir / f"{stamp}-{time.monotonic_ns()}"
    fallback.mkdir()
    return fallback


def apply_latency_budgets(results: list[dict[str, Any]], cases: list[dict[str, Any]]) -> None:
    case_by_id = {str(case.get("id") or ""): case for case in cases}
    for result in results:
        case = case_by_id.get(str(result.get("case_id") or ""))
        if not case:
            continue
        try:
            budget = float(case.get("latency_budget_seconds") or 0.0)
            elapsed = float(result.get("latency_measure_seconds") or result.get("total_seconds") or 0.0)
        except (TypeError, ValueError):
            budget = 0.0
            elapsed = 0.0
        if budget <= 0.0:
            continue
        result["latency_budget_seconds"] = round(budget, 3)
        result["latency_measure_seconds"] = round(elapsed, 3)
        result["latency_budget_status"] = "passed" if elapsed <= budget else "failed"
        if elapsed <= budget:
            continue
        warning = f"Case exceeded latency budget: {elapsed:.3f}s > {budget:.3f}s."
        warnings = result.get("warnings")
        if not isinstance(warnings, list):
            warnings = []
            result["warnings"] = warnings
        warnings.append(warning)
        result["status"] = "failed"


def chrome_memory_safety_snapshot(limit_mb: float = 12000.0) -> dict[str, Any]:
    """Return a fail-closed Chrome memory check before live browser automation."""
    try:
        completed = subprocess.run(
            ["/bin/ps", "-axo", "pid=,rss=,command="],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "ok": False,
            "status": "chrome_memory_unknown",
            "reason": f"Could not inspect Chrome memory: {type(error).__name__}",
            "limit_mb": round(float(limit_mb), 3),
            "total_mb": None,
            "processes": [],
        }
    if completed.returncode != 0:
        return {
            "ok": False,
            "status": "chrome_memory_unknown",
            "reason": (completed.stderr.strip() or "ps returned a non-zero exit code.")[-500:],
            "limit_mb": round(float(limit_mb), 3),
            "total_mb": None,
            "processes": [],
        }

    processes: list[dict[str, Any]] = []
    total_kb = 0
    for line in completed.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        pid_text, rss_text, command = parts
        if "Google Chrome" not in command:
            continue
        try:
            rss_kb = int(rss_text)
        except ValueError:
            continue
        total_kb += max(rss_kb, 0)
        processes.append({
            "pid": pid_text,
            "rss_mb": round(max(rss_kb, 0) / 1024.0, 3),
            "command_preview": command[:240],
        })

    total_mb = total_kb / 1024.0
    if not processes:
        return {
            "ok": True,
            "status": "chrome_not_running",
            "reason": "Google Chrome is not running.",
            "limit_mb": round(float(limit_mb), 3),
            "total_mb": 0.0,
            "processes": [],
        }
    if total_mb > float(limit_mb):
        return {
            "ok": False,
            "status": "chrome_memory_too_high",
            "reason": f"Google Chrome is using {total_mb:.1f} MB, above the {float(limit_mb):.1f} MB safety limit.",
            "limit_mb": round(float(limit_mb), 3),
            "total_mb": round(total_mb, 3),
            "processes": processes[:40],
        }
    return {
        "ok": True,
        "status": "chrome_memory_ok",
        "reason": f"Google Chrome is using {total_mb:.1f} MB, below the {float(limit_mb):.1f} MB safety limit.",
        "limit_mb": round(float(limit_mb), 3),
        "total_mb": round(total_mb, 3),
        "processes": processes[:40],
    }


def voice_loop_user_latency_seconds(voice_report: dict[str, Any]) -> float | None:
    """Return the user-facing voice loop time, excluding offline proof generation."""
    result = voice_report.get("result") if isinstance(voice_report.get("result"), dict) else {}
    timings = result.get("stage_timings")
    if not isinstance(timings, list):
        return _optional_float(result.get("total_seconds"))
    included_stages = {
        "command_stt",
        "wake_route",
        "jarvis_stream",
        "native_visible_screen_followup",
        "live_speech_runtime",
    }
    measured = 0.0
    found = False
    for item in timings:
        if not isinstance(item, dict):
            continue
        if str(item.get("stage") or "") not in included_stages:
            continue
        duration = _optional_float(item.get("duration_seconds"))
        if duration is None:
            continue
        measured += max(0.0, duration)
        found = True
    if found:
        return round(measured, 3)
    return _optional_float(result.get("total_seconds"))


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def run_music_waving_case(
    case: dict[str, Any],
    *,
    base_url: str,
    music_bridge_url: str,
    run_dir: Path,
    timeout: float,
    exercise_live_speech: bool,
) -> dict[str, Any]:
    started = time.monotonic()
    run_dir.mkdir(parents=True, exist_ok=True)
    cleanup: dict[str, Any] = {}
    result: dict[str, Any] | None = None
    before_afplay = afplay_process_snapshot()
    before_media_surfaces = media_playback_surface_snapshot()
    write_json(run_dir / "afplay-before.json", {"processes": before_afplay})
    write_json(run_dir / "media-surfaces-before.json", before_media_surfaces)
    try:
        preflight = ensure_music_bridge_ready(music_bridge_url)

        voice_report = voice_loop_qa.run_voice_loop(
            command_text=case["command"],
            base_url=base_url,
            run_dir=run_dir / "voice-loop",
            length_scale=0.85,
            timeout=timeout,
            stt_provider="local",
            no_permission_prompts=True,
            expect_tools=list(case["expect_tool"]),
            expect_visible_contains=list(case["expect_visible_contains"]),
            expect_routed_contains=list(case["expect_routed_contains"]),
            exercise_live_speech=exercise_live_speech,
            allow_audio_actions=True,
        )
        write_json(run_dir / "voice-loop-report.json", voice_report)
        playback = wait_for_music_playback(music_bridge_url, timeout=7.0)
        action_proof = verify_waving_playback(playback)
        status = "passed"
        warnings: list[str] = []
        voice_status = str(voice_report.get("result", {}).get("status") or "failed")
        music_voice_summary = music_voice_loop_result_summary(voice_report)
        if voice_status == "failed":
            status = "failed"
            warnings.append("Voice loop failed.")
        elif voice_status != "passed":
            if not action_proof.get("honest_permission_blocked"):
                status = "warning"
                warnings.append(f"Voice loop returned {voice_status}.")
        music_voice_warning = music_voice_loop_warning(music_voice_summary)
        if music_voice_warning:
            warnings.append(music_voice_warning)
        if not action_proof["passed"]:
            status = "failed"
            warnings.extend(action_proof["failures"])
        result = {
            "case_id": case["id"],
            "status": status,
            "warnings": warnings,
            "command": case["command"],
            "voice_loop_status": voice_status,
            "voice_loop_report": str(run_dir / "voice-loop-report.json"),
            "voice_loop_music_summary": music_voice_summary,
            "action_proof": action_proof,
            "preflight": preflight,
            "playback_state": playback,
            "cleanup": cleanup,
            "total_seconds": round(time.monotonic() - started, 3),
        }
        return result
    finally:
        cleanup["stop"] = music_bridge_request(music_bridge_url, "POST", "/stop", timeout=3.5)
        cleanup["post_playback_state"] = music_bridge_request(music_bridge_url, "GET", "/playback-state", timeout=3.5)
        cleanup["verified_stopped"] = (
            cleanup["post_playback_state"].get("ok") is True
            and cleanup["post_playback_state"].get("playing") is not True
        )
        cleanup["close_window"] = music_bridge_request(
            music_bridge_url,
            "POST",
            "/diagnostics/window-control-action",
            query={"action": "close"},
            timeout=3.5,
        )
        if result is not None:
            after_afplay = afplay_process_snapshot()
            after_media_surfaces = media_playback_surface_snapshot()
            cleanup["afplay_processes_after"] = after_afplay
            cleanup["new_afplay_processes_after"] = new_processes_since(before_afplay, after_afplay)
            cleanup["media_surfaces_after"] = after_media_surfaces
            cleanup["new_media_surfaces_after"] = new_media_surfaces_since(before_media_surfaces, after_media_surfaces)
            cleanup["new_blocked_media_inspections_after"] = new_blocked_media_inspections_since(
                before_media_surfaces,
                after_media_surfaces,
            )
            result["cleanup"] = cleanup
            result["total_seconds"] = round(time.monotonic() - started, 3)
            if not cleanup["verified_stopped"]:
                result["status"] = "failed"
                warnings = result.get("warnings")
                if not isinstance(warnings, list):
                    warnings = []
                    result["warnings"] = warnings
                warnings.append("Music cleanup did not verify playback stopped.")
            if cleanup["new_afplay_processes_after"]:
                result["status"] = "failed"
                warnings = result.get("warnings")
                if not isinstance(warnings, list):
                    warnings = []
                    result["warnings"] = warnings
                warnings.append("Music cleanup left a new hidden afplay process running.")
            if cleanup["new_media_surfaces_after"]:
                result["status"] = "failed"
                warnings = result.get("warnings")
                if not isinstance(warnings, list):
                    warnings = []
                    result["warnings"] = warnings
                warnings.append("Music cleanup left a new media playback surface running.")
            blocked_surfaces = cleanup["new_blocked_media_inspections_after"]
            if isinstance(blocked_surfaces, list) and "Google Chrome" in blocked_surfaces:
                if result.get("status") == "passed":
                    result["status"] = "warning"
                warnings = result.get("warnings")
                if not isinstance(warnings, list):
                    warnings = []
                    result["warnings"] = warnings
                warnings.append(
                    "Chrome media-surface inspection became blocked during the test, so this proof could not rule out hidden Chrome audio."
                )
        write_json(run_dir / "cleanup.json", cleanup)


def music_voice_loop_result_summary(voice_report: dict[str, Any]) -> dict[str, Any]:
    result = voice_report.get("result") if isinstance(voice_report.get("result"), dict) else {}
    summary = result.get("command_response_result") if isinstance(result.get("command_response_result"), dict) else {}
    if not summary:
        return {}
    return {
        key: summary.get(key)
        for key in (
            "tool",
            "played_by",
            "preferred_playback_owner",
            "playback_confirmation",
            "permission_issue",
            "requires_user_action",
            "jarvis_played_audio",
            "native_music_bridge_enabled",
            "legacy_localos_fallback_allowed",
            "spoken_summary",
            "reply",
            "music_app_attempt_status",
            "music_app_song_count",
            "music_app_library_source",
        )
        if key in summary
    }


def music_voice_loop_warning(summary: dict[str, Any]) -> str:
    if not summary:
        return ""
    confirmation = str(summary.get("playback_confirmation") or "").strip()
    permission_issue = str(summary.get("permission_issue") or "").strip()
    if confirmation == "music_app_library_empty" or permission_issue == "music_app_library_empty":
        song_count = summary.get("music_app_song_count")
        count_text = ""
        if song_count is not None:
            count_text = f" Music app bridge reports {song_count} songs."
        return (
            "Jarvis diagnosed the Music app library as empty and did not start hidden fallback audio."
            + count_text
        )
    reply = str(summary.get("reply") or summary.get("spoken_summary") or "").strip()
    if reply:
        return f"Jarvis Music reply: {reply}"
    return ""


def afplay_process_snapshot() -> list[dict[str, Any]]:
    completed = subprocess.run(
        ["ps", "ax", "-o", "pid=,command="],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    if completed.returncode != 0:
        return []
    processes: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        stripped = line.strip()
        if not stripped or "afplay" not in stripped:
            continue
        pid_text, _, command = stripped.partition(" ")
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        if not is_afplay_process_command(command):
            continue
        processes.append({"pid": pid, "command": command.strip()})
    return processes


def is_afplay_process_command(command: str) -> bool:
    try:
        parts = shlex.split(str(command or ""))
    except ValueError:
        parts = str(command or "").split()
    if not parts:
        return False
    executable = Path(parts[0]).name
    return executable == "afplay"


def new_processes_since(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[dict[str, Any]]:
    before_pids = {int(item.get("pid")) for item in before if isinstance(item.get("pid"), int)}
    return [item for item in after if isinstance(item.get("pid"), int) and int(item["pid"]) not in before_pids]


def media_playback_surface_snapshot() -> dict[str, Any]:
    """Inspect app-level playback surfaces without reading page text or pausing audio."""
    chrome_js = "Array.from(document.querySelectorAll('audio,video')).filter(function(el){ return !el.paused && !el.ended; }).length.toString();"
    attempts = {
        "music": _media_surface_osascript(
            '''
if application "Music" is running then
    try
        tell application id "com.apple.Music"
            if player state is playing then return "Music"
        end tell
    end try
end if
return "none"
'''.strip(),
            timeout=0.8,
        ),
        "quicktime": _media_surface_osascript(
            '''
if application "QuickTime Player" is running then
    try
        tell application "QuickTime Player"
            repeat with quickTimeDocument in documents
                if playing of quickTimeDocument is true then return "QuickTime Player"
            end repeat
        end tell
    end try
end if
return "none"
'''.strip(),
            timeout=0.8,
        ),
        "chrome": _media_surface_osascript(
            f'''
set lf to ASCII character 10
set outputLines to {{}}
if application "Google Chrome" is running then
    try
        tell application "Google Chrome"
            repeat with chromeWindow in windows
                repeat with chromeTab in tabs of chromeWindow
                    try
                        set playingCount to execute javascript "{escape_applescript_string(chrome_js)}" in chromeTab
                        if playingCount is not "0" then set end of outputLines to "Google Chrome"
                    end try
                end repeat
            end repeat
        end tell
    end try
end if
if (count of outputLines) is 0 then return "none"
set AppleScript's text item delimiters to lf
set joinedOutput to outputLines as text
set AppleScript's text item delimiters to ""
return joinedOutput
'''.strip(),
            timeout=2.5,
        ),
    }
    surfaces: set[str] = set()
    blocked: list[str] = []
    for name, attempt in attempts.items():
        stdout = str(attempt.get("stdout") or "").strip()
        if attempt.get("ok") and stdout and stdout != "none":
            surfaces.update(line.strip() for line in stdout.splitlines() if line.strip() and line.strip() != "none")
        stderr = str(attempt.get("stderr") or "")
        if name == "chrome" and not attempt.get("ok") and ("Access not allowed" in stderr or "-1723" in stderr):
            blocked.append("Google Chrome")
    return {
        "surfaces": sorted(surfaces),
        "blocked": sorted(blocked),
        "attempts": attempts,
    }


def _media_surface_osascript(script: str, *, timeout: float) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "executed": True, "stdout": "", "stderr": "timeout", "returncode": None}
    except OSError as error:
        return {"ok": False, "executed": False, "stdout": "", "stderr": str(error), "returncode": None}
    return {
        "ok": completed.returncode == 0,
        "executed": True,
        "stdout": (completed.stdout or "").strip(),
        "stderr": (completed.stderr or "").strip(),
        "returncode": completed.returncode,
    }


def new_media_surfaces_since(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    before_surfaces = {str(item) for item in before.get("surfaces", [])}
    after_surfaces = {str(item) for item in after.get("surfaces", [])}
    return sorted(after_surfaces - before_surfaces)


def new_blocked_media_inspections_since(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    before_blocked = {str(item) for item in before.get("blocked", [])}
    after_blocked = {str(item) for item in after.get("blocked", [])}
    return sorted(after_blocked - before_blocked)


def wait_for_music_playback(music_bridge_url: str, *, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_state: dict[str, Any] = {}
    while True:
        state = music_bridge_request(music_bridge_url, "GET", "/playback-state", timeout=3.5)
        last_state = state
        playback_seconds = _music_playback_seconds(state.get("currentTime"))
        if bool(state.get("playing")) and playback_seconds is not None and playback_seconds >= 0.5:
            return state
        if time.monotonic() >= deadline:
            return last_state
        time.sleep(0.25)


def ensure_music_bridge_ready(music_bridge_url: str, *, timeout: float = 6.0) -> dict[str, Any]:
    health = music_bridge_request(music_bridge_url, "GET", "/health", timeout=2.0, auth=False)
    if health.get("ok") is True:
        return health
    startup: dict[str, Any] = {
        "attempted": False,
        "app_path": str(DEFAULT_MUSIC_APP_BUNDLE_PATH),
        "initial_health": health,
    }
    if not DEFAULT_MUSIC_APP_BUNDLE_PATH.exists():
        return {
            "ok": False,
            "error": "music_app_bundle_missing",
            "startup": startup,
        }
    try:
        completed = subprocess.run(
            ["/usr/bin/open", str(DEFAULT_MUSIC_APP_BUNDLE_PATH)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
        startup.update({
            "attempted": True,
            "returncode": completed.returncode,
            "stderr": (completed.stderr or "").strip()[-500:],
        })
    except subprocess.TimeoutExpired:
        startup.update({"attempted": True, "error": "open_timeout"})
        return {"ok": False, "error": "music_app_open_timeout", "startup": startup}
    except OSError as error:
        startup.update({"attempted": True, "error": str(error)})
        return {"ok": False, "error": "music_app_open_failed", "startup": startup}

    deadline = time.monotonic() + max(0.0, timeout)
    last_health = health
    while True:
        last_health = music_bridge_request(music_bridge_url, "GET", "/health", timeout=1.0, auth=False)
        if last_health.get("ok") is True:
            return {**last_health, "startup": startup}
        if time.monotonic() >= deadline:
            return {"ok": False, "error": "music_bridge_unreachable_after_open", "health": last_health, "startup": startup}
        time.sleep(0.25)


def _music_playback_seconds(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def verify_waving_playback(playback_state: dict[str, Any]) -> dict[str, Any]:
    now_playing = playback_state.get("nowPlaying") if isinstance(playback_state.get("nowPlaying"), dict) else {}
    title = str(now_playing.get("title") or "")
    file_name = str(now_playing.get("fileName") or "")
    current_time = _music_playback_seconds(playback_state.get("currentTime"))
    haystack = f"{title} {file_name}".casefold()
    failures: list[str] = []
    if not playback_state.get("playing"):
        failures.append("Music app did not report active playback.")
    if current_time is None or current_time < 0.5:
        failures.append("Music app did not show playback progress.")
    if "dear evan hansen" not in haystack:
        failures.append("Selected track was not the Dear Evan Hansen recording.")
    if "tony awards" not in haystack:
        failures.append("Selected track was not the expected Tony Awards video audio.")
    if "through the fire and flames" in haystack:
        failures.append("Regressed to the old DragonForce false match.")
    return {
        "passed": not failures,
        "failures": failures,
        "selected_title": title,
        "selected_file_name": file_name,
        "selected_current_time": current_time,
    }


def run_ram_activity_case(
    case: dict[str, Any],
    *,
    base_url: str,
    run_dir: Path,
    timeout: float,
    exercise_live_speech: bool,
) -> dict[str, Any]:
    started = time.monotonic()
    run_dir.mkdir(parents=True, exist_ok=True)
    voice_report = voice_loop_qa.run_voice_loop(
        command_text=case["command"],
        base_url=base_url,
        run_dir=run_dir / "voice-loop",
        length_scale=0.85,
        timeout=timeout,
        stt_provider="local",
        no_permission_prompts=True,
        expect_tools=list(case["expect_tool"]),
        expect_visible_contains=list(case["expect_visible_contains"]),
        expect_routed_contains=list(case["expect_routed_contains"]),
        exercise_live_speech=exercise_live_speech,
        allow_audio_actions=False,
    )
    write_json(run_dir / "voice-loop-report.json", voice_report)
    memory_proof = memory_usage_status()
    write_json(run_dir / "memory-proof.json", memory_proof)
    action_proof = verify_memory_usage(memory_proof)
    route_proof = verify_voice_route_source(
        voice_report,
        expected_tool="diagnostics.memory_usage",
        expected_sources={"model_tool_call"},
    )
    action_proof["route_source"] = route_proof.get("route_source")
    action_proof["route_source_passed"] = route_proof["passed"]
    status = "passed"
    warnings: list[str] = []
    voice_status = str(voice_report.get("result", {}).get("status") or "failed")
    if voice_status == "failed":
        status = "failed"
        warnings.append("Voice loop failed.")
    elif voice_status != "passed":
        status = "warning"
        warnings.append(f"Voice loop returned {voice_status}.")
    if not action_proof["passed"]:
        status = "failed"
        warnings.extend(action_proof["failures"])
    if not route_proof["passed"]:
        status = "failed"
        warnings.extend(route_proof["failures"])
    return {
        "case_id": case["id"],
        "status": status,
        "warnings": warnings,
        "command": case["command"],
        "voice_loop_status": voice_status,
        "voice_loop_report": str(run_dir / "voice-loop-report.json"),
        "action_proof": action_proof,
        "memory_proof": memory_proof,
        "cleanup": {"required": False, "reason": "Read-only memory check does not open apps or start playback."},
        "total_seconds": round(time.monotonic() - started, 3),
    }


def verify_memory_usage(memory_proof: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    if memory_proof.get("tool") != "diagnostics.memory_usage":
        failures.append("Memory proof did not come from diagnostics.memory_usage.")
    if memory_proof.get("status") != "checked":
        failures.append("Memory proof did not report checked status.")
    if not memory_proof.get("activity_monitor_equivalent"):
        failures.append("Memory proof was not marked Activity Monitor equivalent.")
    if not memory_proof.get("vm_stat_available"):
        failures.append("vm_stat was not available for memory proof.")
    try:
        total_bytes = int(memory_proof.get("total_bytes") or 0)
        used_bytes = int(memory_proof.get("used_bytes") or 0)
        percent_used = float(memory_proof.get("percent_used") or 0.0)
    except (TypeError, ValueError):
        total_bytes = 0
        used_bytes = 0
        percent_used = 0.0
    if total_bytes <= 0:
        failures.append("Total memory bytes were not positive.")
    if used_bytes <= 0:
        failures.append("Used memory bytes were not positive.")
    if not 0.0 < percent_used <= 100.0:
        failures.append("Memory percent used was outside 0-100.")
    return {
        "passed": not failures,
        "failures": failures,
        "used_human": str(memory_proof.get("used_human") or ""),
        "total_human": str(memory_proof.get("total_human") or ""),
        "percent_used": percent_used,
        "memory_pressure": str(memory_proof.get("memory_pressure") or ""),
    }


def run_calendar_today_case(
    case: dict[str, Any],
    *,
    base_url: str,
    run_dir: Path,
    timeout: float,
    exercise_live_speech: bool,
) -> dict[str, Any]:
    started = time.monotonic()
    run_dir.mkdir(parents=True, exist_ok=True)
    voice_report = voice_loop_qa.run_voice_loop(
        command_text=case["command"],
        base_url=base_url,
        run_dir=run_dir / "voice-loop",
        length_scale=0.85,
        timeout=timeout,
        stt_provider="local",
        no_permission_prompts=True,
        expect_tools=list(case["expect_tool"]),
        expect_visible_contains=list(case["expect_visible_contains"]),
        expect_routed_contains=list(case["expect_routed_contains"]),
        exercise_live_speech=exercise_live_speech,
        allow_audio_actions=False,
    )
    write_json(run_dir / "voice-loop-report.json", voice_report)
    calendar_proof = calendar_today_schedule()
    write_json(run_dir / "calendar-proof.json", calendar_proof)
    action_proof = verify_calendar_today(calendar_proof)
    route_proof = verify_voice_route_source(
        voice_report,
        expected_tool="calendar.today_schedule",
        expected_sources={"model_tool_call"},
    )
    action_proof["route_source"] = route_proof.get("route_source")
    action_proof["route_source_passed"] = route_proof["passed"]
    status = "passed"
    warnings: list[str] = []
    voice_status = str(voice_report.get("result", {}).get("status") or "failed")
    if voice_status == "failed":
        status = "failed"
        warnings.append("Voice loop failed.")
    elif voice_status != "passed":
        status = "warning"
        warnings.append(f"Voice loop returned {voice_status}.")
    if not action_proof["passed"]:
        status = "failed"
        warnings.extend(action_proof["failures"])
    if not route_proof["passed"]:
        status = "failed"
        warnings.extend(route_proof["failures"])
    return {
        "case_id": case["id"],
        "status": status,
        "warnings": warnings,
        "command": case["command"],
        "voice_loop_status": voice_status,
        "voice_loop_report": str(run_dir / "voice-loop-report.json"),
        "action_proof": action_proof,
        "calendar_proof": calendar_proof,
        "cleanup": {"required": False, "reason": "Read-only Calendar check does not open apps or change events."},
        "total_seconds": round(time.monotonic() - started, 3),
    }


def verify_calendar_today(calendar_proof: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    if calendar_proof.get("tool") != "calendar.today_schedule":
        failures.append("Calendar proof did not come from calendar.today_schedule.")
    if calendar_proof.get("status") != "checked":
        failures.append("Calendar proof did not report checked status.")
    if not calendar_proof.get("read_private_content"):
        failures.append("Calendar proof did not mark itself as a private-content read.")
    if calendar_proof.get("changed_calendar"):
        failures.append("Calendar proof says it changed the calendar.")
    try:
        event_count = int(calendar_proof.get("event_count") or 0)
    except (TypeError, ValueError):
        event_count = 0
    if event_count < 0:
        failures.append("Calendar event count was negative.")
    if not str(calendar_proof.get("reply") or "").strip():
        failures.append("Calendar proof did not include a reply.")
    return {
        "passed": not failures,
        "failures": failures,
        "event_count": event_count,
        "source": str(calendar_proof.get("source") or ""),
        "changed_calendar": bool(calendar_proof.get("changed_calendar")),
    }


def run_magic_keyboard_case(
    case: dict[str, Any],
    *,
    base_url: str,
    run_dir: Path,
    timeout: float,
    exercise_live_speech: bool,
) -> dict[str, Any]:
    started = time.monotonic()
    run_dir.mkdir(parents=True, exist_ok=True)
    voice_report = voice_loop_qa.run_voice_loop(
        command_text=case["command"],
        base_url=base_url,
        run_dir=run_dir / "voice-loop",
        length_scale=0.85,
        timeout=max(timeout, 90.0),
        stt_provider="local",
        no_permission_prompts=True,
        expect_tools=list(case["expect_tool"]),
        expect_visible_contains=list(case["expect_visible_contains"]),
        expect_routed_contains=list(case["expect_routed_contains"]),
        exercise_live_speech=exercise_live_speech,
        allow_audio_actions=False,
    )
    write_json(run_dir / "voice-loop-report.json", voice_report)
    commerce_proof = commerce_proof_from_voice_report(voice_report)
    if not commerce_proof:
        commerce_proof = commerce_price_convert("Magic Keyboard", target_currency="CNY", source_country="US")
    write_json(run_dir / "commerce-proof.json", commerce_proof)
    action_proof = verify_magic_keyboard_yuan(commerce_proof)
    route_proof = verify_voice_route_source(
        voice_report,
        expected_tool="commerce.price_convert",
        expected_sources={"model_tool_call"},
    )
    action_proof["route_source"] = route_proof.get("route_source")
    action_proof["route_source_passed"] = route_proof["passed"]
    status = "passed"
    warnings: list[str] = []
    voice_status = str(voice_report.get("result", {}).get("status") or "failed")
    if voice_status == "failed":
        status = "failed"
        warnings.append("Voice loop failed.")
    elif voice_status != "passed":
        status = "warning"
        warnings.append(f"Voice loop returned {voice_status}.")
    if not action_proof["passed"]:
        status = "failed"
        warnings.extend(action_proof["failures"])
    if not route_proof["passed"]:
        status = "failed"
        warnings.extend(route_proof["failures"])
    return {
        "case_id": case["id"],
        "status": status,
        "warnings": warnings,
        "command": case["command"],
        "voice_loop_status": voice_status,
        "voice_loop_report": str(run_dir / "voice-loop-report.json"),
        "action_proof": action_proof,
        "commerce_proof": commerce_proof,
        "cleanup": {"required": False, "reason": "Public web price check does not open browser tabs."},
        "latency_measure_seconds": voice_loop_user_latency_seconds(voice_report),
        "latency_measure_source": "voice_loop_user_stages_excluding_synthetic_tts_and_offline_speech_audit",
        "total_seconds": round(time.monotonic() - started, 3),
    }


def commerce_proof_from_voice_report(voice_report: dict[str, Any]) -> dict[str, Any]:
    result = voice_report.get("result") if isinstance(voice_report.get("result"), dict) else {}
    summary = result.get("command_response_result") if isinstance(result.get("command_response_result"), dict) else {}
    if summary.get("tool") != "commerce.price_convert" and result.get("command_response_tool") != "commerce.price_convert":
        return {}
    required_dicts = ("source", "price", "exchange_rate", "converted")
    if not all(isinstance(summary.get(key), dict) and summary.get(key) for key in required_dicts):
        return {}
    return {
        "tool": "commerce.price_convert",
        "status": summary.get("status"),
        "source": summary.get("source"),
        "price": summary.get("price"),
        "exchange_rate": summary.get("exchange_rate"),
        "converted": summary.get("converted"),
        "opened_browser": bool(summary.get("opened_browser")),
        "changed_browser_state": bool(summary.get("changed_browser_state")),
        "reply": summary.get("reply"),
        "proof_source": "voice_loop_command_response",
        "route_source": summary.get("route_source"),
    }


def verify_voice_route_source(
    voice_report: dict[str, Any],
    *,
    expected_tool: str,
    expected_sources: set[str],
) -> dict[str, Any]:
    result = voice_report.get("result") if isinstance(voice_report.get("result"), dict) else {}
    summary = result.get("command_response_result") if isinstance(result.get("command_response_result"), dict) else {}
    actual_tool = str(result.get("command_response_tool") or summary.get("tool") or "")
    route_source = str(summary.get("route_source") or "")
    failures: list[str] = []
    if actual_tool != expected_tool:
        failures.append(f"Voice-loop command used {actual_tool or 'no tool'}, expected {expected_tool}.")
    if route_source not in expected_sources:
        allowed = ", ".join(sorted(expected_sources))
        failures.append(f"Voice-loop route source was {route_source or 'missing'}, expected one of: {allowed}.")
    return {
        "passed": not failures,
        "failures": failures,
        "tool": actual_tool,
        "route_source": route_source,
        "expected_sources": sorted(expected_sources),
    }


def verify_magic_keyboard_yuan(commerce_proof: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    source = commerce_proof.get("source") if isinstance(commerce_proof.get("source"), dict) else {}
    price = commerce_proof.get("price") if isinstance(commerce_proof.get("price"), dict) else {}
    exchange = commerce_proof.get("exchange_rate") if isinstance(commerce_proof.get("exchange_rate"), dict) else {}
    converted = commerce_proof.get("converted") if isinstance(commerce_proof.get("converted"), dict) else {}
    if commerce_proof.get("tool") != "commerce.price_convert":
        failures.append("Commerce proof did not come from commerce.price_convert.")
    if commerce_proof.get("status") != "converted":
        failures.append("Commerce proof did not report converted status.")
    if commerce_proof.get("opened_browser") or commerce_proof.get("changed_browser_state"):
        failures.append("Commerce proof opened or changed browser state.")
    if source.get("source_type") != "official_product_page" or source.get("brand") != "Apple":
        failures.append("Commerce proof did not use an official Apple product page.")
    if price.get("currency") != "USD" or float(price.get("amount") or 0.0) <= 0.0:
        failures.append("Commerce proof did not include a positive USD price.")
    if exchange.get("target") != "CNY" or float(exchange.get("rate") or 0.0) <= 0.0:
        failures.append("Commerce proof did not include a positive CNY exchange rate.")
    if converted.get("currency") != "CNY" or float(converted.get("amount") or 0.0) <= 0.0:
        failures.append("Commerce proof did not include a positive CNY conversion.")
    reply = str(commerce_proof.get("reply") or "")
    if "Magic Keyboard" not in reply or "yuan" not in reply:
        failures.append("Commerce proof reply did not mention Magic Keyboard and yuan.")
    return {
        "passed": not failures,
        "failures": failures,
        "source_label": str(source.get("label") or ""),
        "price": str(price.get("formatted_price") or ""),
        "converted": str(converted.get("formatted") or ""),
        "rate": float(exchange.get("rate") or 0.0),
    }


def run_gemma_model_plan_case(
    case: dict[str, Any],
    *,
    base_url: str,
    run_dir: Path,
    timeout: float,
    exercise_live_speech: bool,
) -> dict[str, Any]:
    started = time.monotonic()
    run_dir.mkdir(parents=True, exist_ok=True)
    voice_report = voice_loop_qa.run_voice_loop(
        command_text=case["command"],
        base_url=base_url,
        run_dir=run_dir / "voice-loop",
        length_scale=0.85,
        timeout=timeout,
        stt_provider="local",
        no_permission_prompts=True,
        expect_tools=list(case["expect_tool"]),
        expect_visible_contains=list(case["expect_visible_contains"]),
        expect_routed_contains=list(case["expect_routed_contains"]),
        exercise_live_speech=exercise_live_speech,
        allow_audio_actions=False,
    )
    write_json(run_dir / "voice-loop-report.json", voice_report)
    model_proof = model_test_plan("Gemma 3 4B", prompt="Test the Gemma 3 4B model for me.")
    write_json(run_dir / "model-proof.json", model_proof)
    action_proof = verify_gemma_model_plan(model_proof)
    status = "passed"
    warnings: list[str] = []
    voice_status = str(voice_report.get("result", {}).get("status") or "failed")
    if voice_status == "failed":
        status = "failed"
        warnings.append("Voice loop failed.")
    elif voice_status != "passed":
        status = "warning"
        warnings.append(f"Voice loop returned {voice_status}.")
    if not action_proof["passed"]:
        status = "failed"
        warnings.extend(action_proof["failures"])
    return {
        "case_id": case["id"],
        "status": status,
        "warnings": warnings,
        "command": case["command"],
        "voice_loop_status": voice_status,
        "voice_loop_report": str(run_dir / "voice-loop-report.json"),
        "action_proof": action_proof,
        "model_proof": model_proof,
        "cleanup": {"required": False, "reason": "Model test plan must not load or run the model locally."},
        "total_seconds": round(time.monotonic() - started, 3),
    }


def verify_gemma_model_plan(model_proof: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    if model_proof.get("tool") != "models.test_plan":
        failures.append("Model proof did not come from models.test_plan.")
    if model_proof.get("status") != "planned":
        failures.append("Model proof did not report planned status.")
    if model_proof.get("ran_model"):
        failures.append("Model proof says it ran a model.")
    if model_proof.get("changed_system_state"):
        failures.append("Model proof says it changed system state.")
    preferred_lane = str(model_proof.get("preferred_lane") or "")
    remote_status = str((model_proof.get("remote_worker") or {}).get("status") or "")
    if preferred_lane == "remote_macbook_air":
        pass
    elif preferred_lane == "ask_before_local" and remote_status not in {"available", "reachable"}:
        pass
    else:
        failures.append("Model proof did not prefer the MacBook Air lane or ask before local fallback.")
    if "Gemma 3 4B" not in str(model_proof.get("model") or ""):
        failures.append("Model proof did not preserve Gemma 3 4B.")
    reply = str(model_proof.get("reply") or "")
    local_guardrail = "not on this Mac" in reply or "ask before running" in reply
    if "MacBook Air" not in reply or not local_guardrail:
        failures.append("Model proof reply did not explain the remote-first local guardrail.")
    return {
        "passed": not failures,
        "failures": failures,
        "model": str(model_proof.get("model") or ""),
        "preferred_lane": preferred_lane,
        "remote_status": remote_status,
        "ran_model": bool(model_proof.get("ran_model")),
    }


def run_codex_default_plan_case(
    case: dict[str, Any],
    *,
    base_url: str,
    run_dir: Path,
    timeout: float,
    exercise_live_speech: bool,
) -> dict[str, Any]:
    started = time.monotonic()
    run_dir.mkdir(parents=True, exist_ok=True)
    voice_report = voice_loop_qa.run_voice_loop(
        command_text=case["command"],
        base_url=base_url,
        run_dir=run_dir / "voice-loop",
        length_scale=0.85,
        timeout=timeout,
        stt_provider="local",
        no_permission_prompts=True,
        expect_tools=list(case["expect_tool"]),
        expect_visible_contains=list(case["expect_visible_contains"]),
        expect_routed_contains=list(case["expect_routed_contains"]),
        exercise_live_speech=exercise_live_speech,
        allow_audio_actions=False,
    )
    write_json(run_dir / "voice-loop-report.json", voice_report)
    voice_result = voice_report.get("result") if isinstance(voice_report.get("result"), dict) else {}
    routed_command = str(voice_result.get("routed_command") or case["command"])
    codex_proof = codex_chat_plan(routed_command)
    write_json(run_dir / "codex-proof.json", codex_proof)
    action_proof = verify_codex_default_plan(codex_proof, voice_report=voice_report)
    status = "passed"
    warnings: list[str] = []
    voice_status = str(voice_report.get("result", {}).get("status") or "failed")
    if voice_status == "failed":
        status = "failed"
        warnings.append("Voice loop failed.")
    elif voice_status != "passed":
        status = "warning"
        warnings.append(f"Voice loop returned {voice_status}.")
    if not action_proof["passed"]:
        status = "failed"
        warnings.extend(action_proof["failures"])
    return {
        "case_id": case["id"],
        "status": status,
        "warnings": warnings,
        "command": case["command"],
        "voice_loop_status": voice_status,
        "voice_loop_report": str(run_dir / "voice-loop-report.json"),
        "action_proof": action_proof,
        "codex_proof": codex_proof,
        "cleanup": {"required": False, "reason": "Safety-gated Codex plan must not start a Codex job."},
        "total_seconds": round(time.monotonic() - started, 3),
    }


def verify_codex_default_plan(codex_proof: dict[str, Any], *, voice_report: dict[str, Any] | None = None) -> dict[str, Any]:
    failures: list[str] = []
    voice_result = voice_report.get("result") if isinstance(voice_report, dict) and isinstance(voice_report.get("result"), dict) else {}
    routed_command = str(voice_result.get("routed_command") or "")
    command_transcript = str(voice_result.get("command_transcript") or "")
    voice_tool = str(voice_result.get("command_response_tool") or "")
    alias_text = f"{routed_command} {command_transcript}".casefold()
    alias_detected = any(alias in alias_text for alias in ("codex", "cortex", "kodak"))
    if codex_proof.get("tool") != "codex.chat_plan":
        failures.append("Codex proof did not come from codex.chat_plan.")
    if codex_proof.get("status") != "planned":
        failures.append("Codex proof did not report planned status.")
    if voice_report is not None and voice_tool != "codex.chat_plan":
        failures.append(f"Voice-loop command used {voice_tool or 'no tool'}, expected codex.chat_plan.")
    if voice_report is not None and not alias_detected:
        failures.append("Voice-loop Codex proof did not preserve a Codex/Cortex/Kodak routed command.")
    if codex_proof.get("called_codex") or codex_proof.get("started_codex_job") or codex_proof.get("sent_prompt_to_codex"):
        failures.append("Codex proof unexpectedly sent or started Codex.")
    if str(codex_proof.get("selected_chat_name") or "") != "Default":
        failures.append("Codex proof did not select the Default chat.")
    if not codex_proof.get("session_ids_hidden"):
        failures.append("Codex proof did not hide session IDs.")
    if not codex_proof.get("would_resume_configured_session"):
        failures.append("Codex proof did not identify the configured Default session.")
    return {
        "passed": not failures,
        "failures": failures,
        "selected_chat": str(codex_proof.get("selected_chat_name") or ""),
        "sent_prompt_to_codex": bool(codex_proof.get("sent_prompt_to_codex")),
        "session_ids_hidden": bool(codex_proof.get("session_ids_hidden")),
        "voice_tool": voice_tool,
        "routed_command": routed_command,
        "command_transcript": command_transcript,
        "alias_detected": alias_detected,
    }


def run_teams_assignment_case(
    case: dict[str, Any],
    *,
    base_url: str,
    run_dir: Path,
    timeout: float,
    exercise_live_speech: bool,
    exercise_visible_navigation: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    run_dir.mkdir(parents=True, exist_ok=True)
    chrome_memory_guard: dict[str, Any] | None = None
    if exercise_visible_navigation:
        chrome_memory_guard = chrome_memory_safety_snapshot()
        write_json(run_dir / "chrome-memory-safety.json", chrome_memory_guard)
        if not chrome_memory_guard.get("ok"):
            reason = str(chrome_memory_guard.get("reason") or "Chrome memory safety check failed.")
            warning = f"Chrome live navigation skipped for computer safety: {reason}"
            return {
                "case_id": case["id"],
                "status": "warning",
                "warnings": [warning],
                "command": case["command"],
                "voice_loop_status": "skipped_for_chrome_memory_safety",
                "voice_loop_report": "",
                "action_proof": {
                    "passed": True,
                    "capability_complete": False,
                    "completion_status": "not_inspected",
                    "visible_reply_preview": warning,
                    "chrome_memory_guard": chrome_memory_guard,
                },
                "cleanup": {
                    "required": False,
                    "reason": "Chrome was not touched because the live-navigation memory guard failed closed.",
                },
                "chrome_memory_guard": chrome_memory_guard,
                "total_seconds": round(time.monotonic() - started, 3),
            }
    before_tabs = chrome_tab_snapshot()
    write_json(run_dir / "chrome-tabs-before.json", {"tabs": before_tabs})
    cleanup: dict[str, Any] = {}
    try:
        voice_report = voice_loop_qa.run_voice_loop(
            command_text=case["command"],
            base_url=base_url,
            run_dir=run_dir / "voice-loop",
            length_scale=0.85,
            timeout=timeout,
            stt_provider="local",
            no_permission_prompts=True,
            expect_tools=list(case["expect_tool"]),
            expect_routed_contains=list(case["expect_routed_contains"]),
            exercise_live_speech=exercise_live_speech,
            allow_audio_actions=False,
            allow_browser_actions=exercise_visible_navigation,
            exercise_visible_navigation=exercise_visible_navigation,
        )
        write_json(run_dir / "voice-loop-report.json", voice_report)
        action_proof = verify_teams_assignment_honesty(voice_report)
        status = "passed"
        warnings: list[str] = []
        voice_status = str(voice_report.get("result", {}).get("status") or "failed")
        if voice_status == "failed":
            status = "failed"
            warnings.append("Voice loop failed.")
        elif voice_status != "passed":
            if not action_proof.get("honest_permission_blocked"):
                status = "warning"
                warnings.append(f"Voice loop returned {voice_status}.")
        if action_proof.get("passed") and not action_proof.get("capability_complete"):
            status = "warning"
            warnings.append(
                "Teams workflow was honest but incomplete: Jarvis did not inspect the requested Music assignment."
            )
            warnings.extend(teams_incomplete_detail_warnings(action_proof))
            if action_proof.get("chrome_page_read_blocked"):
                warnings.append("Chrome page-read was blocked before the visible-screen fallback.")
            if action_proof.get("browser_focus_not_verified"):
                warnings.append(teams_focus_warning(action_proof))
            if action_proof.get("requested_class_target_found"):
                warnings.append("Visible requested-class navigation target was found for the next safe navigation step.")
            if action_proof.get("assignments_target_found"):
                warnings.append("Visible Assignments navigation target was found for the next safe navigation step.")
            if action_proof.get("all_teams_target_found"):
                warnings.append("Visible All teams navigation target was found for the next safe navigation step.")
            live_navigation_summary = visible_navigation_execution_warning(action_proof)
            if live_navigation_summary:
                warnings.append(live_navigation_summary)
            else:
                warnings.extend(teams_no_click_plan_warnings(action_proof))
        if not action_proof["passed"]:
            status = "failed"
            warnings.extend(action_proof["failures"])
        return {
            "case_id": case["id"],
            "status": status,
            "warnings": warnings,
            "command": case["command"],
            "voice_loop_status": voice_status,
            "voice_loop_report": str(run_dir / "voice-loop-report.json"),
            "action_proof": action_proof,
            "cleanup": cleanup,
            "chrome_memory_guard": chrome_memory_guard or {},
            "total_seconds": round(time.monotonic() - started, 3),
        }
    finally:
        after_tabs = chrome_tab_snapshot()
        cleanup.update(clean_new_chrome_tabs(before_tabs, after_tabs, hosts=("teams.microsoft.com", "teams.cloud.microsoft")))
        write_json(run_dir / "chrome-tabs-after.json", {"tabs": after_tabs})
        write_json(run_dir / "cleanup.json", cleanup)


def teams_incomplete_detail_warnings(action_proof: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if action_proof.get("honest_login_gate") or action_proof.get("browser_open_login_gate"):
        warnings.append("Teams is behind a Microsoft sign-in gate in Chrome.")
    return warnings


def teams_no_click_plan_warnings(action_proof: dict[str, Any]) -> list[str]:
    labels = {
        "requested_class": "requested-class",
        "assignments": "Assignments",
        "all_teams": "All teams",
        "teams_search": "Teams Search",
    }
    ready_flags = {
        "requested_class": "requested_class_navigation_plan_ready",
        "assignments": "assignments_navigation_plan_ready",
        "all_teams": "all_teams_navigation_plan_ready",
        "teams_search": "teams_search_navigation_plan_ready",
    }
    ordered_keys: list[str] = []
    sequence = action_proof.get("visible_navigation_sequence")
    if isinstance(sequence, list):
        for step in sequence:
            key = str(step.get("key") or "") if isinstance(step, dict) else ""
            if key in labels and action_proof.get(ready_flags[key]) and key not in ordered_keys:
                ordered_keys.append(key)
    for key in ("requested_class", "assignments", "all_teams", "teams_search"):
        if action_proof.get(ready_flags[key]) and key not in ordered_keys:
            ordered_keys.append(key)
    return [
        f"A non-clicking {labels[key]} navigation plan is ready; live navigation still requires an explicit safe run."
        for key in ordered_keys
    ]


def teams_focus_warning(action_proof: dict[str, Any]) -> str:
    capture_status = str(action_proof.get("capture_status") or "").strip()
    capture_response_status = str(action_proof.get("capture_response_status") or "").strip()
    capture_window_title = str(action_proof.get("capture_window_title") or "").strip()
    capture_method = str(action_proof.get("capture_method") or "").strip()
    if capture_status == "failed" or capture_response_status == "native_capture_failed":
        return "Expected Teams window was not capturable before visible-screen OCR."
    if capture_window_title:
        if "teams" in capture_window_title.casefold() or "microsoft" in capture_window_title.casefold():
            if capture_method in {"chrome_applescript_display_crop", "cg_screen_bounds_fallback"}:
                return (
                    "Chrome reports a Teams window, but native OCR used a screen-bounds crop and saw a different "
                    "visible Space instead of Teams content."
                )
            return "Visible-screen OCR captured a Teams-titled Chrome window, but the OCR text did not contain usable Teams assignment content."
        return f"OCR captured a different Chrome window before Teams inspection: {capture_window_title}."
    return "Chrome did not foreground the Teams tab before visible-screen OCR."


def join_unique_reply_fragments(*fragments: str) -> str:
    seen: set[str] = set()
    unique: list[str] = []
    for fragment in fragments:
        text = str(fragment or "").strip()
        if not text:
            continue
        normalized = " ".join(text.casefold().split())
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(text)
    return " ".join(unique).strip()


def verify_teams_assignment_honesty(voice_report: dict[str, Any]) -> dict[str, Any]:
    result = voice_report.get("result") if isinstance(voice_report.get("result"), dict) else {}
    visible_reply = str(result.get("visible_reply_preview") or "")
    follow_up = result.get("visible_screen_follow_up") if isinstance(result.get("visible_screen_follow_up"), dict) else {}
    follow_up_reply = str(follow_up.get("visible_reply_preview") or "")
    browser_follow_up = follow_up.get("browser_page_follow_up") if isinstance(follow_up.get("browser_page_follow_up"), dict) else {}
    initial_browser_follow_up = (
        follow_up.get("browser_page_follow_up_initial")
        if isinstance(follow_up.get("browser_page_follow_up_initial"), dict)
        else {}
    )
    navigation_targets = (
        follow_up.get("visible_navigation_targets")
        if isinstance(follow_up.get("visible_navigation_targets"), dict)
        else {}
    )
    assignments_target = (
        navigation_targets.get("assignments")
        if isinstance(navigation_targets.get("assignments"), dict)
        else {}
    )
    assignments_plan = (
        navigation_targets.get("assignments_plan")
        if isinstance(navigation_targets.get("assignments_plan"), dict)
        else {}
    )
    requested_class_target = (
        navigation_targets.get("requested_class")
        if isinstance(navigation_targets.get("requested_class"), dict)
        else {}
    )
    requested_class_plan = (
        navigation_targets.get("requested_class_plan")
        if isinstance(navigation_targets.get("requested_class_plan"), dict)
        else {}
    )
    all_teams_target = (
        navigation_targets.get("all_teams")
        if isinstance(navigation_targets.get("all_teams"), dict)
        else {}
    )
    all_teams_plan = (
        navigation_targets.get("all_teams_plan")
        if isinstance(navigation_targets.get("all_teams_plan"), dict)
        else {}
    )
    teams_search_target = (
        navigation_targets.get("teams_search")
        if isinstance(navigation_targets.get("teams_search"), dict)
        else {}
    )
    teams_search_plan = (
        navigation_targets.get("teams_search_plan")
        if isinstance(navigation_targets.get("teams_search_plan"), dict)
        else {}
    )
    navigation_sequence = (
        navigation_targets.get("sequence")
        if isinstance(navigation_targets.get("sequence"), list)
        else []
    )
    combined_reply = join_unique_reply_fragments(visible_reply, follow_up_reply)
    lower_reply = combined_reply.casefold()
    failures: list[str] = []
    inspected_music = (
        "assignment-related text" in lower_reply
        and "questions i need answered" in lower_reply
        and any(token in lower_reply for token in ("music", "musical", "song", "instrument"))
    )
    honest_login_gate = (
        str(follow_up.get("status") or "") == "login_gate_visible"
        or "behind a password or sign-in gate" in lower_reply
        or "not reached the assignment page yet" in lower_reply
    )
    honest_not_inspected = "have not inspected the newest music assignment" in lower_reply or honest_login_gate
    honest_wrong_subject = "does not look like the music assignment" in lower_reply
    honest_permission_blocked = (
        "chrome is blocking jarvis from controlling the current page" in lower_reply
        or "chrome control permission" in lower_reply
        or "cannot reliably read the teams page text" in lower_reply
        or "teams is open in chrome, but jarvis cannot reliably read" in lower_reply
    )
    chrome_page_read_blocked = any(
        str(item.get("status") or "") == "browser_permission_blocked"
        for item in (browser_follow_up, initial_browser_follow_up)
        if isinstance(item, dict)
    )
    browser_focus_not_verified = str(follow_up.get("status") or "") == "browser_focus_not_verified"
    if browser_focus_not_verified:
        assignments_target = {}
        assignments_plan = {}
        requested_class_target = {}
        requested_class_plan = {}
        all_teams_target = {}
        all_teams_plan = {}
        teams_search_target = {}
        teams_search_plan = {}
        navigation_sequence = []
    capability_complete = bool(inspected_music)
    completion_status = (
        "complete"
        if inspected_music
        else "permission_blocked"
        if honest_permission_blocked
        else "wrong_subject"
        if honest_wrong_subject
        else "not_inspected"
        if honest_not_inspected
        else "unknown"
    )
    if not (inspected_music or honest_not_inspected or honest_wrong_subject or honest_permission_blocked):
        failures.append("Teams proof neither inspected the Music assignment nor failed honestly.")
    if "what is not random" in lower_reply or "veritasium" in lower_reply:
        failures.append("Teams proof regressed to a generic Chrome/YouTube visible-screen summary.")
    if "geography of greece" in lower_reply and "does not look like the music assignment" not in lower_reply:
        failures.append("Teams proof summarized a Geography assignment as if it were Music.")
    if follow_up.get("status") == "completed" and "screen.visible_text" == follow_up.get("tool") and not inspected_music:
        failures.append("Teams visible-screen follow-up completed without proving Music assignment content.")
    return {
        "passed": not failures,
        "failures": failures,
        "inspected_music": inspected_music,
        "honest_not_inspected": honest_not_inspected,
        "honest_login_gate": honest_login_gate,
        "honest_wrong_subject": honest_wrong_subject,
        "honest_permission_blocked": honest_permission_blocked,
        "chrome_page_read_blocked": chrome_page_read_blocked,
        "browser_focus_not_verified": browser_focus_not_verified,
        "browser_open_login_gate": bool(follow_up.get("browser_open_login_gate")),
        "browser_open_active_url": str(follow_up.get("browser_open_active_url") or ""),
        "browser_open_active_title": str(follow_up.get("browser_open_active_title") or ""),
        "browser_open_verification_url": str(follow_up.get("browser_open_verification_url") or ""),
        "browser_open_verification_source": str(follow_up.get("browser_open_verification_source") or ""),
        "browser_focus_expected_host": str(follow_up.get("browser_focus_expected_host") or ""),
        "browser_focus_attempted_url": str(follow_up.get("browser_focus_attempted_url") or ""),
        "browser_focus_detail": str(follow_up.get("browser_focus_detail") or ""),
        "capture_status": str(follow_up.get("capture_status") or ""),
        "capture_window_title": str(follow_up.get("capture_window_title") or ""),
        "capture_method": str(
            (
                follow_up.get("capture_diagnostics")
                if isinstance(follow_up.get("capture_diagnostics"), dict)
                else {}
            ).get("capture_method")
            or ""
        ),
        "capture_response_status": str(follow_up.get("response_status") or ""),
        "assignments_target_found": bool(assignments_target.get("found")),
        "assignments_target": assignments_target,
        "assignments_navigation_plan_ready": bool(assignments_plan.get("planned")),
        "assignments_navigation_plan": assignments_plan,
        "requested_class_target_found": bool(requested_class_target.get("found")),
        "requested_class_target": requested_class_target,
        "requested_class_navigation_plan_ready": bool(requested_class_plan.get("planned")),
        "requested_class_navigation_plan": requested_class_plan,
        "all_teams_target_found": bool(all_teams_target.get("found")),
        "all_teams_target": all_teams_target,
        "all_teams_navigation_plan_ready": bool(all_teams_plan.get("planned")),
        "all_teams_navigation_plan": all_teams_plan,
        "teams_search_target_found": bool(teams_search_target.get("found")),
        "teams_search_target": teams_search_target,
        "teams_search_navigation_plan_ready": bool(teams_search_plan.get("planned")),
        "teams_search_navigation_plan": teams_search_plan,
        "visible_navigation_sequence": navigation_sequence,
        "visible_navigation_execution": (
            follow_up.get("visible_navigation_execution")
            if isinstance(follow_up.get("visible_navigation_execution"), dict)
            else None
        ),
        "visible_navigation_execution_steps": (
            follow_up.get("visible_navigation_execution_steps")
            if isinstance(follow_up.get("visible_navigation_execution_steps"), list)
            else []
        ),
        "capability_complete": capability_complete,
        "completion_status": completion_status,
        "visible_reply_preview": combined_reply[:500],
        "follow_up_status": str(follow_up.get("status") or ""),
    }


def visible_navigation_execution_warning(action_proof: dict[str, Any]) -> str:
    steps = action_proof.get("visible_navigation_execution_steps")
    if isinstance(steps, list) and any(
        isinstance(step, dict) and step.get("executed") and step.get("visible_state_changed") is False
        for step in steps
    ):
        return "Live visible navigation was exercised but did not visibly change the Teams screen."
    execution = action_proof.get("visible_navigation_execution")
    if not isinstance(execution, dict):
        return ""
    raw_action = str(execution.get("action") or "").replace("_", " ").strip()
    action = raw_action or "visible navigation"
    noun = action if action == "visible navigation" else f"{action} navigation"
    status = str(execution.get("status") or "unknown").replace("_", " ").strip()
    if execution.get("executed"):
        return f"Live {noun} was exercised and returned {status}."
    if str(execution.get("status") or "") == "navigation_loop_prevented":
        if execution.get("attempted"):
            return f"Live {noun} was exercised but stopped as {status}."
        return f"Live {noun} was requested but stopped as {status}."
    if not execution.get("attempted"):
        return ""
    return f"Live {noun} was exercised but stopped as {status}."


def chrome_tab_snapshot() -> list[dict[str, str]]:
    script = '''
if application "Google Chrome" is not running then return ""
set output to ""
tell application "Google Chrome"
  repeat with w in windows
    repeat with t in tabs of w
      set output to output & (id of w as text) & tab & (id of t as text) & tab & (URL of t as text) & linefeed
    end repeat
  end repeat
end tell
return output
'''
    try:
        completed = subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    tabs: list[dict[str, str]] = []
    if completed.returncode != 0:
        return tabs
    for line in completed.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            window_id, tab_id, url = parts
            tabs.append({"window_id": window_id, "tab_id": tab_id, "url": url})
        elif len(parts) == 2:
            window_id, url = parts
            tabs.append({"window_id": window_id, "tab_id": "", "url": url})
    return tabs


def clean_new_chrome_tabs(
    before_tabs: list[dict[str, str]],
    after_tabs: list[dict[str, str]],
    *,
    hosts: tuple[str, ...],
) -> dict[str, Any]:
    before_pairs = {
        (tab.get("window_id", ""), tab.get("tab_id", ""), tab.get("url", ""))
        for tab in before_tabs
    }
    before_window_ids = {str(tab.get("window_id") or "") for tab in before_tabs}
    after_by_window: dict[str, list[dict[str, str]]] = {}
    new_target_tabs: list[dict[str, str]] = []
    for tab in after_tabs:
        window_id = str(tab.get("window_id") or "")
        tab_id = str(tab.get("tab_id") or "")
        url = str(tab.get("url") or "")
        after_by_window.setdefault(window_id, []).append(tab)
        pair = (window_id, tab_id, url)
        if pair in before_pairs:
            continue
        if any(host in url for host in hosts):
            new_target_tabs.append({"window_id": window_id, "tab_id": tab_id, "url": url})
    if not new_target_tabs:
        return {"chrome_tabs_closed": 0, "chrome_windows_closed": 0, "new_target_tabs": 0, "new_target_windows": 0}
    new_target_window_ids = {
        window_id
        for window_id, tabs in after_by_window.items()
        if window_id not in before_window_ids
        and tabs
        and any(tab in new_target_tabs for tab in tabs)
        and all(any(host in str(tab.get("url") or "") for host in hosts) for tab in tabs)
    }
    tab_conditions = "\n".join(
        (
            f'      if windowId is "{escape_applescript_string(tab["window_id"])}" '
            f'and tabId is "{escape_applescript_string(tab["tab_id"])}" '
            f'then set end of closeList to t'
        )
        for tab in new_target_tabs
        if str(tab.get("window_id") or "") not in new_target_window_ids
    )
    window_conditions = "\n".join(
        f'    if windowId is "{escape_applescript_string(window_id)}" then set end of closeWindows to w'
        for window_id in sorted(new_target_window_ids)
    )
    script = f'''
tell application "Google Chrome"
  set closeWindows to {{}}
  repeat with w in windows
    set windowId to id of w as text
{window_conditions}
  end repeat
  repeat with w in closeWindows
    close w
  end repeat
  repeat with w in windows
    set windowId to id of w as text
    set closeList to {{}}
    repeat with t in tabs of w
      set tabId to id of t as text
{tab_conditions}
    end repeat
    repeat with t in closeList
      close t
    end repeat
  end repeat
end tell
'''
    completed = subprocess.run(
        ["/usr/bin/osascript", "-e", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return {
        "chrome_tabs_closed": len(new_target_tabs) if completed.returncode == 0 else 0,
        "chrome_windows_closed": len(new_target_window_ids) if completed.returncode == 0 else 0,
        "new_target_tabs": len(new_target_tabs),
        "new_target_windows": len(new_target_window_ids),
        "cleanup_returncode": completed.returncode,
        "cleanup_error": completed.stderr.strip()[-500:],
    }


def escape_applescript_string(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def run_email_sharpay_case(
    case: dict[str, Any],
    *,
    base_url: str,
    run_dir: Path,
    timeout: float,
    exercise_live_speech: bool,
) -> dict[str, Any]:
    started = time.monotonic()
    run_dir.mkdir(parents=True, exist_ok=True)
    voice_report = _run_email_voice_loop_once(
        case,
        base_url=base_url,
        run_dir=run_dir / "voice-loop",
        timeout=timeout,
        exercise_live_speech=exercise_live_speech,
    )
    retry_voice_report: dict[str, Any] | None = None
    if voice_loop_transient_http_error(voice_report):
        retry_voice_report = _run_email_voice_loop_once(
            case,
            base_url=base_url,
            run_dir=run_dir / "voice-loop-retry",
            timeout=timeout,
            exercise_live_speech=exercise_live_speech,
        )
        write_json(run_dir / "voice-loop-retry-report.json", retry_voice_report)
        if str(retry_voice_report.get("result", {}).get("status") or "") != "failed":
            voice_report = retry_voice_report
    write_json(run_dir / "voice-loop-report.json", voice_report)
    email_filter_proof = email_sharpay_result_summary_proof(voice_report)
    if not email_filter_proof.get("trusted_command_result"):
        email_filter_proof = email_sharpay_filter_proof(fallback_reason=str(email_filter_proof.get("fallback_reason") or "missing_command_result"))
    write_json(run_dir / "email-filter-proof.json", email_filter_proof)
    action_proof = verify_email_sharpay_honesty(voice_report, email_filter_proof=email_filter_proof)
    status = "passed"
    warnings: list[str] = []
    voice_status = str(voice_report.get("result", {}).get("status") or "failed")
    if voice_status == "failed":
        status = "failed"
        warnings.append("Voice loop failed.")
        if retry_voice_report is not None:
            warnings.append("Transient HTTP retry was attempted but did not recover the voice loop.")
    elif voice_status != "passed":
        status = "warning"
        warnings.append(f"Voice loop returned {voice_status}.")
    if retry_voice_report is not None and voice_status == "passed":
        warnings.append("Voice loop recovered after one transient HTTP retry.")
    if not action_proof["passed"]:
        status = "failed"
        warnings.extend(action_proof["failures"])
    return {
        "case_id": case["id"],
        "status": status,
        "warnings": warnings,
        "command": case["command"],
        "voice_loop_status": voice_status,
        "voice_loop_report": str(run_dir / "voice-loop-report.json"),
        "voice_loop_retry_report": str(run_dir / "voice-loop-retry-report.json") if retry_voice_report is not None else None,
        "action_proof": action_proof,
        "email_filter_proof": email_filter_proof,
        "cleanup": {"required": False, "reason": "Read-only local email/contact check."},
        "total_seconds": round(time.monotonic() - started, 3),
    }


def _run_email_voice_loop_once(
    case: dict[str, Any],
    *,
    base_url: str,
    run_dir: Path,
    timeout: float,
    exercise_live_speech: bool,
) -> dict[str, Any]:
    return voice_loop_qa.run_voice_loop(
        command_text=case["command"],
        base_url=base_url,
        run_dir=run_dir,
        length_scale=0.85,
        timeout=timeout,
        stt_provider="local",
        no_permission_prompts=True,
        expect_tools=list(case["expect_tool"]),
        expect_routed_contains=list(case["expect_routed_contains"]),
        exercise_live_speech=exercise_live_speech,
        allow_audio_actions=False,
    )


def voice_loop_transient_http_error(voice_report: dict[str, Any]) -> bool:
    result = voice_report.get("result") if isinstance(voice_report.get("result"), dict) else {}
    if str(result.get("status") or "") != "failed":
        return False
    error = str(result.get("error") or "").casefold()
    return "http 502" in error or "http 503" in error or "http 504" in error


def email_sharpay_result_summary_proof(voice_report: dict[str, Any]) -> dict[str, Any]:
    result = voice_report.get("result") if isinstance(voice_report.get("result"), dict) else {}
    summary = result.get("command_response_result") if isinstance(result.get("command_response_result"), dict) else {}
    sender_bits = " ".join(
        str(summary.get(key) or "")
        for key in ("sender_query", "contact_alias", "contact_display_name")
    )
    tool = str(result.get("command_response_tool") or "")
    status = str(summary.get("status") or "")
    match_count = int(summary.get("match_count") or 0)
    message_count = int(summary.get("message_count") or 0)
    all_senders_match = "sharpay" in sender_bits.casefold()
    trusted = (
        tool == "outlook.visible_summary"
        and status == "checked"
        and match_count > 0
        and message_count > 0
        and all_senders_match
    )
    return {
        "tool": "email.sharpay_filter_proof",
        "proof_source": "voice_loop_command_result",
        "trusted_command_result": trusted,
        "lookup_status": str(summary.get("contact_alias_status") or ""),
        "resolved_sender": str(summary.get("contact_display_name") or summary.get("sender_query") or "Ms Sharpay"),
        "mail_status": status,
        "message_count": message_count,
        "match_count": match_count,
        "selection_mode": str(summary.get("selection_mode") or ""),
        "all_senders_match": all_senders_match,
        "sender_samples_redacted": [],
        "read_email_content": False,
        "read_private_metadata": True,
        "fallback_reason": "" if trusted else "command_result_missing_or_untrusted",
    }


def email_sharpay_filter_proof(*, fallback_reason: str = "") -> dict[str, Any]:
    lookup = contact_data_lookup("Ms Sharpay")
    resolved = str(lookup.get("display_name") or "Ms Sharpay")
    mail = outlook_read_only_check(
        limit=1,
        sender_query=resolved,
        date_range="past_month",
        original_prompt="Summarize all the emails from Ms. Sharpay in the past month.",
        scan_limit_override=75,
    )
    messages = [message for message in (mail.get("messages") or []) if isinstance(message, dict)]
    sender_samples = [str(message.get("sender") or "") for message in messages[:5]]
    all_senders_match = bool(messages) and all(
        "sharpay" in sender.casefold() or resolved.casefold() in sender.casefold()
        for sender in sender_samples
    )
    return {
        "tool": "email.sharpay_filter_proof",
        "proof_source": "direct_mail_rescan",
        "trusted_command_result": False,
        "fallback_reason": fallback_reason,
        "lookup_status": str(lookup.get("status") or ""),
        "resolved_sender": resolved,
        "mail_status": str(mail.get("status") or ""),
        "message_count": int(mail.get("message_count") or 0),
        "match_count": int(mail.get("match_count") or 0),
        "selection_mode": str(mail.get("selection_mode") or ""),
        "all_senders_match": all_senders_match,
        "sender_samples_redacted": [sender[:80] for sender in sender_samples],
        "read_email_content": False,
        "read_private_metadata": True,
    }


def verify_email_sharpay_honesty(
    voice_report: dict[str, Any],
    *,
    email_filter_proof: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = voice_report.get("result") if isinstance(voice_report.get("result"), dict) else {}
    visible_reply = str(result.get("visible_reply_preview") or "")
    lower_reply = visible_reply.casefold()
    email_filter_proof = email_filter_proof or {}
    failures: list[str] = []
    resolved_sharpay = "sharpay" in lower_reply
    needs_confirmation = "do not know who ms sharpay means" in lower_reply or "possible matches" in lower_reply
    filtered_sharpay = (
        str(email_filter_proof.get("lookup_status") or "") == "found"
        and str(email_filter_proof.get("mail_status") or "") == "checked"
        and bool(email_filter_proof.get("all_senders_match"))
    )
    if not (resolved_sharpay or needs_confirmation or filtered_sharpay):
        failures.append("Email proof neither resolved Sharpay nor asked for contact confirmation.")
    if "newest email" in lower_reply and "sharpay" not in lower_reply:
        failures.append("Email proof appears to have fallen back to an unrelated newest email.")
    if "http://" in lower_reply or "https://" in lower_reply:
        failures.append("Email proof exposed a raw link in the spoken/visible summary.")
    return {
        "passed": not failures,
        "failures": failures,
        "resolved_sharpay": resolved_sharpay,
        "needs_confirmation": needs_confirmation,
        "filtered_sharpay": filtered_sharpay,
        "resolved_sender": str(email_filter_proof.get("resolved_sender") or ""),
        "message_count": int(email_filter_proof.get("message_count") or 0),
        "visible_reply_preview": visible_reply[:500],
    }


def music_bridge_request(
    base_url: str,
    method: str,
    path: str,
    *,
    query: dict[str, Any] | None = None,
    timeout: float,
    auth: bool = True,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    headers = {"Accept": "application/json"}
    token_path = Path("~/Library/Application Support/Music/control-token.txt").expanduser()
    if auth and token_path.exists():
        token = token_path.read_text(encoding="utf-8").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
    data = b"{}" if method.upper() in {"POST", "PUT", "PATCH"} else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            parsed = json.loads(body) if body.strip() else {}
            if isinstance(parsed, dict):
                return parsed
            return {"ok": True, "value": parsed}
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        return {"ok": False, "status_code": error.code, "error": body}
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


def is_canonical_summary(summary: dict[str, Any]) -> bool:
    return bool(summary.get("canonical_latest")) or str(summary.get("case_selection") or "") == "all"


def write_summary(summary: dict[str, Any], run_dir: Path, output_dir: Path, *, update_latest: bool = True) -> None:
    write_json(run_dir / "summary.json", summary)
    markdown = render_markdown(summary)
    (run_dir / "summary.md").write_text(markdown, encoding="utf-8")
    if update_latest:
        write_json(output_dir / "latest.json", summary)
        (output_dir / "latest.md").write_text(markdown, encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Latest Jarvis Full Loop Regression",
        "",
        f"- Status: {summary.get('status')}",
        f"- Passed: {summary.get('passed')}/{summary.get('total')}",
        f"- Run dir: {summary.get('run_dir')}",
    ]
    for result in summary.get("results", []):
        if not isinstance(result, dict):
            continue
        proof = result.get("action_proof") if isinstance(result.get("action_proof"), dict) else {}
        proof_label = proof.get("selected_title") or (
            f"{proof.get('used_human')} of {proof.get('total_human')} used"
            if proof.get("used_human") and proof.get("total_human")
            else f"{proof.get('event_count')} calendar events via {proof.get('source')}"
            if proof.get("event_count") is not None and proof.get("source")
            else f"{proof.get('source_label')}: {proof.get('price')} -> {proof.get('converted')}"
            if proof.get("source_label") and proof.get("price") and proof.get("converted")
            else f"{proof.get('model')} via {proof.get('preferred_lane')}"
            if proof.get("model") and proof.get("preferred_lane")
            else f"{proof.get('selected_chat')} Codex chat, sent={proof.get('sent_prompt_to_codex')}"
            if proof.get("selected_chat")
            else "(none)"
        )
        lines.extend(
            [
                "",
                f"## {result.get('case_id')}",
                f"- Status: {result.get('status')}",
                f"- Command: {result.get('command')}",
                f"- Voice loop: {result.get('voice_loop_status')}",
                f"- Proof: {proof_label}",
                f"- Seconds: {result.get('total_seconds')}",
            ]
        )
        warnings = result.get("warnings")
        if warnings:
            lines.append(f"- Warnings: {'; '.join(str(item) for item in warnings)}")
    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
