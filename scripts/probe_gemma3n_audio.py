#!/usr/bin/env python3
"""Probe Gemma 3n E4B audio transcription with synthetic Jarvis commands.

This script is dry-run by default. Use --execute-network only after the public
Hugging Face Gemma 3n E4B Space upload has been explicitly approved.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
import urllib.request
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.tools import _https_context  # noqa: E402


REPORT_ROOT = PROJECT_ROOT / "runtime" / "gemma3n_audio_probe"
DEFAULT_SPACE_BASE = "https://huggingface-projects-gemma-3n-e4b-it.hf.space"
DEFAULT_PROMPTS = [
    "Hey Jarvis, please set a timer for twenty two minutes and then summarize my newest email.",
    "Hey Jarvis, check my second email and summarize it.",
]


@dataclass
class SampleSpec:
    id: str
    provider: str
    voice: str
    prompt: str


@dataclass
class ProbeResult:
    sample_id: str
    provider: str
    voice: str
    reference: str
    audio_path: str
    status: str
    transcript: str
    first_token_seconds: float | None
    total_seconds: float | None
    word_accuracy: float
    word_error_rate: float
    substitutions: list[str]
    insertions: list[str]
    deletions: list[str]
    error: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space-base", default=DEFAULT_SPACE_BASE)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--skip-network", action="store_true", help="Compatibility alias; dry-run is already the default.")
    parser.add_argument("--execute-network", action="store_true", help="Upload generated audio to the configured Hugging Face Space.")
    parser.add_argument("--synthesize-local", action="store_true", help="Generate local audio files even when network upload is skipped.")
    parser.add_argument("--include-piper", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-samples", type=int, default=0, help="0 means all generated samples.")
    args = parser.parse_args()

    run_dir = REPORT_ROOT / time.strftime("%Y%m%d-%H%M%S")
    audio_dir = run_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    samples = build_samples(include_piper=args.include_piper)
    if args.max_samples > 0:
        samples = samples[: args.max_samples]

    results: list[ProbeResult] = []
    should_upload = bool(args.execute_network and not args.skip_network)
    should_synthesize = bool(should_upload or args.synthesize_local)
    for sample in samples:
        audio_path = audio_dir / f"{sample.id}.wav"
        try:
            if not should_synthesize:
                results.append(
                    ProbeResult(
                        sample_id=sample.id,
                        provider=sample.provider,
                        voice=sample.voice,
                        reference=sample.prompt,
                        audio_path=str(audio_path),
                        status="planned_dry_run",
                        transcript="",
                        first_token_seconds=None,
                        total_seconds=None,
                        word_accuracy=0.0,
                        word_error_rate=1.0,
                        substitutions=[],
                        insertions=[],
                        deletions=normalize_words(sample.prompt),
                    )
                )
                continue
            synthesize_sample(sample, audio_path)
            if not should_upload:
                results.append(
                    ProbeResult(
                        sample_id=sample.id,
                        provider=sample.provider,
                        voice=sample.voice,
                        reference=sample.prompt,
                        audio_path=str(audio_path),
                        status="skipped_network",
                        transcript="",
                        first_token_seconds=None,
                        total_seconds=None,
                        word_accuracy=0.0,
                        word_error_rate=1.0,
                        substitutions=[],
                        insertions=[],
                        deletions=normalize_words(sample.prompt),
                    )
                )
                continue
            transcript, timing = transcribe_with_space(
                audio_path,
                prompt="Transcribe this speech segment exactly in English. Return only the transcript, no commentary.",
                space_base=args.space_base,
                timeout=args.timeout,
            )
            score = score_transcript(sample.prompt, transcript)
            results.append(
                ProbeResult(
                    sample_id=sample.id,
                    provider=sample.provider,
                    voice=sample.voice,
                    reference=sample.prompt,
                    audio_path=str(audio_path),
                    status="completed",
                    transcript=transcript,
                    first_token_seconds=timing.get("first_token_seconds"),
                    total_seconds=timing.get("total_seconds"),
                    word_accuracy=score["word_accuracy"],
                    word_error_rate=score["word_error_rate"],
                    substitutions=score["substitutions"],
                    insertions=score["insertions"],
                    deletions=score["deletions"],
                )
            )
        except Exception as error:  # noqa: BLE001 - report every candidate instead of aborting the run.
            results.append(
                ProbeResult(
                    sample_id=sample.id,
                    provider=sample.provider,
                    voice=sample.voice,
                    reference=sample.prompt,
                    audio_path=str(audio_path),
                    status="failed",
                    transcript="",
                    first_token_seconds=None,
                    total_seconds=None,
                    word_accuracy=0.0,
                    word_error_rate=1.0,
                    substitutions=[],
                    insertions=[],
                    deletions=[],
                    error=f"{type(error).__name__}: {error}"[-1000:],
                )
            )

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "model": "gemma-3n-E4B-it",
        "provider": "huggingface_space",
        "space_base": args.space_base,
        "local_gemma_inference": False,
        "uploaded_audio": should_upload,
        "local_audio_generated": should_synthesize,
        "sample_count": len(samples),
        "results": [asdict(result) for result in results],
        "summary": summarize(results),
    }
    json_path = run_dir / "report.json"
    md_path = run_dir / "report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"Gemma 3n audio probe complete: {len(results)} samples")
    print(f"JSON: {json_path}")
    print(f"Report: {md_path}")
    for result in results:
        print(
            f"- {result.sample_id}: {result.status}, "
            f"accuracy={result.word_accuracy:.3f}, first={result.first_token_seconds}, "
            f"total={result.total_seconds}, transcript={result.transcript!r}"
        )
    return 0


def build_samples(*, include_piper: bool) -> list[SampleSpec]:
    samples: list[SampleSpec] = []
    voices = [
        ("say_daniel", "macos-say", "Daniel"),
        ("say_samantha", "macos-say", "Samantha"),
        ("say_moira", "macos-say", "Moira"),
    ]
    for prompt_index, prompt in enumerate(DEFAULT_PROMPTS, 1):
        for voice_id, provider, voice in voices:
            samples.append(SampleSpec(f"{voice_id}_p{prompt_index}", provider, voice, prompt))
        if include_piper and piper_available():
            samples.append(SampleSpec(f"piper_ryan_p{prompt_index}", "piper", "en_US-ryan-high", prompt))
    return samples


def synthesize_sample(sample: SampleSpec, output_wav: Path) -> None:
    if sample.provider == "macos-say":
        synthesize_with_say(sample.prompt, output_wav, voice=sample.voice)
        return
    if sample.provider == "piper":
        synthesize_with_piper(sample.prompt, output_wav)
        return
    raise ValueError(f"Unsupported provider: {sample.provider}")


def synthesize_with_say(text: str, output_wav: Path, *, voice: str) -> None:
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    aiff_path = output_wav.with_suffix(".aiff")
    command = ["/usr/bin/say", "-o", str(aiff_path)]
    if voice != "system default":
        command.extend(["-v", voice])
    command.append(text)
    completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "say failed")
    convert_to_wav(aiff_path, output_wav)
    aiff_path.unlink(missing_ok=True)


def synthesize_with_piper(text: str, output_wav: Path) -> None:
    voice_loop_path = PROJECT_ROOT / "scripts" / "voice_loop_qa.py"
    spec = importlib.util.spec_from_file_location("jarvis_voice_loop_qa", voice_loop_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load voice_loop_qa.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.synthesize_with_piper(text, output_wav, length_scale=0.85)
    converted = output_wav.with_name(f"{output_wav.stem}.converted.wav")
    convert_to_wav(output_wav, converted)
    converted.replace(output_wav)


def piper_available() -> bool:
    return (
        (PROJECT_ROOT / "runtime" / "tts_models" / "piper" / ".venv" / "bin" / "python").exists()
        and (PROJECT_ROOT / "runtime" / "tts_models" / "piper" / "en_US-ryan-high.onnx").exists()
        and (PROJECT_ROOT / "runtime" / "tts_models" / "piper" / "en_US-ryan-high.onnx.json").exists()
    )


def convert_to_wav(source: Path, output_wav: Path) -> None:
    completed = subprocess.run(
        ["/usr/bin/afconvert", "-f", "WAVE", "-d", "LEI16@16000", str(source), str(output_wav)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "afconvert failed")


def transcribe_with_space(audio_path: Path, *, prompt: str, space_base: str, timeout: float) -> tuple[str, dict[str, float]]:
    uploaded_path = upload_file(audio_path, space_base=space_base, timeout=timeout)
    payload = {
        "data": [
            {
                "text": prompt,
                "files": [
                    {
                        "path": uploaded_path,
                        "orig_name": audio_path.name,
                        "mime_type": mimetypes.guess_type(audio_path.name)[0] or "audio/wav",
                        "meta": {"_type": "gradio.FileData"},
                    }
                ],
            },
            [],
            "You are a careful speech transcription engine. Return only the words you hear.",
            200,
        ],
        "fn_index": 7,
    }
    event_id = submit_gradio_call(f"{space_base.rstrip('/')}/gradio_api/call/generate", payload, timeout=timeout)
    return read_gradio_events(f"{space_base.rstrip('/')}/gradio_api/call/generate/{event_id}", timeout=timeout)


def upload_file(audio_path: Path, *, space_base: str, timeout: float) -> str:
    boundary = f"----JarvisGemma3n{uuid.uuid4().hex}"
    data = audio_path.read_bytes()
    mime_type = mimetypes.guess_type(audio_path.name)[0] or "audio/wav"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="files"; filename="{audio_path.name}"\r\n'.encode("utf-8"),
            f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"),
            data,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    request = urllib.request.Request(
        f"{space_base.rstrip('/')}/gradio_api/upload",
        data=body,
        headers={**hf_headers(), "Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout, context=_https_context()) as response:
        uploaded = json.loads(response.read().decode("utf-8", errors="replace"))
    if not uploaded or not isinstance(uploaded, list):
        raise RuntimeError(f"Unexpected upload response: {uploaded!r}")
    return str(uploaded[0])


def submit_gradio_call(url: str, payload: dict[str, Any], *, timeout: float) -> str:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**hf_headers(), "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout, context=_https_context()) as response:
        data = json.loads(response.read().decode("utf-8", errors="replace"))
    event_id = str(data.get("event_id") or "").strip()
    if not event_id:
        raise RuntimeError(f"Missing Gradio event_id: {data!r}")
    return event_id


def read_gradio_events(url: str, *, timeout: float) -> tuple[str, dict[str, float]]:
    started = time.monotonic()
    first_token_at: float | None = None
    latest = ""
    event_name = ""
    request = urllib.request.Request(url, headers={**hf_headers(), "Accept": "text/event-stream"})
    with urllib.request.urlopen(request, timeout=timeout, context=_https_context()) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if line.startswith("event: "):
                event_name = line[7:].strip()
                continue
            if not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if event_name == "error":
                if isinstance(data, dict):
                    raise RuntimeError(str(data.get("error") or data.get("title") or data)[:1000])
                raise RuntimeError(str(data)[:1000])
            if isinstance(data, list) and data:
                text = str(data[0] or "")
                if text and first_token_at is None:
                    first_token_at = time.monotonic()
                if text:
                    latest = text
    total = time.monotonic() - started
    return latest.strip(), {
        "first_token_seconds": round(first_token_at - started, 3) if first_token_at is not None else None,
        "total_seconds": round(total, 3),
    }


def hf_headers() -> dict[str, str]:
    token = (
        os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGINGFACEHUB_API_TOKEN")
        or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        or ""
    ).strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def score_transcript(reference: str, transcript: str) -> dict[str, Any]:
    ref_words = normalize_words(reference)
    hyp_words = normalize_words(transcript)
    distance, substitutions, insertions, deletions = edit_details(ref_words, hyp_words)
    total = max(1, len(ref_words))
    wer = distance / total
    return {
        "word_accuracy": round(max(0.0, 1.0 - wer), 3),
        "word_error_rate": round(wer, 3),
        "substitutions": substitutions,
        "insertions": insertions,
        "deletions": deletions,
    }


def normalize_words(text: str) -> list[str]:
    text = text.lower().replace("twenty two", "22").replace("twenty-two", "22")
    return re.findall(r"[a-z0-9]+", text)


def edit_details(reference: list[str], hypothesis: list[str]) -> tuple[int, list[str], list[str], list[str]]:
    rows = len(reference) + 1
    cols = len(hypothesis) + 1
    dp = [[0] * cols for _ in range(rows)]
    back = [[""] * cols for _ in range(rows)]
    for i in range(1, rows):
        dp[i][0] = i
        back[i][0] = "delete"
    for j in range(1, cols):
        dp[0][j] = j
        back[0][j] = "insert"
    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if reference[i - 1] == hypothesis[j - 1] else 1
            choices = [
                (dp[i - 1][j - 1] + cost, "match" if cost == 0 else "substitute"),
                (dp[i - 1][j] + 1, "delete"),
                (dp[i][j - 1] + 1, "insert"),
            ]
            dp[i][j], back[i][j] = min(choices, key=lambda item: item[0])
    substitutions: list[str] = []
    insertions: list[str] = []
    deletions: list[str] = []
    i = len(reference)
    j = len(hypothesis)
    while i or j:
        action = back[i][j]
        if action == "match":
            i -= 1
            j -= 1
        elif action == "substitute":
            substitutions.append(f"{reference[i - 1]} -> {hypothesis[j - 1]}")
            i -= 1
            j -= 1
        elif action == "delete":
            deletions.append(reference[i - 1])
            i -= 1
        elif action == "insert":
            insertions.append(hypothesis[j - 1])
            j -= 1
        else:
            break
    substitutions.reverse()
    insertions.reverse()
    deletions.reverse()
    return dp[-1][-1], substitutions, insertions, deletions


def summarize(results: list[ProbeResult]) -> dict[str, Any]:
    completed = [result for result in results if result.status == "completed"]
    if not completed:
        return {"status": "no_completed_samples"}
    return {
        "status": "completed",
        "average_word_accuracy": round(sum(result.word_accuracy for result in completed) / len(completed), 3),
        "best_sample": max(completed, key=lambda result: result.word_accuracy).sample_id,
        "worst_sample": min(completed, key=lambda result: result.word_accuracy).sample_id,
        "average_first_token_seconds": round(
            sum(result.first_token_seconds or 0 for result in completed if result.first_token_seconds is not None)
            / max(1, sum(1 for result in completed if result.first_token_seconds is not None)),
            3,
        ),
        "average_total_seconds": round(
            sum(result.total_seconds or 0 for result in completed if result.total_seconds is not None)
            / max(1, sum(1 for result in completed if result.total_seconds is not None)),
            3,
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Gemma 3n Audio Probe",
        "",
        f"Generated: {report['generated_at']}",
        f"Model: `{report['model']}` via Hugging Face Space",
        f"Local Gemma inference: `{report['local_gemma_inference']}`",
        f"Uploaded generated audio: `{report['uploaded_audio']}`",
        f"Local audio generated: `{report.get('local_audio_generated', False)}`",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Results",
            "",
            "| Sample | Voice | Accuracy | First Token | Total | Transcript | Errors |",
            "|---|---|---:|---:|---:|---|---|",
        ]
    )
    for result in report["results"]:
        errors = "; ".join((result.get("substitutions") or []) + (result.get("insertions") or []) + (result.get("deletions") or []))
        transcript = str(result.get("transcript") or result.get("error") or "").replace("|", "\\|").replace("\n", " ")[:220]
        lines.append(
            f"| `{result['sample_id']}` | {result['voice']} | {result['word_accuracy']:.3f} | "
            f"{result.get('first_token_seconds') or ''} | {result.get('total_seconds') or ''} | "
            f"{transcript} | {errors[:180]} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
