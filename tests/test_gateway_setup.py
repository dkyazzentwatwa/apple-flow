"""Tests for gateway_setup module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apple_flow.gateway_setup import (
    EnsureResult,
    GatewayResourceStatus,
    _escape_applescript,
    ensure_calendar,
    ensure_gateway_resources,
    ensure_notes_folder,
    ensure_reminders_list,
    resolve_binary,
)


# --- _escape_applescript ---

def test_escape_applescript_no_special_chars():
    assert _escape_applescript("hello") == "hello"


def test_escape_applescript_quotes():
    assert _escape_applescript('say "hello"') == 'say \\"hello\\"'


def test_escape_applescript_backslashes():
    assert _escape_applescript("a\\b") == "a\\\\b"


def test_escape_applescript_both():
    assert _escape_applescript('a\\"b') == 'a\\\\\\"b'


def test_escape_applescript_empty():
    assert _escape_applescript("") == ""


# --- EnsureResult and GatewayResourceStatus dataclasses ---

def test_ensure_result_created():
    r = EnsureResult(status="created")
    assert r.status == "created"
    assert r.detail == ""


def test_ensure_result_failed_with_detail():
    r = EnsureResult(status="failed", detail="osascript timeout")
    assert r.status == "failed"
    assert r.detail == "osascript timeout"


def test_ensure_result_frozen():
    r = EnsureResult(status="exists")
    with pytest.raises((AttributeError, TypeError)):
        r.status = "created"  # type: ignore[misc]


def test_gateway_resource_status():
    r = EnsureResult(status="created")
    s = GatewayResourceStatus(label="Reminders task list", name="Tasks", result=r)
    assert s.label == "Reminders task list"
    assert s.name == "Tasks"
    assert s.result.status == "created"


# --- _ensure_via_applescript (via ensure_notes_folder etc.) ---

def _make_osa_result(ok: bool, stdout: str = "", detail: str = "") -> MagicMock:
    result = MagicMock()
    result.ok = ok
    result.stdout = stdout
    result.detail = detail
    return result


def test_ensure_notes_folder_created():
    osa_result = _make_osa_result(ok=True, stdout="created")
    with patch("apple_flow.gateway_setup.run_osascript_with_recovery", return_value=osa_result):
        result = ensure_notes_folder("MyFolder")
    assert result.status == "created"


def test_ensure_notes_folder_exists():
    osa_result = _make_osa_result(ok=True, stdout="exists")
    with patch("apple_flow.gateway_setup.run_osascript_with_recovery", return_value=osa_result):
        result = ensure_notes_folder("MyFolder")
    assert result.status == "exists"


def test_ensure_notes_folder_failed():
    osa_result = _make_osa_result(ok=False, detail="Notes not running")
    with patch("apple_flow.gateway_setup.run_osascript_with_recovery", return_value=osa_result):
        result = ensure_notes_folder("MyFolder")
    assert result.status == "failed"
    assert "Notes not running" in result.detail


def test_ensure_notes_folder_unexpected_output():
    osa_result = _make_osa_result(ok=True, stdout="something unexpected")
    with patch("apple_flow.gateway_setup.run_osascript_with_recovery", return_value=osa_result):
        result = ensure_notes_folder("MyFolder")
    assert result.status == "failed"
    assert "unexpected output" in result.detail


def test_ensure_notes_folder_empty_output():
    osa_result = _make_osa_result(ok=True, stdout="")
    with patch("apple_flow.gateway_setup.run_osascript_with_recovery", return_value=osa_result):
        result = ensure_notes_folder("MyFolder")
    assert result.status == "failed"
    assert "empty" in result.detail


def test_ensure_calendar_created():
    osa_result = _make_osa_result(ok=True, stdout="created")
    with patch("apple_flow.gateway_setup.run_osascript_with_recovery", return_value=osa_result):
        result = ensure_calendar("Work")
    assert result.status == "created"


def test_ensure_calendar_exists():
    osa_result = _make_osa_result(ok=True, stdout="exists")
    with patch("apple_flow.gateway_setup.run_osascript_with_recovery", return_value=osa_result):
        result = ensure_calendar("Work")
    assert result.status == "exists"


def test_ensure_reminders_list_simple_created():
    osa_result = _make_osa_result(ok=True, stdout="created")
    with patch("apple_flow.gateway_setup.run_osascript_with_recovery", return_value=osa_result), \
         patch("apple_flow.gateway_setup.apple_tools.reminders_split_selector", return_value=["Tasks"]):
        result = ensure_reminders_list("Tasks")
    assert result.status == "created"


def test_ensure_reminders_list_multi_part_exists():
    """Test multi-part list selector that resolves to an existing list."""
    with patch("apple_flow.gateway_setup.apple_tools.reminders_split_selector", return_value=["iCloud", "Work", "Tasks"]), \
         patch("apple_flow.gateway_setup.apple_tools.reminders_resolve_list_selector", return_value={"id": "list-123", "name": "Tasks"}):
        result = ensure_reminders_list("iCloud/Work/Tasks")
    assert result.status == "exists"


def test_ensure_reminders_list_multi_part_not_found():
    """Test multi-part list selector that needs to be created via AppleScript."""
    osa_result = _make_osa_result(ok=True, stdout="created")
    with patch("apple_flow.gateway_setup.apple_tools.reminders_split_selector", return_value=["iCloud", "Tasks"]), \
         patch("apple_flow.gateway_setup.apple_tools.reminders_resolve_list_selector", return_value=None), \
         patch("apple_flow.gateway_setup.run_osascript_with_recovery", return_value=osa_result):
        result = ensure_reminders_list("iCloud/Tasks")
    assert result.status == "created"


# --- ensure_gateway_resources ---

def test_ensure_gateway_resources_all_disabled():
    result = ensure_gateway_resources(
        enable_reminders=False,
        enable_notes=False,
        enable_notes_logging=False,
        enable_calendar=False,
        reminders_list_name="Tasks",
        reminders_archive_list_name="Archive",
        notes_folder_name="Notes",
        notes_archive_folder_name="Archive",
        notes_log_folder_name="Logs",
        calendar_name="Work",
    )
    assert result == []


def test_ensure_gateway_resources_reminders_only():
    osa_result = _make_osa_result(ok=True, stdout="exists")
    with patch("apple_flow.gateway_setup.run_osascript_with_recovery", return_value=osa_result), \
         patch("apple_flow.gateway_setup.apple_tools.reminders_split_selector", side_effect=lambda s: [s]):
        result = ensure_gateway_resources(
            enable_reminders=True,
            enable_notes=False,
            enable_notes_logging=False,
            enable_calendar=False,
            reminders_list_name="Tasks",
            reminders_archive_list_name="Archive",
            notes_folder_name="Notes",
            notes_archive_folder_name="NotesArchive",
            notes_log_folder_name="Logs",
            calendar_name="Work",
        )

    assert len(result) == 2
    labels = [s.label for s in result]
    assert "Reminders task list" in labels
    assert "Reminders archive list" in labels


def test_ensure_gateway_resources_notes_only():
    osa_result = _make_osa_result(ok=True, stdout="created")
    with patch("apple_flow.gateway_setup.run_osascript_with_recovery", return_value=osa_result):
        result = ensure_gateway_resources(
            enable_reminders=False,
            enable_notes=True,
            enable_notes_logging=False,
            enable_calendar=False,
            reminders_list_name="Tasks",
            reminders_archive_list_name="Archive",
            notes_folder_name="Notes",
            notes_archive_folder_name="NotesArchive",
            notes_log_folder_name="Logs",
            calendar_name="Work",
        )

    assert len(result) == 2
    labels = [s.label for s in result]
    assert "Notes task folder" in labels
    assert "Notes archive folder" in labels


def test_ensure_gateway_resources_notes_logging():
    osa_result = _make_osa_result(ok=True, stdout="exists")
    with patch("apple_flow.gateway_setup.run_osascript_with_recovery", return_value=osa_result):
        result = ensure_gateway_resources(
            enable_reminders=False,
            enable_notes=False,
            enable_notes_logging=True,
            enable_calendar=False,
            reminders_list_name="Tasks",
            reminders_archive_list_name="Archive",
            notes_folder_name="Notes",
            notes_archive_folder_name="NotesArchive",
            notes_log_folder_name="Logs",
            calendar_name="Work",
        )

    assert len(result) == 1
    assert result[0].label == "Notes log folder"


def test_ensure_gateway_resources_calendar_only():
    osa_result = _make_osa_result(ok=True, stdout="created")
    with patch("apple_flow.gateway_setup.run_osascript_with_recovery", return_value=osa_result):
        result = ensure_gateway_resources(
            enable_reminders=False,
            enable_notes=False,
            enable_notes_logging=False,
            enable_calendar=True,
            reminders_list_name="Tasks",
            reminders_archive_list_name="Archive",
            notes_folder_name="Notes",
            notes_archive_folder_name="NotesArchive",
            notes_log_folder_name="Logs",
            calendar_name="Work",
        )

    assert len(result) == 1
    assert result[0].label == "Calendar"
    assert result[0].name == "Work"


def test_ensure_gateway_resources_all_enabled():
    osa_result = _make_osa_result(ok=True, stdout="exists")
    with patch("apple_flow.gateway_setup.run_osascript_with_recovery", return_value=osa_result), \
         patch("apple_flow.gateway_setup.apple_tools.reminders_split_selector", side_effect=lambda s: [s]):
        result = ensure_gateway_resources(
            enable_reminders=True,
            enable_notes=True,
            enable_notes_logging=True,
            enable_calendar=True,
            reminders_list_name="Tasks",
            reminders_archive_list_name="Archive",
            notes_folder_name="Notes",
            notes_archive_folder_name="NotesArchive",
            notes_log_folder_name="Logs",
            calendar_name="Work",
        )

    # 2 reminders + 2 notes + 1 notes_log + 1 calendar = 6
    assert len(result) == 6


# --- resolve_binary ---

def test_resolve_binary_found_via_which(tmp_path):
    fake_bin = tmp_path / "mybin"
    fake_bin.touch()
    fake_bin.chmod(0o755)

    with patch("shutil.which", return_value=str(fake_bin)):
        result = resolve_binary("mybin")

    assert result is not None
    assert "mybin" in result


def test_resolve_binary_not_found():
    with patch("shutil.which", return_value=None):
        # Also mock Path.exists() to return False for all candidates
        with patch.object(Path, "exists", return_value=False):
            result = resolve_binary("nonexistent-binary")

    assert result is None


def test_resolve_binary_found_in_candidate(tmp_path):
    fake_bin = tmp_path / "mybin"
    fake_bin.touch()
    fake_bin.chmod(0o755)

    candidates = [
        Path.home() / ".local" / "bin" / "mybin",
        Path("/opt/homebrew/bin") / "mybin",
        Path("/usr/local/bin") / "mybin",
    ]

    with patch("shutil.which", return_value=None):
        # Simulate found at /opt/homebrew/bin
        def fake_exists(self):
            return str(self) in [str(fake_bin), str(candidates[1])]

        def fake_is_file(self):
            return str(self) in [str(fake_bin), str(candidates[1])]

        with patch.object(Path, "exists", fake_exists), \
             patch.object(Path, "is_file", fake_is_file), \
             patch.object(Path, "resolve", lambda self: self):
            result = resolve_binary("mybin")

    # Should find it somewhere
    assert result is not None
