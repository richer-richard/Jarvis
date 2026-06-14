#!/usr/bin/env python3
"""Run Jarvis' overnight eight-prompt speech-audit regression matrix."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "runtime" / "regression_prompt_matrix"
BEIJING = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class MatrixCase:
    name: str
    command: str
    expect_tool: str
    expect_visible_contains: tuple[str, ...] = ()


CASES: tuple[MatrixCase, ...] = (
    MatrixCase(
        name="teams_assignment",
        command="Look in Teams for my newest Music assignment and ask me a list of questions to answer so that you have enough information to finish the assignment.",
        expect_tool="teams.assignment",
        expect_visible_contains=("signed-in Chrome",),
    ),
    MatrixCase(
        name="music_waving",
        command="Play Waving Through a Window.",
        expect_tool="localos.music_play",
        expect_visible_contains=("LocalOS",),
    ),
    MatrixCase(
        name="ram",
        command="Check in Activity Monitor how much RAM my computer is using.",
        expect_tool="diagnostics.memory_usage",
        expect_visible_contains=("Memory usage",),
    ),
    MatrixCase(
        name="codex_default",
        command="Open Codex and send a prompt called test in the Default chat.",
        expect_tool="codex.chat_plan",
        expect_visible_contains=("Default Codex chat", "confirmation"),
    ),
    MatrixCase(
        name="calendar_today",
        command="Check my calendar for my schedule today.",
        expect_tool="calendar.today_schedule",
        expect_visible_contains=("Calendar schedule",),
    ),
    MatrixCase(
        name="gemma_plan",
        command="Test the Gemma 3 4B model for me.",
        expect_tool="models.test_plan",
        expect_visible_contains=("Gemma 3 4B",),
    ),
    MatrixCase(
        name="sharpay_month",
        command="Summarize all the emails from Ms. Sharpay in the past month.",
        expect_tool="outlook.visible_summary",
        expect_visible_contains=("Ms. Sharpay",),
    ),
    MatrixCase(
        name="magic_keyboard_yuan",
        command="Jarvis, could you search up the price of the Magic Keyboard and tell me its price converted to yuan?",
        expect_tool="commerce.price_convert",
        expect_visible_contains=("Magic Keyboard", "yuan"),
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-root", default=str(OUTPUT_ROOT))
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--length-scale", type=float, default=0.85)
    parser.add_argument(
        "--allow-apple-speech",
        action="store_true",
        help="Allow voice_loop_qa.py to use Apple Speech if it is already authorized.",
    )
    parser.add_argument(
        "--stt-provider",
        choices=("auto", "apple", "local"),
        default=None,
        help="STT provider passed to voice_loop_qa.py. Defaults to local unless --allow-apple-speech is set.",
    )
    parser.add_argument(
        "--no-permission-prompts",
        action="store_true",
        help="Force no Apple Speech permission prompts. This is the unattended default unless --allow-apple-speech is set.",
    )
    args = parser.parse_args()
    stt_provider, no_permission_prompts = resolve_stt_mode(args, parser)

    stamp = datetime.now(BEIJING).strftime("%Y%m%d-%H%M%S")
    run_root = Path(args.output_root).resolve() / stamp
    run_root.mkdir(parents=True, exist_ok=False)

    results = [
        run_case(
            case,
            run_root=run_root,
            base_url=args.base_url.rstrip("/"),
            timeout=args.timeout,
            length_scale=args.length_scale,
            stt_provider=stt_provider,
            no_permission_prompts=no_permission_prompts,
        )
        for case in CASES
    ]
    passed = sum(1 for result in results if result["passed"])
    summary = {
        "generated_at": datetime.now(BEIJING).isoformat(),
        "root": str(run_root.relative_to(PROJECT_ROOT)),
        "total": len(results),
        "passed": passed,
        "ok": passed == len(results),
        "results": results,
    }
    summary_path = run_root / "summary.json"
    latest_path = run_root / "latest.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    latest_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Report: {summary_path}")
    print(f"Passed: {passed}/{len(results)}")
    return 0 if summary["ok"] else 1


def resolve_stt_mode(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> tuple[str, bool]:
    stt_provider = args.stt_provider
    if args.no_permission_prompts:
        if stt_provider in {"auto", "apple"}:
            parser.error("--no-permission-prompts can only be combined with --stt-provider local")
        stt_provider = "local"
    elif stt_provider is None:
        stt_provider = "auto" if args.allow_apple_speech else "local"

    no_permission_prompts = stt_provider == "local"
    if not no_permission_prompts and not args.allow_apple_speech:
        parser.error("--stt-provider auto/apple requires --allow-apple-speech")
    return stt_provider, no_permission_prompts


def run_case(
    case: MatrixCase,
    *,
    run_root: Path,
    base_url: str,
    timeout: float,
    length_scale: float,
    stt_provider: str,
    no_permission_prompts: bool,
) -> dict[str, object]:
    case_root = run_root / case.name
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "voice_loop_qa.py"),
        "--speech-audit-only",
        "--command",
        case.command,
        "--base-url",
        base_url,
        "--output-dir",
        str(case_root),
        "--timeout",
        str(timeout),
        "--length-scale",
        str(length_scale),
        "--expect-tool",
        case.expect_tool,
    ]
    if no_permission_prompts:
        command.append("--no-permission-prompts")
    command.extend(["--stt-provider", stt_provider])
    for expected_text in case.expect_visible_contains:
        command.extend(["--expect-visible-contains", expected_text])

    started = time.monotonic()
    completed = subprocess.run(command, cwd=PROJECT_ROOT, text=True, capture_output=True)
    duration = round(time.monotonic() - started, 3)
    report_path = find_latest_report(case_root)
    report = read_json(report_path) if report_path else {}
    result = report.get("result", {}) if isinstance(report, dict) else {}
    return {
        "name": case.name,
        "passed": completed.returncode == 0 and result.get("status") == "passed",
        "returncode": completed.returncode,
        "duration_seconds": duration,
        "report": str(report_path.relative_to(PROJECT_ROOT)) if report_path else None,
        "tool": result.get("command_response_tool"),
        "visible_reply": result.get("visible_reply_preview"),
        "speech_audit_status": (result.get("speech_audit") or {}).get("status") if isinstance(result, dict) else None,
        "stdout_tail": tail(completed.stdout),
        "stderr_tail": tail(completed.stderr),
    }


def find_latest_report(case_root: Path) -> Path | None:
    reports = sorted(case_root.glob("*/report.json"), key=lambda path: path.stat().st_mtime)
    return reports[-1] if reports else None


def read_json(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def tail(text: str, *, limit: int = 1200) -> str:
    clean = text.strip()
    if len(clean) <= limit:
        return clean
    return clean[-limit:]


if __name__ == "__main__":
    raise SystemExit(main())
