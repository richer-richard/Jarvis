#!/usr/bin/env python3
"""Run the Jarvis pre-build proof gate and write a stable handoff report."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.render_overnight_status import normalize_base_url  # noqa: E402
from scripts.physical_audio_preflight import physical_audio_preflight  # noqa: E402


REPORT_DIR = PROJECT_ROOT / "runtime" / "pre_build_gate"
DEFAULT_BASE_URL = "http://127.0.0.1:8765"
FULL_LOOP_GATE_TIMEOUT_SECONDS = 360.0


CommandRunner = Callable[[list[str], float], subprocess.CompletedProcess[str]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output-dir", default=str(REPORT_DIR))
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--exercise-live-speech", action="store_true")
    parser.add_argument(
        "--exercise-visible-navigation",
        action="store_true",
        help="Pass the explicit Teams visible-navigation exercise flag through to the full-loop regression.",
    )
    parser.add_argument(
        "--require-live-speech",
        action="store_true",
        help="Fail closed unless --exercise-live-speech is also set, so a build cannot be reported as live-speech tested by accident.",
    )
    parser.add_argument(
        "--require-visible-navigation",
        action="store_true",
        help="Fail closed unless --exercise-visible-navigation is also set, so Teams navigation cannot be implied by a no-click plan.",
    )
    parser.add_argument(
        "--require-physical-capture",
        action="store_true",
        help="Fail closed because the current proof harness does not capture physical speaker/microphone audio.",
    )
    parser.add_argument("--skip-python-tests", action="store_true")
    parser.add_argument("--skip-full-loop", action="store_true")
    parser.add_argument("--skip-cleanup", action="store_true")
    args = parser.parse_args(argv)

    try:
        base_url = normalize_base_url(args.base_url)
    except ValueError as error:
        print(f"Refused unsafe base URL: {error}", file=sys.stderr)
        return 2

    summary = run_gate(
        base_url=base_url,
        output_dir=Path(args.output_dir).resolve(),
        timeout=args.timeout,
        exercise_live_speech=args.exercise_live_speech,
        exercise_visible_navigation=args.exercise_visible_navigation,
        require_live_speech=args.require_live_speech,
        require_visible_navigation=args.require_visible_navigation,
        require_physical_capture=args.require_physical_capture,
        skip_python_tests=args.skip_python_tests,
        skip_full_loop=args.skip_full_loop,
        skip_cleanup=args.skip_cleanup,
    )
    print(f"Report: {summary['report_path']}")
    print(f"Passed: {summary['passed']}/{summary['total']}")
    print(f"Status: {summary['status']}")
    return 0 if summary["ok"] else 1


def default_runner(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def run_gate(
    *,
    base_url: str = DEFAULT_BASE_URL,
    output_dir: Path = REPORT_DIR,
    timeout: float = 180.0,
    exercise_live_speech: bool = False,
    exercise_visible_navigation: bool = False,
    require_live_speech: bool = False,
    require_visible_navigation: bool = False,
    require_physical_capture: bool = False,
    skip_python_tests: bool = False,
    skip_full_loop: bool = False,
    skip_cleanup: bool = False,
    runner: CommandRunner = default_runner,
) -> dict[str, Any]:
    base_url = normalize_base_url(base_url)
    run_dir = allocate_run_dir(output_dir)
    started = time.monotonic()
    update_latest = should_update_latest_gate(
        require_live_speech=require_live_speech,
        exercise_live_speech=exercise_live_speech,
        require_visible_navigation=require_visible_navigation,
        exercise_visible_navigation=exercise_visible_navigation,
        require_physical_capture=require_physical_capture,
    )
    steps = build_steps(
        base_url=base_url,
        exercise_live_speech=exercise_live_speech,
        exercise_visible_navigation=exercise_visible_navigation,
        skip_python_tests=skip_python_tests,
        skip_full_loop=skip_full_loop,
        skip_cleanup=skip_cleanup,
    )
    results: list[dict[str, Any]] = []
    if require_physical_capture:
        results.append(physical_capture_requirement_failure(exercise_live_speech=exercise_live_speech))
    if require_live_speech and not exercise_live_speech:
        results.append(live_speech_requirement_failure())
    if require_visible_navigation and not exercise_visible_navigation:
        results.append(visible_navigation_requirement_failure())
    for step in steps:
        if results and any(not item.get("ok") for item in results) and not step.get("always_run_next"):
            continue
        result = run_step(step, timeout=timeout, runner=runner)
        results.append(result)
        write_summary(
            make_summary(
                base_url=base_url,
                run_dir=run_dir,
                results=results,
                started=started,
                exercise_live_speech=exercise_live_speech,
                exercise_visible_navigation=exercise_visible_navigation,
                require_live_speech=require_live_speech,
                require_visible_navigation=require_visible_navigation,
                require_physical_capture=require_physical_capture,
                complete=False,
            ),
            run_dir,
            output_dir,
            update_latest=update_latest,
        )
        if not result["ok"] and not step.get("always_run_next"):
            break

    if not skip_cleanup and not any(item["id"] == "cleanup_chrome_test_tabs" for item in results):
        cleanup_step = cleanup_chrome_step()
        results.append(run_step(cleanup_step, timeout=timeout, runner=runner))
    for step in steps:
        if step.get("always_run_next") and not any(item["id"] == step["id"] for item in results):
            results.append(run_step(step, timeout=timeout, runner=runner))

    summary = make_summary(
        base_url=base_url,
        run_dir=run_dir,
        results=results,
        started=started,
        exercise_live_speech=exercise_live_speech,
        exercise_visible_navigation=exercise_visible_navigation,
        require_live_speech=require_live_speech,
        require_visible_navigation=require_visible_navigation,
        require_physical_capture=require_physical_capture,
        complete=True,
    )
    write_summary(summary, run_dir, output_dir, update_latest=update_latest)
    return summary


def should_update_latest_gate(
    *,
    require_live_speech: bool,
    exercise_live_speech: bool,
    require_visible_navigation: bool,
    exercise_visible_navigation: bool,
    require_physical_capture: bool,
) -> bool:
    if require_physical_capture:
        return False
    if require_live_speech and not exercise_live_speech:
        return False
    if require_visible_navigation and not exercise_visible_navigation:
        return False
    return True


def build_steps(
    *,
    base_url: str,
    exercise_live_speech: bool,
    exercise_visible_navigation: bool,
    skip_python_tests: bool,
    skip_full_loop: bool,
    skip_cleanup: bool,
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    if not skip_python_tests:
        steps.append(
            {
                "id": "python_safety_suite",
                "label": "Python safety suite",
                "command": [sys.executable, "-m", "unittest", "tests.test_safety"],
            }
        )
    if not skip_full_loop:
        full_loop_command = [
            sys.executable,
            "scripts/full_loop_regression.py",
            "--base-url",
            base_url,
            "--case",
            "all",
            "--timeout",
            "75",
        ]
        if exercise_live_speech:
            full_loop_command.append("--exercise-live-speech")
        if exercise_visible_navigation:
            full_loop_command.append("--exercise-visible-navigation")
        full_loop_env = {}
        if exercise_visible_navigation:
            full_loop_env["JARVIS_ALLOW_LIVE_UI_NAVIGATION"] = "1"
        steps.append(
            {
                "id": "full_loop_regression",
                "label": "Full-loop spoken-command regression",
                "command": full_loop_command,
                "env": full_loop_env,
                "timeout_seconds": FULL_LOOP_GATE_TIMEOUT_SECONDS,
                "proof_contract": speech_proof_contract(
                    exercise_live_speech=exercise_live_speech,
                    exercise_visible_navigation=exercise_visible_navigation,
                ),
            }
        )
    steps.append(
        {
            "id": "stop_speaking_probe",
            "label": "Quiet stop-speaking probe",
            "command": [sys.executable, "scripts/probe_stop_speaking.py", "--base-url", base_url],
            "proof_contract": {
                "speech_mode": "suppressed_for_stop_speaking",
                "starts_audio": False,
                "requires_live_worker": True,
            },
        }
    )
    if not skip_cleanup:
        steps.append(cleanup_chrome_step())
    steps.append(
        {
            "id": "report_refresh",
            "label": "Refresh overnight report",
            "command": [sys.executable, "scripts/report_refresh.py", "--base-url", base_url],
            "always_run_next": True,
        }
    )
    return steps


def cleanup_chrome_step() -> dict[str, Any]:
    return {
        "id": "cleanup_chrome_test_tabs",
        "label": "Clean up Jarvis Chrome test tabs",
        "command": [sys.executable, "scripts/cleanup_chrome_test_tabs.py", "--execute", "--json"],
        "always_run_next": True,
        "fatal": False,
    }


def speech_proof_contract(*, exercise_live_speech: bool, exercise_visible_navigation: bool = False) -> dict[str, Any]:
    return {
        "speech_mode": "live_playback_exercised" if exercise_live_speech else "suppressed_for_probe",
        "live_playback_exercised": bool(exercise_live_speech),
        "visible_navigation_exercised": bool(exercise_visible_navigation),
        "physical_speaker_capture": False,
        "physical_microphone_capture": False,
        "notes": (
            "Jarvis live playback is exercised, and exact speech payloads are synthesized/transcribed for content proof."
            if exercise_live_speech
            else "Jarvis live playback is suppressed; exact speech payloads are synthesized/transcribed for quiet content proof."
        ),
    }


def live_speech_requirement_failure() -> dict[str, Any]:
    return {
        "id": "live_speech_requirement",
        "label": "Live speech requirement",
        "ok": False,
        "returncode": "not-run",
        "seconds": 0.0,
        "timeout_seconds": 0.0,
        "command": [],
        "stdout_tail": "",
        "stderr_tail": "Refused to pass: --require-live-speech was set without --exercise-live-speech.",
        "proof_contract": speech_proof_contract(exercise_live_speech=False),
    }


def visible_navigation_requirement_failure() -> dict[str, Any]:
    return {
        "id": "visible_navigation_requirement",
        "label": "Visible navigation requirement",
        "ok": False,
        "returncode": "not-run",
        "seconds": 0.0,
        "timeout_seconds": 0.0,
        "command": [],
        "stdout_tail": "",
        "stderr_tail": "Refused to pass: --require-visible-navigation was set without --exercise-visible-navigation.",
        "proof_contract": {
            "visible_navigation_exercised": False,
            "requires_live_ui_navigation_unlock": True,
        },
    }


def physical_capture_requirement_failure(*, exercise_live_speech: bool) -> dict[str, Any]:
    try:
        preflight = physical_audio_preflight()
    except Exception as error:  # pragma: no cover - defensive gate path.
        preflight = {
            "ok": False,
            "status": "physical_audio_preflight_error",
            "error": f"{type(error).__name__}: {error}",
            "requests_microphone": False,
            "captures_audio": False,
        }
    status = str(preflight.get("status") or "unknown")
    return {
        "id": "physical_capture_requirement",
        "label": "Physical speaker/microphone capture requirement",
        "ok": False,
        "returncode": "not-run",
        "seconds": 0.0,
        "timeout_seconds": 0.0,
        "command": [],
        "stdout_tail": tail_text(json.dumps(preflight, ensure_ascii=False, sort_keys=True)),
        "stderr_tail": (
            "Refused to pass: --require-physical-capture was set, but physical speaker/microphone "
            f"capture is not ready ({status})."
        ),
        "proof_contract": speech_proof_contract(exercise_live_speech=exercise_live_speech),
    }


def run_step(step: dict[str, Any], *, timeout: float, runner: CommandRunner) -> dict[str, Any]:
    started = time.monotonic()
    step_timeout = float(step.get("timeout_seconds") or timeout)
    env_overrides = step.get("env") if isinstance(step.get("env"), dict) else {}
    previous_env: dict[str, str | None] = {}
    try:
        for key, value in env_overrides.items():
            env_key = str(key)
            previous_env[env_key] = os.environ.get(env_key)
            os.environ[env_key] = str(value)
        completed = runner(list(step["command"]), step_timeout)
        return {
            "id": step["id"],
            "label": step["label"],
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "seconds": round(time.monotonic() - started, 3),
            "timeout_seconds": step_timeout,
            "command": list(step["command"]),
            "stdout_tail": tail_text(completed.stdout),
            "stderr_tail": tail_text(completed.stderr),
            "proof_contract": step.get("proof_contract"),
            "fatal": bool(step.get("fatal", True)),
        }
    except subprocess.TimeoutExpired as error:
        return {
            "id": step["id"],
            "label": step["label"],
            "ok": False,
            "returncode": "timeout",
            "seconds": round(time.monotonic() - started, 3),
            "timeout_seconds": step_timeout,
            "command": list(step["command"]),
            "stdout_tail": tail_text(error.stdout or ""),
            "stderr_tail": tail_text(error.stderr or f"Timed out after {step_timeout}s"),
            "proof_contract": step.get("proof_contract"),
            "fatal": bool(step.get("fatal", True)),
        }
    finally:
        for key, previous_value in previous_env.items():
            if previous_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous_value


def make_summary(
    *,
    base_url: str,
    run_dir: Path,
    results: list[dict[str, Any]],
    started: float,
    exercise_live_speech: bool,
    exercise_visible_navigation: bool,
    require_live_speech: bool,
    require_visible_navigation: bool,
    require_physical_capture: bool,
    complete: bool,
) -> dict[str, Any]:
    passed = sum(1 for item in results if item.get("ok"))
    failed = sum(1 for item in results if not item.get("ok") and item.get("fatal", True))
    warnings = sum(1 for item in results if not item.get("ok") and not item.get("fatal", True))
    if complete and failed == 0 and results:
        status = "passed_with_warnings" if warnings else "passed"
    else:
        status = "failed" if failed else "running"
    return {
        "schema": "jarvis.pre_build_gate.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source_commit": git_commit_short(),
        "base_url": base_url,
        "run_dir": str(run_dir),
        "report_path": str(run_dir / "summary.json"),
        "latest_path": str(run_dir.parent / "latest.json"),
        "status": status,
        "ok": status in {"passed", "passed_with_warnings"},
        "passed": passed,
        "failed": failed,
        "warnings": warnings,
        "total": len(results),
        "complete": complete,
        "canonical_latest": should_update_latest_gate(
            require_live_speech=require_live_speech,
            exercise_live_speech=exercise_live_speech,
            require_visible_navigation=require_visible_navigation,
            exercise_visible_navigation=exercise_visible_navigation,
            require_physical_capture=require_physical_capture,
        ),
        "duration_seconds": round(time.monotonic() - started, 3),
        "speech_proof_contract": speech_proof_contract(
            exercise_live_speech=exercise_live_speech,
            exercise_visible_navigation=exercise_visible_navigation,
        ),
        "require_live_speech": bool(require_live_speech),
        "require_visible_navigation": bool(require_visible_navigation),
        "exercise_visible_navigation": bool(exercise_visible_navigation),
        "require_physical_capture": bool(require_physical_capture),
        "results": results,
    }


def git_commit_short() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def write_summary(summary: dict[str, Any], run_dir: Path, output_dir: Path, *, update_latest: bool = True) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "summary.json", summary)
    markdown = render_markdown(summary)
    (run_dir / "summary.md").write_text(markdown, encoding="utf-8")
    if update_latest:
        write_json(output_dir / "latest.json", summary)
        (output_dir / "latest.md").write_text(markdown, encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Jarvis Pre-Build Gate",
        "",
        f"- Status: {summary.get('status')}",
        f"- Passed: {summary.get('passed')}/{summary.get('total')}",
        f"- Run dir: {summary.get('run_dir')}",
        f"- Speech proof: {summary.get('speech_proof_contract', {}).get('speech_mode')}",
        f"- Live speech required: {summary.get('require_live_speech')}",
        f"- Visible navigation required: {summary.get('require_visible_navigation')}",
        f"- Visible navigation exercised: {summary.get('exercise_visible_navigation')}",
        f"- Physical capture required: {summary.get('require_physical_capture')}",
    ]
    for result in summary.get("results", []):
        if not isinstance(result, dict):
            continue
        icon = "PASS" if result.get("ok") else "WARN" if not result.get("fatal", True) else "FAIL"
        lines.extend(
            [
                "",
                f"## {icon} {result.get('label')}",
                f"- Step: {result.get('id')}",
                f"- Seconds: {result.get('seconds')}",
                f"- Return code: {result.get('returncode')}",
            ]
        )
        if result.get("stderr_tail"):
            lines.append(f"- Stderr: `{result.get('stderr_tail')}`")
        proof = result.get("proof_contract")
        if isinstance(proof, dict):
            lines.append(f"- Speech proof: `{proof.get('speech_mode')}`")
            lines.append(f"- Live playback exercised: `{proof.get('live_playback_exercised')}`")
            if "visible_navigation_exercised" in proof:
                lines.append(f"- Visible navigation exercised: `{proof.get('visible_navigation_exercised')}`")
    return "\n".join(lines).rstrip() + "\n"


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


def tail_text(value: str, *, limit: int = 1800) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


if __name__ == "__main__":
    raise SystemExit(main())
