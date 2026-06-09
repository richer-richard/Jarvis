#!/usr/bin/env python3
"""Render the local Jarvis overnight workboard and master report."""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "runtime" / "overnight_status"
BEIJING = ZoneInfo("Asia/Shanghai")


SHIPPED_ITEMS = [
    "Experimental native Hey Jarvis listener in the macOS app, using Speech and AVAudioEngine.",
    "Wake-audition lab at /wake-audition/ for recording samples, scoring transcripts, running noise trials, and copying JSON.",
    "Wake scoring now accepts close transcripts such as hey jervis while still rejecting unrelated speech.",
    "One-breath commands like Hey Jarvis check my email now trigger the immediate Yes sir wake acknowledgement before capture.",
    "Copy Chat JSON now includes recent wake events so Leo can paste back what Jarvis heard and captured.",
    "Normal Dock-app behavior is preserved, with a menu-bar item enabled for quick controls.",
    "Menu-bar Shut Up toggle mutes Jarvis, interrupts current speech, and switches to Keep Blabbering for unmute.",
    "Menu-bar Start Hey Jarvis / Stop Hey Jarvis controls make the wake listener reachable without opening the panel.",
    "Menu-bar Open Wake Test jumps straight to the local wake-audition page.",
    "The Jarvis panel now shows speech mute state and uses Wake Lab for the new audition route.",
    "The Jarvis panel now has a Perms quick action for microphone, speech, screen, accessibility, and notification readiness.",
    "The wake lab now summarizes runs into detected count, best noisy pass, and a suggested next step.",
    "Final answers with normal reply text now auto-speak by default instead of leaving only the working line audible.",
    "Streaming status updates can no longer overwrite an answer that has already started appearing on screen.",
]

PROOF_ITEMS = [
    "Python safety suite: 379/379 passed after the wake, mute, and final-speech work.",
    "Swift build passed for the Jarvis menu-bar app.",
    "Swift self-tests passed, including menu-bar routing labels and worker checks.",
    "Live safe verifier passed 91/91 after the speech-mute endpoint and wake-audition endpoint were added.",
    "Live Jarvis health showed the rebuilt app running from bundled app resources.",
]

TRY_ITEMS = [
    "Open Jarvis from the Dock; it should be a normal app window, not an always-front overlay.",
    "Use the menu-bar item to click Start Hey Jarvis, then say Hey Jarvis followed by a short command.",
    "Try a one-breath command such as Hey Jarvis wake status; Jarvis should acknowledge immediately and then answer.",
    "Use Shut Up if Jarvis is talking too much; use Keep Blabbering to restore speech.",
    "Ask for wake status or overnight status; Jarvis should speak the final answer, not only the Yes sir working line.",
    "Click Perms if Hey Jarvis does not listen; it should show which macOS permission is blocking the loop.",
    "Open the wake lab and record several Hey Jarvis samples in quiet and noisy conditions.",
    "Use the wake lab Copy JSON button if recognition feels wrong, then paste the JSON back to Codex.",
    "Use Copy Chat JSON after a failed wake attempt; it now includes wake detected and command captured events.",
]

RISK_ITEMS = [
    "Real microphone pickup, false wakes, and room-noise reliability still need Leo testing.",
    "Browser loopback noise trials are useful but not a perfect model of a real room.",
    "Speech Recognition permission can still block the native listener until macOS grants it to the current Jarvis bundle.",
    "The current wake phrase is experimental; it is not yet personalized to Leo's voice.",
    "Very technical diagnostics are still intentionally speech-silent so Jarvis does not read backend internals aloud.",
]

