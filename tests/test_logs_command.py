"""Tests for the `logs` command — tail daemon log via iMessage."""
from __future__ import annotations

from apple_flow.commanding import CommandKind, parse_command
from apple_flow.models import InboundMessage
from apple_flow.orchestrator import RelayOrchestrator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_orchestrator(fake_store, fake_connector, fake_egress, log_file_path=None):
    return RelayOrchestrator(
        connector=fake_connector,
        egress=fake_egress,
        store=fake_store,
        allowed_workspaces=["/tmp"],
        default_workspace="/tmp",
        require_chat_prefix=False,
        log_file_path=log_file_path,
    )


def _msg(text: str) -> InboundMessage:
    return InboundMessage(
        id="1",
        sender="+15550001111",
        text=text,
        received_at="2026-01-01T00:00:00",
        is_from_me=False,
        context={},
    )


# ---------------------------------------------------------------------------
# Command parsing
# ---------------------------------------------------------------------------


def test_parse_logs_bare():
    cmd = parse_command("logs")
    assert cmd.kind is CommandKind.LOGS
    assert cmd.payload == ""


def test_parse_logs_with_n():
    cmd = parse_command("logs: 10")
    assert cmd.kind is CommandKind.LOGS
    assert cmd.payload == "10"


def test_parse_logs_uppercase():
    cmd = parse_command("LOGS")
    assert cmd.kind is CommandKind.LOGS


# ---------------------------------------------------------------------------
# Handler: default 20 lines
# ---------------------------------------------------------------------------


def test_logs_default_20_lines(fake_store, fake_connector, fake_egress, tmp_path):
    log_file = tmp_path / "test.log"
    lines = [f"line {i}" for i in range(1, 31)]  # 30 lines total
    log_file.write_text("\n".join(lines))

    orch = _make_orchestrator(fake_store, fake_connector, fake_egress, log_file_path=str(log_file))
    result = orch.handle_message(_msg("logs"))

    assert result.kind is CommandKind.LOGS
    sent = fake_egress.messages[0][1]
    # Should contain last 20 lines (lines 11-30)
    assert "line 10" not in sent
    assert "line 11" in sent
    assert "line 30" in sent
    assert "Last 20 lines" in sent


# ---------------------------------------------------------------------------
# Handler: user-specified N
# ---------------------------------------------------------------------------


def test_logs_custom_n(fake_store, fake_connector, fake_egress, tmp_path):
    log_file = tmp_path / "test.log"
    lines = [f"line {i}" for i in range(1, 21)]  # 20 lines
    log_file.write_text("\n".join(lines))

    orch = _make_orchestrator(fake_store, fake_connector, fake_egress, log_file_path=str(log_file))
    orch.handle_message(_msg("logs: 5"))

    sent = fake_egress.messages[0][1]
    assert "Last 5 lines" in sent
    assert "line 16" in sent
    assert "line 20" in sent
    assert "line 15" not in sent


# ---------------------------------------------------------------------------
# Handler: cap at 50
# ---------------------------------------------------------------------------


def test_logs_capped_at_50(fake_store, fake_connector, fake_egress, tmp_path):
    log_file = tmp_path / "test.log"
    lines = [f"line {i}" for i in range(1, 101)]  # 100 lines
    log_file.write_text("\n".join(lines))

    orch = _make_orchestrator(fake_store, fake_connector, fake_egress, log_file_path=str(log_file))
    orch.handle_message(_msg("logs: 999"))

    sent = fake_egress.messages[0][1]
    assert "Last 50 lines" in sent
    assert "line 51" in sent
    assert "line 100" in sent
    assert "line 50" not in sent


# ---------------------------------------------------------------------------
# Handler: file not found
# ---------------------------------------------------------------------------


def test_logs_file_not_found(fake_store, fake_connector, fake_egress, tmp_path):
    orch = _make_orchestrator(
        fake_store, fake_connector, fake_egress,
        log_file_path=str(tmp_path / "nonexistent.log"),
    )
    result = orch.handle_message(_msg("logs"))

    assert result.kind is CommandKind.LOGS
    sent = fake_egress.messages[0][1]
    assert "not found" in sent.lower()


# ---------------------------------------------------------------------------
# Handler: ANSI codes stripped
# ---------------------------------------------------------------------------


def test_logs_strips_ansi(fake_store, fake_connector, fake_egress, tmp_path):
    log_file = tmp_path / "test.log"
    log_file.write_text("\x1b[32mGREEN\x1b[0m plain")

    orch = _make_orchestrator(fake_store, fake_connector, fake_egress, log_file_path=str(log_file))
    orch.handle_message(_msg("logs"))

    sent = fake_egress.messages[0][1]
    assert "\x1b[" not in sent
    assert "GREEN" in sent
    assert "plain" in sent


# ---------------------------------------------------------------------------
# Handler: response sent to correct sender
# ---------------------------------------------------------------------------


def test_logs_sends_to_sender(fake_store, fake_connector, fake_egress, tmp_path):
    log_file = tmp_path / "test.log"
    log_file.write_text("hello")

    orch = _make_orchestrator(fake_store, fake_connector, fake_egress, log_file_path=str(log_file))
    orch.handle_message(_msg("logs"))

    assert fake_egress.messages[0][0] == "+15550001111"
