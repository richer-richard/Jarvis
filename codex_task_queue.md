# Codex Task Queue

## Active

- [ ] Continue the active Jarvis hardening goal until all known user-reported bugs are fixed or captured by reliable regression tests.
- [ ] Use overnight protocol with no fixed wake-up time: keep working until Leo says he woke up; do not wait for questions, secret-code prompts, or interactive approvals.
- [x] Refresh current proof surfaces after the canonical app rebuild and fresh safe verification.
- [x] Run full `tests.test_safety` for the Hey Jarvis restart-churn fix and commit it if green.
- [x] Expand Chrome/Jarvis test-tab cleanup so overnight-created local report, workboard, wake-audition, and old LocalOS music tabs are identifiable without touching personal tabs.
- [x] Add an explicit pre-build speech proof contract so quiet speech-payload audits cannot be mistaken for live spoken playback tests.
- [x] Run the live Music full-loop case and tighten hidden `afplay` detection so proof reports ignore Piper worker arguments but still fail real hidden playback.
- [x] Run the all-target-prompt full-loop suite and record the `8/8` pass.
- [x] Run the updated pre-build gate wrapper and record the `3/3` pass with explicit `suppressed_for_probe` speech contract.
- [x] Add a morning-status warning for speech being unmuted without any Jarvis menu-bar/status-helper emergency control.
- [x] Add current-night 0.1.468 highlights to the master report so the top shipped archive names the `8/8` target pass, Music proof, speech-proof modes, Chrome cleanup, and speech emergency status.
- [x] Mark Gemma/Qwen-style audio-native models as `research_only` in `models.test_plan` until bounded probes and full-loop STT proof exist.
- [x] Inspect current GitHub branch state without pushing; current branch is ahead-only and dry-run fetch reports no incoming updates.
- [x] Replace native Outlook/screen and early streaming "Working" status rows with the final answer row instead of leaving stale visible progress behind.
- [x] Add a main-app emergency status-item fallback when the always-visible status helper cannot launch, and remove that fallback after helper recovery to avoid duplicate heads.
- [x] Strip markdown/raw URLs and email addresses from app-visible reply fields, not only from TTS payloads.
- [x] Force app-launched Jarvis workers onto macOS `say`/plain system defaults so inherited Piper settings cannot return in the app.
- [x] Rebuild canonical ignored `output/Jarvis.app` after the Swift fixes and verify bundle plist, codesign, menu-bar self-test, and status-helper self-test.
- [x] Fix the live `output/Jarvis.app` launch hang so stale-process cleanup cannot block before worker monitoring starts, and verify the app launches with one helper and one bundled worker.
- [ ] Pick the next risky bug from `JARVIS_BUG_BACKLOG.md`, implement a focused fix, add/update tests, and commit only after meaningful passing proof.

## Completed This Turn

- [x] Re-read `/Users/leoxu/.codex/AGENTS.md` and acknowledged the updated overnight and task-queue rules.
- [x] Rebuilt the canonical `output/Jarvis.app` bundle at version `0.1.468`.
- [x] Reran `scripts/verify_safe.py`; safe verification passed `105/105`.
- [x] Refreshed report/workboard surfaces and reran `scripts/smoke_fast_latency.py`; fast latency passed `3/3`.
- [x] Implemented a Hey Jarvis restart-churn guard so final/error recognition callbacks stop the old audio session before scheduling a restart.
- [x] Focused wake source-contract tests, Swift build, and Swift menu-bar self-test passed for the restart-churn guard.
- [x] Full `tests.test_safety` passed `925/925` for the restart-churn guard.
- [x] Focused Chrome cleanup tests passed, and cleanup dry-run found zero current matching tabs to close.
- [x] Focused pre-build gate tests passed for `suppressed_for_probe`, `live_playback_exercised`, and `--require-live-speech` fail-closed behavior.
- [x] Live Music full-loop case passed again in `11.942s` with the expected Dear Evan Hansen track, verified stopped, and both `afplay_processes_after` and `new_afplay_processes_after` empty.
- [x] Full target prompt regression passed `8/8` in `130.873s` with zero warnings and all latency budgets passing.
- [x] Pre-build gate wrapper passed `3/3` in `128.093s`, including full-loop regression, Chrome cleanup, and report refresh.
- [x] Focused morning-status speech emergency tests passed, and live status reports `Speech emergency: safe (speech muted)`.
- [x] Focused master-report render tests passed for the new current-night product highlights.
- [x] Focused model-plan tests passed for the `audio_input_status` research-only contract.
- [x] Git CLI proof: `codex/jarvis-overnight-20260608` is `ahead 126, behind 0`; dry-run fetch reported no incoming updates and no push was attempted.
- [x] Focused Swift progress/status tests passed for replacing native Outlook/screen and early streaming status placeholders with the final answer.
- [x] Full `tests.test_safety` passed `931/931` and canonical `scripts/verify_safe.py` passed `105/105` for the stale Working status row cleanup.
- [x] Focused status-helper emergency tests passed, `swift build --product jarvis-menu-bar` passed, `jarvis-menu-bar --self-test` passed, and `jarvis-status-helper --self-test` passed for the emergency fallback.
- [x] Full `tests.test_safety` passed `931/931` and canonical `scripts/verify_safe.py` passed `105/105` for the status-helper emergency fallback.
- [x] Focused visible/speech sanitizer tests passed for removing raw links from displayed command replies and spoken payloads.
- [x] Focused worker voice-default tests passed, `swift build --product jarvis-menu-bar` passed, and `jarvis-menu-bar --self-test` passed for the macOS `say` provider patch.
- [x] `swift-shell/scripts/build_app_bundle.sh` rebuilt `output/Jarvis.app` as Jarvis `0.1.468` build `468`; plist lint, codesign verify, bundled `jarvis-menu-bar --self-test`, and bundled `jarvis-status-helper --self-test` passed.
- [x] Fixed the live app launch path: stale-process cleanup now fails fast instead of hanging in `ps`, launch-time panel open no longer forces a parallel refresh, and worker monitoring performs the initial refresh after readiness.
- [x] Live `build_and_launch_app.sh` succeeded after the fix; health reported `Jarvis 0.1.468 build 468 is online and ready`, with bundled worker source and `worker_launch_matches_bundle: true`.
- [x] Full `tests.test_safety` passed `934/934`, and `scripts/verify_safe.py` passed `105/105` with report `runtime/verification/verify-safe-20260620-001017.json`.
