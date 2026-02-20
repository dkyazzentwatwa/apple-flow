"""Tests for Apple Calendar egress."""

import subprocess
from unittest.mock import MagicMock, patch

from apple_flow.calendar_egress import AppleCalendarEgress


def _make_egress():
    return AppleCalendarEgress(calendar_name="Codex Schedule")


@patch("apple_flow.calendar_egress.subprocess.run")
def test_annotate_event_success(mock_run):
    result = MagicMock()
    result.returncode = 0
    result.stdout = "ok"
    mock_run.return_value = result

    egress = _make_egress()
    ok = egress.annotate_event("evt123", "Task completed successfully.")

    assert ok is True
    mock_run.assert_called_once()


@patch("apple_flow.calendar_egress.subprocess.run")
def test_annotate_event_failure(mock_run):
    result = MagicMock()
    result.returncode = 1
    result.stdout = "error: event not found"
    mock_run.return_value = result

    egress = _make_egress()
    ok = egress.annotate_event("evt123", "Result text")

    assert ok is False


@patch("apple_flow.calendar_egress.subprocess.run")
def test_annotate_event_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=15)

    egress = _make_egress()
    ok = egress.annotate_event("evt123", "Result text")

    assert ok is False


@patch("apple_flow.calendar_egress.subprocess.run")
def test_annotate_event_osascript_not_found(mock_run):
    mock_run.side_effect = FileNotFoundError("osascript not found")

    egress = _make_egress()
    ok = egress.annotate_event("evt123", "Result text")

    assert ok is False


@patch("apple_flow.calendar_egress.subprocess.run")
def test_annotate_event_escapes_special_chars(mock_run):
    result = MagicMock()
    result.returncode = 0
    result.stdout = "ok"
    mock_run.return_value = result

    egress = _make_egress()
    ok = egress.annotate_event("evt123", 'Result with "quotes" and\nnewlines')

    assert ok is True
