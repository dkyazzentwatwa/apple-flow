# Codex Relay

Codex Relay is a local-first daemon that bridges iMessage on macOS to Codex CLI/App Server, with policy gating, approval workflows, and an admin API. By default, it uses the stateless CLI connector to avoid state corruption issues.

**Text yourself to chat with Claude, brainstorm ideas, and execute tasks in your workspace!**

## 🚀 Quick Start

**New to Codex Relay?** See **[QUICKSTART.md](QUICKSTART.md)** for complete setup instructions.

**TL;DR** for experienced users:

```bash
# 1. Authenticate with Codex
codex login

# 2. One-command setup with auto-start at boot
./scripts/setup_autostart.sh
# Edit .env when prompted, then grant Full Disk Access to Python binary

# OR manual foreground run
cp .env.example .env
nano .env  # Set your phone number and workspace
./scripts/start_beginner.sh
```

## Logs and Monitoring

When running as a service (via `setup_autostart.sh`), logs are stored in:

```bash
logs/codex-relay.log       # Standard output
logs/codex-relay.err.log   # Errors and diagnostics
```

**View logs in real-time:**
```bash
tail -f logs/codex-relay.log      # Watch daemon activity
tail -f logs/codex-relay.err.log  # Watch for errors
```

**Check service status:**
```bash
launchctl list | grep codex.relay  # Should show PID if running
```

## Features

- Poll inbound iMessages from local Apple Messages database
- Map sender handles to persistent Codex threads
- Human-in-the-loop approval for mutating tasks
- Workspace allowlist policy enforcement
- Local FastAPI admin endpoints
- Launchd service profile for always-on operation
- **NEW**: Stateless CLI connector (default) - eliminates state corruption freezes
- **NEW**: Database connection caching + indexes for performance
- **NEW**: Approval sender verification for security
- **NEW**: Graceful shutdown with signal handling

## Documentation

- **[QUICKSTART.md](QUICKSTART.md)** - Complete beginner's guide
- **[CLAUDE.md](CLAUDE.md)** - Architecture and development guide
- **[.env.example](.env.example)** - All configuration options

Manual setup:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pytest -q
```

Run the relay API:

```bash
uvicorn codex_relay.main:app --reload
```

Run the relay daemon:

```bash
python -m codex_relay daemon
```

Run admin API only:

```bash
python -m codex_relay admin
```

## Commands Over iMessage

- `relay: <message>`: general chat mode (default safety trigger)
- `idea: <prompt>`: brainstorming and options
- `plan: <goal>`: implementation plan only (non-mutating)
- `task: <instruction>`: creates an approval request before execution
- `project: <spec>`: project concierge pipeline with approval gate
- `clear context` / `new chat`: reset sender thread and start fresh context
- `approve <request_id>`: executes a queued request
- `deny <request_id>`: cancels a queued request
- `status`: pending approval count

If `codex_relay_send_startup_intro=true`, relay sends an intro iMessage on startup with current workspace + command list.

## Security Defaults

- Allowlisted senders only
- Workspace allowlist only
- Human approval required for mutating requests (`task:` and `project:`)
- Per-sender rate limiting

## Codex Authentication

Authenticate locally once:

```bash
codex login
```

Relay uses `codex exec` by default (stateless CLI connector) to avoid thread state corruption. You can switch to the app-server connector by setting `codex_relay_use_codex_cli=false` in `.env`.

## Beginner Checklist

1. Make sure iMessage is signed in on this Mac.
2. Run `codex login` once.
3. Put your own phone number in `/Users/cypher/Public/code/codex-flow/.env` as `codex_relay_allowed_senders`.
4. Put safe folders in `codex_relay_allowed_workspaces`.
5. Start the daemon and text commands like `idea:`, `plan:`, or `task:`.

## Important Safety Behavior

- On first start, Codex Relay now skips historical messages by default.
- It does not auto-message blocked senders unless you explicitly enable it.
- It can poll only allowlisted senders at SQL-query time.
- It can require a chat prefix (default `relay:`) so echoed self-messages are ignored.
- Keep these in `.env` for safest behavior:
  - `codex_relay_process_historical_on_first_start=false`
  - `codex_relay_notify_blocked_senders=false`
  - `codex_relay_notify_rate_limited_senders=false`
  - `codex_relay_only_poll_allowed_senders=true`
  - `codex_relay_require_chat_prefix=true`
  - `codex_relay_chat_prefix=relay:`
