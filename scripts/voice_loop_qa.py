#!/usr/bin/env python3
"""Run a local closed-loop voice QA probe for Jarvis.

The probe synthesizes a spoken command, transcribes that audio through the
Jarvis.app Speech framework identity, sends the recognized command to Jarvis
with speech muted, then synthesizes/transcribes the visible reply so the report
can compare what was printed with what TTS would say.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.wake import detect_wake_command  # noqa: E402


DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_COMMAND = "Hey Jarvis, status."
REPORT_DIR = PROJECT_ROOT / "runtime" / "voice_loop_qa"
PIPER_BIN = PROJECT_ROOT / "runtime" / "tts_models" / "piper" / ".venv" / "bin" / "piper"
PIPER_PYTHON = PIPER_BIN.parent / "python"
PIPER_MODEL = PROJECT_ROOT / "runtime" / "tts_models" / "piper" / "en_US-ryan-high.onnx"
PIPER_CONFIG = PROJECT_ROOT / "runtime" / "tts_models" / "piper" / "en_US-ryan-high.onnx.json"
JARVIS_APP = PROJECT_ROOT / "output" / "Jarvis.app"
LOCAL_STT_ROOT = PROJECT_ROOT / "runtime" / "stt_models" / "faster_whisper"
LOCAL_STT_PYTHON = LOCAL_STT_ROOT / ".venv" / "bin" / "python"
LOCAL_STT_MODEL = "tiny.en"
INTERNAL_SPEECH_LEAK_PATTERNS: list[tuple[str, str, str]] = [
    ("hidden_tool_call", "Hidden tool call syntax", r"\\\s*tool\s*[\(\{]"),
    ("json_tool_key", "Raw JSON tool key", r"[\"']tool[\"']\s*:"),
    ("selected_tool", "Selected-tool field", r"\bselected[_\s-]?tool\b"),
    ("status_text", "Status-text field", r"\bstatus[_\s-]?text\b"),
    ("tool_requested", "Tool-requested routing state", r"\btool[_\s-]?requested\b"),
    ("final_result", "Streaming final-result event", r"\bfinal[_\s-]?result\b"),
    ("audit_event_id", "Audit event identifier", r"\baudit[_\s-]?event[_\s-]?id\b"),
    (
        "internal_tool_id",
        "Internal dotted tool id",
        r"\b(?:app|browser|codex|conversation|diagnostics|files|memory|outlook|quick|screen|shell|system|teams|terminal|tools|ui|voice|workflow)\.[a-z0-9_]+\b",
    ),
]
NORMALIZED_INTERNAL_SPEECH_PHRASES = {
    "backslash tool": "Hidden tool call syntax",
    "selected tool": "Selected-tool field",
    "status text": "Status-text field",
    "tool requested": "Tool-requested routing state",
    "final result": "Streaming final-result event",
    "audit event id": "Audit event identifier",
    "quick local control": "Internal quick local tool id",
    "conversation fast local": "Internal fast-chat tool id",
    "outlook visible summary": "Internal email tool id",
}

PIPER_SYNTHESIZE_CODE = r"""
import sys
import wave
from pathlib import Path

from piper import PiperVoice, SynthesisConfig
from piper.phonemize_espeak import ESPEAK_DATA_DIR

model_path = Path(sys.argv[1])
config_path = Path(sys.argv[2])
wav_path = Path(sys.argv[3])
espeak_data_dir = Path(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4] else ESPEAK_DATA_DIR
length_scale = float(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5] else 0.85
text = sys.stdin.read().strip()
if not text:
    raise SystemExit(2)

voice = PiperVoice.load(model_path, config_path=config_path, espeak_data_dir=espeak_data_dir)
syn_config = SynthesisConfig(length_scale=length_scale)
params_set = False
with wave.open(str(wav_path), "wb") as wav_file:
    for audio_chunk in voice.synthesize(text, syn_config):
        if not params_set:
            wav_file.setframerate(audio_chunk.sample_rate)
            wav_file.setsampwidth(audio_chunk.sample_width)
            wav_file.setnchannels(audio_chunk.sample_channels)
            params_set = True
        wav_file.writeframes(audio_chunk.audio_int16_bytes)
"""

LOCAL_STT_TRANSCRIBE_CODE = r"""
import json
import sys
import time
from pathlib import Path

audio_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
model_name = sys.argv[3]
download_root = Path(sys.argv[4])
started = time.monotonic()

