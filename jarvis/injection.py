"""Prompt-injection scanning helpers for untrusted text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .audit import redact_sensitive_text


MAX_EXCERPT_CHARS = 220


@dataclass(frozen=True)
class InjectionPattern:
    id: str
    label: str
    pattern: re.Pattern[str]


PROMPT_INJECTION_PATTERNS = [
    InjectionPattern(
        "instruction_override",
        "Instruction override",
        re.compile(r"\b(ignore|forget|override|bypass|disregard)\b.{0,80}\b(previous|prior|system|developer|safety)\b.{0,40}\b(instructions?|rules?|prompt)\b", re.IGNORECASE),
    ),
    InjectionPattern(
        "secret_extraction",
        "Secret extraction",
        re.compile(r"\b(reveal|show|print|copy|exfiltrate|send|leak)\b.{0,80}\b(secret|token|password|api\s*keys?|credential|system prompt|hidden prompt)\b", re.IGNORECASE),
    ),
    InjectionPattern(
        "hidden_behavior",
        "Hidden behavior",
        re.compile(r"\b(do not tell|don't tell|hide this|keep this secret|without (?:telling|notifying))\b.{0,80}\b(user|owner|leo)\b", re.IGNORECASE),
    ),
    InjectionPattern(
        "authority_impersonation",
        "Authority impersonation",
        re.compile(
            r"\b(?:this|the following|message|instruction)\b.{0,80}\b(?:is from|was written by|comes from|came from)\b.{0,80}\b(?:user|owner|leo|system|developer)\b"
            r"|\b(?:user|owner|leo|system|developer)\s+(?:says|said|instructs|requires|authorized|approved)\b",
            re.IGNORECASE,
        ),
    ),
    InjectionPattern(
        "external_transfer",
        "External transfer",
        re.compile(r"\b(send|upload|export|share|forward)\b.{0,80}\b(this|these|file|document|data|email|message|attachment)\b", re.IGNORECASE),
    ),
    InjectionPattern(
        "destructive_or_settings_change",
        "Destructive or settings change",
        re.compile(r"\b(delete|remove|overwrite|install|uninstall|change)\b.{0,80}\b(file|files|setting|settings|vpn|network|security|browser|shell|git|codex)\b", re.IGNORECASE),
    ),
]


def scan_untrusted_text(text: str, source: str = "untrusted text") -> dict[str, Any]:
    """Flag suspicious instructions in untrusted content without following them."""
    findings: list[dict[str, str]] = []
    for pattern in PROMPT_INJECTION_PATTERNS:
        match = pattern.pattern.search(text)
        if not match:
            continue
        findings.append(
            {
                "id": pattern.id,
                "label": pattern.label,
                "excerpt": _excerpt(text, match.start(), match.end()),
            }
        )
    return {
        "tool": "safety.injection_scan",
        "source": redact_sensitive_text(source),
        "status": "flagged" if findings else "clear",
        "requires_user_review": bool(findings),
        "findings": findings,
        "prototype_behavior": "Read-only scan. Suspicious untrusted text is flagged for review; it is not treated as a user instruction.",
    }


def _excerpt(text: str, start: int, end: int) -> str:
    left = max(0, start - 70)
    right = min(len(text), end + 70)
    excerpt = " ".join(text[left:right].split())
    if left > 0:
        excerpt = f"...{excerpt}"
    if right < len(text):
        excerpt = f"{excerpt}..."
    return redact_sensitive_text(excerpt[:MAX_EXCERPT_CHARS])
