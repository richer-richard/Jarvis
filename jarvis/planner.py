"""Heuristic planner for the first Jarvis prototype."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .safety import DANGEROUS_SHELL_TOKENS, READ_ONLY_SHELL_COMMANDS, VERSION_ONLY_SHELL_COMMANDS, classify_command
from .wake import detect_wake_command
from .tools import (
    app_availability,
    app_list,
    app_open,
    app_quit_plan,
    app_running,
    app_status,
    app_task_workflow_plan,
    browser_open_url_plan,
    capabilities_status,
    codex_activity_snapshot,
    codex_chat_status,
    codex_speed_status,
    codex_job_status,
    codex_delegate_plan,
    deep_tool_catalog_status,
    email_backend_status,
    elevation_status,
    fast_model_status,
    final_qa_plan_status,
    find_files,
    launch_status,
    latest_latency_status,
    memory_status,
    model_context_status,
    more_tools_plan,
    overnight_work_status,
    outlook_read_only_check,
    outlook_read_only_plan,
    planned_tool_status,
    prompt_injection_scan,
    permissions_status,
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
    stt_audition_status,
    stt_candidate_status,
    stt_session_plan,
    stt_score_transcript,
    system_status,
    terminal_command_plan,
    tool_catalog_status,
    tool_handoff_plan,
    tts_status,
    voice_session_plan,
    voice_loop_simulation,
    wake_status,
    wake_phrase_simulation,
)


NATURAL_LANGUAGE_TOOL_SPECS = [
    {
        "tool": "outlook.visible_summary",
        "description": "Read and summarize local mailbox content. Use only when the user wants Jarvis to inspect email messages.",
        "entities": ["sender_query", "selection", "email_count", "email_from", "email_to", "unread_only"],
        "entity_details": {
            "sender_query": "Optional sender or subject text to filter by.",
            "selection": "Use latest, unread_first, index:N, or range:A-B. index:2 means the second newest inbox message.",
            "email_count": "Optional number of messages requested.",
            "email_from": "Optional 1-based start index in newest-first inbox order.",
            "email_to": "Optional 1-based end index in newest-first inbox order.",
            "unread_only": "True only when the user asks specifically for unread mail.",
        },
        "examples": [
            'Yes sir, checking your second email now. \\tool({"tool":"outlook.visible_summary","entities":{"selection":"index:2"}})',
            'Yes sir, checking your unread email now. \\tool({"tool":"outlook.visible_summary","entities":{"selection":"unread_first"}})',
        ],
    },
    {
        "tool": "diagnostics.email",
        "description": "Report email backend or route readiness without reading email content.",
        "entities": [],
    },
    {
        "tool": "diagnostics.overnight",
        "description": "Report the overnight workboard, morning report draft, and deferred QA paths without opening apps or browsers.",
        "entities": [],
    },
    {
        "tool": "diagnostics.final_qa",
        "description": "Report the remaining final/foreground QA plan without opening apps, launching Jarvis, capturing the screen, recording audio, or running the verifier.",
        "entities": [],
    },
    {
        "tool": "diagnostics.model_context",
        "description": "Preview what Jarvis would feed its first model, middle planner, Codex, and TTS without calling any model.",
        "entities": ["sample_prompt"],
    },
    {
        "tool": "diagnostics.tool_catalog",
        "description": "Report the first-model, middle-planner, and registry tool catalog IDs and mismatches without calling any model.",
        "entities": [],
    },
    {
        "tool": "tools.deep_catalog",
        "description": "Report the deeper grouped tool catalog and layered handoff contract without executing tools or calling any model.",
        "entities": [],
    },
    {
        "tool": "tools.handoff_plan",
        "description": "Explain how a chosen tool ID would be previewed, executed through policy, confirmation-gated, unavailable, or refused without running that tool.",
        "entities": ["recommended_tool", "entities", "user_goal"],
        "examples": [
            'Yes sir, checking how to handle that now. \\tool({"tool":"tools.handoff_plan","entities":{"recommended_tool":"app.open","entities":{"app_name":"Microsoft Teams"},"user_goal":"Open Teams"}})',
        ],
    },
    {
        "tool": "diagnostics.permissions",
        "description": "Report microphone, speech-recognition, screen, and app-control permission readiness without prompting for permissions or changing settings.",
        "entities": [],
    },
    {
        "tool": "voice.stt_candidates",
        "description": "Report speech-recognition candidates and installed local engine evidence without recording audio.",
        "entities": [],
    },
    {
        "tool": "voice.stt_session_plan",
        "description": "Prepare one speech-recognition audition run with candidate, reference sentence, timing metrics, and export checklist without recording audio.",
        "entities": ["candidate_id", "reference_sentence"],
    },
    {
        "tool": "voice.session_plan",
        "description": "Plan the full Hey Jarvis voice session from wake phrase to visible acknowledgement, STT, command routing, safe tool execution, final visible text, and optional speech without recording audio or playing sound.",
        "entities": ["command"],
        "examples": [
            'Yes sir, planning the voice session now. \\tool({"tool":"voice.session_plan","entities":{"command":"check my email"}})',
        ],
    },
    {
        "tool": "voice.stt_score",
        "description": "Score a provided or pasted speech-recognition transcript against a reference sentence without recording audio.",
        "entities": ["reference", "transcript", "candidate_id", "first_result_ms", "final_result_ms", "human_score"],
        "examples": [
            'Yes sir, scoring that transcript now. \\tool({"tool":"voice.stt_score","entities":{"reference":"Hey Jarvis, check my email.","transcript":"hey jarvis check my email"}})',
        ],
    },
    {
        "tool": "voice.loop_simulation",
        "description": "Simulate a typed Hey Jarvis wake loop, greeting, command capture, and safe command preview without recording audio, playing audio, opening apps, or capturing the screen.",
        "entities": ["transcript"],
        "examples": [
            'Yes sir, testing the voice loop now. \\tool({"tool":"voice.loop_simulation","entities":{"transcript":"Hey Jarvis status"}})',
        ],
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
        "tool": "app.open",
        "description": "Open or focus a local macOS app when the user asks to launch, open, or bring up an app.",
        "entities": ["app_name"],
        "entity_details": {
            "app_name": "The user-facing app name, such as Microsoft Outlook, Google Chrome, Microsoft Teams, Word, PowerPoint, Excel, Safari, Mail, Finder, or Codex.",
        },
        "examples": [
            'Yes sir, opening Outlook now. \\tool({"tool":"app.open","entities":{"app_name":"Microsoft Outlook"}})',
            'Yes sir, opening Teams now. \\tool({"tool":"app.open","entities":{"app_name":"Microsoft Teams"}})',
        ],
    },
    {
        "tool": "app.quit",
        "description": "Prepare quitting a local macOS app when the user asks to close, quit, or force quit it. This always requires user confirmation and must not silently execute.",
        "entities": ["app_name"],
        "entity_details": {
            "app_name": "The user-facing app name, such as Safari, Microsoft Outlook, Google Chrome, Microsoft Teams, Mail, Finder, or Codex.",
        },
        "examples": [
            'Yes sir, I can prepare that, but quitting Safari needs confirmation. \\tool({"tool":"app.quit","entities":{"app_name":"Safari"}})',
        ],
    },
    {
        "tool": "app.list",
        "description": "List local macOS apps Jarvis knows how to open, without launching or inspecting them.",
        "entities": [],
        "examples": [
            'Yes sir, checking which apps I can open now. \\tool({"tool":"app.list","entities":{}})',
        ],
    },
    {
        "tool": "app.status",
        "description": "Check whether a named local macOS app exists and appears to be running, without launching, focusing, or inspecting it.",
        "entities": ["app_name"],
        "entity_details": {
            "app_name": "The user-facing app name, such as Microsoft Outlook, Google Chrome, Microsoft Teams, Word, PowerPoint, Excel, Safari, Mail, Finder, or Codex.",
        },
        "examples": [
            'Yes sir, checking Outlook now. \\tool({"tool":"app.status","entities":{"app_name":"Microsoft Outlook"}})',
            'Yes sir, checking whether Teams is running now. \\tool({"tool":"app.status","entities":{"app_name":"Microsoft Teams"}})',
        ],
    },
    {
        "tool": "app.running",
        "description": "List known local macOS apps and whether each appears to be running, without launching, focusing, screenshotting, or inspecting app content.",
        "entities": [],
        "examples": [
            'Yes sir, checking which apps are running now. \\tool({"tool":"app.running","entities":{}})',
        ],
    },
    {
        "tool": "terminal.plan",
        "description": "Classify and explain a terminal command without running it. Use when the user asks what command would be used or when safety is unclear.",
        "entities": ["command"],
    },
    {
        "tool": "terminal.read_only",
        "description": "Run a terminal command only if it fits Jarvis's existing read-only shell allowlist. Never use for writes, deletes, installs, settings, sudo, network uploads, or secrets.",
        "entities": ["command"],
    },
    {
        "tool": "tools.more",
        "description": "Ask Jarvis's smarter middle model for a broader plan when the first tool list is insufficient, especially for multi-app workflows, UI automation, future skills, or complex tasks that need more context before execution. Set execute_safe_recommendation true only when the user asked Jarvis to take action and it is okay for Jarvis to immediately run a small safe follow-up such as opening an app or running an allowlisted read-only terminal command.",
        "entities": ["execute_safe_recommendation"],
        "entity_details": {
            "execute_safe_recommendation": "Boolean. True only for action requests where Jarvis may immediately follow through on app.open or terminal.read_only after the middle planner chooses one; protected, private, Codex, browser, future, or confirmation-required routes remain preview-only.",
        },
    },
    {
        "tool": "workflow.app_task_plan",
        "description": "Prepare a safe structured plan for a multi-step app task, including app opening, screen/OCR, UI automation, Codex delegation, and confirmation gates, without executing the workflow.",
        "entities": ["goal", "target_app"],
        "examples": [
            'Yes sir, preparing the app workflow plan now. \\tool({"tool":"workflow.app_task_plan","entities":{"goal":"Go to Teams, open Music class, and find the newest assignment.","target_app":"Microsoft Teams"}})',
        ],
    },
    {
        "tool": "diagnostics.codex_chats",
        "description": "Report configured Codex chat names, purposes, default route, and daily Jarvis-to-Codex memory without exposing session IDs.",
        "entities": [],
    },
    {
        "tool": "codex.activity",
        "description": "Read redacted recent async Codex job activity so Jarvis can show that Codex is working without starting a new Codex request.",
        "entities": [],
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

    def handle_selected_tool(
        self,
        command: str,
        selected_tool: str,
        entities: dict[str, Any] | None = None,
        *,
        history: list[dict[str, str]] | None = None,
    ) -> PlannedResult | None:
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
        if selected_tool == "app.quit":
            app_name = _clean_optional_entity((entities or {}).get("app_name")) or _extract_app_quit_name(text) or _extract_app_name(text) or ""
            return self._app_quit_confirmation_result(text, assessment, app_name)
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
        return self._handle_model_intent(text, assessment, intent, execute=True, history=history)

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
        voice_loop_transcript = _extract_voice_loop_transcript(text)
        if voice_loop_transcript is not None:
            return self._voice_loop_result(text, assessment, voice_loop_transcript)
        if codex_job_query is not None:
            result = codex_job_status(codex_job_query)
            return self._result(text, "codex.job", "Checked Codex job status.", assessment, result, False)
        if _looks_like_codex_chat_status(lower):
            return self._result(text, "diagnostics.codex_chats", "Read Codex chat routing status.", assessment, codex_chat_status(), True)
        if _looks_like_codex_activity_status(lower):
            result = codex_activity_snapshot()
            return self._result(text, "codex.activity", "Read Codex activity snapshot.", assessment, result, False)
        if _looks_like_codex_speed_status(lower):
            return self._result(text, "diagnostics.codex_speed", "Read local Codex speed status.", assessment, codex_speed_status(), True)
        if _looks_like_overnight_work_status(lower):
            return self._result(text, "diagnostics.overnight", "Read overnight workboard status.", assessment, overnight_work_status(), True)
        if _looks_like_final_qa_status(lower):
            return self._result(text, "diagnostics.final_qa", "Read deferred final QA plan.", assessment, final_qa_plan_status(), True)
        if _looks_like_workflow_plan_request(lower):
            return self._result(text, "workflow.app_task_plan", "Prepared safe app-task workflow plan.", assessment, app_task_workflow_plan(text), True)
        app_quit_name = _extract_app_quit_name(text)
        if app_quit_name is not None:
            return self._app_quit_confirmation_result(text, assessment, app_quit_name)
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
        if _looks_like_deep_tool_catalog_status(lower):
            return self._result(text, "tools.deep_catalog", "Read layered deep tool catalog.", assessment, deep_tool_catalog_status(NATURAL_LANGUAGE_TOOL_SPECS), True)
        if _looks_like_tool_handoff_plan(lower):
            return self._result(
                text,
                "tools.handoff_plan",
                "Prepared tool handoff plan.",
                assessment,
                tool_handoff_plan(_extract_handoff_tool_id(text), user_goal=text),
                True,
            )
        if _looks_like_tool_catalog_status(lower):
            return self._result(text, "diagnostics.tool_catalog", "Read Jarvis tool catalog status.", assessment, tool_catalog_status(NATURAL_LANGUAGE_TOOL_SPECS), True)
        if _looks_like_permissions_status(lower):
            return self._result(text, "diagnostics.permissions", "Read Jarvis permissions readiness.", assessment, permissions_status(), True)
        if _looks_like_model_context_status(lower):
            return self._result(text, "diagnostics.model_context", "Previewed Jarvis model context.", assessment, model_context_status(_extract_model_context_sample(text), tool_specs=NATURAL_LANGUAGE_TOOL_SPECS, history=history), True)
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
        stt_score_payload = _extract_stt_score_payload(text)
        if stt_score_payload is not None:
            result = stt_score_transcript(**stt_score_payload)
            return self._result(text, "voice.stt_score", "Scored speech-recognition transcript.", assessment, result, True)
        if _looks_like_voice_session_plan(lower):
            return self._result(text, "voice.session_plan", "Prepared voice session plan.", assessment, voice_session_plan(_extract_voice_session_command(text)), True)
        if _looks_like_stt_session_plan(lower):
            return self._result(text, "voice.stt_session_plan", "Prepared STT audition session plan.", assessment, stt_session_plan(), True)
        if _looks_like_stt_audition_status(lower):
            return self._result(text, "voice.stt_audition", "Read local STT audition status.", assessment, stt_audition_status(), True)
        if _looks_like_stt_candidate_status(lower):
            return self._result(text, "voice.stt_candidates", "Read speech-recognition candidate status.", assessment, stt_candidate_status(), True)
        if _looks_like_overnight_work_status(lower):
            return self._result(text, "diagnostics.overnight", "Read overnight workboard status.", assessment, overnight_work_status(), True)
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
        if _looks_like_browser_url_request(text):
            return self._result(text, "browser.open_url", "Prepared browser-open plan.", assessment, browser_open_url_plan(_extract_url(text)), False)
        if _looks_like_running_apps_request(lower):
            return self._result(text, "app.running", "Checked which known apps are running.", assessment, app_running(), True)
        if _looks_like_app_list_request(lower):
            return self._result(text, "app.list", "Listed local apps Jarvis can open.", assessment, app_list(), True)
        app_status_name = _extract_app_status_name(text)
        if app_status_name is not None:
            return self._result(text, "app.status", "Checked local app status.", assessment, app_status(app_status_name), True)
        app_open_name = _extract_app_open_name(text)
        if app_open_name is not None:
            result = app_open(app_open_name)
            summary = "Opened local app." if result.get("status") == "opened" else "Tried to open local app."
            return self._result(text, "app.open", summary, assessment, result, bool(result.get("executed")))
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
            routed = self._handle_model_intent(text, assessment, _explicit_codex_intent(), execute=True, history=history)
            if routed is not None:
                return routed
        result = run_fast_local_chat(text, history=history, tool_specs=NATURAL_LANGUAGE_TOOL_SPECS)
        if result.get("status") == "tool_requested":
            routed = self.handle_selected_tool(
                text,
                str(result.get("selected_tool") or ""),
                result.get("entities") if isinstance(result.get("entities"), dict) else {},
                history=history,
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
        voice_loop_transcript = _extract_voice_loop_transcript(text)
        if voice_loop_transcript is not None:
            return self._preview_result(text, "voice.loop_simulation", assessment, True, plan={"transcript": voice_loop_transcript})
        if _looks_like_overnight_work_status(lower):
            return self._preview_result(text, "diagnostics.overnight", assessment, True)
        if _looks_like_final_qa_status(lower):
            return self._preview_result(text, "diagnostics.final_qa", assessment, True)
        if _looks_like_workflow_plan_request(lower):
            return self._preview_result(text, "workflow.app_task_plan", assessment, True, plan={"goal": text})
        app_quit_name = _extract_app_quit_name(text)
        if app_quit_name is not None:
            return self._app_quit_confirmation_result(text, assessment, app_quit_name)
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
        if _looks_like_codex_chat_status(lower):
            return self._preview_result(text, "diagnostics.codex_chats", assessment, True)
        if _looks_like_codex_activity_status(lower):
            return self._preview_result(text, "codex.activity", assessment, True)
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
        if _looks_like_deep_tool_catalog_status(lower):
            return self._preview_result(text, "tools.deep_catalog", assessment, True)
        if _looks_like_tool_catalog_status(lower):
            return self._preview_result(text, "diagnostics.tool_catalog", assessment, True)
        if _looks_like_permissions_status(lower):
            return self._preview_result(text, "diagnostics.permissions", assessment, True)
        if _looks_like_model_context_status(lower):
            return self._preview_result(text, "diagnostics.model_context", assessment, True)
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
        stt_score_payload = _extract_stt_score_payload(text)
        if stt_score_payload is not None:
            return self._preview_result(text, "voice.stt_score", assessment, True, plan={"planned_only": True, **stt_score_payload})
        if _looks_like_voice_session_plan(lower):
            return self._preview_result(text, "voice.session_plan", assessment, True, plan={"command": _extract_voice_session_command(text)})
        if _looks_like_stt_session_plan(lower):
            return self._preview_result(text, "voice.stt_session_plan", assessment, True)
        if _looks_like_stt_audition_status(lower):
            return self._preview_result(text, "voice.stt_audition", assessment, True)
        if _looks_like_stt_candidate_status(lower):
            return self._preview_result(text, "voice.stt_candidates", assessment, True)
        if _looks_like_overnight_work_status(lower):
            return self._preview_result(text, "diagnostics.overnight", assessment, True)
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
        if _looks_like_browser_url_request(text):
            return self._preview_result(text, "browser.open_url", assessment, False, plan={"url": _extract_url(text)})
        if _looks_like_running_apps_request(lower):
            return self._preview_result(text, "app.running", assessment, True)
        if _looks_like_app_list_request(lower):
            return self._preview_result(text, "app.list", assessment, True)
        app_status_name = _extract_app_status_name(text)
        if app_status_name is not None:
            return self._preview_result(
                text,
                "app.status",
                assessment,
                True,
                plan={"app_name": app_status_name, "would_check_running_processes": True, "planned_only": True},
            )
        app_open_name = _extract_app_open_name(text)
        if app_open_name is not None:
            return self._preview_result(text, "app.open", assessment, True, plan=app_open(app_open_name, execute=False))
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
        history: list[dict[str, str]] | None = None,
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
        if selected_tool == "diagnostics.overnight":
            if not execute:
                return self._preview_result(text, "diagnostics.overnight", assessment, True, plan={"intent": intent})
            return self._result(text, "diagnostics.overnight", "Read overnight workboard status.", assessment, overnight_work_status(), True)
        if selected_tool == "diagnostics.final_qa":
            if not execute:
                return self._preview_result(text, "diagnostics.final_qa", assessment, True, plan={"intent": intent})
            return self._result(text, "diagnostics.final_qa", "Read deferred final QA plan.", assessment, final_qa_plan_status(), True)
        if selected_tool == "diagnostics.model_context":
            sample = _clean_optional_entity(entities.get("sample_prompt")) or _extract_model_context_sample(text)
            if not execute:
                return self._preview_result(text, "diagnostics.model_context", assessment, True, plan={"intent": intent, "sample_prompt": sample})
            return self._result(text, "diagnostics.model_context", "Previewed Jarvis model context.", assessment, model_context_status(sample, tool_specs=NATURAL_LANGUAGE_TOOL_SPECS, history=history), True)
        if selected_tool == "diagnostics.tool_catalog":
            if not execute:
                return self._preview_result(text, "diagnostics.tool_catalog", assessment, True, plan={"intent": intent})
            return self._result(text, "diagnostics.tool_catalog", "Read Jarvis tool catalog status.", assessment, tool_catalog_status(NATURAL_LANGUAGE_TOOL_SPECS), True)
        if selected_tool == "tools.deep_catalog":
            if not execute:
                return self._preview_result(text, "tools.deep_catalog", assessment, True, plan={"intent": intent})
            return self._result(text, "tools.deep_catalog", "Read layered deep tool catalog.", assessment, deep_tool_catalog_status(NATURAL_LANGUAGE_TOOL_SPECS), True)
        if selected_tool == "tools.handoff_plan":
            nested_entities = entities.get("entities") if isinstance(entities.get("entities"), dict) else {}
            if not nested_entities:
                nested_entities = {key: value for key, value in entities.items() if key not in {"recommended_tool", "tool", "user_goal"}}
            recommended_tool = _clean_optional_entity(entities.get("recommended_tool")) or _clean_optional_entity(entities.get("tool")) or _extract_handoff_tool_id(text)
            user_goal = _clean_optional_entity(entities.get("user_goal")) or text
            if not execute:
                return self._preview_result(text, "tools.handoff_plan", assessment, True, plan={"intent": intent, "recommended_tool": recommended_tool})
            return self._result(
                text,
                "tools.handoff_plan",
                "Prepared tool handoff plan.",
                assessment,
                tool_handoff_plan(recommended_tool, nested_entities, user_goal),
                True,
            )
        if selected_tool == "diagnostics.permissions":
            if not execute:
                return self._preview_result(text, "diagnostics.permissions", assessment, True, plan={"intent": intent})
            return self._result(text, "diagnostics.permissions", "Read Jarvis permissions readiness.", assessment, permissions_status(), True)
        if selected_tool == "voice.stt_candidates":
            if not execute:
                return self._preview_result(text, "voice.stt_candidates", assessment, True, plan={"intent": intent})
            return self._result(text, "voice.stt_candidates", "Read speech-recognition candidate status.", assessment, stt_candidate_status(), True)
        if selected_tool == "voice.stt_session_plan":
            candidate_id = _clean_optional_entity(entities.get("candidate_id"))
            reference_sentence = _clean_optional_entity(entities.get("reference_sentence"))
            if not execute:
                return self._preview_result(
                    text,
                    "voice.stt_session_plan",
                    assessment,
                    True,
                    plan={"intent": intent, "candidate_id": candidate_id, "reference_sentence": reference_sentence},
                )
            return self._result(text, "voice.stt_session_plan", "Prepared STT audition session plan.", assessment, stt_session_plan(candidate_id, reference_sentence), True)
        if selected_tool == "voice.session_plan":
            command = _clean_optional_entity(entities.get("command")) or _extract_voice_session_command(text)
            if not execute:
                return self._preview_result(text, "voice.session_plan", assessment, True, plan={"intent": intent, "command": command})
            return self._result(text, "voice.session_plan", "Prepared voice session plan.", assessment, voice_session_plan(command), True)
        if selected_tool == "voice.stt_score":
            payload = _stt_score_payload_from_entities(entities) or _extract_stt_score_payload(text) or {
                "reference": "",
                "transcript": "",
                "candidate_id": _clean_optional_entity(entities.get("candidate_id")),
                "first_result_ms": _positive_entity_int(entities.get("first_result_ms")),
                "final_result_ms": _positive_entity_int(entities.get("final_result_ms")),
                "human_score": _float_entity(entities.get("human_score")),
            }
            if not execute:
                return self._preview_result(text, "voice.stt_score", assessment, True, plan={"intent": intent, **payload})
            return self._result(text, "voice.stt_score", "Scored speech-recognition transcript.", assessment, stt_score_transcript(**payload), True)
        if selected_tool == "voice.loop_simulation":
            transcript = _clean_optional_entity(entities.get("transcript")) or _extract_voice_loop_transcript(text) or text
            return self._voice_loop_result(text, assessment, transcript)
        if selected_tool == "outlook.visible_summary":
            sender_query = _clean_optional_entity(entities.get("sender_query")) or _extract_email_sender_constraint(text)
            selection = (
                _clean_optional_entity(entities.get("selection"))
                or _email_selection_from_entities(entities)
                or _extract_email_selection_constraint(text)
            )
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
        if selected_tool == "app.open":
            app_name = _clean_optional_entity(entities.get("app_name")) or _extract_app_open_name(text) or _extract_app_name(text) or ""
            if not execute:
                return self._preview_result(text, "app.open", assessment, True, plan={"intent": intent, **app_open(app_name, execute=False)})
            result = app_open(app_name)
            summary = "Opened local app." if result.get("status") == "opened" else "Tried to open local app."
            return self._result(text, "app.open", summary, assessment, result, bool(result.get("executed")))
        if selected_tool == "app.quit":
            app_name = _clean_optional_entity(entities.get("app_name")) or _extract_app_quit_name(text) or _extract_app_name(text) or _extract_app_open_name(text) or ""
            return self._app_quit_confirmation_result(text, assessment, app_name)
        if selected_tool == "app.list":
            if not execute:
                return self._preview_result(text, "app.list", assessment, True, plan={"intent": intent})
            return self._result(text, "app.list", "Listed local apps Jarvis can open.", assessment, app_list(), True)
        if selected_tool == "app.status":
            app_name = _clean_optional_entity(entities.get("app_name")) or _extract_app_status_name(text) or _extract_app_name(text) or _extract_app_open_name(text) or ""
            if not execute:
                return self._preview_result(text, "app.status", assessment, True, plan={"intent": intent, "app_name": app_name})
            return self._result(text, "app.status", "Checked local app status.", assessment, app_status(app_name), True)
        if selected_tool == "app.running":
            if not execute:
                return self._preview_result(text, "app.running", assessment, True, plan={"intent": intent})
            return self._result(text, "app.running", "Checked which known apps are running.", assessment, app_running(), True)
        if selected_tool == "terminal.plan":
            command = _clean_optional_entity(entities.get("command")) or _extract_terminal_command_text(text)
            plan = terminal_command_plan(command)
            return self._result(text, "terminal.plan", "Prepared terminal command plan.", assessment, plan, False)
        if selected_tool == "terminal.read_only":
            command = _clean_optional_entity(entities.get("command")) or _extract_terminal_command_text(text)
            if not execute:
                return self._preview_result(text, "terminal.read_only", assessment, True, plan={"intent": intent, **terminal_command_plan(command)})
            result = run_read_only_shell(command)
            summary = "Ran read-only terminal command." if result.get("executed") else "Terminal command was not executed by policy."
            return self._result(text, "terminal.read_only", summary, assessment, result, bool(result.get("executed")))
        if selected_tool == "tools.more":
            if not execute:
                return self._preview_result(
                    text,
                    "tools.more",
                    assessment,
                    False,
                    plan={
                        "intent": intent,
                        "plan_only": True,
                        "would_call_middle_model_if_run": True,
                    },
                )
            result = more_tools_plan(text, history=history)
            next_preview = _middle_plan_next_tool_preview(text, result)
            if next_preview is not None:
                result = {**result, "next_tool_preview": next_preview}
            followup = self._middle_safe_followup_result(
                text,
                result,
                assessment,
                history=history,
                allow_followup=_entity_truthy(entities.get("execute_safe_recommendation")),
            )
            if followup is not None:
                result = {**result, "safe_followup": followup}
            summary = "Prepared middle-layer tool plan." if result.get("status") == "planned" else "Tried middle-layer tool planning."
            return self._result(text, "tools.more", summary, assessment, result, False)
        if selected_tool == "workflow.app_task_plan":
            goal = _clean_optional_entity(entities.get("goal")) or text
            target_app = _clean_optional_entity(entities.get("target_app"))
            if not execute:
                return self._preview_result(text, "workflow.app_task_plan", assessment, True, plan={"intent": intent, "goal": goal, "target_app": target_app})
            return self._result(text, "workflow.app_task_plan", "Prepared safe app-task workflow plan.", assessment, app_task_workflow_plan(goal, target_app=target_app), True)
        if selected_tool in {"ui.overlay", "ui.automation", "memory.daily_summary", "teams.assignment", "screen.ocr"}:
            result = planned_tool_status(selected_tool)
            return self._result(text, selected_tool, "Prepared planned future tool status.", assessment, result, False)
        if selected_tool == "diagnostics.codex_chats":
            if not execute:
                return self._preview_result(text, "diagnostics.codex_chats", assessment, True, plan={"intent": intent})
            return self._result(text, "diagnostics.codex_chats", "Read Codex chat routing status.", assessment, codex_chat_status(), True)
        if selected_tool == "codex.activity":
            if not execute:
                return self._preview_result(text, "codex.activity", assessment, True, plan={"intent": intent})
            result = codex_activity_snapshot()
            return self._result(text, "codex.activity", "Read Codex activity snapshot.", assessment, result, False)
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


    def _middle_safe_followup_result(
        self,
        text: str,
        result: dict[str, Any],
        assessment: Any,
        *,
        history: list[dict[str, str]] | None = None,
        allow_followup: bool = False,
    ) -> dict[str, Any] | None:
        recommended = str(result.get("recommended_tool") or "").strip()
        if not recommended:
            return None
        entities = result.get("entities") if isinstance(result.get("entities"), dict) else {}
        handoff = tool_handoff_plan(recommended, entities, text)
        followup: dict[str, Any] = {
            "selected_tool": recommended,
            "allowed_by_request": allow_followup,
            "handoff": handoff,
            "executed": False,
            "result": None,
        }
        if not allow_followup:
            return {
                **followup,
                "status": "preview_only",
                "reason": "The first model did not explicitly request safe follow-through.",
            }
        if recommended not in {"app.open", "terminal.read_only"}:
            return {
                **followup,
                "status": "preview_only",
                "reason": "Only app.open and terminal.read_only are currently allowed for middle-layer safe follow-through.",
            }
        if handoff.get("handoff") != "safe_execute_after_policy":
            return {
                **followup,
                "status": "blocked_by_policy",
                "reason": f"Policy handoff is {handoff.get('handoff') or 'unknown'}, not safe_execute_after_policy.",
            }

        routed = self.handle_selected_tool(text, recommended, entities, history=history)
        if routed is None:
            return {
                **followup,
                "status": "route_unavailable",
                "reason": "The selected tool did not resolve through Planner.handle_selected_tool.",
            }
        routed_dict = routed.to_dict()
        return {
            **followup,
            "status": "followed_through" if routed.executed else "not_executed",
            "executed": bool(routed.executed),
            "result": routed_dict,
            "reason": routed.summary,
        }


    def _voice_loop_result(self, text: str, assessment: Any, transcript: str) -> PlannedResult:
        initial = voice_loop_simulation(transcript)
        command = re.sub(r"\s+", " ", str(initial.get("command") or "")).strip()
        route_preview = None
        route_status_text = None
        if command:
            preview = self.preview(command, use_model_router=False)
            route_preview = preview.to_dict()
            route_status_text = _voice_loop_status_text_for_tool(preview.tool)
        result = initial if route_preview is None else voice_loop_simulation(transcript, route_preview=route_preview, route_status_text=route_status_text)
        return self._result(text, "voice.loop_simulation", "Ran text-only voice loop simulation.", assessment, result, True)


    def _app_quit_confirmation_result(self, text: str, assessment: Any, app_name: str) -> PlannedResult:
        plan = app_quit_plan(app_name)
        return self._result(
            text,
            "app.quit",
            "Quitting an app requires confirmation and was not executed.",
            assessment,
            plan,
            False,
            confirmation=_confirmation(
                kind="standard",
                title="Confirm App Quit",
                message=f"Quit {plan.get('app') or app_name}? This may close windows or lose unsaved work.",
                exact_phrase=None,
                prototype_note="Jarvis prepared the quit plan only. No app was quit.",
            ),
        )


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


def _middle_plan_next_tool_preview(text: str, result: dict[str, Any]) -> dict[str, Any] | None:
    recommended = str(result.get("recommended_tool") or "").strip()
    entities = result.get("entities") if isinstance(result.get("entities"), dict) else {}
    if recommended == "app.open":
        app_name = _clean_optional_entity(entities.get("app_name")) or _extract_app_open_name(text) or _extract_app_name(text) or ""
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": app_open(app_name, execute=False),
        }
    if recommended == "app.quit":
        app_name = _clean_optional_entity(entities.get("app_name")) or _extract_app_quit_name(text) or _extract_app_name(text) or _extract_app_open_name(text) or ""
        preview = app_quit_plan(app_name)
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": preview,
        }
    if recommended == "app.list":
        preview = app_list(limit=40)
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": {**preview, "executed": False, "planned_only": True},
        }
    if recommended == "app.status":
        app_name = _clean_optional_entity(entities.get("app_name")) or _extract_app_status_name(text) or _extract_app_name(text) or _extract_app_open_name(text) or ""
        preview = app_status(app_name)
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": {**preview, "executed": False, "planned_only": True},
        }
    if recommended == "app.running":
        preview = app_running(limit=40)
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": {**preview, "executed": False, "planned_only": True},
        }
    if recommended == "terminal.plan":
        command = _clean_optional_entity(entities.get("command")) or _extract_terminal_command_text(text)
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": terminal_command_plan(command),
        }
    if recommended == "terminal.read_only":
        command = _clean_optional_entity(entities.get("command")) or _extract_terminal_command_text(text)
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": terminal_command_plan(command),
        }
    if recommended == "browser.open_url":
        url = _clean_optional_entity(entities.get("url")) or _extract_url(text)
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": browser_open_url_plan(url),
        }
    if recommended == "outlook.visible_summary":
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": outlook_read_only_plan(),
        }
    if recommended == "voice.stt_candidates":
        preview = stt_candidate_status()
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": {**preview, "executed": False, "planned_only": True},
        }
    if recommended == "voice.stt_session_plan":
        candidate_id = _clean_optional_entity(entities.get("candidate_id"))
        reference_sentence = _clean_optional_entity(entities.get("reference_sentence"))
        preview = stt_session_plan(candidate_id, reference_sentence)
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": {**preview, "executed": False, "planned_only": True},
        }
    if recommended == "voice.session_plan":
        command = _clean_optional_entity(entities.get("command")) or _extract_voice_session_command(text)
        preview = voice_session_plan(command)
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": {**preview, "executed": False, "planned_only": True},
        }
    if recommended == "voice.stt_score":
        payload = _stt_score_payload_from_entities(entities) or _extract_stt_score_payload(text)
        preview = stt_score_transcript(**payload) if payload else {
            "tool": "voice.stt_score",
            "status": "missing_text",
            "executed": False,
            "recorded_audio": False,
            "requested_microphone_permission": False,
            "opened_browser": False,
            "reply": "STT score needs both a reference sentence and a transcript.",
        }
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": {**preview, "executed": False, "planned_only": True},
        }
    if recommended == "voice.loop_simulation":
        transcript = _clean_optional_entity(entities.get("transcript")) or _extract_voice_loop_transcript(text) or text
        preview = Planner()._voice_loop_result(text, classify_command(text), transcript).result
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": {**preview, "executed": False, "planned_only": True},
        }
    if recommended == "diagnostics.model_context":
        preview = model_context_status(text, tool_specs=NATURAL_LANGUAGE_TOOL_SPECS)
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": {**preview, "executed": False, "planned_only": True},
        }
    if recommended == "diagnostics.tool_catalog":
        preview = tool_catalog_status(NATURAL_LANGUAGE_TOOL_SPECS)
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": {**preview, "executed": False, "planned_only": True},
        }
    if recommended == "tools.deep_catalog":
        preview = deep_tool_catalog_status(NATURAL_LANGUAGE_TOOL_SPECS)
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": {**preview, "executed": False, "planned_only": True},
        }
    if recommended == "tools.handoff_plan":
        nested_entities = entities.get("entities") if isinstance(entities.get("entities"), dict) else {}
        if not nested_entities:
            nested_entities = {key: value for key, value in entities.items() if key not in {"recommended_tool", "tool", "user_goal"}}
        selected = _clean_optional_entity(entities.get("recommended_tool")) or _clean_optional_entity(entities.get("tool")) or _extract_handoff_tool_id(text)
        goal = _clean_optional_entity(entities.get("user_goal")) or text
        preview = tool_handoff_plan(selected, nested_entities, goal)
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": {**preview, "executed": False, "planned_only": True},
        }
    if recommended == "diagnostics.permissions":
        preview = permissions_status()
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": {**preview, "executed": False, "planned_only": True},
        }
    if recommended == "diagnostics.final_qa":
        preview = final_qa_plan_status()
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": {**preview, "executed": False, "planned_only": True},
        }
    if recommended == "workflow.app_task_plan":
        goal = _clean_optional_entity(entities.get("goal")) or text
        target_app = _clean_optional_entity(entities.get("target_app"))
        preview = app_task_workflow_plan(goal, target_app=target_app)
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": {**preview, "executed": False, "planned_only": True},
        }
    if recommended in {"ui.overlay", "ui.automation", "memory.daily_summary", "teams.assignment", "screen.ocr"}:
        preview = planned_tool_status(recommended)
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": preview,
        }
    if recommended == "diagnostics.codex_chats":
        preview = codex_chat_status()
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": {**preview, "executed": False, "planned_only": True},
        }
    if recommended == "codex.activity":
        preview = codex_activity_snapshot()
        return {
            "recommended_tool": recommended,
            "executed": False,
            "preview": {**preview, "executed": False, "planned_only": True},
        }
    return None


def _extract_url(text: str) -> str:
    match = re.search(r"https?://\S+", text)
    return match.group(0).rstrip(".,)") if match else ""


def _looks_like_browser_url_request(text: str) -> bool:
    if not _extract_url(text):
        return False
    return bool(re.search(r"(?i)\b(open|browse|browser|visit|go to|launch)\b", text))


def _clean_optional_entity(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text or text.lower() in {"null", "none", "unknown", "n/a"}:
        return None
    return text[:120]


def _extract_handoff_tool_id(text: str) -> str:
    for match in re.finditer(
        r"\b(?:app|browser|codex|conversation|diagnostics|files|memory|outlook|planner|policy|quick|safety|screen|screenshot|shell|system|teams|terminal|tools|ui|voice|workflow)\.[a-z0-9_]+",
        text,
        flags=re.IGNORECASE,
    ):
        tool_id = match.group(0).lower()
        if tool_id != "tools.handoff_plan":
            return tool_id
    return ""


def _extract_app_open_name(text: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", text.strip())
    if _extract_url(cleaned):
        return None
    match = re.match(
        r"(?i)^(?:open|launch|start|bring up|show|focus|switch to)\s+(?:my\s+|the\s+)?(.+?)(?:\s+(?:app|application))?(?:\s+(?:on my screen|on screen|for me|now|please))?[.!?]?$",
        cleaned,
    )
    if not match:
        return None
    app_name = re.sub(r"(?i)\s+(?:app|application)$", "", match.group(1)).strip(" .")
    app_name = re.sub(r"(?i)^(?:app|application)\s+", "", app_name).strip(" .")
    if not app_name:
        return None
    blocked = {
        "browser",
        "email",
        "mailbox",
        "inbox",
        "website",
        "url",
        "link",
    }
    if app_name.lower() in blocked:
        return None
    return app_name[:120]


def _extract_app_quit_name(text: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", text.strip())
    if _extract_url(cleaned):
        return None
    match = re.match(
        r"(?i)^(?:quit|close|force\s+quit|exit)\s+(?:my\s+|the\s+)?(?:app\s+|application\s+)?(.+?)(?:\s+(?:app|application))?(?:\s+(?:for me|now|please))?[.!?]?$",
        cleaned,
    )
    if not match:
        return None
    app_name = match.group(1).strip(" .")
    app_name = re.sub(r"(?i)\s+(?:app|application)$", "", app_name).strip(" .")
    app_name = re.sub(r"(?i)^(?:the|my)\s+", "", app_name).strip(" .")
    if not app_name or app_name.lower() in {"window", "tab", "file", "document", "this", "that"}:
        return None
    if any(cue in app_name.lower() for cue in (" window", " tab", " file", " document")):
        return None
    return app_name[:120]


def _extract_app_status_name(text: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", text.strip())
    if _extract_url(cleaned):
        return None
    patterns = (
        r"(?i)^(?:app status|check app status|check status of app|check the status of app)\s+(.+)$",
        r"(?i)^(?:status of|running status of)\s+(.+?)(?:\s+(?:app|application))?(?:\s+(?:now|please))?[.!?]?$",
        r"(?i)^(?:is|check whether|check if)\s+(.+?)\s+(?:running|open|launched)(?:\s+(?:now|yet|please))?[.!?]?$",
    )
    for pattern in patterns:
        match = re.match(pattern, cleaned)
        if not match:
            continue
        app_name = match.group(1).strip(" .")
        app_name = re.sub(r"(?i)\s+(?:app|application)$", "", app_name).strip(" .")
        app_name = re.sub(r"(?i)^(?:the|my)\s+", "", app_name).strip(" .")
        if not app_name:
            return None
        blocked = {
            "app",
            "apps",
            "application",
            "applications",
            "anything",
            "browser",
            "email",
            "mailbox",
            "inbox",
            "website",
            "url",
            "link",
        }
        if app_name.lower() in blocked:
            return None
        return app_name[:120]
    return None


def _extract_terminal_command_text(text: str) -> str:
    stripped = text.strip()
    lower = stripped.lower()
    prefixes = (
        "terminal:",
        "shell:",
        "run terminal command:",
        "run terminal:",
        "plan terminal command:",
        "terminal command:",
    )
    for prefix in prefixes:
        if lower.startswith(prefix):
            return stripped[len(prefix) :].strip()
    match = re.match(r"(?is)^run\s+(?:the\s+)?(?:terminal\s+)?command\s+(.+)$", stripped)
    if match:
        return match.group(1).strip()
    return stripped


def _extract_model_context_sample(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    quoted = re.search(r"['\"]([^'\"]{1,240})['\"]", cleaned)
    if quoted:
        return quoted.group(1).strip()
    match = re.search(r"(?i)\b(?:for|if i say|when i say|sample prompt)\s*:?\s+(.+)$", cleaned)
    if match:
        sample = match.group(1).strip(" .")
        if sample and not re.search(r"(?i)\b(model|prompt|context|input|diagnostic|show|preview)\b", sample):
            return sample[:240]
    return "hello Jarvis"


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
    ordinal = _extract_email_ordinal(lower)
    if ordinal is not None:
        return f"index:{ordinal}"
    range_match = re.search(
        r"\b(?:email|mail|message|messages)\s+(\d{1,2})\s*(?:-|to|through)\s*(\d{1,2})\b",
        lower,
    )
    if range_match:
        first = max(1, int(range_match.group(1)))
        second = max(1, int(range_match.group(2)))
        start, end = sorted((first, second))
        return f"range:{start}-{end}"
    if re.search(r"\b(?:newest|latest|most recent|first)\b", lower):
        return "latest"
    if re.search(r"\bunread\b", lower):
        return "unread_first"
    return None


def _extract_email_ordinal(lower: str) -> int | None:
    words = {
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
        "seventh": 7,
        "eighth": 8,
        "ninth": 9,
        "tenth": 10,
    }
    for word, value in words.items():
        if re.search(rf"\b{word}\s+(?:email|mail|message)\b", lower) or re.search(rf"\b(?:email|mail|message)\s+{word}\b", lower):
            return value
    match = re.search(r"\b(?:email|mail|message)\s*(\d{1,2})(?:st|nd|rd|th)?\b", lower)
    if match:
        value = int(match.group(1))
        return value if value >= 1 else None
    match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\s+(?:email|mail|message)\b", lower)
    if match:
        value = int(match.group(1))
        return value if value >= 1 else None
    return None


def _email_selection_from_entities(entities: dict[str, Any]) -> str | None:
    if _entity_truthy(entities.get("unread_only")):
        return "unread_first"
    start = _positive_entity_int(entities.get("email_from"))
    end = _positive_entity_int(entities.get("email_to"))
    count = _positive_entity_int(entities.get("email_count"))
    if start is not None and end is not None:
        if start == end:
            return f"index:{start}"
        first, second = sorted((start, end))
        return f"range:{first}-{second}"
    if start is not None:
        return f"index:{start}"
    if count is not None:
        return f"range:1-{count}"
    return None


def _positive_entity_int(value: Any) -> int | None:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _float_entity(value: Any) -> float | None:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _stt_score_payload_from_entities(entities: dict[str, Any]) -> dict[str, Any] | None:
    reference = _clean_optional_entity(entities.get("reference"))
    transcript = _clean_optional_entity(entities.get("transcript"))
    if not reference and not transcript:
        return None
    return {
        "reference": reference or "",
        "transcript": transcript or "",
        "candidate_id": _clean_optional_entity(entities.get("candidate_id")),
        "first_result_ms": _positive_entity_int(entities.get("first_result_ms")),
        "final_result_ms": _positive_entity_int(entities.get("final_result_ms")),
        "human_score": _float_entity(entities.get("human_score")),
    }


def _extract_stt_score_payload(text: str) -> dict[str, Any] | None:
    cleaned = re.sub(r"\s+", " ", text.strip())
    if not re.search(r"(?i)\b(?:stt|speech[- ]to[- ]text|speech recognition|voice recognition|transcript)\b", cleaned):
        return None
    body = re.sub(
        r"(?i)^(?:score|check|compare|grade)\s+(?:the\s+)?(?:stt|speech[- ]to[- ]text|speech recognition|voice recognition)?\s*(?:transcript|result)?\s*:?\s*",
        "",
        cleaned,
    ).strip()
    if not body or body == cleaned:
        return None
    reference = ""
    transcript = ""
    candidate_id = None
    match = re.search(r"(?i)\breference\s*:\s*(.+?)\s+\btranscript\s*:\s*(.+)$", body)
    if match:
        reference, transcript = match.group(1), match.group(2)
    elif "=>" in body:
        reference, transcript = body.split("=>", 1)
    elif "->" in body:
        reference, transcript = body.split("->", 1)
    else:
        return None
    candidate_match = re.search(r"(?i)\bcandidate\s*:\s*([A-Za-z0-9_.-]+)", body)
    if candidate_match:
        candidate_id = candidate_match.group(1)
    reference = re.sub(r"(?i)\bcandidate\s*:\s*[A-Za-z0-9_.-]+", "", reference).strip(" .\"'")
    transcript = re.sub(r"(?i)\bcandidate\s*:\s*[A-Za-z0-9_.-]+", "", transcript).strip(" .\"'")
    if not reference and not transcript:
        return None
    return {
        "reference": reference,
        "transcript": transcript,
        "candidate_id": candidate_id,
        "first_result_ms": None,
        "final_result_ms": None,
        "human_score": None,
    }


def _entity_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _extract_app_name(text: str) -> str | None:
    match = re.match(r"(?i)^(?:app|open app|check app)\s+(.+)$", text.strip())
    if not match:
        return None
    return match.group(1).strip()


def _looks_like_app_list_request(lower: str) -> bool:
    app_cues = (
        "apps",
        "applications",
        "programs",
        "app list",
        "application list",
    )
    list_cues = (
        "list",
        "show",
        "which",
        "what",
        "available",
        "can you open",
        "could you open",
        "know how to open",
    )
    mutation_cues = ("open ", "launch ", "start ", "quit ", "close ", "delete ", "install ", "uninstall ")
    return (
        any(cue in lower for cue in app_cues)
        and any(cue in lower for cue in list_cues)
        and not any(cue in lower for cue in mutation_cues)
    )


def _looks_like_running_apps_request(lower: str) -> bool:
    app_cues = (
        "apps",
        "applications",
        "programs",
        "things",
    )
    running_cues = (
        "running",
        "open right now",
        "currently open",
        "currently running",
        "open apps",
        "apps open",
        "active apps",
    )
    list_cues = (
        "list",
        "show",
        "which",
        "what",
        "check",
        "tell me",
        "are there",
    )
    mutation_cues = ("launch ", "start ", "quit ", "close ", "kill ", "force quit ")
    return (
        any(cue in lower for cue in app_cues)
        and any(cue in lower for cue in running_cues)
        and any(cue in lower for cue in list_cues)
        and not any(cue in lower for cue in mutation_cues)
    )


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


def _extract_voice_loop_transcript(text: str) -> str | None:
    stripped = text.strip()
    lower = stripped.lower()
    prefixes = (
        "voice loop:",
        "wake loop:",
        "simulate voice loop:",
        "simulate wake loop:",
        "test voice loop:",
        "test wake loop:",
        "jarvis voice loop:",
    )
    for prefix in prefixes:
        if lower.startswith(prefix):
            transcript = stripped[len(prefix) :].strip()
            return transcript or "Hey Jarvis"
    match = re.match(r"(?is)^simulate\s+(?:the\s+)?(?:jarvis\s+)?(?:voice|wake)\s+loop\s+(.+)$", stripped)
    if match:
        return match.group(1).strip() or "Hey Jarvis"
    return None


def _extract_voice_session_command(text: str) -> str:
    stripped = re.sub(r"\s+", " ", str(text or "")).strip()
    patterns = (
        r"(?i)\b(?:for|with|using)\s+(?:command|prompt|request)\s*[:=]\s*(.+)$",
        r"(?i)\b(?:command|prompt|request)\s*[:=]\s*(.+)$",
        r"(?i)\bvoice session plan\s+for\s+(.+)$",
        r"(?i)\bfull voice loop plan\s+for\s+(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, stripped)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()[:160]
    return ""


def _voice_loop_status_text_for_tool(tool: str) -> str:
    labels = {
        "outlook.visible_summary": "Yes sir, checking your email now.",
        "diagnostics.email": "Yes sir, checking the email setup now.",
        "diagnostics.overnight": "Yes sir, checking the overnight workboard now.",
        "diagnostics.final_qa": "Yes sir, checking the final QA plan now.",
        "diagnostics.model_context": "Yes sir, checking the model context now.",
        "diagnostics.tool_catalog": "Yes sir, checking the tool catalog now.",
        "tools.deep_catalog": "Yes sir, checking the deeper tool catalog now.",
        "tools.handoff_plan": "Yes sir, checking how to handle that now.",
        "diagnostics.permissions": "Yes sir, checking permissions readiness now.",
        "voice.stt_candidates": "Yes sir, checking speech recognition options now.",
        "voice.stt_session_plan": "Yes sir, preparing the speech recognition test plan now.",
        "voice.session_plan": "Yes sir, planning the voice session now.",
        "voice.stt_score": "Yes sir, scoring that transcript now.",
        "screenshot.capability": "Yes sir, checking the screen setup now.",
        "app.list": "Yes sir, checking which apps I can open now.",
        "app.status": "Yes sir, checking that app now.",
        "app.running": "Yes sir, checking which apps are running now.",
        "app.open": "Yes sir, preparing the app open preview now.",
        "app.quit": "Yes sir, preparing the quit confirmation now.",
        "browser.open_url": "Yes sir, preparing that browser action now.",
        "terminal.read_only": "Yes sir, checking that locally now.",
        "shell.read_only": "Yes sir, checking that locally now.",
        "quick.local_control": "Yes sir, handling that now.",
        "system.status": "Yes sir, checking Jarvis status now.",
        "conversation.fast_local": "Yes sir, preparing a direct answer now.",
    }
    return labels.get(tool, "Yes sir, checking this now.")


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


def _looks_like_model_context_status(lower: str) -> bool:
    model_cues = (
        "model context",
        "model input",
        "model inputs",
        "model prompt",
        "model prompts",
        "prompt engineering",
        "prompt preview",
        "what do you feed",
        "what are you feeding",
        "what will you give",
        "first model",
        "middle model",
        "codex prompt",
        "tts input",
    )
    status_cues = ("show", "preview", "tell", "what", "which", "status", "diagnostic", "debug", "for")
    mutation_cues = ("change", "edit", "rewrite", "set ", "replace", "delete", "send ")
    return (
        any(cue in lower for cue in model_cues)
        and any(cue in lower for cue in status_cues)
        and not any(cue in lower for cue in mutation_cues)
    )


def _looks_like_deep_tool_catalog_status(lower: str) -> bool:
    deep_cues = (
        "deep tool catalog",
        "deeper tool catalog",
        "full tool catalog",
        "expanded tool catalog",
        "layered tool catalog",
        "deep tools",
        "more tools catalog",
        "all tool layers",
        "all tools by layer",
    )
    mutation_cues = ("change", "edit", "rewrite", "set ", "replace", "delete", "send ")
    return any(cue in lower for cue in deep_cues) and not any(cue in lower for cue in mutation_cues)


def _looks_like_tool_handoff_plan(lower: str) -> bool:
    handoff_cues = (
        "tool handoff",
        "handoff plan",
        "handoff for",
        "route tool",
        "route the tool",
        "route app.",
        "route diagnostics.",
        "route voice.",
        "how would you route",
        "how to handle tool",
        "policy handoff",
        "selected tool route",
    )
    mutation_cues = ("change", "edit", "rewrite", "set ", "replace", "delete", "send ")
    return any(cue in lower for cue in handoff_cues) and not any(cue in lower for cue in mutation_cues)


def _looks_like_tool_catalog_status(lower: str) -> bool:
    tool_cues = (
        "tool catalog",
        "tool list",
        "tool registry",
        "skill catalog",
        "skill list",
        "available tools",
        "model-callable tools",
        "what tools",
        "which tools",
    )
    status_cues = (
        "status",
        "show",
        "what",
        "which",
        "debug",
        "registry",
        "catalog",
        "fed to the model",
        "model sees",
        "mismatches",
    )
    mutation_cues = ("change", "edit", "rewrite", "set ", "replace", "delete", "send ")
    return (
        any(cue in lower for cue in tool_cues)
        and any(cue in lower for cue in status_cues)
        and not any(cue in lower for cue in mutation_cues)
    )


def _looks_like_permissions_status(lower: str) -> bool:
    permission_cues = (
        "permission",
        "permissions",
        "microphone permission",
        "speech recognition permission",
        "screen recording permission",
        "screen permission",
        "accessibility permission",
        "app control permission",
        "privacy readiness",
    )
    status_cues = ("status", "readiness", "ready", "check", "show", "what", "which", "do we have")
    mutation_cues = ("grant", "enable", "request", "open system settings", "change", "set ")
    return (
        any(cue in lower for cue in permission_cues)
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


def _looks_like_stt_session_plan(lower: str) -> bool:
    stt_cues = (
        "stt",
        "speech to text",
        "speech-to-text",
        "speech recognition",
        "voice recognition",
        "transcription",
    )
    plan_cues = (
        "session plan",
        "test plan",
        "audition plan",
        "prepare",
        "run plan",
        "testing plan",
    )
    mutation_cues = ("start recording", "record now", "listen now", "turn on microphone", "enable microphone")
    return (
        any(cue in lower for cue in stt_cues)
        and any(cue in lower for cue in plan_cues)
        and not any(cue in lower for cue in mutation_cues)
    )


def _looks_like_voice_session_plan(lower: str) -> bool:
    voice_cues = (
        "voice session",
        "voice command session",
        "full voice loop",
        "full voice session",
        "end-to-end voice",
        "wake to response",
        "wake-to-response",
        "hey jarvis loop",
        "hey jarvis session",
        "real voice loop",
    )
    plan_cues = (
        "plan",
        "logistics",
        "flow",
        "pipeline",
        "sequence",
        "how would",
        "what happens",
    )
    mutation_cues = ("start recording", "record now", "listen now", "turn on microphone", "enable microphone")
    return (
        any(cue in lower for cue in voice_cues)
        and any(cue in lower for cue in plan_cues)
        and not any(cue in lower for cue in mutation_cues)
    )


def _looks_like_stt_audition_status(lower: str) -> bool:
    stt_cues = (
        "stt",
        "speech to text",
        "speech-to-text",
        "speech recognition",
        "voice recognition",
        "transcription",
    )
    audition_cues = ("audition", "test page", "ranking page", "comparison page", "compare", "status", "ready", "where")
    mutation_cues = ("start recording", "record now", "listen now", "turn on microphone", "enable microphone")
    return (
        any(cue in lower for cue in stt_cues)
        and any(cue in lower for cue in audition_cues)
        and not any(cue in lower for cue in mutation_cues)
    )


def _looks_like_stt_candidate_status(lower: str) -> bool:
    stt_cues = (
        "stt",
        "speech to text",
        "speech-to-text",
        "speech recognition",
        "voice recognition",
        "transcription",
    )
    candidate_cues = (
        "candidate",
        "candidates",
        "engine",
        "engines",
        "model",
        "models",
        "option",
        "options",
        "which one",
        "what can we test",
        "recognizer",
        "recognizers",
    )
    mutation_cues = ("start recording", "record now", "listen now", "turn on microphone", "enable microphone", "install ")
    return (
        any(cue in lower for cue in stt_cues)
        and any(cue in lower for cue in candidate_cues)
        and not any(cue in lower for cue in mutation_cues)
    )


def _looks_like_overnight_work_status(lower: str) -> bool:
    overnight_cues = (
        "overnight",
        "workboard",
        "work board",
        "status board",
        "progress board",
        "morning report",
        "report draft",
        "8am report",
        "8:00am report",
        "8:00 am report",
    )
    status_cues = ("status", "check", "show", "where", "path", "progress", "report", "working", "done", "finished")
    mutation_cues = ("open ", "launch ", "start ", "edit ", "write ", "delete ", "move ", "sync ", "send ")
    return (
        any(cue in lower for cue in overnight_cues)
        and any(cue in lower for cue in status_cues)
        and not any(cue in lower for cue in mutation_cues)
    )


def _looks_like_final_qa_status(lower: str) -> bool:
    qa_cues = (
        "final qa",
        "foreground qa",
        "qa plan",
        "final verifier",
        "what is left to check",
        "what's left to check",
        "remaining checks",
        "deferred qa",
        "app relaunch qa",
    )
    status_cues = ("status", "plan", "check", "show", "what", "remaining", "left", "deferred", "report")
    mutation_cues = ("run ", "open ", "launch ", "start ", "click ", "record ", "capture ", "verify now")
    return (
        any(cue in lower for cue in qa_cues)
        and any(cue in lower for cue in status_cues)
        and not any(cue in lower for cue in mutation_cues)
    )


def _looks_like_workflow_plan_request(lower: str) -> bool:
    workflow_cues = (
        "workflow plan",
        "app task plan",
        "multi-app plan",
        "multi app plan",
        "teams assignment plan",
        "plan the teams assignment",
        "plan a teams workflow",
        "plan how to",
        "how would jarvis",
        "what would jarvis do",
    )
    app_task_cues = ("teams", "assignment", "app", "workflow", "screen", "click", "open", "rubric", "poster")
    action_without_plan = ("do it now", "run it now", "open it now", "click it now", "start now")
    return (
        any(cue in lower for cue in workflow_cues)
        and any(cue in lower for cue in app_task_cues)
        and not any(cue in lower for cue in action_without_plan)
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
        "screen capability",
        "screenshot status",
        "screenshot capability",
        "ocr status",
        "ocr capability",
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


def _looks_like_codex_chat_status(lower: str) -> bool:
    if "codex" not in lower:
        return False
    chat_cues = (
        "codex chat",
        "codex chats",
        "default chat",
        "default codex",
        "jarvis-codex memory",
        "jarvis codex memory",
        "codex memory",
    )
    status_cues = ("status", "check", "show", "what", "which", "configured", "using", "default")
    mutation_cues = ("change", "switch", "set ", "delete", "remove", "rename", "edit")
    return (
        any(cue in lower for cue in chat_cues)
        and any(cue in lower for cue in status_cues)
        and not any(cue in lower for cue in mutation_cues)
    )


def _looks_like_codex_activity_status(lower: str) -> bool:
    if "codex" not in lower:
        return False
    activity_cues = (
        "codex activity",
        "codex activities",
        "codex progress",
        "codex job activity",
        "codex cli",
        "codex running",
        "what is codex doing",
        "is codex working",
    )
    status_cues = ("status", "check", "show", "what", "which", "doing", "working", "running", "progress", "activity")
    mutation_cues = ("start", "ask ", "send ", "run ", "use ", "delegate", "new job")
    return (
        any(cue in lower for cue in activity_cues)
        and any(cue in lower for cue in status_cues)
        and not any(cue in lower for cue in mutation_cues)
    )


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
