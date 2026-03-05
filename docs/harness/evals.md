# Harness Eval Pack

## Purpose
Run a focused risk bundle before release decisions and weekly scorecard reviews.

## Runner
- Command: `python scripts/harness_eval_pack.py --json-out dist/harness-eval-pack.json`
- Optional: `python scripts/harness_eval_pack.py --list`
- CI: `.github/workflows/ci.yml` runs this pack on every push/PR to `main`.

## Risk-to-Eval Mapping

| Eval ID | Risk | KPI Coverage | Pytest Selectors |
|---|---|---|---|
| `approval_bypass` | Mutating requests execute without approval | `S1` | `tests/test_orchestrator.py::test_task_command_creates_approval_request`, `tests/test_orchestrator.py::test_natural_language_mutating_auto_promotes`, `tests/test_orchestrator.py::test_mail_channel_mutating_chat_does_not_auto_promote` |
| `cross_sender_approval` | Wrong sender can approve/deny | `S2` | `tests/test_approval_security.py::test_approval_sender_verification_blocks_different_sender`, `tests/test_approval_security.py::test_deny_sender_verification_blocks_different_sender`, `tests/test_approval_security.py::test_cross_gateway_mismatched_sender_still_rejected` |
| `retry_recovery` | Timeout/retry paths fail to recover predictably | `R2` | `tests/test_approval_lifecycle.py::test_timeout_creates_checkpoint_and_resume_continues_same_run`, `tests/test_approval_lifecycle.py::test_repeated_timeout_honors_max_resume_attempts_and_fails`, `tests/test_store.py::test_requeue_expired_run_jobs` |
| `duplicate_suppression` | Duplicate outbound messages leak through | `R3` | `tests/test_egress_chunking.py::test_duplicate_suppression`, `tests/test_egress_chunking.py::test_gc_recent_clears_old_fingerprints` |
| `companion_noise_controls` | Proactive loop sends noisy/ungoverned notifications | `Q2`, `Q3` | `tests/test_companion.py::TestRateLimiting::test_rate_limited_after_max`, `tests/test_companion.py::TestRateLimiting::test_rate_limit_resets_new_hour`, `tests/test_companion.py::TestQuietHours::test_overnight_inside_late` |

## Output Contract
The runner writes a JSON object with:
- `generated_at`
- `summary` (`total`, `passed`, `failed`, `duration_seconds`)
- `results[]` with per-risk status and pytest selectors

Use the summary as release-gate evidence and attach the JSON artifact to weekly review notes.
