#!/usr/bin/env python3
"""Repair the local faster-whisper tiny.en model cache from a reachable mirror.

Dry-run is the default. Use --execute-network only after the model download has
been explicitly approved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_REPO_DIR = "models--Systran--faster-whisper-tiny.en"
SNAPSHOT_ID = "0d3d19a32d3338f10357c0889762bd8d64bbdeba"
MODEL_BLOB_ID = "1a5afae06a4db91c975c9a9d78be5cc110ee4ea022ad57d55492e4550e936b2a"
MODEL_SIZE = 75_537_502
DEFAULT_URL = "https://hf-mirror.com/Systran/faster-whisper-tiny.en/resolve/main/model.bin"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--dry-run", action="store_true", help="Plan only. This is the default.")
    parser.add_argument("--execute-network", action="store_true", help="Actually download the model blob if repair is needed.")
    args = parser.parse_args()

    root = Path(args.project_root).expanduser().resolve()
    dry_run = not args.execute_network or args.dry_run
    status = repair_model_cache(root, url=args.url, dry_run=dry_run)
    status["execute_network"] = bool(args.execute_network and not args.dry_run)
    print(json.dumps(status, indent=2, ensure_ascii=False))
    return 0 if status["ok"] or status.get("dry_run") else 1


def repair_model_cache(root: Path, *, url: str = DEFAULT_URL, dry_run: bool = False) -> dict[str, Any]:
    paths = model_cache_paths(root)
    before = model_cache_status(root)
    if before["ok"]:
        return {**before, "repaired": False, "dry_run": dry_run}
    if dry_run:
        return {**before, "repaired": False, "dry_run": True}

    paths["blob_dir"].mkdir(parents=True, exist_ok=True)
    paths["snapshot_dir"].mkdir(parents=True, exist_ok=True)
    temp_path = paths["blob"].with_suffix(paths["blob"].suffix + f".download-{int(time.time())}")
    download_file(url, temp_path)
    digest = sha256_file(temp_path)
    size = temp_path.stat().st_size
    if digest != MODEL_BLOB_ID or size != MODEL_SIZE:
        return {
            **before,
            "ok": False,
            "repaired": False,
            "dry_run": dry_run,
            "downloaded_path": str(temp_path),
            "downloaded_size": size,
            "downloaded_sha256": digest,
            "error": "download_checksum_or_size_mismatch",
        }
    os.replace(temp_path, paths["blob"])
    if paths["model_bin"].is_symlink() and os.readlink(paths["model_bin"]) == f"../../blobs/{MODEL_BLOB_ID}":
        pass
    elif paths["model_bin"].exists() or paths["model_bin"].is_symlink():
        return {
            **model_cache_status(root),
            "ok": False,
            "repaired": True,
            "dry_run": dry_run,
            "error": "model_bin_exists_with_unexpected_target",
        }
    else:
        paths["model_bin"].symlink_to(f"../../blobs/{MODEL_BLOB_ID}")
    return {**model_cache_status(root), "repaired": True, "dry_run": dry_run}


def model_cache_paths(root: Path) -> dict[str, Path]:
    model_root = root / "runtime" / "stt_models" / "faster_whisper" / "models" / MODEL_REPO_DIR
    blob_dir = model_root / "blobs"
    snapshot_dir = model_root / "snapshots" / SNAPSHOT_ID
    return {
        "model_root": model_root,
        "blob_dir": blob_dir,
        "snapshot_dir": snapshot_dir,
        "blob": blob_dir / MODEL_BLOB_ID,
        "model_bin": snapshot_dir / "model.bin",
    }


def model_cache_status(root: Path) -> dict[str, Any]:
    paths = model_cache_paths(root)
    blob_exists = paths["blob"].exists()
    model_exists = paths["model_bin"].exists()
    blob_size = paths["blob"].stat().st_size if blob_exists else 0
    blob_sha256 = sha256_file(paths["blob"]) if blob_exists and blob_size == MODEL_SIZE else ""
    model_target = os.readlink(paths["model_bin"]) if paths["model_bin"].is_symlink() else ""
    ok = (
        blob_exists
        and model_exists
        and blob_size == MODEL_SIZE
        and blob_sha256 == MODEL_BLOB_ID
        and (not paths["model_bin"].is_symlink() or model_target == f"../../blobs/{MODEL_BLOB_ID}")
    )
    return {
        "ok": ok,
        "model_bin": str(paths["model_bin"]),
        "model_bin_exists": model_exists,
        "model_bin_symlink_target": model_target,
        "blob": str(paths["blob"]),
        "blob_exists": blob_exists,
        "blob_size": blob_size,
        "blob_sha256": blob_sha256,
        "expected_size": MODEL_SIZE,
        "expected_sha256": MODEL_BLOB_ID,
    }


def download_file(url: str, output_path: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Jarvis-local-stt-repair/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response, output_path.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