try:
    from faster_whisper import WhisperModel

    model = WhisperModel(
        model_name,
        device="cpu",
        compute_type="int8",
        download_root=str(download_root),
    )
    segments, info = model.transcribe(
        str(audio_path),
        beam_size=1,
        language="en",
        vad_filter=False,
    )
    transcript = " ".join(segment.text.strip() for segment in segments).strip()
    payload = {
        "status": "completed",
        "provider": "faster_whisper",
        "model": model_name,
        "audio_path": str(audio_path),
        "transcript": transcript,
        "language": getattr(info, "language", None),
        "language_probability": round(float(getattr(info, "language_probability", 0.0)), 6),
        "duration_seconds": round(time.monotonic() - started, 3),
    }
except Exception as error:
    payload = {
        "status": "failed",
        "provider": "faster_whisper",
        "model": model_name,
        "audio_path": str(audio_path),
        "transcript": "",
        "error": f"{type(error).__name__}: {error}",
        "duration_seconds": round(time.monotonic() - started, 3),
    }

output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
raise SystemExit(0 if payload["status"] == "completed" else 1)
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command", default=DEFAULT_COMMAND, help="Command text to synthesize as the user.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output-dir", default=str(REPORT_DIR))
    parser.add_argument("--length-scale", type=float, default=0.85)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--stt-provider",
        choices=("auto", "apple", "local"),
        default="auto",
        help="auto tries Apple Speech first, apple uses only the app-bundle Speech path, local uses faster-whisper only.",
    )
    parser.add_argument(
        "--no-permission-prompts",
        action="store_true",
        help="Do not open the Apple Speech transcription path; use local STT only and fail closed if it is unavailable.",
    )
    parser.add_argument(
        "--speech-audit-only",
        action="store_true",
        help="Skip wake-command synthesis and audit only the exact speech payloads Jarvis would produce for --command.",
    )
    parser.add_argument(
        "--expect-tool",
        action="append",
        default=[],
        help="Require the final Jarvis response to use this tool id. May be passed more than once.",
    )
    parser.add_argument(
        "--expect-visible-contains",
        action="append",
        default=[],
        help="Require the visible final reply to contain this text, case-insensitively. May be passed more than once.",
    )
    parser.add_argument(
        "--expect-routed-contains",
        action="append",
        default=[],
        help="Require the STT-routed command to contain this text, case-insensitively. May be passed more than once.",
    )
    args = parser.parse_args()

    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.output_dir).resolve() / stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    if args.speech_audit_only:
        report = run_speech_audit(
            command_text=args.command,
            base_url=args.base_url.rstrip("/"),
            run_dir=run_dir,
            length_scale=args.length_scale,
            timeout=args.timeout,
            stt_provider=args.stt_provider,
            no_permission_prompts=args.no_permission_prompts,
            expect_tools=args.expect_tool,
            expect_visible_contains=args.expect_visible_contains,
            expect_routed_contains=args.expect_routed_contains,
        )
    else:
        report = run_voice_loop(
            command_text=args.command,
            base_url=args.base_url.rstrip("/"),
            run_dir=run_dir,
            length_scale=args.length_scale,
            timeout=args.timeout,
            stt_provider=args.stt_provider,
            no_permission_prompts=args.no_permission_prompts,
            expect_tools=args.expect_tool,
            expect_visible_contains=args.expect_visible_contains,
            expect_routed_contains=args.expect_routed_contains,
        )

    report_path = run_dir / "report.json"
    latest_path = Path(args.output_dir).resolve() / "latest.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    latest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    result = report.get("result", {})
    print(f"Report: {report_path}")
    if args.speech_audit_only:
        audit = result.get("speech_audit") if isinstance(result.get("speech_audit"), dict) else {}
        transcripts = [
            str(item.get("transcript") or "").strip()
            for item in audit.get("items", [])
            if isinstance(item, dict) and str(item.get("transcript") or "").strip()
        ]
        print(f"Speech audit status: {audit.get('status')}")
        print(f"Payloads: {audit.get('payload_count')} | Leaks: {audit.get('leak_count')}")
        print(f"Visible reply: {result.get('visible_reply_preview')!r}")
        if transcripts:
            print(f"Speech transcript: {transcripts[-1]!r}")
    else:
        print(f"Command transcript: {result.get('command_transcript')!r}")
        print(f"Routed command: {result.get('routed_command')!r}")
        print(f"Visible reply: {result.get('visible_reply_preview')!r}")
        print(f"Reply transcript: {result.get('reply_transcript')!r}")
        print(f"Similarity: {result.get('reply_similarity')}")
    return 0 if result.get("status") == "passed" else 1


