"""Localhost dashboard server for the Jarvis prototype."""

from __future__ import annotations

import json
import mimetypes
import threading
import time
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
from .planner import NATURAL_LANGUAGE_TOOL_SPECS, Planner
from .safety import classify_command, policy_summary
from .self_check import run_self_checks
from .tools import (
    codex_activity_snapshot,
    outlook_visible_text_summary,
    prewarm_tts_async,
    speak_text_async,
    stream_fast_local_chat_events,
    system_status,
    tool_registry,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_VERIFICATION_AGE_SECONDS = 12 * 60 * 60


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
        self.tts_prewarm = prewarm_tts_async(reason="server_startup")

    def command(self, command: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
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
            _attach_auto_speech(data, reason="final")
            return data

        planned = self.planner.handle(command, history=history, use_model_router=False)
        data = planned.to_dict()
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
        _attach_auto_speech(data, reason="final")
        return data

    def stream_command(self, command: str, history: list[dict[str, str]] | None = None):
        with self._mode_lock:
            is_paused = self.paused
        if is_paused:
            yield {"event": "final", "data": self.command(command)}
            return

        preview = self.planner.preview(command, use_model_router=False).to_dict()
        if preview.get("tool") != "conversation.fast_local":
            status_text = _stream_status_text(preview)
            if status_text:
                speech = speak_text_async(status_text, reason="status")
                yield {
                    "event": "status",
                    "data": {
                        "text": status_text,
                        "tool": preview.get("tool"),
                        "speech": speech,
                    },
                }
            yield {"event": "final", "data": self.command(command)}
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
            if not status_text:
                status_text = _stream_status_text({"tool": selected_tool})
            if status_text:
                speech = speak_text_async(status_text, reason="status")
                yield {
                    "event": "status",
                    "data": {
                        "text": status_text,
                        "tool": selected_tool,
                        "speech": speech,
                    },
                }
            entities = result.get("entities") if isinstance(result.get("entities"), dict) else {}
            planned = self.planner.handle_selected_tool(command, selected_tool, entities)
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
                _attach_auto_speech(data, reason="final")
                yield {"event": "final", "data": data}
                return
            data = planned.to_dict()
            event = self._record_command_result(data)
            data["audit_event_id"] = event.id
            _attach_auto_speech(data, reason="final")
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
        _attach_auto_speech(data, reason="final")
        yield {"event": "final", "data": data}

    def _record_command_result(self, data: dict[str, Any]):
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
            result = outlook_visible_text_summary(text, diagnostics=diagnostics)
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
        return data

    def plan(self, command: str) -> dict[str, Any]:
        return self.planner.preview(command).to_dict()

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
                    "POST /api/mode",
                    "POST /api/plan",
                ],
            }

    def readiness(self) -> dict[str, Any]:
        status = system_status()
        mode = self.mode()
        audit_status = self.audit.status()
        registry = tool_registry()
        self_check = run_self_checks()

        tools = registry["tools"]
        unavailable_tools = [tool["id"] for tool in tools if not tool.get("available")]
        failed_checks = [check["name"] for check in self_check["checks"] if not check.get("passed")]
        notes: list[str] = []
        if mode["paused"]:
            notes.append("Command execution is paused.")
        if unavailable_tools:
            notes.append(f"Unavailable tools: {', '.join(unavailable_tools)}.")
        if failed_checks:
            notes.append(f"Failed self-checks: {', '.join(failed_checks)}.")
        if audit_status.get("unreadable_lines"):
            notes.append("Audit log has unreadable lines.")

        return {
            "ok": bool(self_check["ok"] and not audit_status.get("unreadable_lines")),
            "generated_at": time.time(),
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
                "available": len(tools) - len(unavailable_tools),
                "unavailable_ids": unavailable_tools,
            },
            "self_check": {
                "ok": bool(self_check["ok"]),
                "total": len(self_check["checks"]),
                "passed": len(self_check["checks"]) - len(failed_checks),
                "failed": failed_checks,
            },
            "audit": audit_status,
            "verification": _latest_verification_summary(),
            "notes": notes,
        }

    def preflight(self) -> dict[str, Any]:
        readiness = self.readiness()
        status = system_status()
        registry = tool_registry()
        policy = policy_summary()
        tool_ids = {tool["id"] for tool in registry["tools"]}
        required_tools = {
            "planner.preview",
            "system.status",
            "shell.read_only",
            "terminal.read_only",
            "files.search",
            "app.availability",
            "app.list",
            "app.status",
            "app.running",
            "diagnostics.overnight",
            "diagnostics.model_context",
            "voice.stt_candidates",
            "voice.stt_score",
            "voice.wake_simulation",
            "safety.injection_scan",
            "diagnostics.codex_chats",
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
            "generated_at": time.time(),
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


def _stream_status_text(preview: dict[str, Any]) -> str:
    tool = str(preview.get("tool") or "")
    labels = {
        "outlook.visible_summary": "Yes sir, checking your email now.",
        "diagnostics.email": "Yes sir, checking the email setup now.",
        "screenshot.capability": "Yes sir, checking the screen setup now.",
        "browser.open_url": "Yes sir, opening that now.",
        "codex.job": "Yes sir, checking with Codex now.",
        "codex.delegate": "Yes sir, checking with Codex now.",
        "diagnostics.codex_chats": "Yes sir, checking the Codex chats now.",
        "codex.activity": "Yes sir, checking Codex activity now.",
        "diagnostics.codex_speed": "Yes sir, checking Codex timing now.",
        "diagnostics.remote_worker": "Yes sir, checking the MacBook Air now.",
        "diagnostics.fast_model": "Yes sir, checking the model setup now.",
        "diagnostics.memory": "Yes sir, checking Jarvis memory now.",
        "diagnostics.model_context": "Yes sir, checking the model context now.",
        "diagnostics.overnight": "Yes sir, checking the overnight workboard now.",
        "diagnostics.tts": "Yes sir, checking the voice setup now.",
        "voice.stt_candidates": "Yes sir, checking speech recognition options now.",
        "voice.stt_score": "Yes sir, scoring that transcript now.",
        "files.search": "Yes sir, searching your files now.",
        "app.list": "Yes sir, checking which apps I can open now.",
        "app.status": "Yes sir, checking that app now.",
        "app.running": "Yes sir, checking which apps are running now.",
        "shell.read_only": "Yes sir, checking that locally now.",
        "terminal.read_only": "Yes sir, checking that locally now.",
        "quick.local_control": "Yes sir, handling that now.",
        "system.status": "Yes sir, checking Jarvis status now.",
        "policy.block": "Checking safety policy.",
        "policy.confirmation": "Checking safety policy.",
        "policy.strong_confirmation": "Checking safety policy.",
    }
    return labels.get(tool, "Yes sir, checking this now.")


def _attach_auto_speech(data: dict[str, Any], *, reason: str) -> None:
    result = data.get("result")
    if not isinstance(result, dict):
        return
    if not _should_auto_speak(data):
        return
    if result.get("action") == "speech.say":
        return
    text = _speech_text_from_result(result) or str(data.get("summary") or "").strip()
    speech = speak_text_async(text, reason=reason)
    if speech.get("spoken") or speech.get("status") not in {"disabled", "empty"}:
        data["speech"] = speech


def _should_auto_speak(data: dict[str, Any]) -> bool:
    tool = str(data.get("tool") or "")
    return tool in {
        "conversation.local",
        "conversation.local_exact",
        "conversation.fast_local",
        "outlook.visible_summary",
        "quick.local_control",
    }


def _speech_text_from_result(result: dict[str, Any]) -> str:
    for key in ("reply", "email_summary"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "JarvisPrototype/0.1"

    def do_GET(self) -> None:  # noqa: N802
        if not self._host_header_allowed():
            self._send_json({"error": "Host header must be loopback"}, status=HTTPStatus.FORBIDDEN)
            return
        route = urlparse(self.path)
        if route.path == "/":
            self._send_file(STATIC_DIR / "index.html")
            return
        if route.path.startswith("/static/"):
            self._send_file(STATIC_DIR / route.path.removeprefix("/static/"))
            return
        if route.path == "/api/health":
            self._send_json({"ok": True, "status": system_status(), "mode": STATE.mode()})
            return
        if route.path == "/api/mode":
            self._send_json(STATE.mode())
            return
        if route.path == "/api/policy":
            self._send_json(policy_summary())
            return
        if route.path == "/api/tools":
            self._send_json(tool_registry())
            return
        if route.path == "/api/readiness":
            self._send_json(STATE.readiness())
            return
        if route.path == "/api/preflight":
            self._send_json(STATE.preflight())
            return
        if route.path == "/api/codex/activity":
            query = parse_qs(route.query)
            limit = _bounded_int(query.get("limit", ["3"])[0], default=3, minimum=1, maximum=10)
            self._send_json(codex_activity_snapshot(limit=limit))
            return
        if route.path == "/api/audit/status":
            self._send_json(STATE.audit.status())
            return
        if route.path == "/api/audit":
            query = parse_qs(route.query)
            limit = _bounded_int(query.get("limit", ["50"])[0], default=50, minimum=1, maximum=MAX_AUDIT_EVENTS)
            self._send_json({"events": STATE.audit.recent(limit=limit)})
            return
        if route.path == "/api/self-check":
            self._send_json(run_self_checks())
            return
        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

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
                command = str(payload.get("command", ""))
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
            self._send_json(STATE.plan(command))
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
        if route.path == "/api/command/stream":
            try:
                payload = self._read_json_payload()
                command = str(payload.get("command", ""))
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
            self._send_event_stream(STATE.stream_command(command, history=history))
            return
        if route.path != "/api/command":
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self._read_json_payload()
            command = str(payload.get("command", ""))
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
        self._send_json(STATE.command(command, history=history))

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_file(self, path: Path) -> None:
        resolved = path.resolve()
        static_root = STATIC_DIR.resolve()
        if not resolved.is_relative_to(static_root) or not resolved.exists() or not resolved.is_file():
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return
        content = resolved.read_bytes()
        content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self._send_common_headers()
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self._send_common_headers()
        self.end_headers()
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

    def _send_common_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "base-uri 'none'; "
            "form-action 'none'; "
            "frame-ancestors 'none'",
        )

    def _host_header_allowed(self) -> bool:
        return host_allowed(_host_from_header(self.headers.get("Host", "")))

    def _read_json_payload(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise UnsupportedContentType()
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length < 0:
            raise ValueError("Content-Length must be non-negative")
        if content_length > MAX_REQUEST_BYTES:
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
    if start_paused is not None:
        STATE.configure_mode(
            paused=start_paused,
            reason="Dashboard started in paused mode." if start_paused else "Dashboard started in live mode.",
        )
    httpd = ThreadingHTTPServer((host, port), RequestHandler)
    print(f"Jarvis dashboard: http://{host}:{port}")
    httpd.serve_forever()


def _bounded_int(raw: str, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


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
        if role not in {"user", "assistant", "system"} or not text:
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
