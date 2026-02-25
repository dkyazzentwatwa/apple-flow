import subprocess
from pathlib import Path

from apple_flow import gateway_setup, setup_wizard


def test_validate_phone_accepts_e164_and_rejects_invalid():
    assert setup_wizard.validate_phone("+15551234567") == "+15551234567"
    assert setup_wizard.validate_phone("15551234567") is None
    assert setup_wizard.validate_phone("+1 5551234567") is None


def test_resolve_binary_uses_path_lookup(monkeypatch):
    monkeypatch.setattr(gateway_setup.shutil, "which", lambda _: "/usr/local/bin/claude")
    assert gateway_setup.resolve_binary("claude") == str(Path("/usr/local/bin/claude").resolve())


def test_resolve_binary_uses_local_bin_fallback(monkeypatch, tmp_path):
    local_bin = tmp_path / ".local" / "bin"
    local_bin.mkdir(parents=True)
    binary = local_bin / "codex"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)

    monkeypatch.setattr(gateway_setup.shutil, "which", lambda _: None)
    monkeypatch.setattr(gateway_setup.Path, "home", classmethod(lambda cls: tmp_path))

    assert gateway_setup.resolve_binary("codex") == str(binary.resolve())


def test_ensure_via_applescript_handles_created_exists_and_failed(monkeypatch):
    monkeypatch.setattr(
        gateway_setup,
        "_run_osascript",
        lambda _script: subprocess.CompletedProcess(args=[], returncode=0, stdout="created\n", stderr=""),
    )
    assert gateway_setup._ensure_via_applescript("test").status == "created"

    monkeypatch.setattr(
        gateway_setup,
        "_run_osascript",
        lambda _script: subprocess.CompletedProcess(args=[], returncode=0, stdout="exists\n", stderr=""),
    )
    assert gateway_setup._ensure_via_applescript("test").status == "exists"

    monkeypatch.setattr(
        gateway_setup,
        "_run_osascript",
        lambda _script: subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="permission denied"),
    )
    failed = gateway_setup._ensure_via_applescript("test")
    assert failed.status == "failed"
    assert "permission denied" in failed.detail


def test_generate_env_uses_standardized_gateway_names_and_pinned_connector():
    env = setup_wizard.generate_env(
        phone="+15551234567",
        connector="claude-cli",
        connector_command="/opt/homebrew/bin/claude",
        workspace="/Users/example/code",
        gateways=["reminders", "notes", "calendar"],
        mail_address="",
    )

    assert "apple_flow_claude_cli_command=/opt/homebrew/bin/claude" in env
    assert "apple_flow_reminders_list_name=agent-task" in env
    assert "apple_flow_reminders_archive_list_name=agent-archive" in env
    assert "apple_flow_notes_folder_name=agent-task" in env
    assert "apple_flow_notes_archive_folder_name=agent-archive" in env
    assert "apple_flow_notes_log_folder_name=agent-logs" in env
    assert "apple_flow_calendar_name=agent-schedule" in env


def test_generate_env_sets_gemini_command_when_gemini_connector_selected():
    env = setup_wizard.generate_env(
        phone="+15551234567",
        connector="gemini-cli",
        connector_command="/opt/homebrew/bin/gemini",
        workspace="/Users/example/code",
        gateways=[],
        mail_address="",
    )

    assert "apple_flow_connector=gemini-cli" in env
    assert "apple_flow_gemini_cli_command=/opt/homebrew/bin/gemini" in env
