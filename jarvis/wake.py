"""Text-only wake phrase simulation for the Jarvis prototype."""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from typing import Any


WAKE_PHRASES = ("hey jarvis", "okay jarvis", "ok jarvis")


@dataclass(frozen=True)
class WakeDetection:
    woke: bool
    phrase: str | None
    command: str
    needs_followup: bool
    normalized: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WakeSession:
    """Small state machine for transcript-only wake flow tests."""

    def __init__(self, *, timeout_seconds: float = 8.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.listening = False
        self.last_wake_at: float | None = None

    def observe(self, transcript: str, *, now: float | None = None) -> dict[str, Any]:
        observed_at = time.time() if now is None else now
        if self.listening and self.last_wake_at is not None:
            if observed_at - self.last_wake_at > self.timeout_seconds:
                self.listening = False
                self.last_wake_at = None

        detection = detect_wake_command(transcript)
        if detection.woke and detection.needs_followup:
            self.listening = True
            self.last_wake_at = observed_at
            return {
                "event": "wake_detected",
                "listening": True,
                "command": "",
                "detection": detection.to_dict(),
            }
        if detection.woke:
            self.listening = False
            self.last_wake_at = None
            return {
                "event": "command_captured",
                "listening": False,
                "command": detection.command,
                "detection": detection.to_dict(),
            }
        if self.listening:
            command = normalize_transcript(transcript)
            if command:
                self.listening = False
                self.last_wake_at = None
                return {
                    "event": "command_captured",
                    "listening": False,
                    "command": command,
                    "detection": detection.to_dict(),
                }

        return {
            "event": "ignored",
            "listening": self.listening,
            "command": "",
            "detection": detection.to_dict(),
        }


def detect_wake_command(transcript: str, wake_phrases: tuple[str, ...] = WAKE_PHRASES) -> WakeDetection:
    normalized = normalize_transcript(transcript)
    for phrase in wake_phrases:
        normalized_phrase = normalize_transcript(phrase)
        if normalized == normalized_phrase:
            return WakeDetection(True, phrase, "", True, normalized)
        prefix = f"{normalized_phrase} "
        if normalized.startswith(prefix):
            command = normalized.removeprefix(prefix).strip()
            return WakeDetection(True, phrase, command, not bool(command), normalized)
    return WakeDetection(False, None, "", False, normalized)


def normalize_transcript(transcript: str) -> str:
    lowered = transcript.strip().lower()
    ascii_words = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(ascii_words.split())
