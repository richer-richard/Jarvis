"""Typed tool implementations for the Jarvis prototype."""

from __future__ import annotations

import json
import os
import plistlib
import platform
import re
import shutil
import shlex
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import time
import threading
import urllib.error
import urllib.request
import ctypes
import ctypes.util
import uuid
from pathlib import Path
from typing import Any

from .config import (
    CODEX_CHAT_TIMEOUT_SECONDS,
    CODEX_TIMEOUT_SECONDS,
    DEFAULT_CODEX_MODEL,
    DEFAULT_CODEX_REASONING_EFFORT,
    FAST_MODEL_BACKEND,
    FAST_MODEL_FALLBACK_BACKEND,
    FAST_MODEL_FALLBACK_ENABLED,
    FAST_MODEL_MAX_TOKENS,
    FAST_MODEL_NAME,
    FAST_MODEL_TIMEOUT_SECONDS,
    GROQ_API_KEY,
    GROQ_BASE_URL,
    GROQ_FAST_MODEL,
    MAX_FILE_SEARCH_RESULTS,
    OLLAMA_BASE_URL,
    OUTLOOK_APPLESCRIPT_TIMEOUT_SECONDS,
    OUTLOOK_MAX_SCAN_MESSAGES,
    OUTLOOK_OCR_TIMEOUT_SECONDS,
    OUTLOOK_USE_APPLESCRIPT,
    OUTLOOK_USE_LEGACY_SQLITE,
    PROJECT_ROOT,
    RUNTIME_DIR,
    SAFE_SHELL_TIMEOUT_SECONDS,
)
from .injection import scan_untrusted_text
from .safety import classify_command, classify_shell_command, is_shell_allowed
from .wake import WAKE_PHRASES, detect_wake_command


APP_STARTED_AT = time.time()
ACTIVE_TIMERS: dict[str, threading.Timer] = {}
ACTIVE_TIMER_DETAILS: dict[str, dict[str, Any]] = {}
ACTIVE_TIMERS_LOCK = threading.Lock()
CODEX_JOBS: dict[str, dict[str, Any]] = {}
CODEX_JOBS_LOCK = threading.Lock()
CODEX_JOBS_LOADED = False
CODEX_JOB_STORE = RUNTIME_DIR / "codex_jobs.json"
MAX_PERSISTED_CODEX_JOBS = 20
REMOTE_WORKER_USER = "hongyi"
REMOTE_WORKER_HOST = "100.72.212.85"
REMOTE_WORKER_SSH_TARGET = f"{REMOTE_WORKER_USER}@{REMOTE_WORKER_HOST}"
APP_SEARCH_DIRS = [
    Path("/Applications"),
    Path("/Applications/Utilities"),
    Path("/System/Applications"),
    Path("/System/Applications/Utilities"),
    Path.home() / "Applications",
]
EXECUTABLE_CANDIDATE_PATHS = {
    "codex": [
        Path("/Applications/Codex.app/Contents/Resources/codex"),
        Path.home() / ".codex/bin/codex",
        Path("/opt/homebrew/bin/codex"),
        Path("/usr/local/bin/codex"),
    ],
    "ollama": [
        Path("/usr/local/bin/ollama"),
        Path("/opt/homebrew/bin/ollama"),
    ],
    "tesseract": [
        Path("/opt/homebrew/bin/tesseract"),
        Path("/usr/local/bin/tesseract"),
    ],
}
FILE_SEARCH_EXCLUDED_DIRS = {
    ".build",
    ".git",
    ".playwright-cli",
    ".swiftpm",
    ".venv",
    "__pycache__",
    "node_modules",
    "output",
    "runtime",
    "venv",
}


def _safe_getcwd() -> tuple[str | None, str | None]:
    try:
        return os.getcwd(), None
    except OSError as error:
        return None, str(error)


def _path_access_status(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
        return {
            "path": str(path),
            "accessible": True,
            "is_dir": path.is_dir(),
            "mtime": stat.st_mtime,
            "error": None,
        }
    except OSError as error:
        return {
            "path": str(path),
            "accessible": False,
            "is_dir": False,
            "mtime": None,
            "error": str(error),
        }


def tool_registry() -> dict[str, Any]:
    """Return the current typed-tool surface exposed to the planner."""
    codex_path = _find_executable("codex")
    ollama_path = _find_executable("ollama")
    screenshot_tool = _find_executable("screencapture")
    primary_available = (FAST_MODEL_BACKEND == "ollama" and bool(ollama_path)) or (FAST_MODEL_BACKEND == "groq" and bool(GROQ_API_KEY))
    fallback_available = FAST_MODEL_FALLBACK_ENABLED and FAST_MODEL_FALLBACK_BACKEND == "ollama" and bool(ollama_path)
    fast_model_available = primary_available or fallback_available
    return {
        "execution_boundary": "Commands are classified by policy before routing. Protected actions return confirmation objects and are not executed by this prototype.",
        "tools": [
            {
                "id": "conversation.local",
                "label": "Local Reply",
                "mode": "execute",
                "risk": "local",
                "available": True,
                "description": "Returns a local fallback reply when no tool action is needed.",
            },
            {
                "id": "conversation.fast_local",
                "label": "Fast Local Chat",
                "mode": "execute",
                "risk": "local_or_opt_in_cloud_model",
                "available": fast_model_available,
                "description": "Answers safe casual chat through Groq when configured, with local Ollama fallback; no Codex call for casual replies.",
            },
            {
                "id": "diagnostics.fast_model",
                "label": "Fast Model Status",
                "mode": "read_only",
                "risk": "local_metadata",
                "available": True,
                "description": "Reports the configured fast chat model, fallback route, timeout, and latest first-visible latency evidence without calling a model.",
            },
            {
                "id": "diagnostics.tts",
                "label": "TTS Status",
                "mode": "read_only",
                "risk": "local_metadata",
                "available": True,
                "description": "Reports local text-to-speech readiness without playing audio.",
            },
            {
                "id": "conversation.codex",
                "label": "Codex Chat",
                "mode": "execute",
                "risk": "external_model_possible",
                "available": bool(codex_path),
                "description": "Legacy bounded Codex chat path kept for explicit deeper delegation, not default casual conversation.",
            },
            {
                "id": "quick.local_control",
                "label": "Quick Local Control",
                "mode": "execute",
                "risk": "local_control",
                "available": True,
                "description": "Handles deterministic low-latency commands such as time, timers, media controls, volume, brightness, and explicit local speech without a model round trip.",
            },
            {
                "id": "planner.preview",
                "label": "Command Preview",
                "mode": "plan_only",
                "risk": "local",
                "available": True,
                "description": "Classifies and routes a command without executing the selected tool.",
            },
            {
                "id": "system.status",
                "label": "System Status",
                "mode": "execute",
                "risk": "read_only",
                "available": True,
                "description": "Reports local Python, platform, Codex CLI, and macOS tool availability.",
            },
            {
                "id": "diagnostics.latency",
                "label": "Fast Latency Status",
                "mode": "execute",
                "risk": "read_only",
                "available": True,
                "description": "Reads the latest local Jarvis first-visible-text smoke report without calling a model.",
            },
            {
                "id": "diagnostics.launch",
                "label": "Launch Status",
                "mode": "execute",
                "risk": "read_only",
                "available": True,
                "description": "Reports the stable app path, open command, launcher script, bundle id, and app version.",
            },
            {
                "id": "diagnostics.wake",
                "label": "Wake Status",
                "mode": "execute",
                "risk": "read_only",
                "available": True,
                "description": "Reports current keyboard/text wake support and clearly labels real microphone wake as not active yet.",
            },
            {
                "id": "diagnostics.email",
                "label": "Email Backend Status",
                "mode": "execute",
                "risk": "read_only_no_email_content",
                "available": True,
                "description": "Explains configured local email backends and installed app availability without reading email content.",
            },
            {
                "id": "diagnostics.capabilities",
                "label": "Capability Status",
                "mode": "execute",
                "risk": "read_only",
                "available": True,
                "description": "Summarizes what Jarvis can do now, what is partial, and what is not active yet without reading private content.",
            },
            {
                "id": "diagnostics.safety",
                "label": "Safety Status",
                "mode": "execute",
                "risk": "read_only",
                "available": True,
                "description": "Summarizes Jarvis safety gates, confirmation rules, logging, and private-data handling without reading private content.",
            },
            {
                "id": "diagnostics.codex_speed",
                "label": "Codex Speed Status",
                "mode": "execute",
                "risk": "read_only",
                "available": True,
                "description": "Summarizes persisted Codex job timings without starting a new Codex request.",
            },
            {
                "id": "diagnostics.remote_worker",
                "label": "Remote Worker Status",
                "mode": "execute",
                "risk": "read_only_remote_metadata",
                "available": bool(_find_executable("ssh")),
                "description": "Checks the Tailscale MacBook Air SSH helper target using bounded read-only system metadata only.",
            },
            {
                "id": "diagnostics.elevation",
                "label": "Elevation Status",
                "mode": "execute",
                "risk": "read_only",
                "available": True,
                "description": "Explains the planned routing ladder from deterministic local actions to fast chat, smarter model planning, and async Codex.",
            },
            {
                "id": "diagnostics.memory",
                "label": "Memory Status",
                "mode": "execute",
                "risk": "read_only_no_chat_export",
                "available": True,
                "description": "Explains the proposed Jarvis memory system without reading or syncing chat history.",
            },
            {
                "id": "diagnostics.source_access",
                "label": "Source Access Status",
                "mode": "execute",
                "risk": "read_only_metadata",
                "available": True,
                "description": "Reports project-root, Git metadata, source write-open, running bundle, and hardened patch-artifact status without changing source files.",
            },
            {
                "id": "shell.read_only",
                "label": "Read-only Shell",
                "mode": "execute",
                "risk": "read_only_allowlist",
                "available": True,
                "description": "Runs argv-only project-local reads and version checks; code runners, shell chaining, secret paths, secret-bearing filenames, and outside-project paths stop at policy gates.",
            },
            {
                "id": "files.search",
                "label": "File Search",
                "mode": "execute",
                "risk": "read_only",
                "available": True,
                "description": "Searches filenames inside the selected local project root.",
            },
            {
                "id": "app.availability",
                "label": "App Availability",
                "mode": "execute",
                "risk": "read_only",
                "available": True,
                "description": "Checks whether a named macOS app bundle exists in standard app folders.",
            },
            {
                "id": "voice.wake_simulation",
                "label": "Wake Phrase Simulation",
                "mode": "execute",
                "risk": "read_only",
                "available": True,
                "description": "Runs text-only wake phrase detection without microphone access or background listening.",
            },
            {
                "id": "safety.injection_scan",
                "label": "Prompt-Injection Scan",
                "mode": "execute",
                "risk": "read_only",
                "available": True,
                "description": "Flags suspicious instructions in untrusted text without treating them as user commands.",
            },
            {
                "id": "screenshot.capability",
                "label": "Screenshot Capability",
                "mode": "capability_only",
                "risk": "private_read_possible",
                "available": bool(screenshot_tool),
                "description": "Detects whether screenshot tooling exists; screenshots are not stored by default.",
            },
            {
                "id": "browser.open_url",
                "label": "Browser Open URL",
                "mode": "plan_only",
                "risk": "external_navigation_possible",
                "available": True,
                "description": "Records an intent to open a URL; execution belongs to a later native/browser layer.",
            },
            {
                "id": "outlook.visible_summary",
                "label": "Outlook Visible Summary",
                "mode": "execute",
                "risk": "private_read",
                "available": True,
                "description": "Attempts a read-only Outlook newest-message summary, including read mail; asks before drafting, deleting, forwarding, sending, downloading, or exporting.",
            },
            {
                "id": "codex.delegate",
                "label": "Codex Delegation",
                "mode": "execute",
                "risk": "external_model_possible",
                "available": bool(codex_path),
                "description": "Runs explicit Codex CLI requests with a lightweight model and read-only sandbox by default.",
            },
            {
                "id": "codex.job",
                "label": "Async Codex Job",
                "mode": "execute",
                "risk": "external_model_possible",
                "available": bool(codex_path),
                "description": "Starts a background read-only Codex CLI job for broad coding/project requests and lets Leo query the result later.",
            },
            {
                "id": "control.pause",
                "label": "Pause Commands",
                "mode": "execute",
                "risk": "local_control",
                "available": True,
                "description": "Pauses Jarvis command execution at the server boundary while keeping health, audit, and policy endpoints available.",
            },
            {
                "id": "control.resume",
                "label": "Resume Commands",
                "mode": "execute",
                "risk": "local_control",
                "available": True,
                "description": "Resumes Jarvis command execution after a local pause.",
            },
            {
                "id": "policy.pause",
                "label": "Paused",
                "mode": "policy_gate",
                "risk": "local_control",
                "available": True,
                "description": "Refuses command execution while Jarvis is paused.",
            },
            {
                "id": "policy.confirmation",
                "label": "Standard Confirmation",
                "mode": "policy_gate",
                "risk": "reversible_change",
                "available": True,
                "description": "Stops local-changing actions until the UI collects confirmation.",
            },
            {
                "id": "policy.strong_confirmation",
                "label": "Strong Confirmation",
                "mode": "policy_gate",
                "risk": "external_destructive_sensitive",
                "available": True,
                "description": "Stops external, destructive, settings, secret, install, or money-related actions.",
            },
            {
                "id": "policy.block",
                "label": "Policy Block",
                "mode": "policy_gate",
                "risk": "blocked",
                "available": True,
                "description": "Blocks commands that cannot be represented safely in the prototype.",
            },
        ],
    }


def system_status() -> dict[str, Any]:
    codex_path = _find_executable("codex")
    ollama_path = _find_executable("ollama")
    primary_fast_model_available = (FAST_MODEL_BACKEND == "ollama" and bool(ollama_path)) or (FAST_MODEL_BACKEND == "groq" and bool(GROQ_API_KEY))
    fallback_fast_model_available = FAST_MODEL_FALLBACK_ENABLED and FAST_MODEL_FALLBACK_BACKEND == "ollama" and bool(ollama_path)
    cwd, cwd_error = _safe_getcwd()
    project_root_status = _path_access_status(PROJECT_ROOT)
    return {
        "project_root": str(PROJECT_ROOT),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "runtime": {
            "pid": os.getpid(),
            "cwd": cwd or "",
            "cwd_available": cwd_error is None,
            "cwd_error": cwd_error,
            "started_at": APP_STARTED_AT,
            "uptime_seconds": round(time.time() - APP_STARTED_AT, 3),
            "source": str(Path(__file__).resolve()),
            "project_root_access": project_root_status,
        },
        "timers": {
            "active_count": _active_timer_count(),
        },
        "codex_jobs": _codex_job_counts(),
        "codex": {
            "path": codex_path,
            "version": _command_output([codex_path, "--version"]) if codex_path else None,
        },
        "fast_model": {
            "backend": FAST_MODEL_BACKEND,
            "model": GROQ_FAST_MODEL if FAST_MODEL_BACKEND == "groq" else FAST_MODEL_NAME,
            "fallback_enabled": FAST_MODEL_FALLBACK_ENABLED,
            "fallback_backend": FAST_MODEL_FALLBACK_BACKEND,
            "fallback_model": FAST_MODEL_NAME if FAST_MODEL_FALLBACK_BACKEND == "ollama" else None,
            "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
            "max_tokens": FAST_MODEL_MAX_TOKENS,
            "ollama_path": ollama_path,
            "ollama_base_url": OLLAMA_BASE_URL,
            "groq_base_url": GROQ_BASE_URL,
            "groq_key_configured": bool(GROQ_API_KEY),
            "available": primary_fast_model_available or fallback_fast_model_available,
        },
        "mac_tools": {
            "osascript": _find_executable("osascript"),
            "say": _find_executable("say"),
            "screencapture": _find_executable("screencapture"),
            "swift": _find_executable("swift"),
            "xcrun": _find_executable("xcrun"),
        },
    }


def latest_latency_status() -> dict[str, Any]:
    report_dir = PROJECT_ROOT / "runtime" / "model_benchmarks"
    reports = sorted(report_dir.glob("localhost-fast-latency-*.json"))
    base: dict[str, Any] = {
        "tool": "diagnostics.latency",
        "executed": True,
        "report_dir": str(report_dir),
    }
    if not reports:
        return {
            **base,
            "status": "missing",
            "reply": "I do not have a local fast-latency smoke report yet. Run `python3 scripts/smoke_fast_latency.py` from the project folder.",
        }

    latest = reports[-1]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            **base,
            "status": "unreadable",
            "report": _relative_project_path(latest),
            "error": str(error),
            "reply": "I found a fast-latency smoke report, but I could not read it.",
        }

    results = data.get("results", [])
    if not isinstance(results, list):
        results = []
    max_first_allowed = _float_or_default(data.get("max_first_visible_seconds"), 3.0)
    max_total_allowed = _float_or_default(data.get("max_total_seconds"), 5.0)
    min_after_first_cps = _float_or_default(data.get("min_after_first_chars_per_second"), 20.0)
    min_rate_visible_chars = int(_float_or_default(data.get("min_rate_visible_chars"), 20.0))
    completed_count = 0
    first_values: list[float] = []
    total_values: list[float] = []
    after_first_cps_values: list[float] = []
    prompt_summaries: list[dict[str, Any]] = []
    ok = bool(results)
    for result in results:
        if not isinstance(result, dict):
            ok = False
            continue
        if result.get("status") == "completed":
            completed_count += 1
        else:
            ok = False
        first = _float_or_none(result.get("first_visible_seconds"))
        total = _float_or_none(result.get("total_seconds"))
        cps = _float_or_none(result.get("chars_per_second_after_first_visible"))
        visible_chars = int(_float_or_default(result.get("visible_chars"), 0.0))
        if first is None or first > max_first_allowed:
            ok = False
        else:
            first_values.append(first)
        if total is None or total > max_total_allowed:
            ok = False
        else:
            total_values.append(total)
        if cps is not None:
            after_first_cps_values.append(cps)
        if visible_chars >= min_rate_visible_chars and (cps is None or cps < min_after_first_cps):
            ok = False
        prompt_summaries.append(
            {
                "prompt": str(result.get("prompt") or "")[:160],
                "status": str(result.get("status") or "unknown"),
                "first_visible_seconds": first,
                "total_seconds": total,
                "visible_chars": visible_chars,
                "chars_per_second_after_first_visible": cps,
            }
        )
    if completed_count != len(results):
        ok = False
    max_first = max(first_values) if first_values else None
    max_total = max(total_values) if total_values else None
    min_after_first = min(after_first_cps_values) if after_first_cps_values else None
    state = "passed" if ok else "needs_attention"
    reply = (
        f"Latest fast-latency smoke {state.replace('_', ' ')}: "
        f"{completed_count}/{len(results)} prompts completed"
    )
    if max_first is not None:
        reply += f", max first visible text {max_first:.3f}s"
    if max_total is not None:
        reply += f", max total {max_total:.3f}s"
    if min_after_first is not None:
        reply += f", min after-first output {min_after_first:.1f} chars/s"
    reply += f". Report: {_relative_project_path(latest)}."
    return {
        **base,
        "status": state,
        "ok": ok,
        "report": _relative_project_path(latest),
        "generated_at": data.get("generated_at"),
        "age_seconds": round(max(0.0, time.time() - latest.stat().st_mtime), 3),
        "prompt_count": len(results),
        "completed_count": completed_count,
        "max_first_visible_seconds": round(max_first, 3) if max_first is not None else None,
        "max_total_seconds": round(max_total, 3) if max_total is not None else None,
        "min_after_first_chars_per_second": round(min_after_first, 1) if min_after_first is not None else None,
        "max_first_visible_allowed_seconds": max_first_allowed,
        "max_total_allowed_seconds": max_total_allowed,
        "min_after_first_allowed_chars_per_second": min_after_first_cps,
        "min_rate_visible_chars": min_rate_visible_chars,
        "prompts": prompt_summaries,
        "reply": reply,
    }


