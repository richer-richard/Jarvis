"""Wake phrase helpers for the Jarvis prototype."""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from typing import Any


WAKE_PHRASES = ("hey jarvis", "okay jarvis", "ok jarvis")
DEFAULT_WAKE_THRESHOLD = 0.82


@dataclass(frozen=True)
class WakeDetection:
    woke: bool
    phrase: str | None
    command: str
    needs_followup: bool
    normalized: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WakeScore:
    detected: bool
    score: float
    threshold: float
    phrase: str | None
    command: str
    normalized: str
    window: str
    start_word_index: int | None
    mode: str

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
            if is_wake_greeting_echo(command):
                return {
                    "event": "ignored_echo",
                    "listening": True,
                    "command": "",
                    "detection": detection.to_dict(),
                }
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
    exact = _exact_wake_detection(normalized, wake_phrases)
    if exact is not None:
        return exact
    fuzzy = _best_fuzzy_wake_match(normalized, wake_phrases)
    if fuzzy is not None and fuzzy["score"] >= DEFAULT_WAKE_THRESHOLD:
        command = _clean_command(str(fuzzy["command"]))
        return WakeDetection(True, str(fuzzy["phrase"]), command, not bool(command), normalized)
    return WakeDetection(False, None, "", False, normalized)


def score_wake_transcript(
    transcript: str,
    *,
    wake_phrases: tuple[str, ...] = WAKE_PHRASES,
    threshold: float = DEFAULT_WAKE_THRESHOLD,
) -> WakeScore:
    """Score a transcript for wake-word use without inspecting raw audio."""
    normalized = normalize_transcript(transcript)
    exact = _exact_wake_detection(normalized, wake_phrases)
    if exact is not None:
        return WakeScore(
            detected=True,
            score=1.0,
            threshold=threshold,
            phrase=exact.phrase,
            command=exact.command,
            normalized=normalized,
            window=normalize_transcript(exact.phrase or ""),
            start_word_index=0,
            mode="exact_prefix",
        )

    fuzzy = _best_fuzzy_wake_match(normalized, wake_phrases)
    best_phrase = str(fuzzy["phrase"]) if fuzzy is not None else None
    best_score = float(fuzzy["score"]) if fuzzy is not None else 0.0
    best_window = str(fuzzy["window"]) if fuzzy is not None else ""
    best_start = int(fuzzy["start_word_index"]) if fuzzy is not None and fuzzy["start_word_index"] is not None else None
    detected = bool(best_phrase and best_score >= threshold)
    command = _clean_command(str(fuzzy["command"])) if detected and fuzzy is not None else ""
    return WakeScore(
        detected=detected,
        score=round(best_score, 6),
        threshold=threshold,
        phrase=best_phrase if detected else None,
        command=command,
        normalized=normalized,
        window=best_window,
        start_word_index=best_start,
        mode="fuzzy_window",
    )


def normalize_transcript(transcript: str) -> str:
    lowered = transcript.strip().lower()
    ascii_words = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(ascii_words.split())


def _exact_wake_detection(normalized: str, wake_phrases: tuple[str, ...]) -> WakeDetection | None:
    for phrase in wake_phrases:
        normalized_phrase = normalize_transcript(phrase)
        if normalized == normalized_phrase:
            return WakeDetection(True, phrase, "", True, normalized)
        prefix = f"{normalized_phrase} "
        if normalized.startswith(prefix):
            command = _clean_command(normalized.removeprefix(prefix))
            return WakeDetection(True, phrase, command, not bool(command), normalized)
    return None


def _best_fuzzy_wake_match(normalized: str, wake_phrases: tuple[str, ...]) -> dict[str, Any] | None:
    words = normalized.split()
    best: dict[str, Any] | None = None
    for phrase in wake_phrases:
        phrase_words = normalize_transcript(phrase).split()
        if not words or not phrase_words or len(words) < len(phrase_words):
            continue
        for index in range(0, len(words) - len(phrase_words) + 1):
            window_words = words[index : index + len(phrase_words)]
            score = _window_similarity(phrase_words, window_words)
            if best is None or score > float(best["score"]):
                command_words = words[index + len(phrase_words) :]
                best = {
                    "phrase": phrase,
                    "score": score,
                    "window": " ".join(window_words),
                    "start_word_index": index,
                    "command": " ".join(command_words).strip(),
                }
    return best


def _clean_command(value: str) -> str:
    return re.sub(r"^(please\s+)+", "", normalize_transcript(value)).strip()


def is_wake_greeting_echo(value: str) -> bool:
    return normalize_transcript(value) in {"yes", "yes sir", "yes sir yes sir"}


def _window_similarity(phrase_words: list[str], window_words: list[str]) -> float:
    if len(phrase_words) != len(window_words) or not phrase_words:
        return 0.0
    scores = [_word_similarity(left, right) for left, right in zip(phrase_words, window_words)]
    return sum(scores) / len(scores)


def _word_similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    distance = _levenshtein(left, right)
    width = max(len(left), len(right), 1)
    return max(0.0, 1.0 - distance / width)


def _levenshtein(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for row_index, left_char in enumerate(left, start=1):
        current = [row_index]
        for column_index, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            current.append(
                min(
                    previous[column_index] + 1,
                    current[column_index - 1] + 1,
                    previous[column_index - 1] + cost,
                )
            )
        previous = current
    return previous[-1]
