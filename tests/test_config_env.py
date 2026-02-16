from pathlib import Path

from codex_relay.config import RelaySettings


def test_csv_dotenv_values_load_without_json(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "\n".join(
            [
                "codex_relay_allowed_senders=+15551234567,+15550000000",
                "codex_relay_allowed_workspaces=/Users/cypher/Public/code/codex-flow,/tmp/safe",
                "codex_relay_codex_app_server_cmd=codex app-server",
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
    assert settings.codex_app_server_cmd == ["codex", "app-server"]