def fast_model_status() -> dict[str, Any]:
    """Return model-routing status without calling a model."""
    status = system_status()
    fast_model = status.get("fast_model", {})
    latency = latest_latency_status()
    backend = str(fast_model.get("backend") or "unknown")
    model = str(fast_model.get("model") or "unknown")
    fallback_enabled = bool(fast_model.get("fallback_enabled"))
    fallback_backend = fast_model.get("fallback_backend")
    fallback_model = fast_model.get("fallback_model")
    available = bool(fast_model.get("available"))
    key_configured = bool(fast_model.get("groq_key_configured"))
    timeout = fast_model.get("timeout_seconds")
    max_tokens = fast_model.get("max_tokens")
    reply = (
        f"Fast model status: primary {backend}/{model} is "
        f"{'available' if available else 'not available'}"
    )
    if backend == "groq":
        reply += f" with Groq key {'configured' if key_configured else 'missing'}"
    if fallback_enabled:
        reply += f"; fallback {fallback_backend}/{fallback_model}"
    else:
        reply += "; fallback disabled"
    if timeout is not None:
        reply += f"; timeout {timeout}s"
    if max_tokens is not None:
        reply += f"; max {max_tokens} output tokens"
    if latency.get("status") == "passed":
        max_first = latency.get("max_first_visible_seconds")
        max_total = latency.get("max_total_seconds")
        min_after_first = latency.get("min_after_first_chars_per_second")
        reply += (
            f". Latest live smoke: max first visible {max_first:.3f}s, "
            f"max total {max_total:.3f}s"
        )
        if min_after_first is not None:
            reply += f", min after-first output {min_after_first:.1f} chars/s"
    elif latency.get("reply"):
        reply += f". {latency['reply']}"
    reply += ". Normal conversation uses this route, not Codex."
    return {
        "tool": "diagnostics.fast_model",
        "executed": True,
        "status": "checked",
        "read_private_content": False,
        "backend": backend,
        "model": model,
        "available": available,
        "groq_key_configured": key_configured,
        "fallback_enabled": fallback_enabled,
        "fallback_backend": fallback_backend,
        "fallback_model": fallback_model,
        "timeout_seconds": timeout,
        "max_tokens": max_tokens,
        "latency": latency,
        "reply": reply,
    }


def tts_status() -> dict[str, Any]:
    """Return text-to-speech readiness without playing audio."""
    say_path = _find_executable("say")
    voice_names: list[str] = []
    voice_output = ""
    if say_path:
        voice_output = _command_output([say_path, "-v", "?"])
        for line in voice_output.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            name = stripped.split(maxsplit=1)[0]
            if name and name not in voice_names:
                voice_names.append(name)
    available = bool(say_path)
    sample_voices = voice_names[:8]
    reply = (
        "TTS status: macOS `say` is "
        f"{'available' if available else 'not available'}"
    )
    if say_path:
        reply += f" at {say_path}"
    reply += (
        ". Explicit speech commands are "
        f"{'available' if available else 'not available'}: `speak ...`, `say out loud ...`, and `read ... loud ...`."
        " Automatic spoken replies are off."
    )
    if voice_names:
        reply += f" Detected {len(voice_names)} voices"
        if sample_voices:
            reply += f" (examples: {', '.join(sample_voices[:5])})"
        reply += "."
    reply += " This did not play audio, record audio, or request microphone permission."
    return {
        "tool": "diagnostics.tts",
        "executed": True,
        "status": "available" if available else "missing",
        "read_private_content": False,
        "played_audio": False,
        "say_path": say_path,
        "explicit_tts_available": available,
        "automatic_tts_enabled": False,
        "voice_count": len(voice_names),
        "sample_voices": sample_voices,
        "reply": reply,
    }


def launch_status() -> dict[str, Any]:
    running_bundle = _enclosing_app_bundle(Path(__file__).resolve())
    bundle_path = Path(running_bundle) if running_bundle else PROJECT_ROOT / "output" / "Jarvis.app"
    stable_bundle_path = PROJECT_ROOT / "output" / "Jarvis.app"
    launcher_path = PROJECT_ROOT / "scripts" / "open_jarvis.sh"
    metadata = _bundle_metadata(bundle_path)
    exists = bundle_path.exists()
    bundle_display = str(bundle_path)
    open_command = f'open "{bundle_display}"'
    launcher_command = "scripts/open_jarvis.sh"
    reply_lines = [
        f"Open Jarvis with: {open_command}",
        f"Short launcher from the project folder: {launcher_command}",
    ]
    if running_bundle:
        reply_lines.append(f"Running bundle: {running_bundle}.")
    if metadata:
        version = metadata.get("version") or "unknown"
        build = metadata.get("build") or "unknown"
        bundle_id = metadata.get("bundle_id") or "unknown"
        reply_lines.append(f"Current bundle: version {version}, build {build}, bundle id {bundle_id}.")
    elif not exists:
        reply_lines.append("I do not see the stable Jarvis app bundle at the expected path.")
    return {
        "tool": "diagnostics.launch",
        "executed": True,
        "status": "available" if exists else "missing",
        "bundle_path": bundle_display,
        "bundle_exists": exists,
        "running_bundle": running_bundle,
        "stable_bundle_path": str(stable_bundle_path),
        "stable_bundle_exists": stable_bundle_path.exists(),
        "open_command": open_command,
        "launcher_path": str(launcher_path),
        "launcher_exists": launcher_path.exists(),
        "launcher_command": launcher_command,
        "metadata": metadata,
        "reply": "\n".join(reply_lines),
    }


def _bundle_metadata(bundle_path: Path) -> dict[str, Any] | None:
    info_plist = bundle_path / "Contents" / "Info.plist"
    if not info_plist.exists():
        return None
    try:
        with info_plist.open("rb") as handle:
            plist = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException):
        return None
    return {
        "name": plist.get("CFBundleName"),
        "display_name": plist.get("CFBundleDisplayName"),
        "bundle_id": plist.get("CFBundleIdentifier"),
        "version": plist.get("CFBundleShortVersionString"),
        "build": plist.get("CFBundleVersion"),
    }


