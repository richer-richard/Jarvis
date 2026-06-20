#!/usr/bin/env python3
"""Run a local closed-loop voice QA probe for Jarvis.

The unattended default uses local STT and per-request speech/action suppression,
so it does not ask macOS for Apple Speech permission or make Jarvis speak while
testing. Apple Speech is available only with explicit opt-in flags.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
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
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.wake import detect_wake_command  # noqa: E402
from scripts.render_overnight_status import normalize_base_url  # noqa: E402
from scripts.report_refresh import refresh_report_surfaces_quietly  # noqa: E402


DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_COMMAND = "Hey Jarvis, status."
REPORT_DIR = PROJECT_ROOT / "runtime" / "voice_loop_qa"
PIPER_BIN = PROJECT_ROOT / "runtime" / "tts_models" / "piper" / ".venv" / "bin" / "piper"
PIPER_PYTHON = PIPER_BIN.parent / "python"
PIPER_MODEL = PROJECT_ROOT / "runtime" / "tts_models" / "piper" / "en_US-ryan-high.onnx"
PIPER_CONFIG = PROJECT_ROOT / "runtime" / "tts_models" / "piper" / "en_US-ryan-high.onnx.json"
JARVIS_APP = PROJECT_ROOT / "output" / "Jarvis.app"
VISIBLE_SCREEN_PROBE = JARVIS_APP / "Contents" / "MacOS" / "jarvis-visible-screen-probe"
VISIBLE_SCREEN_FOLLOW_UP_RETRY_ATTEMPTS = 4
VISIBLE_SCREEN_FOLLOW_UP_RETRY_DELAY_SECONDS = 1.6
VISIBLE_SCREEN_FOLLOW_UP_INITIAL_OPEN_DELAY_SECONDS = 1.2
SPEECH_AUDIT_MAX_WORKERS = 2
LOCAL_STT_ROOT = PROJECT_ROOT / "runtime" / "stt_models" / "faster_whisper"
LOCAL_STT_PYTHON = LOCAL_STT_ROOT / ".venv" / "bin" / "python"
LOCAL_STT_MODEL = "tiny.en"
INTERNAL_SPEECH_LEAK_PATTERNS: list[tuple[str, str, str]] = [
    ("hidden_tool_call", "Hidden tool call syntax", r"\\\s*[A-Za-z][A-Za-z0-9_.-]*\s*[\(\{]"),
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

NUMBER_WORD_VALUES: dict[str, int] = {
    "zero": 0,
    "oh": 0,
    "o": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}

TENS_WORD_VALUES: dict[str, int] = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
NORMALIZED_INTERNAL_SPEECH_PHRASES = {
    "backslash tool": "Hidden tool call syntax",
    "selected tool": "Selected-tool field",
    "status text": "Status-text field",
    "tool requested": "Tool-requested routing state",
    "final result": "Streaming final-result event",
    "audit event id": "Audit event identifier",
    "audit verification": "Internal audit/verification status",
    "verification passed": "Internal verification status",
    "worker already online": "Internal worker status",
    "app perms": "Internal app-permission status",
    "codex activity": "Internal Codex activity status",
    "cli tail": "Internal CLI tail status",
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
        default="local",
        help="local is the unattended default; auto tries Apple Speech first, and apple uses only the app-bundle Speech path.",
    )
    parser.add_argument(
        "--allow-apple-speech",
        action="store_true",
        help="Allow the harness to use the Jarvis.app Apple Speech path if it is already authorized.",
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
        "--exercise-live-speech",
        action="store_true",
        help="Let Jarvis actually speak during the probe, then verify that the live playback path was exercised. This still does not capture room audio.",
    )
    parser.add_argument(
        "--require-physical-capture",
        action="store_true",
        help="Fail closed because this harness does not yet capture physical speaker or microphone loopback audio.",
    )
    parser.add_argument(
        "--allow-audio-actions",
        action="store_true",
        help="Allow live audio/app actions such as Music playback. The default suppresses them for quiet unattended probes.",
    )
    parser.add_argument(
        "--exercise-visible-navigation",
        action="store_true",
        help="Allow an explicit visible-screen navigation attempt. Also requires JARVIS_ALLOW_LIVE_UI_NAVIGATION=1 before any click is sent.",
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
        "--expect-visible-not-contains",
        action="append",
        default=[],
        help="Require the visible final reply to avoid this text, case-insensitively. May be passed more than once.",
    )
    parser.add_argument(
        "--expect-routed-contains",
        action="append",
        default=[],
        help="Require the STT-routed command to contain this text, case-insensitively. May be passed more than once.",
    )
    parser.add_argument(
        "--no-refresh-report",
        action="store_true",
        help="Do not refresh the master report/workboard after writing voice-loop artifacts.",
    )
    args = parser.parse_args()
    if args.no_permission_prompts and args.stt_provider != "local":
        parser.error("--no-permission-prompts can only be combined with --stt-provider local")
    if args.stt_provider in {"auto", "apple"} and not args.allow_apple_speech:
        parser.error("--stt-provider auto/apple requires --allow-apple-speech")
    if args.require_physical_capture:
        parser.error("--require-physical-capture is not supported yet; this harness verifies generated audio/STT, not physical speaker or microphone capture")
    try:
        base_url = normalize_base_url(args.base_url)
    except ValueError as error:
        print(f"Refused unsafe base URL: {error}", file=sys.stderr)
        return 2
    no_permission_prompts = args.no_permission_prompts or args.stt_provider == "local"

    run_dir = allocate_run_dir(Path(args.output_dir).resolve())

    if args.speech_audit_only:
        report = run_speech_audit(
            command_text=args.command,
            base_url=base_url,
            run_dir=run_dir,
            length_scale=args.length_scale,
            timeout=args.timeout,
            stt_provider=args.stt_provider,
            no_permission_prompts=no_permission_prompts,
            expect_tools=args.expect_tool,
            expect_visible_contains=args.expect_visible_contains,
            expect_visible_not_contains=args.expect_visible_not_contains,
            expect_routed_contains=args.expect_routed_contains,
            exercise_live_speech=args.exercise_live_speech,
            allow_audio_actions=args.allow_audio_actions,
            exercise_visible_navigation=args.exercise_visible_navigation,
        )
    else:
        report = run_voice_loop(
            command_text=args.command,
            base_url=base_url,
            run_dir=run_dir,
            length_scale=args.length_scale,
            timeout=args.timeout,
            stt_provider=args.stt_provider,
            no_permission_prompts=no_permission_prompts,
            expect_tools=args.expect_tool,
            expect_visible_contains=args.expect_visible_contains,
            expect_routed_contains=args.expect_routed_contains,
            exercise_live_speech=args.exercise_live_speech,
            allow_audio_actions=args.allow_audio_actions,
            exercise_visible_navigation=args.exercise_visible_navigation,
        )

    report_path = run_dir / "report.json"
    latest_path = Path(args.output_dir).resolve() / "latest.json"
    latest_md_path = Path(args.output_dir).resolve() / "latest.md"
    global_latest_path = REPORT_DIR / "latest.json"
    global_latest_md_path = REPORT_DIR / "latest.md"
    markdown = render_markdown(report)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    global_latest_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    latest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    latest_md_path.write_text(markdown, encoding="utf-8")
    if latest_path != global_latest_path:
        global_latest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if latest_md_path != global_latest_md_path:
        global_latest_md_path.write_text(markdown, encoding="utf-8")
    if not args.no_refresh_report:
        refresh_report_surfaces_quietly(base_url)

    result = report.get("result", {})
    print(f"Report: {report_path}")
    if args.speech_audit_only:
        audit = result.get("speech_audit") if isinstance(result.get("speech_audit"), dict) else {}
        speech_runtime = result.get("speech_runtime") if isinstance(result.get("speech_runtime"), dict) else {}
        transcripts = [
            str(item.get("transcript") or "").strip()
            for item in audit.get("items", [])
            if isinstance(item, dict) and str(item.get("transcript") or "").strip()
        ]
        print(f"Speech audit status: {audit.get('status')}")
        print(f"Payloads: {audit.get('payload_count')} | Leaks: {audit.get('leak_count')}")
        print(
            "Speech mode: "
            f"{speech_runtime.get('mode') or ('live_playback_exercised' if args.exercise_live_speech else 'suppressed_for_probe')}"
        )
        if speech_runtime:
            print(
                "Live playback requested: "
                f"{speech_runtime.get('playback_requested')} | Active observed: {speech_runtime.get('active_observed')}"
            )
        contract = result.get("measurement_contract") if isinstance(result.get("measurement_contract"), dict) else {}
        if contract:
            print(
                "Physical capture: "
                f"speaker={contract.get('physical_speaker_capture')} | microphone={contract.get('physical_microphone_capture')}"
            )
        print(f"Visible reply: {result.get('visible_reply_preview')!r}")
        if transcripts:
            print(f"Speech transcript: {transcripts[-1]!r}")
    else:
        speech_runtime = result.get("speech_runtime") if isinstance(result.get("speech_runtime"), dict) else {}
        print(f"Command transcript: {result.get('command_transcript')!r}")
        print(f"Routed command: {result.get('routed_command')!r}")
        print(f"Visible reply: {result.get('visible_reply_preview')!r}")
        print(f"Reply transcript: {result.get('reply_transcript')!r}")
        print(f"Similarity: {result.get('reply_similarity')}")
        print(
            "Speech mode: "
            f"{speech_runtime.get('mode') or ('live_playback_exercised' if args.exercise_live_speech else 'suppressed_for_probe')}"
        )
        if speech_runtime:
            print(
                "Live playback requested: "
                f"{speech_runtime.get('playback_requested')} | Active observed: {speech_runtime.get('active_observed')}"
            )
    return 0 if result.get("status") == "passed" else 1


def render_markdown(report: dict[str, Any]) -> str:
    """Render a compact human-readable summary for the latest voice-loop probe."""
    result = report.get("result") if isinstance(report.get("result"), dict) else {}
    input_data = report.get("input") if isinstance(report.get("input"), dict) else {}
    status = str(result.get("status") or "unknown")
    mode = "speech audit" if input_data.get("speech_audit_only") else "closed loop"
    speech_runtime = result.get("speech_runtime") if isinstance(result.get("speech_runtime"), dict) else {}
    speech_mode = str(
        speech_runtime.get("mode")
        or ("live_playback_exercised" if input_data.get("exercise_live_speech") else "suppressed_for_probe")
    )
    lines = [
        "# Latest Jarvis Voice Loop QA",
        "",
        f"- Status: {status}",
        f"- Mode: {mode}",
        f"- Speech mode: {speech_mode}",
        f"- Command: {str(input_data.get('command_text') or '').strip() or '(none)'}",
        f"- STT provider: {str(input_data.get('stt_provider') or 'local')}",
    ]
    if speech_runtime:
        lines.extend(
            [
                f"- Live playback requested: {bool(speech_runtime.get('playback_requested'))}",
                f"- Active speech observed: {bool(speech_runtime.get('active_observed'))}",
            ]
        )
    contract = result.get("measurement_contract") if isinstance(result.get("measurement_contract"), dict) else {}
    if contract:
        lines.extend(
            [
                f"- Physical speaker capture: {bool(contract.get('physical_speaker_capture'))}",
                f"- Physical microphone capture: {bool(contract.get('physical_microphone_capture'))}",
                f"- Proof note: {str(contract.get('notes') or '')}",
            ]
        )
    if input_data.get("speech_audit_only"):
        audit = result.get("speech_audit") if isinstance(result.get("speech_audit"), dict) else {}
        lines.extend(
            [
                f"- Tool: {str(result.get('command_response_tool') or '')}",
                f"- Final visible tool: {str(result.get('final_visible_tool') or '')}",
                f"- Spoken payloads: {int(audit.get('payload_count') or 0)}",
                f"- Speech leaks: {int(audit.get('leak_count') or 0)}",
            ]
        )
    else:
        lines.extend(
            [
                f"- Command transcript: {str(result.get('command_transcript') or '')}",
                f"- Routed command: {str(result.get('routed_command') or '')}",
                f"- Visible reply: {str(result.get('visible_reply_preview') or '')}",
                f"- Reply transcript: {str(result.get('reply_transcript') or '')}",
                f"- Reply similarity: {float(result.get('reply_similarity') or 0.0):.3f}",
            ]
        )
    visible_screen_follow_up = (
        result.get("visible_screen_follow_up")
        if isinstance(result.get("visible_screen_follow_up"), dict)
        else {}
    )
    if visible_screen_follow_up.get("attempted") or visible_screen_follow_up.get("used"):
        lines.append(
            "- Visible-screen follow-up: "
            f"{str(visible_screen_follow_up.get('status') or 'unknown')}"
            f" via {str(visible_screen_follow_up.get('tool') or 'n/a')}"
        )
    return "\n".join(lines).rstrip() + "\n"


def allocate_run_dir(output_dir: Path) -> Path:
    """Create a unique run directory even when multiple probes start together."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    for suffix in ["", *[f"-{index:02d}" for index in range(2, 100)]]:
        candidate = output_dir / f"{stamp}{suffix}"
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue
    fallback = output_dir / f"{stamp}-{os.getpid()}-{time.monotonic_ns()}"
    fallback.mkdir()
    return fallback


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
    expect_visible_not_contains: list[str] | None = None,
    expect_routed_contains: list[str] | None = None,
    exercise_live_speech: bool = False,
    allow_audio_actions: bool = False,
    exercise_visible_navigation: bool = False,
) -> dict[str, Any]:
    base_url = normalize_base_url(base_url)
    started = time.monotonic()
    stage_timings: list[dict[str, Any]] = []
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
            "exercise_live_speech": exercise_live_speech,
            "allow_audio_actions": allow_audio_actions,
            "exercise_visible_navigation": exercise_visible_navigation,
            "expect_tools": expect_tools or [],
            "expect_visible_contains": expect_visible_contains or [],
            "expect_visible_not_contains": expect_visible_not_contains or [],
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
        stage_started = time.monotonic()
        command_tts = synthesize(command_text, command_audio, length_scale=length_scale)
        stage_timings.append(stage_timing("command_tts", stage_started))
        stage_started = time.monotonic()
        command_transcription = transcribe_audio(
            command_audio,
            apple_output_json=command_stt,
            local_output_json=command_local_stt,
            timeout=timeout,
            provider=stt_provider,
            no_permission_prompts=no_permission_prompts,
        )
        stage_timings.append(stage_timing("command_stt", stage_started))
        command_transcript = str(command_transcription.get("transcript") or "").strip()
        stage_started = time.monotonic()
        route = route_transcript(command_transcript)
        stage_timings.append(stage_timing("wake_route", stage_started))
        if not route["command"]:
            report["result"] = {
                "status": "failed",
                "warnings": [
                    f"Command STT status was {command_transcription.get('status')}.",
                    "No command was extracted from the spoken command transcript.",
                ],
                "total_seconds": round(time.monotonic() - started, 3),
                "stage_timings": stage_timings,
                "command_tts": command_tts,
                "command_stt": command_transcription,
                "command_transcript": command_transcript,
                "wake_route": route,
                "routed_command": "",
                "speech_runtime": inspect_live_speech_runtime(
                    [],
                    base_url=base_url,
                    timeout=min(timeout, 4.0),
                    exercise_live_speech=exercise_live_speech,
                ),
            }
            return report

        stage_started = time.monotonic()
        stream_events = stream_command_events(
            base_url,
            route["command"],
            timeout=timeout,
            suppress_speech=not exercise_live_speech,
            suppress_audio_actions=not allow_audio_actions,
        )
        stage_timings.append(stage_timing("jarvis_stream", stage_started))
        command_response = final_response_from_stream_events(stream_events)
        if not command_response:
            raise RuntimeError("Jarvis stream did not return a final response.")

        stage_started = time.monotonic()
        visible_screen_follow_up = run_native_visible_screen_follow_up(
            command_text=route["command"],
            command_response=command_response,
            base_url=base_url,
            run_dir=run_dir,
            timeout=timeout,
            exercise_visible_navigation=exercise_visible_navigation,
        )
        if visible_screen_follow_up.get("attempted"):
            stage_timings.append(stage_timing("native_visible_screen_followup", stage_started))
        effective_response = (
            visible_screen_follow_up.get("response")
            if isinstance(visible_screen_follow_up.get("response"), dict)
            else command_response
        )
        visible_reply = extract_visible_reply(effective_response)
        expectation = evaluate_expectations(
            command_response=command_response,
            visible_reply=visible_reply,
            routed_command=route["command"],
            expect_tools=expect_tools or [],
            expect_visible_contains=expect_visible_contains or [],
            expect_visible_not_contains=expect_visible_not_contains or [],
            expect_routed_contains=expect_routed_contains or [],
        )
        stage_timings.append(stage_timing("expectations", stage_started))
        stage_started = time.monotonic()
        speech_runtime = inspect_live_speech_runtime(
            stream_events,
            base_url=base_url,
            timeout=min(timeout, 4.0),
            exercise_live_speech=exercise_live_speech,
        )
        stage_timings.append(stage_timing("live_speech_runtime", stage_started))
        stage_started = time.monotonic()
        speech_payloads = speech_payloads_from_stream_events(stream_events)
        if isinstance(visible_screen_follow_up.get("response"), dict):
            speech_payloads.extend(
                speech_payloads_from_direct_response(
                    visible_screen_follow_up["response"],
                    source="final",
                    reason="visible_screen_followup",
                )
            )
        speech_audit = audit_spoken_payloads(
            speech_payloads,
            run_dir=run_dir,
            length_scale=length_scale,
            timeout=timeout,
            stt_provider=stt_provider,
            no_permission_prompts=no_permission_prompts,
        )
        stage_timings.append(stage_timing("speech_audit", stage_started))
        final_audit_item = final_spoken_audit_item(speech_audit)
        if final_audit_item:
            reply_tts = final_audit_item.get("tts") if isinstance(final_audit_item.get("tts"), dict) else {}
            reply_transcription = final_audit_item.get("stt") if isinstance(final_audit_item.get("stt"), dict) else {}
            reply_audio_source = "speech_audit_final_payload"
            reply_expected_text = speech_payload_text(final_audit_item, fallback=visible_reply)
            reply_similarity_target = "spoken_payload"
        else:
            stage_started = time.monotonic()
            reply_tts = synthesize(visible_reply or "No visible reply.", reply_audio, length_scale=length_scale)
            stage_timings.append(stage_timing("reply_tts", stage_started))
            stage_started = time.monotonic()
            reply_transcription = transcribe_audio(
                reply_audio,
                apple_output_json=reply_stt,
                local_output_json=reply_local_stt,
                timeout=timeout,
                provider=stt_provider,
                no_permission_prompts=no_permission_prompts,
            )
            stage_timings.append(stage_timing("reply_stt", stage_started))
            reply_audio_source = "visible_reply_resynthesized"
            reply_expected_text = visible_reply
            reply_similarity_target = "visible_reply"
        reply_transcript = str(reply_transcription.get("transcript") or "").strip()
        similarity = text_similarity(reply_expected_text, reply_transcript)

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
            warnings.append(f"Reply transcript differed meaningfully from {reply_similarity_target}.")
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
            "measurement_contract": measurement_contract(exercise_live_speech=exercise_live_speech),
            "stage_timings": stage_timings,
            "command_tts": command_tts,
            "command_stt": command_transcription,
            "command_transcript": command_transcript,
            "wake_route": route,
            "routed_command": route["command"],
            "command_response_tool": command_response.get("tool"),
            "command_response_result": command_response_result_summary(command_response),
            "final_visible_tool": effective_response.get("tool") if isinstance(effective_response, dict) else "",
            "visible_reply": visible_reply,
            "visible_reply_preview": visible_reply[:500],
            "expectation": expectation,
            "stream_event_count": len(stream_events),
            "speech_runtime": speech_runtime,
            "speech_audit": speech_audit,
            "visible_screen_follow_up": compact_visible_screen_follow_up(visible_screen_follow_up),
            "reply_audio_source": reply_audio_source,
            "reply_tts": reply_tts,
            "reply_stt": reply_transcription,
            "reply_transcript": reply_transcript,
            "reply_similarity": similarity,
            "reply_similarity_target": reply_similarity_target,
            "reply_expected_text": reply_expected_text,
            "reply_expected_text_preview": reply_expected_text[:500],
        }
        return report
    except Exception as error:
        report["result"] = {
            "status": "failed",
            "error": f"{type(error).__name__}: {error}",
            "total_seconds": round(time.monotonic() - started, 3),
            "stage_timings": stage_timings,
            "measurement_contract": measurement_contract(exercise_live_speech=exercise_live_speech),
        }
        return report


