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
REPORT_DIR = PROJECT_ROOT / "runtime" / "model_benchmarks"
DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_PROMPTS = [
    "hello Jarvis",
    "tell me a short joke",
    "Write five short bullets about making Jarvis feel fast.",
]


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
    args = parser.parse_args()

    prompts = args.prompts or DEFAULT_PROMPTS
    results = [
        smoke_prompt(prompt, base_url=args.base_url, timeout=args.timeout)
        for prompt in prompts
    ]
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "base_url": args.base_url,
        "max_first_visible_seconds": args.max_first_visible,
        "max_total_seconds": args.max_total,
        "min_after_first_chars_per_second": args.min_after_first_cps,
        "min_rate_visible_chars": args.min_rate_visible_chars,
        "results": results,
    }

    if not args.no_report:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        json_path = REPORT_DIR / f"localhost-fast-latency-{stamp}.json"
        md_path = REPORT_DIR / f"localhost-fast-latency-{stamp}.md"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        md_path.write_text(render_markdown(report), encoding="utf-8")
        print(f"Report: {md_path}")

    failed = False
    for result in results:
        first = result.get("first_visible_seconds")
        total = result.get("total_seconds")
        cps = result.get("chars_per_second_after_first_visible")
        visible_chars = int(result.get("visible_chars") or 0)
        status = result.get("status")
        prompt = result.get("prompt")
        print(f"{status:>10} first_visible={first} total={total} after_first_cps={cps} prompt={prompt!r}")
        if status != "completed":
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


def smoke_prompt(prompt: str, *, base_url: str, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    first_visible_at: float | None = None
    deltas: list[str] = []
    final: dict[str, Any] | None = None
    payload = json.dumps({"command": prompt}).encode("utf-8")
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
                    event_name, final = process_event(
                        event_name,
                        data_lines,
                        deltas,
                        final,
                        first_visible_at=first_visible_at,
                        started=started,
                    )
                    if first_visible_at is None and deltas:
                        first_visible_at = time.monotonic()
                    data_lines = []
                    continue
                if line.startswith("event:"):
                    event_name = line[6:].strip() or "message"
                elif line.startswith("data:"):
                    data_lines.append(line[5:].strip())
            if data_lines:
                _, final = process_event(
                    event_name,
                    data_lines,
                    deltas,
                    final,
                    first_visible_at=first_visible_at,
                    started=started,
                )
                if first_visible_at is None and deltas:
                    first_visible_at = time.monotonic()
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
    first_visible_seconds = round(first_visible_at - started, 3) if first_visible_at else model_first
    visible_chars = len(reply)
    if first_visible_seconds is not None:
        after_first_seconds = max(0.001, total - float(first_visible_seconds))
        chars_per_second = round(visible_chars / after_first_seconds, 1)
    else:
        after_first_seconds = None
        chars_per_second = None
    return {
        "prompt": prompt,
        "status": "completed" if final else "missing_final",
        "first_visible_seconds": first_visible_seconds,
        "total_seconds": round(total, 3),
        "after_first_visible_seconds": round(after_first_seconds, 3) if after_first_seconds is not None else None,
        "visible_chars": visible_chars,
        "chars_per_second_after_first_visible": chars_per_second,
        "model_reported_first_visible_seconds": model_first,
        "model_reported_total_seconds": model_total,
        "tool": final.get("tool") if isinstance(final, dict) else None,
        "backend": result_payload.get("backend") if isinstance(result_payload, dict) else None,
        "model": result_payload.get("model") if isinstance(result_payload, dict) else None,
        "reply_preview": reply[:240],
    }


def process_event(
    event_name: str,
    data_lines: list[str],
    deltas: list[str],
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
        "| Status | First Visible | Total | After-First Cps | Chars | Backend | Model | Prompt | Reply Preview |",
        "|---|---:|---:|---:|---:|---|---|---|---|",
    ]
    for result in report["results"]:
        reply = str(result.get("reply_preview") or result.get("error") or "").replace("\n", " ")[:160]
        lines.append(
            f"| {result.get('status')} | {result.get('first_visible_seconds')}s | "
            f"{result.get('total_seconds')}s | {result.get('chars_per_second_after_first_visible')} | "
            f"{result.get('visible_chars') or 0} | {result.get('backend') or ''} | "
            f"`{result.get('model') or ''}` | {result.get('prompt')!r} | {reply} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
