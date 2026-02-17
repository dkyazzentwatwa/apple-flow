# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Codex Relay is a local-first daemon that bridges iMessage on macOS to Codex CLI/App Server. It polls the local Messages database, routes allowlisted senders to Codex, enforces approval workflows for mutating operations, and replies via AppleScript. By default, it uses the stateless CLI connector (`codex exec`) to avoid state corruption issues.

## Development Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

# Run tests
pytest -q

# Run single test file
pytest tests/test_orchestrator.py -v

# Run single test
pytest tests/test_orchestrator.py::test_function_name -v

# Start daemon (foreground, polls iMessages)
python -m codex_relay daemon

# Start admin API only
python -m codex_relay admin

# Beginner quickstart (creates venv, runs tests, starts daemon)
./scripts/start_beginner.sh

# One-command auto-start setup (does everything!)
./scripts/setup_autostart.sh
# Creates venv, installs deps, configures service, enables auto-start at boot
# Only manual step: edit .env and grant Full Disk Access
# See docs/AUTO_START_SETUP.md for details

# Uninstall auto-start
./scripts/uninstall_autostart.sh
```

## Architecture

### Data Flow
```
iMessage DB → Ingress → Policy → Orchestrator → Codex Connector → Egress → AppleScript send
                                     ↓
                                   Store (SQLite state + approvals)
```

### Core Modules (src/codex_relay/)

| Module | Responsibility |
|--------|---------------|
| `daemon.py` | Main polling loop, graceful shutdown, signal handling |
| `orchestrator.py` | Command routing, approval gates, prompt construction |
| `ingress.py` | Reads from macOS Messages chat.db |
| `egress.py` | Sends iMessages via AppleScript, deduplicates outbound |
| `policy.py` | Sender allowlist, rate limiting |
| `store.py` | Thread-safe SQLite with connection caching and indexes |
| `config.py` | Pydantic settings with `codex_relay_` env prefix, path resolution |
| `commanding.py` | Parses command prefixes (idea:, plan:, task:, etc.) |
| `codex_cli_connector.py` | Stateless CLI connector using `codex exec` (default, avoids state corruption) |
| `codex_connector.py` | Stateful app-server connector via JSON-RPC (fallback option) |
| `main.py` | FastAPI admin endpoints |
| `protocols.py` | Protocol interfaces for type-safe component injection |
| `utils.py` | Shared utilities (normalize_sender) |
| `models.py` | Data models and enums (RunState, ApprovalStatus) |

### Command Types

- **Non-mutating** (execute immediately): `relay:`, `idea:`, `plan:`
- **Mutating** (require approval): `task:`, `project:`
- **Control**: `approve <id>`, `deny <id>`, `status`, `clear context`

### Key Safety Invariants

- `only_poll_allowed_senders=true` filters at SQL query time
- `require_chat_prefix=true` ignores messages without `relay:` prefix
- Mutating commands always go through approval workflow
- **Approval sender verification**: only the original requester can approve/deny their requests
- Duplicate outbound suppression prevents echo loops
- Graceful shutdown with SIGINT/SIGTERM handling

## Configuration

All settings use `codex_relay_` env prefix. Key settings in `.env`:

- `codex_relay_allowed_senders` - comma-separated phone numbers
- `codex_relay_allowed_workspaces` - paths Codex may access (auto-resolved to absolute)
- `codex_relay_messages_db_path` - usually `~/Library/Messages/chat.db`
- `codex_relay_use_codex_cli` - use CLI connector instead of app-server (default: true, recommended)
- `codex_relay_codex_cli_command` - path to codex binary (default: "codex")
- `codex_relay_codex_cli_context_window` - number of recent exchanges to include as context (default: 3)
- `codex_relay_codex_app_server_cmd` - app-server command (only used if use_codex_cli=false)
- `codex_relay_codex_turn_timeout_seconds` - how long to wait for Codex responses (default: 300s/5min)

See `.env.example` for full list. Changes to config fields require updates to both `config.py` and `.env.example`.

## Testing

Tests use pytest-asyncio with `asyncio_mode = "auto"`. Shared test fixtures (FakeStore, FakeConnector, FakeEgress) are in `tests/conftest.py`.

```bash
# Run all tests
pytest -q

# Run with verbose output
pytest -v

# Run specific test module
pytest tests/test_ingress.py -v

# Key test files
tests/test_orchestrator.py      # Core orchestration logic
tests/test_approval_security.py # Sender verification
tests/test_store_connection.py  # Connection caching, thread safety
tests/test_egress_chunking.py   # Message chunking, fingerprinting
tests/test_utils.py             # Shared utilities
```

## Security Model

- **Sender allowlist**: Only messages from configured senders are processed
- **Approval workflow**: Mutating operations (task:, project:) require explicit approval
- **Sender verification**: Approvals can only be granted/denied by the original requester
- **Workspace restrictions**: Codex can only access paths in `allowed_workspaces`

## Prerequisites

- macOS with iMessage signed in
- Full Disk Access granted to terminal app (for reading chat.db)
- `codex login` run once for Codex authentication