def run_voice_loop(
    *,
    command_text: str,
    base_url: str,
    run_dir: Path,
    length_scale: float,
    timeout: float,
    stt_provider: str,
    no_permission_prompts: bool = False,
    expect_tools: list[str] | None = None,
    expect_visible_contains: list[str] | None = None,
    expect_routed_contains: list[str] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    command_audio = run_dir / "01-command.wav"
    command_stt = run_dir / "02-command-stt.json"
    command_local_stt = run_dir / "02-command-local-stt.json"
    reply_audio = run_dir / "03-reply.wav"
    reply_stt = run_dir / "04-reply-stt.json"
    reply_local_stt = run_dir / "04-reply-local-stt.json"

    report: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "base_url": base_url,
        "run_dir": str(run_dir),
        "input": {
            "command_text": command_text,
            "length_scale": length_scale,
            "stt_provider": stt_provider,
            "no_permission_prompts": no_permission_prompts,
            "expect_tools": expect_tools or [],
            "expect_visible_contains": expect_visible_contains or [],
            "expect_routed_contains": expect_routed_contains or [],
        },
        "artifacts": {
            "command_audio": str(command_audio),
            "command_stt": str(command_stt),
            "command_local_stt": str(command_local_stt),
            "reply_audio": str(reply_audio),
            "reply_stt": str(reply_stt),
            "reply_local_stt": str(reply_local_stt),
        },
    }

    try:
        command_tts = synthesize(command_text, command_audio, length_scale=length_scale)
        command_transcription = transcribe_audio(
            command_audio,
            apple_output_json=command_stt,
            local_output_json=command_local_stt,
            timeout=timeout,
            provider=stt_provider,
            no_permission_prompts=no_permission_prompts,
        )
        command_transcript = str(command_transcription.get("transcript") or "").strip()
        route = route_transcript(command_transcript)
        if not route["command"]:
            report["result"] = {
                "status": "failed",
                "warnings": [
                    f"Command STT status was {command_transcription.get('status')}.",
                    "No command was extracted from the spoken command transcript.",
                ],
                "total_seconds": round(time.monotonic() - started, 3),
                "command_tts": command_tts,
                "command_stt": command_transcription,
                "command_transcript": command_transcript,
                "wake_route": route,
                "routed_command": "",
            }
            return report

        stream_events = stream_command_events(
            base_url,
            route["command"],
            timeout=timeout,
            suppress_speech=True,
        )
        command_response = final_response_from_stream_events(stream_events)
        if not command_response:
            raise RuntimeError("Jarvis stream did not return a final response.")

        visible_reply = extract_visible_reply(command_response)
        expectation = evaluate_expectations(
            command_response=command_response,
            visible_reply=visible_reply,
            routed_command=route["command"],
            expect_tools=expect_tools or [],
            expect_visible_contains=expect_visible_contains or [],
            expect_routed_contains=expect_routed_contains or [],
        )
        speech_audit = audit_spoken_payloads(
            speech_payloads_from_stream_events(stream_events),
            run_dir=run_dir,
            length_scale=length_scale,
            timeout=timeout,
            stt_provider=stt_provider,
            no_permission_prompts=no_permission_prompts,
        )
        reply_tts = synthesize(visible_reply or "No visible reply.", reply_audio, length_scale=length_scale)
        reply_transcription = transcribe_audio(
            reply_audio,
            apple_output_json=reply_stt,
            local_output_json=reply_local_stt,
            timeout=timeout,
            provider=stt_provider,
            no_permission_prompts=no_permission_prompts,
        )
        reply_transcript = str(reply_transcription.get("transcript") or "").strip()
        similarity = text_similarity(visible_reply, reply_transcript)

        status = "passed"
        warnings: list[str] = []
        if str(command_transcription.get("status")) != "completed":
            status = "warning"
            warnings.append(f"Command STT status was {command_transcription.get('status')}.")
        if str(reply_transcription.get("status")) != "completed":
            status = "warning"
            warnings.append(f"Reply STT status was {reply_transcription.get('status')}.")
        if similarity < 0.68:
            status = "warning"
            warnings.append("Reply transcript differed meaningfully from visible reply.")
        if speech_audit.get("status") == "failed":
            status = "failed"
            warnings.append("Speech audit found internal text in spoken output.")
        elif speech_audit.get("status") == "warning" and status == "passed":
            status = "warning"
            warnings.extend(str(warning) for warning in speech_audit.get("warnings", []))
        if not expectation["passed"]:
            status = "failed"
            warnings.extend(expectation["failures"])

        report["result"] = {
            "status": status,
            "warnings": warnings,
            "total_seconds": round(time.monotonic() - started, 3),
            "command_tts": command_tts,
            "command_stt": command_transcription,
            "command_transcript": command_transcript,
            "wake_route": route,
            "routed_command": route["command"],
            "command_response_tool": command_response.get("tool"),
            "visible_reply_preview": visible_reply[:500],
            "expectation": expectation,
            "stream_event_count": len(stream_events),
            "speech_audit": speech_audit,
            "reply_tts": reply_tts,
            "reply_stt": reply_transcription,
            "reply_transcript": reply_transcript,
            "reply_similarity": similarity,
        }
        return report
    except Exception as error:
        report["result"] = {
            "status": "failed",
            "error": f"{type(error).__name__}: {error}",
            "total_seconds": round(time.monotonic() - started, 3),
        }
        return report


