# Agent Teams for Codex

Apple Flow now ships a codex-native multi-agent team library under `/agents`.

## Layout

- `agents/catalog.toml` — machine-readable inventory of all teams
- `agents/teams/<slug>/TEAM.md` — team intent and usage contract
- `agents/teams/<slug>/preset.toml` — codex role map for that team
- `agents/teams/<slug>/roles/*.toml` — role-level prompts

## Categories

- Apple Flow Ops (12)
- Software/GTM (12)
- Business Ops (12)

## Activation

List teams:

```bash
./scripts/agents/list_teams.sh
```

Activate one team preset into `.codex/config.toml`:

```bash
./scripts/agents/use_team.sh <team-slug>
```

The activation script writes a managed block and keeps a timestamped backup.

## iMessage-Native Team Control

You can control team loading directly from iMessage.

### Natural commands

- `list available agent teams`
- `load up the codebase-exploration-team`
- `load up the codebase-exploration-team and research new features`
- `switch to customer-support-resolution-team and analyze these emails from test@gmail.com`
- `what team is active`
- `unload team`

### Explicit commands

- `system: teams list`
- `system: team load <team-slug>`
- `system: team current`
- `system: team unload`

### Behavior

- Team activation is **per sender** (allowlisted users do not overwrite each other).
- Team activation is **one-shot**:
  - The loaded team is consumed by the next work command (`idea`, `plan`, `task`, `project`).
  - Non-work commands (`status`, `help`, etc.) do not consume it.
- Combined command support:
  - If you send `load ... and ...`, Apple Flow loads the team and executes the remainder in the same turn.
  - If remainder has no explicit prefix, Apple Flow defaults to `plan:` for safety.

### Unknown team handling

If a requested team slug does not exist, Apple Flow returns close matches plus a short list of valid team slugs.

### Connector behavior

- `codex-cli`: team preset is applied at runtime.
- Other connectors (`claude-cli`, `gemini-cli`, `kilo-cli`, `cline`): Apple Flow injects the selected team `TEAM.md` as prompt fallback context for that turn.

## Manual mode

You can manually copy from `agents/teams/<slug>/preset.toml` into your project-level `.codex/config.toml`.

## Guardrails

- Team presets are additive and do not modify Apple Flow daemon runtime behavior.
- Approval-sensitive actions should remain behind explicit approval in execution workflows.
