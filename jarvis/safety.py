"""Safety classification and command policy for Jarvis."""

from __future__ import annotations

import re
import shlex
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import MAX_COMMAND_CHARS, PROJECT_ROOT


@dataclass(frozen=True)
class SafetyAssessment:
    risk_level: int
    risk_label: str
    decision: str
    requires_confirmation: bool
    requires_typed_confirmation: bool
    blocked: bool
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


RISK_LABELS = {
    0: "Local conversation",
    1: "Read-only local context",
    2: "Private read access",
    3: "Reversible change",
    4: "External/destructive/sensitive action",
}

PRIVATE_READ_PATTERNS = [
    r"\bemail\b",
    r"\boutlook\b",
    r"\bmail\b",
    r"\bcalendar\b",
    r"\bmessage\b",
    r"\bdocument\b",
]

REVERSIBLE_CHANGE_PATTERNS = [
    r"\bdraft\b",
    r"\bcreate\b",
    r"\bedit\b",
    r"\bwrite\b.{0,60}\b(file|document|email|message|note|draft|readme|\.md|\.txt|\.json|\.py|\.swift)\b",
    r"\bwrite\s+(to|into|in)\b",
    r"\bmove\b",
    r"\brename\b",
    r"\barchive\b",
]

READ_ONLY_SHELL_COMMANDS = {
    "pwd",
    "ls",
    "find",
    "rg",
    "grep",
    "cat",
    "sed",
    "awk",
    "head",
    "tail",
    "wc",
    "stat",
    "file",
    "which",
    "command",
    "git",
    "date",
    "uname",
}

VERSION_ONLY_SHELL_COMMANDS = {
    "python": {"--version", "-V"},
    "python3": {"--version", "-V"},
    "swift": {"--version"},
    "xcrun": {"--version"},
    "codex": {"--version"},
}

PROJECT_PATH_SHELL_COMMANDS = {
    "git",
    "ls",
    "find",
    "rg",
    "grep",
    "cat",
    "sed",
    "awk",
    "head",
    "tail",
    "wc",
    "stat",
    "file",
}

SECRET_PATH_HINTS = {
    ".ssh",
    ".gnupg",
    ".env",
    "id_rsa",
    "id_ed25519",
    "keychain",
    "password",
    "token",
    "secret",
    "credential",
}
SECRET_FILENAME_HINTS = {
    ".env",
    "id_rsa",
    "id_ed25519",
}
BARE_SECRET_FILENAME_HINTS = {
    "api_key",
    "apikey",
    "credential",
    "password",
    "passwd",
    "secret",
    "token",
}

GIT_READ_ONLY_SUBCOMMANDS = {
    "status",
    "diff",
    "log",
    "show",
    "branch",
    "remote",
    "rev-parse",
}

DANGEROUS_SHELL_TOKENS = {
    "sudo",
    "rm",
    "mv",
    "cp",
    "chmod",
    "chown",
    "kill",
    "killall",
    "pkill",
    "launchctl",
    "defaults",
    "security",
    "brew",
    "curl",
    "wget",
    "ssh",
    "scp",
    "rsync",
    "osascript",
}

DANGEROUS_SHELL_PATTERNS = [
    r"\brm\s+-[^\n]*r",
    r"\bbrew\s+(install|uninstall|upgrade|services)\b",
    r"\bgit\s+(push|reset|checkout|switch|clean|rebase|merge|commit|pull)\b",
    r"\bdefaults\s+write\b",
    r"\bcurl\b.*\|\s*(sh|bash|zsh)",
    r"\bwget\b.*\|\s*(sh|bash|zsh)",
    r">\s*[/~\w.-]+",
    r"\|\s*(sh|bash|zsh)\b",
]

SHELL_CONTROL_TOKENS = {";", "&&", "||", "|", "&", ">", ">>", "<", "<<", "2>", "2>>", "&>", ">&"}
SHELL_REDIRECTION_PREFIXES = (">", ">>", "<", "<<", "2>", "2>>", "&>", ">&")

