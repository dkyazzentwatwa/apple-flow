# Gemini CLI Connector Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add first-class `gemini-cli` connector support to Apple Flow with default model `gemini-3-flash-preview`, wired through config, daemon selection, setup tooling, scripts, docs, and tests.

**Architecture:** Add a new stateless connector module (`GeminiCliConnector`) following the existing `CodexCliConnector`/`ClaudeCliConnector` design: per-turn subprocess execution, per-sender context buffer, and consistent error handling. Wire it into connector-selection surfaces (`config.py`, `daemon.py`, setup CLI tooling, and shell setup scripts) so users can choose `apple_flow_connector=gemini-cli` end-to-end.

**Tech Stack:** Python 3.11, pytest, subprocess CLI integration, Apple Flow config/daemon architecture.

---

## Objective

Implement complete Gemini CLI support in `/codex-flow` so users can run Apple Flow with:

- `apple_flow_connector=gemini-cli`
- `apple_flow_gemini_cli_model=gemini-3-flash-preview` (default)
- `apple_flow_gemini_cli_command=gemini`

while preserving existing safety, approval, and workspace constraints.

## Scope Assumptions

- Gemini CLI binary exists and supports non-interactive mode via `-p/--prompt`.
- No due date was provided (`[due: missing value]`), so this plan is prioritized as next-up but unscheduled.

## Steps

1. Add Gemini connector implementation
- Create: `src/apple_flow/gemini_cli_connector.py`
- Pattern-match behavior from:
  - `src/apple_flow/codex_cli_connector.py`
  - `src/apple_flow/claude_cli_connector.py`
- Command shape target:
  - `gemini --yolo -m <model> -p <prompt>`
- Include:
  - per-sender context window
  - `set_soul_prompt(...)` support
  - consistent timeout/not-found/exit-code error handling
  - streaming method parity (`run_turn_streaming`) with safe fallback to `run_turn`

2. Add config fields and connector enum support
- Modify: `src/apple_flow/config.py`
- Add fields:
  - `gemini_cli_command: str = "gemini"`
  - `gemini_cli_context_window: int = 10`
  - `gemini_cli_model: str = "gemini-3-flash-preview"`
- Update connector comments/options to include `gemini-cli`.

3. Wire daemon connector selection and startup intro
- Modify: `src/apple_flow/daemon.py`
- Add import and selection branch for `gemini-cli`.
- Update `known_connectors` set.
- Add startup intro rendering branch in `send_startup_intro()`:
  - engine line for Gemini
  - model line from `settings.gemini_cli_model`

4. Wire setup and doctor/config tooling
- Modify: `src/apple_flow/setup_wizard.py`
  - add Gemini in `_choose_connector()`
  - add `apple_flow_gemini_cli_command` in `generate_env()` overrides
- Modify: `src/apple_flow/cli_control.py`
  - include `gemini-cli` in `_connector_command_key()`
  - include default command mapping
  - include validation allowlist and error text

5. Wire shell setup scripts
- Modify:
  - `scripts/setup_autostart.sh`
  - `scripts/start_beginner.sh`
- Add `gemini-cli` case mapping:
  - key: `apple_flow_gemini_cli_command`
  - default cmd: `gemini`
- Update unsupported-connector messages and install/auth hints.

6. Update config templates and docs
- Modify:
  - `.env.example`
  - `README.md`
  - `docs/ENV_SETUP.md`
  - `docs/QUICKSTART.md`
- Add `gemini-cli` as a selectable connector and document default model `gemini-3-flash-preview`.

7. Add/extend tests
- Create: `tests/test_gemini_cli_connector.py`
- Mirror coverage from existing connector tests:
  - protocol conformance
  - command construction with/without model
  - context handling and pruning
  - timeout/not-found/non-zero/empty output behavior
  - streaming fallback behavior
- Modify tests where connector allowlists are asserted:
  - `tests/test_cli_control.py`
  - `tests/test_setup_wizard.py`
- Add config default assertions for Gemini fields in:
  - `tests/test_config.py`
  - `tests/test_config_env.py` (if needed)

8. Verification run
- Run:
  - `pytest -q`
- Optional smoke test (local):
  - set `.env` connector to Gemini
  - run `python -m apple_flow daemon`
  - verify startup intro reports Gemini engine/model.

## Risks

1. Gemini CLI output mode variations
- Risk: output may include formatting/metadata depending on CLI version.
- Mitigation: normalize output text, handle empty output, and keep robust fallback messages.

2. CLI version drift
- Risk: flags or behaviors can change across Gemini CLI versions.
- Mitigation: pin/test against current local CLI (`gemini 0.28.2`) and isolate command build in one helper.

3. Setup/tooling miss paths
- Risk: connector name added in daemon but missed in scripts/wizard leads to broken onboarding.
- Mitigation: update all connector allowlists in same PR and add tests for validation paths.

4. Prompt/system-context parity
- Risk: Gemini lacks a dedicated system-prompt flag; behavior may differ from Claude.
- Mitigation: prepend SOUL/tools context in prompt assembly and validate with unit tests.

## Done Criteria

1. `apple_flow_connector=gemini-cli` starts successfully and routes all turns through `GeminiCliConnector`.
2. Default model is `gemini-3-flash-preview` unless explicitly overridden in `.env`.
3. Setup flows (`setup_wizard`, `cli_control`, `setup_autostart.sh`, `start_beginner.sh`) fully support Gemini selection and binary pinning.
4. Docs and `.env.example` clearly document Gemini as a first-class connector option.
5. Connector/unit/config/tooling test coverage includes Gemini paths and `pytest -q` passes.
