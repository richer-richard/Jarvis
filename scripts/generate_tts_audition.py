#!/usr/bin/env python3
"""Generate a numbered Jarvis TTS audition set and ranking page."""

from __future__ import annotations

import argparse
import html
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "runtime" / "tts_voice_audition"
DEFAULT_SAMPLE_TEXT = (
    "Good evening, Leo. I've checked your email: there's a short form about the "
    "charity sale that may need your attention. I'll keep it brief unless you ask for more."
)
SEED = "jarvis-tts-audition-2026-06-05"
EDGE_CA_CERT = Path("/opt/homebrew/Cellar/ca-certificates/2025-05-20/share/ca-certificates/cacert.pem")


@dataclass(frozen=True)
class Candidate:
    provider: str
    voice: str
    label: str
    accent: str
    style: str
    rate: int = 152
    edge_rate: str = "+0%"
    edge_pitch: str = "+0Hz"
    priority: int = 0


MACOS_CANDIDATES = [
    Candidate("macos_say", "Daniel", "macOS Daniel", "English UK", "classic male system voice", priority=90),
    Candidate("macos_say", "Eddy (English (UK))", "macOS Eddy UK", "English UK", "newer Apple voice", priority=92),
    Candidate("macos_say", "Reed (English (UK))", "macOS Reed UK", "English UK", "newer Apple voice", priority=91),
    Candidate("macos_say", "Rocko (English (UK))", "macOS Rocko UK", "English UK", "newer Apple voice", priority=86),
    Candidate("macos_say", "Sandy (English (UK))", "macOS Sandy UK", "English UK", "newer Apple voice", priority=86),
    Candidate("macos_say", "Shelley (English (UK))", "macOS Shelley UK", "English UK", "newer Apple voice", priority=84),
    Candidate("macos_say", "Flo (English (UK))", "macOS Flo UK", "English UK", "newer Apple voice", priority=82),
    Candidate("macos_say", "Grandpa (English (UK))", "macOS Grandpa UK", "English UK", "character voice", priority=70),
    Candidate("macos_say", "Grandma (English (UK))", "macOS Grandma UK", "English UK", "character voice", priority=68),
    Candidate("macos_say", "Samantha", "macOS Samantha", "English US", "natural Apple voice", priority=88),
    Candidate("macos_say", "Moira", "macOS Moira", "English Ireland", "clear system voice", priority=82),
    Candidate("macos_say", "Karen", "macOS Karen", "English Australia", "clear system voice", priority=78),
    Candidate("macos_say", "Tessa", "macOS Tessa", "English South Africa", "clear system voice", priority=76),
    Candidate("macos_say", "Aman", "macOS Aman", "English India", "clear system voice", priority=72),
    Candidate("macos_say", "Rishi", "macOS Rishi", "English India", "clear system voice", priority=72),
    Candidate("macos_say", "Albert", "macOS Albert", "English US", "older male system voice", priority=55),
    Candidate("macos_say", "Fred", "macOS Fred", "English US", "older male system voice", priority=54),
    Candidate("macos_say", "Ralph", "macOS Ralph", "English US", "older male system voice", priority=50),
    Candidate("macos_say", "Kathy", "macOS Kathy", "English US", "older female system voice", priority=50),
]


EDGE_CANDIDATES = [
    Candidate("edge_tts", "en-GB-ThomasNeural", "Edge Thomas Neural", "English UK", "male general neural", priority=100),
    Candidate("edge_tts", "en-GB-RyanNeural", "Edge Ryan Neural", "English UK", "male general neural", priority=99),
    Candidate("edge_tts", "en-GB-SoniaNeural", "Edge Sonia Neural", "English UK", "female general neural", priority=96),
    Candidate("edge_tts", "en-GB-LibbyNeural", "Edge Libby Neural", "English UK", "female general neural", priority=94),
    Candidate("edge_tts", "en-GB-MaisieNeural", "Edge Maisie Neural", "English UK", "female general neural", priority=88),
    Candidate("edge_tts", "en-IE-ConnorNeural", "Edge Connor Neural", "English Ireland", "male general neural", priority=90),
    Candidate("edge_tts", "en-IE-EmilyNeural", "Edge Emily Neural", "English Ireland", "female general neural", priority=86),
    Candidate("edge_tts", "en-AU-WilliamMultilingualNeural", "Edge William Multilingual", "English Australia", "male multilingual neural", priority=84),
    Candidate("edge_tts", "en-AU-NatashaNeural", "Edge Natasha Neural", "English Australia", "female general neural", priority=78),
    Candidate("edge_tts", "en-CA-LiamNeural", "Edge Liam Neural", "English Canada", "male general neural", priority=78),
    Candidate("edge_tts", "en-CA-ClaraNeural", "Edge Clara Neural", "English Canada", "female general neural", priority=74),
    Candidate("edge_tts", "en-ZA-LukeNeural", "Edge Luke Neural", "English South Africa", "male general neural", priority=76),
    Candidate("edge_tts", "en-ZA-LeahNeural", "Edge Leah Neural", "English South Africa", "female general neural", priority=72),
    Candidate("edge_tts", "en-US-AndrewMultilingualNeural", "Edge Andrew Multilingual", "English US", "warm confident conversational", priority=90),
    Candidate("edge_tts", "en-US-AndrewNeural", "Edge Andrew Neural", "English US", "warm confident conversational", priority=88),
    Candidate("edge_tts", "en-US-BrianMultilingualNeural", "Edge Brian Multilingual", "English US", "approachable conversational", priority=84),
    Candidate("edge_tts", "en-US-BrianNeural", "Edge Brian Neural", "English US", "approachable conversational", priority=82),
    Candidate("edge_tts", "en-US-AvaMultilingualNeural", "Edge Ava Multilingual", "English US", "expressive conversational", priority=78),
    Candidate("edge_tts", "en-US-EmmaMultilingualNeural", "Edge Emma Multilingual", "English US", "clear conversational", priority=76),
    Candidate("edge_tts", "en-US-ChristopherNeural", "Edge Christopher Neural", "English US", "authoritative news/novel", priority=74),
    Candidate("edge_tts", "en-US-SteffanNeural", "Edge Steffan Neural", "English US", "rational news/novel", priority=72),
    Candidate("edge_tts", "en-US-RogerNeural", "Edge Roger Neural", "English US", "lively news/novel", priority=68),
]


