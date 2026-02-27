from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "agents" / "catalog.toml"
TEAMS_DIR = ROOT / "agents" / "teams"

REQUIRED_TEAM_HEADERS = [
    "## Purpose",
    "## Trigger Phrases",
    "## Inputs Required",
    "## Agent Topology",
    "## Output Contract",
    "## Failure Modes",
    "## When to Use",
    "## Anti-Pattern (Do Not Use For)",
    "## Approval-Sensitive Scenario",
]


def _load_catalog() -> dict:
    return tomllib.loads(CATALOG.read_text(encoding="utf-8"))


def test_catalog_has_expected_team_count_and_unique_slugs() -> None:
    data = _load_catalog()
    teams = data["teams"]

    assert len(teams) == 37

    slugs = [t["slug"] for t in teams]
    assert len(set(slugs)) == 37


def test_every_team_folder_contains_required_files_and_parseable_toml() -> None:
    data = _load_catalog()

    for team in data["teams"]:
        slug = team["slug"]
        team_dir = TEAMS_DIR / slug
        assert team_dir.exists(), f"Missing team folder: {slug}"

        team_md = team_dir / "TEAM.md"
        preset = team_dir / "preset.toml"
        role_dir = team_dir / "roles"

        assert team_md.exists(), f"Missing TEAM.md for: {slug}"
        assert preset.exists(), f"Missing preset.toml for: {slug}"

        preset_data = tomllib.loads(preset.read_text(encoding="utf-8"))
        assert "agents" in preset_data

        for role_name in ["default", "explorer", "reviewer", "worker", "monitor"]:
            assert role_name in preset_data["agents"], f"Missing role {role_name} in {slug}"
            role_file = role_dir / f"{role_name}.toml"
            assert role_file.exists(), f"Missing role file {role_file}"

            role_data = tomllib.loads(role_file.read_text(encoding="utf-8"))
            assert "model" in role_data
            assert "model_reasoning_effort" in role_data
            assert "developer_instructions" in role_data


def test_team_docs_include_required_sections_and_usage_lines() -> None:
    data = _load_catalog()

    for team in data["teams"]:
        slug = team["slug"]
        category = team["category"]
        team_md = (TEAMS_DIR / slug / "TEAM.md").read_text(encoding="utf-8")

        for header in REQUIRED_TEAM_HEADERS:
            assert header in team_md, f"Missing header {header} in {slug}"

        when_to_use_block = team_md.split("## When to Use", 1)[1].split(
            "## Anti-Pattern (Do Not Use For)", 1
        )[0]
        assert when_to_use_block.count("- ") >= 3, f"Need >= 3 use-cases in {slug}"

        if category == "apple_flow_ops":
            assert "Apple Flow" in team_md
            assert "task:" in team_md
            assert "project:" in team_md
            assert "plan:" in team_md
        else:
            assert "Apple Flow operations" not in team_md
