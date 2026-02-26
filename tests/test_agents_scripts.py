from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIST_SCRIPT = ROOT / "scripts" / "agents" / "list_teams.sh"
USE_SCRIPT = ROOT / "scripts" / "agents" / "use_team.sh"


def _run(cmd: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(cmd, text=True, capture_output=True, check=True, env=merged_env)


def test_list_teams_outputs_all_teams() -> None:
    out = _run([str(LIST_SCRIPT)]).stdout.strip().splitlines()
    assert len(out) == 36
    assert any(line.startswith("imessage-command-center") for line in out)
    assert any(line.startswith("partnership-operations-team") for line in out)


def test_use_team_creates_managed_block_on_fresh_config() -> None:
    with tempfile.TemporaryDirectory() as td:
        config_path = Path(td) / "config.toml"
        env = {"CODEX_CONFIG_PATH": str(config_path)}

        _run([str(USE_SCRIPT), "imessage-command-center"], env=env)

        content = config_path.read_text(encoding="utf-8")
        assert "# BEGIN APPLE_FLOW_TEAM_PRESET" in content
        assert "[agents.default]" in content
        assert "imessage-command-center" in content


def test_use_team_updates_without_duplicate_managed_blocks() -> None:
    with tempfile.TemporaryDirectory() as td:
        config_path = Path(td) / "config.toml"
        env = {"CODEX_CONFIG_PATH": str(config_path)}

        _run([str(USE_SCRIPT), "imessage-command-center"], env=env)
        _run([str(USE_SCRIPT), "security-audit-team"], env=env)

        content = config_path.read_text(encoding="utf-8")
        assert content.count("# BEGIN APPLE_FLOW_TEAM_PRESET") == 1
        assert "security-audit-team" in content
        assert "imessage-command-center" not in content


def test_use_team_preserves_non_managed_content_and_creates_backup() -> None:
    with tempfile.TemporaryDirectory() as td:
        config_path = Path(td) / "config.toml"
        config_path.write_text(
            "[mcp_servers.sample]\ncommand = \"echo\"\n\n"
            "# BEGIN APPLE_FLOW_TEAM_PRESET\nold\n# END APPLE_FLOW_TEAM_PRESET\n",
            encoding="utf-8",
        )

        env = {"CODEX_CONFIG_PATH": str(config_path)}
        result = _run([str(USE_SCRIPT), "feature-implementation-team"], env=env)

        content = config_path.read_text(encoding="utf-8")
        assert "[mcp_servers.sample]" in content
        assert "feature-implementation-team" in content
        assert "old\n" not in content
        assert "Backup created:" in result.stdout

        backups = list(Path(td).glob("config.toml.bak.*"))
        assert backups, "Expected backup file to exist"