def run_read_only_shell(command: str) -> dict[str, Any]:
    assessment = classify_shell_command(command)
    if not is_shell_allowed(command):
        return {
            "executed": False,
            "assessment": assessment.to_dict(),
            "stdout": "",
            "stderr": "",
            "returncode": None,
        }
    parts = shlex.split(command)
    try:
        completed = subprocess.run(
            parts,
            shell=False,
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=SAFE_SHELL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        return {
            "executed": True,
            "timed_out": True,
            "assessment": assessment.to_dict(),
            "stdout": _text_tail(error.stdout, 6000),
            "stderr": _text_tail(error.stderr, 3000),
            "returncode": None,
            "error": f"Command timed out after {SAFE_SHELL_TIMEOUT_SECONDS}s.",
        }
    except OSError as error:
        return {
            "executed": False,
            "assessment": assessment.to_dict(),
            "stdout": "",
            "stderr": "",
            "returncode": None,
            "error": str(error),
        }
    return {
        "executed": True,
        "assessment": assessment.to_dict(),
        "stdout": completed.stdout[-6000:],
        "stderr": completed.stderr[-3000:],
        "returncode": completed.returncode,
    }


def _text_tail(value: str | bytes | None, max_chars: int) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value[-max_chars:]


def _relative_project_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except (OSError, ValueError):
        return str(path)


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float_or_default(value: Any, default: float) -> float:
    parsed = _float_or_none(value)
    return parsed if parsed is not None else default


def find_files(query: str, root: str | None = None, limit: int = MAX_FILE_SEARCH_RESULTS) -> dict[str, Any]:
    search_root = _safe_root(root)
    cleaned = query.strip().lower()
    if not cleaned:
        return {"root": str(search_root), "query": query, "results": []}
    results: list[str] = []
    for current_root, dirs, files in os.walk(search_root):
        dirs[:] = [d for d in dirs if d not in FILE_SEARCH_EXCLUDED_DIRS]
        for filename in files:
            if cleaned in filename.lower():
                results.append(str(Path(current_root, filename).relative_to(search_root)))
                if len(results) >= limit:
                    return {"root": str(search_root), "query": query, "results": results}
    return {"root": str(search_root), "query": query, "results": results}


def app_availability(app_name: str, search_dirs: list[Path] | None = None) -> dict[str, Any]:
    name = app_name.strip().removesuffix(".app")
    directories = search_dirs or APP_SEARCH_DIRS
    matches: list[str] = []
    for directory in directories:
        if not directory.exists() or not directory.is_dir():
            continue
        lowered = name.lower()
        matched = False
        for candidate in directory.glob("*.app"):
            if candidate.stem.lower() == lowered:
                matches.append(str(candidate))
                matched = True
                break
        if matched:
            continue
        exact = directory / f"{name}.app"
        if exact.exists():
            matches.append(str(exact))
    return {"app": name, "available": bool(matches), "matches": matches}


def screenshot_capability() -> dict[str, Any]:
    tool = _find_executable("screencapture")
    available = bool(tool)
    reply = (
        "Screen status: the worker "
        f"{'can find' if available else 'cannot find'} macOS `screencapture`"
    )
    if tool:
        reply += f" at {tool}"
    reply += (
        ". This status check did not capture the screen, run OCR, or store an image. "
        "Native Jarvis OCR uses the app process and depends on Screen Recording permission for the current app identity."
    )
    return {
        "tool": "screenshot.capability",
        "status": "available" if available else "missing",
        "available": bool(tool),
        "screencapture_path": tool,
        "captured_screen": False,
        "stored_screenshot": False,
        "read_private_content": False,
        "native_ocr_route": "read the visible Outlook screen with OCR",
        "prototype_behavior": "Capability check only. This prototype does not store screenshots by default.",
        "reply": reply,
    }


def wake_phrase_simulation(transcript: str) -> dict[str, Any]:
    detection = detect_wake_command(transcript)
    command_assessment = classify_command(detection.command).to_dict() if detection.command else None
    return {
        "tool": "voice.wake_simulation",
        "status": "detected" if detection.woke else "ignored",
        "wake_phrase": detection.phrase,
        "command": detection.command,
        "command_assessment": command_assessment,
        "needs_followup": detection.needs_followup,
        "detection": detection.to_dict(),
        "prototype_behavior": "Text simulation only. No microphone, audio capture, or background listener is active.",
    }


def wake_status() -> dict[str, Any]:
    wake_phrases = tuple(phrase.title() for phrase in WAKE_PHRASES)
    reply = (
        "Wake status: keyboard shortcut wake/focus is available with Command+Option+J. "
        "Typed wake simulation is available for Hey Jarvis, OK Jarvis, and Okay Jarvis. "
        "Real background microphone wake-word listening is not active yet."
    )
    return {
        "tool": "diagnostics.wake",
        "executed": True,
        "status": "partial",
        "keyboard_shortcut": "Command+Option+J",
        "keyboard_wake_available": True,
        "typed_wake_simulation_available": True,
        "typed_wake_phrases": list(wake_phrases),
        "microphone_wake_available": False,
        "speech_to_text_available": False,
        "background_listener_active": False,
        "missing_for_voice_wake": [
            "Microphone permission",
            "Speech Recognition permission",
            "Local wake-word listener",
            "False-wake tuning with Leo's real voice",
        ],
        "reply": reply,
    }


def capabilities_status() -> dict[str, Any]:
    """Return a compact product-level capability snapshot without private reads."""
    latency = latest_latency_status()
    launch = launch_status()
    wake = wake_status()
    email = email_backend_status()
    source_access = source_access_status()
    status = system_status()
    fast_model = status.get("fast_model", {})
    codex = status.get("codex", {})
    timers = status.get("timers", {})
    codex_jobs = status.get("codex_jobs", {})
    latency_state = "working" if latency.get("status") == "passed" else str(latency.get("status") or "needs_attention")
    launch_state = "working" if launch.get("status") == "available" else str(launch.get("status") or "needs_attention")
    capabilities = [
        {
            "id": "typed_chat",
            "status": "working",
            "summary": "Typed Jarvis chat is available in the macOS app.",
            "test_prompt": "hello Jarvis",
            "needs_leo": False,
        },
        {
            "id": "fast_chat",
            "status": "working" if fast_model.get("available") else "needs_attention",
            "summary": "Safe casual chat uses the fast model route, with Ollama fallback when configured.",
            "test_prompt": "tell me a short joke",
            "needs_leo": False,
            "backend": fast_model.get("backend"),
            "model": fast_model.get("model"),
        },
        {
            "id": "latency",
            "status": latency_state,
            "summary": latency.get("reply"),
            "test_prompt": "latency status",
            "needs_leo": False,
        },
        {
            "id": "quick_controls",
            "status": "partial",
            "summary": "Time, timers, media, volume, brightness, and explicit local speech routes exist; device-affecting controls should be confirmed while Leo is awake.",
            "test_prompt": "what time is it",
            "needs_leo": True,
        },
        {
            "id": "email",
            "status": "partial",
            "summary": "Newest-email routing exists, but real mailbox quality depends on Mail/Outlook permissions or visible OCR state.",
            "test_prompt": "email backend status",
            "needs_leo": True,
            "available_route_ids": email.get("available_route_ids", []),
        },
        {
            "id": "codex",
            "status": "working" if codex.get("path") else "unavailable",
            "summary": "Codex CLI delegation is available for deeper code/project work; broad requests run asynchronously.",
            "test_prompt": "ask Codex to say exactly: Jarvis Codex smoke test OK",
            "needs_leo": False,
            "version": codex.get("version"),
        },
        {
            "id": "elevation",
            "status": "partial",
            "summary": "Deterministic local, fast-model, and async Codex layers exist; the smarter middle planner is designed but not built yet.",
            "test_prompt": "elevation status",
            "needs_leo": False,
        },
        {
            "id": "remote_worker",
            "status": "partial",
            "summary": "MacBook Air SSH diagnostics are available; automatic remote helper jobs are not enabled yet.",
            "test_prompt": "remote worker status",
            "needs_leo": False,
        },
        {
            "id": "memory",
            "status": "not_built",
            "summary": "Memory architecture is designed around daily summaries and optional MacBook Air sync, but chat-history summarization is not enabled yet.",
            "test_prompt": "memory status",
            "needs_leo": True,
        },
        {
            "id": "wake",
            "status": "partial",
            "summary": "Keyboard wake and typed wake simulation are available; real microphone wake-word listening is not active yet.",
            "test_prompt": "wake status",
            "needs_leo": True,
        },
        {
            "id": "speech_to_text",
            "status": "not_built",
            "summary": "Real microphone speech-to-text is not built yet.",
            "test_prompt": "speech recognition permission status",
            "needs_leo": True,
        },
        {
            "id": "tts",
            "status": "partial",
            "summary": "Explicit local macOS speech commands exist; automatic spoken replies are not enabled.",
            "test_prompt": "say out loud Jarvis speech test",
            "needs_leo": True,
        },
        {
            "id": "computer_control",
            "status": "partial",
            "summary": "Policy and planning exist, but full app control needs Accessibility permission and more workflow-specific tooling.",
            "test_prompt": "permissions status",
            "needs_leo": True,
        },
        {
            "id": "launch",
            "status": launch_state,
            "summary": "Stable app launch diagnostics are available.",
            "test_prompt": "Jarvis launch status",
            "needs_leo": False,
            "open_command": launch.get("open_command"),
        },
        {
            "id": "source_access",
            "status": "working" if source_access.get("status") == "checked" else "needs_attention",
            "summary": source_access.get("reply"),
            "test_prompt": "source access status",
            "needs_leo": False,
            "git_visible": source_access.get("git", {}).get("git_dir_exists"),
            "locked_source_count": source_access.get("locked_source_count"),
        },
    ]
    working = sum(1 for item in capabilities if item["status"] == "working")
    partial = sum(1 for item in capabilities if item["status"] == "partial")
    not_ready = sum(1 for item in capabilities if item["status"] in {"not_built", "unavailable", "missing", "needs_attention"})
    reply = (
        f"Capability status: {working} working, {partial} partial, {not_ready} not ready. "
        "Working now includes typed chat, fast casual chat, latency status, Codex async delegation, launch diagnostics, and source-access diagnostics. "
        "Partial work includes email, quick device controls, elevation routing, remote helper diagnostics, wake, TTS, and computer control. "
        "Not active yet: real microphone speech-to-text, memory summarization, and background wake-word listening. "
        "This diagnostic did not read email, screenshots, microphone audio, or files."
    )
    return {
        "tool": "diagnostics.capabilities",
        "executed": True,
        "status": "checked",
        "read_private_content": False,
        "counts": {
            "working": working,
            "partial": partial,
            "not_ready": not_ready,
        },
        "capabilities": capabilities,
        "timers": timers,
        "codex_jobs": codex_jobs,
        "wake": {
            "keyboard_wake_available": wake.get("keyboard_wake_available"),
            "microphone_wake_available": wake.get("microphone_wake_available"),
            "background_listener_active": wake.get("background_listener_active"),
        },
        "reply": reply,
    }


def safety_status() -> dict[str, Any]:
    """Return a product-level safety snapshot without reading private content."""
    rules = [
        {
            "id": "typed_confirmation",
            "status": "active",
            "summary": "External sends/posts/forms, destructive file actions, settings changes, installs, sudo/elevated commands, secret exposure, and money-related actions stop at a typed confirmation gate.",
        },
        {
            "id": "private_reads",
            "status": "visible_logging",
            "summary": "Local private reads such as email are allowed only as read-only workflows and are logged as private-read actions; sends, downloads, forwards, deletes, and exports remain gated.",
        },
        {
            "id": "prompt_injection",
            "status": "active",
            "summary": "Email/OCR/browser-like text is treated as untrusted data and scanned for instruction overrides, secret requests, and authority impersonation before Jarvis acts on it.",
        },
        {
            "id": "shell",
            "status": "restricted",
            "summary": "Shell execution is argv-only and read-only by default; chaining, redirects, code runners, external paths, secret-looking paths, and destructive commands are blocked or require confirmation.",
        },
        {
            "id": "audit",
            "status": "active",
            "summary": "Audit events stay local under the project runtime with retention and size caps; private snippets are not intentionally stored in audit summaries.",
        },
        {
            "id": "capture_storage",
            "status": "minimal",
            "summary": "Jarvis does not store raw microphone audio or screenshots by default. Native OCR sends extracted text to the worker, not the screenshot image.",
        },
        {
            "id": "pause",
            "status": "active",
            "summary": "Pause mode blocks command execution while keeping health, readiness, plan, and policy checks available.",
        },
    ]
    reply = (
        "Safety status: protected actions require confirmation, private local reads stay read-only and visibly logged, "
        "untrusted text is scanned for prompt injection, shell execution is restricted to safe reads, and raw audio/screenshots are not stored by default. "
        "This diagnostic did not read email, files, screenshots, microphone audio, or browser content."
    )
    return {
        "tool": "diagnostics.safety",
        "executed": True,
        "status": "checked",
        "read_private_content": False,
        "rules": rules,
        "confirmation_phrase": "JARVIS APPROVE",
        "audit_location": str(RUNTIME_DIR / "audit"),
        "reply": reply,
    }


def remote_worker_status(*, probe: bool = True) -> dict[str, Any]:
    """Return bounded Tailscale MacBook Air readiness without reading user files."""
    ssh = _find_executable("ssh")
    base: dict[str, Any] = {
        "tool": "diagnostics.remote_worker",
        "executed": bool(probe and ssh),
        "read_private_content": False,
        "changed_remote_state": False,
        "target": REMOTE_WORKER_SSH_TARGET,
        "host": REMOTE_WORKER_HOST,
        "user": REMOTE_WORKER_USER,
        "tailnet_transport": "ssh_over_tailscale",
        "ssh_path": ssh,
        "allowed_probe": "hostname, sw_vers, uname -m, hw.memsize, CPU brand",
        "recommended_roles": [
            "overnight model benchmarks",
            "Codex or test-runner helper jobs",
            "daily Jarvis memory summarizer after Leo approves the retention/sync policy",
            "remote app-control experiments with a separate permission model",
        ],
        "not_enabled_yet": [
            "automatic chat-history sync",
            "remote file browsing",
            "remote destructive commands",
            "always-on remote Jarvis agent",
        ],
    }
    if not ssh:
        return {
            **base,
            "status": "ssh_not_found",
            "reply": "Remote worker status: SSH is not available on this Mac, so I cannot check the MacBook Air helper.",
        }
    if not probe:
        return {
            **base,
            "status": "planned",
            "reply": f"Remote worker status: MacBook Air helper is configured as {REMOTE_WORKER_SSH_TARGET}, but this was a plan-only check.",
        }

    remote_script = (
        "printf 'JARVIS_REMOTE_OK\\n'; "
        "hostname; "
        "sw_vers -productName; "
        "sw_vers -productVersion; "
        "uname -m; "
        "sysctl -n hw.memsize; "
        "sysctl -n machdep.cpu.brand_string 2>/dev/null || sysctl -n hw.optional.arm64"
    )
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [
                ssh,
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                REMOTE_WORKER_SSH_TARGET,
                remote_script,
            ],
            shell=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        duration = _duration_fields(started)
        return {
            **base,
            **duration,
            "status": "timeout",
            "reply": f"Remote worker status: SSH to {REMOTE_WORKER_SSH_TARGET} timed out after {duration['duration_human']}.",
            "error": str(error),
        }
    except OSError as error:
        duration = _duration_fields(started)
        return {
            **base,
            **duration,
            "status": "ssh_error",
            "reply": f"Remote worker status: I could not start SSH to {REMOTE_WORKER_SSH_TARGET}.",
            "error": str(error),
        }

    duration = _duration_fields(started)
    lines = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
    if completed.returncode != 0 or not lines or lines[0] != "JARVIS_REMOTE_OK":
        return {
            **base,
            **duration,
            "status": "unavailable",
            "returncode": completed.returncode,
            "stderr": _text_tail(completed.stderr, 600),
            "reply": f"Remote worker status: SSH reached {REMOTE_WORKER_SSH_TARGET} unsuccessfully or returned an unexpected probe response.",
        }

    hostname = lines[1] if len(lines) > 1 else "unknown"
    product_name = lines[2] if len(lines) > 2 else "unknown"
    product_version = lines[3] if len(lines) > 3 else "unknown"
    architecture = lines[4] if len(lines) > 4 else "unknown"
    memory_bytes = _safe_int(lines[5] if len(lines) > 5 else None)
    cpu = lines[6] if len(lines) > 6 else "unknown"
    memory_gb = round(memory_bytes / (1024 ** 3), 1) if memory_bytes else None
    reply = (
        f"Remote worker status: MacBook Air SSH is reachable at {REMOTE_WORKER_SSH_TARGET} "
        f"as {hostname}, {product_name} {product_version}, {architecture}, {cpu}"
    )
    if memory_gb is not None:
        reply += f", {memory_gb:g} GB RAM"
    reply += f". Probe time: {duration['duration_human']}. No user files were read."
    return {
        **base,
        **duration,
        "status": "available",
        "returncode": completed.returncode,
        "hostname": hostname,
        "product_name": product_name,
        "product_version": product_version,
        "architecture": architecture,
        "memory_bytes": memory_bytes,
        "memory_gb": memory_gb,
        "cpu": cpu,
        "reply": reply,
    }


def elevation_status() -> dict[str, Any]:
    """Describe the model-routing ladder without calling a model."""
    fast = fast_model_status()
    codex_path = _find_executable("codex")
    stages = [
        {
            "id": "deterministic_local",
            "status": "active",
            "target_latency": "instant_to_1s",
            "examples": ["time", "date", "timers", "battery", "storage", "media keys", "volume", "brightness"],
            "route": "quick.local_control",
        },
        {
            "id": "fast_chat",
            "status": "active" if fast.get("available") else "needs_attention",
            "target_latency": "first_visible_under_1_to_3s",
            "backend": fast.get("backend"),
            "model": fast.get("model"),
            "fallback_backend": fast.get("fallback_backend"),
            "fallback_model": fast.get("fallback_model"),
            "route": "conversation.fast_local",
        },
        {
            "id": "smarter_planner",
            "status": "planned",
            "target_latency": "under_5s_when_possible",
            "route": "future conversation.elevated_planner",
            "purpose": "Ambiguous multi-step requests, careful email summaries, and deciding whether Codex is needed.",
        },
        {
            "id": "codex",
            "status": "active" if codex_path else "unavailable",
            "target_latency": "async_minutes_ok",
            "route": "codex.job",
            "purpose": "Code, repo review, builds, tests, and long project work.",
        },
    ]
    reply = (
        "Elevation status: Jarvis already has the bottom and top of the ladder: deterministic local commands for instant actions, "
        f"fast chat through {fast.get('backend')}/{fast.get('model')}, and async Codex for project work. "
        "The missing middle is a smarter planner route that can decide when the fast model is not enough without making every reply wait for Codex. "
        "This diagnostic did not call any model."
    )
    return {
        "tool": "diagnostics.elevation",
        "executed": True,
        "status": "partial",
        "read_private_content": False,
        "called_model": False,
        "stages": stages,
        "reply": reply,
    }


def memory_status() -> dict[str, Any]:
    """Describe the proposed Jarvis memory system without reading chat history."""
    memory_root = RUNTIME_DIR / "memory"
    daily_summary_dir = memory_root / "daily_summaries"
    design = {
        "local_daily_summaries": str(daily_summary_dir),
        "profile_memory_file": str(memory_root / "MEMORY.md"),
        "remote_target": REMOTE_WORKER_SSH_TARGET,
        "sync_unit": "summaries_first_not_raw_chat_by_default",
        "default_retention": "daily summaries retained, raw debug exports opt-in and deletable",
    }
    phases = [
        "Add local daily summary export from Jarvis chat history with private-content redaction options.",
        "Let Leo review or delete a daily summary before any remote sync.",
        "Sync approved summaries to the MacBook Air over Tailscale SSH.",
        "Run a remote summarizer that updates a growing MEMORY.md-style profile plus dated evidence summaries.",
        "Use the profile as retrieval context for Jarvis responses, with a visible memory status/delete flow.",
    ]
    reply = (
        "Memory status: feasible, but not enabled yet. The safe design is daily local summaries first, "
        "optional approved sync to the MacBook Air, then a remote summarizer maintaining a MEMORY.md-style profile. "
        "I did not read or sync chat history in this diagnostic."
    )
    return {
        "tool": "diagnostics.memory",
        "executed": True,
        "status": "planned",
        "read_private_content": False,
        "synced_remote": False,
        "read_chat_history": False,
        "design": design,
        "phases": phases,
        "reply": reply,
    }


def source_access_status() -> dict[str, Any]:
    """Explain whether this process can see and update the project source tree."""
    running_bundle = _enclosing_app_bundle(Path(__file__).resolve())
    source_candidates = [
        PROJECT_ROOT / "jarvis" / "tools.py",
        PROJECT_ROOT / "jarvis" / "server.py",
        PROJECT_ROOT / "jarvis" / "audit.py",
        PROJECT_ROOT / "jarvis" / "planner.py",
        PROJECT_ROOT / "scripts" / "run_dashboard.py",
    ]
    git_candidates = [
        PROJECT_ROOT / ".git",
        PROJECT_ROOT / "jarvis" / ".git",
    ]
    patch_paths = [
        Path.home() / "Library" / "Application Support" / "Jarvis" / "Jarvis-Hardened-SourceDiag-source.patch",
        Path.home() / "Library" / "Application Support" / "Jarvis" / "Jarvis-Hardened-SourceDiag-runtime.patch",
        Path.home() / "Library" / "Application Support" / "Jarvis" / "Jarvis-Hardened-Final.patch",
    ]

    project_root_status = _path_access_status(PROJECT_ROOT)
    file_checks = [_source_file_access(path) for path in source_candidates]
    locked_files = [check["path"] for check in file_checks if check.get("exists") and not check.get("open_for_update_ok")]
    git_dirs = [_git_dir_status(path) for path in git_candidates]
    visible_git_dirs = [check["path"] for check in git_dirs if check.get("exists")]
    git_probes = [_git_status_probe(candidate) for candidate in (PROJECT_ROOT, PROJECT_ROOT / "jarvis")]
    preferred_probe = next((probe for probe in git_probes if probe.get("status") == "ok"), git_probes[0] if git_probes else {})
    patch_checks = [_patch_artifact_status(path) for path in patch_paths]
    preferred_patch = next((check for check in patch_checks if check.get("exists")), patch_checks[0] if patch_checks else {})

    source_state = "writable" if file_checks and not locked_files else "locked_or_unavailable"
    git_state = "visible" if visible_git_dirs else "not_visible"
    reply = (
        f"Source access status: project root is "
        f"{'accessible' if project_root_status.get('accessible') else 'not accessible'}, "
        f"Git metadata is {git_state}, and source files are {source_state} to this Jarvis worker."
    )
    if visible_git_dirs:
        reply += f" Git metadata visible at {', '.join(visible_git_dirs)}."
    if locked_files:
        reply += f" {len(locked_files)} source file(s) cannot be opened for update by this process."
    if preferred_patch.get("exists"):
        reply += f" Hardened patch artifact exists at {preferred_patch.get('path')} ({preferred_patch.get('bytes')} bytes)."
    else:
        reply += " Hardened patch artifact is missing."
    return {
        "tool": "diagnostics.source_access",
        "executed": True,
        "status": "checked",
        "read_private_content": False,
        "changed_files": False,
        "project_root": project_root_status,
        "git": {
            "git_dir": str(git_candidates[0]),
            "git_dir_exists": bool(visible_git_dirs),
            "git_dirs": git_dirs,
            "visible_git_dirs": visible_git_dirs,
            "probe": preferred_probe,
            "probes": git_probes,
        },
        "source_files": file_checks,
        "locked_source_count": len(locked_files),
        "running_bundle": running_bundle,
        "stable_bundle": str(PROJECT_ROOT / "output" / "Jarvis.app"),
        "patch_artifact": preferred_patch,
        "patch_artifacts": patch_checks,
        "reply": reply,
    }


def _git_dir_status(path: Path) -> dict[str, Any]:
    status = _path_access_status(path)
    return {
        **status,
        "exists": bool(status.get("accessible") and path.is_dir()),
    }


def _patch_artifact_status(path: Path) -> dict[str, Any]:
    status = _path_access_status(path)
    bytes_count = 0
    if status.get("accessible"):
        try:
            bytes_count = path.stat().st_size
        except OSError:
            bytes_count = 0
    return {
        **status,
        "exists": bool(status.get("accessible") and path.is_file()),
        "bytes": bytes_count,
    }


def _source_file_access(path: Path) -> dict[str, Any]:
    status = _path_access_status(path)
    exists = False
    open_update_ok = False
    open_update_error = None
    try:
        exists = path.exists()
    except OSError:
        exists = False
    if status.get("accessible") and path.is_file():
        try:
            with path.open("r+b"):
                pass
            open_update_ok = True
        except OSError as error:
            open_update_error = str(error)
    return {
        **status,
        "exists": exists,
        "open_for_update_ok": open_update_ok,
        "open_for_update_error": open_update_error,
    }


def _git_status_probe(worktree: Path) -> dict[str, Any]:
    git = _find_executable("git")
    if not git:
        return {
            "worktree": str(worktree),
            "available": False,
            "status": "git_not_found",
            "returncode": None,
            "stdout": "",
            "stderr": "",
        }
    try:
        completed = subprocess.run(
            [git, "-C", str(worktree), "status", "--short"],
            shell=False,
            cwd="/",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "worktree": str(worktree),
            "available": True,
            "status": "probe_error",
            "returncode": None,
            "stdout": "",
            "stderr": str(error),
        }
    return {
        "worktree": str(worktree),
        "available": True,
        "status": "ok" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "stdout": _text_tail(completed.stdout, 1200),
        "stderr": _text_tail(completed.stderr, 1200),
    }


def prompt_injection_scan(text: str, source: str = "manual untrusted text") -> dict[str, Any]:
    return scan_untrusted_text(text, source=source)


def browser_open_url_plan(url: str) -> dict[str, Any]:
    return {
        "tool": "browser.open_url",
        "url": url.strip(),
        "status": "planned",
        "note": "Prototype records the plan only. The Swift shell or browser tool layer will execute later.",
        "safety_note": "Treat webpage text as untrusted; scan suspicious page instructions with safety.injection_scan before acting on them.",
    }


def quick_local_control(command: str, *, execute: bool = True) -> dict[str, Any]:
    """Handle deterministic low-latency commands without model or Codex calls."""
    text = command.strip()
    lower = text.lower()
    if _is_time_request(lower):
        now = time.localtime()
        return {
            "tool": "quick.local_control",
            "matched": True,
            "status": "completed",
            "executed": True,
            "action": "time",
            "reply": f"It is {time.strftime('%-I:%M %p', now)}.",
            "local_time_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z", now),
        }

    if _is_date_request(lower):
        now = time.localtime()
        date_human = time.strftime("%A, %B %d, %Y", now).replace(" 0", " ")
        return {
            "tool": "quick.local_control",
            "matched": True,
            "status": "completed",
            "executed": True,
            "action": "date",
            "reply": f"Today is {date_human}.",
            "local_date": time.strftime("%Y-%m-%d", now),
            "weekday": time.strftime("%A", now),
        }

    if _is_battery_status_request(lower):
        return _battery_status()

    if _is_storage_status_request(lower):
        return _storage_status()

    if _is_cancel_timer_request(lower):
        canceled = _cancel_active_timers() if execute else 0
        return {
            "tool": "quick.local_control",
            "matched": True,
            "status": "completed" if execute else "planned",
            "executed": execute,
            "action": "timer.cancel",
            "canceled_count": canceled,
            "reply": (
                f"Canceled {canceled} active timer{'s' if canceled != 1 else ''}."
                if execute
                else "Would cancel active timers."
            ),
        }

    if _is_timer_status_request(lower):
        snapshot = _active_timer_snapshot()
        return {
            "tool": "quick.local_control",
            "matched": True,
            "status": "completed",
            "executed": True,
            "action": "timer.status",
            **snapshot,
            "reply": _timer_status_reply(snapshot),
        }

    timer_seconds = _parse_timer_seconds(lower)
    if timer_seconds is not None:
        if not execute:
            return {
                "tool": "quick.local_control",
                "matched": True,
                "status": "planned",
                "executed": False,
                "action": "timer",
                "duration_seconds": timer_seconds,
                "reply": f"Would set a timer for {_human_duration(timer_seconds)}.",
            }
        timer_id = _schedule_timer(timer_seconds, text)
        return {
            "tool": "quick.local_control",
            "matched": True,
            "status": "timer_started",
            "executed": True,
            "action": "timer",
            "timer_id": timer_id,
            "duration_seconds": timer_seconds,
            "reply": f"Timer set for {_human_duration(timer_seconds)}. It will notify you if Jarvis stays open.",
        }

    media_action = _parse_media_action(lower)
    if media_action is not None:
        if not execute:
            return {
                "tool": "quick.local_control",
                "matched": True,
                "status": "planned",
                "executed": False,
                "action": f"media.{media_action}",
                "reply": "Would send a media command.",
            }
        return _run_media_control(media_action)

    speech_text = _extract_speech_text(text)
    if speech_text is not None:
        if not execute:
            return {
                "tool": "quick.local_control",
                "matched": True,
                "status": "planned",
                "executed": False,
                "action": "speech.say",
                "text_length": len(speech_text),
                "reply": "Would speak the requested text locally.",
            }
        return _run_say_text(speech_text)

    volume_target = _parse_volume_target(lower)
    if volume_target is not None:
        if not execute:
            return {
                "tool": "quick.local_control",
                "matched": True,
                "status": "planned",
                "executed": False,
                "action": "volume.set",
                "volume_percent": volume_target,
                "reply": f"Would set system volume to {volume_target}%.",
            }
        return _run_volume_set(volume_target)

    volume_delta = _parse_volume_delta(lower)
    if volume_delta is not None:
        if not execute:
            return {
                "tool": "quick.local_control",
                "matched": True,
                "status": "planned",
                "executed": False,
                "action": "volume.up" if volume_delta > 0 else "volume.down",
                "reply": "Would change system volume.",
            }
        return _run_volume_control(volume_delta)

    brightness_target = _parse_brightness_target(lower)
    if brightness_target is not None:
        if not execute:
            return {
                "tool": "quick.local_control",
                "matched": True,
                "status": "planned",
                "executed": False,
                "action": "brightness.set",
                "brightness_percent": brightness_target,
                "reply": f"Would set display brightness to {brightness_target}%.",
            }
        return _run_brightness_set(brightness_target)

    brightness_delta = _parse_brightness_delta(lower)
    if brightness_delta is not None:
        if not execute:
            return {
                "tool": "quick.local_control",
                "matched": True,
                "status": "planned",
                "executed": False,
                "action": "brightness.up" if brightness_delta > 0 else "brightness.down",
                "reply": "Would change display brightness.",
            }
        return _run_brightness_control(brightness_delta)

    return {"tool": "quick.local_control", "matched": False, "status": "unmatched", "executed": False}


