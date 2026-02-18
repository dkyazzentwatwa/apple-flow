# Apple Flow

Apple Flow is a local-first daemon that bridges iMessage and Apple Mail on macOS to Codex CLI/App Server, with policy gating, approval workflows, and an admin API. By default, it uses the stateless CLI connector to avoid state corruption issues.

**Text or email yourself to chat with Claude, brainstorm ideas, and execute tasks in your workspace!**

## 🚀 Quick Start

**New to Apple Flow?** See **[QUICKSTART.md](docs/QUICKSTART.md)** for complete setup instructions.

**TL;DR** for experienced users:

```bash
# 1. Authenticate — pick your AI backend (only one needed):
codex login   # if using Codex (default)
claude auth login  # if using Claude Code CLI

# 2. One-command setup with auto-start at boot
./scripts/setup_autostart.sh
# Edit .env when prompted, then grant Full Disk Access to Python binary

# OR manual foreground run
cp .env.example .env
nano .env  # Set your phone number, workspace, and connector
./scripts/start_beginner.sh
```

## Logs and Monitoring

When running as a service (via `setup_autostart.sh`), logs are stored in:

```bash
logs/apple-flow.log       # Standard output
logs/apple-flow.err.log   # Errors and diagnostics
```

**View logs in real-time:**
```bash
tail -f logs/apple-flow.err.log  # All daemon output (Python logging goes to stderr)
```

**Check service status:**
```bash
launchctl list local.apple-flow  # Should show PID and exit status 0
```

**Start / stop / restart the service:**
```bash
launchctl start local.apple-flow
launchctl stop local.apple-flow

# Restart (stop then start):
launchctl stop local.apple-flow && launchctl start local.apple-flow
```

## Features

- **iMessage** — poll local Messages database for inbound commands
- **Apple Mail** — text OR email Claude with threaded replies and custom signatures
- **Apple Reminders** — incomplete reminders in a designated list become Apple Flow tasks
- **Apple Notes** — notes tagged with `!!agent` (configurable) trigger tasks; optional per-turn logging of AI responses to an "agent-logs" folder
- **Notes timeout hardening** — configurable Notes fetch timeout/retry controls to reduce AppleScript stall impact
- **Apple Calendar** — events in a designated calendar become scheduled tasks when due
- **Stateless CLI connector** (default) — `codex exec` per turn, eliminates state corruption freezes
- **Claude Code CLI connector** — swap to `claude -p` by setting `apple_flow_connector=claude-cli`
- **Model selection** — `apple_flow_codex_cli_model=gpt-5.3-codex` for Codex, `apple_flow_claude_cli_model=claude-sonnet-4-6` for Claude
- **Claude tool control** — optional `apple_flow_claude_cli_tools` / `apple_flow_claude_cli_allowed_tools` (for example: `WebSearch`)
- **Multi-workspace routing** — `@alias` prefix routes to different workspace paths
- **Human-in-the-loop approval** — mutating `task:` / `project:` commands require explicit approval
- **Workspace allowlist** — Codex can only access configured paths
- **Progress streaming** — periodic iMessage updates during long tasks
- **File attachments** — read inbound attachments and include in prompts
- **Conversation memory** — auto-inject recent history into prompts
- **Health dashboard** — `health:` command shows uptime, sessions, pending approvals
- **Admin API** — FastAPI endpoints for sessions, approvals, audit log, programmatic task submission
- **Launchd service** — one-command setup for always-on auto-start at boot

## Documentation

- **[QUICKSTART.md](docs/QUICKSTART.md)** - Complete beginner's guide
- **[BEGINNER_SETUP_10_MIN.md](docs/BEGINNER_SETUP_10_MIN.md)** - 10-minute setup guide
- **[AUTO_START_SETUP.md](docs/AUTO_START_SETUP.md)** - Auto-start at boot setup
- **[ENV_SETUP.md](docs/ENV_SETUP.md)** - Full `.env` configuration reference (all options, defaults, examples)
- **[CLAUDE.md](CLAUDE.md)** - Architecture and development guide
- **[.env.example](.env.example)** - Annotated configuration file

