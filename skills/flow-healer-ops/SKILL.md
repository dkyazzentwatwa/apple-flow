---
name: flow-healer-ops
description: Use when setting up, operating, reviewing, or troubleshooting a GitHub issue-driven auto-healing workflow in any repo. Covers guarded rollout, preflight checks, label gating, worktree and Docker test execution, verifier flow, PR review handoff, and recovery from stuck or failed healer runs. Uses Apple Flow as a reference example, not a requirement.
---

# Flow Healer Ops

Use this skill for normal healer operations in any GitHub repo.

This skill is the default path for:
- setting up a healer loop
- validating preconditions before enabling autonomous healing
- running guarded PR workflows safely
- understanding what happens after a healer PR opens
- diagnosing failed Docker gates, verifier failures, label-gate stalls, or stuck worktrees

## Safe Defaults

Start with these defaults unless the user explicitly wants a more aggressive rollout:
- disposable or low-risk repo for first validation
- guarded PR flow before any auto-merge path
- single-issue concurrency for early rollout
- explicit issue labels for intake and PR advancement
- human review after PR creation

Prefer a narrow, deterministic issue first:
- one failing test
- one obvious fix
- one repo

## Primary Workflow

### 1) Run preflight first

From the target repo root:

```bash
python skills/flow-healer-ops/scripts/healer_preflight.py .
```

Use the output to confirm:
- git repo and remote exist
- Docker is available
- repo has a likely default branch
- healer auth assumptions are plausible
- Python project/test signals are present when using Python-based gates

If preflight reports major blockers, fix them before attempting a live run.

For preflight interpretation and rollout defaults, read:
- `references/preflight.md`

### 2) Confirm intake and trust model

For v1, standardize on GitHub issue intake:
- issue labels define eligibility
- issue text is untrusted input
- PR publication happens only after test and verifier gates pass

Guarded mode should require:
- intake label such as `healer:ready`
- PR advancement label such as `healer:pr-approved`

### 3) Expect this runtime path

The normal healer lifecycle is:
1. ingest labeled issue
2. create isolated worktree and healer branch
3. generate and apply patch
4. run Docker test gates in the worktree
5. run an independent verifier pass
6. commit and push the healer branch
7. open or update a PR
8. hand off to human review

For the live runbook, read:
- `references/live-runbook.md`

### 4) Handle the PR correctly

Once the healer opens a PR, the normal human workflow is:
1. review the diff
2. confirm test/verifier output
3. move from draft to reviewable state if appropriate
4. merge only after repo checks and human review are satisfied

The healer’s job is to get to a safe, reviewable branch and PR.
The human’s job is the final judgment call.

### 5) Recover cleanly when something fails

Use failure signatures to decide the next move:
- Docker/test bootstrap failure: fix container gate assumptions first
- verifier failure: inspect diff scope and correctness
- label-gate stall: confirm required labels are present
- push/PR failure: confirm auth, remote access, and branch state
- repeated failures: pause healer, inspect recent attempts, then retry with a narrower issue

For concrete failure handling, read:
- `references/failure-modes.md`

## Apple Flow Example

Apple Flow is the reference implementation for this skill’s patterns:
- guarded GitHub issue intake
- isolated worktrees
- Docker-based test gates
- verifier split
- PR handoff

Only load the Apple Flow reference when you need concrete file names or repo-specific examples:
- `references/apple-flow-example.md`

## Done Criteria

Before finishing a healer-ops task, confirm:
- rollout mode is explicit
- intake labels and trust boundary are clear
- Docker/worktree/test path has been validated or diagnosed
- PR handoff guidance is clear
- any blocker is identified with the next corrective step
