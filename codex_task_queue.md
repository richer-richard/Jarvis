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
