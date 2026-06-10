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
    args = parser.parse_args()

    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.output_dir).resolve() / stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    report = run_voice_loop(
        command_text=args.command,
        base_url=args.base_url.rstrip("/"),
        run_dir=run_dir,
        length_scale=args.length_scale,
        timeout=args.timeout,
        stt_provider=args.stt_provider,
    )

    report_path = run_dir / "report.json"
    latest_path = Path(args.output_dir).resolve() / "latest.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    latest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    result = report.get("result", {})
    print(f"Report: {report_path}")
    print(f"Command transcript: {result.get('command_transcript')!r}")
    print(f"Routed command: {result.get('routed_command')!r}")
    print(f"Visible reply: {result.get('visible_reply_preview')!r}")
    print(f"Reply transcript: {result.get('reply_transcript')!r}")
    print(f"Similarity: {result.get('reply_similarity')}")
    return 0 if result.get("status") in {"passed", "warning"} else 1


def run_voice_loop(
    *,
    command_text: str,
    base_url: str,
    run_dir: Path,
    length_scale: float,
    timeout: float,
    stt_provider: str,
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
        "input": {"command_text": command_text, "length_scale": length_scale, "stt_provider": stt_provider},
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
        )
        command_transcript = str(command_transcription.get("transcript") or "").strip()
        route = route_transcript(command_transcript)

        original_mute = speech_mute_status(base_url)
        set_speech_mute(base_url, True)
        try:
            command_response = post_json(
                f"{base_url}/api/command",
                {"command": route["command"]},
                timeout=timeout,
            )
        finally:
            set_speech_mute(base_url, original_mute)

        visible_reply = extract_visible_reply(command_response)
        reply_tts = synthesize(visible_reply or "No visible reply.", reply_audio, length_scale=length_scale)
        reply_transcription = transcribe_audio(
            reply_audio,
            apple_output_json=reply_stt,
            local_output_json=reply_local_stt,
            timeout=timeout,
            provider=stt_provider,
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


def synthesize(text: str, output_wav: Path, *, length_scale: float) -> dict[str, Any]:
    output_wav.parent.mkdir(parents=True, exist_ok=True)
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
        return fallback

    return synthesize_with_say(text, output_wav)


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
        ["/usr/bin/say", "-v", "Alex", "-o", str(aiff_path), text],
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
        "voice": "Alex",
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
) -> dict[str, Any]:
    if provider == "local":
        return transcribe_with_local_stt(audio_path, local_output_json, timeout=timeout)

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
    if not LOCAL_STT_PYTHON.exists():
        data = {
            "status": "local_stt_unavailable",
            "provider": "faster_whisper",
            "model": LOCAL_STT_MODEL,
            "audio_path": str(audio_path),
            "transcript": "",
            "missing": str(LOCAL_STT_PYTHON),
        }
        output_json.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return data

    output_json.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    ca_bundle = Path("/opt/homebrew/Cellar/ca-certificates/2025-05-20/share/ca-certificates/cacert.pem")
    if ca_bundle.exists():
        env.setdefault("SSL_CERT_FILE", str(ca_bundle))
        env.setdefault("REQUESTS_CA_BUNDLE", str(ca_bundle))
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
    data["returncode"] = completed.returncode
    if completed.stdout.strip():
        data["stdout_tail"] = completed.stdout.strip()[-500:]
    if completed.stderr.strip():
        data["stderr_tail"] = completed.stderr.strip()[-500:]
    output_json.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def route_transcript(transcript: str) -> dict[str, Any]:
    detection = detect_wake_command(transcript)
    command = detection.command.strip() if detection.woke else transcript.strip()
    if detection.woke and not command:
        command = "status"
    return {
        "woke": detection.woke,
        "wake_phrase": detection.phrase,
        "needs_followup": detection.needs_followup,
        "normalized": detection.normalized,
        "command": command or "status",
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
