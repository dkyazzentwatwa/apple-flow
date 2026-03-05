# Flow Healer Manual

## Comprehensive Operator and Developer Reference

Version: March 5, 2026

---

## 1. Purpose

This manual is the comprehensive reference for Flow Healer inside Apple Flow.

It is written for:

- operators running Flow Healer in real repositories
- developers extending the healer code path
- maintainers teaching the system internally
- anyone debugging healer queue, scan, verifier, PR, or learning behavior

If you want a simpler, presentation-friendly document, start with [`04-workshop-guide.md`](./04-workshop-guide.md).

---

## 2. System Overview

Flow Healer is Apple Flow's autonomous remediation subsystem for GitHub-issue-driven maintenance work.

It is intentionally designed as a control plane, not a raw “AI edits code” loop.

The system continuously:

1. ingests approved GitHub issues
2. optionally scans the local repository for failures
3. stores healer issues in a durable SQLite queue
4. claims issues with leases
5. predicts lock scope before editing
6. creates per-issue workspaces
7. asks a proposer for a unified diff
8. runs test gates
9. asks a verifier for an independent pass/fail judgment
10. opens or updates a PR if all required gates pass
11. reconciles stale leases, stale locks, and dead workspaces on future cycles

The healer is implemented primarily across:

- [`healer_loop.py`](../../src/apple_flow/healer_loop.py)
- [`healer_runner.py`](../../src/apple_flow/healer_runner.py)
- [`healer_verifier.py`](../../src/apple_flow/healer_verifier.py)
- [`healer_dispatcher.py`](../../src/apple_flow/healer_dispatcher.py)
- [`healer_reconciler.py`](../../src/apple_flow/healer_reconciler.py)
- [`healer_workspace.py`](../../src/apple_flow/healer_workspace.py)
- [`healer_tracker.py`](../../src/apple_flow/healer_tracker.py)
- [`healer_scan.py`](../../src/apple_flow/healer_scan.py)
- [`healer_memory.py`](../../src/apple_flow/healer_memory.py)
- [`store.py`](../../src/apple_flow/store.py)

---

## 3. Architectural Model

### 3.1 Core loop

The main runtime pattern is:

`ingest -> queue -> claim -> lock -> workspace -> propose -> test -> verify -> publish -> reconcile`

### 3.2 Separation of responsibilities

- `GitHubHealerTracker` handles GitHub issue and PR IO.
- `HealerDispatcher` handles queue claims and lock acquisition.
- `HealerRunner` handles proposer execution, patch application, diff size checks, and test gates.
- `HealerVerifier` handles an independent validation turn.
- `HealerReconciler` repairs stale healer state after expiry or interruption.
- `HealerWorkspaceManager` creates and tears down isolated worktrees.
- `HealerMemoryService` optionally learns internal lessons from prior attempts.

### 3.3 Trust boundaries

- issue titles and bodies are untrusted input
- proposer output is untrusted until applied, tested, and verified
- GitHub is the intake and PR transport layer, not the source of truth for internal queue state
- SQLite is the internal source of truth for healer queue, attempts, locks, and lessons

---

## 4. State Model

Tracked healer issue states include:

- `queued`
- `claimed`
- `running`
- `verify_pending`
- `pr_pending_approval`
- `pr_open`
- `blocked`
- `failed`
- `resolved`

Practical meanings:

- `queued`: eligible for claim when backoff allows
- `claimed`: reserved by a worker lease
- `running`: a workspace exists and an attempt is in flight
- `pr_pending_approval`: the fix path succeeded, but guarded PR rules still block publish
- `pr_open`: a PR was created or updated
- `failed`: the issue exhausted retries or hit a terminal failure condition

The healer dashboard groups these states and reports recent attempt failure rate.

---

## 5. SQLite Storage

Flow Healer uses the main Apple Flow SQLite store and adds healer-specific tables.

### 5.1 `healer_issues`

Stores issue queue state and operational metadata such as:

- issue ID, repo, title, body, author
- labels
- priority
- issue state
- attempt count
- backoff time
- lease owner and expiry
- workspace path and branch name
- PR number and PR state
- last failure class and reason

### 5.2 `healer_attempts`

Stores per-attempt execution records such as:

