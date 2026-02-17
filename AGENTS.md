# AGENTS.md

## Project
Apple Flow is a local-first macOS daemon that bridges iMessage, Apple Mail, Apple Reminders, Apple Notes, and Apple Calendar to Codex CLI. It uses stateless `codex exec` by default to avoid state corruption.

Core goals:
- Read inbound messages/tasks from iMessage, Mail, Reminders, Notes, and Calendar.
- Route allowlisted senders into Codex CLI via `codex exec`.
- Enforce safe execution with approval gates for mutating operations.
- Send replies back via AppleScript across all channels.

## Working Rules

### 1) Safety first
- Never disable sender allowlist by default.
- Keep `apple_flow_only_poll_allowed_senders=true`.
- Keep `apple_flow_require_chat_prefix=true` unless explicitly requested.
- Keep mutating workflows behind approval (`task:` / `project:`).

### 2) Startup behavior
- Use `./scripts/start_beginner.sh` for normal runs.
- The daemon is foreground and should stay running.
- If startup seems idle, check for:
  - Full Disk Access for terminal app
  - valid `apple_flow_messages_db_path`
  - valid `codex login`

### 3) Avoid iMessage loops
- Respect duplicate outbound suppression settings.
- Do not remove echo suppression without explicit user request.
- Prefer prefix-triggered general chat (`relay:`) for self-chat testing.

### 4) Config hygiene
- Keep `.env.example` aligned with runtime settings in `src/apple_flow/config.py`.
- New config fields must have:
  - sensible defaults
  - docs in `README.md`
  - sample in `.env.example`

### 5) Logging expectations
- Terminal logs should clearly show:
  - inbound row processed or ignored
  - ignore reason (echo/prefix/empty/etc.)
  - handled command kind and duration
- Avoid noisy spam logs; prefer actionable logs.

## Development Workflow

### Before changes
1. Reproduce the issue with current startup flow.
2. Identify root cause before patching.

### During changes
1. Keep patches minimal and focused.
2. Update tests for behavior changes.

### After changes
Run:
```bash
source .venv/bin/activate
pytest -q
```

Expected: all tests passing.

## Key Files
- Runtime config: `src/apple_flow/config.py`
- Main loop: `src/apple_flow/daemon.py`
- iMessage ingress/egress: `src/apple_flow/ingress.py`, `src/apple_flow/egress.py`
- Mail ingress/egress: `src/apple_flow/mail_ingress.py`, `src/apple_flow/mail_egress.py`
- Reminders ingress/egress: `src/apple_flow/reminders_ingress.py`, `src/apple_flow/reminders_egress.py`
- Notes ingress/egress: `src/apple_flow/notes_ingress.py`, `src/apple_flow/notes_egress.py`
- Calendar ingress/egress: `src/apple_flow/calendar_ingress.py`, `src/apple_flow/calendar_egress.py`
- CLI connector: `src/apple_flow/codex_cli_connector.py`
- Orchestration: `src/apple_flow/orchestrator.py`
- Startup script: `scripts/start_beginner.sh`
- Docs: `README.md`, `docs/QUICKSTART.md`

## User Experience Priorities
- Beginner-first defaults.
- Clear, explicit startup and error messages.
- Safe by default over clever by default.
- Fast feedback in terminal for every received/ignored/handled message.
