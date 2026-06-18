#!/usr/bin/env python3
"""Smoke-test Jarvis wake phrase threshold behavior without recording audio."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.wake import DEFAULT_WAKE_THRESHOLD, score_wake_transcript
from scripts.render_overnight_status import normalize_base_url
from scripts.report_refresh import refresh_report_surfaces_quietly

REPORT_DIR = PROJECT_ROOT / "runtime" / "wake_threshold"
DEFAULT_BASE_URL = "http://127.0.0.1:8765"

WAKE_CASES = [
    {"label": "exact hey jarvis", "transcript": "hey jarvis status", "detected": True, "command": "status"},
    {"label": "fuzzy hey jervis", "transcript": "hey jervis status", "detected": True, "command": "status"},
    {"label": "fuzzy okay jervis", "transcript": "okay jervis status", "detected": True, "command": "status"},
    {"label": "exact ok jarvis", "transcript": "ok jarvis status", "detected": True, "command": "status"},
    {"label": "wake only", "transcript": "okay jarvis", "detected": True, "command": ""},
    {"label": "short near miss", "transcript": "hey jars status", "detected": False, "command": ""},
    {"label": "below-threshold charvis", "transcript": "hey charvis status", "detected": False, "command": ""},
    {"label": "wrong phrase", "transcript": "okay service status", "detected": False, "command": ""},
    {"label": "missing wake prefix", "transcript": "jarvis status", "detected": False, "command": ""},
    {"label": "ordinary command", "transcript": "please check status", "detected": False, "command": ""},
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--threshold", type=float, default=DEFAULT_WAKE_THRESHOLD)
    parser.add_argument("--no-report", action="store_true")
    parser.add_argument("--no-refresh-report", action="store_true")
    args = parser.parse_args()
    try:
        base_url = normalize_base_url(args.base_url)
    except ValueError as error:
        print(f"Refused unsafe base URL: {error}", file=sys.stderr)
        return 2

    report = run_wake_threshold_smoke(threshold=args.threshold)
    if not args.no_report:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        json_path = REPORT_DIR / f"wake-threshold-{stamp}.json"
        md_path = REPORT_DIR / f"wake-threshold-{stamp}.md"
        latest_json_path = REPORT_DIR / "latest.json"
        latest_md_path = REPORT_DIR / "latest.md"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        md_path.write_text(render_markdown(report), encoding="utf-8")
        latest_json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        latest_md_path.write_text(render_markdown(report), encoding="utf-8")
        print(f"Report: {md_path}")
        if not args.no_refresh_report:
            refresh_report_surfaces_quietly(base_url)
    summary = report["summary"]
    print(
        f"status={summary['status']} cases={summary['passed']}/{summary['total']} "
        f"threshold={summary['threshold']:.3f} closest_reject={summary['closest_reject_label']} "
        f"{summary['closest_reject_score']:.6f}"
    )
    return 0 if summary["status"] == "passed" else 1


def run_wake_threshold_smoke(*, threshold: float = DEFAULT_WAKE_THRESHOLD) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for case in WAKE_CASES:
        score = score_wake_transcript(str(case["transcript"]), threshold=threshold)
        expected_detected = bool(case["detected"])
        expected_command = str(case["command"])
        command_ok = (not expected_detected) or score.command == expected_command
        passed = score.detected == expected_detected and command_ok
        cases.append(
            {
                "label": case["label"],
                "transcript": case["transcript"],
                "expected_detected": expected_detected,
                "expected_command": expected_command,
                "detected": score.detected,
                "score": score.score,
                "threshold": score.threshold,
                "phrase": score.phrase,
                "command": score.command,
                "window": score.window,
                "mode": score.mode,
                "passed": passed,
            }
        )
    passed_count = sum(1 for case in cases if case["passed"])
    rejected = [case for case in cases if not case["expected_detected"]]
    closest_reject = max(rejected, key=lambda case: float(case["score"]), default={})
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "summary": {
            "status": "passed" if passed_count == len(cases) else "failed",
            "passed": passed_count,
            "total": len(cases),
            "threshold": threshold,
            "accepted_count": sum(1 for case in cases if case["detected"]),
            "rejected_count": sum(1 for case in cases if not case["detected"]),
            "closest_reject_label": str(closest_reject.get("label") or ""),
            "closest_reject_score": float(closest_reject.get("score") or 0.0),
        },
        "cases": cases,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Jarvis Wake Threshold Smoke",
        "",
        f"Generated: {report['generated_at']}",
        f"Status: **{summary['status']}**",
        f"Passed: {summary['passed']} / {summary['total']}",
        f"Threshold: {summary['threshold']:.3f}",
        f"Closest rejected phrase: {summary['closest_reject_label']} ({summary['closest_reject_score']:.6f})",
        "",
        "| Case | Transcript | Expected | Score | Detected | Command |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for case in report["cases"]:
        expected = "detect" if case["expected_detected"] else "reject"
        detected = "yes" if case["detected"] else "no"
        lines.append(
            f"| {case['label']} | `{case['transcript']}` | {expected} | "
            f"{float(case['score']):.6f} | {detected} | `{case['command']}` |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