def outlook_read_only_plan() -> dict[str, Any]:
    return {
        "tool": "outlook.visible_summary",
        "status": "planned",
        "steps": [
            "Open or focus Outlook.",
            "Scan recent inbox messages, including read messages.",
            "Select newest messages by received time.",
            "Summarize sender, subject, received time, and a short local snippet.",
            "Treat email content as untrusted and scan suspicious instructions with safety.injection_scan before acting on them.",
            "Ask before opening messages, downloading attachments, drafting, deleting, forwarding, or sending.",
        ],
    }


def email_backend_status() -> dict[str, Any]:
    mail_app = app_availability("Mail")
    outlook_app = app_availability("Microsoft Outlook")
    screencapture = _find_executable("screencapture")
    tesseract = _find_executable("tesseract")
    osascript = _find_executable("osascript")
    routes = [
        {
            "id": "apple_mail_applescript",
            "label": "Apple Mail metadata",
            "enabled": True,
            "available": bool(mail_app.get("available") and osascript),
            "reads_email_content_if_used": True,
            "note": "Generic email summaries try Apple Mail first when Mail and osascript are available.",
        },
        {
            "id": "outlook_applescript",
            "label": "Outlook AppleScript metadata",
            "enabled": bool(OUTLOOK_USE_APPLESCRIPT),
            "available": bool(outlook_app.get("available") and osascript),
            "reads_email_content_if_used": True,
        },
        {
            "id": "outlook_sqlite",
            "label": "Local Outlook database fallback",
            "enabled": bool(OUTLOOK_USE_LEGACY_SQLITE),
            "available": _outlook_sqlite_db_path().exists(),
            "reads_email_content_if_used": True,
        },
        {
            "id": "visible_ocr",
            "label": "Visible Outlook OCR fallback",
            "enabled": False,
            "available": bool(screencapture and tesseract),
            "reads_email_content_if_used": True,
            "note": "Disabled for normal email summaries because Leo's Outlook start view does not expose the newest email body. Use an explicit visible-screen/OCR request instead.",
        },
        {
            "id": "native_apple_vision_ocr",
            "label": "Native app Apple Vision OCR",
            "enabled": True,
            "available": None,
            "reads_email_content_if_used": True,
            "note": "This runs in the Swift app process when Leo explicitly asks for visible Outlook OCR.",
        },
    ]
    available_routes = [route["id"] for route in routes if route.get("available") is True and route.get("enabled")]
    reply = (
        "Email backend status: this diagnostic did not read email content. "
        "Jarvis tries Apple Mail metadata first for normal email summaries, "
        "then tries structured Outlook metadata or the local Outlook database. "
        "Visible Outlook OCR is only used for explicit visible-screen/OCR requests. "
    )
    if not OUTLOOK_USE_APPLESCRIPT:
        reply += "Outlook AppleScript metadata is currently disabled by JARVIS_OUTLOOK_USE_APPLESCRIPT. Apple Mail metadata can still be used when Mail and osascript are available. "
    if not OUTLOOK_USE_LEGACY_SQLITE:
        reply += "The local Outlook SQLite fallback is currently disabled by JARVIS_OUTLOOK_USE_LEGACY_SQLITE. "
    if available_routes:
        reply += f"Currently available route ids: {', '.join(available_routes)}."
    else:
        reply += "I do not see a fully available structured route from the worker right now; native visible OCR may still work from the app if Screen Recording is granted."
    return {
        "tool": "diagnostics.email",
        "executed": True,
        "status": "checked",
        "read_email_content": False,
        "selection_rule": "newest_received_any_read_state",
        "configuration": {
            "apple_mail_use_applescript": True,
            "outlook_use_applescript": OUTLOOK_USE_APPLESCRIPT,
            "outlook_use_legacy_sqlite": OUTLOOK_USE_LEGACY_SQLITE,
            "outlook_max_scan_messages": OUTLOOK_MAX_SCAN_MESSAGES,
        },
        "apps": {
            "mail": mail_app,
            "outlook": outlook_app,
        },
        "routes": routes,
        "available_route_ids": available_routes,
        "reply": reply,
    }


