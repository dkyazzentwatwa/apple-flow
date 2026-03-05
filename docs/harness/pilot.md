# Two-Week Harness Pilot

## Focus
Highest-friction workflow: stale approvals + overdue reminders.

## Timeline
- Baseline window: `2026-03-05` to `2026-03-07`
- Pilot week 1: `2026-03-08` to `2026-03-14`
- Pilot week 2: `2026-03-15` to `2026-03-21`
- Rollout decision: `2026-03-22`

## Metrics to Track
1. Stale approvals older than 30 minutes (count/day).
2. Reminder backlog closure for overdue items from Feb 19-24 (closures/day).
3. Companion proactive noise ratio (`false_alerts / total_alerts`).
4. Harness eval pack pass rate (`passed_evals / total_evals`).

## Baseline Capture Checklist
1. Run `python scripts/harness_eval_pack.py --json-out dist/harness-eval-baseline.json`.
2. Capture pending-approval counts from `store` / admin endpoint.
3. Capture overdue reminder counts from Reminders gateway.
4. Record values in the weekly review template under `Companion Fatigue Check` and KPI table.

## Intervention Checklist
1. Enforce state-machine invariants from `docs/harness/state-machine.md` during all workflow changes.
2. Run harness eval pack before each merge affecting approval, execution, egress, or companion.
3. Use the workspace ops guardrails in `agent-office/docs/HARNESS_WORKSPACE_OPS.md`.

## Exit Criteria
- No approval bypass incidents (`S1 = Green`).
- No cross-sender approvals accepted (`S2 = Green`).
- Retry recovery remains at or above threshold (`R2 >= 80%`).
- Duplicate suppression correctness remains at or above threshold (`R3 >= 99.90%`).
- Companion noise trends down week-over-week with no quiet-hours violations.

## Rollout Decision Template
- Decision: `rollout | extend pilot | rollback`
- Why:
- Metrics summary:
- Risks still open:
- Owner:
