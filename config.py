"""Configuration constants for the Jarvis prototype."""

from __future__ import annotations

import os
import re
import shlex
from ipaddress import ip_address
from pathlib import Path


def load_user_env_file() -> None:
    """Load simple KEY=VALUE assignments for app launches that do not inherit a shell."""
    env_path = Path(os.environ.get("JARVIS_ENV_FILE", "~/.jarvis.env")).expanduser()
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            parts = shlex.split(line, comments=True, posix=True)
        except ValueError:
            continue
        if not parts:
            continue
        if parts[0] == "export":
            parts = parts[1:]
        for part in parts:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                os.environ.setdefault(key, value)


load_user_env_file()


def env_int(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


PROJECT_ROOT = Path(os.environ.get("JARVIS_WORKSPACE_ROOT", Path(__file__).resolve().parent.parent)).expanduser().resolve()
RUNTIME_DIR = PROJECT_ROOT / "runtime"
AUDIT_DIR = RUNTIME_DIR / "audit"
AUDIT_LOG = AUDIT_DIR / "events.jsonl"

DEFAULT_HOST = os.environ.get("JARVIS_HOST", "127.0.0.1")
DEFAULT_PORT = env_int("JARVIS_PORT", 8765, minimum=1, maximum=65535)
START_PAUSED = env_bool("JARVIS_START_PAUSED", False)
ALLOW_NON_LOOPBACK = env_bool("JARVIS_ALLOW_NON_LOOPBACK", False)

AUDIT_RETENTION_DAYS = env_int("JARVIS_AUDIT_RETENTION_DAYS", 90, minimum=1)
AUDIT_MAX_BYTES = env_int("JARVIS_AUDIT_MAX_BYTES", 1024 * 1024 * 1024, minimum=1024 * 1024)

SAFE_SHELL_TIMEOUT_SECONDS = 8
MAX_COMMAND_CHARS = 4000
MAX_REQUEST_BYTES = 16 * 1024
MAX_AUDIT_EVENTS = 200
MAX_FILE_SEARCH_RESULTS = 50

DEFAULT_CODEX_MODEL = os.environ.get("JARVIS_CODEX_MODEL", "gpt-5.4-mini")
DEFAULT_CODEX_REASONING_EFFORT = os.environ.get("JARVIS_CODEX_REASONING_EFFORT", "low")
CODEX_TIMEOUT_SECONDS = env_int("JARVIS_CODEX_TIMEOUT_SECONDS", 210, minimum=10, maximum=300)
CODEX_CHAT_TIMEOUT_SECONDS = env_int("JARVIS_CODEX_CHAT_TIMEOUT_SECONDS", 12, minimum=3, maximum=90)
FAST_MODEL_BACKEND = os.environ.get("JARVIS_FAST_MODEL_BACKEND", "ollama")
FAST_MODEL_NAME = os.environ.get("JARVIS_FAST_MODEL", "qwen3:0.6b")
FAST_MODEL_FALLBACK_BACKEND = os.environ.get("JARVIS_FAST_MODEL_FALLBACK_BACKEND", "ollama").strip().lower()
FAST_MODEL_FALLBACK_ENABLED = env_bool("JARVIS_FAST_MODEL_FALLBACK_ENABLED", True)
FAST_MODEL_TIMEOUT_SECONDS = env_int("JARVIS_FAST_MODEL_TIMEOUT_SECONDS", 5, minimum=1, maximum=15)
FAST_MODEL_MAX_TOKENS = env_int("JARVIS_FAST_MODEL_MAX_TOKENS", 80, minimum=16, maximum=256)
OLLAMA_BASE_URL = os.environ.get("JARVIS_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_BASE_URL = os.environ.get("JARVIS_GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_FAST_MODEL = os.environ.get("JARVIS_GROQ_MODEL", "llama-3.3-70b-versatile")
OUTLOOK_MAX_SCAN_MESSAGES = env_int("JARVIS_OUTLOOK_MAX_SCAN_MESSAGES", 250, minimum=10, maximum=2000)
OUTLOOK_APPLESCRIPT_TIMEOUT_SECONDS = env_int("JARVIS_OUTLOOK_APPLESCRIPT_TIMEOUT_SECONDS", 20, minimum=5, maximum=90)
OUTLOOK_OCR_TIMEOUT_SECONDS = env_int("JARVIS_OUTLOOK_OCR_TIMEOUT_SECONDS", 30, minimum=5, maximum=90)
OUTLOOK_USE_APPLESCRIPT = env_bool("JARVIS_OUTLOOK_USE_APPLESCRIPT", False)
OUTLOOK_USE_LEGACY_SQLITE = env_bool("JARVIS_OUTLOOK_USE_LEGACY_SQLITE", False)


def host_allowed(host: str, *, allow_non_loopback: bool = ALLOW_NON_LOOPBACK) -> bool:
    if allow_non_loopback:
        return True
    normalized = host.strip().lower()
    if normalized == "localhost":
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False
