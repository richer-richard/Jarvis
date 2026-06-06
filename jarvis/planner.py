"""Heuristic planner for the first Jarvis prototype."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .safety import DANGEROUS_SHELL_TOKENS, READ_ONLY_SHELL_COMMANDS, VERSION_ONLY_SHELL_COMMANDS, classify_command
from .wake import detect_wake_command
from .tools import (
    app_availability,
    browser_open_url_plan,
    capabilities_status,
    codex_speed_status,
    codex_job_status,
    codex_delegate_plan,
    email_backend_status,
    elevation_status,
    fast_model_status,
    find_files,
    launch_status,
    latest_latency_status,
    memory_status,
    outlook_read_only_check,
    outlook_read_only_plan,
    prompt_injection_scan,
    quick_local_control,
    remote_worker_status,
    run_codex_chat,
    run_codex_delegate,
    run_fast_local_chat,
    run_read_only_shell,
    safety_status,
    select_tool_intent,
    screenshot_capability,
    source_access_status,
    start_codex_continue_job,
    start_codex_delegate_job,
    system_status,
    tts_status,
    wake_status,
    wake_phrase_simulation,
)


NATURAL_LANGUAGE_TOOL_SPECS = [
    {
        "tool": "outlook.visible_summary",
        "description": "Read and summarize local mailbox content. Use only when the user wants Jarvis to inspect email messages.",
        "entities": ["sender_query", "selection"],
    },
    {
        "tool": "diagnostics.email",
        "description": "Report email backend or route readiness without reading email content.",
        "entities": [],
    },
    {
        "tool": "screenshot.capability",
        "description": "Report screen capture, OCR, or screenshot capability/status; do not read email content.",
        "entities": [],
    },
    {
        "tool": "browser.open_url",
        "description": "Prepare a browser URL action when the user asks to open a URL or browser target.",
        "entities": ["url"],
    },
    {
        "tool": "codex.job",
        "description": "Start deeper Codex work for code, repo, debugging, build, implementation, or review tasks.",
        "entities": [],
    },
    {
        "tool": "conversation.fast_local",
        "description": "Ordinary conversation or requests that do not need a tool.",
        "entities": [],
    },
]


@dataclass
class PlannedResult:
    command: str
    tool: str
    summary: str
    assessment: dict[str, Any]
    result: dict[str, Any]
    executed: bool
    confirmation: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Planner:
    """Small typed-tool planner until model routing is wired in."""

    def handle_selected_tool(self, command: str, selected_tool: str, entities: dict[str, Any] | None = None) -> PlannedResult | None:
        text = command.strip()
        assessment = classify_command(text)
        if assessment.blocked:
            return self._result(text, "policy.block", "Command blocked by safety policy.", assessment, {}, False)
        if assessment.requires_typed_confirmation:
            return self._result(
                text,
                "policy.strong_confirmation",
                "Command requires strong confirmation and was not executed.",
                assessment,
                {"next_step": "Show a typed confirmation prompt in the Jarvis UI."},
                False,
                confirmation=_confirmation(
                    kind="typed",
                    title="Strong Confirmation Required",
                    message="This command could affect external data, secrets, settings, files, or other hard-to-undo state.",
                    exact_phrase="JARVIS APPROVE",
                    prototype_note="The prototype records this confirmation requirement but does not execute protected actions.",
                ),
            )
        if assessment.requires_confirmation:
            return self._result(
                text,
                "policy.confirmation",
                "Command requires confirmation and was not executed.",
                assessment,
                {"next_step": "Show a confirmation prompt in the Jarvis UI."},
                False,
                confirmation=_confirmation(
                    kind="standard",
                    title="Confirmation Required",
                    message="This command may change local state and needs user approval before execution.",
                    exact_phrase=None,
                    prototype_note="The prototype records this confirmation requirement but does not execute protected actions.",
                ),
            )
        intent = {
            "status": "completed",
            "selected_tool": selected_tool,
            "confidence": 1.0,
            "entities": entities or {},
            "reason": "Selected by fast chat tool request.",
        }
        return self._handle_model_intent(text, assessment, intent, execute=True)

    def handle(
        self,
        command: str,
        *,
        history: list[dict[str, str]] | None = None,
        use_model_router: bool = True,
    ) -> PlannedResult:
        text = command.strip()
        assessment = classify_command(text)
        lower = text.lower()
        codex_job_query = _extract_codex_job_query(text)

        if assessment.blocked:
            return self._result(text, "policy.block", "Command blocked by safety policy.", assessment, {}, False)
        if codex_job_query is not None:
            result = codex_job_status(codex_job_query)
            return self._result(text, "codex.job", "Checked Codex job status.", assessment, result, False)
        if _looks_like_codex_speed_status(lower):
            return self._result(text, "diagnostics.codex_speed", "Read local Codex speed status.", assessment, codex_speed_status(), True)
        if assessment.requires_typed_confirmation:
            return self._result(
                text,
                "policy.strong_confirmation",
                "Command requires strong confirmation and was not executed.",
                assessment,
                {"next_step": "Show a typed confirmation prompt in the Jarvis UI."},
                False,
                confirmation=_confirmation(
                    kind="typed",
                    title="Strong Confirmation Required",
                    message="This command could affect external data, secrets, settings, files, or other hard-to-undo state.",
                    exact_phrase="JARVIS APPROVE",
                    prototype_note="The prototype records this confirmation requirement but does not execute protected actions.",
                ),
            )
        if assessment.requires_confirmation:
            return self._result(
                text,
                "policy.confirmation",
                "Command requires confirmation and was not executed.",
                assessment,
                {"next_step": "Show a confirmation prompt in the Jarvis UI."},
                False,
                confirmation=_confirmation(
                    kind="standard",
                    title="Confirmation Required",
                    message="This command may change local state and needs user approval before execution.",
                    exact_phrase=None,
                    prototype_note="The prototype records this confirmation requirement but does not execute protected actions.",
                ),
            )
        if _looks_like_codex_continuation(text, history):
            result = start_codex_continue_job(text, history=history)
            summary = "Continued Codex CLI job." if result.get("status") == "running" else "Tried to continue Codex CLI job."
            return self._result(text, "codex.job", summary, assessment, result, bool(result.get("executed")))
        wake_transcript = _extract_wake_transcript(text)
        if wake_transcript is not None:
            return self._result(text, "voice.wake_simulation", "Ran text-only wake phrase simulation.", assessment, wake_phrase_simulation(wake_transcript), True)
        if lower.startswith(("shell:", "$ ")):
            shell_command = text.split(":", 1)[1].strip() if lower.startswith("shell:") else text[2:].strip()
            result = run_read_only_shell(shell_command)
            return self._result(
                text,
                "shell.read_only",
                "Read-only shell command processed.",
                assessment,
                result,
                bool(result.get("executed")),
            )
        if lower.startswith("find ") or lower.startswith("search "):
            query = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""
            return self._result(text, "files.search", "Searched project files by name.", assessment, find_files(query), True)
        injection_text = _extract_injection_scan_text(text)
        if injection_text is not None:
            return self._result(text, "safety.injection_scan", "Scanned untrusted text for prompt-injection patterns.", assessment, prompt_injection_scan(injection_text), True)
        if _looks_like_shell_command(text):
            result = run_read_only_shell(text)
            return self._result(text, "shell.read_only", "Read-only shell command processed.", assessment, result, bool(result.get("executed")))
        if _looks_like_latency_status(lower):
            return self._result(text, "diagnostics.latency", "Read local fast-latency status.", assessment, latest_latency_status(), True)
        if _looks_like_fast_model_status(lower):
            return self._result(text, "diagnostics.fast_model", "Read local fast-model status.", assessment, fast_model_status(), True)
        if _looks_like_remote_worker_status(lower):
            return self._result(text, "diagnostics.remote_worker", "Read remote MacBook Air worker status.", assessment, remote_worker_status(), True)
        if _looks_like_elevation_status(lower):
            return self._result(text, "diagnostics.elevation", "Read Jarvis elevation routing status.", assessment, elevation_status(), True)
        if _looks_like_memory_status(lower):
            return self._result(text, "diagnostics.memory", "Read Jarvis memory design status without reading chat history.", assessment, memory_status(), True)
        if _looks_like_source_access_status(lower):
            return self._result(text, "diagnostics.source_access", "Read Jarvis source access status.", assessment, source_access_status(), True)
        if _looks_like_tts_status(lower):
            return self._result(text, "diagnostics.tts", "Read local TTS status.", assessment, tts_status(), True)
        if _looks_like_screen_status(lower):
            return self._result(text, "screenshot.capability", "Read local screen capability status.", assessment, screenshot_capability(), True)
        if _looks_like_launch_status(lower):
            return self._result(text, "diagnostics.launch", "Read local Jarvis launch status.", assessment, launch_status(), True)
        if _looks_like_wake_status(lower):
            return self._result(text, "diagnostics.wake", "Read local Jarvis wake status.", assessment, wake_status(), True)
        if _is_exact_email_status_command(lower):
            return self._result(text, "diagnostics.email", "Read local email backend status without reading email content.", assessment, email_backend_status(), True)
        if _looks_like_capability_status(lower):
            return self._result(text, "diagnostics.capabilities", "Read local Jarvis capability status.", assessment, capabilities_status(), True)
        if _looks_like_safety_status(lower):
            return self._result(text, "diagnostics.safety", "Read local Jarvis safety status.", assessment, safety_status(), True)
        quick_result = quick_local_control(text)
        if quick_result.get("matched"):
            summary = "Handled quick local command." if quick_result.get("status") == "completed" else "Tried quick local command."
            return self._result(text, "quick.local_control", summary, assessment, quick_result, bool(quick_result.get("executed")))
        if lower in {"status", "health", "check status", "jarvis status"}:
            return self._result(text, "system.status", "Collected local Jarvis status.", assessment, system_status(), True)
        app_name = _extract_app_name(text)
        if app_name is not None:
            return self._result(text, "app.availability", "Checked local app availability.", assessment, app_availability(app_name), True)
        exact_reply = _extract_exact_reply(text)
        if exact_reply is not None and not _explicitly_asks_codex(lower):
            return self._result(
                text,
                "conversation.local_exact",
                "Answered exact-output request locally.",
                assessment,
                {
                    "tool": "conversation.local_exact",
                    "status": "completed",
                    "executed": True,
                    "reply": exact_reply,
                },
                True,
            )
        if _explicitly_asks_codex(lower):
            routed = self._handle_model_intent(text, assessment, _explicit_codex_intent(), execute=True)
            if routed is not None:
                return routed
        if use_model_router:
            intent = select_tool_intent(text, NATURAL_LANGUAGE_TOOL_SPECS)
            routed = self._handle_model_intent(text, assessment, intent, execute=True)
            if routed is not None:
                return routed
            result = run_fast_local_chat(text, history=history)
        else:
            result = run_fast_local_chat(text, history=history, tool_specs=NATURAL_LANGUAGE_TOOL_SPECS)
            if result.get("status") == "tool_requested":
                routed = self.handle_selected_tool(
                    text,
                    str(result.get("selected_tool") or ""),
                    result.get("entities") if isinstance(result.get("entities"), dict) else {},
                )
                if routed is not None:
                    return routed
        tool = str(result.get("tool") or "conversation.fast_local")
        if result.get("status") == "completed":
            summary = "Answered through fast local chat."
        else:
            summary = "Answered with fast local fallback."
        if result.get("duration_human"):
            summary = f"{summary} Fast model time: {result['duration_human']}."
        return self._result(text, tool, summary, assessment, result, bool(result.get("executed", True)))

    def preview(self, command: str, *, use_model_router: bool = True) -> PlannedResult:
        text = command.strip()
        assessment = classify_command(text)
        lower = text.lower()

        if assessment.blocked:
            return self._preview_result(text, "policy.block", assessment, False)
        if assessment.requires_typed_confirmation:
            return self._preview_result(
                text,
                "policy.strong_confirmation",
                assessment,
                False,
                confirmation=_confirmation(
                    kind="typed",
                    title="Strong Confirmation Required",
                    message="This command could affect external data, secrets, settings, files, or other hard-to-undo state.",
                    exact_phrase="JARVIS APPROVE",
                    prototype_note="Preview only. No protected action was executed.",
                ),
            )
        if assessment.requires_confirmation:
            return self._preview_result(
                text,
                "policy.confirmation",
                assessment,
                False,
                confirmation=_confirmation(
                    kind="standard",
                    title="Confirmation Required",
                    message="This command may change local state and needs user approval before execution.",
                    exact_phrase=None,
                    prototype_note="Preview only. No protected action was executed.",
                ),
            )
        codex_job_query = _extract_codex_job_query(text)
        if codex_job_query is not None:
            return self._preview_result(text, "codex.job", assessment, False)
        if _looks_like_same_codex_reference(text):
            return self._preview_result(
                text,
                "codex.job",
                assessment,
                True,
                plan={
                    "selected_tool": "codex.job",
                    "execution_mode": "async_continuation",
                    "continuation": True,
                },
            )
        if _looks_like_codex_speed_status(lower):
            return self._preview_result(text, "diagnostics.codex_speed", assessment, True)
        if lower.startswith("find ") or lower.startswith("search "):
            return self._preview_result(text, "files.search", assessment, True)
        if _extract_wake_transcript(text) is not None:
            return self._preview_result(text, "voice.wake_simulation", assessment, True)
        if _extract_injection_scan_text(text) is not None:
            return self._preview_result(text, "safety.injection_scan", assessment, True)
        if lower.startswith(("shell:", "$ ")) or _looks_like_shell_command(text):
            return self._preview_result(text, "shell.read_only", assessment, True)
        if _looks_like_latency_status(lower):
            return self._preview_result(text, "diagnostics.latency", assessment, True)
        if _looks_like_fast_model_status(lower):
            return self._preview_result(text, "diagnostics.fast_model", assessment, True)
        if _looks_like_source_access_status(lower):
            return self._preview_result(text, "diagnostics.source_access", assessment, True)
        if _looks_like_tts_status(lower):
            return self._preview_result(text, "diagnostics.tts", assessment, True)
        if _looks_like_screen_status(lower):
            return self._preview_result(text, "screenshot.capability", assessment, True)
        if _looks_like_launch_status(lower):
            return self._preview_result(text, "diagnostics.launch", assessment, True)
        if _looks_like_wake_status(lower):
            return self._preview_result(text, "diagnostics.wake", assessment, True)
        if _is_exact_email_status_command(lower):
            return self._preview_result(text, "diagnostics.email", assessment, True)
        if _looks_like_capability_status(lower):
            return self._preview_result(text, "diagnostics.capabilities", assessment, True)
        if _looks_like_safety_status(lower):
            return self._preview_result(text, "diagnostics.safety", assessment, True)
        if lower in {"status", "health", "check status", "jarvis status"}:
            return self._preview_result(text, "system.status", assessment, True)
        quick_result = quick_local_control(text, execute=False)
        if quick_result.get("matched"):
            return self._preview_result(
                text,
                "quick.local_control",
                assessment,
                bool(quick_result.get("executed")),
                plan=quick_result,
            )
        if _extract_app_name(text) is not None:
            return self._preview_result(text, "app.availability", assessment, True)
        exact_reply = _extract_exact_reply(text)
        if exact_reply is not None and not _explicitly_asks_codex(lower):
            return self._preview_result(text, "conversation.local_exact", assessment, True)
        if _explicitly_asks_codex(lower):
            routed = self._handle_model_intent(text, assessment, _explicit_codex_intent(), execute=False)
            if routed is not None:
                return routed
        if use_model_router:
            intent = select_tool_intent(text, NATURAL_LANGUAGE_TOOL_SPECS)
            routed = self._handle_model_intent(text, assessment, intent, execute=False)
            if routed is not None:
                return routed
        return self._preview_result(text, "conversation.fast_local", assessment, True)

    def _handle_model_intent(
        self,
        text: str,
        assessment: Any,
        intent: dict[str, Any],
        *,
        execute: bool,
    ) -> PlannedResult | None:
        selected_tool = str(intent.get("selected_tool") or "conversation.fast_local")
        if selected_tool == "conversation.fast_local":
            return None
        if intent.get("status") != "completed":
            return None
        entities = intent.get("entities") if isinstance(intent.get("entities"), dict) else {}
        if selected_tool == "diagnostics.email":
            if not execute:
                return self._preview_result(text, "diagnostics.email", assessment, True, plan={"intent": intent})
            return self._result(text, "diagnostics.email", "Read local email backend status without reading email content.", assessment, email_backend_status(), True)
        if selected_tool == "outlook.visible_summary":
            sender_query = _clean_optional_entity(entities.get("sender_query")) or _extract_email_sender_constraint(text)
            selection = _clean_optional_entity(entities.get("selection")) or _extract_email_selection_constraint(text)
            if not execute:
                return PlannedResult(
                    command=text,
                    tool="outlook.visible_summary",
                    summary="Command preview prepared by local intent router. No email was read.",
                    assessment=assessment.to_dict(),
                    result={
                        "planned_only": True,
                        "would_execute_if_run": True,
                        "selected_tool": "outlook.visible_summary",
                        "intent": intent,
                        "sender_query": sender_query,
                        "selection": selection,
                        "plan": outlook_read_only_plan(),
                    },
                    executed=False,
                    confirmation=None,
                )
            result = outlook_read_only_check(sender_query=sender_query, selection=selection, original_prompt=text)
            summary = "Checked read-only email summary." if result.get("status") == "checked" else "Tried read-only email summary."
            return self._result(text, "outlook.visible_summary", summary, assessment, result, True)
        if selected_tool == "screenshot.capability":
            if not execute:
                return self._preview_result(text, "screenshot.capability", assessment, True, plan={"intent": intent})
            return self._result(text, "screenshot.capability", "Checked screenshot capability.", assessment, screenshot_capability(), True)
        if selected_tool == "browser.open_url":
            url = _clean_optional_entity(entities.get("url")) or _extract_url(text)
            if not execute:
                return self._preview_result(text, "browser.open_url", assessment, False, plan={"intent": intent, "url": url})
            return self._result(text, "browser.open_url", "Prepared browser-open plan.", assessment, browser_open_url_plan(url), False)
        if selected_tool == "codex.job":
            if _should_run_codex_synchronously(text.lower()):
                if not execute:
                    return PlannedResult(
                        command=text,
                        tool="codex.delegate",
                        summary="Codex CLI preview prepared by local intent router. No Codex job was executed.",
                        assessment=assessment.to_dict(),
                        result={
                            "planned_only": True,
                            "would_execute_if_run": True,
                            "selected_tool": "codex.delegate",
                            "execution_mode": "sync",
                            "intent": intent,
                            "plan": codex_delegate_plan(text),
                        },
                        executed=False,
                        confirmation=None,
                    )
                result = run_codex_delegate(text)
                summary = "Ran Codex CLI delegation." if result.get("status") == "completed" else "Tried Codex CLI delegation."
                if result.get("duration_human"):
                    summary = f"{summary} Codex time: {result['duration_human']}."
                return self._result(text, "codex.delegate", summary, assessment, result, bool(result.get("executed")))
            if not execute:
                return PlannedResult(
                    command=text,
                    tool="codex.job",
                    summary="Codex CLI preview prepared by local intent router. No Codex job was executed.",
                    assessment=assessment.to_dict(),
                    result={
                        "planned_only": True,
                        "would_execute_if_run": True,
                        "selected_tool": "codex.job",
                        "execution_mode": "async",
                        "intent": intent,
                        "plan": codex_delegate_plan(text),
                    },
                    executed=False,
                    confirmation=None,
                )
            result = start_codex_delegate_job(text)
            summary = "Started Codex CLI job." if result.get("status") == "running" else "Tried to start Codex CLI job."
            return self._result(text, "codex.job", summary, assessment, result, bool(result.get("executed")))
        return None

    def _result(
        self,
        command: str,
        tool: str,
        summary: str,
        assessment: Any,
        result: dict[str, Any],
        executed: bool,
        confirmation: dict[str, Any] | None = None,
    ) -> PlannedResult:
        return PlannedResult(command, tool, summary, assessment.to_dict(), result, executed, confirmation)

    def _preview_result(
        self,
        command: str,
        tool: str,
        assessment: Any,
        would_execute: bool,
        confirmation: dict[str, Any] | None = None,
        plan: dict[str, Any] | None = None,
    ) -> PlannedResult:
        result = {
            "planned_only": True,
            "would_execute_if_run": would_execute,
            "selected_tool": tool,
        }
        if plan is not None:
            result["plan"] = plan
        return PlannedResult(
            command=command,
            tool=tool,
            summary="Command preview prepared. No tool was executed.",
            assessment=assessment.to_dict(),
            result=result,
            executed=False,
            confirmation=confirmation,
        )



def _extract_url(text: str) -> str:
    match = re.search(r"https?://\S+", text)
    return match.group(0).rstrip(".,)") if match else ""


def _clean_optional_entity(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text or text.lower() in {"null", "none", "unknown", "n/a"}:
        return None
    return text[:120]


def _extract_email_sender_constraint(text: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", text).strip()
    match = re.search(
        r"(?i)\bfrom\s+([A-Za-z][A-Za-z0-9 ._'’\-]{0,80}?)(?:[?.,!;:]|\s+(?:about|after|before|by|in|on|regarding|that|to|with)\b|$)",
        cleaned,
    )
    if not match:
        return None
    sender = re.sub(r"\s+", " ", match.group(1)).strip(" ._'’-,")
    if not sender:
        return None
    blocked = {"my inbox", "inbox", "mail", "email", "outlook"}
    if sender.lower() in blocked:
        return None
    return sender[:120]


def _extract_email_selection_constraint(text: str) -> str | None:
    lower = text.lower()
    if re.search(r"\b(newest|latest|most recent)\b", lower):
        return "latest"
    if re.search(r"\bunread\b", lower):
        return "unread_first"
    return None


def _extract_app_name(text: str) -> str | None:
    match = re.match(r"(?i)^(?:app|open app|check app)\s+(.+)$", text.strip())
    if not match:
        return None
    return match.group(1).strip()


def _extract_wake_transcript(text: str) -> str | None:
    stripped = text.strip()
    if stripped.lower().startswith("wake:"):
        return stripped.split(":", 1)[1].strip()
    match = re.match(r"(?i)^simulate wake\s+(.+)$", stripped)
    if match:
        return match.group(1).strip()
    if detect_wake_command(stripped).woke:
        return stripped
    return None


def _extract_injection_scan_text(text: str) -> str | None:
    stripped = text.strip()
    lower = stripped.lower()
    prefixes = (
        "scan untrusted:",
        "scan untrusted text:",
        "scan prompt injection:",
        "scan prompt-injection:",
    )
    for prefix in prefixes:
        if lower.startswith(prefix):
            return stripped[len(prefix) :].strip()
    return None


def _looks_like_shell_command(text: str) -> bool:
    first = text.split(maxsplit=1)[0] if text.split() else ""
    shell_commands = READ_ONLY_SHELL_COMMANDS.union(DANGEROUS_SHELL_TOKENS).union(VERSION_ONLY_SHELL_COMMANDS)
    return first in shell_commands


def _looks_like_latency_status(lower: str) -> bool:
    return (
        "latency" in lower
        or "first visible" in lower
        or "first token" in lower
        or "speed smoke" in lower
        or "fast smoke" in lower
    ) and not any(word in lower for word in ("email", "mail", "outlook"))


def _looks_like_fast_model_status(lower: str) -> bool:
    model_cues = (
        "fast model",
        "model status",
        "model backend",
        "which model",
        "what model",
        "groq status",
        "ollama status",
    )
    status_cues = ("status", "check", "show", "what", "which", "using", "configured")
    mutation_cues = ("change", "switch", "set ", "use ", "replace", "install", "remove", "delete")
    return (
        any(cue in lower for cue in model_cues)
        and any(cue in lower for cue in status_cues)
        and not any(cue in lower for cue in mutation_cues)
    )


def _looks_like_tts_status(lower: str) -> bool:
    tts_cues = (
        "tts",
        "text-to-speech",
        "text to speech",
        "speech output",
        "spoken reply",
        "spoken replies",
        "speak status",
        "can you speak",
        "voice output",
    )
    status_cues = ("status", "check", "show", "what", "which", "ready", "available", "can")
    mutation_cues = ("enable", "turn on", "always speak", "auto speak", "automatic speech", "say out loud ")
    return (
        any(cue in lower for cue in tts_cues)
        and any(cue in lower for cue in status_cues)
        and not any(cue in lower for cue in mutation_cues)
    )


def _looks_like_remote_worker_status(lower: str) -> bool:
    remote_cues = (
        "remote worker",
        "macbook air",
        "macbook-air",
        "tailnet",
        "tailscale",
        "100.72.212.85",
    )
    status_cues = ("status", "check", "show", "ready", "available", "ssh", "helper")
    mutation_cues = ("sync", "copy", "run job", "delete", "move", "install", "change")
    return (
        any(cue in lower for cue in remote_cues)
        and any(cue in lower for cue in status_cues)
        and not any(cue in lower for cue in mutation_cues)
    )


def _looks_like_elevation_status(lower: str) -> bool:
    elevation_cues = (
        "elevation",
        "elevating",
        "escalation",
        "smarter model",
        "smart model",
        "model ladder",
        "model routing",
    )
    status_cues = ("status", "check", "show", "explain", "how", "route", "routing")
    mutation_cues = ("switch", "change", "set ", "install", "delete", "remove")
    return (
        any(cue in lower for cue in elevation_cues)
        and any(cue in lower for cue in status_cues)
        and not any(cue in lower for cue in mutation_cues)
    )


def _looks_like_memory_status(lower: str) -> bool:
    memory_cues = (
        "memory status",
        "model memory",
        "jarvis memory",
        "memory.md",
        "daily memory",
        "memory sync",
        "remember me",
    )
    status_cues = ("status", "check", "show", "explain", "how", "plan", "design", "memory")
    mutation_cues = ("sync now", "copy now", "upload", "delete", "erase", "export all")
    return (
        any(cue in lower for cue in memory_cues)
        and any(cue in lower for cue in status_cues)
        and not any(cue in lower for cue in mutation_cues)
    )


def _looks_like_source_access_status(lower: str) -> bool:
    source_cues = (
        "source access",
        "source status",
        "source lock",
        "repo access",
        "repo status",
        "git access",
        "git visibility",
        "patch artifact",
        "hardened patch",
    )
    status_cues = ("status", "check", "show", "explain", "why", "access", "visibility", "locked")
    mutation_cues = ("commit", "push", "pull", "reset", "delete", "remove", "apply", "write")
    return (
        any(cue in lower for cue in source_cues)
        and any(cue in lower for cue in status_cues)
        and not any(cue in lower for cue in mutation_cues)
    )


def _looks_like_screen_status(lower: str) -> bool:
    screen_cues = (
        "screen status",
        "screen capture status",
        "screenshot status",
        "ocr status",
        "native ocr status",
        "screen readiness",
    )
    mutation_cues = ("capture", "read the visible", "scan", "take")
    return any(cue in lower for cue in screen_cues) and not any(cue in lower for cue in mutation_cues)


def _looks_like_launch_status(lower: str) -> bool:
    jarvis_cues = ("jarvis", "app", "launcher", "open command", "launch command", "reopen command")
    launch_cues = ("open", "launch", "launcher", "reopen", "start")
    help_cues = ("command", "how", "path", "where", "status", "help")
    if not any(cue in lower for cue in jarvis_cues):
        return False
    return any(cue in lower for cue in launch_cues) and any(cue in lower for cue in help_cues)


def _looks_like_wake_status(lower: str) -> bool:
    wake_cues = ("wake", "wake word", "hey jarvis listener", "microphone listener", "voice listener")
    status_cues = ("status", "check", "show", "what", "which", "help", "ready")
    return any(cue in lower for cue in wake_cues) and any(cue in lower for cue in status_cues)


def _looks_like_email_status(lower: str) -> bool:
    email_cues = ("email", "mail", "outlook")
    status_cues = ("backend", "diagnostic", "diagnostics", "route", "routes", "status", "permission", "readiness")
    private_read_cues = ("check my email", "summarize", "summary", "newest", "latest", "inbox", "read my", "scan my")
    return (
        any(cue in lower for cue in email_cues)
        and any(cue in lower for cue in status_cues)
        and not any(cue in lower for cue in private_read_cues)
    )


def _is_exact_email_status_command(lower: str) -> bool:
    return lower.strip() in {
        "email backend status",
        "email route status",
        "email routes status",
        "email status",
        "mail backend status",
        "mail route status",
        "mail status",
    }


def _looks_like_capability_status(lower: str) -> bool:
    capability_cues = (
        "capability",
        "capabilities",
        "can you do",
        "what can you do",
        "what works",
        "what is working",
        "what's working",
        "feature status",
        "feature list",
    )
    status_cues = ("status", "check", "show", "list", "right now", "currently", "today")
    private_read_cues = ("email", "mail", "outlook", "screen", "screenshot")
    return (
        any(cue in lower for cue in capability_cues)
        and any(cue in lower for cue in status_cues)
        and not any(cue in lower for cue in private_read_cues)
    )


def _looks_like_safety_status(lower: str) -> bool:
    safety_cues = (
        "safety",
        "privacy",
        "safe",
        "safeties",
        "confirmation",
        "confirmations",
        "approval",
        "protected action",
        "dangerous policy",
        "what is protected",
    )
    status_cues = ("status", "check", "show", "list", "what", "which", "explain", "rules", "policy")
    permission_cues = ("permission", "screen recording", "accessibility", "microphone", "speech recognition")
    return (
        any(cue in lower for cue in safety_cues)
        and any(cue in lower for cue in status_cues)
        and not any(cue in lower for cue in permission_cues)
    )


def _looks_like_codex_delegate(lower: str) -> bool:
    return bool(
        re.search(
            r"\b(codex|coding|code|debug|bug|fix|implement|build|compile|review|project|repo|repository|swift|python|tests?)\b",
            lower,
        )
    )


def _looks_like_codex_speed_status(lower: str) -> bool:
    if "codex" not in lower:
        return False
    speed_cues = ("speed", "latency", "timing", "time", "slow", "performance")
    status_cues = ("status", "check", "show", "what", "how")
    return any(cue in lower for cue in speed_cues) and any(cue in lower for cue in status_cues)


def _looks_like_codex_continuation(text: str, history: list[dict[str, str]] | None) -> bool:
    if _looks_like_same_codex_reference(text):
        return True
    lower = text.strip().lower()
    if re.match(r"(?is)^tell\s+codex\s+(?:this\s*:?)", text.strip()) and _history_shows_codex_waiting(history):
        return True
    if _looks_like_confirmation_code_reply(text) and _history_shows_codex_waiting(history):
        return True
    return False


def _looks_like_same_codex_reference(text: str) -> bool:
    lower = text.strip().lower()
    return bool(
        re.search(
            r"\b(?:same|previous|last|that)\s+codex\b"
            r"|\bcontinue\s+(?:the\s+)?(?:same\s+)?codex\b"
            r"|\bresume\s+(?:the\s+)?(?:same\s+)?codex\b",
            lower,
        )
    )


def _looks_like_confirmation_code_reply(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) > 80:
        return False
    return re.fullmatch(r"(?:code\s*:?\s*)?\d{4,12}", stripped, re.IGNORECASE) is not None


def _history_shows_codex_waiting(history: list[dict[str, str]] | None) -> bool:
    if not history:
        return False
    for item in reversed(history[-12:]):
        content = str(item.get("content") or "").lower()
        if not content:
            continue
        if "codex" not in content and "agents.md" not in content:
            continue
        waiting_cues = ("secret code", "confirmation code", "reply with", "provide", "permission", "approval", "waiting")
        if any(cue in content for cue in waiting_cues):
            return True
    return False


def _should_run_codex_synchronously(lower: str) -> bool:
    return "say exactly" in lower or "smoke test" in lower or re.search(r"\bexactly\s*:", lower) is not None


def _extract_codex_job_query(text: str) -> str | None:
    stripped = text.strip()
    lower = stripped.lower()
    if lower in {"codex jobs", "codex job status", "check codex jobs", "codex status"}:
        return ""
    match = re.match(r"(?i)^codex\s+job(?:\s+(?:status|result))?\s+([A-Za-z0-9-]+)$", stripped)
    if match:
        return match.group(1)
    match = re.match(r"(?i)^(?:check|get|show)\s+codex\s+job\s+([A-Za-z0-9-]+)$", stripped)
    if match:
        return match.group(1)
    return None


def _extract_exact_reply(text: str) -> str | None:
    match = re.search(r"\b(?:say|reply|respond|print)\s+exactly\s*:?\s*(.+)$", text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    reply = match.group(1).strip()
    if len(reply) >= 2 and reply[0] == reply[-1] and reply[0] in {"'", '"'}:
        reply = reply[1:-1].strip()
    return reply[:1200] if reply else None


def _explicitly_asks_codex(lower: str) -> bool:
    return bool(
        re.search(
            r"\b(?:ask|use|run|start)\s+codex\b"
            r"|\bdelegate\s+(?:this\s+)?to\s+codex\b"
            r"|\bsend\s+(?:this\s+)?to\s+codex\b"
            r"|\bcodex\s+to\b"
            r"|\bthrough\s+codex\b"
            r"|\busing\s+codex\b",
            lower,
        )
    )


def _explicit_codex_intent() -> dict[str, Any]:
    return {
        "status": "completed",
        "selected_tool": "codex.job",
        "confidence": 1.0,
        "entities": {},
        "reason": "Explicit Codex request.",
    }


def _confirmation(
    *,
    kind: str,
    title: str,
    message: str,
    exact_phrase: str | None,
    prototype_note: str,
) -> dict[str, Any]:
    return {
        "required": True,
        "kind": kind,
        "title": title,
        "message": message,
        "exact_phrase": exact_phrase,
        "prototype_note": prototype_note,
    }