def run_speech_audit(
    *,
    command_text: str,
    base_url: str,
    run_dir: Path,
    length_scale: float,
    timeout: float,
    stt_provider: str,
    no_permission_prompts: bool = False,
    expect_tools: list[str] | None = None,
    expect_visible_contains: list[str] | None = None,
    expect_routed_contains: list[str] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    report: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "base_url": base_url,
        "run_dir": str(run_dir),
        "input": {
            "command_text": command_text,
            "length_scale": length_scale,
            "stt_provider": stt_provider,
            "no_permission_prompts": no_permission_prompts,
            "speech_audit_only": True,
            "expect_tools": expect_tools or [],
            "expect_visible_contains": expect_visible_contains or [],
            "expect_routed_contains": expect_routed_contains or [],
        },
    }
    try:
        stream_events = stream_command_events(
            base_url,
            command_text,
            timeout=timeout,
            suppress_speech=True,
        )
        command_response = final_response_from_stream_events(stream_events)
        visible_reply = extract_visible_reply(command_response) if command_response else ""
        expectation = evaluate_expectations(
            command_response=command_response or {},
            visible_reply=visible_reply,
            routed_command=command_text,
            expect_tools=expect_tools or [],
            expect_visible_contains=expect_visible_contains or [],
            expect_routed_contains=expect_routed_contains or [],
        )
        speech_audit = audit_spoken_payloads(
            speech_payloads_from_stream_events(stream_events),
            run_dir=run_dir,
            length_scale=length_scale,
            timeout=timeout,
            stt_provider=stt_provider,
            no_permission_prompts=no_permission_prompts,
        )
        status = str(speech_audit.get("status", "failed"))
        warnings = list(speech_audit.get("warnings", []))
        if not expectation["passed"]:
            status = "failed"
            warnings.extend(expectation["failures"])
        report["result"] = {
            "status": status,
            "warnings": warnings,
            "total_seconds": round(time.monotonic() - started, 3),
            "command_response_tool": command_response.get("tool") if command_response else "",
            "visible_reply_preview": visible_reply[:500],
            "expectation": expectation,
            "stream_event_count": len(stream_events),
            "speech_audit": speech_audit,
        }
        return report
    except Exception as error:
        report["result"] = {
            "status": "failed",
            "error": f"{type(error).__name__}: {error}",
            "total_seconds": round(time.monotonic() - started, 3),
        }
        return report