def run(command: list[str], *, timeout: int, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env=env,
        check=False,
    )


def available_macos_voice_names() -> set[str]:
    say = shutil.which("say")
    if not say:
        return set()
    completed = run([say, "-v", "?"], timeout=8)
    if completed.returncode != 0:
        return set()
    names: set[str] = set()
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        marker = "  "
        if marker in line:
            names.add(line.split(marker, 1)[0].strip())
    return names


def edge_command(output_dir: Path) -> Path | None:
    local = output_dir / ".venv" / "bin" / "edge-tts"
    if local.exists():
        return local
    found = shutil.which("edge-tts")
    return Path(found) if found else None


def candidate_pool(
    output_dir: Path,
    max_samples: int | None,
    *,
    include_online_voices: bool = False,
) -> tuple[list[Candidate], list[dict[str, Any]]]:
    unavailable: list[dict[str, Any]] = []
    macos_names = available_macos_voice_names()
    candidates: list[Candidate] = []
    if macos_names:
        for candidate in MACOS_CANDIDATES:
            if candidate.voice in macos_names:
                candidates.append(candidate)
            else:
                unavailable.append({"provider": candidate.provider, "voice": candidate.voice, "reason": "macOS voice is not installed"})
    else:
        unavailable.append({"provider": "macos_say", "voice": "*", "reason": "macOS say is unavailable or did not list voices"})

    if not include_online_voices:
        for candidate in EDGE_CANDIDATES:
            unavailable.append({"provider": candidate.provider, "voice": candidate.voice, "reason": "online voices require --include-online-voices"})
    elif edge_command(output_dir):
        candidates.extend(EDGE_CANDIDATES)
    else:
        for candidate in EDGE_CANDIDATES:
            unavailable.append({"provider": candidate.provider, "voice": candidate.voice, "reason": "edge-tts command is unavailable"})

    ranked = sorted(candidates, key=lambda item: (-item.priority, item.provider, item.voice))
    if max_samples is not None:
        ranked = ranked[:max_samples]

    rng = random.Random(SEED)
    rng.shuffle(ranked)
    return ranked, unavailable


