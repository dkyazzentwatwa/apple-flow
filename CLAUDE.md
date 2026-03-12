# CLAUDE.md

Claude Code entry point for this repository.

Last updated: 2026-03-12

`AGENTS.md` is the canonical repo-wide guide. Read it first and treat this file as a Claude-specific companion, not a separate source of truth.

## Read Order

1. `AGENTS.md`
2. `docs/PROJECT_REFERENCE.md`
3. `README.md`
4. `docs/ENV_SETUP.md`
5. `SECURITY.md`

## Project Snapshot

Apple Flow is a local-first macOS daemon that routes work from iMessage, Apple Mail, Apple Reminders, Apple Notes, Apple Calendar, and the Admin API through policy checks, orchestration, connector execution, and Apple-app egress.

Current version: `0.6.0`

Main runtime modules:

- `src/apple_flow/daemon.py`
- `src/apple_flow/orchestrator.py`
- `src/apple_flow/commanding.py`
- `src/apple_flow/store.py`
- `src/apple_flow/config.py`
- `src/apple_flow/main.py`
- `src/apple_flow/companion.py`
- `src/apple_flow/memory.py`
- `src/apple_flow/memory_v2.py`

## Claude-Specific Notes

- Claude connector module: `src/apple_flow/claude_cli_connector.py`
- Connector key: `apple_flow_connector=claude-cli`
- Auth prerequisite: `claude auth login`
- Main Claude settings:
  - `apple_flow_claude_cli_command`
  - `apple_flow_claude_cli_model`
  - `apple_flow_claude_cli_context_window`
  - `apple_flow_claude_cli_dangerously_skip_permissions`
  - `apple_flow_claude_cli_tools`
  - `apple_flow_claude_cli_allowed_tools`

If you change Claude connector behavior or config, also update:

- `AGENTS.md`
- `GEMINI.md` if the shared project surface changed
- `README.md`
- `.env.example`
- `docs/ENV_SETUP.md`

## Common Commands

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

pytest -q
python -m apple_flow daemon
python -m apple_flow admin
python -m apple_flow version
python -m apple_flow tools --list
```

## Commands Users Can Send

Parsed in `src/apple_flow/commanding.py`:

- Natural chat or `relay:`
- `idea:`
- `plan:`
- `task:`
- `project:`
- `voice:`
- `voice-task:`
- `help`, `health`, `history:`, `usage`, `logs`, `status`
- `approve <id>`, `deny <id>`, `deny all`
- `system: ...`

## Safety Rules To Preserve

- Allowlisted senders only by default
- Approval gates for mutating work
- Approval requester verification
- Workspace boundaries via `allowed_workspaces`
- Read-only iMessage DB access
- Duplicate outbound suppression
- Rate limiting

## Contributor Expectations

- Run `pytest -q` after behavior changes.
- Update docs when config, commands, connectors, or admin endpoints change.
- Prefer `rg` for code search.
- Defer to `AGENTS.md` when this file and another doc disagree.