def audit_spoken_payloads(
    payloads: list[dict[str, Any]],
    *,
    run_dir: Path,
    length_scale: float,
    timeout: float,
    stt_provider: str,
    no_permission_prompts: bool = False,
) -> dict[str, Any]:
    audit_dir = run_dir / "speech-audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    all_leaks: list[dict[str, Any]] = []
    for index, payload in enumerate(payloads, start=1):
        source = re.sub(r"[^a-z0-9]+", "-", str(payload.get("source") or "speech").lower()).strip("-") or "speech"
        text = str(payload.get("text") or "").strip()
        audio_path = audit_dir / f"{index:02d}-{source}.wav"
        stt_path = audit_dir / f"{index:02d}-{source}-stt.json"
        local_stt_path = audit_dir / f"{index:02d}-{source}-local-stt.json"
        intended_leaks = detect_internal_speech_leaks(text, source=f"{source}.intended")
        item: dict[str, Any] = {
            "index": index,
            "source": source,
            "reason": payload.get("reason"),
            "tool": payload.get("tool"),
            "text_preview": text[:500],
            "intended_leaks": intended_leaks,
            "audio_path": str(audio_path),
            "stt_path": str(stt_path),
            "local_stt_path": str(local_stt_path),
        }
        all_leaks.extend(intended_leaks)
        try:
            item["tts"] = synthesize(text, audio_path, length_scale=length_scale)
            transcription = transcribe_audio(
                audio_path,
                apple_output_json=stt_path,
                local_output_json=local_stt_path,
                timeout=timeout,
                provider=stt_provider,
                no_permission_prompts=no_permission_prompts,
            )
            transcript = str(transcription.get("transcript") or "").strip()
            transcript_leaks = detect_internal_speech_leaks(transcript, source=f"{source}.transcript")
            all_leaks.extend(transcript_leaks)
            item["stt"] = transcription
            item["transcript"] = transcript
            item["transcript_leaks"] = transcript_leaks
            item["similarity"] = text_similarity(text, transcript)
            if transcription.get("status") != "completed":
                warnings.append(f"{source} STT status was {transcription.get('status')}.")
        except Exception as error:
            item["stt"] = {
                "status": "failed",
                "error": f"{type(error).__name__}: {error}",
            }
            warnings.append(f"{source} audit failed: {type(error).__name__}: {error}")
        items.append(item)

    if not payloads:
        warnings.append("No spoken payloads were captured from the Jarvis stream.")
    status = "passed"
    if all_leaks:
        status = "failed"
    elif warnings:
        status = "warning"
    return {
        "status": status,
        "payload_count": len(payloads),
        "warnings": warnings,
        "leak_count": len(all_leaks),
        "leaks": all_leaks,
        "items": items,
    }


def evaluate_expectations(
    *,
    command_response: dict[str, Any],
    visible_reply: str,
    routed_command: str,
    expect_tools: list[str],
    expect_visible_contains: list[str],
    expect_routed_contains: list[str],
) -> dict[str, Any]:
    actual_tool = str(command_response.get("tool") or "")
    visible_norm = normalize_text(visible_reply)
    routed_norm = normalize_text(routed_command)
    failures: list[str] = []
    clean_tools = [tool.strip() for tool in expect_tools if tool.strip()]
    if clean_tools and actual_tool not in clean_tools:
        failures.append(f"Expected tool {clean_tools}, got {actual_tool or '(none)'}.")
    for needle in expect_visible_contains:
        needle_norm = normalize_text(needle)
        if needle_norm and needle_norm not in visible_norm:
            failures.append(f"Visible reply did not contain {needle!r}.")
    for needle in expect_routed_contains:
        needle_norm = normalize_text(needle)
        if needle_norm and needle_norm not in routed_norm:
            failures.append(f"Routed command did not contain {needle!r}.")
    return {
        "passed": not failures,
        "expected_tools": clean_tools,
        "actual_tool": actual_tool,
        "expect_visible_contains": [text for text in expect_visible_contains if text],
        "expect_routed_contains": [text for text in expect_routed_contains if text],
        "failures": failures,
    }


def detect_internal_speech_leaks(text: str, *, source: str = "speech") -> list[dict[str, Any]]:
    leaks: list[dict[str, Any]] = []
    raw_text = str(text or "")
    for leak_id, label, pattern in INTERNAL_SPEECH_LEAK_PATTERNS:
        match = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if match:
            leaks.append(
                {
                    "id": leak_id,
                    "label": label,
                    "source": source,
                    "excerpt": match.group(0)[:160],
                }
            )
    normalized = normalize_text(raw_text)
    for phrase, label in NORMALIZED_INTERNAL_SPEECH_PHRASES.items():
        if phrase in normalized:
            leaks.append(
                {
                    "id": phrase.replace(" ", "_"),
                    "label": label,
                    "source": source,
                    "excerpt": phrase,
                }
            )
    return leaks


