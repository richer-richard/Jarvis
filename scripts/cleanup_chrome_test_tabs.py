#!/usr/bin/env python3
"""Close only Chrome tabs created by Jarvis/Codex local testing."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from typing import Any


LOCALOS_MUSIC_HTTP_URL = "http://127.0.0.1:8787/localFiles/HTMLfiles/!musicPlayer.html"
LOCALOS_MUSIC_FILE_MARKER = "/developer/localOSroot/localOS/localFiles/HTMLfiles/!musicPlayer.html"
JARVIS_LOOPBACK_PREFIXES = (
    "http://127.0.0.1:8765/overnight-report",
    "http://127.0.0.1:8765/overnight-workboard",
    "http://127.0.0.1:8765/wake-audition",
)
JARVIS_FILE_MARKERS = (
    "/developer/Jarvis/runtime/overnight_status/report.html",
    "/developer/Jarvis/runtime/overnight_status/index.html",
)
CHROME_CLEANUP_TIMEOUT_SECONDS = 8
CHROME_CLEANUP_ATTEMPTS = 2
CHROME_CLEANUP_WARMUP_TIMEOUT_SECONDS = 8
CHROME_CLEANUP_WARMUP_ATTEMPTS = 2
CHROME_CLEANUP_WARMUP_RETRY_DELAY_SECONDS = 1.0


def _chrome_warmup() -> dict[str, Any]:
    script = 'tell application "Google Chrome" to count windows'
    attempts: list[dict[str, Any]] = []
    for attempt in range(1, CHROME_CLEANUP_WARMUP_ATTEMPTS + 1):
        if attempt > 1:
            time.sleep(CHROME_CLEANUP_WARMUP_RETRY_DELAY_SECONDS)
        try:
            completed = subprocess.run(
                ["osascript", "-e", script],
                check=False,
                capture_output=True,
                text=True,
                timeout=CHROME_CLEANUP_WARMUP_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            attempts.append({"attempt": attempt, "status": "timeout", "timeout_seconds": error.timeout})
            continue
        result = {
            "attempt": attempt,
            "status": "completed" if completed.returncode == 0 else "failed",
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
        attempts.append(result)
        return {**result, "attempts": attempts}
    return {
        "status": "timeout",
        "timeout_seconds": CHROME_CLEANUP_WARMUP_TIMEOUT_SECONDS,
        "attempts": attempts,
    }


def is_cleanup_target(url: str) -> bool:
    value = str(url or "")
    if value == LOCALOS_MUSIC_HTTP_URL:
        return True
    if any(value.startswith(prefix) for prefix in JARVIS_LOOPBACK_PREFIXES):
        return True
    if value.startswith("file:///Users/leoxu/"):
        return LOCALOS_MUSIC_FILE_MARKER in value or any(marker in value for marker in JARVIS_FILE_MARKERS)
    return False


def _cleanup_jxa(*, close_targets: bool) -> str:
    close_targets_js = "true" if close_targets else "false"
    return f'''
const chrome = Application("Google Chrome");
const closeTargets = {close_targets_js};
const localosMusicHttpUrl = {json.dumps(LOCALOS_MUSIC_HTTP_URL)};
const localosMusicFileMarker = {json.dumps(LOCALOS_MUSIC_FILE_MARKER)};
const jarvisLoopbackPrefixes = {json.dumps(list(JARVIS_LOOPBACK_PREFIXES))};
const jarvisFileMarkers = {json.dumps(list(JARVIS_FILE_MARKERS))};

function isCleanupTarget(url) {{
  const value = String(url || "");
  if (value === localosMusicHttpUrl) return true;
  if (jarvisLoopbackPrefixes.some((prefix) => value.startsWith(prefix))) return true;
  if (value.startsWith("file:///Users/leoxu/")) {{
    return value.includes(localosMusicFileMarker) || jarvisFileMarkers.some((marker) => value.includes(marker));
  }}
  return false;
}}

const targets = [];
for (const win of chrome.windows()) {{
  const tabs = win.tabs();
  for (let index = tabs.length - 1; index >= 0; index -= 1) {{
    const tab = tabs[index];
    const url = String(tab.url() || "");
    if (!isCleanupTarget(url)) continue;
    const title = String(tab.title() || "");
    targets.push({{ title, url }});
    if (closeTargets) tab.close();
  }}
}}
JSON.stringify(targets);
'''


def cleanup_chrome_test_tabs(*, execute: bool) -> dict[str, Any]:
    script = _cleanup_jxa(close_targets=execute)
    warmup = _chrome_warmup()
    if warmup.get("status") == "timeout":
        return {
            "ok": False,
            "executed": execute,
            "closed_count": 0,
            "target_count": 0,
            "targets": [],
            "attempts": [],
            "warmup": warmup,
            "error": (
                f"Chrome cleanup warm-up timed out after {CHROME_CLEANUP_WARMUP_ATTEMPTS} "
                f"attempts of {CHROME_CLEANUP_WARMUP_TIMEOUT_SECONDS:g}s while reading Chrome windows."
            ),
            "timeout_seconds": CHROME_CLEANUP_WARMUP_TIMEOUT_SECONDS,
        }
    attempts: list[dict[str, Any]] = []
    completed: subprocess.CompletedProcess[str] | None = None
    for attempt in range(1, CHROME_CLEANUP_ATTEMPTS + 1):
        try:
            completed = subprocess.run(
                ["osascript", "-l", "JavaScript", "-e", script],
                check=False,
                capture_output=True,
                text=True,
                timeout=CHROME_CLEANUP_TIMEOUT_SECONDS,
            )
            attempts.append({"attempt": attempt, "status": "completed", "returncode": completed.returncode})
            break
        except subprocess.TimeoutExpired as error:
            attempts.append({"attempt": attempt, "status": "timeout", "timeout_seconds": error.timeout})
            completed = None
    if completed is None:
        return {
            "ok": False,
            "executed": execute,
            "closed_count": 0,
            "target_count": 0,
            "targets": [],
            "attempts": attempts,
            "warmup": warmup,
            "error": (
                f"Chrome cleanup timed out after {CHROME_CLEANUP_ATTEMPTS} "
                f"attempts of {CHROME_CLEANUP_TIMEOUT_SECONDS:g}s while reading tab URLs."
            ),
            "timeout_seconds": CHROME_CLEANUP_TIMEOUT_SECONDS,
        }
    if completed.returncode != 0:
        return {
            "ok": False,
            "executed": execute,
            "closed_count": 0,
            "targets": [],
            "attempts": attempts,
            "warmup": warmup,
            "error": completed.stderr.strip() or completed.stdout.strip(),
        }
    try:
        loaded = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError as error:
        return {
            "ok": False,
            "executed": execute,
            "closed_count": 0,
            "target_count": 0,
            "targets": [],
            "attempts": attempts,
            "warmup": warmup,
            "error": f"Chrome cleanup returned invalid JSON: {error}",
        }
    targets = [
        {"title": str(item.get("title") or ""), "url": str(item.get("url") or "")}
        for item in loaded
        if isinstance(item, dict)
    ]
    return {
        "ok": True,
        "executed": execute,
        "closed_count": len(targets) if execute else 0,
        "target_count": len(targets),
        "targets": targets,
        "attempts": attempts,
        "warmup": warmup,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Actually close matching Chrome tabs.")
    parser.add_argument("--dry-run", action="store_false", dest="execute", help="Preview matching tabs without closing them. This is the default.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = cleanup_chrome_test_tabs(execute=args.execute)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    elif result["ok"]:
        action = "Closed" if args.execute else "Would close"
        print(f"{action} {result['target_count']} Jarvis/Codex Chrome test tab(s).")
    else:
        print(f"Chrome cleanup failed: {result['error']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