def outlook_visible_text_summary(
    text: str,
    *,
    limit: int = 3,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize native-app OCR text without receiving or storing a screenshot."""
    safe_limit = max(1, min(int(limit), 10))
    diagnostics = diagnostics or {}
    source = str(diagnostics.get("source") or "native_vision_ocr")
    engine = str(diagnostics.get("ocr_engine") or "apple_vision")
    capture_error = _clean_local_field(diagnostics.get("capture_error"))
    clean_text = str(text or "")[:12000]
    screen_access_preflight = bool(diagnostics.get("screen_access_preflight"))
    app_bundle_path = _clean_local_field(diagnostics.get("app_bundle_path"))
    app_executable_path = _clean_local_field(diagnostics.get("app_executable_path"))
    bundle_identifier = _clean_local_field(diagnostics.get("bundle_identifier"))
    base: dict[str, Any] = {
        "tool": "outlook.visible_summary",
        "risk": "private_read_local_only",
        "source": source,
        "ocr_engine": engine,
        "capture_process": "native_jarvis_app",
        "line_count": int(diagnostics.get("line_count") or 0),
        "capture_width": int(diagnostics.get("capture_width") or 0),
        "capture_height": int(diagnostics.get("capture_height") or 0),
        "screen_access_preflight": screen_access_preflight,
        "text_length": len(clean_text),
        "messages": [],
        "audit_note": "Audit stores status and counts only; native OCR text and message snippets are omitted from audit details.",
        "safety_note": "Read-only summary only. Screenshots are not sent to the worker or stored by default.",
    }
    if app_bundle_path:
        base["app_bundle_path"] = app_bundle_path
    if app_executable_path:
        base["app_executable_path"] = app_executable_path
    if bundle_identifier:
        base["bundle_identifier"] = bundle_identifier
    if capture_error:
        return {
            **base,
            "status": "native_capture_failed",
            "reply": "Jarvis tried native screenshot and Apple Vision OCR, but the native capture step failed.",
            "error": capture_error,
            "next_steps": [
                "Confirm the stable Jarvis app has Screen Recording permission, then quit and reopen Jarvis.",
                "Bring the Outlook inbox to the front and try Email again.",
            ],
        }
    if not clean_text.strip():
        return {
            **base,
            "status": "native_ocr_empty",
            "reply": "Jarvis captured the screen natively, but Apple Vision OCR did not return readable text.",
            "next_steps": ["Bring the Outlook inbox list to the front and try again."],
        }

    lines = _ocr_email_lines(clean_text, limit=safe_limit)
    if not lines:
        return {
            **base,
            "status": "ocr_empty",
            "reply": "Jarvis ran native Apple Vision OCR, but did not find readable inbox lines.",
            "next_steps": ["Bring the Outlook inbox list to the front and try again."],
        }

    snippet = " | ".join(lines)
    messages = [
        {
            "sender": "Visible Outlook window",
            "subject": "Native Apple Vision OCR",
            "received": "",
            "read_state": "visible",
            "snippet": snippet[:700],
            "source": source,
        }
    ]
    return {
        **base,
        "status": "checked",
        "inbox_count": len(lines),
        "scanned_count": len(lines),
        "message_count": 1,
        "messages": messages,
        "injection_scan": _messages_injection_scan(messages, source),
        "reply": "I read the visible Outlook window with native Apple Vision OCR inside the Jarvis app. This summarizes visible screen text, not a guaranteed full inbox scan.",
    }


def outlook_read_only_check(limit: int = 3) -> dict[str, Any]:
    """Try a bounded read-only newest-inbox summary, preferring Apple Mail."""
    safe_limit = max(1, min(int(limit), 10))
    scan_limit = max(safe_limit, OUTLOOK_MAX_SCAN_MESSAGES)
    app = app_availability("Microsoft Outlook")
    mail_app = app_availability("Mail")
    osascript = _find_executable("osascript")
    base: dict[str, Any] = {
        "tool": "outlook.visible_summary",
        "risk": "private_read_local_only",
        "limit": safe_limit,
        "scan_limit": scan_limit,
        "app": app,
        "mail_app": mail_app,
        "osascript": osascript,
        "applescript_enabled": OUTLOOK_USE_APPLESCRIPT,
        "legacy_sqlite_enabled": OUTLOOK_USE_LEGACY_SQLITE,
        "visible_ocr_for_generic_email": False,
        "messages": [],
        "selection_rule": "newest_received_any_read_state",
        "audit_note": "Audit stores status and counts only; sender, subject, and snippet details are omitted from audit details.",
        "safety_note": "Read-only summary only. Attachments, drafts, deletes, forwards, sends, downloads, and exports require confirmation.",
    }
    mail_result = _apple_mail_messages(safe_limit, scan_limit, osascript) if mail_app["available"] else {"messages": [], "status": "not_found"}
    if mail_result["messages"]:
        newest = mail_result["messages"][0]
        injection_scan = _messages_injection_scan(mail_result["messages"], "apple_mail")
        return {
            **base,
            "status": "checked",
            "reply": (
                "I checked Apple Mail and selected the newest inbox email I could read, including read messages. "
                f"Newest: {newest['sender']}: {newest['subject']}."
            ),
            "inbox_count": mail_result["inbox_count"],
            "scanned_count": mail_result["scanned_count"],
            "messages": mail_result["messages"],
            "message_count": len(mail_result["messages"]),
            "source": "apple_mail",
            "mail_status": mail_result.get("status", "checked"),
            "injection_scan": injection_scan,
            "prototype_behavior": "Reads sender, subject, received time, read state, and a short body snippet locally; it does not read attachments or send content to a model.",
        }
    base["mail_status"] = mail_result.get("status")
    if mail_result.get("error"):
        base["mail_error"] = mail_result.get("error")

    if not app["available"]:
        return {
            **base,
            "status": "outlook_not_found",
            "reply": "I could not read Apple Mail and could not find Microsoft Outlook in the standard Applications folders.",
            "next_steps": [
                "If macOS asks for Automation permission, allow Jarvis or Terminal to control Mail.",
                "Install Outlook or use `app Microsoft Outlook` to check the app path.",
            ],
        }
    if OUTLOOK_USE_APPLESCRIPT and not osascript:
        return {
            **base,
            "status": "osascript_not_found",
            "reply": "I found Outlook, but macOS AppleScript tooling is unavailable.",
            "next_steps": ["Install or repair macOS command line tooling before enabling Outlook automation."],
        }

    completed = None
    outlook_script_failure: dict[str, Any] | None = None
    if OUTLOOK_USE_APPLESCRIPT and osascript:
        script = _outlook_newest_applescript(safe_limit, scan_limit)
        try:
            completed = subprocess.run(
                [osascript, "-e", script],
                shell=False,
                cwd=PROJECT_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=OUTLOOK_APPLESCRIPT_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            completed = None
        except OSError as error:
            return {
                **base,
                "status": "automation_error",
                "reply": "I could not start the Outlook automation check.",
                "error": str(error),
                "next_steps": ["Open Outlook manually, then try the email command again."],
            }

        if completed is not None and completed.returncode != 0:
            error_text = _text_tail(completed.stderr or completed.stdout, 1800)
            outlook_script_failure = {
                "status": "needs_permission_or_scripting",
                "returncode": completed.returncode,
                "error": error_text,
            }
            base["outlook_applescript_status"] = outlook_script_failure["status"]
            base["outlook_applescript_returncode"] = completed.returncode
            base["outlook_applescript_error"] = error_text
            completed = None

    parsed = _parse_outlook_newest_output(completed.stdout if completed is not None else "")
    scanned_count = parsed["scanned_count"]
    inbox_count = parsed["inbox_count"]
    messages = parsed["messages"]
    source = "applescript"
    if not messages:
        sqlite_result = (
            _outlook_sqlite_messages(safe_limit)
            if OUTLOOK_USE_LEGACY_SQLITE
            else {"messages": [], "inbox_count": 0, "scanned_count": 0, "status": "disabled"}
        )
        if sqlite_result["messages"]:
            messages = sqlite_result["messages"]
            scanned_count = sqlite_result["scanned_count"]
            inbox_count = sqlite_result["inbox_count"]
            source = "sqlite"
        else:
            base["outlook_sqlite_status"] = sqlite_result.get("status")
            if sqlite_result.get("reply"):
                base["outlook_sqlite_note"] = sqlite_result.get("reply")
            base["visible_ocr_status"] = "skipped_for_generic_email"

    if not messages:
        mail_failed = mail_result.get("status") in {"needs_permission_or_scripting", "timeout", "automation_error", "osascript_not_found"}
        if outlook_script_failure:
            return {
                **base,
                "status": outlook_script_failure["status"],
                "reply": "I could not read Apple Mail or Outlook inbox metadata yet. Outlook AppleScript was blocked, and the local Outlook database did not find messages. I did not use visible Outlook OCR for this normal email request because your Outlook start view does not expose the newest email body.",
                "inbox_count": inbox_count,
                "scanned_count": scanned_count,
                "messages": [],
                "message_count": 0,
                "source": "fallback_failed",
                "next_steps": [
                    "Use Apple Mail for the normal email route, or grant Automation permission if macOS asks Jarvis to control Mail.",
                    "If macOS asks for Automation permission, allow Jarvis or Terminal to control Microsoft Outlook.",
                    "If you specifically want screen reading, ask: read the visible Outlook screen with OCR.",
                ],
            }
        if mail_failed or sqlite_result.get("status") == "disabled":
            return {
                **base,
                "status": mail_result.get("status") if mail_failed else "no_structured_email_route",
                "reply": "I could not read Apple Mail inbox metadata yet, and the structured Outlook fallback did not return messages. I did not use visible Outlook OCR for this normal email request because your Outlook start view does not expose the newest email body.",
                "inbox_count": inbox_count,
                "scanned_count": scanned_count,
                "messages": [],
                "message_count": 0,
                "source": "fallback_failed",
                "next_steps": [
                    "Allow Jarvis to control Mail if macOS shows an Automation prompt.",
                    "If no prompt appears, quit and reopen Jarvis, then try the email command again.",
                    "If you specifically want screen reading, ask: read the visible Outlook screen with OCR.",
                ],
            }
        reply = "I could not read Apple Mail or structured Outlook inbox messages yet. I skipped visible Outlook OCR for this normal email request because Outlook's start view does not show the newest email body."
    elif source == "screen_ocr":
        reply = "I read the visible Outlook window locally with OCR. This fallback summarizes visible screen text rather than a guaranteed full inbox scan."
    else:
        newest = messages[0]
        reply = (
            "I checked Outlook and selected the newest inbox email I could read, including read messages. "
            f"Newest: {newest['sender']}: {newest['subject']}."
        )

    return {
        **base,
        "status": "checked",
        "reply": reply,
        "inbox_count": inbox_count,
        "scanned_count": scanned_count,
        "messages": messages,
        "message_count": len(messages),
        "source": source,
        "injection_scan": _messages_injection_scan(messages, source),
        "prototype_behavior": "Reads sender, subject, received time, read state, and a short body snippet locally; it does not read attachments or send content to a model.",
    }


def _email_failure_reply(applescript_failure: dict[str, Any] | None, fallback_result: dict[str, Any]) -> str:
    fallback_reply = fallback_result.get("reply") or "None of the local read routes could see inbox messages yet."
    if not applescript_failure:
        return str(fallback_reply)
    return (
        "Outlook AppleScript could not read inbox metadata, and the fallback route also failed. "
        f"Fallback: {fallback_reply}"
    )


def _messages_injection_scan(messages: list[dict[str, Any]], source: str) -> dict[str, Any]:
    lines: list[str] = []
    for message in messages:
        sender = str(message.get("sender") or "")
        subject = str(message.get("subject") or "")
        snippet = str(message.get("snippet") or "")
        lines.append(f"Sender: {sender}\nSubject: {subject}\nSnippet: {snippet}")
    return scan_untrusted_text("\n\n".join(lines), source=f"{source} email preview")


def codex_delegate_plan(prompt: str, project_dir: str | None = None, model: str | None = None) -> dict[str, Any]:
    codex_path = _find_executable("codex")
    workdir = str(_safe_root(project_dir))
    selected_model = (model or DEFAULT_CODEX_MODEL).strip() or DEFAULT_CODEX_MODEL
    delegated_prompt = _codex_fast_prompt(prompt)
    command = [
        codex_path or "codex",
        "--model",
        selected_model,
        "-c",
        f"model_reasoning_effort={DEFAULT_CODEX_REASONING_EFFORT}",
        "--sandbox",
        "read-only",
        "--ask-for-approval",
        "never",
        "exec",
        "--cd",
        workdir,
        "--skip-git-repo-check",
        "--ephemeral",
        delegated_prompt,
    ]
    return {
        "tool": "codex.delegate",
        "available": bool(codex_path),
        "codex_path": codex_path,
        "model": selected_model,
        "timeout_seconds": CODEX_TIMEOUT_SECONDS,
        "sandbox": "read-only",
        "reasoning_effort": DEFAULT_CODEX_REASONING_EFFORT,
        "planned_command": command,
        "status": "dry_run",
        "note": "Codex CLI execution sends the prompt and any files it chooses to read to the configured model. This route uses a read-only sandbox.",
    }


def run_codex_chat(prompt: str, project_dir: str | None = None, model: str | None = None) -> dict[str, Any]:
    codex_path = _find_executable("codex")
    selected_model = (model or DEFAULT_CODEX_MODEL).strip() or DEFAULT_CODEX_MODEL
    workdir = str(_safe_root(project_dir))
    local_reply = _local_conversation_reply(prompt)
    if not codex_path:
        return {
            "tool": "conversation.codex",
            "available": False,
            "status": "codex_not_found",
            "executed": False,
            "fallback_used": True,
            "duration_seconds": 0.0,
            "duration_human": "0.0s",
            "reply": local_reply,
        }

    started_at = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="jarvis-chat-") as temp_dir:
        output_path = Path(temp_dir) / "last-message.txt"
        command = [
            codex_path,
            "--model",
            selected_model,
            "-c",
            f"model_reasoning_effort={DEFAULT_CODEX_REASONING_EFFORT}",
            "--sandbox",
            "read-only",
            "--ask-for-approval",
            "never",
            "exec",
            "--cd",
            workdir,
            "--skip-git-repo-check",
            "--ephemeral",
            "--output-last-message",
            str(output_path),
            _codex_chat_prompt(prompt),
        ]
        try:
            completed = subprocess.run(
                command,
                shell=False,
                cwd=workdir,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=CODEX_CHAT_TIMEOUT_SECONDS,
                check=False,
            )
            last_message = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
        except subprocess.TimeoutExpired:
            duration = _duration_fields(started_at)
            return {
                "tool": "conversation.codex",
                "available": True,
                "status": "timeout",
                "executed": True,
                "fallback_used": True,
                "model": selected_model,
                "timeout_seconds": CODEX_CHAT_TIMEOUT_SECONDS,
                **duration,
                "reply": local_reply,
            }
        except OSError as error:
            duration = _duration_fields(started_at)
            return {
                "tool": "conversation.codex",
                "available": True,
                "status": "execution_error",
                "executed": False,
                "fallback_used": True,
                "model": selected_model,
                "error": str(error),
                **duration,
                "reply": local_reply,
            }

    duration = _duration_fields(started_at)
    stdout = _text_tail(completed.stdout, 4000)
    stderr = _text_tail(completed.stderr, 1500)
    if completed.returncode == 0:
        reply = (last_message or stdout).strip()
        return {
            "tool": "conversation.codex",
            "available": True,
            "status": "completed",
            "executed": True,
            "fallback_used": False,
            "model": selected_model,
            **duration,
            "reply": reply[-1800:] if reply else local_reply,
        }
    return {
        "tool": "conversation.codex",
        "available": True,
        "status": "failed",
        "executed": True,
        "fallback_used": True,
        "model": selected_model,
        "stderr": stderr,
        **duration,
        "reply": local_reply,
    }


def run_fast_local_chat(prompt: str, project_dir: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Answer casual conversation through a tiny local model with a hard timeout."""
    if FAST_MODEL_BACKEND == "groq":
        primary = _run_groq_fast_chat(prompt, model=model)
        if _fast_chat_completed(primary):
            return primary
        return _fast_chat_with_fallback(prompt, primary)

    selected_model = (model or FAST_MODEL_NAME).strip() or FAST_MODEL_NAME
    started_at = time.monotonic()
    if FAST_MODEL_BACKEND != "ollama":
        primary = {
            "tool": "conversation.fast_local",
            "backend": FAST_MODEL_BACKEND,
            "model": selected_model,
            "available": False,
            "status": "backend_unavailable",
            "executed": False,
            "fallback_used": True,
            "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
            **_duration_fields(started_at),
            "reply": _fast_model_unavailable_reply(prompt),
        }
        return _fast_chat_with_fallback(prompt, primary)
    return _run_ollama_fast_chat(prompt, model=model)


def _run_ollama_fast_chat(prompt: str, model: str | None = None) -> dict[str, Any]:
    selected_model = (model or FAST_MODEL_NAME).strip() or FAST_MODEL_NAME
    ollama_path = _find_executable("ollama")
    started_at = time.monotonic()
    if not ollama_path:
        return {
            "tool": "conversation.fast_local",
            "backend": "ollama",
            "model": selected_model,
            "available": False,
            "status": "ollama_not_found",
            "executed": False,
            "fallback_used": True,
            "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
            **_duration_fields(started_at),
            "reply": _fast_model_unavailable_reply(prompt),
        }

    payload = {
        "model": selected_model,
        "prompt": _fast_local_prompt(prompt),
        "stream": False,
        "think": False,
        "options": {
            "num_predict": FAST_MODEL_MAX_TOKENS,
            "temperature": 0.4,
            "top_p": 0.9,
        },
    }
    request = urllib.request.Request(
        f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=FAST_MODEL_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except TimeoutError:
        duration = _duration_fields(started_at)
        return {
            "tool": "conversation.fast_local",
            "backend": "ollama",
            "model": selected_model,
            "available": True,
            "status": "timeout",
            "executed": True,
            "fallback_used": True,
            "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
            **duration,
            "reply": _fast_model_timeout_reply(selected_model, duration["duration_human"]),
        }
    except urllib.error.URLError as error:
        duration = _duration_fields(started_at)
        return {
            "tool": "conversation.fast_local",
            "backend": "ollama",
            "model": selected_model,
            "available": True,
            "status": "ollama_error",
            "executed": False,
            "fallback_used": True,
            "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
            "error": str(error.reason if hasattr(error, "reason") else error),
            **duration,
            "reply": _fast_model_unavailable_reply(prompt),
        }
    except OSError as error:
        duration = _duration_fields(started_at)
        return {
            "tool": "conversation.fast_local",
            "backend": "ollama",
            "model": selected_model,
            "available": True,
            "status": "execution_error",
            "executed": False,
            "fallback_used": True,
            "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
            "error": str(error),
            **duration,
            "reply": _fast_model_unavailable_reply(prompt),
        }

    duration = _duration_fields(started_at)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}
    reply = _strip_think_blocks(str(data.get("response") or "")).strip()
    if not reply:
        return {
            "tool": "conversation.fast_local",
            "backend": "ollama",
            "model": selected_model,
            "available": True,
            "status": "empty_response",
            "executed": True,
            "fallback_used": True,
            "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
            **duration,
            "reply": _fast_model_unavailable_reply(prompt),
        }
    reply = reply[-1200:]
    return {
        "tool": "conversation.fast_local",
        "backend": "ollama",
        "model": selected_model,
        "available": True,
        "status": "completed",
        "executed": True,
        "fallback_used": False,
        "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
        **duration,
        "reply": reply,
    }


def _fast_chat_completed(result: dict[str, Any]) -> bool:
    return result.get("status") == "completed" and bool(str(result.get("reply") or "").strip())


def _fast_chat_with_fallback(prompt: str, primary: dict[str, Any]) -> dict[str, Any]:
    if not FAST_MODEL_FALLBACK_ENABLED:
        return primary
    if FAST_MODEL_FALLBACK_BACKEND != "ollama":
        return primary
    if primary.get("backend") == "ollama":
        return primary
    if not _find_executable("ollama"):
        return primary

    fallback = _run_ollama_fast_chat(prompt)
    primary_summary = {
        "backend": primary.get("backend"),
        "model": primary.get("model"),
        "status": primary.get("status"),
        "duration_human": primary.get("duration_human"),
    }
    if _fast_chat_completed(fallback):
        fallback["fallback_used"] = True
        fallback["primary_backend"] = primary.get("backend")
        fallback["primary_model"] = primary.get("model")
        fallback["primary_status"] = primary.get("status")
        fallback["fallback_backend"] = "ollama"
        return fallback

    primary["fallback_attempt"] = {
        "backend": fallback.get("backend"),
        "model": fallback.get("model"),
        "status": fallback.get("status"),
        "duration_human": fallback.get("duration_human"),
    }
    primary["primary_result"] = primary_summary
    return primary


def _run_groq_fast_chat(prompt: str, model: str | None = None) -> dict[str, Any]:
    selected_model = (model or GROQ_FAST_MODEL).strip() or GROQ_FAST_MODEL
    started_at = time.monotonic()
    if not GROQ_API_KEY:
        return {
            "tool": "conversation.fast_local",
            "backend": "groq",
            "model": selected_model,
            "available": False,
            "status": "groq_key_missing",
            "executed": False,
            "fallback_used": True,
            "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
            **_duration_fields(started_at),
            "reply": "Groq fast chat is selected, but GROQ_API_KEY is not configured.",
        }

    payload = {
        "model": selected_model,
        "messages": [
            {
                "role": "system",
                "content": _fast_chat_system_prompt(),
            },
            {"role": "user", "content": prompt.strip()},
        ],
        "temperature": 0.4,
        "max_completion_tokens": FAST_MODEL_MAX_TOKENS,
        "stream": False,
    }
    request = urllib.request.Request(
        f"{GROQ_BASE_URL.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Jarvis/0.1 local-mac-assistant",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=FAST_MODEL_TIMEOUT_SECONDS, context=_https_context()) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except TimeoutError:
        duration = _duration_fields(started_at)
        return {
            "tool": "conversation.fast_local",
            "backend": "groq",
            "model": selected_model,
            "available": True,
            "status": "timeout",
            "executed": True,
            "fallback_used": True,
            "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
            **duration,
            "reply": _fast_model_timeout_reply(selected_model, duration["duration_human"]),
        }
    except urllib.error.HTTPError as error:
        body = _text_tail(error.read(), 1200)
        duration = _duration_fields(started_at)
        return {
            "tool": "conversation.fast_local",
            "backend": "groq",
            "model": selected_model,
            "available": True,
            "status": "http_error",
            "executed": True,
            "fallback_used": True,
            "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
            "http_status": error.code,
            "error": body,
            **duration,
            "reply": "Groq fast chat returned an HTTP error.",
        }
    except urllib.error.URLError as error:
        duration = _duration_fields(started_at)
        return {
            "tool": "conversation.fast_local",
            "backend": "groq",
            "model": selected_model,
            "available": True,
            "status": "network_error",
            "executed": False,
            "fallback_used": True,
            "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
            "error": str(error.reason if hasattr(error, "reason") else error),
            **duration,
            "reply": "Groq fast chat could not be reached.",
        }
    except OSError as error:
        duration = _duration_fields(started_at)
        return {
            "tool": "conversation.fast_local",
            "backend": "groq",
            "model": selected_model,
            "available": True,
            "status": "execution_error",
            "executed": False,
            "fallback_used": True,
            "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
            "error": str(error),
            **duration,
            "reply": "Groq fast chat failed before returning an answer.",
        }

    duration = _duration_fields(started_at)
    try:
        data = json.loads(raw)
        reply = str(data["choices"][0]["message"].get("content") or "").strip()
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        reply = ""
    if not reply:
        return {
            "tool": "conversation.fast_local",
            "backend": "groq",
            "model": selected_model,
            "available": True,
            "status": "empty_response",
            "executed": True,
            "fallback_used": True,
            "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
            **duration,
            "reply": "Groq fast chat returned an empty answer.",
        }
    return {
        "tool": "conversation.fast_local",
        "backend": "groq",
        "model": selected_model,
        "available": True,
        "status": "completed",
        "executed": True,
        "fallback_used": False,
        "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
        **duration,
        "reply": reply[-1200:],
    }


def stream_fast_local_chat_events(prompt: str, model: str | None = None):
    """Yield SSE-friendly fast-chat events. Falls back to one final event when streaming is unavailable."""
    if FAST_MODEL_BACKEND != "groq":
        yield {"event": "final_result", "data": run_fast_local_chat(prompt, model=model)}
        return

    selected_model = (model or GROQ_FAST_MODEL).strip() or GROQ_FAST_MODEL
    started_at = time.monotonic()
    if not GROQ_API_KEY:
        result = {
            "tool": "conversation.fast_local",
            "backend": "groq",
            "model": selected_model,
            "available": False,
            "status": "groq_key_missing",
            "executed": False,
            "fallback_used": True,
            "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
            **_duration_fields(started_at),
            "reply": "Groq fast chat is selected, but GROQ_API_KEY is not configured.",
        }
        yield {"event": "final_result", "data": _fast_chat_with_fallback(prompt, result)}
        return

    payload = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": _fast_chat_system_prompt()},
            {"role": "user", "content": prompt.strip()},
        ],
        "temperature": 0.4,
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
    yield {
        "event": "meta",
        "data": {
            "tool": "conversation.fast_local",
            "backend": "groq",
            "model": selected_model,
            "streaming": True,
        },
    }

    chunks: list[str] = []
    first_visible_token_at: float | None = None
    try:
        with urllib.request.urlopen(request, timeout=FAST_MODEL_TIMEOUT_SECONDS, context=_https_context()) as response:
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
                if not content:
                    continue
                if first_visible_token_at is None:
                    first_visible_token_at = time.monotonic()
                chunks.append(content)
                yield {"event": "delta", "data": {"text": content}}
    except TimeoutError:
        duration = _duration_fields(started_at)
        result = {
            "tool": "conversation.fast_local",
            "backend": "groq",
            "model": selected_model,
            "available": True,
            "status": "timeout",
            "executed": True,
            "fallback_used": True,
            "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
            **duration,
            "reply": _fast_model_timeout_reply(selected_model, duration["duration_human"]),
        }
        yield {"event": "final_result", "data": _fast_chat_with_fallback(prompt, result)}
        return
    except urllib.error.HTTPError as error:
        body = _text_tail(error.read(), 1200)
        duration = _duration_fields(started_at)
        result = {
            "tool": "conversation.fast_local",
            "backend": "groq",
            "model": selected_model,
            "available": True,
            "status": "http_error",
            "executed": True,
            "fallback_used": True,
            "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
            "http_status": error.code,
            "error": body,
            **duration,
            "reply": "Groq fast chat returned an HTTP error.",
        }
        yield {"event": "final_result", "data": _fast_chat_with_fallback(prompt, result)}
        return
    except (urllib.error.URLError, OSError) as error:
        duration = _duration_fields(started_at)
        reason = getattr(error, "reason", error)
        result = {
            "tool": "conversation.fast_local",
            "backend": "groq",
            "model": selected_model,
            "available": True,
            "status": "network_error",
            "executed": False,
            "fallback_used": True,
            "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
            "error": str(reason),
            **duration,
            "reply": "Groq fast chat could not be reached.",
        }
        yield {"event": "final_result", "data": _fast_chat_with_fallback(prompt, result)}
        return

    duration = _duration_fields(started_at)
    reply = "".join(chunks).strip()
    if not reply:
        result = {
            "tool": "conversation.fast_local",
            "backend": "groq",
            "model": selected_model,
            "available": True,
            "status": "empty_response",
            "executed": True,
            "fallback_used": True,
            "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
            **duration,
            "reply": "Groq fast chat returned an empty answer.",
        }
        yield {"event": "final_result", "data": _fast_chat_with_fallback(prompt, result)}
        return

    result = {
        "tool": "conversation.fast_local",
        "backend": "groq",
        "model": selected_model,
        "available": True,
        "status": "completed",
        "executed": True,
        "fallback_used": False,
        "timeout_seconds": FAST_MODEL_TIMEOUT_SECONDS,
        "first_visible_token_seconds": round(first_visible_token_at - started_at, 3) if first_visible_token_at else None,
        "first_token_seconds": round(first_visible_token_at - started_at, 3) if first_visible_token_at else None,
        **duration,
        "reply": reply[-1200:],
    }
    yield {"event": "final_result", "data": result}


