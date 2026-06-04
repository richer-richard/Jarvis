"""Local audit logging for Jarvis prototype actions."""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import AUDIT_LOG, AUDIT_MAX_BYTES, AUDIT_RETENTION_DAYS


SENSITIVE_TEXT_PATTERNS = [
    re.compile(
        r"\b([A-Za-z0-9_]*(?:api[_ -]?key|token|password|secret|credential)[A-Za-z0-9_]*)\s*[:=]\s*([^\s,;]+)",
        re.IGNORECASE,
    ),
    re.compile(r"\b(api[_ -]?key|token|password|secret|credential)\s*[:=]\s*([^\s,;]+)", re.IGNORECASE),
    re.compile(r"\b(api[_ -]?key|token|password|secret|credential)\s+is\s+([^\s,;]+)", re.IGNORECASE),
    re.compile(r"\b(bearer)\s+[A-Za-z0-9._~+/\-]+=*", re.IGNORECASE),
]
STANDALONE_SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{8,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{12,}\b"),
]
SENSITIVE_DETAIL_KEY_PATTERN = re.compile(
    r"(api[_ -]?key|authorization|bearer|credential|password|secret|token)",
    re.IGNORECASE,
)
AUDIT_MAX_STRING_CHARS = 4000


@dataclass
class AuditEvent:
    id: str
    timestamp: float
    command: str
    risk_level: int
    risk_label: str
    tool: str
    decision: str
    summary: str
    details: dict[str, Any]


class AuditLogger:
    """Append-only JSONL audit log with simple retention trimming."""

    def __init__(self, path: Path = AUDIT_LOG) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def record(
        self,
        *,
        command: str,
        risk_level: int,
        risk_label: str,
        tool: str,
        decision: str,
        summary: str,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            command=redact_sensitive_text(command),
            risk_level=risk_level,
            risk_label=risk_label,
            tool=tool,
            decision=decision,
            summary=redact_sensitive_text(summary),
            details=_redact_audit_value(details or {}),
        )
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(event), ensure_ascii=False, sort_keys=True) + "\n")
            self.enforce_retention()
        return event

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            if not self.path.exists():
                return []
            lines: deque[str] = deque(maxlen=max(1, limit))
            with self.path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    lines.append(line.rstrip("\n"))
        events: list[dict[str, Any]] = []
        for line in lines:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                events.append({"timestamp": 0, "summary": "Unreadable audit line", "raw": redact_sensitive_text(line)})
        return events

    def status(self) -> dict[str, Any]:
        with self._lock:
            exists = self.path.exists()
            byte_size = self.path.stat().st_size if exists else 0
            event_count = 0
            unreadable_lines = 0
            oldest_timestamp: float | None = None
            newest_timestamp: float | None = None

            if exists:
                with self.path.open("r", encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        if not line.strip():
                            continue
                        event_count += 1
                        try:
                            event = json.loads(line)
                            timestamp = float(event.get("timestamp", 0))
                        except (json.JSONDecodeError, TypeError, ValueError):
                            unreadable_lines += 1
                            continue
                        if timestamp <= 0:
                            continue
                        oldest_timestamp = timestamp if oldest_timestamp is None else min(oldest_timestamp, timestamp)
                        newest_timestamp = timestamp if newest_timestamp is None else max(newest_timestamp, timestamp)

        return {
            "path": str(self.path),
            "exists": exists,
            "event_count": event_count,
            "unreadable_lines": unreadable_lines,
            "byte_size": byte_size,
            "byte_size_human": _format_bytes(byte_size),
            "retention_days": AUDIT_RETENTION_DAYS,
            "max_bytes": AUDIT_MAX_BYTES,
            "max_bytes_human": _format_bytes(AUDIT_MAX_BYTES),
            "oldest_timestamp": oldest_timestamp,
            "newest_timestamp": newest_timestamp,
            "raw_audio_or_screenshots": "not stored by default",
        }

    def enforce_retention(
        self,
        *,
        max_age_days: int = AUDIT_RETENTION_DAYS,
        max_bytes: int = AUDIT_MAX_BYTES,
    ) -> None:
        with self._lock:
            if not self.path.exists():
                return
            cutoff = time.time() - (max_age_days * 24 * 60 * 60)
            lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
            kept: list[str] = []
            for line in lines:
                try:
                    event = json.loads(line)
                    if float(event.get("timestamp", 0)) >= cutoff:
                        kept.append(line)
                except (json.JSONDecodeError, TypeError, ValueError):
                    kept.append(line)
            while sum(len(line.encode("utf-8")) + 1 for line in kept) > max_bytes and kept:
                kept.pop(0)
            if kept != lines:
                self.path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")


def _format_bytes(value: int) -> str:
    amount = float(value)
    for suffix in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or suffix == "TB":
            if suffix == "B":
                return f"{int(amount)} {suffix}"
            return f"{amount:.1f} {suffix}"
        amount /= 1024


def redact_sensitive_text(text: str) -> str:
    redacted = text
    for pattern in SENSITIVE_TEXT_PATTERNS:
        redacted = pattern.sub(_redact_match, redacted)
    for pattern in STANDALONE_SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return _truncate_text(redacted)


def _redact_match(match: re.Match[str]) -> str:
    first = match.group(1)
    if first.lower() == "bearer":
        return f"{first} [REDACTED]"
    separator = " is " if " is " in match.group(0).lower() else "="
    return f"{first}{separator}[REDACTED]"


def _truncate_text(text: str, max_chars: int = AUDIT_MAX_STRING_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return f"{text[:max_chars]}...[truncated {omitted} chars]"


def _redact_audit_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, (bytes, bytearray)):
        return redact_sensitive_text(bytes(value).decode("utf-8", errors="replace"))
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key)
            redacted_key = redact_sensitive_text(key_text)
            redacted[redacted_key] = "[REDACTED]" if _is_sensitive_detail_key(key_text) else _redact_audit_value(child)
        return redacted
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_redact_audit_value(child) for child in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_sensitive_text(str(value))


def _is_sensitive_detail_key(key: str) -> bool:
    return bool(SENSITIVE_DETAIL_KEY_PATTERN.search(key))
