#!/usr/bin/env python3
"""Measure Groq streaming time-to-first-visible-content for Jarvis candidate models.

Dry-run is the default. Use --execute-network only after the external Groq
benchmark has been explicitly approved.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.config import FAST_MODEL_MAX_TOKENS, GROQ_API_KEY, GROQ_BASE_URL  # noqa: E402
from jarvis.tools import _fast_chat_system_prompt, _https_context  # noqa: E402


REPORT_DIR = PROJECT_ROOT / "runtime" / "model_benchmarks"
DEFAULT_MODELS = [
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "meta-llama/llama-4-scout-17b-16e-instruct",
]
PROMPT = "hello Jarvis"
SYSTEM_PROMPT = _fast_chat_system_prompt()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--execute-network", action="store_true", help="Actually contact Groq for streaming timings.")
    args = parser.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    results = [
        stream_model(model, timeout=args.timeout) if args.execute_network else dry_run_model(model)
        for model in args.models
    ]
    generated = time.strftime("%Y%m%d-%H%M%S")
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "execute_network": bool(args.execute_network),
        "prompt": PROMPT,
        "results": results,
    }
    json_path = REPORT_DIR / f"streaming-benchmark-{generated}.json"
    md_path = REPORT_DIR / f"streaming-benchmark-{generated}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    for result in sorted(results, key=lambda item: item.get("first_visible_token_seconds") or item.get("first_token_seconds") or 999):
        print(
            result["model"],
            result["status"],
            "first_visible=",
            result.get("first_visible_token_seconds") or result.get("first_token_seconds"),
            "total=",
            result.get("total_seconds"),
        )
    print(f"Report: {md_path}")
    return 0


def dry_run_model(model: str) -> dict[str, object]:
    return {
        "model": model,
        "status": "dry_run",
        "first_visible_token_seconds": None,
        "first_token_seconds": None,
        "total_seconds": None,
        "chars": 0,
        "reply": "",
        "note": "No network request was sent. Re-run with --execute-network after approval.",
    }


def stream_model(model: str, *, timeout: int) -> dict[str, object]:
    started = time.monotonic()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": PROMPT},
        ],
        "temperature": 0.0,
        "max_completion_tokens": FAST_MODEL_MAX_TOKENS,
        "stream": True,
    }
    request = urllib.request.Request(
        f"{GROQ_BASE_URL.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "User-Agent": "Jarvis/0.1 local-mac-assistant",
        },
        method="POST",
    )
    first_visible_token_at: float | None = None
    chunks = []
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_https_context()) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = payload.get("choices", [{}])[0].get("delta", {})
                content = str(delta.get("content") or "")
                if content:
                    if first_visible_token_at is None:
                        first_visible_token_at = time.monotonic()
                    chunks.append(content)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        return {
            "model": model,
            "status": "http_error",
            "total_seconds": round(time.monotonic() - started, 3),
            "error": f"{error.code}: {body[:400]}",
        }
    except Exception as error:
        return {
            "model": model,
            "status": type(error).__name__,
            "total_seconds": round(time.monotonic() - started, 3),
            "error": str(error)[:400],
        }
    total = time.monotonic() - started
    reply = "".join(chunks).strip()
    return {
        "model": model,
        "status": "completed" if reply else "empty",
        "first_visible_token_seconds": round((first_visible_token_at - started), 3) if first_visible_token_at else None,
        "first_token_seconds": round((first_visible_token_at - started), 3) if first_visible_token_at else None,
        "total_seconds": round(total, 3),
        "chars": len(reply),
        "reply": reply[:500],
    }


def render_markdown(report: dict[str, object]) -> str:
    lines = [
        "# Jarvis Streaming Model Benchmark",
        "",
        f"Generated: {report['generated_at']}",
        f"Executed network calls: `{report.get('execute_network')}`",
        f"Prompt: `{report['prompt']}`",
        "",
        "| Model | Status | First Visible | Total | Chars | Reply |",
        "|---|---|---:|---:|---:|---|",
    ]
    for result in sorted(report["results"], key=lambda item: item.get("first_visible_token_seconds") or item.get("first_token_seconds") or 999):
        first = result.get("first_visible_token_seconds") or result.get("first_token_seconds")
        total = result.get("total_seconds")
        reply = str(result.get("reply") or result.get("error") or "").replace("\n", " ")[:160]
        lines.append(
            f"| `{result['model']}` | {result['status']} | "
            f"{first if first is not None else 'n/a'}s | {total}s | {result.get('chars', 0)} | {reply} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