def _fast_chat_system_prompt() -> str:
    return (
        "You are Jarvis, Leo's local Mac assistant prototype. "
        "Leo is the user's real name for profile context, but do not address him as Leo, Sir, or by any title unless he explicitly asks. "
        "Answer directly and briefly unless he asks for more. "
        "Follow Leo's requested output format, including exact text or bullet counts. "
        "Be useful and natural. Do not claim you performed computer actions. "
        "Do not invent schedule, email, weather, app, file, or system facts. "
        "For a simple greeting, only say hello and ask what he wants done. "
        "For jokes, give one short joke directly without unrelated follow-up text. "
        "Do not mention that you are a language model. Do not use emojis."
    )


def _https_context() -> ssl.SSLContext:
    default_paths = ssl.get_default_verify_paths()
    if default_paths.cafile:
        return ssl.create_default_context()
    system_cafile = Path("/etc/ssl/cert.pem")
    if system_cafile.exists():
        return ssl.create_default_context(cafile=str(system_cafile))
    return ssl.create_default_context()


def run_codex_delegate(prompt: str, project_dir: str | None = None, model: str | None = None) -> dict[str, Any]:
    plan = codex_delegate_plan(_clean_codex_prompt(prompt), project_dir=project_dir, model=model)
    if not plan["available"]:
        return {
            **plan,
            "status": "codex_not_found",
            "executed": False,
            "duration_seconds": 0.0,
            "duration_human": "0.0s",
            "reply": "Codex CLI is not available on this machine.",
        }
    started_at = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="jarvis-codex-") as temp_dir:
        output_path = Path(temp_dir) / "last-message.txt"
        command = [
            *plan["planned_command"][:-1],
            "--output-last-message",
            str(output_path),
            plan["planned_command"][-1],
        ]
        try:
            completed = subprocess.run(
                command,
                shell=False,
                cwd=plan["planned_command"][plan["planned_command"].index("--cd") + 1],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=CODEX_TIMEOUT_SECONDS,
                check=False,
            )
            last_message = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
        except subprocess.TimeoutExpired as error:
            duration = _duration_fields(started_at)
            return {
                **plan,
                "status": "timeout",
                "executed": True,
                "stdout": _text_tail(error.stdout, 4000),
                "stderr": _text_tail(error.stderr, 2000),
                **duration,
                "reply": f"Codex CLI timed out after {CODEX_TIMEOUT_SECONDS} seconds using {plan['model']}.",
            }
        except OSError as error:
            duration = _duration_fields(started_at)
            return {
                **plan,
                "status": "execution_error",
                "executed": False,
                "error": str(error),
                **duration,
                "reply": f"I could not start Codex CLI: {error}",
            }

    duration = _duration_fields(started_at)
    stdout = _text_tail(completed.stdout, 8000)
    stderr = _text_tail(completed.stderr, 3000)
    return {
        **plan,
        "status": "completed" if completed.returncode == 0 else "failed",
        "executed": True,
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
        **duration,
        "reply": _codex_reply(stdout, stderr, completed.returncode, plan["model"], last_message=last_message),
    }


def start_codex_delegate_job(prompt: str, project_dir: str | None = None, model: str | None = None) -> dict[str, Any]:
    cleaned = _clean_codex_prompt(prompt)
    plan = codex_delegate_plan(cleaned, project_dir=project_dir, model=model)
    if not plan["available"]:
        return {
            "tool": "codex.job",
            "status": "codex_not_found",
            "executed": False,
            "available": False,
            "reply": "Codex CLI is not available on this machine.",
        }

    job_id = f"codex-{uuid.uuid4().hex[:8]}"
    job = {
        "tool": "codex.job",
        "job_id": job_id,
        "status": "running",
        "model": plan["model"],
        "started_at": time.time(),
        "prompt_summary": _rough_understanding(cleaned),
    }
    with CODEX_JOBS_LOCK:
        _ensure_codex_jobs_loaded_unlocked()
        CODEX_JOBS[job_id] = job
        _persist_codex_jobs_unlocked()
    thread = threading.Thread(
        target=_codex_delegate_job_worker,
        args=(job_id, cleaned, project_dir, model),
        daemon=True,
    )
    thread.start()
    return {
        **job,
        "available": True,
        "executed": True,
        "reply": f"I started Codex job {job_id}. Ask `codex job {job_id}` for the result.",
    }


def codex_job_status(job_id: str | None = None) -> dict[str, Any]:
    with CODEX_JOBS_LOCK:
        _ensure_codex_jobs_loaded_unlocked()
        if job_id:
            job = dict(CODEX_JOBS.get(job_id, {}))
        else:
            jobs = [dict(value) for value in CODEX_JOBS.values()]

    if job_id:
        if not job:
            return {
                "tool": "codex.job",
                "status": "not_found",
                "executed": False,
                "job_id": job_id,
                "reply": f"I do not have a Codex job named {job_id}.",
            }
        return {
            "tool": "codex.job",
            "status": job.get("status", "unknown"),
            "executed": False,
            "job": job,
            "reply": _codex_job_reply(job),
        }

    recent_jobs = sorted(jobs, key=lambda item: float(item.get("started_at") or 0), reverse=True)[:10]
    return {
        "tool": "codex.job",
        "status": "listed",
        "executed": False,
        "jobs": recent_jobs,
        "reply": f"{len(recent_jobs)} Codex job{'s' if len(recent_jobs) != 1 else ''} tracked.",
    }


def codex_speed_status() -> dict[str, Any]:
    with CODEX_JOBS_LOCK:
        _ensure_codex_jobs_loaded_unlocked()
        jobs = [dict(value) for value in CODEX_JOBS.values()]
    recent_jobs = sorted(jobs, key=lambda item: float(item.get("started_at") or 0), reverse=True)[:10]
    completed = [
        job
        for job in jobs
        if job.get("status") == "completed" and _float_or_none(job.get("duration_seconds")) is not None
    ]
    durations = [float(job["duration_seconds"]) for job in completed]
    running_count = sum(1 for job in jobs if job.get("status") == "running")
    interrupted_count = sum(1 for job in jobs if job.get("status") == "interrupted")
    latest = recent_jobs[0] if recent_jobs else None
    average = sum(durations) / len(durations) if durations else None
    fastest = min(durations) if durations else None
    slowest = max(durations) if durations else None
    if durations:
        timing_text = (
            f"{len(durations)} completed Codex job timings tracked; "
            f"average {_format_seconds(average or 0)}, fastest {_format_seconds(fastest or 0)}, slowest {_format_seconds(slowest or 0)}"
        )
    else:
        timing_text = "No completed Codex job timings are tracked yet"
    latest_text = ""
    if latest:
        latest_id = latest.get("job_id") or "unknown"
        latest_status = latest.get("status") or "unknown"
        latest_duration = latest.get("duration_human") or (
            _format_seconds(float(latest["duration_seconds"])) if _float_or_none(latest.get("duration_seconds")) is not None else "not finished"
        )
        latest_text = f" Latest job {latest_id} is {latest_status}, duration {latest_duration}."
    reply = (
        f"Codex speed status: {timing_text}; {running_count} running, {interrupted_count} interrupted."
        f"{latest_text} Normal chat should not wait for Codex; broad Codex work runs asynchronously."
    )
    return {
        "tool": "diagnostics.codex_speed",
        "executed": True,
        "status": "checked",
        "read_private_content": False,
        "tracked_count": len(jobs),
        "running_count": running_count,
        "interrupted_count": interrupted_count,
        "completed_timing_count": len(durations),
        "average_duration_seconds": round(average, 3) if average is not None else None,
        "fastest_duration_seconds": round(fastest, 3) if fastest is not None else None,
        "slowest_duration_seconds": round(slowest, 3) if slowest is not None else None,
        "latest_job": latest,
        "recent_jobs": recent_jobs,
        "reply": reply,
    }


def _codex_delegate_job_worker(job_id: str, prompt: str, project_dir: str | None, model: str | None) -> None:
    result = run_codex_delegate(prompt, project_dir=project_dir, model=model)
    completed_at = time.time()
    with CODEX_JOBS_LOCK:
        job = CODEX_JOBS.get(job_id)
        if not job:
            return
        job["status"] = "completed" if result.get("status") == "completed" else str(result.get("status") or "failed")
        job["completed_at"] = completed_at
        job["duration_human"] = result.get("duration_human")
        job["duration_seconds"] = result.get("duration_seconds")
        job["returncode"] = result.get("returncode")
        job["reply"] = result.get("reply")
        _persist_codex_jobs_unlocked()


def _codex_job_reply(job: dict[str, Any]) -> str:
    status = str(job.get("status") or "unknown")
    job_id = str(job.get("job_id") or "unknown")
    if status == "running":
        return f"Codex job {job_id} is still running."
    if status == "interrupted":
        return f"Codex job {job_id} was interrupted because the worker restarted before it finished."
    reply = str(job.get("reply") or "").strip()
    if reply:
        return reply
    return f"Codex job {job_id} finished with status {status}."


