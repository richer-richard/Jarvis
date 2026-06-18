#!/usr/bin/env python3
"""Close only Chrome tabs created by Jarvis/Codex local testing."""

from __future__ import annotations

import argparse
import json
import subprocess
from typing import Any


LOCALOS_MUSIC_HTTP_URL = "http://127.0.0.1:8787/localFiles/HTMLfiles/!musicPlayer.html"
LOCALOS_MUSIC_FILE_MARKER = "/developer/localOSroot/localOS/localFiles/HTMLfiles/!musicPlayer.html"


def is_cleanup_target(url: str) -> bool:
    value = str(url or "")
    return value == LOCALOS_MUSIC_HTTP_URL or (
        value.startswith("file:///Users/leoxu/") and LOCALOS_MUSIC_FILE_MARKER in value
    )


def _cleanup_applescript(*, close_targets: bool) -> str:
    close_line = "close t" if close_targets else "-- dry run"
    return f'''
set output to ""
tell application "Google Chrome"
  repeat with w in windows
    repeat with t in tabs of w
      set tabTitle to title of t
      set tabUrl to URL of t
      set shouldClose to false
      if tabUrl is "{LOCALOS_MUSIC_HTTP_URL}" then set shouldClose to true
      if tabUrl starts with "file:///Users/leoxu/" and tabUrl contains "{LOCALOS_MUSIC_FILE_MARKER}" then set shouldClose to true
      if shouldClose then
        set output to output & tabTitle & tab & tabUrl & linefeed
        {close_line}
      end if
    end repeat
  end repeat
end tell
return output
'''


def cleanup_chrome_test_tabs(*, execute: bool) -> dict[str, Any]:
    script = _cleanup_applescript(close_targets=execute)
    completed = subprocess.run(
        ["osascript", "-e", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.returncode != 0:
        return {
            "ok": False,
            "executed": execute,
            "closed_count": 0,
            "targets": [],
            "error": completed.stderr.strip() or completed.stdout.strip(),
        }
    targets = []
    for line in completed.stdout.splitlines():
        if not line.strip() or "\t" not in line:
            continue
        title, url = line.split("\t", 1)
        targets.append({"title": title, "url": url})
    return {
        "ok": True,
        "executed": execute,
        "closed_count": len(targets) if execute else 0,
        "target_count": len(targets),
        "targets": targets,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Actually close matching Chrome tabs.")
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
