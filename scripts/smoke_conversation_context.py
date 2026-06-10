#!/usr/bin/env python3
"""Smoke-test that Jarvis uses prior conversation history in live fast chat."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "runtime" / "conversation_context"
DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_HISTORY = [
    {"role": "user", "text": "Give me a one-step algebra problem."},
    {"role": "assistant", "text": "Solve x + 2 = 5."},
]
DEFAULT_COMMAND = "x = 3"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--no-report", action="store_true")
    args = parser.parse_args()

    report = run_context_smoke(base_url=args.base_url.rstrip("/"), timeout=args.timeout)
    if not args.no_report:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        json_path = REPORT_DIR / f"conversation-context-{stamp}.json"
        md_path = REPORT_DIR / f"conversation-context-{stamp}.md"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        md_path.write_text(render_markdown(report), encoding="utf-8")
        print(f"Report: {md_path}")
    result = report["result"]
    print(
        f"{result['status']:>10} used_history={result['used_history']} "
        f"total={result.get('total_seconds')} reply={result.get('reply_preview')!r}"
    )
    return 0 if result.get("status") == "passed" else 1


def run_context_smoke(*, base_url: str, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    final, deltas, error = stream_command(
        base_url,
        {"command": DEFAULT_COMMAND, "history": DEFAULT_HISTORY, "suppress_speech": True},
        timeout=timeout,
    )
    total = round(time.monotonic() - started, 3)
    result_payload = (final or {}).get("result") if isinstance(final, dict) else {}
    if not isinstance(result_payload, dict):
        result_payload = {}
    reply = "".join(deltas).strip() or str(result_payload.get("reply") or "").strip()
    used_history = context_reply_uses_history(reply)
    result_status = str(result_payload.get("status") or "").strip()
    model_busy = result_status in {"temporarily_busy", "rate_limited", "timeout"}
    if final and used_history and not error:
        status = "passed"
    elif model_busy:
        status = "model_busy"
    else:
        status = "failed"
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "base_url": base_url,
        "command": DEFAULT_COMMAND,
        "history": DEFAULT_HISTORY,
        "result": {
            "status": status,
            "used_history": used_history,
            "total_seconds": total,
            "tool": final.get("tool") if isinstance(final, dict) else None,
            "result_status": result_status or None,
            "model_busy": model_busy,
            "backend": result_payload.get("backend"),
            "model": result_payload.get("model"),
            "reply_preview": reply[:400],
            "error": error,
            "speech_suppressed_per_request": True,
            "speech_was_muted": False,
            "speech_mute_restored_to": None,
        },
    }


def context_reply_uses_history(reply: str) -> bool:
    lowered = str(reply or "").lower()
    if any(blocker in lowered for blocker in ("don't know", "do not know", "what problem", "which problem")):
        return False
    return "3" in lowered or any(marker in lowered for marker in ("correct", "right", "exactly"))


def speech_mute_status(base_url: str) -> bool:
    try:
        data = get_json(f"{base_url}/api/speech/mute")
        return bool(data.get("muted", False))
    except Exception:
        return False


def set_speech_mute(base_url: str, muted: bool) -> None:
    post_json(f"{base_url}/api/speech/mute", {"muted": muted}, timeout=5)


def stream_command(base_url: str, payload: dict[str, Any], *, timeout: float) -> tuple[dict[str, Any] | None, list[str], str | None]:
    request = urllib.request.Request(
        f"{base_url}/api/command/stream",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    final: dict[str, Any] | None = None
    deltas: list[str] = []
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            event_name = "message"
            data_lines: list[str] = []
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    final = process_event(event_name, data_lines, deltas, final)
                    event_name = "message"
                    data_lines = []
                    continue
                if line.startswith("event:"):
                    event_name = line[6:].strip() or "message"
                elif line.startswith("data:"):
                    data_lines.append(line[5:].strip())
            if data_lines:
                final = process_event(event_name, data_lines, deltas, final)
    except urllib.error.HTTPError as error:
        return None, deltas, error.read().decode("utf-8", errors="replace")[:500]
    except Exception as error:
        return None, deltas, f"{type(error).__name__}: {error}"
    return final, deltas, None


def process_event(event_name: str, data_lines: list[str], deltas: list[str], final: dict[str, Any] | None) -> dict[str, Any] | None:
    if not data_lines:
        return final
    try:
        data = json.loads("\n".join(data_lines))
    except json.JSONDecodeError:
        return final
    if event_name == "delta":
        text = str(data.get("text") or "")
        if text:
            deltas.append(text)
    elif event_name == "final" and isinstance(data, dict):
        return data
    return final


def get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=5) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data if isinstance(data, dict) else {}


def post_json(url: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data if isinstance(data, dict) else {}


def render_markdown(report: dict[str, Any]) -> str:
    result = report["result"]
    lines = [
        "# Jarvis Conversation Context Smoke",
        "",
        f"Generated: {report['generated_at']}",
        f"Base URL: `{report['base_url']}`",
        f"Command: `{report['command']}`",
        f"Status: **{result['status']}**",
        f"Used prior history: `{result['used_history']}`",
        f"Total: {result.get('total_seconds')}s",
        f"Tool: `{result.get('tool') or ''}`",
        f"Backend/model: `{result.get('backend') or ''}` / `{result.get('model') or ''}`",
        "",
        "History sent:",
        "",
    ]
    for item in report["history"]:
        lines.append(f"- {item['role']}: {item['text']}")
    lines.extend(["", "Reply preview:", "", str(result.get("reply_preview") or "")])
    if result.get("error"):
        lines.extend(["", "Error:", "", str(result["error"])])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
