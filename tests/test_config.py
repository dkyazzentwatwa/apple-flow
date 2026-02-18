from pathlib import Path

from apple_flow.config import RelaySettings


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


def test_parse_claude_tool_lists_from_settings_init():
    settings = RelaySettings(
        claude_cli_tools="default,WebSearch",
        claude_cli_allowed_tools='["WebSearch"]',
    )

    assert settings.claude_cli_tools == ["default", "WebSearch"]
    assert settings.claude_cli_allowed_tools == ["WebSearch"]


def test_personality_prompt_default_nonempty(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = RelaySettings()
    assert settings.personality_prompt
    assert "{workspace}" in settings.personality_prompt


def test_require_chat_prefix_default_false(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = RelaySettings()
    assert settings.require_chat_prefix is False


def test_auto_context_messages_default_10(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = RelaySettings()
    assert settings.auto_context_messages == 10


def test_trigger_tag_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = RelaySettings()
    assert settings.trigger_tag == "!!agent"
