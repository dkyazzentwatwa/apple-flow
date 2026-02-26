# Agent Team Library

This directory provides a Codex-native multi-agent catalog for Apple Flow and adjacent software/business workflows.

## What You Get

- 36 self-contained team bundles under `agents/teams/`
- Team-level `preset.toml` files with `[agents.<role>]` mappings
- Role prompt files in `roles/*.toml`
- Machine-readable `agents/catalog.toml`
- Activation scripts:
  - `scripts/agents/list_teams.sh`
  - `scripts/agents/use_team.sh <team-slug>`

## Team Tracks

- Apple Flow Ops (12)
- Software/GTM (12)
- Business Ops (12)

## Quick Start

```bash
./scripts/agents/list_teams.sh
./scripts/agents/use_team.sh imessage-command-center
```

This writes a managed block into `./.codex/config.toml` by default.

## Manual Activation

Copy the desired `agents/teams/<slug>/preset.toml` entries into your project `.codex/config.toml`.

## Notes

- Presets are additive and do not change Apple Flow runtime behavior.
- Team files are designed for straightforward customization.
