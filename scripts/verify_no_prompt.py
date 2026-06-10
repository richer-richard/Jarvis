#!/usr/bin/env python3
"""Run Jarvis live checks that must not trigger macOS permission prompts."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from scripts import verify_safe
except ImportError:  # pragma: no cover - direct script execution fallback.
    import verify_safe  # type: ignore[no-redef]

REPORT_DIR = PROJECT_ROOT / "runtime" / "verification_no_prompt"
DEFAULT_BASE_URL = "http://127.0.0.1:8765"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output-dir", default=str(REPORT_DIR))
    args = parser.parse_args()

    report = run_no_prompt_checks(args.base_url.rstrip("/"))
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    report_path = output_dir / f"verify-no-prompt-{stamp}.json"
    latest_path = output_dir / "latest.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    latest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Report: {report_path}")
    print(f"Passed: {report['passed']}/{report['total']}")
    return 0 if report["ok"] else 1


def run_no_prompt_checks(base_url: str = DEFAULT_BASE_URL) -> dict[str, object]:
    started = time.monotonic()
    checks: list[tuple[str, Callable[[], str]]] = [
        ("worker_health", lambda: check_worker_health(base_url)),
        ("overnight_report_routes", lambda: verify_safe.check_endpoint_overnight_report_routes(base_url)),
        ("wake_audition_corpus", lambda: verify_safe.check_endpoint_wake_audition_corpus(base_url)),
        ("wake_simulation", lambda: verify_safe.check_endpoint_wake_simulation(base_url)),
        ("speech_mute", lambda: verify_safe.check_endpoint_speech_mute(base_url)),
        ("model_context", lambda: verify_safe.check_endpoint_model_context(base_url)),
        ("voice_loop_echo", lambda: verify_safe.check_endpoint_voice_loop_echo(base_url)),
        ("voice_loop_repeated_wake", lambda: verify_safe.check_endpoint_voice_loop_repeated_wake(base_url)),
        ("wake_debug", lambda: verify_safe.check_endpoint_wake_debug(base_url)),
    ]
    results = [asdict(verify_safe.endpoint_check(name, check)) for name, check in checks]
    passed = sum(1 for item in results if item.get("passed"))
    total = len(results)
    return {
        "schema": "jarvis.no_prompt_verification.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "base_url": base_url,
        "ok": passed == total and total > 0,
        "passed": passed,
        "total": total,
        "duration_seconds": round(time.monotonic() - started, 3),
        "policy": {
            "opens_apps": False,
            "requests_microphone": False,
            "requests_speech_recognition": False,
            "uses_screen_capture": False,
            "uses_accessibility": False,
            "pushes_to_network_repo": False,
        },
        "results": results,
    }


def check_worker_health(base_url: str) -> str:
    health = verify_safe.get_json("/api/health", base_url=base_url)
    verify_safe.require(health.get("ok") is True, f"health ok was {health.get('ok')}")
    app = health.get("status", {}).get("app", {}) if isinstance(health.get("status"), dict) else {}
    version = app.get("version") or "unknown"
    build = app.get("build") or "unknown"
    worker_kind = app.get("worker_source_kind") or "unknown worker"
    return f"worker healthy, Jarvis {version} build {build}, {worker_kind}"


if __name__ == "__main__":
    raise SystemExit(main())
