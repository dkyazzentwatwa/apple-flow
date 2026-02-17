"""Tests for Apple Notes egress."""

from unittest.mock import patch, MagicMock
import subprocess

from codex_relay.notes_egress import AppleNotesEgress


def _make_egress():
    return AppleNotesEgress(folder_name="Codex Inbox")


@patch("codex_relay.notes_egress.subprocess.run")
def test_append_result_success(mock_run):
    result = MagicMock()
    result.returncode = 0
    result.stdout = "ok"
    mock_run.return_value = result

    egress = _make_egress()
    ok = egress.append_result("note123", "The task is complete.")

    assert ok is True
    mock_run.assert_called_once()
    call_args = mock_run.call_args
    assert "osascript" in call_args[0][0]


@patch("codex_relay.notes_egress.subprocess.run")
def test_append_result_failure_returncode(mock_run):
    result = MagicMock()
    result.returncode = 1
    result.stdout = "error: something went wrong"
    mock_run.return_value = result

    egress = _make_egress()
    ok = egress.append_result("note123", "Result text")

    assert ok is False


@patch("codex_relay.notes_egress.subprocess.run")
def test_append_result_failure_error_output(mock_run):
    result = MagicMock()
    result.returncode = 0
    result.stdout = "error: note not found"
    mock_run.return_value = result

    egress = _make_egress()
    ok = egress.append_result("note123", "Result text")

    assert ok is False


@patch("codex_relay.notes_egress.subprocess.run")
def test_append_result_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=15)

    egress = _make_egress()
    ok = egress.append_result("note123", "Result text")

    assert ok is False


@patch("codex_relay.notes_egress.subprocess.run")
def test_append_result_osascript_not_found(mock_run):
    mock_run.side_effect = FileNotFoundError("osascript not found")

    egress = _make_egress()
    ok = egress.append_result("note123", "Result text")

    assert ok is False


@patch("codex_relay.notes_egress.subprocess.run")
def test_append_result_escapes_special_chars(mock_run):
    result = MagicMock()
    result.returncode = 0
    result.stdout = "ok"
    mock_run.return_value = result

    egress = _make_egress()
    ok = egress.append_result("note123", 'Result with "quotes" and\nnewlines')

    assert ok is True
    script_arg = mock_run.call_args[0][0][2]  # osascript -e <script>
    assert '\\"' in script_arg or "quotes" in script_arg
