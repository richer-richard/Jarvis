#!/usr/bin/env python3
"""Print a read-only morning status summary for Jarvis."""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://127.0.0.1:8765"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
MAX_VERIFICATION_AGE_SECONDS = 12 * 60 * 60
VERIFICATION_HIGHLIGHTS = {
    "endpoint_read_only_shell_allowlist": "shell allowlist routing",
    "endpoint_readiness": "readiness summary",
    "endpoint_preflight": "local preflight summary",
    "endpoint_plan_preview": "plan-only command preview",
    "endpoint_wake_simulation": "text wake simulation + command assessment",
    "endpoint_prompt_injection_scan": "prompt-injection scan",
    "morning_status_base_url_command": "morning status URL normalization",
    "dashboard_non_loopback_rejected": "loopback bind guard",
    "dashboard_invalid_port_rejected": "dashboard port guard",
    "isolated_response_security_headers": "localhost hardening",
    "isolated_bad_host_header_rejected": "Host header guard",
    "isolated_plain_text_command_rejected": "JSON POST guard",
    "isolated_plain_text_plan_rejected": "JSON preview guard",
    "isolated_malformed_json_post_rejected": "malformed JSON guard",
    "isolated_sed_write_shell_policy": "sed write-script policy",
    "isolated_awk_file_shell_policy": "awk script-file policy",
    "isolated_secret_filename_shell_policy": "secret filename policy",
    "isolated_pause_blocks_commands": "pause mode",
    "isolated_readiness_available_while_paused": "paused readiness",
    "isolated_plan_available_while_paused": "paused preview",
    "start_paused_mode_endpoint": "start-paused launch",
    "swift_host_probe_readiness": "Swift readiness probe",
    "swift_host_probe_preflight": "Swift preflight probe",
    "swift_host_probe_plan": "Swift preview probe",
    "swift_host_probe_pause": "Swift pause probe",
    "swift_host_probe_resume": "Swift resume probe",
    "swift_host_probe_jarvis_base_url_command": "Swift URL environment normalization",
    "swift_worker_concurrency_self_test": "worker startup concurrency",
    "swift_worker_monitor_self_test": "worker monitor recovery",
    "swift_worker_autostart_disabled_self_test": "worker autostart opt-out",
    "swift_worker_autostart_disabled_no_worker": "autostart opt-out no-worker guard",
    "temporary_app_bundle_build": "temporary app bundle",
    "temporary_app_autostart_disabled_self_test": "bundled autostart opt-out",
    "temporary_app_autostart_disabled_no_worker": "bundled opt-out no-worker guard",
}
REQUIREMENT_AUDIT_IDS = {
    "stronger_layered_tool_loop",
    "app_opening_groundwork",
    "safe_terminal_groundwork",
    "voice_recognition_audition_prep",
    "master_report",
    "rebuilt_bundle",
}
REQUIREMENT_STATUS_LABELS = {
    "implemented_terminal_verified": "implemented terminal-verified",
    "implemented_live_verified": "implemented live-verified",
    "prepared": "prepared",
    "prepared_live_verified": "prepared live-verified",
    "available": "available",
    "available_live_verified": "available live-verified",
    "partial": "partial",
    "missing": "missing",
    "artifact_missing": "artifact missing",
}
REQUIREMENT_STATUS_ORDER = [
    "implemented live-verified",
    "implemented terminal-verified",
    "prepared live-verified",
    "prepared",
    "available live-verified",
    "available",
    "partial",
    "artifact missing",
    "missing",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Print a read-only Jarvis morning status summary.")
    parser.add_argument("--base-url", default=None, help="Worker base URL. Defaults to JARVIS_URL, JARVIS_BASE_URL, or http://127.0.0.1:8765.")
    args = parser.parse_args()
    try:
        base_url = normalize_base_url(args.base_url) if args.base_url else base_url_from_environment()
    except ValueError as error:
        print(f"Worker: refused unsafe base URL ({error})")
        return 2

    print("Jarvis morning status")
    print(f"Project: {PROJECT_ROOT}")
    print_worker_status(base_url)
    print_report_surfaces(base_url)
    print_latest_verification()
    print_latest_pre_build_gate()
    print_latest_context_smoke()
    print_latest_wake_threshold()
    print_physical_capture_contract()
    print_requirement_audit()
    print_latest_latency_smoke()
    print_current_bundle()
    print_process_status(base_url)
    return 0


def print_worker_status(base_url: str) -> None:
    try:
        health = get_json(f"{base_url.rstrip('/')}/api/health", timeout=2)
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as error:
        print(f"Worker: offline or unavailable at {base_url} ({error})")
        return

    mode = health.get("mode")
    runtime = health.get("status", {}).get("runtime")
    if not isinstance(mode, dict) or not isinstance(runtime, dict):
        print(f"Worker: online at {base_url}, but stale metadata is missing")
        print("Action: restart the existing worker, then run `python3 scripts/run_dashboard.py` to load current code")
        return

    mode_label = "Paused" if mode.get("paused") else "Live"
    pid = runtime.get("pid", "unknown")
    uptime = format_uptime(float(runtime.get("uptime_seconds") or 0))
    print(f"Worker: {mode_label} at {base_url} (pid {pid}, uptime {uptime})")
    print_fast_model_status(health.get("status", {}).get("fast_model"))
    print_timer_status(health.get("status", {}).get("timers"))
    print_codex_job_status(health.get("status", {}).get("codex_jobs"))
    print_worker_source(runtime)


def print_fast_model_status(fast_model: Any) -> None:
    if not isinstance(fast_model, dict):
        print("Fast model: unknown")
        return
    backend = fast_model.get("backend") or "unknown"
    model = fast_model.get("model") or "unknown"
    availability = "available" if fast_model.get("available") else "unavailable"
    timeout = fast_model.get("timeout_seconds")
    max_tokens = fast_model.get("max_tokens")
    details = [availability]
    if timeout is not None:
        details.append(f"timeout {timeout}s")
    if max_tokens is not None:
        details.append(f"max {max_tokens} tokens")
    if backend == "groq":
        key_state = "key configured" if fast_model.get("groq_key_configured") else "key missing"
        details.append(key_state)
    if fast_model.get("fallback_enabled"):
        fallback_backend = fast_model.get("fallback_backend") or "unknown"
        fallback_model = fast_model.get("fallback_model") or "unknown"
        details.append(f"fallback {fallback_backend}/{fallback_model}")
    print(f"Fast model: {backend} / {model} ({', '.join(details)})")


def print_worker_source(runtime: dict[str, Any]) -> None:
    source = str(runtime.get("source") or "")
    if not source:
        print("Worker source: unknown")
        return
    print(f"Worker source: {classify_worker_source(source)} ({display_path(source)})")


def print_timer_status(timers: Any) -> None:
    if not isinstance(timers, dict):
        return
    active_count = timers.get("active_count")
    if active_count is not None:
        print(f"Timers: {active_count} active")


def print_codex_job_status(codex_jobs: Any) -> None:
    if not isinstance(codex_jobs, dict):
        return
    tracked = codex_jobs.get("tracked_count")
    running = codex_jobs.get("running_count")
    if tracked is None or running is None:
        return
    latest_job_id = codex_jobs.get("latest_job_id")
    latest_status = codex_jobs.get("latest_status")
    suffix = ""
    if latest_job_id and latest_status:
        suffix = f", latest {latest_job_id} {latest_status}"
    print(f"Codex jobs: {running} running, {tracked} tracked{suffix}")


def print_latest_verification() -> None:
    reports = sorted((PROJECT_ROOT / "runtime" / "verification").glob("verify-safe-*.json"))
    if not reports:
        print("Latest verification: none")
        return

    latest = reports[-1]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"Latest verification: {latest.relative_to(PROJECT_ROOT)} unreadable ({error})")
        return

    results = data.get("results", [])
    passed = sum(1 for result in results if result.get("passed"))
    total = len(results)
    state = "passed" if data.get("ok") else "failed"
    timestamp = verification_timestamp(latest, data)
    age_seconds = time_since(timestamp)
    age = format_uptime(age_seconds)
    print(f"Latest verification: {state} {passed}/{total} ({latest.relative_to(PROJECT_ROOT)}, age {age})")
    action = verification_action(bool(data.get("ok")), age_seconds)
    if action:
        print(f"Action: {action}")
    highlights = verification_highlights(results)
    if highlights:
        print(f"Verification includes: {', '.join(highlights)}")
    window_probe = verification_window_probe(results)
    if window_probe:
        print(f"Latest window probe: {window_probe}")