def speech_payloads_from_stream_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        event_name = str(event.get("event") or "")
        speech = data.get("speech") if isinstance(data.get("speech"), dict) else {}
        if event_name == "status":
            text = str(speech.get("text_preview") or data.get("text") or "").strip()
            if text and speech.get("status") != "suppressed_for_stop_speaking":
                payloads.append(
                    {
                        "source": "status",
                        "event_index": index,
                        "reason": speech.get("reason") or "status",
                        "tool": data.get("tool"),
                        "text": text,
                    }
                )
        elif event_name == "final":
            text = str(speech.get("text_preview") or "").strip()
            if text:
                payloads.append(
                    {
                        "source": "final",
                        "event_index": index,
                        "reason": speech.get("reason") or "final",
                        "tool": data.get("tool"),
                        "text": text,
                    }
                )
    return payloads


def final_response_from_stream_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in reversed(events):
        if event.get("event") == "final" and isinstance(event.get("data"), dict):
            return event["data"]
    return {}


def synthesize(text: str, output_wav: Path, *, length_scale: float) -> dict[str, Any]:
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = synthesize_with_say(text, output_wav)
        result["matches_live_provider"] = True
        return result
    except Exception as say_error:
        if not (PIPER_PYTHON.exists() and PIPER_MODEL.exists() and PIPER_CONFIG.exists()):
            raise
        fallback = synthesize_with_piper(text, output_wav, length_scale=length_scale)
        fallback["fallback_from"] = "macos-say"
        fallback["fallback_reason"] = f"{type(say_error).__name__}: {say_error}"[-500:]
        fallback["matches_live_provider"] = False
        return fallback


def synthesize_with_piper(text: str, output_wav: Path, *, length_scale: float) -> dict[str, Any]:
    if PIPER_PYTHON.exists() and PIPER_MODEL.exists() and PIPER_CONFIG.exists():
        started = time.monotonic()
        env = os.environ.copy()
        env["PYTHONNOUSERSITE"] = "1"
        completed = subprocess.run(
            [
                str(PIPER_PYTHON),
                "-c",
                PIPER_SYNTHESIZE_CODE,
                str(PIPER_MODEL),
                str(PIPER_CONFIG),
                str(output_wav),
                str(piper_espeak_data_dir() or ""),
                str(length_scale),
            ],
            input=text,
            text=True,
            capture_output=True,
            cwd=PROJECT_ROOT,
            env=env,
            timeout=60,
            check=False,
        )
        if completed.returncode == 0:
            return {
                "provider": "piper",
                "voice": "en_US-ryan-high",
                "espeak_data": str(piper_espeak_data_dir() or ""),
                "output": str(output_wav),
                "duration_seconds": round(time.monotonic() - started, 3),
            }
        piper_error = completed.stderr.strip() or completed.stdout.strip() or "Piper failed."
        fallback = synthesize_with_say(text, output_wav)
        fallback["fallback_from"] = "piper"
        fallback["fallback_reason"] = piper_error[-500:]
        fallback["matches_live_provider"] = True
        return fallback

    raise RuntimeError("Piper is unavailable.")


def piper_espeak_data_dir() -> Path | None:
    lib_dir = PIPER_BIN.parents[1] / "lib"
    preferred = Path.home() / ".jarvis" / "tts" / "piper" / "espeak-ng-data"
    candidates = [preferred]
    candidates.extend(lib_dir.glob("python*/site-packages/piper/espeak-ng-data"))
    candidates.extend(lib_dir.glob("python*/site-packages/espeakng_loader/espeak-ng-data"))
    for candidate in candidates:
        if (candidate / "phontab").exists():
            return candidate
    return None