MUTATING_SHELL_OPTIONS = {
    "find": {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls"},
    "sed": {"-i", "--in-place", "-f", "--file"},
    "awk": {"-f", "--file"},
    "git": {"--output"},
}

EMBEDDED_CODE_SHELL_PATTERNS = {
    "awk": [r"\bsystem\s*\(", r">\s*['\"]?[/~\w.-]+"],
}

SED_WRITE_COMMAND_PATTERN = re.compile(
    r"(?:^|[;\n{}])\s*(?:[0-9,$]+(?:,[0-9,$]+)?|/[^/]+/)?\s*w\s+\S+|\bw\s+\S+",
    re.IGNORECASE,
)


def policy_summary() -> dict[str, Any]:
    return {
        "risk_labels": RISK_LABELS,
        "strong_confirmation": [
            "Sending or forwarding email/messages/posts/forms.",
            "Uploading, exporting, sharing, or transmitting private data.",
            "Revealing credentials, tokens, keys, passwords, or account data.",
            "Deleting, overwriting, moving, or renaming important files.",
            "Changing system, network, VPN, browser, shell, Git, Codex, or security settings.",
            "Installing or uninstalling software.",
            "Running sudo, destructive shell patterns, or scripts piped from the internet.",
            "Payments, purchases, subscriptions, or financial/account changes.",
        ],
        "private_read_policy": "Read-only private summaries may proceed after permission, must stay local, and must be visibly logged.",
        "pause_policy": "When paused, /api/command refuses every command at the server boundary while health, mode, policy, tools, readiness, self-check, and audit endpoints remain available.",
        "start_paused_policy": "JARVIS_START_PAUSED=1 or scripts/run_dashboard.py --paused starts command execution paused for cautious local launches.",
        "network_policy": "The dashboard binds only to loopback hosts by default; non-loopback binds require JARVIS_ALLOW_NON_LOOPBACK=1.",
        "request_policy": "Command, plan, and mode POST endpoints require application/json request bodies and reject malformed JSON before routing.",
        "natural_language_policy": {
            "requires_strong_confirmation": [
                "External transmission such as sending, forwarding, posting, submitting, uploading, downloading, sharing, or exporting.",
                "File or software changes such as deleting, removing, overwriting, installing, or uninstalling.",
                "Protected setting changes for system, security, network, VPN, browser, shell, Git, or Codex configuration.",
                "Privileged or destructive shell-like execution such as sudo, rm -rf, chmod, chown, killall, launchctl, or defaults write.",
                "Credential or account access such as passwords, tokens, API keys, secrets, cookies, credentials, or Keychain data.",
                "Payments, purchases, subscriptions, or financial/account changes.",
            ],
        },
        "shell_policy": {
            "execution": "Allowed shell commands run with argv and shell=False.",
            "auto_execute": [
                "Project-local read-only metadata and file inspection commands.",
                "Version metadata for python, swift, xcrun, and Codex.",
                "Read-only Git subcommands only.",
            ],
            "requires_confirmation": [
                "Unknown executables.",
                "Paths outside the project folder.",
            ],
            "requires_strong_confirmation": [
                "Shell chaining, piping, backgrounding, substitution, or redirection.",
                "Code-runner commands beyond version metadata.",
                "Secret-looking paths and bare secret-bearing filenames.",
                "Mutating options, write scripts, or external script files on otherwise read-only tools, such as `find -delete`, `find -exec`, `sed -i`, `sed 'w file'`, or `awk -f script.awk`.",
                "Dangerous commands or destructive patterns.",
            ],
        },
        "audit_policy": {
            "retention_days": 90,
            "size_cap": "1 GB",
            "raw_audio_or_screenshots": "Never stored by default.",
        },
    }


def classify_command(command: str) -> SafetyAssessment:
    text = command.strip()
    lower = text.lower()
    reasons: list[str] = []

    if not text:
        return SafetyAssessment(0, RISK_LABELS[0], "idle", False, False, False, ["No command text."])
    if len(text) > MAX_COMMAND_CHARS:
        return SafetyAssessment(
            4,
            RISK_LABELS[4],
            "blocked",
            True,
            True,
            True,
            [f"Command is longer than {MAX_COMMAND_CHARS} characters."],
        )
    if lower.startswith(("wake:", "simulate wake ")) or re.match(r"^(hey|ok|okay)\s+jarvis\b", lower):
        reasons.append("Command is a text-only wake phrase simulation.")
        return SafetyAssessment(1, RISK_LABELS[1], "allowed", False, False, False, reasons)
    if lower.startswith(("scan untrusted:", "scan untrusted text:", "scan prompt injection:", "scan prompt-injection:")):
        reasons.append("Command is a read-only prompt-injection scan of untrusted text.")
        return SafetyAssessment(1, RISK_LABELS[1], "allowed", False, False, False, reasons)
    if _looks_like_codex_job_status_query(text):
        reasons.append("Command checks local Codex status only.")
        return SafetyAssessment(1, RISK_LABELS[1], "allowed", False, False, False, reasons)
    high_risk_reasons = _external_or_sensitive_reasons(lower)
    if high_risk_reasons:
        reasons.extend(high_risk_reasons)
        return SafetyAssessment(4, RISK_LABELS[4], "needs_typed_confirmation", True, True, False, reasons)
    if lower.startswith(("find ", "search ")):
        reasons.append("Command appears to be a read-only file search.")
        return SafetyAssessment(1, RISK_LABELS[1], "allowed", False, False, False, reasons)
    if _looks_like_shell(text):
        return classify_shell_command(_strip_shell_prefix(text))
    if _matches_any(lower, REVERSIBLE_CHANGE_PATTERNS):
        reasons.append("Command may create or change local state.")
        return SafetyAssessment(3, RISK_LABELS[3], "needs_confirmation", True, False, False, reasons)
    if _matches_any(lower, PRIVATE_READ_PATTERNS):
        reasons.append("Command may read private local app content.")
        return SafetyAssessment(2, RISK_LABELS[2], "allowed_with_visible_logging", False, False, False, reasons)
    if any(word in lower for word in ["status", "find", "search", "check", "list", "open"]):
        reasons.append("Command appears read-only or low-risk.")
        return SafetyAssessment(1, RISK_LABELS[1], "allowed", False, False, False, reasons)
    return SafetyAssessment(0, RISK_LABELS[0], "allowed", False, False, False, ["No protected action detected."])


def classify_shell_command(command: str) -> SafetyAssessment:
    text = command.strip()
    lower = text.lower()
    reasons: list[str] = []
    if not text:
        return SafetyAssessment(0, RISK_LABELS[0], "idle", False, False, False, ["No shell command."])
    if _matches_any(lower, DANGEROUS_SHELL_PATTERNS):
        return SafetyAssessment(
            4,
            RISK_LABELS[4],
            "needs_typed_confirmation",
            True,
            True,
            False,
            ["Shell command matches a dangerous pattern."],
        )
    try:
        parts = shlex.split(text)
    except ValueError as exc:
        return SafetyAssessment(
            4,
            RISK_LABELS[4],
            "blocked",
            True,
            True,
            True,
            [f"Shell command could not be parsed safely: {exc}"],
        )
    if not parts:
        return SafetyAssessment(0, RISK_LABELS[0], "idle", False, False, False, ["No shell command."])
    if _has_shell_control(text, parts):
        return SafetyAssessment(
            4,
            RISK_LABELS[4],
            "needs_typed_confirmation",
            True,
            True,
            False,
            ["Shell command contains chaining, piping, backgrounding, substitution, or other shell control syntax."],
        )
    executable = parts[0]
    if executable in DANGEROUS_SHELL_TOKENS:
        return SafetyAssessment(
            4,
            RISK_LABELS[4],
            "needs_typed_confirmation",
            True,
            True,
            False,
            [f"`{executable}` is not an auto-executable prototype command."],
        )
    if executable == "git" and len(parts) > 1 and parts[1] not in GIT_READ_ONLY_SUBCOMMANDS:
        return SafetyAssessment(
            4,
            RISK_LABELS[4],
            "needs_typed_confirmation",
            True,
            True,
            False,
            [f"`git {parts[1]}` is not read-only."],
        )
    if executable in VERSION_ONLY_SHELL_COMMANDS:
        allowed_args = VERSION_ONLY_SHELL_COMMANDS[executable]
        if len(parts) == 2 and parts[1] in allowed_args:
            reasons.append("Shell command is read-only version metadata.")
            return SafetyAssessment(1, RISK_LABELS[1], "allowed", False, False, False, reasons)
        return SafetyAssessment(
            4,
            RISK_LABELS[4],
            "needs_typed_confirmation",
            True,
            True,
            False,
            [f"`{executable}` can execute code or change local state unless restricted to version metadata."],
        )
    if executable not in READ_ONLY_SHELL_COMMANDS:
        return SafetyAssessment(
            3,
            RISK_LABELS[3],
            "needs_confirmation",
            True,
            False,
            False,
            [f"`{executable}` is not in the read-only shell allowlist."],
        )
    mutating_assessment = _classify_mutating_shell_options(executable, parts, text)
    if mutating_assessment is not None:
        return mutating_assessment
    if executable in PROJECT_PATH_SHELL_COMMANDS:
        path_assessment = _classify_shell_paths(parts)
        if path_assessment is not None:
            return path_assessment
    reasons.append("Shell command is in the read-only allowlist.")
    return SafetyAssessment(1, RISK_LABELS[1], "allowed", False, False, False, reasons)


def _looks_like_codex_job_status_query(command: str) -> bool:
    stripped = command.strip()
    lower = stripped.lower()
    if lower in {
        "codex jobs",
        "codex job status",
        "check codex jobs",
        "codex status",
        "codex speed status",
        "codex chat status",
        "codex chats",
        "codex activity",
        "codex activity status",
        "codex progress",
        "codex job activity",
        "what is codex doing",
        "is codex working",
        "codex memory status",
        "jarvis codex memory status",
        "jarvis-codex memory status",
    }:
        return True
    if re.match(r"(?i)^codex\s+job(?:\s+(?:status|result))?\s+[A-Za-z0-9-]+$", stripped):
        return True
    if re.match(r"(?i)^(?:check|get|show)\s+codex\s+job\s+[A-Za-z0-9-]+$", stripped):
        return True
    if re.match(r"(?i)^(?:check|get|show|what|which)\b.*\bcodex\b.*\b(?:status|speed|latency|chat|chats|default|memory)\b", stripped):
        return True
    return False


def is_shell_allowed(command: str) -> bool:
    assessment = classify_shell_command(command)
    return not assessment.blocked and not assessment.requires_confirmation


def _matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _external_or_sensitive_reasons(text: str) -> list[str]:
    checks = [
        (
            [
                r"\bsend\b",
                r"\bforward\b",
                r"\bpost\b",
                r"\bsubmit\b",
                r"\bupload\b",
                r"\bdownload\b",
                r"\bshare\b",
                r"\bexport\b",
            ],
            "Command appears to involve external transmission, sharing, export, or download.",
        ),
        (
            [
                r"\bdelete\b",
                r"\bremove\b",
                r"\boverwrite\b",
                r"\binstall\b",
                r"\buninstall\b",
            ],
            "Command appears to modify files or software.",
        ),
        (
            [
                r"\b(system|security|network|vpn|browser|shell|git|codex)\s+settings\b",
                r"\bchange\s+(system|security|network|vpn|browser|shell|git|codex)\b",
                r"\b(change|edit|modify)\b.{0,40}\b(settings?|preferences?|configuration|config)\b",
            ],
            "Command appears to change protected system, app, network, or developer settings.",
        ),
        (
            [
                r"\bsudo\b",
                r"\brm\s+-[^\n]*r",
                r"\bchmod\b",
                r"\bchown\b",
                r"\bkillall\b",
                r"\blaunchctl\b",
                r"\bdefaults\s+write\b",
            ],
            "Command appears to request privileged or destructive shell-like execution.",
        ),
        (
            [
                r"\bkeychain\b",
                r"\bcookies?\b",
                r"\bpassword\b",
                r"\btoken\b",
                r"\bapi\s*keys?\b",
                r"\bsecret\b",
                r"\bcredential\b",
                r"\bid_rsa\b",
                r"\bid_ed25519\b",
                r"(?<!\w)\.env\b",
            ],
            "Command appears to request credentials, cookies, Keychain data, or other secrets.",
        ),
        (
            [
                r"\bpay\b",
                r"\bpurchase\b",
                r"\bsubscribe\b",
                r"\bunsubscribe\b",
            ],
            "Command appears to involve payments, purchases, subscriptions, or account changes.",
        ),
    ]
    reasons: list[str] = []
    for patterns, reason in checks:
        if _matches_any(text, patterns):
            reasons.append(reason)
    return reasons


def _looks_like_shell(command: str) -> bool:
    lower = command.strip().lower()
    if lower.startswith(("shell:", "$ ")):
        return True
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    shell_commands = READ_ONLY_SHELL_COMMANDS.union(DANGEROUS_SHELL_TOKENS).union(VERSION_ONLY_SHELL_COMMANDS)
    return bool(parts and parts[0] in shell_commands)


def _strip_shell_prefix(command: str) -> str:
    stripped = command.strip()
    if stripped.lower().startswith("shell:"):
        return stripped.split(":", 1)[1].strip()
    if stripped.startswith("$ "):
        return stripped[2:].strip()
    return stripped


def _has_shell_control(text: str, parts: list[str]) -> bool:
    if "$(" in text or "`" in text:
        return True
    if any(token in SHELL_CONTROL_TOKENS for token in parts):
        return True
    if any(_starts_with_redirection(part) for part in parts):
        return True
    return any(part.endswith(";") for part in parts)


def _starts_with_redirection(part: str) -> bool:
    return any(part.startswith(prefix) and part != prefix for prefix in SHELL_REDIRECTION_PREFIXES)


def _classify_shell_paths(parts: list[str]) -> SafetyAssessment | None:
    for token in parts[1:]:
        lower = token.lower()
        if _is_secret_like_path_token(lower):
            return SafetyAssessment(
                4,
                RISK_LABELS[4],
                "needs_typed_confirmation",
                True,
                True,
                False,
                ["Shell command references a secret-looking path."],
            )
        if _is_option_or_pattern(token):
            continue
        if _is_outside_project_path(token):
            return SafetyAssessment(
                3,
                RISK_LABELS[3],
                "needs_confirmation",
                True,
                False,
                False,
                ["Shell command references a path outside the project folder."],
            )
    return None


def _classify_mutating_shell_options(executable: str, parts: list[str], text: str) -> SafetyAssessment | None:
    dangerous_options = MUTATING_SHELL_OPTIONS.get(executable, set())
    if any(_matches_shell_option(part, option) for part in parts[1:] for option in dangerous_options):
        return SafetyAssessment(
            4,
            RISK_LABELS[4],
            "needs_typed_confirmation",
            True,
            True,
            False,
            [f"`{executable}` command includes an option that can modify files or execute commands."],
        )

    patterns = EMBEDDED_CODE_SHELL_PATTERNS.get(executable, [])
    if _matches_any(text, patterns):
        return SafetyAssessment(
            4,
            RISK_LABELS[4],
            "needs_typed_confirmation",
            True,
            True,
            False,
            [f"`{executable}` command includes embedded code that can execute commands or write files."],
        )
    if executable == "sed" and _sed_scripts_include_write(parts):
        return SafetyAssessment(
            4,
            RISK_LABELS[4],
            "needs_typed_confirmation",
            True,
            True,
            False,
            ["`sed` script includes a write command."],
        )
    return None


def _matches_shell_option(part: str, option: str) -> bool:
    if part == option or part.startswith(f"{option}="):
        return True
    return option == "-i" and part.startswith("-i")


def _sed_scripts_include_write(parts: list[str]) -> bool:
    scripts: list[str] = []
    first_script_seen = False
    index = 1
    while index < len(parts):
        part = parts[index]
        if part in {"-e", "--expression"} and index + 1 < len(parts):
            scripts.append(parts[index + 1])
            first_script_seen = True
            index += 2
            continue
        if part.startswith("-e") and len(part) > 2:
            scripts.append(part[2:])
            first_script_seen = True
            index += 1
            continue
        if part.startswith("--expression="):
            scripts.append(part.split("=", 1)[1])
            first_script_seen = True
            index += 1
            continue
        if part.startswith("-"):
            index += 1
            continue
        if not first_script_seen:
            scripts.append(part)
            first_script_seen = True
        index += 1
    return any(SED_WRITE_COMMAND_PATTERN.search(script) for script in scripts)


def _is_secret_like_path_token(lower_token: str) -> bool:
    if lower_token in SECRET_FILENAME_HINTS:
        return True
    filename = lower_token.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    if filename.startswith(("id_rsa", "id_ed25519")):
        return True
    if _is_bare_secret_filename(filename):
        return True
    path_like = lower_token.startswith((".", "~", "/")) or "/" in lower_token or ":" in lower_token
    return path_like and any(hint in lower_token for hint in SECRET_PATH_HINTS)


def _is_bare_secret_filename(filename: str) -> bool:
    if "." not in filename:
        return False
    return any(hint in filename for hint in BARE_SECRET_FILENAME_HINTS)


def _is_option_or_pattern(token: str) -> bool:
    if not token:
        return True
    if token == ".":
        return True
    if token.startswith("-"):
        return True
    if any(character in token for character in "*?[]"):
        return True
    if "/" not in token and not token.startswith(("~", ".")):
        return True
    return False


def _is_outside_project_path(token: str) -> bool:
    candidate = Path(token).expanduser()
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        resolved = candidate.absolute()
    return not resolved.is_relative_to(PROJECT_ROOT.resolve())
