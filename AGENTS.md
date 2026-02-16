# AGENTS.md

## Project
Codex Relay is a local-first iMessage bridge to Codex App Server.

Core goals:
- Read inbound iMessages from local Messages DB.
- Route allowlisted senders into Codex threads.
- Enforce safe execution with approval gates.
- Send concise replies back via AppleScript.

## Working Rules

### 1) Safety first
- Never disable sender allowlist by default.
- Keep `codex_relay_only_poll_allowed_senders=true`.
- Keep `codex_relay_require_chat_prefix=true` unless explicitly requested.
- Keep mutating workflows behind approval (`task:` / `project:`).

### 2) Startup behavior
- Use `./scripts/start_beginner.sh` for normal runs.
- The daemon is foreground and should stay running.
- If startup seems idle, check for:
  - Full Disk Access for terminal app
  - valid `codex_relay_messages_db_path`
  - valid `codex login`

### 3) Avoid iMessage loops
- Respect duplicate outbound suppression settings.
- Do not remove echo suppression without explicit user request.
- Prefer prefix-triggered general chat (`relay:`) for self-chat testing.

### 4) Config hygiene
- Keep `.env.example` aligned with runtime settings in `src/codex_relay/config.py`.
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
- Runtime config: `src/codex_relay/config.py`
- Main loop: `src/codex_relay/daemon.py`
- Ingress: `src/codex_relay/ingress.py`
- Egress: `src/codex_relay/egress.py`
- Orchestration: `src/codex_relay/orchestrator.py`
- Startup script: `scripts/start_beginner.sh`
- Docs: `README.md`, `BEGINNER_SETUP_10_MIN.md`

## User Experience Priorities
- Beginner-first defaults.
- Clear, explicit startup and error messages.
- Safe by default over clever by default.
- Fast feedback in terminal for every received/ignored/handled message.
