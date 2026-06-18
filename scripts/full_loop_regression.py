#!/usr/bin/env python3
"""Run Jarvis full-loop regressions with external action proof and cleanup."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.tools import memory_usage_status  # noqa: E402
from scripts import voice_loop_qa  # noqa: E402
from scripts.render_overnight_status import normalize_base_url  # noqa: E402


REPORT_DIR = PROJECT_ROOT / "runtime" / "full_loop_regression"
DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_MUSIC_BRIDGE_URL = "http://127.0.0.1:47879"


MUSIC_WAVING_CASE = {
    "id": "music_play_waving_through_window",
    "command": "Hey Jarvis, play Waving Through a Window.",
    "expect_tool": ["localos.music_play"],
    "expect_visible_contains": ["Music", "Dear Evan Hansen"],
    "expect_routed_contains": ["play", "Waving"],
}
RAM_ACTIVITY_CASE = {
    "id": "ram_activity_monitor",
    "command": "Hey Jarvis, check in Activity Monitor how much RAM my computer is using.",
    "expect_tool": ["diagnostics.memory_usage"],
    "expect_visible_contains": ["Memory", "GB"],
    "expect_routed_contains": ["Activity Monitor", "RAM"],
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--music-bridge-url", default=DEFAULT_MUSIC_BRIDGE_URL)
    parser.add_argument("--output-dir", default=str(REPORT_DIR))
    parser.add_argument("--case", choices=("music", "ram", "all"), default="all")
    parser.add_argument("--timeout", type=float, default=75.0)
    parser.add_argument("--exercise-live-speech", action="store_true")
    parser.add_argument("--no-report-refresh", action="store_true")
    args = parser.parse_args()

    base_url = normalize_base_url(args.base_url)
    run_dir = allocate_run_dir(Path(args.output_dir).resolve())
    cases = []
    if args.case in {"music", "all"}:
        cases.append(MUSIC_WAVING_CASE)
    if args.case in {"ram", "all"}:
        cases.append(RAM_ACTIVITY_CASE)
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

    passed = sum(1 for result in results if result.get("status") == "passed")
    failed = sum(1 for result in results if result.get("status") == "failed")
    warnings = sum(1 for result in results if result.get("status") == "warning")
    summary = {
        "schema": "jarvis.full_loop_regression.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "base_url": base_url,
        "run_dir": str(run_dir),
        "status": "passed" if failed == 0 and warnings == 0 else "warning" if failed == 0 else "failed",
        "passed": passed,
        "warning": warnings,
        "failed": failed,
        "total": len(results),
        "results": results,
    }
    write_summary(summary, run_dir, Path(args.output_dir).resolve())
    if not args.no_report_refresh:
        try:
            from scripts.report_refresh import refresh_report_surfaces_quietly

            summary["report_refresh"] = refresh_report_surfaces_quietly(base_url)
            write_summary(summary, run_dir, Path(args.output_dir).resolve())
        except Exception as error:  # pragma: no cover - defensive live-only path.
            summary["report_refresh"] = {"ok": False, "error": f"{type(error).__name__}: {error}"}
            write_summary(summary, run_dir, Path(args.output_dir).resolve())

    print(f"Report: {run_dir / 'summary.json'}")
    for result in results:
        print(f"{result['case_id']}: {result['status']} ({result.get('total_seconds')}s)")
    return 0 if summary["status"] == "passed" else 1


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
    try:
        preflight = music_bridge_request(music_bridge_url, "GET", "/health", timeout=3.5, auth=False)
        if not preflight.get("ok"):
            return {
                "case_id": case["id"],
                "status": "failed",
                "error": "Music bridge is not healthy.",
                "preflight": preflight,
                "total_seconds": round(time.monotonic() - started, 3),
            }

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
            "playback_state": playback,
            "cleanup": cleanup,
            "total_seconds": round(time.monotonic() - started, 3),
        }
    finally:
        cleanup["stop"] = music_bridge_request(music_bridge_url, "POST", "/stop", timeout=3.5)
        cleanup["close_window"] = music_bridge_request(
            music_bridge_url,
            "POST",
            "/diagnostics/window-control-action",
            query={"action": "close"},
            timeout=3.5,
        )
        write_json(run_dir / "cleanup.json", cleanup)


def wait_for_music_playback(music_bridge_url: str, *, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_state: dict[str, Any] = {}
    while True:
        state = music_bridge_request(music_bridge_url, "GET", "/playback-state", timeout=3.5)
        last_state = state
        if bool(state.get("playing")):
            return state
        if time.monotonic() >= deadline:
            return last_state
        time.sleep(0.25)


def verify_waving_playback(playback_state: dict[str, Any]) -> dict[str, Any]:
    now_playing = playback_state.get("nowPlaying") if isinstance(playback_state.get("nowPlaying"), dict) else {}
    title = str(now_playing.get("title") or "")
    file_name = str(now_playing.get("fileName") or "")
    haystack = f"{title} {file_name}".casefold()
    failures: list[str] = []
    if not playback_state.get("playing"):
        failures.append("Music app did not report active playback.")
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


def write_summary(summary: dict[str, Any], run_dir: Path, output_dir: Path) -> None:
    write_json(run_dir / "summary.json", summary)
    write_json(output_dir / "latest.json", summary)
    markdown = render_markdown(summary)
    (run_dir / "summary.md").write_text(markdown, encoding="utf-8")
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