def synthesize_with_say(text: str, output_wav: Path) -> dict[str, Any]:
    started = time.monotonic()
    aiff_path = output_wav.with_suffix(".aiff")
    completed = subprocess.run(
        ["/usr/bin/say", "-o", str(aiff_path), text],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"say failed: {completed.stderr.strip() or completed.stdout.strip()}")
    ffmpeg = Path("/opt/homebrew/bin/ffmpeg")
    if not ffmpeg.exists():
        raise RuntimeError("Piper and ffmpeg are unavailable, so the harness cannot create WAV audio.")
    converted = subprocess.run(
        [str(ffmpeg), "-y", "-loglevel", "error", "-i", str(aiff_path), str(output_wav)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if converted.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {converted.stderr.strip() or converted.stdout.strip()}")
    return {
        "provider": "macos-say",
        "voice": "system default",
        "output": str(output_wav),
        "duration_seconds": round(time.monotonic() - started, 3),
    }


def transcribe_with_jarvis_app(audio_path: Path, output_json: Path, *, timeout: float) -> dict[str, Any]:
    if not JARVIS_APP.exists():
        raise RuntimeError(f"Jarvis app bundle not found at {JARVIS_APP}")
    completed = subprocess.run(
        [
            "/usr/bin/open",
            "-n",
            "-W",
            str(JARVIS_APP),
            "--args",
            "--stt-file-self-test",
            str(audio_path),
            str(output_json),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=max(10.0, timeout + 10.0),
        check=False,
    )
    if not output_json.exists():
        raise RuntimeError(
            "Jarvis app did not write STT JSON. "
            f"open exit={completed.returncode}, stdout={completed.stdout[-500:]!r}, stderr={completed.stderr[-500:]!r}"
        )
    data = json.loads(output_json.read_text(encoding="utf-8"))
    data["open_returncode"] = completed.returncode
    if completed.stdout.strip():
        data["stdout_tail"] = completed.stdout.strip()[-500:]
    if completed.stderr.strip():
        data["stderr_tail"] = completed.stderr.strip()[-500:]
    return data


def transcribe_audio(
    audio_path: Path,
    *,
    apple_output_json: Path,
    local_output_json: Path,
    timeout: float,
    provider: str,
    no_permission_prompts: bool = False,
) -> dict[str, Any]:
    if provider == "local":
        return transcribe_with_local_stt(audio_path, local_output_json, timeout=timeout)

    if no_permission_prompts:
        apple = {
            "status": "apple_speech_skipped_no_permission_prompts",
            "provider": "apple_speech",
            "audio_path": str(audio_path),
            "transcript": "",
            "error": "Skipped Apple Speech so the overnight harness cannot trigger a macOS permission prompt.",
        }
        apple_output_json.write_text(json.dumps(apple, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        try:
            apple = transcribe_with_jarvis_app(audio_path, apple_output_json, timeout=timeout)
        except Exception as error:
            apple = {
                "status": "apple_speech_failed",
                "provider": "apple_speech",
                "audio_path": str(audio_path),
                "transcript": "",
                "error": f"{type(error).__name__}: {error}",
            }
            apple_output_json.write_text(json.dumps(apple, indent=2, ensure_ascii=False), encoding="utf-8")
    apple["provider"] = "apple_speech"
    if apple.get("status") == "completed" and str(apple.get("transcript") or "").strip():
        return apple
    if provider == "apple":
        return apple

    local = transcribe_with_local_stt(audio_path, local_output_json, timeout=timeout)
    if local.get("status") == "completed" and str(local.get("transcript") or "").strip():
        local["apple_speech"] = apple
        return local
    apple["local_stt"] = local
    return apple


def transcribe_with_local_stt(audio_path: Path, output_json: Path, *, timeout: float) -> dict[str, Any]:
    cache_status = local_stt_cache_status()
    if not LOCAL_STT_PYTHON.exists():
        data = {
            "status": "local_stt_unavailable",
            "provider": "faster_whisper",
            "model": LOCAL_STT_MODEL,
            "audio_path": str(audio_path),
            "transcript": "",
            "missing": str(LOCAL_STT_PYTHON),
            "cache_status": cache_status,
        }
        output_json.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return data

    output_json.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    env.setdefault("HF_HUB_DISABLE_XET", "1")
    ca_bundle = first_existing_path(
        [
            *sorted((LOCAL_STT_ROOT / ".venv" / "lib").glob("python*/site-packages/certifi/cacert.pem")),
            Path("/etc/ssl/cert.pem"),
            Path("/opt/homebrew/Cellar/ca-certificates/2025-05-20/share/ca-certificates/cacert.pem"),
        ]
    )
    if ca_bundle.exists():
        env.setdefault("SSL_CERT_FILE", str(ca_bundle))
        env.setdefault("REQUESTS_CA_BUNDLE", str(ca_bundle))
    try:
        completed = subprocess.run(
            [
                str(LOCAL_STT_PYTHON),
                "-c",
                LOCAL_STT_TRANSCRIBE_CODE,
                str(audio_path),
                str(output_json),
                LOCAL_STT_MODEL,
                str(LOCAL_STT_ROOT / "models"),
            ],
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=max(120.0, timeout + 90.0),
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        data = {
            "status": "local_stt_timeout",
            "provider": "faster_whisper",
            "model": LOCAL_STT_MODEL,
            "audio_path": str(audio_path),
            "transcript": "",
            "error": f"Timed out after {error.timeout}s.",
            "cache_status": local_stt_cache_status(),
        }
        output_json.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return data
    if output_json.exists():
        data = json.loads(output_json.read_text(encoding="utf-8"))
    else:
        data = {
            "status": "failed",
            "provider": "faster_whisper",
            "model": LOCAL_STT_MODEL,
            "audio_path": str(audio_path),
            "transcript": "",
            "error": "Local STT did not write JSON.",
        }
    data["cache_status"] = local_stt_cache_status()
    data["returncode"] = completed.returncode
    if completed.stdout.strip():
        data["stdout_tail"] = completed.stdout.strip()[-500:]
    if completed.stderr.strip():
        data["stderr_tail"] = completed.stderr.strip()[-500:]
    output_json.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def local_stt_cache_status() -> dict[str, Any]:
    snapshot_dir = LOCAL_STT_ROOT / "models" / "models--Systran--faster-whisper-tiny.en" / "snapshots"
    snapshots = sorted(snapshot_dir.glob("*"))
    active_snapshot = snapshots[-1] if snapshots else snapshot_dir
    model_path = active_snapshot / "model.bin"
    blob_dir = LOCAL_STT_ROOT / "models" / "models--Systran--faster-whisper-tiny.en" / "blobs"
    incomplete = sorted(blob_dir.glob("*.incomplete"))
    return {
        "snapshot": str(active_snapshot),
        "model_bin": str(model_path),
        "model_bin_exists": model_path.exists(),
        "model_bin_size": model_path.stat().st_size if model_path.exists() else 0,
        "incomplete_blobs": [
            {"path": str(path), "size": path.stat().st_size}
            for path in incomplete
        ],
    }


def first_existing_path(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[-1] if paths else Path("")


def route_transcript(transcript: str) -> dict[str, Any]:
    detection = detect_wake_command(transcript)
    command = detection.command.strip() if detection.woke else transcript.strip()
    return {
        "woke": detection.woke,
        "wake_phrase": detection.phrase,
        "needs_followup": detection.needs_followup,
        "normalized": detection.normalized,
        "command": command,
    }


def speech_mute_status(base_url: str) -> bool:
    try:
        data = get_json(f"{base_url}/api/speech/mute", timeout=5)
        return bool(data.get("muted", False))
    except Exception:
        return False


def set_speech_mute(base_url: str, muted: bool) -> None:
    post_json(f"{base_url}/api/speech/mute", {"muted": muted}, timeout=5)


def extract_visible_reply(response: dict[str, Any]) -> str:
    candidates: list[Any] = []
    result = response.get("result")
    if isinstance(result, dict):
        for key in (
            "reply",
            "summary",
            "answer",
            "spoken_text",
            "visible_reply",
            "message",
            "status",
        ):
            candidates.append(result.get(key))
    for key in ("reply", "message", "summary", "answer"):
        candidates.append(response.get(key))
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return json.dumps(response, ensure_ascii=False, sort_keys=True)[:500]


def text_similarity(left: str, right: str) -> float:
    normalized_left = normalize_text(left)
    normalized_right = normalize_text(right)
    if not normalized_left and not normalized_right:
        return 1.0
    if not normalized_left or not normalized_right:
        return 0.0
    return round(difflib.SequenceMatcher(None, normalized_left, normalized_right).ratio(), 3)


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def get_json(url: str, *, timeout: float) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def stream_command_events(
    base_url: str,
    command: str,
    *,
    timeout: float,
    suppress_speech: bool = True,
) -> list[dict[str, Any]]:
    payload = {"command": command, "suppress_speech": True}
    if not suppress_speech:
        payload["suppress_speech"] = False
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/command/stream",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    events: list[dict[str, Any]] = []
    event_name = "message"
    data_lines: list[str] = []

    def flush_event() -> None:
        nonlocal event_name, data_lines
        if not data_lines:
            event_name = "message"
            return
        raw_data = "\n".join(data_lines)
        try:
            data: Any = json.loads(raw_data)
        except json.JSONDecodeError:
            data = raw_data
        events.append({"event": event_name, "data": data})
        event_name = "message"
        data_lines = []

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line:
                    flush_event()
                    continue
                if line.startswith("event:"):
                    event_name = line[6:].strip() or "message"
                elif line.startswith("data:"):
                    data_lines.append(line[5:].strip())
            flush_event()
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {body[:500]}") from error
    return events


def post_json(url: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {body[:500]}") from error


if __name__ == "__main__":
    raise SystemExit(main())