- attempt ID and attempt number
- prediction source
- predicted lock set
- actual diff set
- test summary
- verifier summary
- failure class and failure reason
- started and finished timestamps

### 5.3 `healer_locks`

Stores active scope locks so overlapping issues do not edit the same paths concurrently.

### 5.4 `healer_lessons`

Stores reusable internal lessons when learning is enabled.

Each lesson includes:

- `lesson_id`
- `issue_id`
- `attempt_id`
- `lesson_kind`
- `scope_key`
- `fingerprint`
- `problem_summary`
- `lesson_text`
- `test_hint`
- `guardrail_json`
- `confidence`
- `outcome`
- `use_count`
- `last_used_at`

---

## 6. Configuration Reference

Core healer configuration lives in `.env` using the `apple_flow_` prefix.

### 6.1 Required settings for normal use

```env
apple_flow_enable_autonomous_healer=true
apple_flow_healer_mode=guarded_pr
apple_flow_healer_repo_path=/absolute/path/to/repo
apple_flow_healer_issue_required_labels=healer:ready
apple_flow_healer_pr_actions_require_approval=true
apple_flow_healer_pr_required_label=healer:pr-approved
apple_flow_healer_sandbox_mode=docker
```

### 6.2 Recommended rollout defaults

```env
apple_flow_healer_max_concurrent_issues=1
apple_flow_healer_retry_budget=8
apple_flow_healer_backoff_initial_seconds=60
apple_flow_healer_backoff_max_seconds=3600
apple_flow_healer_circuit_breaker_failure_rate=0.5
apple_flow_healer_circuit_breaker_window=20
apple_flow_healer_max_wall_clock_seconds_per_issue=1800
apple_flow_healer_max_diff_files=20
apple_flow_healer_max_diff_lines=1200
apple_flow_healer_max_failed_tests_allowed=0
apple_flow_healer_scan_enable_issue_creation=true
apple_flow_healer_scan_max_issues_per_run=5
apple_flow_healer_scan_severity_threshold=medium
apple_flow_healer_scan_default_labels=healer:ready,kind:scan
apple_flow_healer_learning_enabled=false
```

### 6.3 Important configuration meanings

#### `apple_flow_healer_mode`

Controls the intended autonomy target.

Current safe operational target is:

`guarded_pr`

#### `apple_flow_healer_issue_required_labels`

Defines which labels must be present before an issue is even considered.

#### `apple_flow_healer_trusted_actors`

Restricts intake to specific GitHub usernames.

#### `apple_flow_healer_pr_actions_require_approval`

If true, publish actions stay behind a PR approval label.

#### `apple_flow_healer_learning_enabled`

Enables the internal retrieval-and-guardrail learning layer.

Keep this off until the basic propose/test/verify/publish loop is stable.

---

## 7. Runtime Workflow

### 7.1 Issue ingestion

The healer polls GitHub for open issues that:

- are not pull requests
- match required labels
- match trusted actor rules if configured

Those issues are upserted into `healer_issues`.

### 7.2 Queue claim

The dispatcher claims one queued issue at a time, respecting:

- backoff timers
- priority
- lease expiry rules

### 7.3 Lock prediction

Before the attempt begins, the healer predicts a lock set from issue text.

This predicted scope is used to acquire preliminary locks and reduce overlap with other work.

### 7.4 Workspace creation

The healer creates an isolated workspace for the issue and assigns a branch name.

### 7.5 Proposal

The proposer is asked to return only a unified diff fenced as `diff`.

If no valid patch is returned, the attempt fails as `no_patch`.

### 7.6 Patch application

The diff is written to a patch file and applied with:

```bash
git apply --index --reject
```

If this fails, the attempt fails as `patch_apply_failed`.

### 7.7 Diff gate

The resulting staged diff is measured against:

- max changed files
- max changed lines

If limits are exceeded, the attempt fails as `diff_limit_exceeded`.

### 7.8 Test gates

The healer runs:

- targeted pytest first when issue text includes matching tests
- full `pytest -q` afterward

Tests run in Docker with networking disabled.

### 7.9 Verification

The verifier receives:

- issue context
- changed file list
- test summary
- proposer output
- optional learned lesson context

It returns strict JSON with `pass` or `fail`.

### 7.10 Publish path

If verification passes and guarded PR approval requirements are satisfied:

- the healer commits changes
- pushes the branch
- opens or updates the PR

