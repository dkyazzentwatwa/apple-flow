from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from apple_flow import cli_control


def _args(**kwargs):
    defaults = {
        "tool_args": [],
        "env_file": ".env",
        "set_values": [],
        "keys": [],
        "effective": False,
        "stream_name": "stderr",
        "lines": 200,
        "phone": "",
        "connector": "",
        "connector_command": "",
        "workspace": "",
        "gateways": "",
        "mail_address": "",
        "admin_api_token": "",
        "enable_agent_office": False,
        "soul_file": "agent-office/SOUL.md",
        "enable_reminders": False,
        "enable_notes": False,
        "enable_notes_logging": False,
        "enable_calendar": False,
        "reminders_list_name": "agent-task",
        "reminders_archive_list_name": "agent-archive",
        "notes_folder_name": "agent-task",
        "notes_archive_folder_name": "agent-archive",
        "notes_log_folder_name": "agent-logs",
        "calendar_name": "agent-schedule",
        "calendar_name_override": "agent-schedule",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_run_cli_control_rejects_missing_subcommand(capsys):
    code = cli_control.run_cli_control("wizard", _args())
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["code"] == "missing_command"


def test_wizard_generate_env_validation_failure(capsys, tmp_path):
    args = _args(
        tool_args=["generate-env"],
        phone="not-a-phone",
        connector="codex-cli",
        connector_command="codex",
        workspace=str(tmp_path / "missing"),
    )
    code = cli_control.run_cli_control("wizard", args)
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["code"] == "validation_failed"
    assert payload["validation_errors"]


def test_wizard_generate_env_success(capsys, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(cli_control, "resolve_binary", lambda _binary: "/usr/local/bin/codex")

    args = _args(
        tool_args=["generate-env"],
        phone="+15551234567",
        connector="codex-cli",
        connector_command="codex",
        workspace=str(workspace),
        gateways="",
    )
    code = cli_control.run_cli_control("wizard", args)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert "apple_flow_allowed_senders=+15551234567" in payload["env_preview"]
    assert payload["validation_errors"] == []


def test_wizard_generate_env_supports_gemini_connector(capsys, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(cli_control, "resolve_binary", lambda _binary: "/usr/local/bin/gemini")

    args = _args(
        tool_args=["generate-env"],
        phone="+15551234567",
        connector="gemini-cli",
        connector_command="gemini",
        workspace=str(workspace),
        gateways="",
    )
    code = cli_control.run_cli_control("wizard", args)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert "apple_flow_connector=gemini-cli" in payload["env_preview"]
    assert "apple_flow_gemini_cli_command=gemini" in payload["env_preview"]


def test_wizard_generate_env_supports_custom_gateway_names(capsys, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(cli_control, "resolve_binary", lambda _binary: "/usr/local/bin/codex")

    args = _args(
        tool_args=["generate-env"],
        phone="+15551234567",
        connector="codex-cli",
        connector_command="codex",
        workspace=str(workspace),
        gateways="reminders,notes,calendar",
        reminders_list_name="My Tasks",
        reminders_archive_list_name="My Archive",
        notes_folder_name="Tasks Notes",
        notes_archive_folder_name="Done Notes",
        notes_log_folder_name="Ops Logs",
        calendar_name_override="Work Calendar",
    )
    code = cli_control.run_cli_control("wizard", args)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    env_preview = payload["env_preview"]
    assert "apple_flow_reminders_list_name=My Tasks" in env_preview
    assert "apple_flow_reminders_archive_list_name=My Archive" in env_preview
    assert "apple_flow_notes_folder_name=Tasks Notes" in env_preview
    assert "apple_flow_notes_archive_folder_name=Done Notes" in env_preview
    assert "apple_flow_notes_log_folder_name=Ops Logs" in env_preview
    assert "apple_flow_calendar_name=Work Calendar" in env_preview


def test_wizard_generate_env_can_enable_agent_office(capsys, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(cli_control, "resolve_binary", lambda _binary: "/usr/local/bin/codex")

    args = _args(
        tool_args=["generate-env"],
        phone="+15551234567",
        connector="codex-cli",
        connector_command="codex",
        workspace=str(workspace),
        gateways="",
        enable_agent_office=True,
        soul_file="agent-office/SOUL.md",
    )
    code = cli_control.run_cli_control("wizard", args)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    env_preview = payload["env_preview"]
    assert "apple_flow_enable_memory=true" in env_preview
    assert "apple_flow_soul_file=agent-office/SOUL.md" in env_preview


def test_wizard_doctor_contract_fields(capsys, tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "apple_flow_connector=codex-cli\n"
        "apple_flow_codex_cli_command=codex\n"
        "apple_flow_admin_api_token=test-token\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli_control, "check_messages_db_access", lambda: (True, "OK"))
    monkeypatch.setattr(cli_control.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(cli_control, "resolve_binary", lambda _binary: "/usr/local/bin/codex")

    args = _args(tool_args=["doctor"], env_file=str(env_file))
    code = cli_control.run_cli_control("wizard", args)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert set(
        [
            "python_ok",
            "venv_ok",
            "messages_db_exists",
            "messages_db_readable",
            "connector_binary_found",
            "connector_binary_path",
            "admin_api_token_present",
            "errors",
        ]
    ).issubset(payload.keys())


def test_wizard_ensure_gateways_serializes_results(capsys, monkeypatch):
    class FakeStatus:
        def __init__(self, label: str, name: str, status: str, detail: str = ""):
            self.label = label
            self.name = name
            self.result = SimpleNamespace(status=status, detail=detail)

    monkeypatch.setattr(
        cli_control,
        "ensure_gateway_resources",
        lambda **_kwargs: [
            FakeStatus("Reminders task list", "agent-task", "created"),
            FakeStatus("Calendar", "agent-schedule", "exists"),
        ],
    )
    args = _args(tool_args=["ensure-gateways"], enable_reminders=True, enable_calendar=True)
    code = cli_control.run_cli_control("wizard", args)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert len(payload["results"]) == 2
    assert payload["results"][0]["label"] == "Reminders task list"


def test_config_write_then_read(capsys, tmp_path):
    env_file = tmp_path / ".env"
    write_args = _args(
        tool_args=["write"],
        env_file=str(env_file),
        set_values=["apple_flow_admin_api_token=test", "apple_flow_allowed_senders=+15551234567"],
    )
    write_code = cli_control.run_cli_control("config", write_args)
    assert write_code == 0
    write_payload = json.loads(capsys.readouterr().out)
    assert write_payload["ok"] is True
    assert "apple_flow_admin_api_token" in write_payload["updated_keys"]

    read_args = _args(
        tool_args=["read"],
        env_file=str(env_file),
        keys=["apple_flow_admin_api_token", "apple_flow_allowed_senders"],
    )
    read_code = cli_control.run_cli_control("config", read_args)
    assert read_code == 0
    read_payload = json.loads(capsys.readouterr().out)
    assert read_payload["ok"] is True
    assert read_payload["values"]["apple_flow_admin_api_token"] == "test"
    assert read_payload["values"]["apple_flow_allowed_senders"] == "+15551234567"
    assert write_payload["written_count"] == 2
    assert write_payload["backup_path"] == ""


def test_config_write_creates_backup_when_env_exists(capsys, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("apple_flow_admin_api_token=old\n", encoding="utf-8")
    args = _args(
        tool_args=["write"],
        env_file=str(env_file),
        set_values=["apple_flow_admin_api_token=new"],
    )
    code = cli_control.run_cli_control("config", args)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["backup_path"]
    assert Path(payload["backup_path"]).exists()


def test_config_read_effective_returns_sources(capsys, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("apple_flow_admin_api_token=test\n", encoding="utf-8")
    args = _args(
        tool_args=["read"],
        env_file=str(env_file),
        keys=["apple_flow_admin_api_token", "apple_flow_admin_port"],
        effective=True,
    )
    code = cli_control.run_cli_control("config", args)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["effective"] is True
    assert payload["value_states"]["apple_flow_admin_api_token"]["source"] == "env"
    assert payload["value_states"]["apple_flow_admin_port"]["source"] == "default"


def test_config_schema_contains_fields_and_sections(capsys):
    args = _args(tool_args=["schema"])
    code = cli_control.run_cli_control("config", args)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["schema_version"] == "1"
    assert payload["sections"]
    assert payload["fields"]
    keys = {field["key"] for field in payload["fields"]}
    assert "apple_flow_admin_api_token" in keys
    assert "apple_flow_connector" in keys


def test_config_validate_requires_token(capsys, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "apple_flow_allowed_senders=+15551234567\n"
        f"apple_flow_allowed_workspaces={workspace}\n"
        f"apple_flow_default_workspace={workspace}\n",
        encoding="utf-8",
    )
    args = _args(tool_args=["validate"], env_file=str(env_file))
    code = cli_control.run_cli_control("config", args)
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["code"] == "config_invalid"
    assert "apple_flow_admin_api_token is missing" in payload["errors"]


def test_service_status_contract(capsys, monkeypatch):
    monkeypatch.setattr(cli_control, "_launchctl_service_row", lambda _label: (True, 123))
    monkeypatch.setattr(cli_control, "_daemon_process_detected", lambda: True)
    monkeypatch.setattr(cli_control, "_admin_health", lambda _host, _port, _token: True)
    monkeypatch.setattr(
        cli_control,
        "RelaySettings",
        lambda: SimpleNamespace(admin_host="127.0.0.1", admin_port=8787, admin_api_token="token"),
    )
    args = _args(tool_args=["status"])
    code = cli_control.run_cli_control("service", args)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["launchd_loaded"] is True
    assert payload["launchd_pid"] == 123
    assert payload["daemon_process_detected"] is True
    assert payload["healthy"] is True


def test_service_logs_returns_path_and_lines(capsys, tmp_path, monkeypatch):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    log_file = logs_dir / "apple-flow.err.log"
    log_file.write_text("line1\nline2\nline3\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    args = _args(tool_args=["logs"], stream_name="stderr", lines=2)
    code = cli_control.run_cli_control("service", args)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["path"] == str(Path("logs") / "apple-flow.err.log")
    assert payload["lines"] == ["line2", "line3"]
