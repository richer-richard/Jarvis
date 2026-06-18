#!/usr/bin/env python3
"""Refresh Jarvis report surfaces after proof artifacts change."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def refresh_report_surfaces(base_url: str) -> dict[str, Any]:
    """Render the loopback master report/workboard from the latest artifacts."""
    from scripts import render_overnight_status

    normalized_base_url = render_overnight_status.normalize_base_url(base_url)
    latest = ensure_latest_artifacts()
    context = render_overnight_status.build_context(normalized_base_url)
    render_overnight_status.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = render_overnight_status.OUTPUT_DIR / "report.html"
    workboard_path = render_overnight_status.OUTPUT_DIR / "index.html"
    report_path.write_text(render_overnight_status.render_report(context), encoding="utf-8")
    workboard_path.write_text(render_overnight_status.render_workboard(context), encoding="utf-8")
    return {
        "ok": True,
        "base_url": normalized_base_url,
        "report_path": str(report_path),
        "workboard_path": str(workboard_path),
        "latest_artifacts": latest,
    }


def refresh_report_surfaces_quietly(base_url: str) -> dict[str, Any]:
    """Refresh report surfaces without letting report rendering fail proof scripts."""
    try:
        return refresh_report_surfaces(base_url)
    except Exception as error:  # pragma: no cover - defensive wrapper around live IO.
        return {
            "ok": False,
            "base_url": str(base_url or "http://127.0.0.1:8765").rstrip("/"),
            "error": f"{type(error).__name__}: {error}",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--json", action="store_true", help="Print the full refresh result as JSON.")
    args = parser.parse_args()
    try:
        result = refresh_report_surfaces(args.base_url)
    except ValueError as error:
        print(f"Refused unsafe base URL: {error}", file=sys.stderr)
        return 2
    except Exception as error:  # pragma: no cover - defensive wrapper around live IO.
        print(f"Report refresh failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(
            "Refreshed Jarvis report surfaces: "
            f"{result['report_path']} and {result['workboard_path']}"
        )
    return 0


def ensure_latest_artifacts() -> dict[str, Any]:
    """Backfill stable latest proof artifacts from the newest timestamped reports."""
    from jarvis import tools as jarvis_tools
    from scripts import (
        codex_cli_proxy_benchmark,
        run_regression_prompt_matrix,
        full_loop_regression,
        smoke_conversation_context,
        smoke_fast_latency,
        smoke_wake_threshold,
        voice_loop_qa,
    )

    results = {
        "fast_latency": _write_latest_from_newest(
            smoke_fast_latency.REPORT_DIR.glob("localhost-fast-latency-*.json"),
            smoke_fast_latency.REPORT_DIR / "latest.json",
            smoke_fast_latency.REPORT_DIR / "latest.md",
            smoke_fast_latency.render_markdown,
        ),
        "conversation_context": _write_latest_from_newest(
            smoke_conversation_context.REPORT_DIR.glob("conversation-context-*.json"),
            smoke_conversation_context.REPORT_DIR / "latest.json",
            smoke_conversation_context.REPORT_DIR / "latest.md",
            smoke_conversation_context.render_markdown,
        ),
        "wake_threshold": _write_latest_from_newest(
            smoke_wake_threshold.REPORT_DIR.glob("wake-threshold-*.json"),
            smoke_wake_threshold.REPORT_DIR / "latest.json",
            smoke_wake_threshold.REPORT_DIR / "latest.md",
            smoke_wake_threshold.render_markdown,
        ),
        "regression_prompt_matrix": _write_latest_from_newest(
            run_regression_prompt_matrix.OUTPUT_ROOT.glob("*/summary.json"),
            run_regression_prompt_matrix.OUTPUT_ROOT / "latest.json",
            run_regression_prompt_matrix.OUTPUT_ROOT / "latest.md",
            run_regression_prompt_matrix.render_markdown,
            transform_payload=run_regression_prompt_matrix.enrich_summary_payload,
        ),
        "voice_loop_qa": _write_latest_from_newest(
            voice_loop_qa.REPORT_DIR.glob("*/report.json"),
            voice_loop_qa.REPORT_DIR / "latest.json",
            voice_loop_qa.REPORT_DIR / "latest.md",
            voice_loop_qa.render_markdown,
        ),
        "full_loop_regression": _write_latest_from_newest(
            full_loop_regression.REPORT_DIR.glob("*/summary.json"),
            full_loop_regression.REPORT_DIR / "latest.json",
            full_loop_regression.REPORT_DIR / "latest.md",
            full_loop_regression.render_markdown,
            payload_filter=full_loop_regression.is_canonical_summary,
        ),
        "codex_cli_proxy_benchmark": _write_latest_from_newest(
            codex_cli_proxy_benchmark.REPORT_DIR.glob("codex-cli-proxy-benchmark-*.json"),
            codex_cli_proxy_benchmark.REPORT_DIR / "latest.json",
            codex_cli_proxy_benchmark.REPORT_DIR / "latest.md",
            codex_cli_proxy_benchmark.render_markdown,
        ),
        "contact_alias_memory": _ensure_json_surface(
            jarvis_tools.CONTACT_DATA_PATH,
            {"schema": "jarvis.contact_aliases.v1", "aliases": {}},
        ),
    }
    return {
        "ok": all(bool(result.get("ok")) or result.get("status") == "no_source" for result in results.values()),
        "results": results,
    }


def _write_latest_from_newest(
    candidates: Any,
    latest_json_path: Path,
    latest_md_path: Path,
    render_markdown: Any,
    *,
    transform_payload: Any = None,
    payload_filter: Any = None,
) -> dict[str, Any]:
    paths = sorted(
        (Path(path) for path in candidates),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
    )
    if not paths:
        return {
            "ok": False,
            "status": "no_source",
            "latest_json": str(latest_json_path),
            "latest_md": str(latest_md_path),
        }
    skipped: list[dict[str, str]] = []
    for source in reversed(paths):
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
            if transform_payload is not None:
                payload = transform_payload(payload)
            if payload_filter is not None and not payload_filter(payload):
                skipped.append(
                    {
                        "source": str(source),
                        "error": "filtered",
                    }
                )
                continue
            markdown = render_markdown(payload)
            latest_json_path.parent.mkdir(parents=True, exist_ok=True)
            latest_md_path.parent.mkdir(parents=True, exist_ok=True)
            latest_json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            latest_md_path.write_text(markdown, encoding="utf-8")
        except Exception as error:
            skipped.append(
                {
                    "source": str(source),
                    "error": f"{type(error).__name__}: {error}",
                }
            )
            continue
        return {
            "ok": True,
            "status": "updated",
            "source": str(source),
            "latest_json": str(latest_json_path),
            "latest_md": str(latest_md_path),
            "skipped": skipped,
        }
    return {
        "ok": False,
        "status": "no_valid_source",
        "latest_json": str(latest_json_path),
        "latest_md": str(latest_md_path),
        "skipped": skipped,
        "error": skipped[0]["error"] if skipped else "No readable source artifacts.",
    }


def _ensure_json_surface(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    if path.exists():
        return {
            "ok": True,
            "status": "exists",
            "path": str(path),
        }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    except OSError as error:
        return {
            "ok": False,
            "status": "write_failed",
            "path": str(path),
            "error": f"{type(error).__name__}: {error}",
        }
    return {
        "ok": True,
        "status": "created",
        "path": str(path),
    }


if __name__ == "__main__":
    raise SystemExit(main())