Otherwise it pauses in `pr_pending_approval`.

### 7.11 Attempt finalization

Regardless of outcome, the healer:

- finalizes the attempt record
- stores failure class and failure reason
- optionally records a reusable lesson
- releases issue locks

---

## 8. Scanner Operation

The scanner is a separate but related path.

It can be triggered from iMessage using:

```text
system: healer scan dry-run
system: healer scan
```

The scan summary includes:

- findings total
- findings above threshold
- created issues
- deduped findings count
- skipped budget count
- failed checks
- active severity threshold

### 8.1 Dry run

Dry run never creates issues. Use this for preview and tuning.

### 8.2 Live mode

Live mode can create GitHub issues when:

- issue creation is enabled
- the finding is above threshold
- the finding is not already deduped
- run budget still allows more issue creation

---

## 9. Dashboard Reference

Run:

```text
system: healer
```

The dashboard currently reports:

- paused status
- total tracked issues
- state counts
- recent attempts and failure rate
- active lock leases
- top pending issues
- learned lessons and recent lesson usage
- top learned failure classes

### 9.1 Reading failure rate

The recent failure rate is based on recent attempts and is also used by the circuit breaker logic.

### 9.2 Reading learned lesson stats

- `Learned lessons` is the total number of retained internal lessons
- `recently_used` counts lessons that were actually injected into prompts
- `top learned failure classes` shows recurring operational patterns being captured as guardrails

---

## 10. Learning Layer

The learning layer is implemented in [`healer_memory.py`](../../src/apple_flow/healer_memory.py).

It is intentionally conservative.

### 10.1 Design goals

- improve future prompts using prior healer outcomes
- stay fully internal to Flow Healer
- avoid self-editing behavior
- avoid external dependencies or embeddings
- remain deterministic and auditable

### 10.2 What gets stored

#### Successful lessons

Stored only when:

- the final state is a successful publish-path state
- the verifier passed

These lessons usually encode:

- narrow scope patterns
- working file paths or module scope
- targeted test hints

#### Failure guardrails

Stored only for meaningful failure classes:

- `no_patch`
- `patch_apply_failed`
- `diff_limit_exceeded`
- `tests_failed`
- `verifier_failed`
- `lock_conflict`
- `lock_upgrade_conflict`

The system does not store noisy guidance from transient failures like push or network problems.

### 10.3 Retrieval strategy

Retrieval is deterministic and local.

Scoring uses:

- overlap with predicted lock scope
- overlap with actual prior diff scope
- failure-class match
- simple token overlap from issue/problem text
- confidence and outcome bias

The system returns only a short list of top lessons and injects them as:

`Relevant prior healer lessons:`

### 10.4 Safety boundary

The learning layer does not:

- rewrite source files
- rewrite prompts on disk
- modify config
- tune policies automatically
- write into `agent-office`

It only stores and retrieves internal lessons.

---

## 11. Locking and Concurrency

Flow Healer uses deterministic lock keys to reduce overlapping edits.

### 11.1 Why locking matters

Without locking, two issues might:

- touch the same file
- touch the same module
- expand scope during patching and collide later

### 11.2 Two-stage lock behavior

1. predicted locks are acquired before the attempt
2. actual locks are upgraded after the staged diff is known

If lock acquisition or upgrade fails, the issue is requeued or failed based on retry budget.

### 11.3 When to lower concurrency

Lower `apple_flow_healer_max_concurrent_issues` to `1` when:

- lock conflicts are frequent
- issues are broad or poorly scoped
- the repo is very active
- you are in early rollout

---

## 12. Retry, Backoff, and Circuit Breaker

### 12.1 Retry budget

Each healer issue has a bounded attempt count.

When the retry budget is exhausted, the issue is marked `failed`.

### 12.2 Backoff

Before the retry budget is exhausted, failed issues are requeued with exponential backoff.

This prevents tight retry loops.

### 12.3 Circuit breaker

The circuit breaker uses a recent attempt window and failure rate threshold.

When recent failure rate crosses the threshold, the healer skips the cycle instead of pushing forward blindly.

This protects the system during bad model behavior, bad repo state, or infrastructure drift.

---

## 13. GitHub Integration

Flow Healer uses GitHub for:

- issue intake
- issue lookup
- issue dedupe for scan findings
- PR creation or update
- PR state refresh