SUPPORTING_FILES = [
    ("runtime/overnight_status/index.html", "Live overnight workboard"),
    ("runtime/overnight_status/report.html", "This master report"),
    ("http://127.0.0.1:8765/wake-audition/", "Hey Jarvis wake audition lab"),
    ("runtime/wake_audition/samples/", "Locally saved wake samples"),
    ("runtime/verification/", "Safe verifier reports"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the Jarvis overnight report surfaces.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765", help="Jarvis worker base URL.")
    args = parser.parse_args()

    context = build_context(args.base_url.rstrip("/"))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "report.html").write_text(render_report(context), encoding="utf-8")
    (OUTPUT_DIR / "index.html").write_text(render_workboard(context), encoding="utf-8")
    print(f"Rendered {OUTPUT_DIR / 'index.html'}")
    print(f"Rendered {OUTPUT_DIR / 'report.html'}")
    return 0


def build_context(base_url: str) -> dict[str, Any]:
    health = get_json(f"{base_url}/api/health")
    app = nested(health, "status", "app")
    runtime = nested(health, "status", "runtime")
    fast_model = nested(health, "status", "fast_model")
    verification = latest_verification()
    now = datetime.now(BEIJING)
    version = str(app.get("version") or "unknown")
    build = str(app.get("build") or "unknown")
    commit = git(["rev-parse", "--short", "HEAD"]) or "unknown"
    branch = git(["branch", "--show-current"]) or "unknown"
    upstream = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    git_sync = git_sync_label(upstream)
    return {
        "base_url": base_url,
        "now": now,
        "updated": now.strftime("%Y-%m-%d %H:%M CST"),
        "version": version,
        "build": build,
        "bundle": f"Jarvis {version} build {build}",
        "commit": commit,
        "branch": branch,
        "upstream": upstream,
        "git_sync": git_sync,
        "verification": verification,
        "worker_source_kind": app.get("worker_source_kind") or "unknown",
        "launch_mode": app.get("launch_mode") or "unknown",
        "runtime_pid": runtime.get("pid") or "unknown",
        "fast_model": fast_model,
        "shipped": SHIPPED_ITEMS,
        "proof": proof_items_with_verification(verification),
        "try": TRY_ITEMS,
        "risks": RISK_ITEMS,
        "supporting": SUPPORTING_FILES,
    }


def proof_items_with_verification(verification: dict[str, Any]) -> list[str]:
    items = list(PROOF_ITEMS)
    if verification.get("path"):
        items.append(
            f"Latest verifier artifact: {verification['path']} with {verification['passed']}/{verification['total']} checks."
        )
    return items


def get_json(url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data if isinstance(data, dict) else {}
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return {}


def latest_verification() -> dict[str, Any]:
    reports = sorted((PROJECT_ROOT / "runtime" / "verification").glob("verify-safe-*.json"))
    if not reports:
        return {"ok": False, "path": "", "passed": 0, "total": 0, "label": "none"}
    latest = reports[-1]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "path": str(latest), "passed": 0, "total": 0, "label": "unreadable"}
    results = data.get("results") if isinstance(data.get("results"), list) else []
    passed = sum(1 for item in results if isinstance(item, dict) and item.get("passed"))
    total = len(results)
    relative = str(latest.relative_to(PROJECT_ROOT))
    return {
        "ok": bool(data.get("ok")) and total > 0 and passed == total,
        "path": relative,
        "passed": passed,
        "total": total,
        "label": f"{passed}/{total} passed" if total else "empty",
    }


def nested(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def git(args: list[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def git_sync_label(upstream: str) -> str:
    if not upstream:
        return "not published"
    counts = git(["rev-list", "--left-right", "--count", f"{upstream}...HEAD"])
    try:
        behind, ahead = [int(part) for part in counts.split()]
    except (ValueError, TypeError):
        return "published"
    if ahead == 0 and behind == 0:
        return "up to date"
    parts = []
    if ahead:
        parts.append(f"{ahead} ahead")
    if behind:
        parts.append(f"{behind} behind")
    return ", ".join(parts)


def render_report(context: dict[str, Any]) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="30">
  <link rel="icon" href="data:,">
  <title>Jarvis Master Report</title>
  {style_block()}
</head>
<body>
  <header>
    <h1>Jarvis Overnight Launch Report</h1>
    <p class="tagline">The voice loop moved from promise to first real test surface. This is the single page Leo needs tomorrow morning.</p>
    {pill_row(context)}
  </header>
  <main>
    {section("Tonight's Product Promise", [
        "Jarvis should now be easier to wake, silence, inspect, and test without needing to know which backend path is involved.",
        "The new work is still explicitly experimental around real microphone behavior; the app and tests no longer pretend otherwise.",
        "Tomorrow's job is to test the actual room/audio experience and feed the wake-lab JSON back into the next tuning pass.",
    ], cards=True)}
    {section("Shipped Since The Last Proven Build", context["shipped"])}
    {section("Proof So Far", context["proof"])}
    {section("What You Should Be Able To Do Tomorrow", context["try"])}
    {section("Still Risky Or Unfinished", context["risks"], risk=True)}
    {supporting_section(context)}
  </main>
</body>
</html>
"""


def render_workboard(context: dict[str, Any]) -> str:
    tasks = [
        ("done", "Ship Hey Jarvis native listener", "Experimental app toggle and Speech framework pipeline are in place."),
        ("done", "Acknowledge one-breath wake commands", "Direct Hey Jarvis commands now trigger the wake acknowledgement before capture."),
        ("done", "Add wake debug trace to chat export", "Copy Chat JSON includes the recent wake events and captured command text."),
        ("done", "Ship wake audition lab", "Local page records samples, scores transcripts, and saves samples under runtime."),
        ("done", "Add menu-bar silence control", "Shut Up interrupts and mutes; Keep Blabbering unmutes."),
        ("done", "Add menu-bar wake controls", "Start/Stop Hey Jarvis and Open Wake Test are reachable without the panel."),
        ("done", "Add permission quick action", "The panel has a Perms button for the exact macOS readiness check."),
        ("done", "Add wake-lab decision summary", "Runs now summarize detected count, best noisy pass, and next step."),
        ("done", "Fix final-answer speech coverage", "Normal final replies speak after the working line instead of staying silent."),
        ("done", "Protect streaming answer text", "Late status events can no longer replace visible answer text."),
        ("working", "Next: real-world Leo testing", "Needs actual microphone, room noise, and false-wake feedback."),
    ]
    items = "\n".join(task_item(*task) for task in tasks)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="12">
  <link rel="icon" href="data:,">
  <title>Jarvis Overnight Workboard</title>
  {style_block()}
</head>
<body>
  <header>
    <h1>Jarvis Overnight Workboard</h1>
    {pill_row(context)}
  </header>
  <main>
    <section>
      <h2>Current Focus</h2>
      <p>Jarvis {e(context["version"])} is live with experimental Hey Jarvis, menu-bar mute, menu-bar wake controls, a refreshed wake lab, and broader final-answer speech. The remaining work is real-world listening quality.</p>
      <div class="meter"><div style="width: 88%"></div></div>
    </section>
    <section>
      <h2>Checklist</h2>
      <ul class="tasks">{items}</ul>
    </section>
    {supporting_section(context)}
  </main>
</body>
</html>
"""


def task_item(status: str, title: str, detail: str) -> str:
    checked = " checked" if status == "done" else ""
    badge = "Done" if status == "done" else "Working"
    spinner = '<span class="spin"></span>' if status == "working" else ""
    return (
        f'<li class="{e(status)}"><input type="checkbox" disabled{checked}>'
        f"<span><strong>{spinner}{e(title)}</strong><small>{e(detail)}</small></span>"
        f'<span class="badge">{badge}</span></li>'
    )


def pill_row(context: dict[str, Any]) -> str:
    pills = [
        "Auto-refresh: 30s",
        f"Last updated: {context['updated']}",
        f"Live bundle: {context['bundle']}",
        f"Source commit: {context['commit']}",
        f"Branch: {context['branch']}",
        f"GitHub: {context['upstream'] or 'not published'} ({context['git_sync']})",
        f"Verification: {context['verification']['label']}",
        f"Launch: {context['launch_mode']}",
    ]
    return '<div class="pills">' + "".join(f'<span class="pill">{e(pill)}</span>' for pill in pills) + "</div>"


def section(title: str, items: list[str], *, cards: bool = False, risk: bool = False) -> str:
    if cards:
        body = '<div class="grid">' + "".join(f'<div class="card">{e(item)}</div>' for item in items) + "</div>"
    else:
        cls = ' class="risk-list"' if risk else ""
        body = f"<ul{cls}>" + "".join(f"<li>{e(item)}</li>" for item in items) + "</ul>"
    return f"<section><h2>{e(title)}</h2>{body}</section>"


def supporting_section(context: dict[str, Any]) -> str:
    rows = []
    for path, label in context["supporting"]:
        href = path if path.startswith("http") else "../" + path.removeprefix("runtime/")
        rows.append(f'<li><a href="{e(href)}">{e(path)}</a> - {e(label)}</li>')
    return "<section><h2>Supporting Files</h2><ul>" + "".join(rows) + "</ul></section>"


def style_block() -> str:
    return """<style>
    :root {
      color-scheme: dark;
      --bg: #101216;
      --panel: #181c22;
      --panel-2: #202631;
      --text: #eef3f8;
      --muted: #aab5c4;
      --line: #313a47;
      --green: #55d68f;
      --blue: #7bbcff;
      --gold: #ffd166;
      --red: #ff8080;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.45 -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
    }
    header {
      padding: 26px 22px 18px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(180deg, #171b22, #101216);
    }
    main {
      width: min(1040px, calc(100vw - 28px));
      margin: 0 auto;
      padding: 18px 0 28px;
      display: grid;
      gap: 14px;
    }
    h1 {
      max-width: 1040px;
      margin: 0 auto 8px;
      font-size: clamp(28px, 4vw, 44px);
      line-height: 1.05;
      letter-spacing: 0;
    }
    .tagline {
      max-width: 1040px;
      margin: 0 auto;
      color: var(--muted);
      font-size: 17px;
    }
    .pills {
      max-width: 1040px;
      margin: 15px auto 0;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .pill, .badge {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 999px;
      padding: 5px 9px;
      color: var(--muted);
      white-space: nowrap;
    }
    section {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 15px;
      min-width: 0;
    }
    h2 { margin: 0 0 10px; font-size: 18px; letter-spacing: 0; }
    .grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }
    .card {
      border: 1px solid var(--line);
      background: var(--panel-2);
      border-radius: 8px;
      padding: 12px;
      min-height: 112px;
      overflow-wrap: anywhere;
    }
    ul { margin: 0; padding-left: 19px; }
    li { margin: 6px 0; overflow-wrap: anywhere; }
    a { color: var(--blue); }
    .risk-list li { color: #ffd6d6; }
    .meter {
      height: 10px;
      border: 1px solid var(--line);
      background: #11151b;
      border-radius: 999px;
      overflow: hidden;
      margin-top: 12px;
    }
    .meter > div {
      height: 100%;
      background: linear-gradient(90deg, var(--green), var(--blue));
    }
    .tasks {
      list-style: none;
      padding: 0;
      display: grid;
      gap: 8px;
    }
    .tasks li {
      display: grid;
      grid-template-columns: 22px minmax(0, 1fr) auto;
      gap: 10px;
      align-items: start;
      border: 1px solid var(--line);
      background: var(--panel-2);
      border-radius: 8px;
      padding: 9px;
    }
    input[type="checkbox"] {
      width: 16px;
      height: 16px;
      accent-color: var(--green);
      margin-top: 2px;
    }
    small { display: block; color: var(--muted); margin-top: 2px; }
    .done .badge { color: var(--green); border-color: rgba(85, 214, 143, 0.45); }
    .working .badge { color: var(--gold); border-color: rgba(255, 209, 102, 0.45); }
    .spin {
      width: 14px;
      height: 14px;
      border: 2px solid rgba(123, 188, 255, 0.25);
      border-top-color: var(--blue);
      border-radius: 50%;
      animation: spin 0.9s linear infinite;
      display: inline-block;
      vertical-align: -2px;
      margin-right: 6px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    @media (max-width: 840px) { .grid { grid-template-columns: 1fr; } }
  </style>"""


def e(value: Any) -> str:
    return html.escape(str(value), quote=True)


if __name__ == "__main__":
    raise SystemExit(main())
