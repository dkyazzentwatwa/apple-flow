# Agent Team Library

This directory provides a Codex-native multi-agent catalog for Apple Flow and adjacent software/business workflows.

## What You Get

- 37 self-contained team bundles under `agents/teams/`
- Team-level `preset.toml` files with `[agents.<role>]` mappings
- Role prompt files in `roles/*.toml`
- Machine-readable `agents/catalog.toml`
- iMessage-native natural language team loading/unloading

## Team Tracks

- Apple Flow Ops (12)
- Software/GTM (13)
- Business Ops (12)

## Quick Start (Natural Language)

Use plain language from iMessage:

- `list available agent teams`
- `load up the imessage-command-center team and triage my inbox`
- `what team is active`
- `unload team`

Team activation is per sender and one-shot (it applies to the next work request).

## Explicit Command Form

- `system: teams list`
- `system: team load <team-slug>`
- `system: team current`
- `system: team unload`

## Optional Manual Activation (Advanced)

Copy the desired `agents/teams/<slug>/preset.toml` entries into your project `.codex/config.toml`.

## Notes

- Presets are additive and do not change Apple Flow runtime behavior.
- Team files are designed for straightforward customization.
