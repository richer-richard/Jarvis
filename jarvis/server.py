"""Localhost dashboard server for the Jarvis prototype."""

from __future__ import annotations

import json
import atexit
import base64
import binascii
import mimetypes
import re
import signal
import threading
import time
import uuid
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .audit import AuditLogger
from .config import (
    ALLOW_NON_LOOPBACK,
    DEFAULT_HOST,
    DEFAULT_PORT,
    MAX_AUDIT_EVENTS,
    MAX_REQUEST_BYTES,
    PROJECT_ROOT,
    START_PAUSED,
    host_allowed,
)
from .planner import NATURAL_LANGUAGE_TOOL_SPECS, Planner, email_request_status_text
from .safety import classify_command, policy_summary
from .self_check import run_self_checks
from .tools import (
    browser_read_page,
    cleanup_background_audio,
    codex_activity_snapshot,
    localos_music_pending_control,
    reset_audio_actions_suppressed,
    set_audio_actions_suppressed,
    store_localos_music_snapshot,
    outlook_visible_text_summary,
    visible_screen_text_summary,
    prewarm_tts_async,
    current_speech_state,
    set_speech_muted,
    speech_mute_status,
    speak_text_async,
    stream_fast_local_chat_events,
    system_status,
    tool_registry,
    wake_audition_score,
    wake_audition_status,
    _sanitize_spoken_text,
    _sanitize_user_visible_text,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
OVERNIGHT_STATUS_DIR = PROJECT_ROOT / "runtime" / "overnight_status"
FULL_LOOP_REGRESSION_DIR = PROJECT_ROOT / "runtime" / "full_loop_regression"
MAX_VERIFICATION_AGE_SECONDS = 12 * 60 * 60
MAX_WAKE_SAMPLE_BYTES = 8 * 1024 * 1024
MAX_LOCALOS_MUSIC_SNAPSHOT_BYTES = 256 * 1024
STATUS_ROUTE_CACHE_TTL_SECONDS = 2.0
SYSTEM_STATUS_CACHE_TTL_SECONDS = 1.0
LOCALOS_MUSIC_CORS_PATHS = {
    "/api/integrations/localos/music/control",
    "/api/integrations/localos/music/snapshot",
}


class JarvisServer:
    def __init__(self, *, paused: bool = START_PAUSED, pause_reason: str = "") -> None:
        self.audit = AuditLogger()
        self.planner = Planner()
        self.paused = paused
        self.pause_reason = pause_reason or (
            "Command execution starts paused." if paused else "Command execution is enabled."
        )
        self.mode_updated_at = time.time()
        self._mode_lock = threading.RLock()
        self._system_status_cache_ttl_seconds = SYSTEM_STATUS_CACHE_TTL_SECONDS
        self._system_status_cache: dict[str, Any] | None = None
        self._system_status_cache_lock = threading.RLock()
        self._status_route_cache_ttl_seconds = STATUS_ROUTE_CACHE_TTL_SECONDS
        self._status_route_cache: dict[str, Any] | None = None
        self._status_route_cache_lock = threading.RLock()
        self.tts_prewarm = prewarm_tts_async(reason="server_startup")

    def command(
        self,
        command: str,
        history: list[dict[str, str]] | None = None,
        *,
        suppress_speech: bool = False,
        suppress_audio_actions: bool = False,
        defer_final_speech: bool = False,
    ) -> dict[str, Any]:
        audio_token = set_audio_actions_suppressed(suppress_audio_actions)
        try:
            with self._mode_lock:
                is_paused = self.paused
            if is_paused:
                assessment = classify_command(command).to_dict()
                assessment["decision"] = "paused"
                assessment["reasons"] = [*assessment.get("reasons", []), "Jarvis command execution is paused."]
                data = self._paused_result(command, assessment)
                event = self.audit.record(
                    command=command,
                    risk_level=int(assessment["risk_level"]),
                    risk_label=str(assessment["risk_label"]),
                    tool=data["tool"],
                    decision="paused",
                    summary=data["summary"],
                    details={
                        "executed": False,
                        "mode": self.mode(),
                        "result": data["result"],
                    },
                )
                data["audit_event_id"] = event.id
                if defer_final_speech:
                    _attach_stream_final_speech(data, suppress=suppress_speech)
                else:
                    _attach_auto_speech(data, reason="final", suppress=suppress_speech)
                return data

            planned = self.planner.handle(command, history=history, use_model_router=True)
            data = planned.to_dict()
            _sanitize_user_visible_result_fields(data)
            event = self.audit.record(
                command=command,
                risk_level=int(data["assessment"]["risk_level"]),
                risk_label=str(data["assessment"]["risk_label"]),
                tool=data["tool"],
                decision=str(data["assessment"]["decision"]),
                summary=data["summary"],
                details={
                    "executed": data["executed"],
                    "result": _audit_safe_result(data["tool"], data["result"]),
                    "confirmation": data.get("confirmation"),
                    "suppress_audio_actions": bool(suppress_audio_actions),
                },
            )
            data["audit_event_id"] = event.id
            if defer_final_speech:
                _attach_stream_final_speech(data, suppress=suppress_speech)
            else:
                _attach_auto_speech(data, reason="final", suppress=suppress_speech)
            return data
        finally:
            reset_audio_actions_suppressed(audio_token)

    def stream_command(
        self,
        command: str,
        history: list[dict[str, str]] | None = None,
        *,
        suppress_speech: bool = False,
        suppress_audio_actions: bool = False,
    ):
        audio_token = set_audio_actions_suppressed(suppress_audio_actions)
        try:
            yield from self._stream_command_inner(
                command,
                history=history,
                suppress_speech=suppress_speech,
                suppress_audio_actions=suppress_audio_actions,
            )
        finally:
            reset_audio_actions_suppressed(audio_token)

    def _stream_command_inner(
        self,
        command: str,
        history: list[dict[str, str]] | None = None,
        *,
        suppress_speech: bool = False,
        suppress_audio_actions: bool = False,
    ):
        with self._mode_lock:
            is_paused = self.paused
        if is_paused:
            yield {
                "event": "final",
                "data": self.command(
                    command,
                    suppress_speech=suppress_speech,
                    suppress_audio_actions=suppress_audio_actions,
                    defer_final_speech=True,
                ),
            }
            return

        preview = self.planner.preview(command, use_model_router=False, history=history).to_dict()
        if preview.get("tool") != "conversation.fast_local":
            status_text = _stream_status_text(preview)
            preview_tool = str(preview.get("tool") or "")
            preview_result = preview.get("result") if isinstance(preview.get("result"), dict) else {}
            preview_plan = preview_result.get("plan") if isinstance(preview_result.get("plan"), dict) else {}
            preview_action = str(preview_plan.get("action") or preview_result.get("action") or "")
            preview_reply = str(preview_plan.get("reply") or preview_result.get("reply") or "").strip()
            if preview_tool == "quick.local_control" and preview_action in {
                "conversation.greeting",
                "conversation.acknowledgement",
            } and preview_reply:
                yield {
                    "event": "delta",
                    "data": {"text": preview_reply},
                }
            if status_text and preview_tool != "quick.local_control":
                if preview_tool == "voice.stop_speaking":
                    speech = {"spoken": False, "status": "suppressed_for_stop_speaking", "reason": "status"}
                elif suppress_speech:
                    speech = _suppressed_speech_result(reason="status", text=status_text)
                else:
                    speech = speak_text_async(status_text, reason="status")
                yield {
                    "event": "status",
                    "data": {
                        "text": status_text,
                        "tool": preview_tool,
                        "kind": "preview",
                        "replace_streaming_preview": False,
                        "speech": speech,
                    },
                }
            yield {
                "event": "final",
                "data": self.command(
                    command,
                    history=history,
                    suppress_speech=suppress_speech,
                    suppress_audio_actions=suppress_audio_actions,
                    defer_final_speech=True,
                ),
            }
            return

        assessment = classify_command(command).to_dict()
        result: dict[str, Any] | None = None
        for event in stream_fast_local_chat_events(
            command,
            history=history,
            tool_specs=NATURAL_LANGUAGE_TOOL_SPECS,
        ):
            if event["event"] == "final_result":
                result = event["data"]
            else:
                yield event
        if result is None:
            result = {
                "tool": "conversation.fast_local",
                "backend": "unknown",
                "available": False,
                "status": "stream_missing_final",
                "executed": False,
                "fallback_used": True,
                "reply": "Jarvis streaming ended without a final answer.",
            }

        if result.get("status") == "tool_requested":
            selected_tool = str(result.get("selected_tool") or "")
            status_text = str(result.get("status_text") or "").strip()
            entities = result.get("entities") if isinstance(result.get("entities"), dict) else {}
            status_text = _tool_request_status_text(command, selected_tool, status_text, entities)
            if not status_text:
                status_text = _stream_status_text({"tool": selected_tool})
            if status_text:
                if selected_tool == "voice.stop_speaking":
                    speech = {"spoken": False, "status": "suppressed_for_stop_speaking", "reason": "status"}
                elif suppress_speech:
                    speech = _suppressed_speech_result(reason="status", text=status_text)
                else:
                    speech = speak_text_async(status_text, reason="status")
                yield {
                    "event": "status",
                    "data": {
                        "text": status_text,
                        "tool": selected_tool,
                        "kind": "tool_request",
                        "replace_streaming_preview": True,
                        "speech": speech,
                    },
                }
            planned = self.planner.handle_selected_tool(command, selected_tool, entities, history=history)
            if planned is None:
                data = {
                    "command": command,
                    "tool": "conversation.fast_local",
                    "summary": "Fast chat requested an unavailable tool.",
                    "assessment": classify_command(command).to_dict(),
                    "result": {
                        "tool": "conversation.fast_local",
                        "status": "tool_unavailable",
                        "executed": False,
                        "selected_tool": selected_tool,
                        "reply": "I could not find the right available tool for that.",
                    },
                    "executed": False,
                    "confirmation": None,
                }
                data["audit_event_id"] = self._record_command_result(data).id
                _attach_stream_final_speech(data, suppress=suppress_speech)
                yield {"event": "final", "data": data}
                return
            data = planned.to_dict()
            event = self._record_command_result(data)
            data["audit_event_id"] = event.id
            _attach_stream_final_speech(data, suppress=suppress_speech)
            yield {"event": "final", "data": data}
            return

        summary = (
            "Answered through streaming fast chat."
            if result.get("status") == "completed"
            else "Answered with streaming fast chat fallback."
        )
        if result.get("duration_human"):
            summary = f"{summary} Fast model time: {result['duration_human']}."
        first_visible_token_seconds = result.get("first_visible_token_seconds", result.get("first_token_seconds"))
        if first_visible_token_seconds is not None:
            summary = f"{summary} First visible text: {float(first_visible_token_seconds):.1f}s."
        data = {
            "command": command,
            "tool": str(result.get("tool") or "conversation.fast_local"),
            "summary": summary,
            "assessment": assessment,
            "result": result,
            "executed": bool(result.get("executed", True)),
            "confirmation": None,
        }
        event = self._record_command_result(data)
        data["audit_event_id"] = event.id
        _attach_stream_final_speech(data, suppress=suppress_speech)
        yield {"event": "final", "data": data}

    def _record_command_result(self, data: dict[str, Any]):
        _sanitize_user_visible_result_fields(data)
        return self.audit.record(
            command=str(data.get("command") or ""),
            risk_level=int(data["assessment"]["risk_level"]),
            risk_label=str(data["assessment"]["risk_label"]),
            tool=str(data["tool"]),
            decision=str(data["assessment"]["decision"]),
            summary=str(data["summary"]),
            details={
                "executed": data["executed"],
                "result": _audit_safe_result(str(data["tool"]), data["result"]),
                "confirmation": data.get("confirmation"),
            },
        )

    def native_outlook_visible_text(
        self,
        *,
        command: str,
        text: str,
        diagnostics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._mode_lock:
            is_paused = self.paused
        assessment = classify_command(command).to_dict()
        if is_paused:
            assessment["decision"] = "paused"
            assessment["reasons"] = [*assessment.get("reasons", []), "Jarvis command execution is paused."]
            data = self._paused_result(command, assessment)
        elif assessment.get("blocked"):
            data = {
                "command": command,
                "tool": "policy.block",
                "summary": "Command blocked by safety policy.",
                "assessment": assessment,
                "result": {},
                "executed": False,
                "confirmation": None,
            }
        elif assessment.get("requires_typed_confirmation"):
            data = {
                "command": command,
                "tool": "policy.strong_confirmation",
                "summary": "Command requires strong confirmation and was not executed.",
                "assessment": assessment,
                "result": {"next_step": "Show a typed confirmation prompt in the Jarvis UI."},
                "executed": False,
                "confirmation": None,
            }
        elif assessment.get("requires_confirmation"):
            data = {
                "command": command,
                "tool": "policy.confirmation",
                "summary": "Command requires confirmation and was not executed.",
                "assessment": assessment,
                "result": {"next_step": "Show a confirmation prompt in the Jarvis UI."},
                "executed": False,
                "confirmation": None,
            }
        else:
            result = outlook_visible_text_summary(text, diagnostics=diagnostics, command=command)
            data = {
                "command": command,
                "tool": "outlook.visible_summary",
                "summary": (
                    "Checked Outlook with native Apple Vision OCR."
                    if result.get("status") == "checked"
                    else "Tried Outlook native Apple Vision OCR."
                ),
                "assessment": assessment,
                "result": result,
                "executed": True,
                "confirmation": None,
            }

        event = self.audit.record(
            command=command,
            risk_level=int(data["assessment"]["risk_level"]),
            risk_label=str(data["assessment"]["risk_label"]),
            tool=data["tool"],
            decision=str(data["assessment"]["decision"]),
            summary=data["summary"],
            details={
                "executed": data["executed"],
                "result": _audit_safe_result(data["tool"], data["result"]),
                "confirmation": data.get("confirmation"),
            },
        )
        data["audit_event_id"] = event.id
        _attach_auto_speech(data, reason="final", suppress=False)
        return data

    def native_visible_screen_text(
        self,
        *,
        command: str,
        text: str,
        diagnostics: dict[str, Any] | None = None,
        suppress_speech: bool = False,
    ) -> dict[str, Any]:
        with self._mode_lock:
            is_paused = self.paused
        assessment = classify_command(command).to_dict()
        if is_paused:
            assessment["decision"] = "paused"
            assessment["reasons"] = [*assessment.get("reasons", []), "Jarvis command execution is paused."]
            data = self._paused_result(command, assessment)
        elif assessment.get("blocked"):
            data = {
                "command": command,
                "tool": "policy.block",
                "summary": "Command blocked by safety policy.",
                "assessment": assessment,
                "result": {},
                "executed": False,
                "confirmation": None,
            }
        elif assessment.get("requires_typed_confirmation"):
            data = {
                "command": command,
                "tool": "policy.strong_confirmation",
                "summary": "Command requires strong confirmation and was not executed.",
                "assessment": assessment,
                "result": {"next_step": "Show a typed confirmation prompt in the Jarvis UI."},
                "executed": False,
                "confirmation": None,
            }
        elif assessment.get("requires_confirmation"):
            data = {
                "command": command,
                "tool": "policy.confirmation",
                "summary": "Command requires confirmation and was not executed.",
                "assessment": assessment,
                "result": {"next_step": "Show a confirmation prompt in the Jarvis UI."},
                "executed": False,
                "confirmation": None,
            }
        else:
            result = visible_screen_text_summary(text, diagnostics=diagnostics, command=command)
            data = {
                "command": command,
                "tool": "screen.visible_text",
                "summary": (
                    "Read visible screen text with native Apple Vision OCR."
                    if result.get("status") in {"checked", "read_without_digest", "suspicious_content"}
                    else "Tried native visible-screen Apple Vision OCR."
                ),
                "assessment": assessment,
                "result": result,
                "executed": True,
                "confirmation": None,
            }

        event = self.audit.record(
            command=command,
            risk_level=int(data["assessment"]["risk_level"]),
            risk_label=str(data["assessment"]["risk_label"]),
            tool=data["tool"],
            decision=str(data["assessment"]["decision"]),
            summary=data["summary"],
            details={
                "executed": data["executed"],
                "result": _audit_safe_result(data["tool"], data["result"]),
                "confirmation": data.get("confirmation"),
            },
        )
        data["audit_event_id"] = event.id
        _attach_auto_speech(data, reason="final", suppress=suppress_speech)
        return data

    def native_browser_read_page(
        self,
        *,
        command: str,
        max_chars: int | None = None,
        suppress_speech: bool = False,
    ) -> dict[str, Any]:
        with self._mode_lock:
            is_paused = self.paused
        assessment = classify_command(command).to_dict()
        if is_paused:
            assessment["decision"] = "paused"
            assessment["reasons"] = [*assessment.get("reasons", []), "Jarvis command execution is paused."]
            data = self._paused_result(command, assessment)
        elif assessment.get("blocked"):
            data = {
                "command": command,
                "tool": "policy.block",
                "summary": "Command blocked by safety policy.",
                "assessment": assessment,
                "result": {},
                "executed": False,
                "confirmation": None,
            }
        elif assessment.get("requires_typed_confirmation"):
            data = {
                "command": command,
                "tool": "policy.strong_confirmation",
                "summary": "Command requires strong confirmation and was not executed.",
                "assessment": assessment,
                "result": {"next_step": "Show a typed confirmation prompt in the Jarvis UI."},
                "executed": False,
                "confirmation": None,
            }
        elif assessment.get("requires_confirmation"):
            data = {
                "command": command,
                "tool": "policy.confirmation",
                "summary": "Command requires confirmation and was not executed.",
                "assessment": assessment,
                "result": {"next_step": "Show a confirmation prompt in the Jarvis UI."},
                "executed": False,
                "confirmation": None,
            }
        else:
            result = browser_read_page(max_chars=max_chars, command=command)
            data = {
                "command": command,
                "tool": "browser.read_page",
                "summary": (
                    "Read current Chrome page text locally."
                    if result.get("status") == "read"
                    else "Tried reading current Chrome page text locally."
                ),
                "assessment": assessment,
                "result": result,
                "executed": True,
                "confirmation": None,
            }

        event = self.audit.record(
            command=command,
            risk_level=int(data["assessment"]["risk_level"]),
            risk_label=str(data["assessment"]["risk_label"]),
            tool=data["tool"],
            decision=str(data["assessment"]["decision"]),
            summary=data["summary"],
            details={
                "executed": data["executed"],
                "result": _audit_safe_result(data["tool"], data["result"]),
                "confirmation": data.get("confirmation"),
            },
        )
        data["audit_event_id"] = event.id
        _attach_auto_speech(data, reason="final", suppress=suppress_speech)
        return data

    def speak_status(self, text: str) -> dict[str, Any]:
        clean_text = str(text or "").strip()[:500]
        speech = speak_text_async(clean_text, reason="status")
        return {
            "tool": "voice.status_speech",
            "status": str(speech.get("status") or "unknown"),
            "executed": bool(speech.get("spoken")),
            "text_length": len(clean_text),
            "speech": speech,
        }

    def speech_mute_status(self) -> dict[str, Any]:
        return speech_mute_status()

    def speech_playing(self) -> dict[str, Any]:
        return current_speech_state()

    def set_speech_muted(self, muted: bool, *, source: str = "api") -> dict[str, Any]:
        return set_speech_muted(muted, source=source)

    def plan(self, command: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        return self.planner.preview(command, history=history).to_dict()

    def mode(self) -> dict[str, Any]:
        with self._mode_lock:
            return {
                "paused": self.paused,
                "reason": self.pause_reason,
                "updated_at": self.mode_updated_at,
                "commands_enabled": not self.paused,
                "allowed_while_paused": [
                    "GET /api/health",
                    "GET /api/mode",
                    "GET /api/policy",
                    "GET /api/tools",
                    "GET /api/readiness",
                    "GET /api/preflight",
                    "GET /api/codex/activity",
                    "GET /api/audit/status",
                    "GET /api/audit",
                    "GET /api/self-check",
                    "GET /api/speech/mute",
                    "GET /api/speech/playing",
                    "GET /api/integrations/localos/music/control",
                    "GET /overnight-report/",
                    "GET /overnight-workboard/",
                    "GET /capability-questions/",
                    "GET /full-loop-regression/latest.json",
                    "HEAD /overnight-report/",
                    "HEAD /overnight-workboard/",
                    "HEAD /capability-questions/",
                    "HEAD /full-loop-regression/latest.json",
                    "POST /api/mode",
                    "POST /api/plan",
                    "POST /api/speech/mute",
                    "POST /api/integrations/localos/music/snapshot",
                ],
            }

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "status": self._cached_system_status(),
            "mode": self.mode(),
        }

    def _cached_system_status(self) -> dict[str, Any]:
        with self._system_status_cache_lock:
            now = time.time()
            cache = self._system_status_cache
            if cache and now - float(cache["generated_at"]) <= self._system_status_cache_ttl_seconds:
                return cache["status"]
            status = system_status()
            self._system_status_cache = {"generated_at": now, "status": status}
            return status

    def readiness(self) -> dict[str, Any]:
        return self._cached_status_routes()["readiness"]

    def preflight(self) -> dict[str, Any]:
        return self._cached_status_routes()["preflight"]

    def _cached_status_routes(self) -> dict[str, Any]:
        with self._status_route_cache_lock:
            now = time.time()
            cache = self._status_route_cache
            if cache and now - float(cache["generated_at"]) <= self._status_route_cache_ttl_seconds:
                return cache

            status = self._cached_system_status()
            mode = self.mode()
            audit_status = self.audit.status()
            registry = tool_registry()
            self_check = run_self_checks()
            verification = _latest_verification_summary()
            policy = policy_summary()

            readiness = self._build_readiness_payload(
                status=status,
                mode=mode,
                audit_status=audit_status,
                registry=registry,
                self_check=self_check,
                verification=verification,
                generated_at=now,
            )
            preflight = self._build_preflight_payload(
                readiness=readiness,
                status=status,
                registry=registry,
                policy=policy,
                generated_at=now,
            )
            self._status_route_cache = {
                "generated_at": now,
                "readiness": readiness,
                "preflight": preflight,
            }
            return self._status_route_cache

    def _build_readiness_payload(
        self,
        *,
        status: dict[str, Any],
        mode: dict[str, Any],
        audit_status: dict[str, Any],
        registry: dict[str, Any],
        self_check: dict[str, Any],
        verification: dict[str, Any],
        generated_at: float,
    ) -> dict[str, Any]:
        tools = registry["tools"]
        unavailable_tools = [tool for tool in tools if not tool.get("available")]
        unavailable_tool_ids = [tool["id"] for tool in unavailable_tools]
        planned_unavailable_ids = [
            tool["id"]
            for tool in unavailable_tools
            if str(tool.get("mode") or "").startswith("planned")
        ]
        actionable_unavailable_ids = [
            tool["id"]
            for tool in unavailable_tools
            if tool["id"] not in planned_unavailable_ids
        ]
        failed_checks = [check["name"] for check in self_check["checks"] if not check.get("passed")]
        notes: list[str] = []
        if mode["paused"]:
            notes.append("Command execution is paused.")
        if actionable_unavailable_ids:
            notes.append(f"Unavailable tools: {', '.join(actionable_unavailable_ids)}.")
        if planned_unavailable_ids:
            notes.append(f"Planned future tools not enabled yet: {', '.join(planned_unavailable_ids)}.")
        if failed_checks:
            notes.append(f"Failed self-checks: {', '.join(failed_checks)}.")
        if audit_status.get("unreadable_lines"):
            notes.append("Audit log has unreadable lines.")

        return {
            "ok": bool(self_check["ok"] and not audit_status.get("unreadable_lines")),
            "generated_at": generated_at,
            "mode": mode,
            "worker": {
                "project_root": status["project_root"],
                "platform": status["platform"],
                "python": status["python"],
                "codex_available": bool(status["codex"]["path"]),
                "codex_version": status["codex"]["version"],
                "runtime": status.get("runtime"),
            },
            "tools": {
                "total": len(tools),
                "available": len(tools) - len(unavailable_tool_ids),
                "unavailable_ids": unavailable_tool_ids,
                "planned_unavailable_ids": planned_unavailable_ids,
                "actionable_unavailable_ids": actionable_unavailable_ids,
            },
            "self_check": {
                "ok": bool(self_check["ok"]),
                "total": len(self_check["checks"]),
                "passed": len(self_check["checks"]) - len(failed_checks),
                "failed": failed_checks,
            },
            "audit": audit_status,
            "verification": verification,
            "notes": notes,
        }

    def _build_preflight_payload(
        self,
        *,
        readiness: dict[str, Any],
        status: dict[str, Any],
        registry: dict[str, Any],
        policy: dict[str, Any],
        generated_at: float,
    ) -> dict[str, Any]:
        tool_ids = {tool["id"] for tool in registry["tools"]}
        required_tools = {
            "planner.preview",
            "system.status",
            "shell.read_only",
            "terminal.read_only",
            "workflow.app_task_plan",
            "files.search",
            "app.availability",
            "app.list",
            "app.status",
            "app.running",
            "app.frontmost",
            "app.focus",
            "app.quit",
            "screen.ocr",
            "ui.automation",
            "diagnostics.overnight",
            "diagnostics.final_qa",
            "diagnostics.model_context",
            "voice.stop_speaking",
            "diagnostics.tool_catalog",
            "tools.deep_catalog",
            "tools.handoff_plan",
            "diagnostics.permissions",
            "memory.daily_summary",
            "voice.stt_candidates",
            "voice.stt_session_plan",
            "voice.session_plan",
            "voice.stt_score",
            "voice.stt_recommendation",
            "voice.loop_simulation",
            "voice.wake_simulation",
            "voice.wake_audition",
            "voice.wake_debug",
            "safety.injection_scan",
            "diagnostics.codex_chats",
            "codex.chat_plan",
            "codex.activity",
            "codex.delegate",
            "codex.job",
            "policy.pause",
            "policy.confirmation",
            "policy.strong_confirmation",
        }
        runtime = status.get("runtime") or {}
        verification = readiness.get("verification") or {}
        audit = readiness.get("audit") or {}
        mac_tools = status.get("mac_tools") or {}

        checks = [
            _preflight_check(
                "worker_runtime_current",
                "Worker runtime metadata",
                bool(runtime.get("pid") and runtime.get("source")),
                "required",
                f"pid={runtime.get('pid', 'unknown')}",
            ),
            _preflight_check(
                "commands_enabled",
                "Command execution live",
                bool(readiness["mode"]["commands_enabled"]),
                "required",
                readiness["mode"]["reason"],
            ),
            _preflight_check(
                "audit_readable",
                "Audit log readable",
                int(audit.get("unreadable_lines") or 0) == 0,
                "required",
                f"{audit.get('event_count', 0)} events",
            ),
            _preflight_check(
                "policy_gates_loaded",
                "Policy gates loaded",
                required_tools.issubset(tool_ids) and bool(policy.get("strong_confirmation")),
                "required",
                f"{len(required_tools.intersection(tool_ids))}/{len(required_tools)} required policy/tool routes",
            ),
            _preflight_check(
                "loopback_only",
                "Loopback-only dashboard",
                not ALLOW_NON_LOOPBACK and not host_allowed("0.0.0.0"),
                "required",
                "Non-loopback binds require explicit opt-in.",
            ),
            _preflight_check(
                "json_post_guard",
                "JSON POST guard",
                bool(policy.get("request_policy")),
                "required",
                str(policy.get("request_policy", "")),
            ),
            _preflight_check(
                "latest_safe_verification",
                "Latest safe verification",
                bool(verification.get("available") and verification.get("ok") and _verification_is_fresh(verification)),
                "recommended",
                _verification_detail(verification),
            ),
            _preflight_check(
                "codex_cli_available",
                "Codex CLI available",
                bool(status.get("codex", {}).get("path")),
                "recommended",
                status.get("codex", {}).get("version") or "not detected",
            ),
            _preflight_check(
                "screenshot_tool_available",
                "Screenshot tool available",
                bool(mac_tools.get("screencapture")),
                "recommended",
                mac_tools.get("screencapture") or "not detected",
            ),
        ]
        required = [check for check in checks if check["severity"] == "required"]
        recommended = [check for check in checks if check["severity"] == "recommended"]
        summary = {
            "required_total": len(required),
            "required_passed": sum(1 for check in required if check["passed"]),
            "recommended_total": len(recommended),
            "recommended_passed": sum(1 for check in recommended if check["passed"]),
        }
        ok = summary["required_passed"] == summary["required_total"]
        notes = list(readiness["notes"])
        if not ok:
            notes.append("Preflight has required failures.")

        return {
            "ok": ok,
            "generated_at": generated_at,
            "mode": readiness["mode"],
            "summary": summary,
            "checks": checks,
            "notes": notes,
        }

    def set_mode(self, *, paused: bool, reason: str = "") -> dict[str, Any]:
        with self._mode_lock:
            mode = self._set_mode_locked(paused=paused, reason=reason)
        tool = "control.pause" if paused else "control.resume"
        event = self.audit.record(
            command=tool,
            risk_level=0,
            risk_label="Local conversation",
            tool=tool,
            decision="allowed",
            summary="Jarvis command execution paused." if paused else "Jarvis command execution resumed.",
            details={"mode": mode},
        )
        data = mode
        data["audit_event_id"] = event.id
        return data

    def configure_mode(self, *, paused: bool, reason: str = "") -> dict[str, Any]:
        with self._mode_lock:
            return self._set_mode_locked(paused=paused, reason=reason)

    def _set_mode_locked(self, *, paused: bool, reason: str = "") -> dict[str, Any]:
        self.paused = paused
        self.pause_reason = _clean_reason(reason) or (
            "Command execution is paused." if paused else "Command execution is enabled."
        )
        self.mode_updated_at = time.time()
        with self._status_route_cache_lock:
            self._status_route_cache = None
        return self.mode()

    def _paused_result(self, command: str, assessment: dict[str, Any]) -> dict[str, Any]:
        return {
            "command": command,
            "tool": "policy.pause",
            "summary": "Jarvis is paused. Command execution was not attempted.",
            "assessment": assessment,
            "result": {
                "mode": self.mode(),
                "next_step": "Resume Jarvis before running commands.",
            },
            "executed": False,
            "confirmation": None,
        }


STATE = JarvisServer()


def _tool_request_status_text(
    command: str,
    selected_tool: str,
    status_text: str,
    entities: dict[str, Any] | None = None,
) -> str:
    if selected_tool == "outlook.visible_summary":
        return email_request_status_text(command, entities)
    return status_text


def _stream_status_text(preview: dict[str, Any]) -> str:
    tool = str(preview.get("tool") or "")
    app_name = _preview_app_name(preview)
    if app_name:
        if tool == "app.open":
            return f"Opening {app_name} now."
        if tool == "app.focus":
            return f"Focusing {app_name} now."
        if tool == "app.status":
            return f"Checking {app_name} now."
    labels = {
        "outlook.visible_summary": "Checking your email now.",
        "localos.music_play": "Starting that in Music now.",
        "localos.music_stop": "Stopping that music now.",
        "localos.music_recommendations": "Checking your music picks now.",
        "localos.music_choose_from_your_pick": "Choosing from Your Pick now.",
        "localos.music_search": "Looking through your music library now.",
        "diagnostics.email": "Checking the email setup now.",
        "screenshot.capability": "Checking the screen setup now.",
        "screen.ocr": "Preparing the screen-reading plan now.",
        "browser.open_url": "Preparing that browser action now.",
        "browser.status": "Checking the browser setup now.",
        "browser.current_tab": "Checking the current Chrome tab now.",
        "browser.read_page": "Reading the current Chrome page now.",
        "browser.search_web": "Preparing that browser search now.",
        "commerce.price_convert": "Checking the price now.",
        "browser.built_in_plan": "Planning the built-in browser now.",
        "browser.session_strategy": "Checking browser session options now.",
        "browser.bookmarks_import": "Importing Chrome bookmarks now.",
        "browser.bookmarks_status": "Checking Chrome bookmarks now.",
        "browser.bookmarks_search": "Searching Chrome bookmarks now.",
        "browser.bookmark_open": "Opening that bookmark now.",
        "browser.teams_deeplinks_inventory": "Checking Teams links now.",
        "calendar.today_schedule": "Checking your calendar now.",
        "contacts.status": "Checking contact data now.",
        "contacts.lookup": "Checking contact data now.",
        "contacts.remember": "Updating contact data now.",
        "contacts.infer": "Looking for that contact locally now.",
        "codex.job": "Checking with Codex now.",
        "codex.delegate": "Checking with Codex now.",
        "diagnostics.codex_chats": "Checking the Codex chats now.",
        "codex.chat_plan": "Choosing the Codex chat now.",
        "codex.activity": "Checking Codex activity now.",
        "diagnostics.codex_speed": "Checking Codex timing now.",
        "diagnostics.remote_worker": "Checking the MacBook Air now.",
        "diagnostics.git": "Checking the GitHub branch state now.",
        "diagnostics.app_identity": "Checking app identity now.",
        "diagnostics.fast_model": "Checking the model setup now.",
        "diagnostics.device": "Checking this Mac now.",
        "diagnostics.memory_usage": "Checking memory usage now.",
        "diagnostics.memory": "Checking Jarvis memory now.",
        "models.test_plan": "Planning the model test now.",
        "memory.daily_summary": "Checking today's memory summary now.",
        "diagnostics.model_context": "Checking the model context now.",
        "voice.stop_speaking": "Stopping my voice now.",
        "diagnostics.tool_catalog": "Checking the tool catalog now.",
        "tools.deep_catalog": "Checking the deeper tool catalog now.",
        "tools.handoff_plan": "Checking how to handle that now.",
        "diagnostics.permissions": "Checking permissions readiness now.",
        "diagnostics.overnight": "Checking the overnight report now.",
        "diagnostics.final_qa": "Checking the final QA plan now.",
        "diagnostics.tts": "Checking the voice setup now.",
        "voice.stt_candidates": "Checking speech recognition options now.",
        "voice.stt_session_plan": "Preparing the speech recognition test plan now.",
        "voice.session_plan": "Planning the voice session now.",
        "voice.stt_score": "Scoring that transcript now.",
        "voice.stt_recommendation": "Ranking the speech recognition results now.",
        "voice.loop_simulation": "Testing the voice loop now.",
        "voice.wake_audition": "Checking the wake test page now.",
        "voice.wake_debug": "Analyzing the wake debug log now.",
        "files.search": "Searching your files now.",
        "app.list": "Checking which apps I can open now.",
        "app.status": "Checking that app now.",
        "app.running": "Checking which apps are running now.",
        "app.frontmost": "Checking the current app now.",
        "app.focus": "Focusing that app now.",
        "app.quit": "Preparing the quit confirmation now.",
        "ui.automation": "Preparing the app-control plan now.",
        "shell.read_only": "Checking that locally now.",
        "terminal.read_only": "Checking that locally now.",
        "workflow.app_task_plan": "Preparing the app workflow plan now.",
        "teams.assignment": "Opening Teams now.",
        "ui.overlay": "Planning the Jarvis overlay now.",
        "quick.local_control": "Handling that now.",
        "conversation.math_check": "Checking your answer now.",
        "system.status": "Checking Jarvis status now.",
        "policy.block": "Checking safety policy.",
        "policy.confirmation": "Checking safety policy.",
        "policy.strong_confirmation": "Checking safety policy.",
    }
    return labels.get(tool, "Checking this now.")


def _preview_app_name(preview: dict[str, Any]) -> str:
    result = preview.get("result")
    if not isinstance(result, dict):
        return ""
    plan = result.get("plan")
    if not isinstance(plan, dict):
        return ""
    for key in ("app", "app_name", "requested_app"):
        value = plan.get(key)
        if isinstance(value, str):
            cleaned = re.sub(r"\s+", " ", value).strip(" .")
            if cleaned:
                return cleaned[:80]
    return ""


def _attach_auto_speech(data: dict[str, Any], *, reason: str, suppress: bool = False) -> None:
    had_raw_speech_candidate = bool(data.pop("_had_raw_speech_candidate_before_sanitize", False)) or _has_raw_speech_candidate(data)
    _sanitize_user_visible_result_fields(data)
    result = data.get("result")
    if not isinstance(result, dict):
        return
    if not _should_auto_speak(data) and not had_raw_speech_candidate:
        return
    if result.get("action") == "speech.say":
        return
    text = _speech_text_from_result(result) or str(data.get("summary") or "").strip()
    if suppress:
        data["speech"] = _suppressed_speech_result(reason=reason, text=text)
        return
    if not text.strip():
        data["speech"] = {
            "spoken": False,
            "status": "empty_after_sanitization",
            "reason": reason,
            "text_preview": "",
            "spoken_text": "",
            "text_length": 0,
        }
        return
    speech = speak_text_async(text, reason=reason)
    if speech.get("spoken") or speech.get("status") not in {"disabled", "empty"}:
        data["speech"] = speech


def _deferred_follow_up_speech_result(*, reason: str) -> dict[str, Any]:
    return {
        "spoken": False,
        "status": "deferred_to_follow_up",
        "reason": reason,
    }


def _stream_should_defer_final_speech(data: dict[str, Any]) -> bool:
    result = data.get("result")
    if not isinstance(result, dict):
        return False
    return result.get("defer_stream_final_speech") is True


def _attach_stream_final_speech(data: dict[str, Any], *, suppress: bool = False) -> None:
    _sanitize_user_visible_result_fields(data)
    if _stream_should_defer_final_speech(data):
        data.pop("_had_raw_speech_candidate_before_sanitize", None)
        data["speech"] = _deferred_follow_up_speech_result(reason="final")
        return
    _attach_auto_speech(data, reason="final", suppress=suppress)


def _suppressed_speech_result(*, reason: str, text: str = "") -> dict[str, Any]:
    sanitized = _sanitize_spoken_text(text)
    result = {
        "spoken": False,
        "status": "suppressed_by_request",
        "reason": reason,
        "text_preview": sanitized,
        "spoken_text": sanitized,
        "text_length": len(sanitized),
    }
    return result


def _should_auto_speak(data: dict[str, Any]) -> bool:
    tool = str(data.get("tool") or "")
    if tool in {
        "voice.status_speech",
        "voice.stop_speaking",
        "diagnostics.model_context",
        "diagnostics.tool_catalog",
        "tools.deep_catalog",
    }:
        return False
    result = data.get("result")
    if not isinstance(result, dict):
        return False
    if result.get("action") == "speech.say":
        return False
    return bool(_speech_text_from_result(result) or str(data.get("summary") or "").strip())


def _has_raw_speech_candidate(data: dict[str, Any]) -> bool:
    tool = str(data.get("tool") or "")
    if tool in {
        "voice.status_speech",
        "voice.stop_speaking",
        "diagnostics.model_context",
        "diagnostics.tool_catalog",
        "tools.deep_catalog",
    }:
        return False
    result = data.get("result")
    if not isinstance(result, dict):
        return False
    if result.get("action") == "speech.say":
        return False
    for key in ("spoken_summary", "email_summary", "reply"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return bool(str(data.get("summary") or "").strip())


def _speech_text_from_result(result: dict[str, Any]) -> str:
    for key in ("spoken_summary", "email_summary", "reply"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            sanitized = _sanitize_spoken_text(value)
            if sanitized:
                return sanitized
    return ""


def _visible_reply_from_result(result: dict[str, Any]) -> str:
    for key in ("reply", "email_summary", "spoken_summary"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            sanitized = _sanitize_user_visible_text(value)
            if sanitized:
                return sanitized
    return ""


def _promote_result_reply(data: dict[str, Any]) -> None:
    result = data.get("result")
    if not isinstance(result, dict):
        return
    reply = _visible_reply_from_result(result)
    if reply:
        data["reply"] = reply


def _sanitize_user_visible_result_fields(data: dict[str, Any]) -> None:
    if _has_raw_speech_candidate(data):
        data["_had_raw_speech_candidate_before_sanitize"] = True
    summary = data.get("summary")
    if isinstance(summary, str) and summary.strip():
        data["summary"] = _sanitize_user_visible_text(summary)
    result = data.get("result")
    if not isinstance(result, dict):
        return
    for key in ("reply", "email_summary", "spoken_summary"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = _sanitize_user_visible_text(value)
    _promote_result_reply(data)


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "JarvisPrototype/0.1"

    def do_OPTIONS(self) -> None:  # noqa: N802
        if not self._host_header_allowed():
            self._send_json({"error": "Host header must be loopback"}, status=HTTPStatus.FORBIDDEN)
            return
        route = urlparse(self.path)
        if route.path in LOCALOS_MUSIC_CORS_PATHS:
            self.send_response(HTTPStatus.NO_CONTENT)
            self._send_common_headers(cors=True)
            self.end_headers()
            return
        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_GET(self) -> None:  # noqa: N802
        self._handle_read_request(head_only=False)

    def do_HEAD(self) -> None:  # noqa: N802
        self._handle_read_request(head_only=True)

    def _handle_read_request(self, *, head_only: bool) -> None:
        if not self._host_header_allowed():
            self._send_json({"error": "Host header must be loopback"}, status=HTTPStatus.FORBIDDEN, head_only=head_only)
            return
        route = urlparse(self.path)
        if route.path == "/":
            self._send_file(STATIC_DIR / "index.html", head_only=head_only)
            return
        if route.path in {"/wake-audition", "/wake-audition/"}:
            self._send_file(STATIC_DIR / "wake-audition.html", head_only=head_only)
            return
        if route.path in {"/overnight-report", "/overnight-report/"}:
            self._send_runtime_file(OVERNIGHT_STATUS_DIR / "report.html", root=OVERNIGHT_STATUS_DIR, head_only=head_only)
            return
        if route.path in {"/overnight-workboard", "/overnight-workboard/"}:
            self._send_runtime_file(OVERNIGHT_STATUS_DIR / "index.html", root=OVERNIGHT_STATUS_DIR, head_only=head_only)
            return
        if route.path in {"/capability-questions", "/capability-questions/"}:
            self._send_runtime_file(OVERNIGHT_STATUS_DIR / "capability_questions.html", root=OVERNIGHT_STATUS_DIR, head_only=head_only)
            return
        if route.path == "/full-loop-regression/latest.json":
            self._send_runtime_file(FULL_LOOP_REGRESSION_DIR / "latest.json", root=FULL_LOOP_REGRESSION_DIR, head_only=head_only)
            return
        if route.path.startswith("/static/"):
            self._send_file(STATIC_DIR / route.path.removeprefix("/static/"), head_only=head_only)
            return
        if route.path == "/api/health":
            self._send_json(STATE.health(), head_only=head_only)
            return
        if route.path == "/api/mode":
            self._send_json(STATE.mode(), head_only=head_only)
            return
        if route.path == "/api/policy":
            self._send_json(policy_summary(), head_only=head_only)
            return
        if route.path == "/api/tools":
            self._send_json(tool_registry(), head_only=head_only)
            return
        if route.path == "/api/readiness":
            self._send_json(STATE.readiness(), head_only=head_only)
            return
        if route.path == "/api/preflight":
            self._send_json(STATE.preflight(), head_only=head_only)
            return
        if route.path == "/api/codex/activity":
            query = parse_qs(route.query)
            limit = _bounded_int(query.get("limit", ["3"])[0], default=3, minimum=1, maximum=10)
            self._send_json(codex_activity_snapshot(limit=limit), head_only=head_only)
            return
        if route.path == "/api/audit/status":
            self._send_json(STATE.audit.status(), head_only=head_only)
            return
        if route.path == "/api/audit":
            query = parse_qs(route.query)
            limit = _bounded_int(query.get("limit", ["50"])[0], default=50, minimum=1, maximum=MAX_AUDIT_EVENTS)
            self._send_json({"events": STATE.audit.recent(limit=limit)}, head_only=head_only)
            return
        if route.path == "/api/self-check":
            self._send_json(run_self_checks(), head_only=head_only)
            return
        if route.path == "/api/speech/mute":
            self._send_json(STATE.speech_mute_status(), head_only=head_only)
            return
        if route.path == "/api/speech/playing":
            self._send_json(STATE.speech_playing(), head_only=head_only)
            return
        if route.path == "/api/integrations/localos/music/control":
            query = parse_qs(route.query)
            since = str(query.get("since", [""])[0] or "")
            self._send_json(localos_music_pending_control(since=since), head_only=head_only, cors=True)
            return
        if route.path == "/api/wake-audition/status":
            self._send_json(wake_audition_status(), head_only=head_only)
            return
        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND, head_only=head_only)

    def do_POST(self) -> None:  # noqa: N802
        if not self._host_header_allowed():
            self._send_json({"error": "Host header must be loopback"}, status=HTTPStatus.FORBIDDEN)
            return
        route = urlparse(self.path)
        if route.path == "/api/mode":
            try:
                payload = self._read_json_payload()
                if "paused" not in payload or not isinstance(payload["paused"], bool):
                    self._send_json({"error": "`paused` must be true or false"}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json(STATE.set_mode(paused=payload["paused"], reason=str(payload.get("reason", ""))))
            except RequestBodyTooLarge:
                    self._send_json({"error": "Request body too large"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            except UnsupportedContentType:
                self._send_json({"error": "Content-Type must be application/json"}, status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            except (TypeError, ValueError, UnicodeDecodeError) as exc:
                self._send_json({"error": f"Invalid JSON: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return
        if route.path == "/api/plan":
            try:
                payload = self._read_json_payload()
                command = _payload_command_text(payload)
                history = _conversation_history_from_payload(payload, current_command=command)
            except RequestBodyTooLarge:
                self._send_json({"error": "Request body too large"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            except UnsupportedContentType:
                self._send_json({"error": "Content-Type must be application/json"}, status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                return
            except (TypeError, ValueError, UnicodeDecodeError) as exc:
                self._send_json({"error": f"Invalid JSON: {exc}"}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(STATE.plan(command, history=history))
            return
        if route.path == "/api/outlook/visible-text":
            try:
                payload = self._read_json_payload()
                command = str(payload.get("command", "check my email"))
                text = str(payload.get("text", ""))
                diagnostics = payload.get("diagnostics", {})
                if not isinstance(diagnostics, dict):
                    diagnostics = {}
            except RequestBodyTooLarge:
                self._send_json({"error": "Request body too large"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            except UnsupportedContentType:
                self._send_json({"error": "Content-Type must be application/json"}, status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                return
            except (TypeError, ValueError, UnicodeDecodeError) as exc:
                self._send_json({"error": f"Invalid JSON: {exc}"}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(
                STATE.native_outlook_visible_text(
                    command=command,
                    text=text[:12000],
                    diagnostics=diagnostics,
                )
            )
            return
        if route.path == "/api/screen/visible-text":
            try:
                payload = self._read_json_payload()
                command = str(payload.get("command", "read the visible screen"))
                text = str(payload.get("text", ""))
                diagnostics = payload.get("diagnostics", {})
                suppress_speech = payload.get("suppress_speech") is True or payload.get("speak") is False
                if not isinstance(diagnostics, dict):
                    diagnostics = {}
            except RequestBodyTooLarge:
                self._send_json({"error": "Request body too large"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            except UnsupportedContentType:
                self._send_json({"error": "Content-Type must be application/json"}, status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                return
            except (TypeError, ValueError, UnicodeDecodeError) as exc:
                self._send_json({"error": f"Invalid JSON: {exc}"}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(
                STATE.native_visible_screen_text(
                    command=command,
                    text=text[:12000],
                    diagnostics=diagnostics,
                    suppress_speech=suppress_speech,
                )
            )
            return
        if route.path == "/api/browser/read-page":
            try:
                payload = self._read_json_payload()
                command = str(payload.get("command", "read the current Chrome page"))
                raw_max_chars = payload.get("max_chars")
                suppress_speech = payload.get("suppress_speech") is True or payload.get("speak") is False
                max_chars = int(raw_max_chars) if raw_max_chars not in (None, "") else None
            except RequestBodyTooLarge:
                self._send_json({"error": "Request body too large"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            except UnsupportedContentType:
                self._send_json({"error": "Content-Type must be application/json"}, status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                return
            except (TypeError, ValueError, UnicodeDecodeError) as exc:
                self._send_json({"error": f"Invalid JSON: {exc}"}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(
                STATE.native_browser_read_page(
                    command=command,
                    max_chars=max_chars,
                    suppress_speech=suppress_speech,
                )
            )
            return
        if route.path == "/api/speech/status":
            try:
                payload = self._read_json_payload()
                text = str(payload.get("text", ""))
            except RequestBodyTooLarge:
                self._send_json({"error": "Request body too large"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            except UnsupportedContentType:
                self._send_json({"error": "Content-Type must be application/json"}, status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                return
            except (TypeError, ValueError, UnicodeDecodeError) as exc:
                self._send_json({"error": f"Invalid JSON: {exc}"}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(STATE.speak_status(text))
            return
        if route.path == "/api/speech/mute":
            try:
                payload = self._read_json_payload()
                if "muted" not in payload or not isinstance(payload["muted"], bool):
                    self._send_json({"error": "`muted` must be true or false"}, status=HTTPStatus.BAD_REQUEST)
                    return
            except RequestBodyTooLarge:
                self._send_json({"error": "Request body too large"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            except UnsupportedContentType:
                self._send_json({"error": "Content-Type must be application/json"}, status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                return
            except (TypeError, ValueError, UnicodeDecodeError) as exc:
                self._send_json({"error": f"Invalid JSON: {exc}"}, status=HTTPStatus.BAD_REQUEST)
                return
            source = _payload_speech_mute_source(payload)
            self._send_json(STATE.set_speech_muted(payload["muted"], source=source))
            return
        if route.path == "/api/wake-audition/score":
            try:
                payload = self._read_json_payload()
                transcript = str(payload.get("transcript", ""))
                threshold = payload.get("threshold")
                noise_db = payload.get("noise_db")
            except RequestBodyTooLarge:
                self._send_json({"error": "Request body too large"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            except UnsupportedContentType:
                self._send_json({"error": "Content-Type must be application/json"}, status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                return
            except (TypeError, ValueError, UnicodeDecodeError) as exc:
                self._send_json({"error": f"Invalid JSON: {exc}"}, status=HTTPStatus.BAD_REQUEST)
                return
            parsed_threshold = _optional_float(threshold)
            parsed_noise_db = _optional_float(noise_db)
            self._send_json(wake_audition_score(transcript, threshold=parsed_threshold, noise_db=parsed_noise_db))
            return
        if route.path == "/api/wake-audition/sample":
            try:
                payload = self._read_json_payload(max_bytes=MAX_WAKE_SAMPLE_BYTES)
                self._send_json(_save_wake_audition_sample(payload))
            except RequestBodyTooLarge:
                self._send_json({"error": "Audio sample body too large"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            except UnsupportedContentType:
                self._send_json({"error": "Content-Type must be application/json"}, status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            except (TypeError, ValueError, UnicodeDecodeError, binascii.Error) as exc:
                self._send_json({"error": f"Invalid wake sample: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            except OSError as exc:
                self._send_json({"error": f"Could not save wake sample: {exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if route.path == "/api/integrations/localos/music/snapshot":
            try:
                payload = self._read_json_or_text_payload(max_bytes=MAX_LOCALOS_MUSIC_SNAPSHOT_BYTES)
                self._send_json(store_localos_music_snapshot(payload), cors=True)
            except RequestBodyTooLarge:
                self._send_json({"error": "Local OS music snapshot body too large"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE, cors=True)
            except UnsupportedContentType:
                self._send_json({"error": "Content-Type must be application/json or text/plain"}, status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE, cors=True)
            except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._send_json({"error": f"Invalid Local OS music snapshot: {exc}"}, status=HTTPStatus.BAD_REQUEST, cors=True)
            except OSError as exc:
                self._send_json({"error": f"Could not save Local OS music snapshot: {exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR, cors=True)
            return
        if route.path == "/api/command/stream":
            try:
                payload = self._read_json_payload()
                command = _payload_command_text(payload)
                if not command:
                    self._send_json({"error": "Command text is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                history = _conversation_history_from_payload(payload, current_command=command)
                suppress_speech = _payload_suppresses_speech(payload)
                suppress_audio_actions = _payload_suppresses_audio_actions(payload)
            except RequestBodyTooLarge:
                self._send_json({"error": "Request body too large"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            except UnsupportedContentType:
                self._send_json({"error": "Content-Type must be application/json"}, status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                return
            except (TypeError, ValueError, UnicodeDecodeError) as exc:
                self._send_json({"error": f"Invalid JSON: {exc}"}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_event_stream(
                STATE.stream_command(
                    command,
                    history=history,
                    suppress_speech=suppress_speech,
                    suppress_audio_actions=suppress_audio_actions,
                )
            )
            return
        if route.path != "/api/command":
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self._read_json_payload()
            command = _payload_command_text(payload)
            if not command:
                self._send_json({"error": "Command text is required"}, status=HTTPStatus.BAD_REQUEST)
                return
            history = _conversation_history_from_payload(payload, current_command=command)
            suppress_speech = _payload_suppresses_speech(payload)
            suppress_audio_actions = _payload_suppresses_audio_actions(payload)
        except RequestBodyTooLarge:
            self._send_json({"error": "Request body too large"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        except UnsupportedContentType:
            self._send_json({"error": "Content-Type must be application/json"}, status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return
        except (TypeError, ValueError, UnicodeDecodeError) as exc:
            self._send_json({"error": f"Invalid JSON: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return
        self._send_json(
            STATE.command(
                command,
                history=history,
                suppress_speech=suppress_speech,
                suppress_audio_actions=suppress_audio_actions,
            )
        )

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_file(self, path: Path, *, head_only: bool = False) -> None:
        resolved = path.resolve()
        static_root = STATIC_DIR.resolve()
        if not resolved.is_relative_to(static_root) or not resolved.exists() or not resolved.is_file():
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND, head_only=head_only)
            return
        content = resolved.read_bytes()
        content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self._send_common_headers()
        self.end_headers()
        if not head_only:
            self.wfile.write(content)

    def _send_runtime_file(self, path: Path, *, root: Path, head_only: bool = False) -> None:
        resolved = path.resolve()
        runtime_root = root.resolve()
        if not resolved.is_relative_to(runtime_root) or not resolved.exists() or not resolved.is_file():
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND, head_only=head_only)
            return
        content = resolved.read_bytes()
        content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self._send_common_headers(style_src="'self' 'unsafe-inline'")
        self.end_headers()
        if not head_only:
            self.wfile.write(content)

    def _send_json(
        self,
        data: Any,
        status: HTTPStatus = HTTPStatus.OK,
        *,
        head_only: bool = False,
        cors: bool = False,
    ) -> None:
        content = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self._send_common_headers(cors=cors)
        self.end_headers()
        if not head_only:
            self.wfile.write(content)

    def _send_event_stream(self, events) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self._send_common_headers()
        self.end_headers()
        try:
            for event in events:
                name = str(event.get("event") or "message")
                data = json.dumps(event.get("data", {}), ensure_ascii=False, separators=(",", ":"))
                self.wfile.write(f"event: {name}\n".encode("utf-8"))
                self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_common_headers(self, *, style_src: str = "'self'", cors: bool = False) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        if cors:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            f"style-src {style_src}; "
            "img-src 'self' data:; "
            "media-src 'self' blob: data:; "
            "connect-src 'self'; "
            "base-uri 'none'; "
            "form-action 'none'; "
            "frame-ancestors 'none'",
        )

    def _host_header_allowed(self) -> bool:
        return host_allowed(_host_from_header(self.headers.get("Host", "")))

    def _read_json_payload(self, *, max_bytes: int = MAX_REQUEST_BYTES) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise UnsupportedContentType()
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length < 0:
            raise ValueError("Content-Length must be non-negative")
        if content_length > max_bytes:
            raise RequestBodyTooLarge()
        body = self.rfile.read(content_length)
        payload = json.loads(body.decode("utf-8") or "{}")
        if not isinstance(payload, dict):
            raise TypeError("JSON body must be an object")
        return payload

    def _read_json_or_text_payload(self, *, max_bytes: int = MAX_REQUEST_BYTES) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type not in {"application/json", "text/plain"}:
            raise UnsupportedContentType()
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length < 0:
            raise ValueError("Content-Length must be non-negative")
        if content_length > max_bytes:
            raise RequestBodyTooLarge()
        body = self.rfile.read(content_length)
        payload = json.loads(body.decode("utf-8") or "{}")
        if not isinstance(payload, dict):
            raise TypeError("JSON body must be an object")
        return payload


class RequestBodyTooLarge(Exception):
    """Raised when a request body exceeds the local prototype cap."""


class UnsupportedContentType(Exception):
    """Raised when a JSON endpoint receives a non-JSON body."""


def run(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, start_paused: bool | None = None) -> None:
    if not host_allowed(host):
        raise ValueError(
            "Jarvis dashboard only binds to loopback hosts by default. "
            "Use 127.0.0.1, localhost, ::1, or set JARVIS_ALLOW_NON_LOOPBACK=1."
        )
    if not 1 <= int(port) <= 65535:
        raise ValueError("Jarvis dashboard port must be between 1 and 65535.")
    try:
        PROJECT_ROOT.joinpath("runtime").mkdir(exist_ok=True)
    except OSError:
        pass
    cleanup_background_audio(reason="server_startup")
    _install_background_audio_shutdown_cleanup()
    if start_paused is not None:
        STATE.configure_mode(
            paused=start_paused,
            reason="Dashboard started in paused mode." if start_paused else "Dashboard started in live mode.",
        )
    httpd = ThreadingHTTPServer((host, port), RequestHandler)
    print(f"Jarvis dashboard: http://{host}:{port}")
    httpd.serve_forever()


_BACKGROUND_AUDIO_SHUTDOWN_CLEANUP_INSTALLED = False


def _install_background_audio_shutdown_cleanup() -> None:
    global _BACKGROUND_AUDIO_SHUTDOWN_CLEANUP_INSTALLED
    if _BACKGROUND_AUDIO_SHUTDOWN_CLEANUP_INSTALLED:
        return
    _BACKGROUND_AUDIO_SHUTDOWN_CLEANUP_INSTALLED = True
    atexit.register(cleanup_background_audio, reason="server_exit")

    def handle_signal(signum: int, _frame: Any) -> None:
        cleanup_background_audio(reason=f"signal_{signum}")
        raise SystemExit(0)

    for shutdown_signal in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(shutdown_signal, handle_signal)
        except (OSError, ValueError):
            pass


def _bounded_int(raw: str, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _payload_suppresses_speech(payload: dict[str, Any]) -> bool:
    return payload.get("suppress_speech") is True or payload.get("speak") is False


def _payload_suppresses_audio_actions(payload: dict[str, Any]) -> bool:
    return payload.get("suppress_audio_actions") is True or payload.get("suppress_audio") is True


def _payload_speech_mute_source(payload: dict[str, Any]) -> str:
    raw = str(payload.get("source") or "api").strip().lower()
    source = re.sub(r"[^a-z0-9_.-]+", "_", raw).strip("._-")
    return source[:80] or "api"


def _payload_command_text(payload: dict[str, Any]) -> str:
    for key in ("command", "message", "text", "prompt"):
        if key not in payload:
            continue
        text = " ".join(str(payload.get(key) or "").split())
        if text:
            return text
    return ""


def _optional_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value != value:
        return None
    return value


def _save_wake_audition_sample(payload: dict[str, Any]) -> dict[str, Any]:
    raw_audio = str(payload.get("audio_base64") or "")
    if "," in raw_audio and raw_audio[:64].lower().startswith("data:"):
        raw_audio = raw_audio.split(",", 1)[1]
    audio_bytes = base64.b64decode(raw_audio.encode("ascii"), validate=True)
    if not audio_bytes:
        raise ValueError("audio_base64 is empty")
    if len(audio_bytes) > MAX_WAKE_SAMPLE_BYTES:
        raise ValueError("audio sample is too large")

    sample_id = _clean_sample_id(payload.get("sample_id"))
    mime_type = _clean_mime_type(payload.get("mime_type"))
    extension = _audio_extension(mime_type)
    sample_dir = PROJECT_ROOT / "runtime" / "wake_audition" / "samples"
    sample_dir.mkdir(parents=True, exist_ok=True)
    audio_path = sample_dir / f"{sample_id}{extension}"
    metadata_path = sample_dir / f"{sample_id}.json"

    transcript = str(payload.get("transcript") or "")[:1000]
    threshold = _optional_float(payload.get("threshold"))
    noise_db = _optional_float(payload.get("noise_db"))
    score = wake_audition_score(transcript, threshold=threshold, noise_db=noise_db)
    audio_path.write_bytes(audio_bytes)
    metadata = {
        "sample_id": sample_id,
        "created_at": time.time(),
        "mime_type": mime_type,
        "audio_path": str(audio_path),
        "bytes": len(audio_bytes),
        "transcript": transcript,
        "threshold": score.get("threshold"),
        "noise_db": noise_db,
        "score": score,
        "source": str(payload.get("source") or "wake-audition-page")[:80],
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "tool": "voice.wake_audition",
        "status": "saved",
        "executed": True,
        "read_private_content": False,
        "sent_audio": False,
        "sample_id": sample_id,
        "mime_type": mime_type,
        "bytes": len(audio_bytes),
        "audio_path": str(audio_path),
        "metadata_path": str(metadata_path),
        "score": score,
        "reply": "Wake sample saved locally under Jarvis runtime.",
    }


def _clean_sample_id(raw: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(raw or "").strip())[:80].strip(".-")
    if not text:
        text = f"wake-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    return text


def _clean_mime_type(raw: Any) -> str:
    text = str(raw or "audio/webm").split(";", 1)[0].strip().lower()
    if not re.fullmatch(r"audio/[a-z0-9.+-]+", text):
        return "audio/webm"
    return text[:80]


def _audio_extension(mime_type: str) -> str:
    mapping = {
        "audio/webm": ".webm",
        "audio/mp4": ".m4a",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/ogg": ".ogg",
    }
    return mapping.get(mime_type, ".audio")


def _clean_reason(reason: str) -> str:
    return " ".join(reason.strip().split())[:240]


def _conversation_history_from_payload(payload: dict[str, Any], *, current_command: str) -> list[dict[str, str]]:
    raw_history = payload.get("history")
    if not isinstance(raw_history, list):
        return []
    current_clean = " ".join(current_command.strip().split())
    history: list[dict[str, str]] = []
    for item in raw_history[-16:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        raw_text = item.get("text")
        if raw_text is None:
            raw_text = item.get("content")
        text = " ".join(str(raw_text or "").split())
        if role == "jarvis":
            role = "assistant"
        if role not in {"user", "assistant"} or not text:
            continue
        if role == "user" and text == current_clean:
            continue
        history.append({"role": role, "text": text[:900]})
    return history[-10:]


def _host_from_header(value: str) -> str:
    host = value.strip()
    if host.startswith("[") and "]" in host:
        return host[1:].split("]", 1)[0]
    if host.count(":") == 1:
        return host.rsplit(":", 1)[0]
    return host


def _latest_verification_summary() -> dict[str, Any]:
    try:
        reports = sorted(PROJECT_ROOT.joinpath("runtime", "verification").glob("verify-safe-*.json"))
    except OSError as error:
        return {
            "available": False,
            "ok": False,
            "error": str(error),
        }
    if not reports:
        return {"available": False}

    latest = reports[-1]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "available": False,
            "path": str(latest.relative_to(PROJECT_ROOT)),
            "error": str(error),
        }

    results = data.get("results", [])
    passed = sum(1 for result in results if result.get("passed"))
    generated_at = _verification_timestamp(latest, data)
    age_seconds = max(0.0, time.time() - generated_at)
    return {
        "available": True,
        "path": str(latest.relative_to(PROJECT_ROOT)),
        "ok": bool(data.get("ok")),
        "passed": passed,
        "total": len(results),
        "generated_at": generated_at,
        "age_seconds": round(age_seconds, 3),
        "age_human": _format_duration(age_seconds),
    }


def _preflight_check(id: str, label: str, passed: bool, severity: str, detail: str) -> dict[str, Any]:
    return {
        "id": id,
        "label": label,
        "passed": bool(passed),
        "severity": severity,
        "detail": detail,
    }


def _verification_detail(verification: dict[str, Any]) -> str:
    if not verification.get("available"):
        return "No safe verification report found."
    count = f"{verification.get('passed', 0)}/{verification.get('total', 0)}"
    path = verification.get("path") or "unknown report"
    state = "passed" if verification.get("ok") else "failed"
    age = verification.get("age_human")
    suffix = f", {age} old" if age else ""
    stale = "" if _verification_is_fresh(verification) else "; stale, rerun scripts/verify_safe.py"
    return f"{state} {count} at {path}{suffix}{stale}"


def _verification_is_fresh(verification: dict[str, Any], max_age_seconds: int = MAX_VERIFICATION_AGE_SECONDS) -> bool:
    try:
        age_seconds = float(verification.get("age_seconds"))
    except (TypeError, ValueError):
        return False
    return 0 <= age_seconds <= max_age_seconds


def _verification_timestamp(path: Path, data: dict[str, Any]) -> float:
    raw = data.get("completed_at") or data.get("generated_at")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return path.stat().st_mtime


def _format_duration(seconds: float) -> str:
    total_seconds = max(0, int(round(seconds)))
    minutes, remaining_seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {remaining_seconds}s"
    if minutes:
        return f"{minutes}m {remaining_seconds}s"
    return f"{remaining_seconds}s"


def _audit_safe_result(tool: str, result: dict[str, Any]) -> dict[str, Any]:
    if tool in {"codex.delegate", "codex.job"}:
        safe = {
            key: value
            for key, value in result.items()
            if key not in {"stdout", "stderr", "reply", "planned_command", "job"}
        }
        if tool == "codex.job" and isinstance(result.get("job"), dict):
            job = result["job"]
            safe["job_status"] = job.get("status")
            safe["job_id"] = job.get("job_id")
        safe["model_output_omitted"] = True
        return safe

    if tool in {"conversation.codex", "conversation.fast_local"}:
        safe = {
            key: value
            for key, value in result.items()
            if key not in {"stdout", "stderr", "reply"}
        }
        safe["model_output_omitted"] = True
        return safe

    if tool == "localos.music_recommendations":
        safe = {
            key: value
            for key, value in result.items()
            if key not in {"tracks", "reply", "current_track", "fallback_library"}
        }
        safe["music_track_details_omitted"] = True
        safe["track_count"] = len(result.get("tracks") or []) if isinstance(result.get("tracks"), list) else 0
        return safe

    if tool == "localos.music_search":
        safe = {
            key: value
            for key, value in result.items()
            if key not in {"matches", "reply", "fallback_library"}
        }
        safe["music_match_details_omitted"] = True
        safe["match_count"] = len(result.get("matches") or []) if isinstance(result.get("matches"), list) else 0
        return safe

    if tool == "localos.music_play":
        safe = {
            key: value
            for key, value in result.items()
            if key not in {"selected_track", "control", "reply"}
        }
        safe["music_play_details_omitted"] = True
        safe["queued"] = result.get("status") == "queued"
        return safe

    if tool == "localos.music_choose_from_your_pick":
        safe = {
            key: value
            for key, value in result.items()
            if key not in {"candidates", "selected_track", "reply"}
        }
        safe["music_choice_details_omitted"] = True
        safe["candidate_count"] = len(result.get("candidates") or []) if isinstance(result.get("candidates"), list) else 0
        return safe

    if tool in {"browser.current_tab", "browser.read_page"}:
        safe = {
            key: value
            for key, value in result.items()
            if key not in {"page_text", "reply", "injection_scan", "title", "url", "stdout", "stderr"}
        }
        injection_scan = result.get("injection_scan") if isinstance(result, dict) else None
        if isinstance(injection_scan, dict):
            findings = injection_scan.get("findings")
            safe["injection_scan_status"] = injection_scan.get("status")
            safe["injection_findings_count"] = len(findings) if isinstance(findings, list) else 0
        safe["browser_private_details_omitted"] = True
        safe["page_text_chars"] = int(result.get("page_text_chars") or 0)
        return safe

    if tool == "screen.visible_text":
        safe = {
            key: value
            for key, value in result.items()
            if key
            not in {
                "page_digest",
                "page_digest_items",
                "assignment_digest_items",
                "reply",
                "spoken_summary",
                "injection_scan",
                "window_title",
                "stdout",
                "stderr",
            }
        }
        injection_scan = result.get("injection_scan") if isinstance(result, dict) else None
        if isinstance(injection_scan, dict):
            findings = injection_scan.get("findings")
            safe["injection_scan_status"] = injection_scan.get("status")
            safe["injection_findings_count"] = len(findings) if isinstance(findings, list) else 0
        safe["visible_screen_private_details_omitted"] = True
        safe["visible_text_chars"] = int(result.get("visible_text_chars") or 0)
        return safe

    if tool in {"browser.bookmarks_import", "browser.bookmarks_search", "browser.bookmark_open"}:
        safe = {
            key: value
            for key, value in result.items()
            if key not in {"bookmarks", "matches", "selected_bookmark", "reply", "url", "title", "profiles", "errors"}
        }
        safe["bookmark_private_details_omitted"] = True
        safe["bookmark_count"] = int(result.get("bookmark_count") or 0)
        safe["match_count"] = len(result.get("matches") or []) if isinstance(result.get("matches"), list) else int(result.get("match_count") or 0)
        safe["profile_count"] = int(result.get("profile_count") or 0)
        return safe

    if tool == "browser.teams_deeplinks_inventory":
        safe = {
            key: value
            for key, value in result.items()
            if key not in {"links", "reply", "url", "title", "errors"}
        }
        safe["teams_deeplink_private_details_omitted"] = True
        safe["row_count"] = int(result.get("row_count") or 0)
        safe["class_count"] = int(result.get("class_count") or 0)
        safe["assignment_count"] = int(result.get("assignment_count") or 0)
        safe["profile_count"] = int(result.get("profile_count") or 0)
        safe["error_count"] = len(result.get("errors") or []) if isinstance(result.get("errors"), list) else int(result.get("error_count") or 0)
        return safe

    if tool == "teams.assignment":
        safe = {
            key: value
            for key, value in result.items()
            if key not in {"selected_bookmark", "selected_teams_deeplink", "matches", "reply", "url", "title", "browser_open_plan"}
        }
        safe["teams_browser_private_details_omitted"] = True
        safe["browser_target_available"] = bool(result.get("browser_target_available"))
        safe["read_private_browser_metadata"] = bool(result.get("read_private_browser_metadata"))
        return safe

    if tool == "calendar.today_schedule":
        events = result.get("events") if isinstance(result, dict) else None
        safe = {
            key: value
            for key, value in result.items()
            if key not in {"events", "reply", "stdout", "stderr", "error"}
        }
        safe["calendar_private_details_omitted"] = True
        safe["event_count"] = len(events) if isinstance(events, list) else int(result.get("event_count") or 0)
        return safe

    if tool in {"contacts.status", "contacts.lookup", "contacts.remember", "contacts.infer"}:
        candidates = result.get("candidates") if isinstance(result, dict) else None
        aliases = result.get("aliases") if isinstance(result, dict) else None
        safe = {
            key: value
            for key, value in result.items()
            if key
            not in {
                "aliases",
                "suggestions",
                "candidates",
                "display_name",
                "alias",
                "reply",
                "path",
            }
        }
        safe["contact_private_details_omitted"] = True
        safe["alias_count"] = len(aliases) if isinstance(aliases, list) else int(result.get("alias_count") or 0)
        safe["candidate_count"] = len(candidates) if isinstance(candidates, list) else 0
        return safe

    if tool != "outlook.visible_summary":
        return result

    messages = result.get("messages") if isinstance(result, dict) else None
    safe = {
        key: value
        for key, value in result.items()
        if key not in {"messages", "reply", "email_summary", "stdout", "stderr", "injection_scan"}
    }
    injection_scan = result.get("injection_scan") if isinstance(result, dict) else None
    if isinstance(injection_scan, dict):
        findings = injection_scan.get("findings")
        safe["injection_scan_status"] = injection_scan.get("status")
        safe["injection_findings_count"] = len(findings) if isinstance(findings, list) else 0
    safe["message_count"] = len(messages) if isinstance(messages, list) else int(result.get("message_count") or 0)
    safe["private_message_details_omitted"] = True
    safe["email_summary_omitted"] = "email_summary" in result
    return safe


if __name__ == "__main__":
    run()
