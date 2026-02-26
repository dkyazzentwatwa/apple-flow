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

## Manual mode

You can manually copy from `agents/teams/<slug>/preset.toml` into your project-level `.codex/config.toml`.

## Guardrails

- Team presets are additive and do not modify Apple Flow daemon runtime behavior.
- Approval-sensitive actions should remain behind explicit approval in execution workflows.
