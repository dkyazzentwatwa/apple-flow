from pathlib import Path

import pytest

from apple_flow.config import RelaySettings


def test_csv_dotenv_values_load_without_json(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "\n".join(
            [
                "apple_flow_allowed_senders=+15551234567,+15550000000",
                "apple_flow_allowed_workspaces=/Users/cypher/Public/code/codex-flow,/tmp/safe",
            ]
        )
    )

    monkeypatch.chdir(tmp_path)
    settings = RelaySettings()

    assert settings.allowed_senders == ["+15551234567", "+15550000000"]
    # Paths are resolved to absolute paths
    assert settings.allowed_workspaces == [
        str(Path("/Users/cypher/Public/code/codex-flow").resolve()),
        str(Path("/tmp/safe").resolve()),
    ]
    assert settings.get_connector_type() == "codex-cli"


def test_dotenv_rejects_non_absolute_db_paths(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "\n".join(
            [
                "apple_flow_db_path=~/.apple-flow/relay.db",
                "apple_flow_messages_db_path=chat.db",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="absolute path"):
        RelaySettings()
