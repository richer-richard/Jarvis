#!/usr/bin/env python3
"""Run Jarvis's no-prompt Apple Speech file transcription probe."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from voice_loop_qa import transcribe_with_local_stt


PROJECT_ROOT = Path(__file__).resolve().parents[1]
JARVIS_APP = PROJECT_ROOT / "output" / "Jarvis.app"
RUNTIME_ROOT = PROJECT_ROOT / "runtime" / "stt_apple_probe"
DEFAULT_TEXT = "Hey Jarvis, check my calendar."


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", default=DEFAULT_TEXT, help="Reference text to synthesize and transcribe.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Optional output directory under the project.")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--skip-local-compare", action="store_true", help="Skip local faster-whisper comparison.")
    args = parser.parse_args(argv)

    output_dir = args.output_dir or RUNTIME_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = output_dir if output_dir.is_absolute() else PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    report = run_probe(text=args.text, output_dir=output_dir, timeout=args.timeout, compare_local=not args.skip_local_compare)
    report_path = output_dir / "summary.json"
    report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    latest_path = RUNTIME_ROOT / "latest.json"
    latest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Report: {report_path}")
    print(f"Status: {report.get('status')}")
    print(f"Transcript: {report.get('transcript')!r}")
    return 0 if report.get("status") in {"completed", "not_authorized", "recognizer_unavailable"} else 1


def run_probe(*, text: str, output_dir: Path, timeout: float, compare_local: bool) -> dict[str, object]:
    started = time.monotonic()
    aiff_path = output_dir / "reference.aiff"
    wav_path = output_dir / "reference.wav"
    apple_json = output_dir / "apple-speech.json"
    report: dict[str, object] = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "tool": "voice.apple_speech_probe",
        "text": text,
        "recorded_audio": False,
        "requested_microphone_permission": False,
        "requested_speech_permission": False,
        "sent_audio": False,
        "installed_anything": False,
        "jarvis_app_path": str(JARVIS_APP),
        "audio_path": str(wav_path),
        "apple_output_path": str(apple_json),
        "local_compare_requested": compare_local,
    }
    if not JARVIS_APP.exists():
        return {**report, "status": "jarvis_app_missing", "duration_seconds": elapsed(started)}
    say_path = shutil.which("say") or "/usr/bin/say"
    ffmpeg_path = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    if not Path(ffmpeg_path).exists():
        return {**report, "status": "ffmpeg_missing", "duration_seconds": elapsed(started)}

    say = subprocess.run(
        [say_path, "-o", str(aiff_path), text],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if say.returncode != 0:
        return {
            **report,
            "status": "say_failed",
            "returncode": say.returncode,
            "stderr_tail": say.stderr[-500:],
            "stdout_tail": say.stdout[-500:],
            "duration_seconds": elapsed(started),
        }
    ffmpeg = subprocess.run(
        [ffmpeg_path, "-y", "-loglevel", "error", "-i", str(aiff_path), str(wav_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if ffmpeg.returncode != 0:
        return {
            **report,
            "status": "ffmpeg_failed",
            "returncode": ffmpeg.returncode,
            "stderr_tail": ffmpeg.stderr[-500:],
            "stdout_tail": ffmpeg.stdout[-500:],
            "duration_seconds": elapsed(started),
        }

    opened = subprocess.run(
        [
            "/usr/bin/open",
            "-n",
            "-W",
            str(JARVIS_APP),
            "--args",
            "--stt-file-self-test",
            str(wav_path),
            str(apple_json),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=max(10.0, timeout + 10.0),
        check=False,
    )
    if not apple_json.exists():
        return {
            **report,
            "status": "apple_output_missing",
            "open_returncode": opened.returncode,
            "stderr_tail": opened.stderr[-500:],
            "stdout_tail": opened.stdout[-500:],
            "duration_seconds": elapsed(started),
        }

    apple = json.loads(apple_json.read_text(encoding="utf-8"))
    transcript = str(apple.get("transcript") or "")
    result = {
        **report,
        "status": apple.get("status"),
        "authorized": apple.get("authorized"),
        "authorization": apple.get("authorization"),
        "authorization_not_requested": apple.get("authorization_not_requested", False),
        "transcript": transcript,
        "word_match": normalize(text) == normalize(transcript),
        "apple_duration_seconds": apple.get("duration_seconds"),
        "open_returncode": opened.returncode,
        "duration_seconds": elapsed(started),
    }
    if compare_local:
        local_json = output_dir / "local-faster-whisper.json"
        try:
            local = transcribe_with_local_stt(wav_path, local_json, timeout=timeout)
        except Exception as error:
            local = {
                "status": "local_compare_failed",
                "provider": "faster_whisper",
                "error": f"{type(error).__name__}: {error}",
                "transcript": "",
            }
            local_json.write_text(json.dumps(local, indent=2, ensure_ascii=False), encoding="utf-8")
        result["local_compare"] = {
            "path": str(local_json),
            "status": local.get("status"),
            "provider": local.get("provider"),
            "duration_seconds": local.get("duration_seconds"),
            "transcript": local.get("transcript"),
            "word_match": normalize(text) == normalize(str(local.get("transcript") or "")),
        }
    return result


def normalize(value: str) -> str:
    return " ".join(part.strip(".,!?;:").casefold() for part in str(value or "").split() if part.strip(".,!?;:"))


def elapsed(started: float) -> float:
    return round(time.monotonic() - started, 3)


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
