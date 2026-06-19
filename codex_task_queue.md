# Codex Task Queue

## Active

- [ ] Continue the active Jarvis hardening goal until all known user-reported bugs are fixed or captured by reliable regression tests.
- [ ] Use overnight protocol with no fixed wake-up time: keep working until Leo says he woke up; do not wait for questions, secret-code prompts, or interactive approvals.
- [x] Refresh current proof surfaces after the canonical app rebuild and fresh safe verification.
- [x] Run full `tests.test_safety` for the Hey Jarvis restart-churn fix and commit it if green.
- [ ] Pick the next risky bug from `JARVIS_BUG_BACKLOG.md`, implement a focused fix, add/update tests, and commit only after meaningful passing proof.

## Completed This Turn

- [x] Re-read `/Users/leoxu/.codex/AGENTS.md` and acknowledged the updated overnight and task-queue rules.
- [x] Rebuilt the canonical `output/Jarvis.app` bundle at version `0.1.468`.
- [x] Reran `scripts/verify_safe.py`; safe verification passed `105/105`.
- [x] Refreshed report/workboard surfaces and reran `scripts/smoke_fast_latency.py`; fast latency passed `3/3`.
- [x] Implemented a Hey Jarvis restart-churn guard so final/error recognition callbacks stop the old audio session before scheduling a restart.
- [x] Focused wake source-contract tests, Swift build, and Swift menu-bar self-test passed for the restart-churn guard.
- [x] Full `tests.test_safety` passed `925/925` for the restart-churn guard.
