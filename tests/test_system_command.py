"""Tests for the system: command (stop / restart via iMessage)."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest.mock import patch

from apple_flow.commanding import CommandKind, parse_command
from apple_flow.models import InboundMessage
from apple_flow.orchestrator import RelayOrchestrator


def _make_orchestrator(fake_connector, fake_egress, fake_store, shutdown_callback=None):
    return RelayOrchestrator(
        connector=fake_connector,
        egress=fake_egress,
        store=fake_store,
        allowed_workspaces=["/tmp"],
        default_workspace="/tmp",
        require_chat_prefix=False,
        shutdown_callback=shutdown_callback,
    )


def _make_message(text: str, sender: str = "+15550000001") -> InboundMessage:
    return InboundMessage(
        id="msg_001",
        sender=sender,
        text=text,
        received_at=datetime.now(UTC).isoformat(),
        is_from_me=False,
        context={},
    )


# --- Parser tests ---

def test_system_stop_parsed_correctly():
    cmd = parse_command("system: stop")
    assert cmd.kind is CommandKind.SYSTEM
    assert cmd.payload == "stop"


def test_system_restart_parsed_correctly():
    cmd = parse_command("system: restart")
    assert cmd.kind is CommandKind.SYSTEM
    assert cmd.payload == "restart"


def test_system_stop_case_insensitive():
    cmd = parse_command("SYSTEM: STOP")
    assert cmd.kind is CommandKind.SYSTEM
    assert cmd.payload == "STOP"


# --- Orchestrator tests ---

def test_system_stop_calls_shutdown_callback(fake_connector, fake_egress, fake_store):
    called = []
    orchestrator = _make_orchestrator(
        fake_connector, fake_egress, fake_store,
        shutdown_callback=lambda: called.append(True),
    )
    result = orchestrator.handle_message(_make_message("system: stop"))

    assert result.kind is CommandKind.SYSTEM
    assert called == [True]
    assert len(fake_egress.messages) == 1
    assert "shutting down" in fake_egress.messages[0][1].lower()


def test_system_restart_triggers_launchd_kickstart(fake_connector, fake_egress, fake_store):
    called = []
    orchestrator = _make_orchestrator(
        fake_connector, fake_egress, fake_store,
        shutdown_callback=lambda: called.append(True),
    )
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        result = orchestrator.handle_message(_make_message("system: restart"))
        mock_run.assert_called_once_with(
            ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/local.apple-flow"],
            check=False,
            timeout=8,
        )

    assert result.kind is CommandKind.SYSTEM
    assert called == []
    assert len(fake_egress.messages) == 1
    assert "restarting" in fake_egress.messages[0][1].lower()


def test_system_restart_falls_back_to_shutdown_when_kickstart_fails(fake_connector, fake_egress, fake_store):
    called = []
    orchestrator = _make_orchestrator(
        fake_connector, fake_egress, fake_store,
        shutdown_callback=lambda: called.append(True),
    )
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        result = orchestrator.handle_message(_make_message("system: restart"))

    assert result.kind is CommandKind.SYSTEM
    assert called == [True]
    assert len(fake_egress.messages) == 1
    assert "restarting" in fake_egress.messages[0][1].lower()


def test_system_unknown_subcommand(fake_connector, fake_egress, fake_store):
    called = []
    orchestrator = _make_orchestrator(
        fake_connector, fake_egress, fake_store,
        shutdown_callback=lambda: called.append(True),
    )
    result = orchestrator.handle_message(_make_message("system: dance"))

    assert result.kind is CommandKind.SYSTEM
    assert called == [], "Callback must NOT be called for unknown subcommand"
    assert len(fake_egress.messages) == 1
    assert "unknown system command" in fake_egress.messages[0][1].lower()
    assert "kill provider" in fake_egress.messages[0][1].lower()


def test_system_kill_provider_invokes_killswitch(fake_connector, fake_egress, fake_store):
    orchestrator = _make_orchestrator(fake_connector, fake_egress, fake_store)

    with patch.object(
        orchestrator,
        "_kill_provider_processes",
        return_value="Killed 2 active Gemini provider process(es).",
    ) as mock_kill:
        result = orchestrator.handle_message(_make_message("system: kill provider"))

    assert result.kind is CommandKind.SYSTEM
    mock_kill.assert_called_once_with()
    assert len(fake_egress.messages) == 1
    assert "killed 2 active gemini provider process(es)." in fake_egress.messages[0][1].lower()


def test_mark_inflight_runs_failed_marks_only_running_states(fake_connector, fake_egress, fake_store):
    orchestrator = _make_orchestrator(fake_connector, fake_egress, fake_store)

    fake_store.create_run("run_plan", "+15550000001", "task", "planning", "/tmp", "execute")
    fake_store.create_run("run_exec", "+15550000001", "task", "executing", "/tmp", "execute")
    fake_store.create_run("run_verify", "+15550000001", "task", "verifying", "/tmp", "execute")
    fake_store.create_run("run_wait", "+15550000001", "task", "awaiting_approval", "/tmp", "execute")
    fake_store.create_run("run_done", "+15550000001", "task", "completed", "/tmp", "execute")

    updated = orchestrator._mark_inflight_runs_failed("test reason")
    assert updated == 3
    assert fake_store.get_run("run_plan")["state"] == "failed"
    assert fake_store.get_run("run_exec")["state"] == "failed"
    assert fake_store.get_run("run_verify")["state"] == "failed"
    assert fake_store.get_run("run_wait")["state"] == "awaiting_approval"
    assert fake_store.get_run("run_done")["state"] == "completed"


def test_system_no_callback_is_safe(fake_connector, fake_egress, fake_store):
    orchestrator = _make_orchestrator(
        fake_connector, fake_egress, fake_store,
        shutdown_callback=None,
    )
    # Neither stop nor restart should raise when callback is None
    result_stop = orchestrator.handle_message(_make_message("system: stop", sender="+15550000001"))
    assert result_stop.kind is CommandKind.SYSTEM

    # Use a different message id to avoid dedup
    msg2 = InboundMessage(
        id="msg_002",
        sender="+15550000001",
        text="system: restart",
        received_at=datetime.now(UTC).isoformat(),
        is_from_me=False,
        context={},
    )
    result_restart = orchestrator.handle_message(msg2)
    assert result_restart.kind is CommandKind.SYSTEM