def _ensure_codex_jobs_loaded_unlocked() -> None:
    global CODEX_JOBS_LOADED
    if CODEX_JOBS_LOADED:
        return
    CODEX_JOBS_LOADED = True
    try:
        data = json.loads(CODEX_JOB_STORE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    raw_jobs = data.get("jobs", [])
    if not isinstance(raw_jobs, list):
        return
    changed = False
    for raw_job in raw_jobs:
        if not isinstance(raw_job, dict):
            continue
        job = _codex_job_persistable(raw_job)
        job_id = str(job.get("job_id") or "")
        if not job_id:
            continue
        if job.get("status") == "running":
            job["status"] = "interrupted"
            job["completed_at"] = time.time()
            job["reply"] = _codex_job_reply(job)
            changed = True
        CODEX_JOBS.setdefault(job_id, job)
    if changed:
        _persist_codex_jobs_unlocked()


def _persist_codex_jobs_unlocked() -> None:
    jobs = sorted(
        (_codex_job_persistable(job) for job in CODEX_JOBS.values()),
        key=lambda item: float(item.get("started_at") or 0),
        reverse=True,
    )[:MAX_PERSISTED_CODEX_JOBS]
    payload = {
        "schema": "jarvis.codex_jobs.v1",
        "updated_at": time.time(),
        "max_jobs": MAX_PERSISTED_CODEX_JOBS,
        "jobs": jobs,
    }
    try:
        CODEX_JOB_STORE.parent.mkdir(parents=True, exist_ok=True)
        temp_path = CODEX_JOB_STORE.with_suffix(".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        temp_path.replace(CODEX_JOB_STORE)
    except OSError:
        return


def _codex_job_persistable(job: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "tool",
        "job_id",
        "status",
        "model",
        "prompt_summary",
        "started_at",
        "completed_at",
        "duration_human",
        "duration_seconds",
        "returncode",
        "reply",
        "error",
    }
    clean = {key: job[key] for key in allowed_keys if key in job}
    clean.setdefault("tool", "codex.job")
    if "prompt_summary" in clean:
        clean["prompt_summary"] = _text_tail(str(clean["prompt_summary"]), 500)
    if "reply" in clean:
        clean["reply"] = _text_tail(str(clean["reply"]), 4000)
    if "error" in clean:
        clean["error"] = _text_tail(str(clean["error"]), 1000)
    return clean


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def _find_executable(name: str) -> str | None:
    path = shutil.which(name)
    if path:
        return path
    for candidate in EXECUTABLE_CANDIDATE_PATHS.get(name, []):
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _worker_process_context() -> dict[str, Any]:
    executable = Path(sys.executable).resolve()
    cwd, cwd_error = _safe_getcwd()
    return {
        "pid": os.getpid(),
        "python_executable": str(executable),
        "python_app_bundle": _enclosing_app_bundle(executable),
        "cwd": cwd or "",
        "cwd_available": cwd_error is None,
        "cwd_error": cwd_error,
        "source": str(Path(__file__).resolve()),
    }


def _enclosing_app_bundle(path: Path) -> str | None:
    for parent in [path, *path.parents]:
        if parent.suffix == ".app":
            return str(parent)
    return None


def _command_output(args: list[str]) -> str:
    try:
        completed = subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)
    return (completed.stdout or completed.stderr).strip()


def _safe_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _is_time_request(lower: str) -> bool:
    if "timer" in lower:
        return False
    return bool(
        re.search(
            r"\b(what time is it|current time|check the time|tell me the time|time now)\b",
            lower,
        )
        or lower.strip() in {"time", "the time"}
    )


def _is_date_request(lower: str) -> bool:
    if "timer" in lower:
        return False
    return bool(
        re.search(
            r"\b(what date is it|what day is it|current date|today's date|date today|day today|tell me the date|check the date)\b",
            lower,
        )
        or lower.strip() in {"today", "the date"}
    )


def _is_battery_status_request(lower: str) -> bool:
    return bool(
        re.search(r"\b(battery|power)\b", lower)
        and re.search(r"\b(status|level|percent|percentage|charge|charging|how much|left|remaining)\b", lower)
    )


def _is_storage_status_request(lower: str) -> bool:
    return bool(
        re.search(r"\b(storage|disk|drive space|free space)\b", lower)
        and re.search(r"\b(status|space|free|available|left|remaining|usage|how much)\b", lower)
    )


def _storage_status() -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(PROJECT_ROOT)
    except OSError as error:
        return {
            "tool": "quick.local_control",
            "matched": True,
            "status": "storage_unavailable",
            "executed": False,
            "action": "storage.status",
            "path_checked": str(PROJECT_ROOT),
            "error": str(error),
            "reply": "I could not read storage status for the Jarvis project root right now.",
        }
    used = usage.total - usage.free
    percent_used = (used / usage.total * 100.0) if usage.total else 0.0
    reply = (
        f"Storage status: {_human_bytes(usage.free)} free of {_human_bytes(usage.total)} total "
        f"({percent_used:.1f}% used)."
    )
    return {
        "tool": "quick.local_control",
        "matched": True,
        "status": "completed",
        "action": "storage.status",
        "executed": True,
        "path_checked": str(PROJECT_ROOT),
        "total_bytes": usage.total,
        "used_bytes": used,
        "free_bytes": usage.free,
        "percent_used": round(percent_used, 1),
        "reply": reply,
    }


def _human_bytes(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    amount = float(max(0, value))
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(amount)} {unit}"
            return f"{amount:.1f} {unit}"
        amount /= 1024.0


def _battery_status() -> dict[str, Any]:
    pmset = _find_executable("pmset")
    base = {
        "tool": "quick.local_control",
        "matched": True,
        "action": "battery.status",
        "executed": True,
    }
    if not pmset:
        return {
            **base,
            "status": "unavailable",
            "reply": "Battery status is not available because `pmset` was not found.",
        }
    output = _command_output([pmset, "-g", "batt"])
    percent_match = re.search(r"(\d{1,3})%", output)
    percent = int(percent_match.group(1)) if percent_match else None
    lower_output = output.lower()
    if "discharging" in lower_output:
        power_state = "discharging"
    elif "charging" in lower_output:
        power_state = "charging"
    elif "charged" in lower_output:
        power_state = "charged"
    elif "ac power" in lower_output:
        power_state = "on AC power"
    else:
        power_state = "unknown"
    time_match = re.search(r"(\d+:\d+)\s+remaining", output)
    time_remaining = time_match.group(1) if time_match else None
    if time_remaining == "0:00" and power_state != "discharging":
        time_remaining = None
    reply = "Battery status:"
    if percent is not None:
        reply += f" {percent}%"
    else:
        reply += " percentage unknown"
    reply += f", {power_state}"
    if time_remaining:
        reply += f", about {time_remaining} remaining"
    reply += "."
    return {
        **base,
        "status": "completed",
        "pmset_path": pmset,
        "battery_percent": percent,
        "power_state": power_state,
        "time_remaining": time_remaining,
        "reply": reply,
    }


def _parse_timer_seconds(lower: str) -> int | None:
    if not re.search(r"\b(timer|remind me in|alarm in)\b", lower):
        return None
    match = re.search(r"\b(\d{1,4})\s*(seconds?|secs?|sec|s|minutes?|mins?|min|m|hours?|hrs?|hr|h)\b", lower)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit.startswith(("s", "sec")):
        seconds = amount
    elif unit.startswith(("m", "min")):
        seconds = amount * 60
    else:
        seconds = amount * 60 * 60
    return max(1, min(seconds, 24 * 60 * 60))


def _is_cancel_timer_request(lower: str) -> bool:
    return bool(re.search(r"\b(cancel|clear|stop)\s+(all\s+)?(active\s+)?timers?\b", lower))


def _is_timer_status_request(lower: str) -> bool:
    return bool(
        re.search(r"\b(timer|timers)\b", lower)
        and re.search(r"\b(status|active|running|list|show|how many|left|remaining)\b", lower)
    )


def _schedule_timer(seconds: int, label: str) -> str:
    timer_id = f"timer-{int(time.time() * 1000)}"
    now = time.time()
    timer = threading.Timer(seconds, _timer_finished, args=(timer_id, label, seconds))
    timer.daemon = True
    with ACTIVE_TIMERS_LOCK:
        ACTIVE_TIMERS[timer_id] = timer
        ACTIVE_TIMER_DETAILS[timer_id] = {
            "timer_id": timer_id,
            "label": label[:120],
            "duration_seconds": seconds,
            "started_at": now,
            "finishes_at": now + seconds,
        }
    timer.start()
    return timer_id


def _active_timer_count() -> int:
    with ACTIVE_TIMERS_LOCK:
        return len(ACTIVE_TIMERS)


def _active_timer_snapshot() -> dict[str, Any]:
    now = time.time()
    with ACTIVE_TIMERS_LOCK:
        timers = [dict(value) for value in ACTIVE_TIMER_DETAILS.values()]
    timers.sort(key=lambda item: float(item.get("finishes_at") or 0))
    for item in timers:
        remaining = max(0, int(round(float(item.get("finishes_at") or now) - now)))
        item["remaining_seconds"] = remaining
        item["remaining_human"] = _human_duration(remaining) if remaining > 0 else "now"
    return {
        "active_count": len(timers),
        "timers": timers,
    }


def _codex_job_counts() -> dict[str, Any]:
    with CODEX_JOBS_LOCK:
        _ensure_codex_jobs_loaded_unlocked()
        jobs = [dict(value) for value in CODEX_JOBS.values()]
    running = [job for job in jobs if job.get("status") == "running"]
    latest = max(jobs, key=lambda job: float(job.get("started_at") or 0), default=None)
    return {
        "tracked_count": len(jobs),
        "running_count": len(running),
        "latest_job_id": latest.get("job_id") if latest else None,
        "latest_status": latest.get("status") if latest else None,
    }


def _cancel_active_timers() -> int:
    with ACTIVE_TIMERS_LOCK:
        timers = list(ACTIVE_TIMERS.values())
        ACTIVE_TIMERS.clear()
        ACTIVE_TIMER_DETAILS.clear()
    for timer in timers:
        timer.cancel()
    return len(timers)


def _timer_finished(timer_id: str, label: str, seconds: int) -> None:
    with ACTIVE_TIMERS_LOCK:
        ACTIVE_TIMERS.pop(timer_id, None)
        ACTIVE_TIMER_DETAILS.pop(timer_id, None)
    osascript = _find_executable("osascript")
    if not osascript:
        return
    title = "Jarvis Timer"
    body = f"{_human_duration(seconds)} timer finished."
    if label:
        body = f"{body} {label[:80]}"
    script = f'display notification "{_escape_applescript_string(body)}" with title "{_escape_applescript_string(title)}"'
    try:
        subprocess.run([osascript, "-e", script], shell=False, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return


def _human_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} second" + ("" if seconds == 1 else "s")
    if seconds < 60 * 60:
        minutes = seconds // 60
        remainder = seconds % 60
        suffix = f"{minutes} minute" + ("" if minutes == 1 else "s")
        if remainder:
            suffix += f" {remainder} second" + ("" if remainder == 1 else "s")
        return suffix
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    suffix = f"{hours} hour" + ("" if hours == 1 else "s")
    if minutes:
        suffix += f" {minutes} minute" + ("" if minutes == 1 else "s")
    return suffix


def _timer_status_reply(snapshot: dict[str, Any]) -> str:
    count = int(snapshot.get("active_count") or 0)
    if count == 0:
        return "No active timers."
    timers = snapshot.get("timers") or []
    first = timers[0] if timers else {}
    remaining = first.get("remaining_human") or "soon"
    return f"{count} active timer{'s' if count != 1 else ''}. Next finishes in {remaining}."


def _parse_media_action(lower: str) -> str | None:
    if re.search(r"\b(play\s+next|next\s+(song|track)|skip\s+(song|track|music))\b", lower):
        return "next"
    if re.search(r"\b(play\s+previous|previous\s+(song|track)|prev\s+(song|track)|back\s+(song|track))\b", lower):
        return "previous"
    if re.search(r"\b(play|pause|resume)\s+(the\s+)?current(\s+(song|track|music|media))?(\s+for\s+me)?\b", lower):
        return "playpause"
    if lower.strip() in {"play", "pause", "resume", "play current", "pause current"}:
        return "playpause"
    if re.search(r"\b(play|pause|resume)\s+(song|track|music|media)\b", lower):
        return "playpause"
    return None


def _run_media_control(action: str) -> dict[str, Any]:
    result = _run_media_key_control(action)
    method = "system_events_media_key"
    labels = {"playpause": "play/pause", "next": "next track", "previous": "previous track"}
    if result["ok"]:
        reply = f"Pressed the system {labels[action]} key."
    elif "not allowed to send keystrokes" in str(result.get("stderr") or "").lower():
        reply = f"I tried to press the system {labels[action]} key, but macOS blocked keystrokes. Grant Accessibility permission to Jarvis, then try again."
    else:
        reply = f"I could not press the system {labels[action]} key."
    return {
        "tool": "quick.local_control",
        "matched": True,
        "status": "completed" if result["ok"] else "failed",
        "executed": result["executed"],
        "action": f"media.{action}",
        "reply": reply,
        "method": method,
        **result,
    }


def _run_media_key_control(action: str) -> dict[str, Any]:
    key_codes = {
        "previous": 98,
        "playpause": 100,
        "next": 101,
    }
    script = f'tell application "System Events" to key code {key_codes[action]}'
    return _run_osascript(script, timeout=0.8)


def _extract_speech_text(text: str) -> str | None:
    stripped = text.strip()
    lower = stripped.lower()
    if lower.startswith("say exactly"):
        return None
    patterns = [
        r"(?is)^speak\s+(.+)$",
        r"(?is)^say\s+out\s+loud\s+(.+)$",
        r"(?is)^read\s+(?:this\s+)?(?:out\s+)?loud\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, stripped)
        if not match:
            continue
        speech_text = match.group(1).strip()
        return speech_text[:600] if speech_text else None
    return None


def _run_say_text(text: str) -> dict[str, Any]:
    say_path = _find_executable("say") or "/usr/bin/say"
    started_at = time.monotonic()
    try:
        completed = subprocess.run(
            [say_path, text],
            shell=False,
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "tool": "quick.local_control",
            "matched": True,
            "status": "timeout",
            "executed": True,
            "action": "speech.say",
            "text_length": len(text),
            **_duration_fields(started_at),
            "reply": "I started speaking, but the speech command ran too long.",
        }
    except OSError as error:
        return {
            "tool": "quick.local_control",
            "matched": True,
            "status": "unavailable",
            "executed": False,
            "action": "speech.say",
            "text_length": len(text),
            "error": str(error),
            **_duration_fields(started_at),
            "reply": "I could not start local speech.",
        }
    return {
        "tool": "quick.local_control",
        "matched": True,
        "status": "completed" if completed.returncode == 0 else "failed",
        "executed": True,
        "action": "speech.say",
        "text_length": len(text),
        "returncode": completed.returncode,
        "stderr": (completed.stderr or "").strip()[-500:],
        **_duration_fields(started_at),
        "reply": "Spoke the text locally." if completed.returncode == 0 else "I tried to speak the text locally, but macOS returned an error.",
    }


def _parse_volume_delta(lower: str) -> int | None:
    if re.search(r"\b(volume|sound)\s+(up|louder|increase)\b|\b(increase|raise)\s+(the\s+)?(volume|sound)\b", lower):
        return 10
    if re.search(r"\b(volume|sound)\s+(down|lower|decrease)\b|\b(decrease|lower)\s+(the\s+)?(volume|sound)\b", lower):
        return -10
    return None


def _parse_volume_target(lower: str) -> int | None:
    patterns = [
        r"\b(?:set|change|turn)\s+(?:the\s+)?(?:volume|sound)\s+(?:to|at)\s+(\d{1,3})\s*(?:%|percent)?\b",
        r"\b(?:volume|sound)\s+(?:to|at)\s+(\d{1,3})\s*(?:%|percent)?\b",
    ]
    return _parse_percent_target(lower, patterns)


def _parse_percent_target(lower: str, patterns: list[str]) -> int | None:
    for pattern in patterns:
        match = re.search(pattern, lower)
        if match:
            return max(0, min(100, int(match.group(1))))
    return None


def _run_volume_control(delta: int) -> dict[str, Any]:
    script = f'''
set currentVolume to output volume of (get volume settings)
set newVolume to currentVolume + ({delta})
if newVolume > 100 then set newVolume to 100
if newVolume < 0 then set newVolume to 0
set volume output volume newVolume
return newVolume
'''.strip()
    result = _run_osascript(script)
    direction = "up" if delta > 0 else "down"
    reply = f"Volume {direction}." if result["ok"] else f"I could not turn volume {direction}."
    if result["stdout"]:
        reply = f"{reply} Current volume: {result['stdout']}."
    return {
        "tool": "quick.local_control",
        "matched": True,
        "status": "completed" if result["ok"] else "failed",
        "executed": result["executed"],
        "action": f"volume.{direction}",
        "reply": reply,
        **result,
    }


def _run_volume_set(percent: int) -> dict[str, Any]:
    target = max(0, min(100, int(percent)))
    script = f'''
set volume output volume {target}
return output volume of (get volume settings)
'''.strip()
    result = _run_osascript(script)
    reply = f"Volume set to {target}%." if result["ok"] else f"I could not set volume to {target}%."
    if result["stdout"]:
        reply = f"{reply} Current volume: {result['stdout']}."
    return {
        "tool": "quick.local_control",
        "matched": True,
        "status": "completed" if result["ok"] else "failed",
        "executed": result["executed"],
        "action": "volume.set",
        "volume_percent": target,
        "reply": reply,
        **result,
    }


def _parse_brightness_delta(lower: str) -> float | None:
    if re.search(r"\bbrightness\s+(up|higher|increase)\b|\b(increase|raise)\s+(the\s+)?brightness\b", lower):
        return 0.1
    if re.search(r"\bbrightness\s+(down|lower|decrease)\b|\b(decrease|lower)\s+(the\s+)?brightness\b", lower):
        return -0.1
    return None


def _parse_brightness_target(lower: str) -> int | None:
    patterns = [
        r"\b(?:set|change|turn)\s+(?:the\s+)?brightness\s+(?:to|at)\s+(\d{1,3})\s*(?:%|percent)?\b",
        r"\bbrightness\s+(?:to|at)\s+(\d{1,3})\s*(?:%|percent)?\b",
    ]
    return _parse_percent_target(lower, patterns)


def _run_brightness_control(delta: float) -> dict[str, Any]:
    direction = "up" if delta > 0 else "down"
    try:
        current = _get_display_brightness()
        target = min(1.0, max(0.0, current + delta))
        _set_display_brightness(target)
    except Exception as error:
        return {
            "tool": "quick.local_control",
            "matched": True,
            "status": "unavailable",
            "executed": False,
            "action": f"brightness.{direction}",
            "reply": f"I could not turn brightness {direction}.",
            "error": str(error),
            "method": "coredisplay",
        }
    return {
        "tool": "quick.local_control",
        "matched": True,
        "status": "completed",
        "executed": True,
        "action": f"brightness.{direction}",
        "reply": f"Brightness {direction}. Current brightness: {round(target * 100)}%.",
        "method": "coredisplay",
        "previous_brightness": round(current, 3),
        "brightness": round(target, 3),
        "brightness_percent": round(target * 100),
    }


def _run_brightness_set(percent: int) -> dict[str, Any]:
    target_percent = max(0, min(100, int(percent)))
    target = target_percent / 100.0
    try:
        current = _get_display_brightness()
        _set_display_brightness(target)
    except Exception as error:
        return {
            "tool": "quick.local_control",
            "matched": True,
            "status": "unavailable",
            "executed": False,
            "action": "brightness.set",
            "reply": f"I could not set brightness to {target_percent}%.",
            "error": str(error),
            "method": "coredisplay",
        }
    return {
        "tool": "quick.local_control",
        "matched": True,
        "status": "completed",
        "executed": True,
        "action": "brightness.set",
        "reply": f"Brightness set to {target_percent}%.",
        "method": "coredisplay",
        "previous_brightness": round(current, 3),
        "brightness": round(target, 3),
        "brightness_percent": target_percent,
    }


def _get_display_brightness() -> float:
    core_graphics, core_display = _load_brightness_libraries()
    display_id = _main_display_id(core_graphics)
    getter = core_display.CoreDisplay_Display_GetUserBrightness
    getter.argtypes = [ctypes.c_uint32]
    getter.restype = ctypes.c_double
    value = float(getter(display_id))
    if not 0.0 <= value <= 1.0:
        raise RuntimeError(f"Display brightness read returned out-of-range value {value}.")
    return value


def _set_display_brightness(value: float) -> None:
    core_graphics, core_display = _load_brightness_libraries()
    display_id = _main_display_id(core_graphics)
    safe_value = min(1.0, max(0.0, float(value)))
    for symbol in ("CoreDisplay_Display_SetUserBrightness", "CoreDisplay_Display_SetDynamicLinearBrightness"):
        setter = getattr(core_display, symbol)
        setter.argtypes = [ctypes.c_uint32, ctypes.c_double]
        setter.restype = ctypes.c_int
        result = int(setter(display_id, ctypes.c_double(safe_value)))
        if result != 0:
            raise RuntimeError(f"{symbol} failed with code {result}.")


def _load_brightness_libraries():
    core_graphics_path = ctypes.util.find_library("CoreGraphics")
    core_display_path = ctypes.util.find_library("CoreDisplay")
    if not core_graphics_path or not core_display_path:
        raise RuntimeError("CoreGraphics/CoreDisplay brightness APIs are unavailable.")
    return ctypes.CDLL(core_graphics_path), ctypes.CDLL(core_display_path)


def _main_display_id(core_graphics) -> int:
    core_graphics.CGMainDisplayID.restype = ctypes.c_uint32
    return int(core_graphics.CGMainDisplayID())


def _run_osascript(script: str, timeout: float = 3.0) -> dict[str, Any]:
    osascript = _find_executable("osascript")
    if not osascript:
        return {"ok": False, "executed": False, "stdout": "", "stderr": "osascript not found", "returncode": None}
    try:
        completed = subprocess.run(
            [osascript, "-e", script],
            shell=False,
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "executed": True, "stdout": "", "stderr": "osascript timed out", "returncode": None}
    except OSError as error:
        return {"ok": False, "executed": False, "stdout": "", "stderr": str(error), "returncode": None}
    return {
        "ok": completed.returncode == 0,
        "executed": True,
        "stdout": (completed.stdout or "").strip()[-500:],
        "stderr": (completed.stderr or "").strip()[-500:],
        "returncode": completed.returncode,
    }


def _escape_applescript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _clean_codex_prompt(prompt: str) -> str:
    text = prompt.strip()
    prefixes = [
        r"(?i)^codex\s*:\s*",
        r"(?i)^ask\s+codex\s+to\s+",
        r"(?i)^ask\s+codex\s+",
        r"(?i)^codex\s+",
    ]
    for pattern in prefixes:
        text = re.sub(pattern, "", text).strip()
    return text or prompt.strip()


def _codex_fast_prompt(prompt: str) -> str:
    cleaned = prompt.strip()
    file_map = _project_file_map()
    return f"""You are running as a fast read-only Codex delegate for Jarvis.
Use a narrow pass and finish quickly. If the request is broad, inspect only the most relevant source, config, and test files; skip generated folders such as output, runtime, .build, node_modules, and caches.
Return the useful answer directly in under 10 bullets. Prioritize concrete bugs, blockers, and next actions. Do not perform long exhaustive review.
Trust this generated file map as the starting point for what exists. Do not claim a target or source folder is missing if it appears here.

Visible project file map:
{file_map}

User request:
{cleaned}"""


def _codex_chat_prompt(prompt: str) -> str:
    cleaned = prompt.strip()
    return f"""You are Jarvis, Leo's local Mac assistant prototype.
Leo is the user's real name for profile context, but do not address him as Leo, Sir, or by any title unless he explicitly asks.
Answer this safe general chat request directly, warmly, and briefly. Do not claim you performed computer actions. Do not inspect project files unless the user explicitly asks about the project. Keep the answer under 8 sentences.

Leo says:
{cleaned}"""


def _fast_local_prompt(prompt: str) -> str:
    cleaned = prompt.strip()
    return f"""You are Jarvis, Leo's local Mac assistant prototype.
Leo is the user's real name for profile context, but do not address him as Leo, Sir, or by any title unless he explicitly asks.
Answer directly and briefly unless he asks for more.
Follow Leo's requested output format, including exact text or bullet counts.
Be useful and natural. Do not claim you performed computer actions.
Do not invent schedule, email, weather, app, file, or system facts.
For a simple greeting, only say hello and ask what he wants done.
Do not mention that you are a language model. Do not use emojis.

Leo says:
{cleaned}"""


def _rough_understanding(prompt: str) -> str:
    text = re.sub(r"\s+", " ", prompt.strip())
    if not text:
        return "Leo has not given a concrete request yet."
    if len(text) > 180:
        text = text[:177].rstrip() + "..."
    return text


def _strip_think_blocks(text: str) -> str:
    cleaned = re.sub(r"(?is)<think>.*?</think>", "", text)
    cleaned = re.sub(r"(?is)</?think>", "", cleaned)
    cleaned = cleaned.replace("/no_think", "")
    return cleaned.strip()


def _fast_model_unavailable_reply(prompt: str) -> str:
    if _looks_codex_worthy(prompt):
        return f"I should hand this to Codex. My understanding: {_rough_understanding(prompt)}"
    return "My fast local model is not ready yet, and I will not fake an AI answer."


def _fast_model_timeout_reply(model: str, duration_human: str) -> str:
    return f"The fast local model {model} did not answer within {duration_human}, so I stopped instead of making you wait."


def _looks_codex_worthy(prompt: str) -> bool:
    lower = prompt.lower()
    return bool(
        re.search(
            r"\b(code|coding|codex|debug|bug|fix|implement|build|compile|review|project|repo|repository|swift|python|test|tests)\b",
            lower,
        )
    )


def _local_conversation_reply(prompt: str) -> str:
    return "I can route that through Codex when it is available. Right now I can also route status, safe shell reads, file search, app checks, screenshots, Outlook summaries, browser planning, and Codex delegation."


def _duration_fields(started_at: float) -> dict[str, Any]:
    duration_seconds = max(0.0, time.monotonic() - started_at)
    return {
        "duration_seconds": round(duration_seconds, 3),
        "duration_human": _format_seconds(duration_seconds),
    }


def _format_seconds(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    remainder = seconds - minutes * 60
    return f"{minutes}m {remainder:.1f}s"


def _project_file_map(max_files: int = 160) -> str:
    roots = ["jarvis", "scripts", "swift-shell/Sources", "swift-shell/scripts", "tests"]
    files: list[str] = []
    for root_name in roots:
        root = PROJECT_ROOT / root_name
        if not root.exists():
            continue
        if root.is_file():
            files.append(root_name)
            continue
        for current_root, dirs, names in os.walk(root):
            dirs[:] = [directory for directory in dirs if directory not in FILE_SEARCH_EXCLUDED_DIRS]
            for name in names:
                path = Path(current_root, name)
                if path.suffix in {".pyc", ".png", ".jpg", ".jpeg", ".icns"}:
                    continue
                files.append(str(path.relative_to(PROJECT_ROOT)))
                if len(files) >= max_files:
                    return "\n".join(f"- {file}" for file in sorted(files))
    return "\n".join(f"- {file}" for file in sorted(files)) or "- No project files discovered."


def _codex_reply(stdout: str, stderr: str, returncode: int, model: str, *, last_message: str = "") -> str:
    if returncode == 0:
        if last_message.strip():
            return last_message.strip()[-4000:]
        content = stdout.strip()
        if not content:
            return f"Codex CLI finished with {model}, but it did not return visible text."
        return content[-1800:]
    error = (stderr or stdout).strip()
    if not error:
        error = f"exit code {returncode}"
    return f"Codex CLI failed using {model}: {error[-1200:]}"


def _apple_mail_messages(limit: int, scan_limit: int, osascript: str | None) -> dict[str, Any]:
    base: dict[str, Any] = {
        "status": "unavailable",
        "source": "apple_mail",
        "inbox_count": 0,
        "scanned_count": 0,
        "messages": [],
    }
    if not osascript:
        return {**base, "status": "osascript_not_found", "reply": "macOS AppleScript tooling is unavailable."}

    try:
        completed = subprocess.run(
            [osascript, "-e", _apple_mail_newest_applescript(limit, scan_limit)],
            shell=False,
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=OUTLOOK_APPLESCRIPT_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {**base, "status": "timeout", "reply": "Apple Mail read-only check timed out."}
    except OSError as error:
        return {**base, "status": "automation_error", "error": str(error)}

    if completed.returncode != 0:
        return {
            **base,
            "status": "needs_permission_or_scripting",
            "returncode": completed.returncode,
            "error": _text_tail(completed.stderr or completed.stdout, 1800),
        }

    parsed = _parse_outlook_newest_output(completed.stdout)
    return {
        **base,
        "status": "checked" if parsed["messages"] else "empty",
        **parsed,
    }


def _apple_mail_newest_applescript(limit: int, scan_limit: int) -> str:
    return f'''
on cleanText(rawValue)
    set textValue to rawValue as text
    set AppleScript's text item delimiters to {{return, linefeed, tab}}
    set parts to text items of textValue
    set AppleScript's text item delimiters to " "
    set cleanedValue to parts as text
    set AppleScript's text item delimiters to ""
    if length of cleanedValue > 700 then set cleanedValue to text 1 thru 700 of cleanedValue
    return cleanedValue
end cleanText

tell application "Mail"
    launch
    delay 0.4
    set inboxMessages to messages of inbox
    set inboxCount to count of inboxMessages
    set scanCount to {scan_limit}
    if inboxCount < scanCount then set scanCount to inboxCount
    set maxItems to {limit}
    if scanCount < maxItems then set maxItems to scanCount
    set selectedIndexes to {{}}
    set outputText to "INBOX_COUNT" & tab & (inboxCount as text) & tab & "SCANNED" & tab & (scanCount as text)
    repeat with slotIndex from 1 to maxItems
        set bestIndex to 0
        set bestDate to missing value
        repeat with itemIndex from 1 to scanCount
            if selectedIndexes does not contain itemIndex then
                set currentMessage to item itemIndex of inboxMessages
                try
                    set currentDate to date received of currentMessage
                    if bestDate is missing value or currentDate > bestDate then
                        set bestDate to currentDate
                        set bestIndex to itemIndex
                    end if
                end try
            end if
        end repeat
        if bestIndex is 0 then exit repeat
        set end of selectedIndexes to bestIndex
        set currentMessage to item bestIndex of inboxMessages
        set senderText to "Unknown sender"
        try
            set senderText to sender of currentMessage
        end try
        set subjectText to "(no subject)"
        try
            set subjectText to subject of currentMessage
        end try
        set receivedText to ""
        try
            set receivedText to date received of currentMessage as text
        end try
        set readText to "unknown"
        try
            if read status of currentMessage then
                set readText to "read"
            else
                set readText to "unread"
            end if
        end try
        set snippetText to ""
        try
            set snippetText to my cleanText(content of currentMessage)
        end try
        set outputText to outputText & linefeed & "MESSAGE" & tab & my cleanText(senderText) & tab & my cleanText(subjectText) & tab & my cleanText(receivedText) & tab & readText & tab & snippetText
    end repeat
    return outputText
end tell
'''.strip()


def _outlook_newest_applescript(limit: int, scan_limit: int) -> str:
    return f'''
on cleanText(rawValue)
    set textValue to rawValue as text
    set AppleScript's text item delimiters to {{return, linefeed, tab}}
    set parts to text items of textValue
    set AppleScript's text item delimiters to " "
    set cleanedValue to parts as text
    set AppleScript's text item delimiters to ""
    if length of cleanedValue > 700 then set cleanedValue to text 1 thru 700 of cleanedValue
    return cleanedValue
end cleanText

tell application "Microsoft Outlook"
    activate
    delay 0.4
    set inboxMessages to messages of inbox
    set inboxCount to count of inboxMessages
    set scanCount to {scan_limit}
    if inboxCount < scanCount then set scanCount to inboxCount
    set maxItems to {limit}
    if scanCount < maxItems then set maxItems to scanCount
    set selectedIndexes to {{}}
    set outputText to "INBOX_COUNT" & tab & (inboxCount as text) & tab & "SCANNED" & tab & (scanCount as text)
    repeat with slotIndex from 1 to maxItems
        set bestIndex to 0
        set bestDate to missing value
        repeat with itemIndex from 1 to scanCount
            if selectedIndexes does not contain itemIndex then
                set currentMessage to item itemIndex of inboxMessages
                try
                    set currentDate to time received of currentMessage
                    if bestDate is missing value or currentDate > bestDate then
                        set bestDate to currentDate
                        set bestIndex to itemIndex
                    end if
                end try
            end if
        end repeat
        if bestIndex is 0 then exit repeat
        set end of selectedIndexes to bestIndex
        set currentMessage to item bestIndex of inboxMessages
        set senderText to "Unknown sender"
        try
            set senderText to name of sender of currentMessage
        end try
        if senderText is "" then
            try
                set senderText to address of sender of currentMessage
            end try
        end if
        set subjectText to "(no subject)"
        try
            set subjectText to subject of currentMessage
        end try
        set receivedText to ""
        try
            set receivedText to time received of currentMessage as text
        end try
        set readText to "unknown"
        try
            if is read of currentMessage then
                set readText to "read"
            else
                set readText to "unread"
            end if
        end try
        set snippetText to ""
        try
            set snippetText to my cleanText(content of currentMessage)
        end try
        set outputText to outputText & linefeed & "MESSAGE" & tab & my cleanText(senderText) & tab & my cleanText(subjectText) & tab & my cleanText(receivedText) & tab & readText & tab & snippetText
    end repeat
    return outputText
end tell
'''.strip()


def _parse_outlook_newest_output(output: str) -> dict[str, Any]:
    inbox_count = 0
    scanned_count = 0
    messages: list[dict[str, str]] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 4 and parts[0] == "INBOX_COUNT":
            try:
                inbox_count = max(0, int(parts[1]))
                scanned_count = max(0, int(parts[3]))
            except ValueError:
                inbox_count = 0
                scanned_count = 0
            continue
        if len(parts) >= 6 and parts[0] == "MESSAGE":
            messages.append(
                {
                    "sender": parts[1].strip() or "Unknown sender",
                    "subject": parts[2].strip() or "(no subject)",
                    "received": parts[3].strip(),
                    "read_state": parts[4].strip() or "unknown",
                    "snippet": parts[5].strip(),
                }
            )
    return {"inbox_count": inbox_count, "scanned_count": scanned_count, "messages": messages}


def _outlook_sqlite_messages(limit: int) -> dict[str, Any]:
    db_path = _outlook_sqlite_db_path()
    base: dict[str, Any] = {
        "status": "unavailable",
        "source": "sqlite",
        "database": str(db_path),
        "inbox_count": 0,
        "scanned_count": 0,
        "messages": [],
    }
    if not db_path.exists():
        return {**base, "reply": "The legacy Outlook local database was not found."}

    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2)
        connection.row_factory = sqlite3.Row
        try:
            total = int(connection.execute("select count(*) from Mail").fetchone()[0])
            rows = connection.execute(
                """
                select
                    coalesce(Message_SenderList, '') as sender,
                    coalesce(Message_NormalizedSubject, Message_ThreadTopic, '(no subject)') as subject,
                    coalesce(Message_TimeReceived, Message_TimeSent, '') as received,
                    case coalesce(Message_ReadFlag, 0) when 1 then 'read' else 'unread' end as read_state,
                    coalesce(Message_Preview, '') as snippet,
                    coalesce(Folders.Folder_Name, '') as folder_name
                from Mail
                left join Folders on Folders.Record_RecordID = Mail.Record_FolderID
                where coalesce(Message_IsOutgoingMessage, 0) = 0
                  and coalesce(Message_Hidden, 0) = 0
                  and coalesce(Message_MarkedForDelete, 0) = 0
                order by datetime(coalesce(Message_TimeReceived, Message_TimeSent, '1900-01-01')) desc,
                         Mail.Record_RecordID desc
                limit ?
                """,
                (max(1, min(int(limit), 10)),),
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.Error as error:
        return {**base, "status": "sqlite_error", "reply": f"The Outlook local database could not be read: {error}"}

    messages = [
        {
            "sender": _clean_local_field(row["sender"]) or "Unknown sender",
            "subject": _clean_local_field(row["subject"]) or "(no subject)",
            "received": _clean_local_field(row["received"]),
            "read_state": _clean_local_field(row["read_state"]) or "unknown",
            "snippet": _clean_local_field(row["snippet"]),
            "source": "sqlite",
            "folder": _clean_local_field(row["folder_name"]),
        }
        for row in rows
    ]
    return {
        **base,
        "status": "checked" if messages else "empty",
        "inbox_count": total,
        "scanned_count": total,
        "messages": messages,
    }


def _outlook_sqlite_db_path() -> Path:
    return Path.home() / "Library/Group Containers/UBF8T346G9.Office/Outlook/Outlook 15 Profiles/Main Profile/Data/Outlook.sqlite"


def _outlook_screen_ocr_messages(limit: int) -> dict[str, Any]:
    screencapture = _find_executable("screencapture")
    tesseract = _find_executable("tesseract")
    base: dict[str, Any] = {
        "status": "unavailable",
        "source": "screen_ocr",
        "screencapture": screencapture,
        "tesseract": tesseract,
        "worker_process": _worker_process_context(),
        "inbox_count": 0,
        "scanned_count": 0,
        "messages": [],
    }
    if not screencapture or not tesseract:
        return {
            **base,
            "reply": "Local screen OCR is unavailable because screencapture or tesseract is missing.",
            "next_steps": ["Install tesseract or use a direct Outlook/Graph integration later."],
        }

    try:
        subprocess.run(["open", "-a", "Microsoft Outlook"], shell=False, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass
    time.sleep(1.2)

    with tempfile.TemporaryDirectory(prefix="jarvis-outlook-ocr-") as temp_dir:
        image_path = Path(temp_dir) / "outlook.png"
        capture = subprocess.run(
            [screencapture, "-x", str(image_path)],
            shell=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=8,
            check=False,
        )
        if capture.returncode != 0 or not image_path.exists() or image_path.stat().st_size < 1024:
            return {
                **base,
                "status": "screen_capture_failed",
                "reply": "I opened Outlook, but the Python worker process doing OCR does not have usable Screen Recording access yet.",
                "error": _text_tail(capture.stderr or capture.stdout, 1000),
                "next_steps": [
                    "In System Settings > Privacy & Security > Screen Recording, also grant access to the Python process listed in worker_process if macOS shows it.",
                    "If only Jarvis is listed, turn Jarvis off/on in Screen Recording, then quit and reopen Jarvis with the exact v27 command.",
                    "Longer-term fix: move screen capture into the native Jarvis app process instead of this Python OCR worker.",
                ],
            }
        try:
            ocr = subprocess.run(
                [tesseract, str(image_path), "stdout", "--psm", "6"],
                shell=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=OUTLOOK_OCR_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                **base,
                "status": "ocr_timeout",
                "reply": "I captured Outlook locally, but OCR timed out before it could read visible text.",
                "next_steps": ["Bring the Outlook inbox to the front and try again."],
            }

    if ocr.returncode != 0:
        return {
            **base,
            "status": "ocr_failed",
            "reply": "I captured Outlook locally, but OCR failed.",
            "error": _text_tail(ocr.stderr or ocr.stdout, 1000),
            "next_steps": ["Bring the Outlook inbox to the front and try again."],
        }

    lines = _ocr_email_lines(ocr.stdout, limit=max(1, min(int(limit), 5)))
    if not lines:
        return {
            **base,
            "status": "ocr_empty",
            "reply": "I captured Outlook locally, but OCR did not find readable inbox text.",
            "next_steps": ["Bring the Outlook inbox list to the front and try again."],
        }

    snippet = " | ".join(lines)
    return {
        **base,
        "status": "checked",
        "inbox_count": len(lines),
        "scanned_count": len(lines),
        "messages": [
            {
                "sender": "Visible Outlook window",
                "subject": "Local OCR fallback",
                "received": "",
                "read_state": "visible",
                "snippet": snippet[:700],
                "source": "screen_ocr",
            }
        ],
        "reply": "I read visible Outlook text locally with OCR. This fallback summarizes the visible window, not the full mailbox database.",
    }


def _ocr_email_lines(text: str, *, limit: int) -> list[str]:
    noise = {
        "all accounts",
        "archive",
        "conversation history",
        "deleted items",
        "drafts",
        "edit",
        "favorites",
        "file",
        "filter",
        "focused",
        "format",
        "help",
        "inbox",
        "junk email",
        "message",
        "new mail",
        "other",
        "outlook",
        "outbox",
        "profiles",
        "search",
        "sent",
        "snoozed",
        "tools",
        "view",
        "window",
    }
    lines: list[str] = []
    for raw_line in text.splitlines():
        fragments = raw_line.split("|") if "|" in raw_line else [raw_line]
        for raw_fragment in fragments:
            line = _clean_local_field(raw_fragment)
            if len(line) < 4:
                continue
            normalized = _normalize_outlook_ocr_fragment(line)
            if normalized in noise:
                continue
            if _looks_like_outlook_chrome_line(line):
                continue
            if _looks_like_outlook_navigation_fragment(line):
                continue
            if re.fullmatch(r"[\W_]+", line):
                continue
            lines.append(line)
            if len(lines) >= limit * 4:
                break
        if len(lines) >= limit * 4:
            break
    return lines[: max(1, limit * 4)]


def _looks_like_outlook_chrome_line(line: str) -> bool:
    lower = line.lower()
    if "outlook | file | edit" in lower or "file | edit | view" in lower:
        return True
    if "new mail" in lower and ("favorites" in lower or "focused" in lower or "inbox" in lower):
        return True

    chrome_terms = {
        "outlook",
        "file",
        "edit",
        "view",
        "message",
        "format",
        "profiles",
        "tools",
        "window",
        "help",
        "new mail",
        "favorites",
        "focused",
        "other",
        "filter",
        "search",
    }
    if "|" not in line:
        return False

    parts = [part.strip(" -_:;,.•·0123456789cv") for part in lower.split("|")]
    parts = [part for part in parts if part]
    if len(parts) < 3:
        return False
    hits = 0
    for part in parts:
        if part in chrome_terms or any(part.endswith(term) for term in chrome_terms):
            hits += 1
    return hits >= 3


def _looks_like_outlook_navigation_fragment(line: str) -> bool:
    raw_lower = line.lower()
    normalized = _normalize_outlook_ocr_fragment(line)
    if not normalized:
        return True
    if "@" in normalized and "..." in raw_lower:
        return True
    if normalized in {
        "all accounts",
        "conversation history",
        "deleted items",
        "drafts",
        "edit",
        "favorites",
        "file",
        "format",
        "groups",
        "help",
        "inbox",
        "junk email",
        "message",
        "new mail",
        "outlook",
        "outbox",
        "profiles",
        "sent",
        "snoozed",
        "tools",
        "view",
        "window",
    }:
        return True
    return False


def _normalize_outlook_ocr_fragment(line: str) -> str:
    normalized = line.lower()
    normalized = re.sub(r"^[\s•·\-_:;,.]+", "", normalized)
    normalized = re.sub(r"^(?:c|v|co)\s+", "", normalized)
    normalized = re.sub(r"^[\s•·\-_:;,.0-9]+", "", normalized)
    normalized = " ".join(normalized.split())
    return normalized.strip(" -_:;,.•·")


def _clean_local_field(value: Any) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.replace("\x00", " ").split())
    return text[:700]


def _safe_root(root: str | None) -> Path:
    if not root:
        return PROJECT_ROOT
    candidate = Path(root).expanduser()
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    candidate = candidate.resolve()
    if not candidate.exists() or not candidate.is_dir():
        return PROJECT_ROOT
    if not candidate.is_relative_to(PROJECT_ROOT.resolve()):
        return PROJECT_ROOT
    return candidate