def stage_timing(name: str, started: float) -> dict[str, Any]:
    return {"stage": name, "duration_seconds": round(time.monotonic() - started, 3)}


def measurement_contract(*, exercise_live_speech: bool = False) -> dict[str, Any]:
    return {
        "audio_input": "Synthesized command WAV transcribed by the selected STT provider.",
        "jarvis_speech_output": (
            "Exact Jarvis speech payloads were synthesized to WAV and transcribed."
            if not exercise_live_speech
            else "Exact Jarvis speech payloads were synthesized to WAV and transcribed, and the live playback path was exercised in Jarvis."
        ),
        "live_playback_exercised": bool(exercise_live_speech),
        "physical_speaker_capture": False,
        "physical_microphone_capture": False,
        "notes": (
            "This verifies the sound files Jarvis would hear/say, not room acoustics or Mac speaker loopback."
            if not exercise_live_speech
            else "This verifies the live speech path plus the sound files Jarvis would hear/say, but it still does not capture room acoustics or Mac speaker loopback."
        ),
    }


def speech_statuses_from_stream_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        speech = data.get("speech")
        if not isinstance(speech, dict) or not speech:
            continue
        statuses.append(
            {
                "source": str(event.get("event") or ""),
                "event_index": index,
                "spoken": bool(speech.get("spoken")),
                "status": str(speech.get("status") or ""),
                "provider": str(speech.get("provider") or ""),
                "reason": str(speech.get("reason") or ""),
                "text_preview": speech_payload_text(speech, fallback=data.get("text"))[:200],
            }
        )
    return statuses