Manual setup:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pytest -q
```

Run the relay API:

```bash
uvicorn apple_flow.main:app --reload
```

Run the relay daemon:

```bash
python -m apple_flow daemon
```

Run admin API only:

```bash
python -m apple_flow admin
```

## Commands Over iMessage or Email

Same commands work via iMessage or email (when mail integration is enabled):

- `relay: <message>` — general chat mode (default safety trigger)
- `idea: <prompt>` — brainstorming and options
- `plan: <goal>` — implementation plan only (non-mutating)
- `task: <instruction>` — creates an approval request before execution
- `project: <spec>` — project concierge pipeline with approval gate
- `approve <request_id>` — executes a queued request
- `deny <request_id>` — cancels a queued request
- `status` — pending approval count
- `health:` — daemon uptime, session count, run states
- `history: [query]` — recent messages or search by keyword
- `clear context` / `new chat` — reset sender thread and start fresh context
- `system: stop` — gracefully shut down the daemon
- `system: restart` — shut down (launchd auto-restarts if configured)

**Multi-workspace routing:** prefix any command with `@alias` to target a specific workspace:
```
task: @web-app deploy to staging
relay: @api show recent errors
```

### Email Integration (Optional)

Enable Apple Mail polling in `.env`:
```bash
apple_flow_enable_mail_polling=true
apple_flow_mail_allowed_senders=your.email@example.com
apple_flow_mail_from_address=your.email@example.com
apple_flow_mail_max_age_days=2
```

Features:
- Replies stay in the same email thread
- Custom signature: "Apple Flow 🤖, Your 24/7 Assistant"
- Only processes recent emails (2 days by default)
- Works alongside iMessage seamlessly

If `apple_flow_send_startup_intro=true`, relay sends an intro iMessage on startup with current workspace + command list.

### Notes Logging (Optional)

Log every AI response as a new Apple Note for easy review outside iMessage:

```bash
apple_flow_enable_notes_logging=true
apple_flow_notes_log_folder_name=agent-logs  # default
```

Each completed AI turn (chat, idea, plan, task) creates a note in the configured folder. Notes are titled `[<command>] <request preview> — <timestamp>` and contain the full request and response. The folder is created automatically if it does not exist.

This is independent of the notes polling ingress (`enable_notes_polling`) — you can enable logging without enabling Notes as a task source.

## Security Defaults

- Allowlisted senders only
- Workspace allowlist only
- Human approval required for mutating requests (`task:` and `project:`)
- Per-sender rate limiting

## Authentication

Apple Flow supports two AI backends. Authenticate once for whichever you're using:

```bash
# Option A — Codex (default)
codex login

# Option B — Claude Code CLI
claude auth login
```

### Choosing a connector

Set `apple_flow_connector` in `.env`:

```bash
apple_flow_connector=codex-cli    # default — uses `codex exec`
apple_flow_connector=claude-cli   # uses `claude -p`
```

Both are stateless (one process per turn). The `codex-app-server` value is still accepted for legacy setups but is deprecated.

## Beginner Checklist

1. Make sure iMessage is signed in on this Mac.
2. Authenticate your AI backend — run `codex login` (Codex) **or** `claude auth login` (Claude).
3. Put your own phone number in `.env` as `apple_flow_allowed_senders`.
4. Put safe folders in `apple_flow_allowed_workspaces`.
5. Set `apple_flow_connector=codex-cli` or `apple_flow_connector=claude-cli` in `.env`.
6. Start the daemon and text commands like `idea:`, `plan:`, or `task:`.

## Important Safety Behavior

- On first start, Apple Flow now skips historical messages by default.
- It does not auto-message blocked senders unless you explicitly enable it.
- It can poll only allowlisted senders at SQL-query time.
- It can require a chat prefix (default `relay:`) so echoed self-messages are ignored.
- Keep these in `.env` for safest behavior:
  - `apple_flow_process_historical_on_first_start=false`
  - `apple_flow_notify_blocked_senders=false`
  - `apple_flow_notify_rate_limited_senders=false`
  - `apple_flow_only_poll_allowed_senders=true`
  - `apple_flow_require_chat_prefix=true`
  - `apple_flow_chat_prefix=relay:`
