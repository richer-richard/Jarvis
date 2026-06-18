#!/usr/bin/env python3
"""Run Jarvis live checks that must not trigger macOS permission prompts."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from scripts import verify_safe
except ImportError:  # pragma: no cover - direct script execution fallback.
    import verify_safe  # type: ignore[no-redef]

REPORT_DIR = PROJECT_ROOT / "runtime" / "verification_no_prompt"
DEFAULT_BASE_URL = "http://127.0.0.1:8765"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output-dir", default=str(REPORT_DIR))
    args = parser.parse_args()

    try:
        base_url = verify_safe.normalize_base_url(args.base_url)
    except ValueError as error:
        print(f"Refused unsafe base URL: {error}", file=sys.stderr)
        return 2
    report = run_no_prompt_checks(base_url)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    report_path = output_dir / f"verify-no-prompt-{stamp}.json"
    latest_path = output_dir / "latest.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    latest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Report: {report_path}")
    print(f"Passed: {report['passed']}/{report['total']}")
    return 0 if report["ok"] else 1


def run_no_prompt_checks(base_url: str = DEFAULT_BASE_URL) -> dict[str, object]:
    base_url = verify_safe.normalize_base_url(base_url)
    started = time.monotonic()
    checks: list[tuple[str, Callable[[], str]]] = [
        ("worker_health", lambda: check_worker_health(base_url)),
        ("overnight_report_routes", lambda: verify_safe.check_endpoint_overnight_report_routes(base_url)),
        ("wake_audition_corpus", lambda: verify_safe.check_endpoint_wake_audition_corpus(base_url)),
        ("wake_simulation", lambda: verify_safe.check_endpoint_wake_simulation(base_url)),
        ("speech_mute", lambda: verify_safe.check_endpoint_speech_mute(base_url)),
        ("quiet_command", lambda: verify_safe.check_endpoint_quiet_command(base_url)),
        ("model_context", lambda: verify_safe.check_endpoint_model_context(base_url)),
        ("voice_loop_echo", lambda: verify_safe.check_endpoint_voice_loop_echo(base_url)),
        ("voice_loop_repeated_wake", lambda: verify_safe.check_endpoint_voice_loop_repeated_wake(base_url)),
        ("wake_debug", lambda: verify_safe.check_endpoint_wake_debug(base_url)),
        ("swift_wake_preflight_contracts", check_swift_wake_preflight_contracts),
        ("swift_source_contracts", check_swift_source_contracts),
    ]
    results = [asdict(verify_safe.endpoint_check(name, check)) for name, check in checks]
    passed = sum(1 for item in results if item.get("passed"))
    total = len(results)
    return {
        "schema": "jarvis.no_prompt_verification.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "base_url": base_url,
        "ok": passed == total and total > 0,
        "passed": passed,
        "total": total,
        "duration_seconds": round(time.monotonic() - started, 3),
        "policy": {
            "opens_apps": False,
            "requests_microphone": False,
            "requests_speech_recognition": False,
            "uses_screen_capture": False,
            "uses_accessibility": False,
            "pushes_to_network_repo": False,
        },
        "results": results,
    }


def check_worker_health(base_url: str) -> str:
    health = verify_safe.get_json("/api/health", base_url=base_url)
    verify_safe.require(health.get("ok") is True, f"health ok was {health.get('ok')}")
    app = health.get("status", {}).get("app", {}) if isinstance(health.get("status"), dict) else {}
    version = app.get("version") or "unknown"
    build = app.get("build") or "unknown"
    worker_kind = app.get("worker_source_kind") or "unknown worker"
    return f"worker healthy, Jarvis {version} build {build}, {worker_kind}"


def check_swift_source_contracts() -> str:
    model_path = PROJECT_ROOT / "swift-shell" / "Sources" / "JarvisMenuBar" / "Models" / "JarvisShellModel.swift"
    listener_path = PROJECT_ROOT / "swift-shell" / "Sources" / "JarvisMenuBar" / "Support" / "JarvisWakeListener.swift"
    model_source = model_path.read_text(encoding="utf-8")
    listener_source = listener_path.read_text(encoding="utf-8")
    verify_safe.require("guard !isBusy else" in model_source, "typed submit busy guard missing")
    verify_safe.require("private static let busyReplyText" in model_source, "busy reply text missing")
    verify_safe.require("private func sendSpeechMute" in model_source, "direct speech mute helper missing")
    first_mute = model_source.find("return try await client.setSpeechMuted(muted)")
    fallback = model_source.find("let startup = await workerSupervisor.ensureRunning()")
    verify_safe.require(first_mute >= 0, "direct speech mute call missing")
    verify_safe.require(fallback >= 0, "worker-start fallback missing")
    verify_safe.require(first_mute < fallback, "speech mute should call backend before worker-start fallback")
    verify_safe.require("JarvisWakeAudioTapSink: @unchecked Sendable" in listener_source, "non-actor audio tap sink missing")
    verify_safe.require("installJarvisWakeAudioTap(on: input, request: request)" in listener_source, "audio tap helper call missing")
    verify_safe.require("input.installTap(onBus: 0, bufferSize: 1024, format: format) { [sink] buffer, _ in" in listener_source, "audio tap should capture sink explicitly")
    verify_safe.require("restartStormLimit = 2" in listener_source, "stricter wake restart storm limit missing")
    verify_safe.require("recoveryRestartDelaySeconds" in listener_source, "wake recovery backoff delay missing")
    verify_safe.require("Speech Recognition is recovering; Hey Jarvis is still listening" in listener_source, "wake recovery should keep listener active")
    verify_safe.require("maxRestartAttemptsPerActivation" not in listener_source, "wake listener should not have a hard activation stop cap")
    verify_safe.require("shouldPauseAfterActivationRestartLimit" in listener_source, "wake activation restart decision missing")
    verify_safe.require("lastPublishedSnapshot" in listener_source, "duplicate wake snapshot guard missing")
    return "Swift source keeps busy-submit guard, direct mute-first path, non-actor wake audio tap, and wake recovery backoff"


def check_swift_wake_preflight_contracts() -> str:
    model_path = PROJECT_ROOT / "swift-shell" / "Sources" / "JarvisMenuBar" / "Models" / "JarvisShellModel.swift"
    permission_path = PROJECT_ROOT / "swift-shell" / "Sources" / "JarvisMenuBar" / "Support" / "JarvisPermissionService.swift"
    model_source = model_path.read_text(encoding="utf-8")
    permission_source = permission_path.read_text(encoding="utf-8")
    verify_safe.require("wakeStartPreflight()" in permission_source, "wake permission preflight helper missing")
    verify_safe.require("let preflight = JarvisPermissionService.wakeStartPreflight()" in model_source, "wake start should preflight permissions")
    verify_safe.require("isRequestableVoiceState" in permission_source, "wake preflight should distinguish requestable and blocked voice states")
    verify_safe.require("Starting Hey Jarvis will ask macOS" in permission_source, "wake preflight should allow explicit start for requestable voice states")
    verify_safe.require("wakeDetailText = preflight.detail" in model_source, "wake start should show preflight detail before starting listener")
    verify_safe.require('recordWakeEvent("listener_start_blocked"' in model_source, "wake start blocked event missing")
    verify_safe.require('detail: "Wake not started"' in model_source, "wake start blocked visible message missing")
    return "Swift wake start preflights permissions, allows explicit requestable voice starts, and blocks denied states visibly"


if __name__ == "__main__":
    raise SystemExit(main())
