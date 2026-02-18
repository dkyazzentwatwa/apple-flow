---
name: apple-flow-ops
description: Use when working on Apple Flow in the apple-flow repository. Enforces safe defaults, beginner-first startup, focused debugging, config hygiene, and required verification.
---

# Codex Flow Ops

## Overview
Use this skill for changes, debugging, and operations in the apple-flow repository.

Apple Flow is a local-first macOS daemon bridging iMessage, Mail, Reminders, Notes, and Calendar to Claude/Codex CLI. This skill keeps workflow safe-by-default and beginner-friendly while giving concrete operator steps.

## When to Use
Use this skill when the task involves any of:
- Starting or troubleshooting the relay daemon
- Editing relay behavior in `src/apple_flow/*`
- Updating runtime config fields or `.env.example`
- Improving ingress/egress/orchestration/logging behavior
- Verifying safety gates around sender allowlist, chat prefix, or approvals

## Non-Negotiable Safety Defaults
Keep these defaults unless the user explicitly asks otherwise:
- `apple_flow_only_poll_allowed_senders=true`
- `apple_flow_require_chat_prefix=true`
- `apple_flow_chat_prefix=relay:`
- `apple_flow_process_historical_on_first_start=false`
- `apple_flow_notify_blocked_senders=false`
- `apple_flow_notify_rate_limited_senders=false`
- Keep mutating workflows behind approval (`task:` and `project:`)

Do not remove duplicate/echo suppression without explicit request:
- `apple_flow_suppress_duplicate_outbound_seconds`
- `IMessageEgress.was_recent_outbound(...)`

## Primary Workflow

### 1) Reproduce First
Use beginner path before changing code:
```bash
cd <path-to-apple-flow>
./scripts/start_beginner.sh
```

If startup appears idle, verify:
- Full Disk Access for terminal host app
- `apple_flow_messages_db_path` points to a real `chat.db`
- `codex login` is completed

### 2) Identify Root Cause
Inspect the right layer first:
- Runtime settings: `src/apple_flow/config.py`
- Polling/loop/logs: `src/apple_flow/daemon.py`
- Messages DB reads: `src/apple_flow/ingress.py`
- iMessage send and suppression: `src/apple_flow/egress.py`
- command routing and approvals: `src/apple_flow/orchestrator.py`

Prefer minimal, focused patches once the cause is clear.

### 3) Keep Config Hygiene
For every new config field:
1. Add sensible default in `src/apple_flow/config.py`
2. Document in `README.md`
3. Add sample in `.env.example`

If runtime behavior changes, update beginner-facing guidance:
- `BEGINNER_SETUP_10_MIN.md`

### 4) Preserve Logging Quality
Terminal logs should stay concise and actionable:
- Inbound row processed or ignored
- Explicit ignore reason (echo, missing prefix, empty, blocked, rate-limited)
- Handled command kind + duration

Avoid noisy repeated logs; keep throttled warnings for recurring failures.

### 5) Verify Before Completion
Run from repo root:
```bash
source .venv/bin/activate
pytest -q
```

Expected result:
- All tests passing

If tests fail, report failing tests and root cause before claiming completion.

## Common Task Playbooks

### A) Startup Failures
1. Run `./scripts/start_beginner.sh`
2. Fix reported safety stop in `.env` (senders, DB path, placeholders)
3. Confirm Messages DB readability and Full Disk Access
4. Re-run script and confirm daemon foreground readiness

### B) No Replies in iMessage
1. Confirm sender matches `apple_flow_allowed_senders`
2. Confirm message uses `relay:` prefix (or explicit command prefix)
3. Confirm sender allowlist polling is on and non-empty
4. Check logs for ignore reason (`ignored_missing_chat_prefix`, echo suppression, rate limit)

### C) Approval Flow Confusion (`task:` / `project:`)
1. Confirm plan is produced first
2. Confirm approval request id issued
3. Confirm only original sender can approve/deny
4. Confirm expiration handling and status transitions are preserved

## Acceptance Checklist
Before finishing a apple-flow task, confirm:
- Safety defaults preserved (unless explicitly changed by request)
- Patch is minimal and scoped to root cause
- Config/docs/examples are in sync if config changed
- `pytest -q` passes
- Final summary includes what changed, why, and how it was verified