def print_latest_pre_build_gate() -> None:
    latest = PROJECT_ROOT / "runtime" / "pre_build_gate" / "latest.json"
    if not latest.exists():
        print("Latest pre-build gate: none")
        return

    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"Latest pre-build gate: {latest.relative_to(PROJECT_ROOT)} unreadable ({error})")
        return

    summary = pre_build_gate_summary(data)
    age = format_uptime(time_since(latest.stat().st_mtime))
    report_path = data.get("report_path") or str(latest)
    report_display = display_path(str(report_path))
    step_suffix = f", steps {', '.join(summary['step_ids'])}" if summary["step_ids"] else ""
    print(
        f"Latest pre-build gate: {summary['status']}, {summary['passed']}/{summary['total']} passed "
        f"{summary['detail']}({report_display}, age {age}{step_suffix})"
    )
    teams_blocker = pre_build_gate_teams_blocker(data)
    if teams_blocker:
        print(f"Teams blocker: {teams_blocker}")


def pre_build_gate_summary(data: dict[str, Any]) -> dict[str, Any]:
    results = data.get("results", [])
    if not isinstance(results, list):
        results = []
    step_ids: list[str] = []
    passed = 0
    for item in results:
        if not isinstance(item, dict):
            continue
        step_id = str(item.get("id") or "").strip()
        if step_id:
            step_ids.append(step_id)
        if item.get("ok"):
            passed += 1
    total = int(data.get("total") or len(results))
    reported_passed = int(data.get("passed") or passed)
    fatal_failures = int(data.get("failed") or 0)
    warnings = int(data.get("warnings") or 0)
    if not fatal_failures and not warnings:
        fatal_failures = sum(1 for item in results if isinstance(item, dict) and not item.get("ok") and item.get("fatal", True))
        warnings = sum(1 for item in results if isinstance(item, dict) and not item.get("ok") and not item.get("fatal", True))
    status = "passed" if data.get("ok") else "needs attention"
    if data.get("status"):
        status = str(data.get("status"))
    detail_parts = []
    if fatal_failures:
        detail_parts.append(f"fatal {fatal_failures}")
    if warnings:
        detail_parts.append(f"warnings {warnings}")
    detail = f"({', '.join(detail_parts)}) " if detail_parts else ""
    return {
        "status": status,
        "passed": reported_passed,
        "total": total,
        "fatal_failures": fatal_failures,
        "warnings": warnings,
        "detail": detail,
        "step_ids": step_ids,
    }


def pre_build_gate_teams_blocker(data: dict[str, Any]) -> str:
    full_loop_path = pre_build_gate_full_loop_report_path(data)
    if not full_loop_path:
        return ""
    try:
        full_loop = json.loads(full_loop_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    results = full_loop.get("results")
    if not isinstance(results, list):
        return ""
    for item in results:
        if not isinstance(item, dict) or item.get("case_id") != "teams_music_assignment_honesty":
            continue
        if str(item.get("status") or "") == "passed":
            return ""
        proof = item.get("action_proof") if isinstance(item.get("action_proof"), dict) else {}
        completion = str(proof.get("completion_status") or item.get("status") or "unknown")
        parts = [f"Teams assignment is {completion}"]
        if proof.get("chrome_page_read_blocked"):
            parts.append("Chrome page-read is blocked")
        if proof.get("requested_class_navigation_plan_ready"):
            plan = (
                proof.get("requested_class_navigation_plan")
                if isinstance(proof.get("requested_class_navigation_plan"), dict)
                else {}
            )
            point = plan.get("point") if isinstance(plan.get("point"), dict) else {}
            target_text = str(plan.get("target_text") or "requested class").strip() or "requested class"
            point_text = ""
            if point:
                point_text = f" at ({point.get('x')}, {point.get('y')})"
            parts.append(f"{target_text} no-click navigation plan is ready{point_text}")
        if proof.get("assignments_navigation_plan_ready"):
            plan = proof.get("assignments_navigation_plan") if isinstance(proof.get("assignments_navigation_plan"), dict) else {}
            point = plan.get("point") if isinstance(plan.get("point"), dict) else {}
            point_text = ""
            if point:
                point_text = f" at ({point.get('x')}, {point.get('y')})"
            parts.append(f"Assignments no-click navigation plan is ready{point_text}")
        elif proof.get("assignments_target_found"):
            parts.append("Assignments OCR target was found")
        return "; ".join(parts) + "."
    return ""


def pre_build_gate_full_loop_report_path(data: dict[str, Any]) -> Path | None:
    results = data.get("results")
    if not isinstance(results, list):
        return None
    for item in results:
        if not isinstance(item, dict) or item.get("id") != "full_loop_regression":
            continue
        text = "\n".join(str(item.get(key) or "") for key in ("stdout", "stdout_tail", "stderr", "stderr_tail"))
        match = re.search(r"Report:\s+(.+?summary\.json)", text)
        if not match:
            continue
        path = Path(match.group(1).strip())
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path
    return None


def print_latest_context_smoke() -> None:
    latest = PROJECT_ROOT / "runtime" / "conversation_context" / "latest.json"
    if not latest.exists():
        print("Latest context smoke: none")
        return

    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"Latest context smoke: {latest.relative_to(PROJECT_ROOT)} unreadable ({error})")
        return

    summary = context_smoke_summary(data)
    state = "passed" if summary["ok"] else "needs attention"
    used = "used history" if summary["used_history"] else "did not use history"
    age = format_uptime(time_since(latest.stat().st_mtime))
    print(
        f"Latest context smoke: {state} ({used}, total {summary['total_seconds']:.3f}s, "
        f"{latest.relative_to(PROJECT_ROOT)}, age {age})"
    )


