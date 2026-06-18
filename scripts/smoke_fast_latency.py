#!/usr/bin/env python3
"""Smoke-test the running Jarvis fast-chat stream for first visible text."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.render_overnight_status import normalize_base_url
from scripts.report_refresh import refresh_report_surfaces_quietly

REPORT_DIR = PROJECT_ROOT / "runtime" / "model_benchmarks"
DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_PROMPTS = [
    "hello Jarvis",
    "tell me a short joke",
    "Write five short bullets about making Jarvis feel fast.",
]
SUCCESS_STATUSES = {"completed", "checked"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--prompt", action="append", dest="prompts")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--max-first-visible", type=float, default=3.0)
    parser.add_argument("--max-total", type=float, default=5.0)
    parser.add_argument("--min-after-first-cps", type=float, default=20.0)
    parser.add_argument("--min-rate-visible-chars", type=int, default=20)
    parser.add_argument("--no-report", action="store_true")
    parser.add_argument("--no-refresh-report", action="store_true")
    args = parser.parse_args()

    try:
        base_url = normalize_base_url(args.base_url)
    except ValueError as error:
        print(f"Refused unsafe base URL: {error}", file=sys.stderr)
        return 2
    prompts = args.prompts or DEFAULT_PROMPTS
    results = [
        smoke_prompt(prompt, base_url=base_url, timeout=args.timeout)
        for prompt in prompts
    ]
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "base_url": base_url,
        "max_first_visible_seconds": args.max_first_visible,
        "max_total_seconds": args.max_total,
        "min_after_first_chars_per_second": args.min_after_first_cps,
        "min_rate_visible_chars": args.min_rate_visible_chars,
        "speech_suppressed_per_request": True,
        "speech_was_muted": False,
        "speech_mute_restored_to": None,
        "results": results,
    }

    if not args.no_report:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        json_path = REPORT_DIR / f"localhost-fast-latency-{stamp}.json"
        md_path = REPORT_DIR / f"localhost-fast-latency-{stamp}.md"
        latest_json_path = REPORT_DIR / "latest.json"
        latest_md_path = REPORT_DIR / "latest.md"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        md_path.write_text(render_markdown(report), encoding="utf-8")
        latest_json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        latest_md_path.write_text(render_markdown(report), encoding="utf-8")
        print(f"Report: {md_path}")
        if not args.no_refresh_report:
            refresh = refresh_report_surfaces_quietly(base_url)
            if refresh.get("ok"):
                print(f"Refreshed Jarvis report surfaces: {base_url}/overnight-report/")
            else:
                print(f"Warning: Jarvis report refresh failed: {refresh.get('error')}", file=sys.stderr)

    failed = False
    for result in results:
        first = result.get("first_visible_seconds")
        total = result.get("total_seconds")
        cps = result.get("chars_per_second_after_first_visible")
        visible_chars = int(result.get("visible_chars") or 0)
        status = result.get("status")
        prompt = result.get("prompt")
        backend = result.get("backend") or ""
        model = result.get("model") or ""
        primary_status = result.get("primary_status") or ""
        fallback_trigger = result.get("fallback_trigger") or ""
        print(
            f"{status:>10} first_visible={first} total={total} after_first_cps={cps} "
            f"backend={backend!r} model={model!r} primary={primary_status!r} trigger={fallback_trigger!r} prompt={prompt!r}"
        )
        if not latency_status_counts_as_success(status):
            failed = True
            continue
        if first is None or float(first) > args.max_first_visible:
            failed = True
        if total is None or float(total) > args.max_total:
            failed = True
        if (
            visible_chars >= args.min_rate_visible_chars
            and (cps is None or float(cps) < args.min_after_first_cps)
        ):
            failed = True
    return 1 if failed else 0


def latency_status_counts_as_success(status: Any) -> bool:
    return str(status or "").strip() in SUCCESS_STATUSES


def smoke_prompt(prompt: str, *, base_url: str, timeout: float) -> dict[str, Any]:
    base_url = normalize_base_url(base_url)
    started = time.monotonic()
    first_visible_at: float | None = None
    first_answer_at: float | None = None
    deltas: list[str] = []
    status_texts: list[str] = []
    final: dict[str, Any] | None = None
    payload = json.dumps({"command": prompt, "suppress_speech": True}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/command/stream",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            event_name = "message"
            data_lines: list[str] = []
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    delta_count = len(deltas)
                    status_count = len(status_texts)
                    event_name, final = process_event(
                        event_name,
                        data_lines,
                        deltas,
                        status_texts,
                        final,
                        first_visible_at=first_visible_at,
                        started=started,
                    )
                    now = time.monotonic()
                    if first_answer_at is None and len(deltas) > delta_count:
                        first_answer_at = now
                    if first_visible_at is None and (len(deltas) > delta_count or len(status_texts) > status_count):
                        first_visible_at = now
                    data_lines = []
                    continue
                if line.startswith("event:"):
                    event_name = line[6:].strip() or "message"
                elif line.startswith("data:"):
                    data_lines.append(line[5:].strip())
            if data_lines:
                delta_count = len(deltas)
                status_count = len(status_texts)
                _, final = process_event(
                    event_name,
                    data_lines,
                    deltas,
                    status_texts,
                    final,
                    first_visible_at=first_visible_at,
                    started=started,
                )
                now = time.monotonic()
                if first_answer_at is None and len(deltas) > delta_count:
                    first_answer_at = now
                if first_visible_at is None and (len(deltas) > delta_count or len(status_texts) > status_count):
                    first_visible_at = now
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        return error_result(prompt, started, f"http_{error.code}", body)
    except Exception as error:
        return error_result(prompt, started, type(error).__name__, str(error))

    result_payload = (final or {}).get("result") if isinstance(final, dict) else {}
    if isinstance(result_payload, dict):
        model_first = result_payload.get("first_visible_token_seconds")
        model_total = result_payload.get("duration_seconds")
    else:
        model_first = None
        model_total = None
    total = time.monotonic() - started
    reply = "".join(deltas).strip()
    if not reply and isinstance(result_payload, dict):
        reply = str(result_payload.get("reply") or "").strip()
    if first_visible_at is not None:
        first_visible_seconds = round(first_visible_at - started, 3)
    elif model_first is not None:
        first_visible_seconds = model_first
    elif reply:
        first_visible_seconds = round(total, 3)
    else:
        first_visible_seconds = None
    visible_chars = len(reply)
    first_answer_seconds = round(first_answer_at - started, 3) if first_answer_at is not None else None
    rate_start_seconds = first_answer_seconds if first_answer_seconds is not None else first_visible_seconds
    if rate_start_seconds is not None:
        after_first_seconds = max(0.001, total - float(rate_start_seconds))
        chars_per_second = round(visible_chars / after_first_seconds, 1)
    else:
        after_first_seconds = None
        chars_per_second = None
    return {
        "prompt": prompt,
        "status": effective_result_status(final, result_payload),
        "stream_status": final.get("status") if isinstance(final, dict) else None,
        "result_status": result_payload.get("status") if isinstance(result_payload, dict) else None,
        "first_visible_seconds": first_visible_seconds,
        "total_seconds": round(total, 3),
        "after_first_visible_seconds": round(after_first_seconds, 3) if after_first_seconds is not None else None,
        "visible_chars": visible_chars,
        "chars_per_second_after_first_visible": chars_per_second,
        "first_answer_seconds": first_answer_seconds,
        "model_reported_first_visible_seconds": model_first,
        "model_reported_total_seconds": model_total,
        "tool": final.get("tool") if isinstance(final, dict) else None,
        "backend": result_payload.get("backend") if isinstance(result_payload, dict) else None,
        "model": result_payload.get("model") if isinstance(result_payload, dict) else None,
        "fallback_used": bool(result_payload.get("fallback_used")) if isinstance(result_payload, dict) else False,
        "primary_fallback_used": bool(result_payload.get("primary_fallback_used")) if isinstance(result_payload, dict) else False,
        "fallback_trigger": result_payload.get("fallback_trigger") if isinstance(result_payload, dict) else None,
        "primary_status": result_payload.get("primary_status") if isinstance(result_payload, dict) else None,
        "rate_limit_fallback_used": bool(result_payload.get("rate_limit_fallback_used")) if isinstance(result_payload, dict) else False,
        "retry_used": bool(result_payload.get("retry_used")) if isinstance(result_payload, dict) else False,
        "tool_catalog_compacted": bool(result_payload.get("tool_catalog_compacted")) if isinstance(result_payload, dict) else False,
        "status_preview": " ".join(status_texts)[:160],
        "reply_preview": reply[:240],
    }


def effective_result_status(final: dict[str, Any] | None, result_payload: Any) -> str:
    if not isinstance(final, dict):
        return "missing_final"
    if isinstance(result_payload, dict):
        result_status = str(result_payload.get("status") or "").strip()
        if result_status:
            return result_status
    stream_status = str(final.get("status") or "").strip()
    return stream_status or "completed"


def process_event(
    event_name: str,
    data_lines: list[str],
    deltas: list[str],
    status_texts: list[str],
    final: dict[str, Any] | None,
    *,
    first_visible_at: float | None,
    started: float,
) -> tuple[str, dict[str, Any] | None]:
    del first_visible_at, started
    if not data_lines:
        return "message", final
    payload = "\n".join(data_lines)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return "message", final
    if event_name == "delta":
        text = str(data.get("text") or "")
        if text:
            deltas.append(text)
    elif event_name == "status":
        text = str(data.get("text") or "")
        if text:
            status_texts.append(text)
    elif event_name == "final" and isinstance(data, dict):
        final = data
    return "message", final


def error_result(prompt: str, started: float, status: str, message: str) -> dict[str, Any]:
    return {
        "prompt": prompt,
        "status": status,
        "first_visible_seconds": None,
        "total_seconds": round(time.monotonic() - started, 3),
        "error": message[:500],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Jarvis Localhost Fast Latency Smoke",
        "",
        f"Generated: {report['generated_at']}",
        f"Base URL: `{report['base_url']}`",
        f"Max first visible: {report['max_first_visible_seconds']}s",
        f"Max total: {report['max_total_seconds']}s",
        f"Min after-first output rate: {report.get('min_after_first_chars_per_second', 20.0)} chars/s for replies with at least {report.get('min_rate_visible_chars', 20)} visible chars",
        "",
        "| Status | First Visible | Total | After-First Cps | Chars | Backend | Model | Primary | Trigger | Compact | Prompt | Reply Preview |",
        "|---|---:|---:|---:|---:|---|---|---|---|---|---|---|",
    ]
    for result in report["results"]:
        reply = str(result.get("reply_preview") or result.get("error") or "").replace("\n", " ")[:160]
        lines.append(
            f"| {result.get('status')} | {_format_seconds(result.get('first_visible_seconds'))} | "
            f"{_format_seconds(result.get('total_seconds'))} | {_format_rate(result.get('chars_per_second_after_first_visible'))} | "
            f"{result.get('visible_chars') or 0} | {result.get('backend') or ''} | "
            f"`{result.get('model') or ''}` | {result.get('primary_status') or ''} | "
            f"{result.get('fallback_trigger') or ''} | {str(bool(result.get('tool_catalog_compacted'))).lower()} | "
            f"{result.get('prompt')!r} | {reply} |"
        )
    return "\n".join(lines) + "\n"


def _format_seconds(value: Any) -> str:
    if value is None:
        return "-"
    return f"{value}s"


def _format_rate(value: Any) -> str:
    if value is None:
        return "-"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
