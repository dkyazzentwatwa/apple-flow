from pathlib import Path

import pytest

from apple_flow.config import RelaySettings


def test_parse_csv_lists_from_settings_init():
    settings = RelaySettings(
        allowed_senders="+15551234567,+15550000000",
        allowed_workspaces="/Users/cypher/Public/code,/tmp/safe",
    )

    assert settings.allowed_senders == ["+15551234567", "+15550000000"]
    # Paths are resolved to absolute paths (e.g., /tmp -> /private/tmp on macOS)
    assert settings.allowed_workspaces == [
        str(Path("/Users/cypher/Public/code").resolve()),
        str(Path("/tmp/safe").resolve()),
    ]
    assert settings.get_connector_type() == "codex-cli"


def test_parse_json_lists_from_settings_init():
    settings = RelaySettings(
        allowed_senders='["+15551234567"]',
        allowed_workspaces='["/Users/cypher/Public/code"]',
    )

    assert settings.allowed_senders == ["+15551234567"]
    assert settings.allowed_workspaces == [str(Path("/Users/cypher/Public/code").resolve())]
    assert settings.get_connector_type() == "codex-cli"


def test_connector_auto_migrates_deprecated_app_server():
    settings = RelaySettings(connector="codex-app-server")
    assert settings.get_connector_type() == "codex-cli"


def test_use_codex_cli_false_is_ignored_when_connector_unset():
    settings = RelaySettings(use_codex_cli=False)
    assert settings.get_connector_type() == "codex-cli"


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


def test_db_path_default_is_apple_flow(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = RelaySettings()
    assert settings.db_path == Path.home() / ".apple-flow" / "relay.db"


@pytest.mark.parametrize("value", ["~/.apple-flow/relay.db", "./relay.db"])
def test_db_path_requires_absolute_path(value):
    with pytest.raises(ValueError, match="db_path must be an absolute path"):
        RelaySettings(db_path=value)


@pytest.mark.parametrize("value", ["~/Library/Messages/chat.db", "chat.db"])
def test_messages_db_path_requires_absolute_path(value):
    with pytest.raises(ValueError, match="messages_db_path must be an absolute path"):
        RelaySettings(messages_db_path=value)


def test_reminders_archive_default_is_agent_archive(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = RelaySettings()
    assert settings.reminders_archive_list_name == "agent-archive"


def test_liveness_and_checkpoint_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = RelaySettings()
    assert settings.enable_progress_streaming is True
    assert settings.execution_heartbeat_seconds == 120.0
    assert settings.checkpoint_on_timeout is True
    assert settings.max_resume_attempts == 5


def test_empty_admin_port_and_memory_fall_back_to_defaults(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "\n".join(
            [
                "apple_flow_admin_port=",
                "apple_flow_enable_memory=",
                "apple_flow_enable_memory_v2=",
                "apple_flow_memory_v2_shadow_mode=",
                "apple_flow_memory_v2_migrate_on_start=",
                "apple_flow_memory_v2_include_legacy_fallback=",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    settings = RelaySettings()

    assert settings.admin_port == 8787
    assert settings.enable_memory is False
    assert settings.enable_memory_v2 is False
    assert settings.memory_v2_shadow_mode is False
    assert settings.memory_v2_migrate_on_start is True
    assert settings.memory_v2_include_legacy_fallback is True


def test_gemini_cli_model_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = RelaySettings()
    assert settings.gemini_cli_model == "gemini-3-flash-preview"


def test_gemini_cli_approval_mode_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = RelaySettings()
    assert settings.gemini_cli_approval_mode == "yolo"


def test_timezone_accepts_valid_iana_name(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = RelaySettings(timezone="America/Los_Angeles")
    assert settings.timezone == "America/Los_Angeles"


def test_timezone_rejects_invalid_name(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="Invalid timezone"):
        RelaySettings(timezone="Not/A_Real_Zone")