def print_latest_wake_threshold() -> None:
    latest = PROJECT_ROOT / "runtime" / "wake_threshold" / "latest.json"
    if not latest.exists():
        print("Latest wake threshold: none")
        return

    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"Latest wake threshold: {latest.relative_to(PROJECT_ROOT)} unreadable ({error})")
        return

    summary = wake_threshold_summary(data)
    state = "passed" if summary["ok"] else "needs attention"
    reject = ""
    if summary["closest_reject_label"]:
        reject = f", closest reject {summary['closest_reject_label']} {summary['closest_reject_score']:.3f}"
    age = format_uptime(time_since(latest.stat().st_mtime))
    print(
        f"Latest wake threshold: {state} {summary['passed']}/{summary['total']}"
        f"{reject} ({latest.relative_to(PROJECT_ROOT)}, age {age})"
    )


def print_physical_capture_contract() -> None:
    print("Physical audio loop: not implemented; strict speaker/microphone capture proof fails closed by design")


def print_requirement_audit() -> None:
    try:
        project_root_text = str(PROJECT_ROOT)
        if project_root_text not in sys.path:
            sys.path.insert(0, project_root_text)
        from jarvis.tools import final_qa_plan_status

        data = final_qa_plan_status()
    except Exception as error:  # pragma: no cover - defensive status reporting
        print(f"Requirement audit: unavailable ({error})")
        return

    audit = data.get("requirement_audit") if isinstance(data, dict) else None
    if not isinstance(audit, list) or not audit:
        print("Requirement audit: unavailable")
        return
    print(f"Requirement audit: {requirement_audit_summary(audit)}")


