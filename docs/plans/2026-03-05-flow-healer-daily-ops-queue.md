# Flow Healer Daily Ops Queue Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a concise daily operator workflow that retrieves current Flow Healer state in a fixed order, checks scan freshness, and outputs a narrow high-signal queue without inventing IDs or findings.

**Architecture:** Reuse existing healer surfaces first: `system: healer` for top-line status, the SQLite-backed healer tables for tracked issues/attempts/locks, and the existing scan runner for conditional lightweight dry-run refresh. Keep analysis read-only except for the explicit dry-run scan fallback; do not auto-create issues or mutate healer state beyond that scan trigger.

**Tech Stack:** Python 3.11+, Apple Flow orchestrator/store, SQLite healer tables, existing system commands, optional admin/reporting surface

---

## Objective

Produce a daily Flow Healer operations queue that:
- fetches data in the exact requested order
- prioritizes blocked PRs, repeated gate failures, verifier failures, and lock conflicts
- emits the exact report shape requested
- says `No healer action needed today` when there is no active work and no fresh findings

## Files To Inspect First

- `src/apple_flow/orchestrator.py`
- `src/apple_flow/store.py`
- `src/apple_flow/healer_loop.py`
- `src/apple_flow/healer_scan.py`
- `docs/flow-healer/03-operations-and-troubleshooting.md`

## Steps

1. Confirm the primary status surface from [`src/apple_flow/orchestrator.py`](/Users/cypher-server/Documents/code/codex-flow/src/apple_flow/orchestrator.py#L1075) and use `system: healer` as the first retrieval step for current state summary.
2. Pull recent healer attempts from [`src/apple_flow/store.py`](/Users/cypher-server/Documents/code/codex-flow/src/apple_flow/store.py#L1058) and filter to the last 7 days by `started_at`, preserving issue IDs, final states, and repeated failure classes.
3. Pull open tracked healer issues from [`src/apple_flow/store.py`](/Users/cypher-server/Documents/code/codex-flow/src/apple_flow/store.py#L806) and filter to items carrying the intake label `healer:ready`.
4. Split tracked issues into PR states using the existing repo state model: `pr_pending_approval` and `pr_open`, matching the dashboard/state docs in [`src/apple_flow/orchestrator.py`](/Users/cypher-server/Documents/code/codex-flow/src/apple_flow/orchestrator.py#L1080) and [`docs/flow-healer/03-operations-and-troubleshooting.md`](/Users/cypher-server/Documents/code/codex-flow/docs/flow-healer/03-operations-and-troubleshooting.md#L8).
5. Pull stuck-state indicators from healer issues and locks: `paused` via `kv_state.healer_paused`, work items in `claimed`/`running`/`verify_pending`/`blocked`, and active lock rows from [`src/apple_flow/store.py`](/Users/cypher-server/Documents/code/codex-flow/src/apple_flow/store.py#L1259).
6. Read `scan_runs` and `scan_findings` directly from the store to determine whether findings exist and whether the most recent scan is fresher than 24 hours; note that there is no dedicated “list recent findings” helper today.
7. If findings are missing, stale, or inconsistent with current healer state, trigger only `system: healer scan dry-run`; do not run `system: healer scan` and do not create issues automatically.
8. Apply the output rules: if there are no active healer items and no fresh findings, emit only `No healer action needed today`; otherwise produce the exact five report sections with at most 8 bullets total and only verified Issue/PR IDs.

## Risks

- Scan freshness is not fully exposed by a high-level command, so relying only on `system: healer` can miss stale or absent findings unless the implementation reads `scan_runs`/`scan_findings` directly.
- Repeated failures can be misclassified if the plan does not normalize successful terminal states the same way the dashboard does: `pr_open`, `resolved`, and `pr_pending_approval` are not failures.
- Lock conflict noise can hide the real blocker unless issue state and `healer_locks` are read together.
- A live scan would violate the prompt’s safety boundary if it creates issues; the fallback must stay dry-run only.

## Done Criteria

- Retrieval order exactly matches: current state, recent attempts, open `healer:ready` issues, PR states, stuck states, scan findings.
- Freshness logic clearly distinguishes fresh findings from missing/stale findings using a 24-hour cutoff.
- Dry-run scan is the only automatic action and only occurs when the specified condition is met.
- Output always uses the requested section headings and never exceeds 8 bullets total.
- Unknown IDs or findings are rendered as `Unknown`, never inferred.