def compact_speech_state(state: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    keys = (
        "status",
        "muted",
        "active_speech",
        "automatic_tts_enabled",
        "automatic_speech_available",
        "tts_provider",
        "tts_available",
        "speech_reason",
        "reply",
    )
    return {key: state.get(key) for key in keys if key in state}


def fetch_speech_state(base_url: str, *, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/speech/mute",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as error:
        return {"status": "unavailable", "error": f"{type(error).__name__}: {error}"}


def inspect_live_speech_runtime(
    events: list[dict[str, Any]],
    *,
    base_url: str,
    timeout: float,
    exercise_live_speech: bool,
) -> dict[str, Any]:
    payload_statuses = speech_statuses_from_stream_events(events)
    playback_requested = bool(exercise_live_speech and any(item.get("spoken") for item in payload_statuses))
    if not exercise_live_speech:
        return {
            "mode": "suppressed_for_probe",
            "playback_requested": False,
            "active_observed": False,
            "payload_statuses": payload_statuses,
            "poll_count": 0,
        }

    poll_timeout = max(0.2, min(timeout, 4.0))
    deadline = time.monotonic() + poll_timeout
    polls: list[dict[str, Any]] = []
    active_observed = False
    saw_active_then_idle = False
    while True:
        state = compact_speech_state(fetch_speech_state(base_url, timeout=min(timeout, 5.0)))
        polls.append(state)
        is_active = bool(state.get("active_speech"))
        if is_active:
            active_observed = True
        elif active_observed:
            saw_active_then_idle = True
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(0.12)

    return {
        "mode": "live_playback_exercised",
        "playback_requested": playback_requested,
        "active_observed": active_observed,
        "payload_statuses": payload_statuses,
        "poll_count": len(polls),
        "saw_active_then_idle": saw_active_then_idle,
        "initial_state": polls[0] if polls else {},
        "final_state": polls[-1] if polls else {},
    }


def final_spoken_audit_item(speech_audit: dict[str, Any]) -> dict[str, Any] | None:
    items = speech_audit.get("items")
    if not isinstance(items, list):
        return None
    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        if item.get("source") == "final" and isinstance(item.get("stt"), dict):
            return item
    return None


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
    expect_visible_not_contains: list[str] | None = None,
    expect_routed_contains: list[str] | None = None,
    exercise_live_speech: bool = False,
    allow_audio_actions: bool = False,
    exercise_visible_navigation: bool = False,
) -> dict[str, Any]:
    base_url = normalize_base_url(base_url)
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
            "exercise_live_speech": exercise_live_speech,
            "allow_audio_actions": allow_audio_actions,
            "exercise_visible_navigation": exercise_visible_navigation,
            "expect_tools": expect_tools or [],
            "expect_visible_contains": expect_visible_contains or [],
            "expect_visible_not_contains": expect_visible_not_contains or [],
            "expect_routed_contains": expect_routed_contains or [],
        },
    }
    try:
        stream_events = stream_command_events(
            base_url,
            command_text,
            timeout=timeout,
            suppress_speech=not exercise_live_speech,
            suppress_audio_actions=not allow_audio_actions,
        )
        command_response = final_response_from_stream_events(stream_events)
        visible_screen_follow_up = run_native_visible_screen_follow_up(
            command_text=command_text,
            command_response=command_response,
            base_url=base_url,
            run_dir=run_dir,
            timeout=timeout,
            exercise_visible_navigation=exercise_visible_navigation,
        )
        effective_response = (
            visible_screen_follow_up.get("response")
            if isinstance(visible_screen_follow_up.get("response"), dict)
            else command_response
        )
        visible_reply = extract_visible_reply(effective_response) if effective_response else ""
        response_result = command_response_result_summary(command_response or {})
        stream_timing = stream_timing_summary(
            stream_events,
            command_response=command_response or {},
            visible_reply=visible_reply,
        )
        expectation = evaluate_expectations(
            command_response=command_response or {},
            visible_reply=visible_reply,
            routed_command=command_text,
            expect_tools=expect_tools or [],
            expect_visible_contains=expect_visible_contains or [],
            expect_visible_not_contains=expect_visible_not_contains or [],
            expect_routed_contains=expect_routed_contains or [],
        )
        speech_runtime = inspect_live_speech_runtime(
            stream_events,
            base_url=base_url,
            timeout=min(timeout, 4.0),
            exercise_live_speech=exercise_live_speech,
        )
        speech_payloads = speech_payloads_from_stream_events(stream_events)
        if isinstance(visible_screen_follow_up.get("response"), dict):
            speech_payloads.extend(
                speech_payloads_from_direct_response(
                    visible_screen_follow_up["response"],
                    source="final",
                    reason="visible_screen_followup",
                )
            )
        speech_audit = audit_spoken_payloads(
            speech_payloads,
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
            "measurement_contract": measurement_contract(exercise_live_speech=exercise_live_speech),
            "command_response_tool": command_response.get("tool") if command_response else "",
            "final_visible_tool": effective_response.get("tool") if isinstance(effective_response, dict) else "",
            "command_response_result": response_result,
            "visible_reply": visible_reply,
            "visible_reply_preview": visible_reply[:500],
            "expectation": expectation,
            "stream_event_count": len(stream_events),
            "stream_timing": stream_timing,
            "speech_runtime": speech_runtime,
            "speech_audit": speech_audit,
            "visible_screen_follow_up": compact_visible_screen_follow_up(visible_screen_follow_up),
        }
        return report
    except Exception as error:
        report["result"] = {
            "status": "failed",
            "error": f"{type(error).__name__}: {error}",
            "total_seconds": round(time.monotonic() - started, 3),
            "measurement_contract": measurement_contract(exercise_live_speech=exercise_live_speech),
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
    worker_inputs = [
        (
            index,
            payload,
            audit_dir,
            length_scale,
            timeout,
            stt_provider,
            no_permission_prompts,
        )
        for index, payload in enumerate(payloads, start=1)
    ]
    worker_count = max(1, min(SPEECH_AUDIT_MAX_WORKERS, len(worker_inputs)))
    if worker_count == 1:
        worker_results = [_audit_spoken_payload_item(*worker_input) for worker_input in worker_inputs]
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            worker_results = list(executor.map(lambda args: _audit_spoken_payload_item(*args), worker_inputs))

    for item, item_warnings, item_leaks in worker_results:
        items.append(item)
        warnings.extend(item_warnings)
        all_leaks.extend(item_leaks)

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


def _audit_spoken_payload_item(
    index: int,
    payload: dict[str, Any],
    audit_dir: Path,
    length_scale: float,
    timeout: float,
    stt_provider: str,
    no_permission_prompts: bool,
) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
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
        "spoken_text": text,
        "text_preview": text[:500],
        "intended_leaks": intended_leaks,
        "audio_path": str(audio_path),
        "stt_path": str(stt_path),
        "local_stt_path": str(local_stt_path),
    }
    warnings: list[str] = []
    leaks: list[dict[str, Any]] = list(intended_leaks)
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
        leaks.extend(transcript_leaks)
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
    return item, warnings, leaks