def convert_to_mp3(source: Path, target: Path) -> tuple[bool, str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False, "ffmpeg is not available"
    completed = run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-codec:a", "libmp3lame", "-q:a", "2", str(target)], timeout=30)
    if completed.returncode != 0:
        return False, completed.stderr.strip() or "ffmpeg conversion failed"
    return True, ""


def generate_macos(candidate: Candidate, text: str, target: Path) -> tuple[bool, str]:
    say = shutil.which("say")
    if not say:
        return False, "macOS say is unavailable"
    with tempfile.TemporaryDirectory(prefix="jarvis-tts-") as tmp_name:
        tmp = Path(tmp_name) / "sample.aiff"
        completed = run([say, "-v", candidate.voice, "-r", str(candidate.rate), "-o", str(tmp), text], timeout=30)
        if completed.returncode != 0:
            return False, completed.stderr.strip() or "say failed"
        return convert_to_mp3(tmp, target)


def edge_env(output_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    venv_cert = output_dir / ".venv" / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages" / "certifi" / "cacert.pem"
    if venv_cert.exists():
        env.setdefault("SSL_CERT_FILE", str(venv_cert))
    elif EDGE_CA_CERT.exists():
        env.setdefault("SSL_CERT_FILE", str(EDGE_CA_CERT))
    return env


def generate_edge(candidate: Candidate, text: str, target: Path, output_dir: Path) -> tuple[bool, str]:
    command = edge_command(output_dir)
    if not command:
        return False, "edge-tts command is unavailable"
    errors: list[str] = []
    for attempt in range(1, 4):
        completed = run(
            [
                str(command),
                "--voice",
                candidate.voice,
                "--rate",
                candidate.edge_rate,
                "--pitch",
                candidate.edge_pitch,
                "--text",
                text,
                "--write-media",
                str(target),
            ],
            timeout=45,
            env=edge_env(output_dir),
        )
        if completed.returncode == 0 and target.exists() and target.stat().st_size > 1000:
            return True, ""
        errors.append((completed.stderr or completed.stdout or f"attempt {attempt} failed").strip())
        time.sleep(1.5)
    return False, errors[-1] if errors else "edge-tts failed"


def probe_duration(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    completed = run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        timeout=8,
    )
    if completed.returncode != 0:
        return None
    try:
        return round(float(completed.stdout.strip()), 3)
    except ValueError:
        return None


def friendly_accent(accent: str) -> str:
    return {
        "English UK": "British",
        "English US": "American",
        "English Ireland": "Irish",
        "English Australia": "Australian",
        "English Canada": "Canadian",
        "English South Africa": "South African",
        "English India": "Indian",
    }.get(accent, accent.replace("English ", ""))


def candidate_base_name(candidate: Candidate) -> str:
    label = candidate.label
    for prefix in ("Edge ", "macOS "):
        if label.startswith(prefix):
            label = label[len(prefix) :]
    for suffix in (" Neural", " UK"):
        if label.endswith(suffix):
            label = label[: -len(suffix)]
    return label.strip()


def candidate_gender(candidate: Candidate) -> str:
    style = candidate.style.lower()
    if "female" in style:
        return "female"
    if "male" in style:
        return "male"
    base_names = {candidate.voice.split(" (", 1)[0], candidate_base_name(candidate).split()[0]}
    female_names = {
        "Ava",
        "Clara",
        "Emily",
        "Emma",
        "Flo",
        "Grandma",
        "Karen",
        "Kathy",
        "Leah",
        "Libby",
        "Maisie",
        "Moira",
        "Natasha",
        "Samantha",
        "Sandy",
        "Shelley",
        "Sonia",
        "Tessa",
    }
    male_names = {
        "Albert",
        "Aman",
        "Andrew",
        "Brian",
        "Christopher",
        "Connor",
        "Daniel",
        "Eddy",
        "Fred",
        "Grandpa",
        "Liam",
        "Luke",
        "Ralph",
        "Reed",
        "Rishi",
        "Rocko",
        "Roger",
        "Ryan",
        "Steffan",
        "Thomas",
        "William",
    }
    if base_names & female_names:
        return "female"
    if base_names & male_names:
        return "male"
    return "voice"


def candidate_style_modifier(candidate: Candidate) -> str:
    style = candidate.style.lower()
    if "older" in style:
        return "older"
    if "classic" in style:
        return "classic"
    if "newer" in style:
        return "modern"
    if "character" in style:
        return "character"
    if "natural" in style:
        return "natural"
    if "warm" in style:
        return "warm"
    if "approachable" in style:
        return "approachable"
    if "expressive" in style:
        return "expressive"
    if "authoritative" in style:
        return "authoritative"
    if "lively" in style:
        return "lively"
    if "rational" in style:
        return "calm"
    if "clear" in style:
        return "clear"
    if "neural" in style or candidate.provider == "edge_tts":
        return "neural"
    return ""


def short_name_for_candidate(candidate: Candidate) -> str:
    parts = [
        candidate_base_name(candidate),
        candidate_style_modifier(candidate),
        friendly_accent(candidate.accent),
        candidate_gender(candidate),
    ]
    return " ".join(part for part in parts if part).strip()


def html_page(samples: list[dict[str, Any]], sample_text: str, generated_at: str) -> str:
    samples_json = json.dumps(samples, ensure_ascii=False, indent=2)
    escaped_sentence = html.escape(sample_text)
    escaped_generated_at = html.escape(generated_at)
    html_doc = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>Jarvis Voice Audition</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f6f8;
      --panel: #ffffff;
      --ink: #181b20;
      --muted: #69707d;
      --line: #d9dde5;
      --red: #a4162a;
      --red-dark: #74101d;
      --gold: #c8942e;
      --blue: #1f5f8f;
      --selected: #e7ebf2;
      --selected-line: #9ba6b8;
      --shadow: 0 18px 45px rgba(21, 25, 33, 0.10);
    }
    * {
      box-sizing: border-box;
    }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 15px;
      letter-spacing: 0;
    }
    main {
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
      padding: 24px 0 44px;
    }
    header {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 20px;
      align-items: end;
      padding: 18px 0 20px;
      border-bottom: 1px solid var(--line);
    }
    h1 {
      margin: 0 0 8px;
      font-size: 28px;
      line-height: 1.15;
      font-weight: 760;
    }
    .sentence {
      margin: 0;
      max-width: 780px;
      color: var(--muted);
      line-height: 1.55;
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }
    button {
      appearance: none;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
      min-height: 38px;
      padding: 0 12px;
      border-radius: 7px;
      font: inherit;
      font-weight: 650;
      cursor: pointer;
      transition: border-color 140ms ease, background 140ms ease, color 140ms ease, transform 140ms ease;
      white-space: nowrap;
    }
    button:hover {
      border-color: #aeb5c2;
      transform: translateY(-1px);
    }
    button.primary {
      background: var(--red);
      border-color: var(--red);
      color: white;
    }
    button.primary:hover {
      background: var(--red-dark);
      border-color: var(--red-dark);
    }
    button.gold {
      border-color: rgba(200, 148, 46, 0.55);
      color: #594019;
      background: #fff8e8;
    }
    .status {
      min-height: 22px;
      margin: 14px 0 16px;
      color: var(--blue);
      font-weight: 650;
    }
    .list {
      display: grid;
      gap: 10px;
    }
    .row {
      display: grid;
      grid-template-columns: 48px 78px 86px minmax(220px, 1fr) 270px 126px;
      gap: 12px;
      align-items: center;
      min-height: 86px;
      padding: 11px 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 1px 0 rgba(255, 255, 255, 0.85);
      transition: border-color 160ms ease, background 160ms ease, box-shadow 180ms ease, opacity 160ms ease;
      will-change: transform;
    }
    .row:hover {
      border-color: #b9c0cd;
    }
    .row.selected {
      background: var(--selected);
      border-color: var(--selected-line);
      box-shadow: 0 13px 32px rgba(31, 43, 62, 0.16);
    }
    .row.dirty {
      border-color: rgba(200, 148, 46, 0.72);
      box-shadow: 0 10px 28px rgba(200, 148, 46, 0.14);
    }
    .row.dragging {
      cursor: grabbing;
      opacity: 0.88;
      position: relative;
      z-index: 5;
      box-shadow: 0 24px 56px rgba(21, 25, 33, 0.24);
    }
    .row.animating {
      transition: transform 230ms cubic-bezier(0.2, 0.8, 0.2, 1), border-color 160ms ease, background 160ms ease, box-shadow 180ms ease;
    }
    .drag-ghost {
      position: fixed;
      top: -1000px;
      left: -1000px;
      pointer-events: none;
      box-shadow: 0 24px 56px rgba(21, 25, 33, 0.26);
      opacity: 0.92;
    }
    .rank {
      width: 34px;
      height: 34px;
      display: grid;
      place-items: center;
      border-radius: 7px;
      background: #eef1f5;
      color: #49515f;
      font-weight: 760;
      font-variant-numeric: tabular-nums;
    }
    .sample-number {
      display: grid;
      place-items: center;
      min-width: 56px;
      height: 36px;
      border-radius: 7px;
      background: #181b20;
      color: white;
      font-size: 18px;
      font-weight: 800;
      font-variant-numeric: tabular-nums;
    }
    .identity {
      min-width: 0;
    }
    .identity strong {
      display: block;
      font-size: 16px;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }
    .meta {
      display: none;
      margin-top: 3px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.35;
      overflow-wrap: anywhere;
    }
    body.show-details .meta {
      display: block;
    }
    .score-box {
      display: grid;
      gap: 7px;
      min-width: 0;
    }
    .score-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 760;
      text-transform: uppercase;
    }
    .score-value {
      color: var(--ink);
      font-variant-numeric: tabular-nums;
    }
    .score-control {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 74px;
      gap: 8px;
      align-items: center;
    }
    .score-slider {
      width: 100%;
      accent-color: var(--red);
    }
    .confirm-score {
      min-height: 32px;
      padding: 0 8px;
      font-size: 13px;
    }
    .confirm-score:disabled {
      cursor: default;
      opacity: 0.48;
      transform: none;
    }
    .moves {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
    }
    .moves button {
      min-height: 34px;
      padding: 0 8px;
    }
    audio {
      display: none;
    }
    footer {
      margin-top: 18px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }
    @media (max-width: 960px) {
      main {
        width: min(100% - 20px, 760px);
        padding-top: 12px;
      }
      header {
        grid-template-columns: 1fr;
        align-items: start;
      }
      .toolbar {
        justify-content: flex-start;
      }
      .row {
        grid-template-columns: 42px 68px 78px 1fr;
      }
      .score-box,
      .moves {
        grid-column: 1 / -1;
      }
      .moves {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }
    @media (max-width: 560px) {
      .row {
        grid-template-columns: 42px 68px 1fr;
      }
      .row > button {
        grid-column: 1 / 3;
      }
      .identity {
        grid-column: 3;
      }
      .score-box,
      .moves {
        grid-column: 1 / -1;
      }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Jarvis Voice Audition</h1>
        <p class="sentence">__SENTENCE__</p>
      </div>
      <div class="toolbar">
        <button class="primary" id="copy-json">Copy JSON</button>
        <button id="copy-text">Copy Text</button>
        <button id="toggle-details">Show Details</button>
        <button class="gold" id="reset-order">Reset</button>
        <button id="stop-audio">Stop</button>
      </div>
    </header>
    <div class="status" id="status"></div>
    <section class="list" id="list" aria-label="Voice sample ranking"></section>
    <footer>__SAMPLE_COUNT__ samples generated at __GENERATED_AT__. Drag samples or score them from 1 to 10. The visible number is still the quickest thing to rank.</footer>
  </main>
  <script>
    const samples = __SAMPLES_JSON__;
    const sampleText = __SAMPLE_TEXT_JSON__;
    const generatedAt = __GENERATED_AT_JSON__;
    const storageKey = "jarvis-voice-audition:" + generatedAt + ":" + samples.length;
    const list = document.getElementById("list");
    const status = document.getElementById("status");
    const sampleByNumber = new Map(samples.map(sample => [sample.number, sample]));
    const knownNumbers = samples.map(sample => sample.number);
    let currentAudio = null;
    let currentPlayButton = null;
    let dragStartOrder = [];
    const state = loadState();

    function clampScore(value) {
      const number = Number(value);
      if (!Number.isFinite(number)) return 1;
      return Math.min(10, Math.max(1, Math.round(number * 1000) / 1000));
    }

    function scoreText(value) {
      return clampScore(value).toFixed(3);
    }

    function defaultScoreForIndex(index) {
      if (samples.length <= 1) return 10;
      return clampScore(10 - (index * 9) / (samples.length - 1));
    }

    function normalizeOrder(order) {
      const known = new Set(knownNumbers);
      const seen = new Set();
      const normalized = [];
      if (Array.isArray(order)) {
        for (const rawNumber of order) {
          const number = Number(rawNumber);
          if (known.has(number) && !seen.has(number)) {
            normalized.push(number);
            seen.add(number);
          }
        }
      }
      for (const number of knownNumbers) {
        if (!seen.has(number)) normalized.push(number);
      }
      return normalized;
    }

    function scoresFromOrder(order) {
      const scores = {};
      normalizeOrder(order).forEach((number, index) => {
        scores[number] = defaultScoreForIndex(index);
      });
      return scores;
    }

    function sanitizeScores(rawScores, fallbackOrder) {
      const fallback = scoresFromOrder(fallbackOrder);
      const scores = {};
      for (const number of knownNumbers) {
        const raw = rawScores && Object.prototype.hasOwnProperty.call(rawScores, number) ? rawScores[number] : rawScores && rawScores[String(number)];
        scores[number] = Number.isFinite(Number(raw)) ? clampScore(raw) : fallback[number];
      }
      return scores;
    }

    function loadState() {
      try {
        const parsed = JSON.parse(localStorage.getItem(storageKey) || "null");
        if (Array.isArray(parsed)) {
          const order = normalizeOrder(parsed);
          return { scores: scoresFromOrder(order), tieOrder: order, selectedNumber: null };
        }
        if (parsed && typeof parsed === "object") {
          const order = normalizeOrder(parsed.tieOrder || parsed.order);
          return {
            scores: sanitizeScores(parsed.scores, order),
            tieOrder: order,
            selectedNumber: null
          };
        }
      } catch {
      }
      const order = normalizeOrder(knownNumbers);
      return { scores: scoresFromOrder(order), tieOrder: order, selectedNumber: null };
    }

    function saveState() {
      localStorage.setItem(storageKey, JSON.stringify({
        scores: state.scores,
        tieOrder: state.tieOrder,
        sample_text: sampleText,
        generated_at: generatedAt
      }));
    }

    function scoreFor(number) {
      return clampScore(state.scores[number]);
    }

    function tieIndexMap() {
      return new Map(state.tieOrder.map((number, index) => [number, index]));
    }

    function sortedNumbers() {
      const tieIndexes = tieIndexMap();
      return knownNumbers.slice().sort((left, right) => {
        const scoreDelta = scoreFor(right) - scoreFor(left);
        if (Math.abs(scoreDelta) > 0.0005) return scoreDelta;
        return (tieIndexes.get(left) ?? left) - (tieIndexes.get(right) ?? right);
      });
    }

    function orderedSamples() {
      return sortedNumbers().map(number => sampleByNumber.get(number)).filter(Boolean);
    }

    function currentNumbers() {
      const rows = [...list.querySelectorAll(".row")];
      return rows.length ? rows.map(row => Number(row.dataset.number)) : sortedNumbers();
    }

    function setStatus(message) {
      status.textContent = message;
      if (message) setTimeout(() => {
        if (status.textContent === message) status.textContent = "";
      }, 1800);
    }

    function selectNumber(number) {
      state.selectedNumber = number;
      refreshSelection();
    }

    function refreshSelection() {
      [...list.querySelectorAll(".row")].forEach(row => {
        row.classList.toggle("selected", Number(row.dataset.number) === state.selectedNumber);
      });
    }

    function stopAudio() {
      if (currentAudio) {
        currentAudio.pause();
        currentAudio.currentTime = 0;
        currentAudio = null;
      }
      if (currentPlayButton) {
        currentPlayButton.textContent = "Play";
        currentPlayButton = null;
      }
    }

    function playSample(sample, button) {
      selectNumber(sample.number);
      stopAudio();
      const audio = new Audio(sample.file);
      currentAudio = audio;
      currentPlayButton = button;
      button.textContent = "Playing";
      audio.addEventListener("ended", () => {
        button.textContent = "Play";
        currentPlayButton = null;
        if (currentAudio === audio) currentAudio = null;
      });
      audio.addEventListener("error", () => {
        button.textContent = "Play";
        currentPlayButton = null;
        setStatus("Could not play sample " + sample.number);
      });
      audio.play().catch(() => {
        button.textContent = "Play";
        currentPlayButton = null;
        setStatus("Browser blocked playback");
      });
    }

    function friendlyAccent(accent) {
      return {
        "English UK": "British",
        "English US": "American",
        "English Ireland": "Irish",
        "English Australia": "Australian",
        "English Canada": "Canadian",
        "English South Africa": "South African",
        "English India": "Indian"
      }[accent] || String(accent || "").replace(/^English\s+/, "");
    }

    function baseName(sample) {
      let label = sample.label || sample.voice || ("Sample " + sample.number);
      label = label.replace(/^Edge\s+/, "").replace(/^macOS\s+/, "");
      label = label.replace(/\s+Neural$/, "").replace(/\s+UK$/, "");
      return label.trim();
    }

    function genderName(sample) {
      const style = String(sample.style || "").toLowerCase();
      if (style.includes("female")) return "female";
      if (/(^|\s)male($|\s)/.test(style)) return "male";
      const rawVoice = String(sample.voice || "").split(" (", 1)[0];
      const labelName = baseName(sample).split(/\s+/)[0];
      const femaleNames = new Set(["Ava", "Clara", "Emily", "Emma", "Flo", "Grandma", "Karen", "Kathy", "Leah", "Libby", "Maisie", "Moira", "Natasha", "Samantha", "Sandy", "Shelley", "Sonia", "Tessa"]);
      const maleNames = new Set(["Albert", "Aman", "Andrew", "Brian", "Christopher", "Connor", "Daniel", "Eddy", "Fred", "Grandpa", "Liam", "Luke", "Ralph", "Reed", "Rishi", "Rocko", "Roger", "Ryan", "Steffan", "Thomas", "William"]);
      if (femaleNames.has(rawVoice) || femaleNames.has(labelName)) return "female";
      if (maleNames.has(rawVoice) || maleNames.has(labelName)) return "male";
      return "voice";
    }

    function styleModifier(sample) {
      const style = String(sample.style || "").toLowerCase();
      if (style.includes("older")) return "older";
      if (style.includes("classic")) return "classic";
      if (style.includes("newer")) return "modern";
      if (style.includes("character")) return "character";
      if (style.includes("natural")) return "natural";
      if (style.includes("warm")) return "warm";
      if (style.includes("approachable")) return "approachable";
      if (style.includes("expressive")) return "expressive";
      if (style.includes("authoritative")) return "authoritative";
      if (style.includes("lively")) return "lively";
      if (style.includes("rational")) return "calm";
      if (style.includes("clear")) return "clear";
      if (style.includes("neural") || sample.provider === "edge_tts") return "neural";
      return "";
    }

    function shortName(sample) {
      if (sample.short_name) return sample.short_name;
      return [baseName(sample), styleModifier(sample), friendlyAccent(sample.accent), genderName(sample)]
        .filter(Boolean)
        .join(" ")
        .replace(/\s+/g, " ")
        .trim();
    }

    function createElement(tag, className, text) {
      const element = document.createElement(tag);
      if (className) element.className = className;
      if (text !== undefined) element.textContent = text;
      return element;
    }

    function updateScoreDisplay(row, value, dirty) {
      const score = clampScore(value);
      const slider = row.querySelector(".score-slider");
      const output = row.querySelector(".score-value");
      const confirm = row.querySelector(".confirm-score");
      output.textContent = scoreText(score);
      if (!dirty) slider.value = scoreText(score);
      row.classList.toggle("dirty", Boolean(dirty));
      confirm.disabled = !dirty;
    }

    function refreshRanks() {
      [...list.querySelectorAll(".row")].forEach((row, index) => {
        row.querySelector(".rank").textContent = String(index + 1);
        updateScoreDisplay(row, scoreFor(Number(row.dataset.number)), false);
      });
      refreshSelection();
    }

    function animateListChange(mutator) {
      const rows = [...list.querySelectorAll(".row")];
      const first = new Map(rows.map(row => [row.dataset.number, row.getBoundingClientRect()]));
      mutator();
      const movedRows = [...list.querySelectorAll(".row")];
      for (const row of movedRows) {
        const previous = first.get(row.dataset.number);
        if (!previous) continue;
        const next = row.getBoundingClientRect();
        const deltaY = previous.top - next.top;
        if (!deltaY) continue;
        row.classList.add("animating");
        row.style.transition = "transform 0s";
        row.style.transform = "translateY(" + deltaY + "px)";
        requestAnimationFrame(() => {
          row.style.transition = "";
          row.style.transform = "";
        });
        row.addEventListener("transitionend", () => row.classList.remove("animating"), { once: true });
      }
    }

    function applyOrder(order, animate = true) {
      const mutator = () => {
        const rowByNumber = new Map([...list.querySelectorAll(".row")].map(row => [Number(row.dataset.number), row]));
        for (const number of order) {
          const row = rowByNumber.get(number);
          if (row) list.appendChild(row);
        }
        refreshRanks();
      };
      if (animate) animateListChange(mutator);
      else mutator();
    }

    function applySortedOrder(message) {
      const order = sortedNumbers();
      applyOrder(order, true);
      state.tieOrder = order;
      saveState();
      if (message) setStatus(message);
    }

    function scoreForPosition(previousNumber, nextNumber) {
      if (previousNumber !== undefined && nextNumber !== undefined) {
        return clampScore((scoreFor(previousNumber) + scoreFor(nextNumber)) / 2);
      }
      if (nextNumber !== undefined) return clampScore(scoreFor(nextNumber) + 0.001);
      if (previousNumber !== undefined) return clampScore(scoreFor(previousNumber) - 0.001);
      return 10;
    }

    function moveNumberToIndex(number, targetIndex, announce = true) {
      const current = currentNumbers();
      const without = current.filter(item => item !== number);
      const index = Math.min(Math.max(targetIndex, 0), without.length);
      without.splice(index, 0, number);
      const previousNumber = without[index - 1];
      const nextNumber = without[index + 1];
      state.scores[number] = scoreForPosition(previousNumber, nextNumber);
      state.tieOrder = without;
      selectNumber(number);
      applySortedOrder(announce ? "Sample " + number + " score set to " + scoreText(state.scores[number]) : "");
    }

    function confirmScore(number, row) {
      const slider = row.querySelector(".score-slider");
      state.scores[number] = clampScore(slider.value);
      selectNumber(number);
      applySortedOrder("Sample " + number + " score set to " + scoreText(state.scores[number]));
    }

    function createDragImage(event, row) {
      const ghost = row.cloneNode(true);
      const rect = row.getBoundingClientRect();
      ghost.classList.add("drag-ghost");
      ghost.style.width = rect.width + "px";
      document.body.appendChild(ghost);
      event.dataTransfer.setDragImage(ghost, 26, Math.min(38, rect.height / 2));
      setTimeout(() => ghost.remove(), 0);
    }

    function arraysEqual(left, right) {
      return left.length === right.length && left.every((value, index) => value === right[index]);
    }

    function finishDrag(number) {
      const visualOrder = currentNumbers();
      const index = visualOrder.indexOf(number);
      if (index < 0 || arraysEqual(visualOrder, dragStartOrder)) {
        refreshRanks();
        return;
      }
      const previousNumber = visualOrder[index - 1];
      const nextNumber = visualOrder[index + 1];
      state.scores[number] = scoreForPosition(previousNumber, nextNumber);
      state.tieOrder = visualOrder;
      applySortedOrder("Sample " + number + " score set to " + scoreText(state.scores[number]));
    }

    function render() {
      list.innerHTML = "";
      for (const sample of orderedSamples()) {
        const row = document.createElement("article");
        row.className = "row";
        row.draggable = true;
        row.dataset.number = sample.number;

        const rank = createElement("div", "rank");
        const numberBadge = createElement("div", "sample-number", String(sample.number));
        const play = createElement("button", "play", "Play");
        play.type = "button";

        const identity = createElement("div", "identity");
        const title = createElement("strong", "", shortName(sample));
        const meta = createElement("div", "meta", [sample.provider, sample.voice, sample.accent, sample.style].filter(Boolean).join(" / "));
        identity.append(title, meta);

        const scoreBox = createElement("div", "score-box");
        const scoreTop = createElement("div", "score-top");
        const scoreLabel = createElement("span", "", "Score");
        const scoreValue = createElement("output", "score-value");
        scoreTop.append(scoreLabel, scoreValue);
        const scoreControl = createElement("div", "score-control");
        const slider = createElement("input", "score-slider");
        slider.type = "range";
        slider.min = "1";
        slider.max = "10";
        slider.step = "0.001";
        slider.setAttribute("aria-label", "Score for sample " + sample.number);
        const confirm = createElement("button", "confirm-score", "Confirm");
        confirm.type = "button";
        confirm.disabled = true;
        scoreControl.append(slider, confirm);
        scoreBox.append(scoreTop, scoreControl);

        const moves = createElement("div", "moves");
        const up = createElement("button", "up", "Up");
        const down = createElement("button", "down", "Down");
        up.type = "button";
        down.type = "button";
        moves.append(up, down);

        row.append(rank, numberBadge, play, identity, scoreBox, moves);

        play.addEventListener("click", event => playSample(sample, event.currentTarget));
        up.addEventListener("click", () => {
          const index = currentNumbers().indexOf(sample.number);
          if (index > 0) moveNumberToIndex(sample.number, index - 1);
        });
        down.addEventListener("click", () => {
          const index = currentNumbers().indexOf(sample.number);
          if (index >= 0 && index < currentNumbers().length - 1) moveNumberToIndex(sample.number, index + 1);
        });
        slider.addEventListener("input", () => {
          selectNumber(sample.number);
          updateScoreDisplay(row, slider.value, true);
        });
        confirm.addEventListener("click", () => confirmScore(sample.number, row));
        row.addEventListener("pointerdown", () => selectNumber(sample.number));
        row.addEventListener("dragstart", event => {
          selectNumber(sample.number);
          dragStartOrder = currentNumbers();
          row.classList.add("dragging");
          event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData("text/plain", String(sample.number));
          createDragImage(event, row);
        });
        row.addEventListener("dragend", () => {
          row.classList.remove("dragging");
          finishDrag(sample.number);
        });
        list.appendChild(row);
      }
      refreshRanks();
    }

    list.addEventListener("dragover", event => {
      event.preventDefault();
      const dragging = list.querySelector(".dragging");
      if (!dragging) return;
      const rows = [...list.querySelectorAll(".row:not(.dragging)")];
      const after = rows.find(row => event.clientY <= row.getBoundingClientRect().top + row.offsetHeight / 2);
      if (after && after !== dragging.nextElementSibling) {
        animateListChange(() => list.insertBefore(dragging, after));
      } else if (!after && dragging !== list.lastElementChild) {
        animateListChange(() => list.appendChild(dragging));
      }
    });

    list.addEventListener("drop", event => event.preventDefault());

    async function copyText(text, label) {
      try {
        await navigator.clipboard.writeText(text);
        setStatus(label + " copied");
      } catch {
        const box = document.createElement("textarea");
        box.value = text;
        document.body.appendChild(box);
        box.select();
        document.execCommand("copy");
        box.remove();
        setStatus(label + " copied");
      }
    }

    document.getElementById("copy-json").addEventListener("click", () => {
      const rankings = currentNumbers().map((number, index) => {
        const sample = sampleByNumber.get(number);
        return {
          rank: index + 1,
          number,
          score: scoreFor(number),
          short_name: shortName(sample),
          label: sample.label,
          provider: sample.provider,
          voice: sample.voice
        };
      });
      const payload = {
        ranked_sample_numbers: currentNumbers(),
        rankings,
        sample_text: sampleText,
        generated_at: generatedAt
      };
      copyText(JSON.stringify(payload, null, 2), "JSON");
    });

    document.getElementById("copy-text").addEventListener("click", () => {
      copyText(currentNumbers().join(", "), "Text");
    });

    document.getElementById("toggle-details").addEventListener("click", event => {
      document.body.classList.toggle("show-details");
      event.currentTarget.textContent = document.body.classList.contains("show-details") ? "Hide Details" : "Show Details";
    });

    document.getElementById("reset-order").addEventListener("click", () => {
      localStorage.removeItem(storageKey);
      const fresh = loadState();
      state.scores = fresh.scores;
      state.tieOrder = fresh.tieOrder;
      state.selectedNumber = null;
      render();
      setStatus("Order reset");
    });

    document.getElementById("stop-audio").addEventListener("click", stopAudio);

    render();
    window.JarvisVoiceAudition = {
      currentNumbers,
      currentScores: () => Object.fromEntries(currentNumbers().map(number => [number, scoreFor(number)])),
      setScore: (number, score) => {
        if (!sampleByNumber.has(number)) return false;
        state.scores[number] = clampScore(score);
        selectNumber(number);
        applySortedOrder("");
        return true;
      },
      moveNumberToIndex: (number, index) => {
        if (!sampleByNumber.has(number)) return false;
        moveNumberToIndex(number, index, false);
        return true;
      },
      reset: () => {
        localStorage.removeItem(storageKey);
        location.reload();
      }
    };
  </script>
</body>
</html>
"""
    return (
        html_doc.replace("__SAMPLES_JSON__", samples_json)
        .replace("__SAMPLE_TEXT_JSON__", json.dumps(sample_text, ensure_ascii=False))
        .replace("__GENERATED_AT_JSON__", json.dumps(generated_at, ensure_ascii=False))
        .replace("__SENTENCE__", escaped_sentence)
        .replace("__SAMPLE_COUNT__", str(len(samples)))
        .replace("__GENERATED_AT__", escaped_generated_at)
    )


def generate(
    output_dir: Path,
    text: str,
    max_samples: int | None,
    *,
    include_online_voices: bool = False,
    allow_external_output_dir: bool = False,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    if not allow_external_output_dir and not is_project_relative(output_dir):
        raise ValueError("output_dir must stay inside the Jarvis project unless allow_external_output_dir is True")
    output_dir.mkdir(parents=True, exist_ok=True)
    samples_dir = output_dir / "samples"
    if samples_dir.exists():
        for old_file in samples_dir.glob("*.mp3"):
            old_file.unlink()
    samples_dir.mkdir(parents=True, exist_ok=True)

    candidates, unavailable = candidate_pool(output_dir, max_samples, include_online_voices=include_online_voices)
    generated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    generated: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    next_number = 1
    for candidate in candidates:
        target = samples_dir / f"{next_number}.mp3"
        started = time.monotonic()
        if candidate.provider == "macos_say":
            ok, error = generate_macos(candidate, text, target)
        elif candidate.provider == "edge_tts":
            ok, error = generate_edge(candidate, text, target, output_dir)
        else:
            ok, error = False, f"unknown provider {candidate.provider}"

        elapsed = round(time.monotonic() - started, 3)
        if ok:
            generated.append(
                {
                    "number": next_number,
                    "file": f"samples/{next_number}.mp3",
                    "provider": candidate.provider,
                    "voice": candidate.voice,
                    "label": candidate.label,
                    "short_name": short_name_for_candidate(candidate),
                    "accent": candidate.accent,
                    "style": candidate.style,
                    "duration_seconds": probe_duration(target),
                    "generation_seconds": elapsed,
                }
            )
            next_number += 1
        else:
            if target.exists():
                target.unlink()
            failures.append(
                {
                    "provider": candidate.provider,
                    "voice": candidate.voice,
                    "label": candidate.label,
                    "reason": error,
                    "elapsed_seconds": elapsed,
                }
            )

    report = {
        "generated_at": generated_at,
        "sample_text": text,
        "seed": SEED,
        "sample_count": len(generated),
        "include_online_voices": include_online_voices,
        "samples": generated,
        "failures": failures,
        "unavailable": unavailable,
        "not_attempted": [
            {
                "provider": "kokoro_onnx",
                "reason": "Package installed, but the model weights were not generated in this pass because the required model download was too slow on this network.",
            },
            {
                "provider": "piper_tts",
                "reason": "No local Piper executable or British English model bundle was available in the workspace.",
            },
            {
                "provider": "commercial_api_tts",
                "reason": "Skipped paid/API-key providers for this first voice audition because Apple and Edge could generate real samples without adding secrets.",
            },
        ],
    }

    (output_dir / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "index.html").write_text(html_page(generated, text, generated_at), encoding="utf-8")
    return report


def is_project_relative(path: Path) -> bool:
    try:
        path.resolve().relative_to(PROJECT_ROOT)
    except ValueError:
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate numbered TTS samples and a ranking HTML page.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--text", default=DEFAULT_SAMPLE_TEXT)
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--include-online-voices", action="store_true", help="Also try online Edge TTS voices.")
    parser.add_argument("--allow-external-output-dir", action="store_true", help="Allow writing/cleaning samples outside this Jarvis project.")
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    if not args.allow_external_output_dir and not is_project_relative(output_dir):
        parser.error("--output-dir must stay inside the Jarvis project unless --allow-external-output-dir is set")

    report = generate(
        output_dir,
        args.text,
        args.max_samples,
        include_online_voices=args.include_online_voices,
        allow_external_output_dir=args.allow_external_output_dir,
    )
    print(f"Generated {report['sample_count']} samples")
    print(args.output_dir.resolve() / "index.html")
    if report["failures"]:
        print(f"{len(report['failures'])} candidates failed; see manifest.json", file=sys.stderr)
    return 0 if report["sample_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