def requirement_audit_summary(audit: list[dict[str, Any]]) -> str:
    status_counts: dict[str, int] = {}
    remaining: list[str] = []
    seen_ids: set[str] = set()
    for item in audit:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        if item_id:
            seen_ids.add(item_id)
        raw_status = str(item.get("status") or "unknown")
        status = REQUIREMENT_STATUS_LABELS.get(raw_status, raw_status.replace("_", " "))
        status_counts[status] = status_counts.get(status, 0) + 1
        note = str(item.get("remaining") or "").strip()
        if note and note not in remaining:
            remaining.append(note)

    parts: list[str] = []
    if status_counts:
        ordered_statuses = [status for status in REQUIREMENT_STATUS_ORDER if status in status_counts]
        ordered_statuses.extend(sorted(status for status in status_counts if status not in set(REQUIREMENT_STATUS_ORDER)))
        parts.append(", ".join(f"{status} {status_counts[status]}" for status in ordered_statuses))
    missing = sorted(REQUIREMENT_AUDIT_IDS - seen_ids)
    if missing:
        parts.append(f"missing audit rows: {', '.join(missing)}")
    if remaining:
        shown = remaining[:4]
        suffix = "; ..." if len(remaining) > len(shown) else ""
        parts.append(f"remaining: {'; '.join(shown)}{suffix}")
    return "; ".join(parts) if parts else "no status rows"


def print_latest_latency_smoke() -> None:
    reports = sorted((PROJECT_ROOT / "runtime" / "model_benchmarks").glob("localhost-fast-latency-*.json"))
    if not reports:
        print("Latest fast latency: none")
        return

    latest = reports[-1]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"Latest fast latency: {latest.relative_to(PROJECT_ROOT)} unreadable ({error})")
        return

    summary = latency_smoke_summary(data)
    age = format_uptime(time_since(latest.stat().st_mtime))
    if summary["total"] == 0:
        print(f"Latest fast latency: no prompt results ({latest.relative_to(PROJECT_ROOT)}, age {age})")
        return

    state = "passed" if summary["ok"] else "needs attention"
    first = summary["max_first_visible_seconds"]
    total = summary["max_total_seconds"]
    after_first = summary.get("min_after_first_chars_per_second")
    rate_text = f", min after-first {after_first:.1f} chars/s" if after_first else ""
    print(
        f"Latest fast latency: {state} {summary['completed']}/{summary['total']} "
        f"(max first visible {first:.3f}s, max total {total:.3f}s{rate_text}, {latest.relative_to(PROJECT_ROOT)}, age {age})"
    )


def latency_smoke_summary(data: dict[str, Any]) -> dict[str, Any]:
    results = data.get("results", [])
    if not isinstance(results, list):
        results = []
    max_first_allowed = float(data.get("max_first_visible_seconds") or 3.0)
    max_total_allowed = float(data.get("max_total_seconds") or 5.0)
    min_after_first_cps = float(data.get("min_after_first_chars_per_second") or 20.0)
    min_rate_visible_chars = int(float(data.get("min_rate_visible_chars") or 20.0))
    completed = 0
    first_values: list[float] = []
    total_values: list[float] = []
    after_first_cps_values: list[float] = []
    ok = True
    for result in results:
        if not isinstance(result, dict):
            ok = False
            continue
        if latency_status_counts_as_success(result.get("status")):
            completed += 1
        else:
            ok = False
        first = numeric_value(result.get("first_visible_seconds"))
        total = numeric_value(result.get("total_seconds"))
        after_first_cps = numeric_value(result.get("chars_per_second_after_first_visible"))
        visible_chars = numeric_value(result.get("visible_chars")) or 0.0
        if first is None:
            ok = False
        else:
            first_values.append(first)
            if first > max_first_allowed:
                ok = False
        if total is None:
            ok = False
        else:
            total_values.append(total)
            if total > max_total_allowed:
                ok = False
        if after_first_cps is not None:
            after_first_cps_values.append(after_first_cps)
        if visible_chars >= min_rate_visible_chars and (after_first_cps is None or after_first_cps < min_after_first_cps):
            ok = False
    if completed != len(results):
        ok = False
    return {
        "ok": ok and bool(results),
        "completed": completed,
        "total": len(results),
        "max_first_visible_seconds": max(first_values) if first_values else 0.0,
        "max_total_seconds": max(total_values) if total_values else 0.0,
        "min_after_first_chars_per_second": min(after_first_cps_values) if after_first_cps_values else 0.0,
    }


def latency_status_counts_as_success(status: Any) -> bool:
    return str(status or "").strip() in {"completed", "checked"}