def evaluate_expectations(
    *,
    command_response: dict[str, Any],
    visible_reply: str,
    routed_command: str,
    expect_tools: list[str],
    expect_visible_contains: list[str],
    expect_visible_not_contains: list[str],
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
    for needle in expect_visible_not_contains:
        needle_norm = normalize_text(needle)
        if needle_norm and needle_norm in visible_norm:
            failures.append(f"Visible reply unexpectedly contained {needle!r}.")
    for needle in expect_routed_contains:
        needle_norm = normalize_text(needle)
        if needle_norm and needle_norm not in routed_norm:
            failures.append(f"Routed command did not contain {needle!r}.")
    return {
        "passed": not failures,
        "expected_tools": clean_tools,
        "actual_tool": actual_tool,
        "expect_visible_contains": [text for text in expect_visible_contains if text],
        "expect_visible_not_contains": [text for text in expect_visible_not_contains if text],
        "expect_routed_contains": [text for text in expect_routed_contains if text],
        "failures": failures,
    }


def detect_internal_speech_leaks(text: str, *, source: str = "speech") -> list[dict[str, Any]]:
    leaks: list[dict[str, Any]] = []
    raw_text = str(text or "")
    for leak_id, label, pattern in INTERNAL_SPEECH_LEAK_PATTERNS:
        match = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if match:
            if leak_id == "internal_tool_id" and _looks_like_public_domain_match(raw_text, match):
                continue
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


def _looks_like_public_domain_match(text: str, match: re.Match[str]) -> bool:
    excerpt = text[match.start(): min(len(text), match.end() + 24)].casefold()
    return bool(
        re.match(
            r"[a-z0-9-]+\.[a-z0-9-]+\.(?:app|cn|co|com|dev|edu|gov|io|net|org|school|uk)\b",
            excerpt,
        )
    )


def speech_payloads_from_stream_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        event_name = str(event.get("event") or "")
        speech = data.get("speech") if isinstance(data.get("speech"), dict) else {}
        if event_name == "status":
            text = speech_payload_text(speech, fallback=data.get("text"))
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
            text = speech_payload_text(speech)
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


def speech_payloads_from_direct_response(
    response: dict[str, Any],
    *,
    source: str = "final",
    reason: str | None = None,
) -> list[dict[str, Any]]:
    speech = response.get("speech") if isinstance(response.get("speech"), dict) else {}
    text = speech_payload_text(speech)
    if not text or speech.get("status") == "suppressed_for_stop_speaking":
        return []
    return [
        {
            "source": source,
            "event_index": None,
            "reason": reason or speech.get("reason") or source,
            "tool": response.get("tool"),
            "text": text,
        }
    ]


def speech_payload_text(speech: dict[str, Any], *, fallback: Any = "") -> str:
    """Return the full spoken text when available, falling back to older previews."""
    return str(speech.get("spoken_text") or speech.get("text_preview") or fallback or "").strip()


def final_response_from_stream_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in reversed(events):
        if event.get("event") == "final" and isinstance(event.get("data"), dict):
            return event["data"]
    return {}


def command_response_result_summary(command_response: dict[str, Any]) -> dict[str, Any]:
    result = command_response.get("result") if isinstance(command_response.get("result"), dict) else {}
    summary = {
        "backend": result.get("backend"),
        "model": result.get("model"),
        "status": result.get("status"),
        "duration_seconds": result.get("duration_seconds"),
        "first_visible_token_seconds": result.get("first_visible_token_seconds"),
        "fallback_used": bool(result.get("fallback_used")),
        "primary_fallback_used": bool(result.get("primary_fallback_used")),
        "fallback_trigger": result.get("fallback_trigger"),
        "primary_status": result.get("primary_status"),
        "tool_catalog_compacted": bool(result.get("tool_catalog_compacted")),
    }
    routing = result.get("routing") if isinstance(result.get("routing"), dict) else {}
    if routing:
        summary["routing"] = {
            "source": routing.get("source"),
            "primitive_exception": routing.get("primitive_exception"),
            "confidence": routing.get("confidence"),
        }
        summary["route_source"] = routing.get("source")
    tool = str(command_response.get("tool") or result.get("tool") or "")
    if tool == "outlook.visible_summary":
        contact_lookup = result.get("contact_alias_lookup") if isinstance(result.get("contact_alias_lookup"), dict) else {}
        summary.update(
            {
                "source": result.get("source"),
                "sender_query": result.get("sender_query"),
                "date_range": result.get("date_range"),
                "selection_mode": result.get("selection_mode"),
                "message_count": result.get("message_count"),
                "match_count": result.get("match_count"),
                "scanned_count": result.get("scanned_count"),
                "unread_count": result.get("unread_count"),
                "contact_alias_status": contact_lookup.get("status"),
                "contact_alias": contact_lookup.get("alias"),
                "contact_display_name": contact_lookup.get("display_name"),
            }
        )
    elif tool == "commerce.price_convert":
        summary.update(
            {
                "tool": result.get("tool"),
                "source": result.get("source") if isinstance(result.get("source"), dict) else {},
                "price": result.get("price") if isinstance(result.get("price"), dict) else {},
                "exchange_rate": result.get("exchange_rate") if isinstance(result.get("exchange_rate"), dict) else {},
                "converted": result.get("converted") if isinstance(result.get("converted"), dict) else {},
                "opened_browser": bool(result.get("opened_browser")),
                "changed_browser_state": bool(result.get("changed_browser_state")),
                "reply": result.get("reply"),
            }
        )
    return summary


def stream_timing_summary(
    events: list[dict[str, Any]],
    *,
    command_response: dict[str, Any],
    visible_reply: str,
) -> dict[str, Any]:
    first_status_seconds: float | None = None
    first_final_seconds: float | None = None
    first_visible_seconds: float | None = None
    first_speech_payload_seconds: float | None = None
    for event in events:
        seconds = _stream_event_seconds(event)
        if seconds is None:
            continue
        event_name = str(event.get("event") or "")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        speech = data.get("speech") if isinstance(data.get("speech"), dict) else {}
        if event_name == "status" and first_status_seconds is None:
            first_status_seconds = seconds
        if event_name == "final" and first_final_seconds is None:
            first_final_seconds = seconds
        spoken_text = speech_payload_text(speech, fallback=data.get("text"))
        if spoken_text and speech.get("status") != "suppressed_for_stop_speaking" and first_speech_payload_seconds is None:
            first_speech_payload_seconds = seconds
        visible_text = stream_event_visible_text(event_name, data, visible_reply=visible_reply)
        if visible_text and first_visible_seconds is None:
            first_visible_seconds = seconds
    result_summary = command_response_result_summary(command_response)
    if first_visible_seconds is None:
        first_visible_seconds = _optional_float(result_summary.get("first_visible_token_seconds"))
    return {
        "first_status_seconds": first_status_seconds,
        "first_final_seconds": first_final_seconds,
        "first_visible_seconds": first_visible_seconds,
        "first_speech_payload_seconds": first_speech_payload_seconds,
    }


def stream_event_visible_text(event_name: str, data: dict[str, Any], *, visible_reply: str) -> str:
    if event_name == "status":
        return str(data.get("text") or "").strip()
    if event_name == "delta":
        return str(data.get("text") or data.get("delta") or data.get("content") or "").strip()
    if event_name == "final":
        final_text = extract_visible_reply(data).strip()
        if final_text:
            return final_text
        return visible_reply.strip()
    return ""


def _stream_event_seconds(event: dict[str, Any]) -> float | None:
    return _optional_float(event.get("received_at_seconds"))


def _optional_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


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
    tokens = text.split()
    normalized: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if index + 1 < len(tokens) and token in {"a", "p"} and tokens[index + 1] == "m":
            normalized.append(f"{token}m")
            index += 2
            continue
        if token in TENS_WORD_VALUES:
            value = TENS_WORD_VALUES[token]
            if index + 1 < len(tokens):
                next_value = NUMBER_WORD_VALUES.get(tokens[index + 1])
                if next_value is not None and 0 < next_value < 10:
                    normalized.append(str(value + next_value))
                    index += 2
                    continue
            normalized.append(str(value))
            index += 1
            continue
        if token in NUMBER_WORD_VALUES:
            normalized.append(str(NUMBER_WORD_VALUES[token]))
            index += 1
            continue
        normalized.append(token)
        index += 1

    merged: list[str] = []
    index = 0
    while index < len(normalized):
        token = normalized[index]
        if token.isdigit() and index + 1 < len(normalized):
            next_token = normalized[index + 1]
            if next_token == "age":
                merged.append(f"{token}h")
                index += 2
                continue
            if len(next_token) == 1 and next_token.isalpha():
                merged.append(f"{token}{next_token}")
                index += 2
                continue
        merged.append(token)
        index += 1
    return " ".join(merged)


def stream_command_events(
    base_url: str,
    command: str,
    *,
    timeout: float,
    suppress_speech: bool = True,
    suppress_audio_actions: bool = True,
) -> list[dict[str, Any]]:
    payload = {
        "command": command,
        "suppress_speech": True,
        "suppress_audio_actions": bool(suppress_audio_actions),
    }
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
    started = time.monotonic()

    def flush_event() -> str | None:
        nonlocal event_name, data_lines
        if not data_lines:
            event_name = "message"
            return None
        current_event_name = event_name
        raw_data = "\n".join(data_lines)
        try:
            data: Any = json.loads(raw_data)
        except json.JSONDecodeError:
            data = raw_data
        events.append(
            {
                "event": event_name,
                "data": data,
                "received_at_seconds": round(time.monotonic() - started, 3),
            }
        )
        event_name = "message"
        data_lines = []
        return current_event_name

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line:
                    flushed_event = flush_event()
                    if flushed_event == "final":
                        break
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


def post_loopback_json(
    base_url: str,
    path: str,
    payload: dict[str, Any],
    *,
    timeout: float,
) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
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


def visible_screen_follow_up_target(command_text: str, command_response: dict[str, Any]) -> dict[str, str] | None:
    if str(command_response.get("tool") or "") != "teams.assignment":
        return None
    lower = str(command_text or "").casefold()
    if "teams" not in lower or "assignment" not in lower:
        return None
    result = command_response.get("result") if isinstance(command_response.get("result"), dict) else {}
    if result and result.get("automatic_teams_page_inspection_supported") is False:
        return None
    return {
        "reason": "teams_assignment_native_visible_screen",
        "target_app_name": "Google Chrome",
        "target_bundle_identifier": "com.google.Chrome",
    }


def run_native_visible_screen_follow_up(
    *,
    command_text: str,
    command_response: dict[str, Any],
    base_url: str,
    run_dir: Path,
    timeout: float,
    exercise_visible_navigation: bool = False,
) -> dict[str, Any]:
    target = visible_screen_follow_up_target(command_text, command_response)
    if not target:
        return {"attempted": False, "used": False, "status": "not_needed"}

    follow_up_dir = run_dir / "visible-screen-followup"
    follow_up_dir.mkdir(parents=True, exist_ok=True)
    capture_path = follow_up_dir / "capture.json"
    response_path = follow_up_dir / "response.json"
    started = time.monotonic()
    result: dict[str, Any] = {
        "attempted": True,
        "used": False,
        "status": "probe_pending",
        "reason": target["reason"],
        "target_app_name": target["target_app_name"],
        "target_bundle_identifier": target["target_bundle_identifier"],
        "capture_report": str(capture_path),
        "response_report": str(response_path),
        "browser_open_attempted": False,
    }
    if not VISIBLE_SCREEN_PROBE.exists():
        return {
            **result,
            "status": "probe_missing",
            "duration_seconds": round(time.monotonic() - started, 3),
            "error": f"Native visible-screen probe not found at {VISIBLE_SCREEN_PROBE}",
        }

    initial_browser_page_follow_up = run_browser_page_follow_up(
        command_text=command_text,
        base_url=base_url,
        follow_up_dir=follow_up_dir,
        timeout=timeout,
    )
    result["browser_page_follow_up_initial"] = compact_direct_follow_up(initial_browser_page_follow_up)
    result["browser_page_follow_up"] = result["browser_page_follow_up_initial"]
    if initial_browser_page_follow_up.get("status") == "completed":
        return {
            **result,
            **initial_browser_page_follow_up,
            "attempts": 1,
            "duration_seconds": round(time.monotonic() - started, 3),
        }
    if initial_browser_page_follow_up.get("status") == "login_gate_visible":
        return {
            **result,
            **initial_browser_page_follow_up,
            "attempts": 0,
            "duration_seconds": round(time.monotonic() - started, 3),
        }

    browser_page_follow_up = initial_browser_page_follow_up
    if initial_browser_page_follow_up.get("status") != "browser_permission_blocked":
        browser_open = open_visible_screen_follow_up_url(command_response, timeout=timeout)
        result.update(browser_open)
        if (
            browser_open.get("browser_open_attempted")
            and browser_open.get("browser_open_returncode") == 0
            and browser_open.get("browser_open_target_host_verified") is False
        ):
            return {
                **result,
                "status": "browser_focus_not_verified",
                "used": False,
                "attempts": 0,
                "duration_seconds": round(time.monotonic() - started, 3),
            }
        if browser_open.get("browser_open_attempted"):
            time.sleep(VISIBLE_SCREEN_FOLLOW_UP_INITIAL_OPEN_DELAY_SECONDS)

        browser_page_follow_up = run_browser_page_follow_up(
            command_text=command_text,
            base_url=base_url,
            follow_up_dir=follow_up_dir,
            timeout=timeout,
        )
        result["browser_page_follow_up"] = compact_direct_follow_up(browser_page_follow_up)
        if browser_page_follow_up.get("status") == "completed":
            return {
                **result,
                **browser_page_follow_up,
                "attempts": 1,
                "duration_seconds": round(time.monotonic() - started, 3),
            }
        if browser_page_follow_up.get("status") == "login_gate_visible":
            return {
                **result,
                **browser_page_follow_up,
                "attempts": 0,
                "duration_seconds": round(time.monotonic() - started, 3),
            }

    latest_failure: dict[str, Any] | None = None
    max_attempts = max(
        1,
        1 if browser_page_follow_up.get("status") == "browser_permission_blocked" else VISIBLE_SCREEN_FOLLOW_UP_RETRY_ATTEMPTS,
    )
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            time.sleep(VISIBLE_SCREEN_FOLLOW_UP_RETRY_DELAY_SECONDS)
        attempt_result = run_native_visible_screen_follow_up_attempt(
            command_text=command_text,
            base_url=base_url,
            follow_up_dir=follow_up_dir,
            timeout=timeout,
            target_app_name=target["target_app_name"],
            target_bundle_identifier=target["target_bundle_identifier"],
            attempt=attempt,
        )
        if attempt_result.get("status") == "completed":
            return {
                **result,
                **attempt_result,
                "attempts": attempt,
                "duration_seconds": round(time.monotonic() - started, 3),
            }
        latest_failure = attempt_result

    navigation_steps: list[dict[str, Any]] = []
    if exercise_visible_navigation and isinstance(latest_failure, dict):
        seen_navigation_points: set[tuple[float, float]] = set()
        for navigation_attempt in range(1, 4):
            plan = next_visible_navigation_plan(latest_failure)
            if not isinstance(plan, dict) or not plan.get("planned"):
                break
            point = plan.get("point") if isinstance(plan.get("point"), dict) else {}
            try:
                point_key = (round(float(point.get("x")), 2), round(float(point.get("y")), 2))
            except (TypeError, ValueError):
                point_key = (float(navigation_attempt), -1.0)
            if point_key in seen_navigation_points:
                latest_failure["visible_navigation_execution"] = {
                    "attempted": False,
                    "executed": False,
                    "status": "navigation_loop_prevented",
                    "point": {"x": point_key[0], "y": point_key[1]},
                }
                break
            seen_navigation_points.add(point_key)
            navigation_result = execute_visible_navigation_plan(
                plan,
                target_app_name=target["target_app_name"],
                timeout=timeout,
            )
            navigation_steps.append(navigation_result)
            latest_failure["visible_navigation_execution"] = navigation_result
            latest_failure["visible_navigation_execution_steps"] = list(navigation_steps)
            if not navigation_result.get("executed"):
                break
            time.sleep(VISIBLE_SCREEN_FOLLOW_UP_RETRY_DELAY_SECONDS)
            after_navigation = run_native_visible_screen_follow_up_attempt(
                command_text=command_text,
                base_url=base_url,
                follow_up_dir=follow_up_dir,
                timeout=timeout,
                target_app_name=target["target_app_name"],
                target_bundle_identifier=target["target_bundle_identifier"],
                attempt=max_attempts + navigation_attempt,
            )
            after_navigation["visible_navigation_execution"] = navigation_result
            after_navigation["visible_navigation_execution_steps"] = list(navigation_steps)
            if after_navigation.get("status") == "completed":
                return {
                    **result,
                    **after_navigation,
                    "attempts": max_attempts + navigation_attempt,
                    "duration_seconds": round(time.monotonic() - started, 3),
                }
            latest_failure = after_navigation

    return {
        **result,
        **merge_follow_up_failures(browser_page_follow_up, latest_failure),
        "attempts": max_attempts,
        "duration_seconds": round(time.monotonic() - started, 3),
    }


def run_browser_page_follow_up(
    *,
    command_text: str,
    base_url: str,
    follow_up_dir: Path,
    timeout: float,
) -> dict[str, Any]:
    response_path = follow_up_dir / "browser-read-response.json"
    try:
        summary_response = post_loopback_json(
            base_url,
            "/api/browser/read-page",
            {
                "command": command_text,
                "max_chars": 6000,
                "suppress_speech": True,
            },
            timeout=timeout,
        )
    except Exception as error:
        return {
            "used": False,
            "status": "browser_read_failed",
            "error": f"{type(error).__name__}: {error}",
            "response_report": str(response_path),
        }

    response_path.write_text(json.dumps(summary_response, indent=2, ensure_ascii=False), encoding="utf-8")
    summary_result = summary_response.get("result") if isinstance(summary_response.get("result"), dict) else {}
    response_status = str(summary_result.get("status") or "")
    visible_reply = extract_visible_reply(summary_response)
    useful = browser_page_follow_up_response_looks_useful(summary_response, command_text=command_text)
    blocked = response_status in {"automation_not_allowed", "chrome_javascript_unavailable", "teams_page_text_unavailable"}
    login_gate_visible = response_status == "visible_screen_login_gate"
    return {
        "used": useful,
        "status": (
            "completed"
            if useful
            else "browser_permission_blocked"
            if blocked
            else "login_gate_visible"
            if login_gate_visible
            else "response_not_useful"
        ),
        "tool": summary_response.get("tool"),
        "response_status": response_status,
        "visible_reply_preview": visible_reply[:500],
        "response": summary_response if useful or blocked or login_gate_visible else None,
        "response_report": str(response_path),
    }


def run_native_visible_screen_follow_up_attempt(
    *,
    command_text: str,
    base_url: str,
    follow_up_dir: Path,
    timeout: float,
    target_app_name: str,
    target_bundle_identifier: str,
    attempt: int,
) -> dict[str, Any]:
    capture_path = follow_up_dir / f"capture-{attempt:02d}.json"
    response_path = follow_up_dir / f"response-{attempt:02d}.json"
    probe_command = [
        str(VISIBLE_SCREEN_PROBE),
        "--target-app-name",
        target_app_name,
        "--target-bundle-id",
        target_bundle_identifier,
    ]
    try:
        completed = subprocess.run(
            probe_command,
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            timeout=max(15.0, timeout + 10.0),
            check=False,
        )
    except Exception as error:
        return {
            "used": False,
            "status": "probe_failed",
            "error": f"{type(error).__name__}: {error}",
            "attempt": attempt,
            "capture_report": str(capture_path),
            "response_report": str(response_path),
        }

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    try:
        capture_payload = json.loads(stdout) if stdout else {
            "status": "failed",
            "error": "Native visible-screen probe returned no JSON.",
            "text": "",
            "diagnostics": {},
        }
    except json.JSONDecodeError as error:
        capture_payload = {
            "status": "failed",
            "error": f"JSONDecodeError: {error}",
            "text": "",
            "diagnostics": {},
        }
    capture_path.write_text(json.dumps(capture_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    diagnostics = capture_payload.get("diagnostics") if isinstance(capture_payload.get("diagnostics"), dict) else {}
    captured_text = str(capture_payload.get("text") or "")

    try:
        summary_response = post_loopback_json(
            base_url,
            "/api/screen/visible-text",
            {
                "command": command_text,
                "text": captured_text,
                "diagnostics": diagnostics,
                "suppress_speech": True,
            },
            timeout=timeout,
        )
    except Exception as error:
        return {
            "used": False,
            "status": "summary_failed",
            "probe_returncode": completed.returncode,
            "probe_stdout_tail": stdout[-500:],
            "probe_stderr_tail": stderr[-500:],
            "capture_status": capture_payload.get("status"),
            "captured_text_chars": len(captured_text),
            "error": f"{type(error).__name__}: {error}",
            "attempt": attempt,
            "capture_report": str(capture_path),
            "response_report": str(response_path),
        }

    response_path.write_text(json.dumps(summary_response, indent=2, ensure_ascii=False), encoding="utf-8")
    summary_result = summary_response.get("result") if isinstance(summary_response.get("result"), dict) else {}
    visible_reply = extract_visible_reply(summary_response)
    summary_status = str(summary_result.get("status") or "")
    useful = visible_screen_follow_up_response_looks_useful(summary_response, command_text=command_text)
    status = "completed" if useful else "response_not_useful"
    if not useful and summary_status in {"login_gate_visible", "assignment_subject_mismatch"}:
        status = summary_status
    response_is_auditable = useful or status in {"login_gate_visible", "assignment_subject_mismatch"}
    navigation_targets: dict[str, Any] = {}
    if "teams" in str(command_text or "").casefold() and "assignment" in str(command_text or "").casefold():
        subject_labels = requested_assignment_subject_navigation_labels(command_text)
        if subject_labels:
            subject_target = select_ocr_line_target(capture_payload, subject_labels)
            navigation_targets["requested_class"] = subject_target
            navigation_targets["requested_class_plan"] = visible_navigation_plan(
                subject_target,
                action="click",
                purpose="open the requested Teams class before reading its Assignments view",
            )
        all_teams_target = select_ocr_line_target(capture_payload, ["All teams"])
        navigation_targets["all_teams"] = all_teams_target
        navigation_targets["all_teams_plan"] = visible_navigation_plan(
            all_teams_target,
            action="click",
            purpose="return to the Teams list so the requested class can be selected",
        )
        assignments_target = select_ocr_line_target(capture_payload, ["Assignments"])
        navigation_targets["assignments"] = assignments_target
        navigation_targets["assignments_plan"] = visible_navigation_plan(
            assignments_target,
            action="click",
            purpose="open the Teams Assignments view before reading the requested Music assignment",
        )
        navigation_targets["sequence"] = visible_navigation_sequence(navigation_targets)
    return {
        "used": useful,
        "status": status,
        "probe_returncode": completed.returncode,
        "probe_stdout_tail": stdout[-500:],
        "probe_stderr_tail": stderr[-500:],
        "capture_status": capture_payload.get("status"),
        "captured_text_chars": len(captured_text),
        "tool": summary_response.get("tool"),
        "response_status": summary_result.get("status"),
        "visible_reply_preview": visible_reply[:500],
        "visible_navigation_targets": navigation_targets,
        "response": summary_response if response_is_auditable else None,
        "attempt": attempt,
        "capture_report": str(capture_path),
        "response_report": str(response_path),
    }


def requested_assignment_subject_navigation_labels(command_text: str) -> list[str]:
    """Return likely visible class labels for a requested Teams assignment subject."""
    lower_command = str(command_text or "").casefold()
    if re.search(r"\b(?:music|musical|song|songs|instrument|instruments|choir|band)\b", lower_command):
        return ["Music", "Music Class", "Music Assignments"]
    return []


def select_ocr_line_target(
    capture_payload: dict[str, Any],
    labels: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Return the best visible OCR line target without clicking it."""
    lines = capture_payload.get("ocr_lines")
    if not isinstance(lines, list):
        return {"found": False, "reason": "ocr_lines_missing"}
    normalized_labels = [str(label or "").strip().casefold() for label in labels if str(label or "").strip()]
    if not normalized_labels:
        return {"found": False, "reason": "labels_missing"}
    best: dict[str, Any] | None = None
    best_score = -1
    for index, raw_line in enumerate(lines):
        if not isinstance(raw_line, dict):
            continue
        text = str(raw_line.get("text") or "").strip()
        text_key = text.casefold()
        if not text_key:
            continue
        score = 0
        for label in normalized_labels:
            if text_key == label:
                score = max(score, 100)
            elif _ocr_label_matches_text(label, text_key):
                score = max(score, 80)
        if score <= best_score:
            continue
        pixels = raw_line.get("pixels") if isinstance(raw_line.get("pixels"), dict) else {}
        try:
            x = float(pixels.get("x"))
            y = float(pixels.get("y"))
            width = float(pixels.get("width"))
            height = float(pixels.get("height"))
        except (TypeError, ValueError):
            continue
        if width <= 0 or height <= 0:
            continue
        best_score = score
        best = {
            "found": score > 0,
            "index": index,
            "text": text,
            "score": score,
            "center": {"x": round(x + width / 2, 2), "y": round(y + height / 2, 2)},
            "pixels": {"x": round(x, 2), "y": round(y, 2), "width": round(width, 2), "height": round(height, 2)},
        }
    return best if best and best.get("found") else {"found": False, "reason": "no_label_match"}


def _ocr_label_matches_text(label: str, text_key: str) -> bool:
    if " " in label:
        return label in text_key
    return bool(re.search(rf"\b{re.escape(label)}\b", text_key))


def visible_navigation_plan(
    target: dict[str, Any],
    *,
    action: str,
    purpose: str,
) -> dict[str, Any]:
    """Describe a visible-screen navigation step without performing it."""
    if not isinstance(target, dict) or not target.get("found"):
        return {
            "planned": False,
            "reason": str(target.get("reason") or "target_missing") if isinstance(target, dict) else "target_missing",
            "will_click": False,
        }
    center = target.get("center") if isinstance(target.get("center"), dict) else {}
    try:
        x = float(center.get("x"))
        y = float(center.get("y"))
    except (TypeError, ValueError):
        return {
            "planned": False,
            "reason": "target_center_missing",
            "will_click": False,
            "target": target,
        }
    return {
        "planned": True,
        "action": action,
        "purpose": purpose,
        "will_click": False,
        "requires_explicit_live_navigation": True,
        "target_text": str(target.get("text") or ""),
        "point": {"x": round(x, 2), "y": round(y, 2)},
        "target": target,
    }


def visible_navigation_sequence(navigation_targets: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the safest ordered Teams navigation plan from the visible state."""
    if not isinstance(navigation_targets, dict):
        return []

    requested_class = _visible_navigation_sequence_step(
        navigation_targets,
        "requested_class",
        "requested class",
        "open the requested Teams class before reading its Assignments view",
    )
    if requested_class:
        return [requested_class, *_visible_navigation_sequence_tail(navigation_targets)]

    all_teams = _visible_navigation_sequence_step(
        navigation_targets,
        "all_teams",
        "All teams",
        "return to the Teams list before looking for the requested class",
    )
    if all_teams:
        return [
            all_teams,
            {
                "key": "requested_class_after_all_teams",
                "label": "requested class",
                "reason": "look for the requested Teams class after opening All teams",
                "plan": {"planned": False, "reason": "requires_previous_step", "will_click": False},
            },
            *_visible_navigation_sequence_tail(navigation_targets),
        ]

    return _visible_navigation_sequence_tail(navigation_targets)


def next_visible_navigation_plan(follow_up: dict[str, Any]) -> dict[str, Any] | None:
    targets = follow_up.get("visible_navigation_targets")
    if not isinstance(targets, dict):
        return None
    sequence = targets.get("sequence") if isinstance(targets.get("sequence"), list) else []
    plan = next(
        (
            step.get("plan")
            for step in sequence
            if isinstance(step, dict)
            and isinstance(step.get("plan"), dict)
            and step["plan"].get("planned")
        ),
        None,
    )
    if isinstance(plan, dict):
        return plan
    for key in ("requested_class_plan", "all_teams_plan", "assignments_plan"):
        plan = targets.get(key)
        if isinstance(plan, dict) and plan.get("planned"):
            return plan
    return None


def _visible_navigation_sequence_step(
    navigation_targets: dict[str, Any],
    key: str,
    label: str,
    reason: str,
) -> dict[str, Any] | None:
    plan = navigation_targets.get(f"{key}_plan")
    if not isinstance(plan, dict) or not plan.get("planned"):
        return None
    return {
        "key": key,
        "label": label,
        "reason": reason,
        "plan": plan,
    }


def _visible_navigation_sequence_tail(navigation_targets: dict[str, Any]) -> list[dict[str, Any]]:
    assignments_plan = navigation_targets.get("assignments_plan")
    if not isinstance(assignments_plan, dict) or not assignments_plan.get("planned"):
        return []
    return [
        {
            "key": "assignments",
            "label": "Assignments",
            "reason": "open Assignments after the requested class is visible",
            "plan": assignments_plan,
        }
    ]


def execute_visible_navigation_plan(
    plan: dict[str, Any],
    *,
    target_app_name: str,
    timeout: float,
) -> dict[str, Any]:
    """Execute a previously generated visible navigation plan only under a double opt-in."""
    if os.environ.get("JARVIS_ALLOW_LIVE_UI_NAVIGATION") != "1":
        return {
            "attempted": False,
            "executed": False,
            "status": "live_navigation_not_unlocked",
            "requires": ["--exercise-visible-navigation", "JARVIS_ALLOW_LIVE_UI_NAVIGATION=1"],
        }
    if not isinstance(plan, dict) or not plan.get("planned"):
        return {"attempted": False, "executed": False, "status": "plan_not_ready"}
    if plan.get("will_click") is not False:
        return {"attempted": False, "executed": False, "status": "plan_not_fail_closed"}
    point = plan.get("point") if isinstance(plan.get("point"), dict) else {}
    try:
        x = float(point.get("x"))
        y = float(point.get("y"))
    except (TypeError, ValueError):
        return {"attempted": False, "executed": False, "status": "point_missing"}
    applescript = f'''
tell application "{escape_applescript_string(target_app_name)}" to activate
delay 0.2
tell application "System Events"
  click at {{{round(x, 2)}, {round(y, 2)}}}
end tell
'''
    completed = subprocess.run(
        ["/usr/bin/osascript", "-e", applescript],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=max(3.0, min(timeout, 10.0)),
        check=False,
    )
    return {
        "attempted": True,
        "executed": completed.returncode == 0,
        "status": "clicked" if completed.returncode == 0 else "click_failed",
        "target_app_name": target_app_name,
        "point": {"x": round(x, 2), "y": round(y, 2)},
        "returncode": completed.returncode,
        "stderr_tail": completed.stderr.strip()[-500:],
    }


def open_visible_screen_follow_up_url(command_response: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    result = command_response.get("result") if isinstance(command_response.get("result"), dict) else {}
    url = str(result.get("url") or "").strip()
    if not url or not re.match(r"^https?://", url, flags=re.IGNORECASE):
        return {"browser_open_attempted": False}
    target_host = (urlparse(url).hostname or "").lower()
    applescript = f"""
set targetURL to "{escape_applescript_string(url)}"
set targetHost to "{escape_applescript_string(target_host)}"
tell application "Google Chrome"
    activate
    if (count of windows) = 0 then
        make new window
    end if
    set matchedTab to false
    repeat with w in windows
        set tabIndex to 1
        repeat with t in tabs of w
            set tabURL to URL of t
            if tabURL is targetURL then
                set active tab index of w to tabIndex
                set index of w to 1
                set matchedTab to true
                exit repeat
            end if
            if (targetHost is "teams.microsoft.com" or targetHost is "teams.cloud.microsoft") and (tabURL contains "teams.microsoft.com" or tabURL contains "teams.cloud.microsoft") then
                set active tab index of w to tabIndex
                set index of w to 1
                set matchedTab to true
                exit repeat
            end if
            set tabIndex to tabIndex + 1
        end repeat
        if matchedTab then
            exit repeat
        end if
    end repeat
    if not matchedTab then
        tell front window
            make new tab at end of tabs with properties {{URL:targetURL}}
            set active tab index to (count of tabs)
        end tell
    end if
    delay 0.3
    set frontURL to ""
    set frontTitle to ""
    try
        set frontURL to URL of active tab of front window
        set frontTitle to title of active tab of front window
    end try
end tell
return frontTitle & linefeed & frontURL
"""
    try:
        completed = subprocess.run(
            ["/usr/bin/osascript", "-e", applescript],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            timeout=max(10.0, timeout),
            check=False,
        )
        stdout = completed.stdout.strip()
        title, active_url = parse_chrome_front_tab_output(stdout)
        active_host = (urlparse(active_url).hostname or "").lower()
        target_host_verified = active_host == target_host or (
            target_host in {"teams.microsoft.com", "teams.cloud.microsoft"}
            and active_host in {"teams.microsoft.com", "teams.cloud.microsoft"}
        )
        return {
            "browser_open_attempted": True,
            "browser_url": url,
            "browser_open_method": "chrome_existing_session",
            "browser_open_returncode": completed.returncode,
            "browser_open_stdout_tail": stdout[-500:],
            "browser_open_stderr_tail": completed.stderr.strip()[-500:],
            "browser_open_active_title": title,
            "browser_open_active_url": active_url,
            "browser_open_target_host_verified": bool(completed.returncode == 0 and target_host_verified),
        }
    except Exception as error:
        return {
            "browser_open_attempted": True,
            "browser_url": url,
            "browser_open_error": f"{type(error).__name__}: {error}",
        }


def escape_applescript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def parse_chrome_front_tab_output(stdout: str) -> tuple[str, str]:
    lines = str(stdout or "").splitlines()
    title = lines[0].strip() if lines else ""
    active_url = lines[1].strip() if len(lines) > 1 else ""
    return title, active_url


def browser_page_follow_up_response_looks_useful(response: dict[str, Any], *, command_text: str = "") -> bool:
    if str(response.get("tool") or "") != "browser.read_page":
        return False
    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    status = str(result.get("status") or "")
    if status in {"automation_not_allowed", "teams_page_text_unavailable", "visible_screen_login_gate", "assignment_subject_mismatch"}:
        return False
    reply = extract_visible_reply(response).casefold()
    digest_items = result.get("page_digest_items") if isinstance(result.get("page_digest_items"), list) else []
    digest_text = " ".join(str(item) for item in digest_items if isinstance(item, str)).casefold()
    combined_text = " ".join([reply, digest_text]).casefold()
    lower_command = str(command_text or "").casefold()
    if "teams" in lower_command and "assignment" in lower_command:
        markers = ["teams", "assignment", "assignments", "rubric", "due", "classwork", "homework"]
        if not any(marker in combined_text for marker in markers):
            return False
        if status == "read_via_visible_screen" and any(
            marker in combined_text
            for marker in ("assignment-related text", "questions i need answered", "newest assignment", "rubric", "due")
        ):
            return True
    if status == "read":
        return True
    try:
        page_text_chars = int(result.get("page_text_chars") or 0)
    except (TypeError, ValueError):
        page_text_chars = 0
    return page_text_chars >= 160


def visible_screen_follow_up_response_looks_useful(response: dict[str, Any], *, command_text: str = "") -> bool:
    if str(response.get("tool") or "") != "screen.visible_text":
        return False
    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    status = str(result.get("status") or "")
    if status in {"login_gate_visible", "assignment_subject_mismatch"}:
        return False
    reply = extract_visible_reply(response).casefold()
    combined_text = " ".join(
        [
            reply,
            " ".join(str(item) for item in (result.get("assignment_digest_items") or []) if isinstance(item, str)),
            " ".join(str(item) for item in (result.get("page_digest_items") or []) if isinstance(item, str)),
        ]
    ).casefold()
    lock_indicators = [
        "enter password",
        "touch id",
        "unlock",
        "who's using chrome",
        "who s using chrome",
        "profiles",
    ]
    if any(indicator in combined_text for indicator in lock_indicators):
        teams_markers = ["teams", "assignment", "assignments", "rubric", "due", "classwork", "homework"]
        if not any(marker in combined_text for marker in teams_markers):
            return False
    lower_command = str(command_text or "").casefold()
    if "teams" in lower_command and "assignment" in lower_command:
        if result.get("detected_assignment_context"):
            return True
        return False
    if status == "checked":
        return True
    assignment_items = result.get("assignment_digest_items") if isinstance(result.get("assignment_digest_items"), list) else []
    if assignment_items:
        return True
    digest_items = result.get("page_digest_items") if isinstance(result.get("page_digest_items"), list) else []
    if digest_items and status not in {"native_ocr_empty", "native_capture_failed"}:
        return True
    try:
        visible_chars = int(result.get("visible_text_chars") or 0)
    except (TypeError, ValueError):
        visible_chars = 0
    return visible_chars >= 160 and status not in {"native_ocr_empty", "native_capture_failed"}


def compact_visible_screen_follow_up(follow_up: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in follow_up.items()
        if key not in {"response"}
    }


def compact_direct_follow_up(follow_up: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in follow_up.items()
        if key not in {"response"}
    }


def merge_follow_up_failures(browser_page_follow_up: dict[str, Any], latest_failure: dict[str, Any] | None) -> dict[str, Any]:
    if latest_failure and latest_failure.get("status") in {"assignment_subject_mismatch", "login_gate_visible"}:
        return latest_failure
    if browser_page_follow_up.get("status") == "browser_permission_blocked":
        merged = dict(latest_failure or {})
        merged.update(
            {
                "used": False,
                "status": "browser_permission_blocked",
                "tool": browser_page_follow_up.get("tool"),
                "response_status": browser_page_follow_up.get("response_status"),
                "visible_reply_preview": browser_page_follow_up.get("visible_reply_preview"),
                "response": browser_page_follow_up.get("response"),
            }
        )
        return merged
    return latest_failure or {"status": "probe_failed", "used": False}


if __name__ == "__main__":
    raise SystemExit(main())