### 13.1 Required token behavior

`GITHUB_TOKEN` must be present for issue and PR operations.

### 13.2 Guarded approval path

When `apple_flow_healer_pr_actions_require_approval=true`, the issue must have the configured approval label before PR actions proceed.

Default:

`healer:pr-approved`

---

## 14. Operations Runbook

### 14.1 Safe rollout order

1. enable healer in `guarded_pr`
2. set concurrency to `1`
3. keep diff and failed-test caps strict
4. use dry-run scans first
5. validate dashboard behavior
6. validate GitHub PR path
7. only then consider enabling learning

### 14.2 Daily operator checks

- run `system: healer`
- inspect paused status
- inspect failure rate
- inspect top pending issues
- inspect lock lease count
- inspect learned lesson stats if learning is on

### 14.3 Demo mode checklist

- keep guarded mode enabled
- keep concurrency low
- prefer dry-run scan first
- narrate the queue and guardrails before narrating AI behavior

---

## 15. Troubleshooting Guide

### 15.1 Healer disabled: missing GitHub token or origin slug

Check:

- `GITHUB_TOKEN` is exported
- the repository has an `origin` remote that points to GitHub

### 15.2 Issues never get ingested

Check:

- labels match `apple_flow_healer_issue_required_labels`
- trusted actor rules are not filtering the author
- GitHub token can read issues

### 15.3 Patch apply failures are common

Likely causes:

- stale file paths in issue context
- repository drift
- broad issue descriptions

Fixes:

- make issue bodies mention the failing path or test
- keep repo state clean
- lower concurrency if related issues are overlapping

### 15.4 PR path never advances

Check:

- guarded approval label exists on the issue
- push works from the local environment
- GitHub token has PR permissions

### 15.5 Lock conflicts keep happening

Fixes:

- reduce concurrency
- make issues narrower
- include deterministic file/module scope in issue body

### 15.6 Circuit breaker opens too often

Check:

- recent failure classes in attempts
- whether tests are failing globally
- whether the verifier is rejecting shallow fixes
- whether scan-created issues are too broad

### 15.7 Learned lessons look noisy

Check:

- whether learning was enabled before the workflow stabilized
- whether failures are mostly transient
- whether issue text is too vague for meaningful retrieval

---

## 16. Security and Safety Notes

- issue text is untrusted data
- GitHub tokens should use minimum practical scopes
- keep `docker` sandbox mode in early rollout
- keep guarded PR mode enabled until there is strong evidence of reliability
- do not treat learned lessons as authority; they are operational hints
- do not remove lock contention controls or verifier checks for convenience

---

## 17. Testing and Verification

After healer behavior changes, run:

```bash
pytest -q
```

Relevant test areas include:

- healer loop behavior
- lock acquisition and release
- scan-to-issue behavior
- dashboard output
- lesson storage and retrieval

Examples:

```bash
pytest tests/test_healer_loop.py -v
pytest tests/test_healer_memory.py -v
pytest tests/test_system_command.py -v
pytest tests/test_store.py -v
```

---

## 18. Best Practices

- keep issues narrow and concrete
- include failing tests in issue text when known
- use `guarded_pr` by default
- keep `healer_max_failed_tests_allowed=0` early on
- keep scan creation budgets small
- treat the dashboard as a first-class operational surface
- only enable learning after baseline workflow quality is acceptable

---

## 19. Quick Reference

### Core commands

```text
system: healer
system: healer pause
system: healer resume
system: healer scan dry-run
system: healer scan
```

### Core labels

- `healer:ready`
- `healer:pr-approved`
- `kind:scan`

### Core files

- [`01-what-and-why.md`](./01-what-and-why.md)
- [`02-how-to-use.md`](./02-how-to-use.md)
- [`03-operations-and-troubleshooting.md`](./03-operations-and-troubleshooting.md)
- [`04-workshop-guide.md`](./04-workshop-guide.md)

---

## 20. Closing Notes

Flow Healer works best when people describe it accurately.

It is not magic, and it is not a reckless autonomous coder.

It is a monitored repair framework that can:

- find work
- queue work
- scope work
- attempt work
- verify work
- publish work under guardrails
- learn conservative internal lessons from recurring outcomes

That combination is what makes it operationally useful.