def context_smoke_summary(data: dict[str, Any]) -> dict[str, Any]:
    result = data.get("result") if isinstance(data, dict) else None
    if not isinstance(result, dict):
        result = {}
    status = str(result.get("status") or "")
    used_history = bool(result.get("used_history"))
    total_seconds = numeric_value(result.get("total_seconds")) or 0.0
    return {
        "ok": status == "passed" and used_history,
        "status": status,
        "used_history": used_history,
        "total_seconds": total_seconds,
    }


def wake_threshold_summary(data: dict[str, Any]) -> dict[str, Any]:
    summary = data.get("summary") if isinstance(data, dict) else None
    if not isinstance(summary, dict):
        summary = {}
    status = str(summary.get("status") or "")
    passed = int(numeric_value(summary.get("passed")) or 0)
    total = int(numeric_value(summary.get("total")) or 0)
    closest_reject_score = numeric_value(summary.get("closest_reject_score")) or 0.0
    return {
        "ok": status == "passed" and total > 0 and passed == total,
        "status": status,
        "passed": passed,
        "total": total,
        "closest_reject_label": str(summary.get("closest_reject_label") or ""),
        "closest_reject_score": closest_reject_score,
    }


def numeric_value(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def print_current_bundle() -> None:
    output = PROJECT_ROOT / "output"
    candidates = sorted(current_bundle_candidates(output), key=current_bundle_sort_key)
    if not candidates:
        print("Current bundle: none")
        return
    latest = candidates[-1]
    metadata = current_bundle_metadata(latest)
    if metadata:
        version = metadata.get("version") or "unknown"
        build = metadata.get("build") or "unknown"
        bundle_id = metadata.get("bundle_id") or "unknown"
        mode = metadata.get("launch_mode") or "unknown launch mode"
        dock = metadata.get("dock_icon") or "unknown Dock visibility"
        print(f"Current bundle: {latest.relative_to(PROJECT_ROOT)} (version {version}, build {build}, id {bundle_id}, {mode}, {dock})")
    else:
        print(f"Current bundle: {latest.relative_to(PROJECT_ROOT)}")
    print(f"Open command: open {shlex.quote(str(latest))}")
    print("Short launcher: scripts/open_jarvis.sh")


def print_process_status(base_url: str) -> None:
    app_pids = process_pids("jarvis-menu-bar")
    helper_pids = process_pids("jarvis-status-helper")
    parts: list[str] = []
    if app_pids:
        parts.append(f"{len(app_pids)} jarvis-menu-bar")
    if helper_pids:
        parts.append(f"{len(helper_pids)} jarvis-status-helper")
    if parts:
        print(f"App processes: {', '.join(parts)} running")
    else:
        print("App processes: none")
    if len(app_pids) > 1 or len(helper_pids) > 1:
        print("Action: quit duplicate Jarvis app/helper processes, then reopen once with `scripts/open_jarvis.sh`")
    print_speech_emergency_status(base_url, app_pids=app_pids, helper_pids=helper_pids)


def report_surfaces(base_url: str) -> list[dict[str, str]]:
    base = base_url.rstrip("/")
    output_dir = PROJECT_ROOT / "runtime" / "overnight_status"
    return [
        {
            "label": "Master report",
            "file": str((output_dir / "report.html").resolve()),
            "url": f"{base}/overnight-report/",
        },
        {
            "label": "Workboard",
            "file": str((output_dir / "index.html").resolve()),
            "url": f"{base}/overnight-workboard/",
        },
    ]


def print_report_surfaces(base_url: str) -> None:
    for surface in report_surfaces(base_url):
        print(f"{surface['label']} file: {surface['file']}")
        print(f"{surface['label']} URL: {surface['url']}")


def process_pids(process_name: str) -> list[str]:
    try:
        completed = subprocess.run(
            ["pgrep", "-x", process_name],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def print_speech_emergency_status(base_url: str, *, app_pids: list[str], helper_pids: list[str]) -> None:
    try:
        speech = get_json(f"{base_url.rstrip('/')}/api/speech/mute", timeout=2)
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
        return
    muted = bool(speech.get("muted"))
    active = bool(speech.get("active_speech"))
    automatic_available = bool(speech.get("automatic_speech_available"))
    emergency_ready = bool(app_pids or helper_pids)
    if muted:
        print("Speech emergency: safe (speech muted)")
        return
    if emergency_ready:
        print("Speech emergency: ready (menu helper/app process present)")
        return
    if active or automatic_available:
        print("Speech emergency: missing menu helper while speech is unmuted")
        print("Action: run `scripts/open_jarvis.sh` before enabling spoken replies")


def current_bundle_candidates(output: Path) -> list[Path]:
    stable = output / "Jarvis.app"
    return [stable] if stable.exists() else []


def current_bundle_sort_key(path: Path) -> tuple[int, int, float]:
    canonical_rank = 1 if path.stem == "Jarvis" else 0
    return (canonical_rank, current_bundle_number(path), path.stat().st_mtime if path.exists() else 0)


def current_bundle_number(path: Path) -> int:
    stem = path.stem
    if stem == "Jarvis":
        return 10_000
    return 0


def current_bundle_metadata(path: Path) -> dict[str, str] | None:
    info_plist = path / "Contents" / "Info.plist"
    try:
        data = plistlib.loads(info_plist.read_bytes())
    except (OSError, plistlib.InvalidFileException):
        return None
    return {
        "version": str(data.get("CFBundleShortVersionString") or ""),
        "build": str(data.get("CFBundleVersion") or ""),
        "bundle_id": str(data.get("CFBundleIdentifier") or ""),
        "lsui_element": "true" if data.get("LSUIElement") is True else "false",
        "launch_mode": "menu-bar accessory app" if data.get("LSUIElement") is True else "regular Dock app",
        "dock_icon": "Dock hidden by default" if data.get("LSUIElement") is True else "Dock visible by default",
    }


def classify_worker_source(source: str) -> str:
    if "/Contents/Resources/JarvisWorker/" in source:
        return "bundled app resources"
    try:
        Path(source).resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return "external path"
    return "source checkout"


def display_path(raw_path: str) -> str:
    path = Path(raw_path)
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except (OSError, ValueError):
        return raw_path


def get_json(url: str, *, timeout: int) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def base_url_from_environment() -> str:
    raw = os.environ.get("JARVIS_URL") or os.environ.get("JARVIS_BASE_URL") or DEFAULT_BASE_URL
    return normalize_base_url(raw)


def normalize_base_url(raw: str) -> str:
    value = raw.rstrip("/")
    if value.endswith("/api/command"):
        value = value.removesuffix("/api/command")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in LOOPBACK_HOSTS:
        raise ValueError("morning status only talks to loopback Jarvis workers")
    return value


def verification_highlights(results: list[dict[str, Any]]) -> list[str]:
    passed_names = {result.get("name") for result in results if result.get("passed")}
    return [
        label
        for check_name, label in VERIFICATION_HIGHLIGHTS.items()
        if check_name in passed_names
    ]


def verification_window_probe(results: list[dict[str, Any]]) -> str:
    for result in results:
        if result.get("name") == "output_bundle_window_self_test":
            return str(result.get("summary") or "").strip()
    return ""


def verification_action(ok: bool, age_seconds: float, max_age_seconds: int = MAX_VERIFICATION_AGE_SECONDS) -> str | None:
    if not ok:
        return "rerun `python3 scripts/verify_safe.py` because the latest verification failed"
    if age_seconds > max_age_seconds:
        return "rerun `python3 scripts/verify_safe.py` because the latest verification is older than 12 hours"
    return None


def verification_timestamp(path: Path, data: dict[str, Any]) -> float:
    raw = data.get("completed_at") or data.get("generated_at")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return path.stat().st_mtime


def time_since(timestamp: float, now: float | None = None) -> float:
    return max(0.0, (now if now is not None else time_now()) - timestamp)


def time_now() -> float:
    import time

    return time.time()


def format_uptime(seconds: float) -> str:
    total_seconds = max(0, int(round(seconds)))
    minutes, remaining_seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {remaining_seconds}s"
    if minutes:
        return f"{minutes}m {remaining_seconds}s"
    return f"{remaining_seconds}s"


if __name__ == "__main__":
    raise SystemExit(main())
