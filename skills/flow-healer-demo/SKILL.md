---
name: flow-healer-demo
description: Use when proving, demoing, or validating a healer workflow end-to-end in a disposable repo. Covers creating a tiny failing fixture, opening a narrow GitHub issue, observing worktree and Docker execution, and confirming branch push and PR creation without touching a production repo.
---

# Flow Healer Demo

Use this skill when the goal is to prove the healer path works end-to-end.

This skill is for:
- first-time healer validation
- disposable-repo demos
- “show me the exact worktree/Docker/PR path”
- reproducing or validating a healer fix under controlled conditions

Keep this separate from normal ops so everyday healer usage stays lean.

## Demo Defaults

Use these defaults unless the user explicitly wants something riskier:
- disposable GitHub repo
- one tiny failing test
- one narrow issue
- guarded human review after PR creation

Avoid demos in production repos unless the user explicitly asks for that risk.

## Standard Demo Flow

### 1) Bootstrap a disposable repo

Use the helper when you want a deterministic Python demo fixture:

```bash
python skills/flow-healer-demo/scripts/bootstrap_demo_repo.py /tmp/healer-demo-repo
```

This creates:
- a minimal Python project
- one intentionally broken function
- one failing pytest
- `.gitignore`

### 2) Create a single narrow issue

The issue should:
- name the broken behavior
- state the expected outcome
- include a minimal acceptance condition such as `pytest -q`
- optionally mention the exact test path

### 3) Observe the real healer path

Capture:
- issue URL
- worktree path
- branch name
- Docker gate result
- verifier result
- PR URL

For the detailed step sequence, read:
- `references/demo-flow.md`

### 4) Treat failure as signal

If the demo fails, do not widen the scope.
Instead:
- identify the exact failing step
- fix that infrastructure assumption
- repeat the same narrow issue

## Done Criteria

A demo is complete when you can point to:
- the disposable repo
- the healer worktree
- the Docker test output
- the pushed branch
- the resulting PR or the exact failure checkpoint
