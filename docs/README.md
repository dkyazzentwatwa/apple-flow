# Apple Flow Docs

Use this folder as a product and setup docs surface first. If a page is primarily for maintainers, prompt libraries, or historical reference, it should live under a subfolder instead of the top level.

## Start Here

- [QUICKSTART.md](./QUICKSTART.md) for the primary installation and onboarding flow
- [AI_INSTALL_MASTER_PROMPT.md](./AI_INSTALL_MASTER_PROMPT.md) for AI-led setup in Codex, Claude, Cline, or Gemini CLI
- [ENV_SETUP.md](./ENV_SETUP.md) for the full `.env` and configuration reference
- [AUTO_START_SETUP.md](./AUTO_START_SETUP.md) for launchd, Full Disk Access, and service troubleshooting
- [PROJECT_REFERENCE.md](./PROJECT_REFERENCE.md) for architecture and contributor orientation

## Specialized Docs

- [SKILLS_AND_MCP.md](./SKILLS_AND_MCP.md) for Codex and Claude skills or MCP setup
- [MACOS_GUI_APP_EXPORT.md](./MACOS_GUI_APP_EXPORT.md) for exporting or running the macOS dashboard app from source
- [harness/README.md](./harness/README.md) for harness engineering, evals, and rollout docs
- [launchd/README.md](./launchd/README.md) for the sample launchd plist and related notes

## Internal And Archived Material

- [internal/prompt-packs/](./internal/prompt-packs/) for prompt libraries, shortcut helpers, and maintainer packs
- [internal/automation/](./internal/automation/) for scheduled task templates and automation-oriented prompt sets
- [archive/](./archive/) for historical plans and superseded setup docs kept for reference only

## Docs Structure Rules

- Keep top-level `docs/` focused on users, setup, and canonical project reference material.
- Put prompt packs, helper templates, and maintainer-only operating docs under `docs/internal/`.
- Put dated plans, retired guides, and superseded docs under `docs/archive/`.
- When setup or config behavior changes, update the canonical docs instead of adding another overlapping walkthrough.
