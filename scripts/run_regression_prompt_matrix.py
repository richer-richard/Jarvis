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
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.render_overnight_status import normalize_base_url
from scripts.report_refresh import refresh_report_surfaces_quietly

OUTPUT_ROOT = PROJECT_ROOT / "runtime" / "regression_prompt_matrix"
BEIJING = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class MatrixCase:
    name: str
    command: str
    expect_tool: str
    expect_visible_contains: tuple[str, ...] = ()
    expect_visible_not_contains: tuple[str, ...] = ()
    require_visible_screen_follow_up: bool = False
    expect_follow_up_tool: str | None = None
    tags: tuple[str, ...] = ("non_music",)


CASES: tuple[MatrixCase, ...] = (
    MatrixCase(
        name="teams_assignment",
        command="Look in Teams for my newest Music assignment and ask me a list of questions to answer so that you have enough information to finish the assignment.",
        expect_tool="teams.assignment",
        require_visible_screen_follow_up=True,
    ),
    MatrixCase(
        name="music_waving",
        command="Play Waving Through a Window.",
        expect_tool="localos.music_play",
        expect_visible_contains=("LocalOS",),
        tags=("music",),
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
        expect_visible_not_contains=("confirm the contact first",),
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
        "--only",
        default="",
        help="Run only matching case names or tags, comma-separated. Examples: non-music, teams_assignment, calendar_today.",
    )
    parser.add_argument(
        "--exclude",
        default="",
        help="Skip matching case names or tags, comma-separated. Example: music.",
    )
    parser.add_argument(
        "--list-cases",
        action="store_true",
        help="Print available case names and tags, then exit without running the matrix.",
    )
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
    parser.add_argument("--no-refresh-report", action="store_true")
    args = parser.parse_args()
    if args.list_cases:
        for case in CASES:
            print(f"{case.name}\t{','.join(case.tags)}")
        return 0
    try:
        selected_cases = select_cases(CASES, only=args.only, exclude=args.exclude)
    except ValueError as error:
        parser.error(str(error))
    canonical_latest = is_canonical_case_selection(selected_cases)
    try:
        base_url = normalize_base_url(args.base_url)
    except ValueError as error:
        print(f"Refused unsafe base URL: {error}", file=sys.stderr)
        return 2
    stt_provider, no_permission_prompts = resolve_stt_mode(args, parser)

    stamp = datetime.now(BEIJING).strftime("%Y%m%d-%H%M%S")
    output_root = Path(args.output_root).resolve()
    run_root = output_root / stamp
    run_root.mkdir(parents=True, exist_ok=False)

    results = [
        run_case(
            case,
            run_root=run_root,
            base_url=base_url,
            timeout=args.timeout,
            length_scale=args.length_scale,
            stt_provider=stt_provider,
            no_permission_prompts=no_permission_prompts,
        )
        for case in selected_cases
    ]
    passed = sum(1 for result in results if result["passed"])
    environment_blocked_count = sum(1 for result in results if result.get("environment_blocked"))
    user_action_required_count = sum(1 for result in results if result.get("user_action_required"))
    fallback_count = sum(1 for result in results if result.get("fallback_used"))
    total_speech_payloads = sum(int(result.get("speech_payload_count") or 0) for result in results)
    total_speech_leaks = sum(int(result.get("speech_leak_count") or 0) for result in results)
    first_visible_values = [
        float(result["first_visible_seconds"])
        for result in results
        if isinstance(result.get("first_visible_seconds"), (int, float))
    ]
    slowest_case = max(
        (
            {
                "name": str(result.get("name") or ""),
                "duration_seconds": float(result.get("duration_seconds") or 0.0),
            }
            for result in results
            if isinstance(result.get("duration_seconds"), (int, float))
        ),
        key=lambda item: item["duration_seconds"],
        default=None,
    )
    unresolved_failure_count = matrix_unresolved_failure_count(results)
    summary = {
        "generated_at": datetime.now(BEIJING).isoformat(),
        "root": str(run_root.relative_to(PROJECT_ROOT)),
        "total": len(results),
        "passed": passed,
        "ok": matrix_summary_ok(results),
        "environment_blocked_count": environment_blocked_count,
        "user_action_required_count": user_action_required_count,
        "unresolved_failure_count": unresolved_failure_count,
        "fallback_count": fallback_count,
        "max_first_visible_seconds": max(first_visible_values) if first_visible_values else None,
        "speech_payload_count": total_speech_payloads,
        "speech_leak_count": total_speech_leaks,
        "slowest_case": slowest_case,
        "canonical_latest": canonical_latest,
        "case_filter": {
            "only": args.only,
            "exclude": args.exclude,
            "selected": [case.name for case in selected_cases],
        },
        "results": results,
    }
    summary = enrich_summary_payload(summary)
    summary_path = run_root / "summary.json"
    latest_path = run_root / "latest.json"
    latest_md_path = run_root / "latest.md"
    global_latest_path = output_root / "latest.json"
    global_latest_md_path = output_root / "latest.md"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    latest_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    latest_md_path.write_text(render_markdown(summary), encoding="utf-8")
    if canonical_latest:
        global_latest_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        global_latest_md_path.write_text(latest_md_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Report: {summary_path}")
    print(f"Passed: {passed}/{len(results)}")
    print(f"Canonical latest: {'yes' if canonical_latest else 'no'}")
    print(f"Environment blocked: {summary.get('environment_blocked_count', 0)}")
    print(f"Needs action: {summary.get('user_action_required_count', 0)}")
    if not args.no_refresh_report:
        refresh = refresh_report_surfaces_quietly(base_url)
        if refresh.get("ok"):
            print(f"Refreshed Jarvis report surfaces: {base_url}/overnight-report/")
        else:
            print(f"Warning: Jarvis report refresh failed: {refresh.get('error')}", file=sys.stderr)
    return 0 if summary["ok"] else 1


def enrich_summary_payload(summary: dict[str, object]) -> dict[str, object]:
    payload = dict(summary)
    original_results = payload.get("results") if isinstance(payload.get("results"), list) else []
    enriched_results = [enrich_case_summary(item) for item in original_results if isinstance(item, dict)]
    payload["results"] = enriched_results
    payload["environment_blocked_count"] = sum(1 for item in enriched_results if item.get("environment_blocked"))
    payload["user_action_required_count"] = sum(1 for item in enriched_results if item.get("user_action_required"))
    payload["unresolved_failure_count"] = matrix_unresolved_failure_count(enriched_results)
    payload["ok"] = matrix_summary_ok(enriched_results)
    payload["fallback_count"] = sum(1 for item in enriched_results if item.get("fallback_used"))
    first_visible_values = [
        float(item["first_visible_seconds"])
        for item in enriched_results
        if isinstance(item.get("first_visible_seconds"), (int, float))
    ]
    payload["max_first_visible_seconds"] = max(first_visible_values) if first_visible_values else None
    payload["slowest_case"] = max(
        (
            {
                "name": str(item.get("name") or ""),
                "duration_seconds": float(item.get("duration_seconds") or 0.0),
            }
            for item in enriched_results
            if isinstance(item.get("duration_seconds"), (int, float))
        ),
        key=lambda item: item["duration_seconds"],
        default=None,
    )
    payload["canonical_latest"] = is_canonical_summary(payload)
    return payload


def is_canonical_case_selection(selected_cases: tuple[MatrixCase, ...]) -> bool:
    return [case.name for case in selected_cases] == [case.name for case in CASES]


def is_canonical_summary(summary: dict[str, object]) -> bool:
    if summary.get("canonical_latest") is True:
        return True
    case_filter = summary.get("case_filter")
    if not isinstance(case_filter, dict):
        return False
    selected = case_filter.get("selected")
    return list(selected) == [case.name for case in CASES]


def matrix_summary_ok(results: list[dict[str, object]]) -> bool:
    """Pass unattended runs when the only missed case is a clean environment block."""
    return (
        matrix_unresolved_failure_count(results) == 0
        and sum(1 for item in results if item.get("user_action_required")) == 0
    )


def matrix_unresolved_failure_count(results: list[dict[str, object]]) -> int:
    return sum(
        1
        for item in results
        if not item.get("passed")
        and not _is_clean_environment_block(item)
        and not _is_clean_user_action_block(item)
    )


def _is_clean_environment_block(item: dict[str, object]) -> bool:
    return bool(item.get("environment_blocked")) and _speech_side_passed(item)


def _is_clean_user_action_block(item: dict[str, object]) -> bool:
    return bool(item.get("user_action_required")) and _speech_side_passed(item)


def _speech_side_passed(item: dict[str, object]) -> bool:
    return bool(item.get("speech_audit_gate_passed", True)) and int(item.get("speech_leak_count") or 0) == 0


def select_cases(
    cases: tuple[MatrixCase, ...],
    *,
    only: str = "",
    exclude: str = "",
) -> tuple[MatrixCase, ...]:
    only_tokens = _case_filter_tokens(only)
    exclude_tokens = _case_filter_tokens(exclude)
    known_labels = {"all"}
    for case in cases:
        known_labels.update(_case_labels(case))
    unknown = sorted((only_tokens | exclude_tokens) - known_labels)
    if unknown:
        raise ValueError(f"Unknown matrix case or tag: {', '.join(unknown)}")

    selected: list[MatrixCase] = []
    for case in cases:
        labels = _case_labels(case)
        if only_tokens and "all" not in only_tokens and not (labels & only_tokens):
            continue
        if exclude_tokens and (labels & exclude_tokens):
            continue
        selected.append(case)
    if not selected:
        raise ValueError("No regression matrix cases selected.")
    return tuple(selected)


def _case_filter_tokens(value: str) -> set[str]:
    tokens = {
        _normalize_case_filter_token(token)
        for token in re_split_case_filter(value)
    }
    return {token for token in tokens if token}


def re_split_case_filter(value: str) -> list[str]:
    return [token for token in str(value or "").replace(",", " ").split()]


def _case_labels(case: MatrixCase) -> set[str]:
    return {_normalize_case_filter_token(case.name), *(_normalize_case_filter_token(tag) for tag in case.tags)}


def _normalize_case_filter_token(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_")


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
    base_url = normalize_base_url(base_url)
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
    for unexpected_text in case.expect_visible_not_contains:
        command.extend(["--expect-visible-not-contains", unexpected_text])

    started = time.monotonic()
    completed = subprocess.run(command, cwd=PROJECT_ROOT, text=True, capture_output=True)
    duration = round(time.monotonic() - started, 3)
    report_path = find_latest_report(case_root)
    report = read_json(report_path) if report_path else {}
    result = report.get("result", {}) if isinstance(report, dict) else {}
    response_result = result.get("command_response_result") if isinstance(result, dict) and isinstance(result.get("command_response_result"), dict) else {}
    stream_timing = result.get("stream_timing") if isinstance(result, dict) and isinstance(result.get("stream_timing"), dict) else {}
    speech_audit = result.get("speech_audit") if isinstance(result, dict) else {}
    if not isinstance(speech_audit, dict):
        speech_audit = {}
    visible_screen_follow_up = (
        result.get("visible_screen_follow_up")
        if isinstance(result, dict) and isinstance(result.get("visible_screen_follow_up"), dict)
        else {}
    )
    speech_payload_count = int(speech_audit.get("payload_count") or 0)
    speech_leak_count = int(speech_audit.get("leak_count") or 0)
    speech_gate = speech_audit_gate(
        status=str(speech_audit.get("status") or ""),
        payload_count=speech_payload_count,
        leak_count=speech_leak_count,
    )
    follow_up_gate = visible_screen_follow_up_gate(
        visible_screen_follow_up,
        required=case.require_visible_screen_follow_up,
        expect_tool=case.expect_follow_up_tool,
    )
    return {
        "name": case.name,
        "passed": completed.returncode == 0 and result.get("status") == "passed" and speech_gate["passed"] and follow_up_gate["passed"],
        "environment_blocked": bool(follow_up_gate.get("environment_blocked")),
        "user_action_required": bool(follow_up_gate.get("user_action_required")),
        "honest_incomplete": bool(follow_up_gate.get("honest_incomplete")),
        "blocking_reason": follow_up_gate.get("blocking_reason"),
        "returncode": completed.returncode,
        "duration_seconds": duration,
        "report": str(report_path.relative_to(PROJECT_ROOT)) if report_path else None,
        "tool": result.get("command_response_tool"),
        "final_visible_tool": result.get("final_visible_tool"),
        "backend": response_result.get("backend"),
        "model": response_result.get("model"),
        "fallback_used": bool(response_result.get("fallback_used")),
        "primary_fallback_used": bool(response_result.get("primary_fallback_used")),
        "fallback_trigger": response_result.get("fallback_trigger"),
        "primary_status": response_result.get("primary_status"),
        "tool_catalog_compacted": bool(response_result.get("tool_catalog_compacted")),
        "first_visible_seconds": stream_timing.get("first_visible_seconds"),
        "first_status_seconds": stream_timing.get("first_status_seconds"),
        "first_final_seconds": stream_timing.get("first_final_seconds"),
        "first_speech_payload_seconds": stream_timing.get("first_speech_payload_seconds"),
        "model_reported_first_visible_seconds": response_result.get("first_visible_token_seconds"),
        "model_reported_total_seconds": response_result.get("duration_seconds"),
        "visible_reply": result.get("visible_reply_preview"),
        "speech_audit_status": speech_audit.get("status"),
        "speech_payload_count": speech_payload_count,
        "speech_leak_count": speech_leak_count,
        "speech_audit_gate_passed": speech_gate["passed"],
        "speech_audit_failures": speech_gate["failures"],
        "visible_screen_follow_up_status": visible_screen_follow_up.get("status"),
        "visible_screen_follow_up_tool": visible_screen_follow_up.get("tool"),
        "visible_screen_follow_up_used": bool(visible_screen_follow_up.get("used")),
        "visible_screen_follow_up_failures": follow_up_gate["failures"],
        "stdout_tail": tail(completed.stdout),
        "stderr_tail": tail(completed.stderr),
    }


def enrich_case_summary(item: dict[str, object]) -> dict[str, object]:
    enriched = dict(item)
    report_value = enriched.get("report")
    report_path = PROJECT_ROOT / str(report_value) if str(report_value or "").strip() else None
    report = read_json(report_path) if report_path else {}
    result = report.get("result", {}) if isinstance(report, dict) else {}
    response_result = result.get("command_response_result") if isinstance(result, dict) and isinstance(result.get("command_response_result"), dict) else {}
    stream_timing = result.get("stream_timing") if isinstance(result, dict) and isinstance(result.get("stream_timing"), dict) else {}
    speech_audit = result.get("speech_audit") if isinstance(result, dict) and isinstance(result.get("speech_audit"), dict) else {}
    visible_screen_follow_up = (
        result.get("visible_screen_follow_up")
        if isinstance(result, dict) and isinstance(result.get("visible_screen_follow_up"), dict)
        else {}
    )

    enriched.setdefault("tool", result.get("command_response_tool"))
    enriched.setdefault("final_visible_tool", result.get("final_visible_tool"))
    if response_result:
        enriched.update(
            {
                "backend": response_result.get("backend"),
                "model": response_result.get("model"),
                "fallback_used": bool(response_result.get("fallback_used")),
                "primary_fallback_used": bool(response_result.get("primary_fallback_used")),
                "fallback_trigger": response_result.get("fallback_trigger"),
                "primary_status": response_result.get("primary_status"),
                "tool_catalog_compacted": bool(response_result.get("tool_catalog_compacted")),
                "model_reported_first_visible_seconds": response_result.get("first_visible_token_seconds"),
                "model_reported_total_seconds": response_result.get("duration_seconds"),
            }
        )
    if stream_timing:
        enriched.update(
            {
                "first_visible_seconds": stream_timing.get("first_visible_seconds"),
                "first_status_seconds": stream_timing.get("first_status_seconds"),
                "first_final_seconds": stream_timing.get("first_final_seconds"),
                "first_speech_payload_seconds": stream_timing.get("first_speech_payload_seconds"),
            }
        )
    if speech_audit:
        enriched.setdefault("speech_audit_status", speech_audit.get("status"))
        enriched.setdefault("speech_payload_count", int(speech_audit.get("payload_count") or 0))
        enriched.setdefault("speech_leak_count", int(speech_audit.get("leak_count") or 0))
    if visible_screen_follow_up:
        enriched.setdefault("visible_screen_follow_up_status", visible_screen_follow_up.get("status"))
        enriched.setdefault("visible_screen_follow_up_tool", visible_screen_follow_up.get("tool"))
        enriched.setdefault("visible_screen_follow_up_used", bool(visible_screen_follow_up.get("used")))
    enriched.setdefault("honest_incomplete", str(enriched.get("blocking_reason") or "") == "assignment_subject_mismatch")
    enriched.setdefault(
        "user_action_required",
        bool(enriched.get("blocking_reason"))
        and not bool(enriched.get("environment_blocked"))
        and not bool(enriched.get("honest_incomplete")),
    )
    return enriched


def speech_audit_gate(*, status: str, payload_count: int, leak_count: int) -> dict[str, object]:
    """Require actual audible-output evidence for every speech-audit matrix row."""
    failures: list[str] = []
    if status != "passed":
        failures.append(f"Speech audit status was {status or 'missing'}.")
    if payload_count < 1:
        failures.append("Speech audit captured no spoken payloads.")
    if leak_count:
        failures.append(f"Speech audit found {leak_count} internal speech leak(s).")
    return {"passed": not failures, "failures": failures}


def visible_screen_follow_up_gate(
    visible_screen_follow_up: dict[str, object],
    *,
    required: bool,
    expect_tool: str | None,
) -> dict[str, object]:
    if not required:
        return {
            "passed": True,
            "failures": [],
            "environment_blocked": False,
            "user_action_required": False,
            "honest_incomplete": False,
            "blocking_reason": "",
        }
    failures: list[str] = []
    environment_blocked = False
    user_action_required = False
    blocking_reason = ""
    status = str(visible_screen_follow_up.get("status") or "")
    honest_terminal_statuses = {"assignment_subject_mismatch"}
    if status in honest_terminal_statuses:
        expected_tool = str(expect_tool or "").strip()
        if expected_tool and str(visible_screen_follow_up.get("tool") or "") != expected_tool:
            return {
                "passed": False,
                "failures": [
                    f"Visible screen follow-up tool was {visible_screen_follow_up.get('tool') or '(none)'}, expected {expected_tool}."
                ],
                "environment_blocked": False,
                "user_action_required": False,
                "honest_incomplete": False,
                "blocking_reason": "",
            }
        return {
            "passed": False,
            "failures": ["Visible screen follow-up found an assignment, but it was not the requested Music assignment."],
            "environment_blocked": False,
            "user_action_required": False,
            "honest_incomplete": True,
            "blocking_reason": "assignment_subject_mismatch",
        }
    if status != "completed":
        failures.append(f"Visible screen follow-up status was {status or 'missing'}.")
    if not visible_screen_follow_up.get("used"):
        if status == "browser_permission_blocked":
            environment_blocked = True
            blocking_reason = "chrome_automation"
            failures.append("Chrome Automation blocked Jarvis from reading the signed-in browser page.")
        elif status == "login_gate_visible":
            user_action_required = True
            blocking_reason = "login_gate"
            failures.append("Visible screen follow-up reached a password or sign-in gate before the target page.")
        else:
            failures.append("Visible screen follow-up did not run.")
    expected_tool = str(expect_tool or "").strip()
    if expected_tool and str(visible_screen_follow_up.get("tool") or "") != expected_tool:
        failures.append(
            f"Visible screen follow-up tool was {visible_screen_follow_up.get('tool') or '(none)'}, expected {expected_tool}."
        )
    return {
        "passed": not failures,
        "failures": failures,
        "environment_blocked": environment_blocked,
        "user_action_required": user_action_required,
        "honest_incomplete": False,
        "blocking_reason": blocking_reason,
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


def render_markdown(summary: dict[str, object]) -> str:
    results = summary.get("results") if isinstance(summary.get("results"), list) else []
    lines = [
        "# Jarvis Regression Prompt Matrix",
        "",
        f"Generated: {summary.get('generated_at', '')}",
        f"Status: {'passed' if summary.get('ok') else 'failed'}",
        f"Passed: {summary.get('passed', 0)} / {summary.get('total', 0)}",
        f"Blocked: {summary.get('environment_blocked_count', 0)}",
        f"Needs action: {summary.get('user_action_required_count', 0)}",
        f"Unresolved failures: {summary.get('unresolved_failure_count', 0)}",
        f"Fallbacks: {summary.get('fallback_count', 0)}",
        f"Max first visible: {format_seconds_cell(summary.get('max_first_visible_seconds'))}",
        f"Speech audit: {summary.get('speech_payload_count', 0)} payloads, {summary.get('speech_leak_count', 0)} leaks",
        f"Slowest case: {slowest_case_text(summary.get('slowest_case'))}",
        f"Run root: `{summary.get('root', '')}`",
        "",
        "| Case | Result | Tool | Follow-up | Route | First visible | Total | Speech | Reply |",
        "| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for item in results:
        if not isinstance(item, dict):
            continue
        result = (
            "blocked"
            if item.get("environment_blocked")
            else "needs action"
            if item.get("user_action_required")
            else "incomplete"
            if item.get("honest_incomplete")
            else "pass"
            if item.get("passed")
            else "fail"
        )
        case_name = str(item.get("name") or "")
        tool = str(item.get("tool") or "")
        follow_up = follow_up_label(item)
        route = route_label(item)
        speech = (
            f"{item.get('speech_audit_status') or 'unknown'}, "
            f"{int(item.get('speech_payload_count') or 0)} payloads, "
            f"{int(item.get('speech_leak_count') or 0)} leaks"
        )
        first_visible = format_seconds_cell(item.get("first_visible_seconds"))
        total = format_seconds_cell(item.get("duration_seconds"))
        reply = compact_preview(item.get("visible_reply"))
        lines.append(f"| {case_name} | {result} | `{tool}` | `{follow_up}` | `{route}` | {first_visible} | {total} | {speech} | {reply} |")
    return "\n".join(lines) + "\n"


def route_label(item: dict[str, object]) -> str:
    backend = str(item.get("backend") or "").strip()
    model = str(item.get("model") or "").strip()
    if backend and model:
        label = f"{backend}/{model}"
    elif backend:
        label = backend
    elif model:
        label = model
    else:
        label = "direct"
    extras: list[str] = []
    if item.get("fallback_used"):
        extras.append("fallback")
    if item.get("tool_catalog_compacted"):
        extras.append("compact")
    if extras:
        label = f"{label} {' '.join(extras)}"
    return label


def follow_up_label(item: dict[str, object]) -> str:
    if not item.get("visible_screen_follow_up_used"):
        status = str(item.get("visible_screen_follow_up_status") or "")
        tool = str(item.get("visible_screen_follow_up_tool") or "")
        if status and tool:
            return f"{status}:{tool}"
        return status or tool or "none"
    tool = str(item.get("visible_screen_follow_up_tool") or "")
    status = str(item.get("visible_screen_follow_up_status") or "")
    if tool and status:
        return f"{status}:{tool}"
    return tool or status or "used"


def format_seconds_cell(value: object) -> str:
    try:
        if value in (None, ""):
            return "n/a"
        return f"{float(value):.3f}s"
    except (TypeError, ValueError):
        return "n/a"


def slowest_case_text(value: object) -> str:
    if not isinstance(value, dict):
        return "n/a"
    name = str(value.get("name") or "").strip()
    seconds = format_seconds_cell(value.get("duration_seconds"))
    if not name:
        return seconds
    return f"{name} ({seconds})"


def compact_preview(value: object, *, limit: int = 120) -> str:
    text = " ".join(str(value or "").replace("|", "/").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


if __name__ == "__main__":
    raise SystemExit(main())
