from pathlib import Path

from codex_relay.config import RelaySettings


def test_parse_csv_lists_from_settings_init():
    settings = RelaySettings(
        allowed_senders="+15551234567,+15550000000",
        allowed_workspaces="/Users/cypher/Public/code,/tmp/safe",
        codex_app_server_cmd="codex app-server",
    )

    assert settings.allowed_senders == ["+15551234567", "+15550000000"]
    # Paths are resolved to absolute paths (e.g., /tmp -> /private/tmp on macOS)
    assert settings.allowed_workspaces == [
        str(Path("/Users/cypher/Public/code").resolve()),
        str(Path("/tmp/safe").resolve()),
    ]
    assert settings.codex_app_server_cmd == ["codex", "app-server"]


def test_parse_json_lists_from_settings_init():
    settings = RelaySettings(
        allowed_senders='["+15551234567"]',
        allowed_workspaces='["/Users/cypher/Public/code"]',
        codex_app_server_cmd='["codex", "app-server"]',
    )

    assert settings.allowed_senders == ["+15551234567"]
    assert settings.allowed_workspaces == [str(Path("/Users/cypher/Public/code").resolve())]
    assert settings.codex_app_server_cmd == ["codex", "app-server"]
