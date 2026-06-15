#!/usr/bin/env python3
"""Benchmark Codex CLI latency across Leo's proxy variants.

The script is dry-run by default. Use --execute only after the external Codex
call has been explicitly approved.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "runtime" / "codex_cli_proxy_benchmarks"
DEFAULT_MODEL = os.environ.get("JARVIS_CODEX_MODEL", "gpt-5.4-mini")
DEFAULT_REASONING = os.environ.get("JARVIS_CODEX_REASONING_EFFORT", "low")
DEFAULT_PROMPT = "Reply exactly with: Codex proxy benchmark OK"
DEFAULT_BASE_URL = "http://127.0.0.1:8765"
PROXY_ENV_KEYS = (
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
)


@dataclass(frozen=True)
class ProxyVariant:
    id: str
    label: str
    env: dict[str, str | None]


VARIANTS = (
    ProxyVariant(
        id="control_no_proxy",
        label="Control, no explicit proxy",
        env={key: None for key in PROXY_ENV_KEYS},
    ),
    ProxyVariant(
        id="clash_local_127",
        label="ClashX local proxy on 127.0.0.1:7890",
        env={
            "http_proxy": "http://127.0.0.1:7890",
            "https_proxy": "http://127.0.0.1:7890",
            "all_proxy": "socks5://127.0.0.1:7890",
            "HTTP_PROXY": "http://127.0.0.1:7890",
            "HTTPS_PROXY": "http://127.0.0.1:7890",
            "ALL_PROXY": "socks5://127.0.0.1:7890",
        },
    ),
    ProxyVariant(
        id="tailscale_air_proxy",
        label="MacBook Air proxy on 10.3.73.198:7890",
        env={
            "http_proxy": "http://10.3.73.198:7890",
            "https_proxy": "http://10.3.73.198:7890",
            "all_proxy": "socks5://10.3.73.198:7890",
            "HTTP_PROXY": "http://10.3.73.198:7890",
            "HTTPS_PROXY": "http://10.3.73.198:7890",
            "ALL_PROXY": "socks5://10.3.73.198:7890",
        },
    ),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Actually run external Codex/Jarvis requests.")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--reasoning", default=DEFAULT_REASONING)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--include-jarvis", action="store_true", help="Also time Jarvis /api/command/stream.")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--no-report", action="store_true")
    args = parser.parse_args(argv)

    codex_path = shutil.which("codex")
    report: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "execute": bool(args.execute),
        "prompt": args.prompt,
        "model": args.model,
        "reasoning": args.reasoning,
        "timeout_seconds": args.timeout,
        "codex_path": codex_path,
        "variants": [variant_plan(variant) for variant in VARIANTS],
        "results": [],
        "jarvis_baseline": None,
        "notes": [
            "Dry-run mode does not contact Codex.",
            "Proxy variables are scoped to each child process and do not modify the parent shell.",
            "Control mode removes common proxy environment variables from that child process.",
        ],
    }

    if args.execute:
        if not codex_path:
            report["status"] = "codex_not_found"
        else:
            for run_index in range(max(1, args.repeat)):
                for variant in VARIANTS:
                    report["results"].append(
                        run_codex_variant(
                            variant,
                            codex_path=codex_path,
                            prompt=args.prompt,
                            model=args.model,
                            reasoning=args.reasoning,
                            timeout=args.timeout,
                            run_index=run_index + 1,
                        )
                    )
            report["status"] = "completed"
        if args.include_jarvis:
            report["jarvis_baseline"] = run_jarvis_baseline(
                args.prompt,
                base_url=args.base_url,
                timeout=min(args.timeout, 60.0),
            )
    else:
        report["status"] = "dry_run"

    if not args.no_report:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        json_path = REPORT_DIR / f"codex-cli-proxy-benchmark-{stamp}.json"
        md_path = REPORT_DIR / f"codex-cli-proxy-benchmark-{stamp}.md"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        md_path.write_text(render_markdown(report), encoding="utf-8")
        report["json_path"] = str(json_path)
        report["markdown_path"] = str(md_path)
        print(f"JSON: {json_path}")
        print(f"Report: {md_path}")

    print_summary(report)
    return 0 if report.get("status") in {"dry_run", "completed"} else 1


def variant_plan(variant: ProxyVariant) -> dict[str, Any]:
    return {
        "id": variant.id,
        "label": variant.label,
        "proxy_env": {
            key: ("<unset>" if value is None else value)
            for key, value in variant.env.items()
        },
    }


def child_env(variant: ProxyVariant) -> dict[str, str]:
    env = os.environ.copy()
    for key, value in variant.env.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


def codex_command(codex_path: str, *, model: str, reasoning: str, output_path: Path) -> list[str]:
    return [
        codex_path,
        "--model",
        model,
        "-c",
        f"model_reasoning_effort={reasoning}",
        "--sandbox",
        "read-only",
        "--ask-for-approval",
        "never",
        "exec",
        "--cd",
        str(PROJECT_ROOT),
        "--skip-git-repo-check",
        "--ephemeral",
        "--json",
        "--output-last-message",
        str(output_path),
        "-",
    ]


def run_codex_variant(
    variant: ProxyVariant,
    *,
    codex_path: str,
    prompt: str,
    model: str,
    reasoning: str,
    timeout: float,
    run_index: int,
) -> dict[str, Any]:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="jarvis-codex-proxy-bench-") as temp_dir:
        output_path = Path(temp_dir) / "last-message.txt"
        command = codex_command(codex_path, model=model, reasoning=reasoning, output_path=output_path)
        try:
            process = subprocess.Popen(
                command,
                cwd=str(PROJECT_ROOT),
                env=child_env(variant),
                text=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,
            )
        except OSError as error:
            return result_error(variant, run_index, started, "start_failed", str(error))

        events: "queue.Queue[tuple[str, float, str]]" = queue.Queue()
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        first_stdout: float | None = None
        first_stderr: float | None = None

        threads = [
            threading.Thread(target=read_stream, args=("stdout", process.stdout, events), daemon=True),
            threading.Thread(target=read_stream, args=("stderr", process.stderr, events), daemon=True),
        ]
        for thread in threads:
            thread.start()

        if process.stdin:
            process.stdin.write(prompt)
            process.stdin.close()

        timed_out = False
        deadline = time.monotonic() + timeout
        while True:
            try:
                stream_name, event_time, line = events.get(timeout=0.05)
                if stream_name == "stdout":
                    stdout_lines.append(line)
                    first_stdout = first_stdout or event_time
                else:
                    stderr_lines.append(line)
                    first_stderr = first_stderr or event_time
            except queue.Empty:
                pass
            if process.poll() is not None:
                break
            if time.monotonic() >= deadline:
                timed_out = True
                process.kill()
                break

        returncode = process.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=1)
        while not events.empty():
            stream_name, event_time, line = events.get_nowait()
            if stream_name == "stdout":
                stdout_lines.append(line)
                first_stdout = first_stdout or event_time
            else:
                stderr_lines.append(line)
                first_stderr = first_stderr or event_time

        total = time.monotonic() - started
        first_output = min([value for value in (first_stdout, first_stderr) if value is not None], default=None)
        last_message = ""
        if output_path.exists():
            last_message = output_path.read_text(encoding="utf-8", errors="replace").strip()
        status = "timeout" if timed_out else ("completed" if returncode == 0 else "failed")
        return {
            "variant": variant.id,
            "label": variant.label,
            "run_index": run_index,
            "status": status,
            "returncode": returncode,
            "total_seconds": round(total, 3),
            "first_stdout_seconds": seconds_since(started, first_stdout),
            "first_stderr_seconds": seconds_since(started, first_stderr),
            "first_output_seconds": seconds_since(started, first_output),
            "stdout_line_count": len(stdout_lines),
            "stderr_line_count": len(stderr_lines),
            "stdout_tail": tail_text(stdout_lines, 2000),
            "stderr_tail": tail_text(stderr_lines, 2000),
            "last_message_preview": last_message[:500],
            "prompt_chars": len(prompt),
            "timed_out": timed_out,
        }


def read_stream(stream_name: str, stream: Any, events: "queue.Queue[tuple[str, float, str]]") -> None:
    if stream is None:
        return
    for line in stream:
        events.put((stream_name, time.monotonic(), line.rstrip("\n")))


def seconds_since(started: float, value: float | None) -> float | None:
    if value is None:
        return None
    return round(max(0.0, value - started), 3)


def tail_text(lines: list[str], max_chars: int) -> str:
    text = "\n".join(lines[-80:])
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def result_error(
    variant: ProxyVariant,
    run_index: int,
    started: float,
    status: str,
    error: str,
) -> dict[str, Any]:
    return {
        "variant": variant.id,
        "label": variant.label,
        "run_index": run_index,
        "status": status,
        "error": error,
        "total_seconds": round(time.monotonic() - started, 3),
    }


def run_jarvis_baseline(prompt: str, *, base_url: str, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    first_event_at: float | None = None
    final_event: dict[str, Any] | None = None
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
                    if data_lines:
                        first_event_at = first_event_at or time.monotonic()
                        parsed = parse_sse_data(data_lines)
                        if event_name == "final" and isinstance(parsed, dict):
                            final_event = parsed
                    event_name = "message"
                    data_lines = []
                    continue
                if line.startswith("event:"):
                    event_name = line[6:].strip() or "message"
                elif line.startswith("data:"):
                    data_lines.append(line[5:].strip())
    except urllib.error.HTTPError as error:
        return {"status": f"http_{error.code}", "error": error.read().decode("utf-8", errors="replace")}
    except Exception as error:
        return {"status": type(error).__name__, "error": str(error), "total_seconds": round(time.monotonic() - started, 3)}
    total = time.monotonic() - started
    result = final_event.get("result") if isinstance(final_event, dict) else {}
    return {
        "status": str(result.get("status") or final_event.get("status") or "completed") if isinstance(result, dict) or isinstance(final_event, dict) else "missing_final",
        "first_event_seconds": seconds_since(started, first_event_at),
        "total_seconds": round(total, 3),
        "tool": final_event.get("tool") if isinstance(final_event, dict) else None,
        "backend": result.get("backend") if isinstance(result, dict) else None,
        "model": result.get("model") if isinstance(result, dict) else None,
        "reply_preview": str(result.get("reply") if isinstance(result, dict) else "")[:300],
    }


def parse_sse_data(data_lines: list[str]) -> Any:
    text = "\n".join(data_lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Codex CLI Proxy Benchmark",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Mode: `{'execute' if report['execute'] else 'dry-run'}`",
        f"- Model: `{report['model']}`",
        f"- Reasoning: `{report['reasoning']}`",
        f"- Codex path: `{report.get('codex_path') or 'not found'}`",
        "",
        "## Variants",
        "",
    ]
    for variant in report["variants"]:
        lines.append(f"- `{variant['id']}`: {variant['label']}")
    lines.extend(["", "## Results", ""])
    if not report["results"]:
        lines.append("No external Codex calls were run. Re-run with `--execute` after approval.")
    else:
        lines.append("| Variant | Status | First output | Total | Return |")
        lines.append("| --- | --- | ---: | ---: | ---: |")
        for result in report["results"]:
            lines.append(
                f"| `{result['variant']}` | {result['status']} | "
                f"{format_seconds(result.get('first_output_seconds'))} | "
                f"{format_seconds(result.get('total_seconds'))} | {result.get('returncode')} |"
            )
    if report.get("jarvis_baseline"):
        baseline = report["jarvis_baseline"]
        lines.extend([
            "",
            "## Jarvis Baseline",
            "",
            f"- Status: `{baseline.get('status')}`",
            f"- First event: `{format_seconds(baseline.get('first_event_seconds'))}`",
            f"- Total: `{format_seconds(baseline.get('total_seconds'))}`",
            f"- Tool: `{baseline.get('tool')}`",
        ])
    lines.append("")
    return "\n".join(lines)


def format_seconds(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.3f}s"
    except (TypeError, ValueError):
        return "-"


def print_summary(report: dict[str, Any]) -> None:
    print(f"Status: {report.get('status')}")
    if not report.get("execute"):
        print("Dry run only. Re-run with --execute after approval to contact Codex.")
    for result in report.get("results", []):
        print(
            f"{result['variant']}: {result['status']} "
            f"first={format_seconds(result.get('first_output_seconds'))} "
            f"total={format_seconds(result.get('total_seconds'))}"
        )
    if report.get("jarvis_baseline"):
        baseline = report["jarvis_baseline"]
        print(
            "jarvis_baseline: "
            f"{baseline.get('status')} first={format_seconds(baseline.get('first_event_seconds'))} "
            f"total={format_seconds(baseline.get('total_seconds'))}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
