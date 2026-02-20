"""Tests for Apple Notes egress."""

import subprocess
from unittest.mock import MagicMock, patch

from apple_flow.notes_egress import AppleNotesEgress


def _make_egress():
    return AppleNotesEgress(folder_name="agent-task")


@patch("apple_flow.notes_egress.subprocess.run")
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


@patch("apple_flow.notes_egress.subprocess.run")
def test_append_result_failure_returncode(mock_run):
    result = MagicMock()
    result.returncode = 1
    result.stdout = "error: something went wrong"
    mock_run.return_value = result

    egress = _make_egress()
    ok = egress.append_result("note123", "Result text")

    assert ok is False


@patch("apple_flow.notes_egress.subprocess.run")
def test_append_result_failure_error_output(mock_run):
    result = MagicMock()
    result.returncode = 0
    result.stdout = "error: note not found"
    mock_run.return_value = result

    egress = _make_egress()
    ok = egress.append_result("note123", "Result text")

    assert ok is False


@patch("apple_flow.notes_egress.subprocess.run")
def test_append_result_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=15)

    egress = _make_egress()
    ok = egress.append_result("note123", "Result text")

    assert ok is False


@patch("apple_flow.notes_egress.subprocess.run")
def test_append_result_osascript_not_found(mock_run):
    mock_run.side_effect = FileNotFoundError("osascript not found")

    egress = _make_egress()
    ok = egress.append_result("note123", "Result text")

    assert ok is False


@patch("apple_flow.notes_egress.subprocess.run")
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


# --- move_to_archive tests ---


@patch("apple_flow.notes_egress.subprocess.run")
def test_move_to_archive_builds_correct_script(mock_run):
    """Verify move_to_archive generates the correct AppleScript with nested folder syntax."""
    result = MagicMock()
    result.returncode = 0
    result.stdout = "ok\n"
    result.stderr = ""
    mock_run.return_value = result

    egress = _make_egress()
    ok = egress.move_to_archive(
        note_id="x-coredata://ABC123",
        result_text="Task completed successfully",
        source_folder_name="codex-task",
        archive_subfolder_name="codex-archive",
    )

    assert ok is True
    mock_run.assert_called_once()

    # Extract the script argument
    script = mock_run.call_args[0][0][2]

    # Verify key AppleScript elements
    assert 'folder "codex-task"' in script
    assert 'folder "codex-archive" of folder "codex-task"' in script
    assert 'x-coredata://ABC123' in script
    assert 'Task completed successfully' in script
    assert "move matchedNote to archiveFolder" in script


@patch("apple_flow.notes_egress.subprocess.run")
def test_move_to_archive_returns_false_on_error(mock_run):
    """Verify move_to_archive returns False when AppleScript errors."""
    result = MagicMock()
    result.returncode = 1
    result.stdout = "error: Note not found\n"
    result.stderr = ""
    mock_run.return_value = result

    egress = _make_egress()
    ok = egress.move_to_archive(
        note_id="x-coredata://INVALID",
        result_text="Test result",
        source_folder_name="codex-task",
        archive_subfolder_name="codex-archive",
    )

    assert ok is False


@patch("apple_flow.notes_egress.subprocess.run")
def test_move_to_archive_handles_timeout(mock_run):
    """Verify move_to_archive handles subprocess timeout gracefully."""
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=15)

    egress = _make_egress()
    ok = egress.move_to_archive(
        note_id="x-coredata://ABC123",
        result_text="Test result",
        source_folder_name="codex-task",
        archive_subfolder_name="codex-archive",
    )

    assert ok is False


@patch("apple_flow.notes_egress.subprocess.run")
def test_move_to_archive_uses_nested_folder_syntax(mock_run):
    """Verify that the archive folder is referenced as a nested subfolder."""
    result = MagicMock()
    result.returncode = 0
    result.stdout = "ok\n"
    result.stderr = ""
    mock_run.return_value = result

    egress = _make_egress()
    egress.move_to_archive(
        note_id="x-coredata://TEST",
        result_text="Result",
        source_folder_name="My Folder",
        archive_subfolder_name="Archive",
    )

    script = mock_run.call_args[0][0][2]

    # Should reference archive as nested within source folder
    assert 'folder "Archive" of folder "My Folder"' in script


@patch("apple_flow.notes_egress.subprocess.run")
def test_move_to_archive_escapes_special_characters(mock_run):
    """Verify proper escaping of quotes and backslashes in text."""
    result = MagicMock()
    result.returncode = 0
    result.stdout = "ok\n"
    result.stderr = ""
    mock_run.return_value = result

    egress = _make_egress()
    egress.move_to_archive(
        note_id="x-coredata://TEST",
        result_text='Result with "quotes" and \\ backslash',
        source_folder_name="codex-task",
        archive_subfolder_name="codex-archive",
    )

    script = mock_run.call_args[0][0][2]

    # Verify escaping
    assert '\\"quotes\\"' in script
    assert '\\\\' in script


@patch("apple_flow.notes_egress.subprocess.run")
def test_move_to_archive_handles_osascript_not_found(mock_run):
    """Verify graceful handling when osascript is not available."""
    mock_run.side_effect = FileNotFoundError("osascript not found")

    egress = _make_egress()
    ok = egress.move_to_archive(
        note_id="x-coredata://TEST",
        result_text="Result",
        source_folder_name="codex-task",
        archive_subfolder_name="codex-archive",
    )

    assert ok is False


# --- create_log_note tests ---


@patch("apple_flow.notes_egress.subprocess.run")
def test_create_log_note_success(mock_run):
    result = MagicMock()
    result.returncode = 0
    result.stdout = "ok\n"
    result.stderr = ""
    mock_run.return_value = result

    egress = AppleNotesEgress(folder_name="agent-task")
    ok = egress.create_log_note(
        folder_name="codex-logs",
        title="[chat] hello — 2024-01-15 14:32:05 UTC",
        body="CODEX LOG\n---\nCommand: chat\n---\nhello",
    )

    assert ok is True
    mock_run.assert_called_once()
    script = mock_run.call_args[0][0][2]
    assert "codex-logs" in script
    assert "make new note" in script


@patch("apple_flow.notes_egress.subprocess.run")
def test_create_log_note_failure_returncode(mock_run):
    result = MagicMock()
    result.returncode = 1
    result.stdout = "error: folder not found\n"
    result.stderr = ""
    mock_run.return_value = result

    egress = AppleNotesEgress(folder_name="agent-task")
    ok = egress.create_log_note(
        folder_name="codex-logs",
        title="[chat] test — 2024-01-15",
        body="body text",
    )
    assert ok is False


@patch("apple_flow.notes_egress.subprocess.run")
def test_create_log_note_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=15)

    egress = AppleNotesEgress(folder_name="agent-task")
    ok = egress.create_log_note("codex-logs", "[idea] test", "body text")
    assert ok is False


@patch("apple_flow.notes_egress.subprocess.run")
def test_create_log_note_osascript_not_found(mock_run):
    mock_run.side_effect = FileNotFoundError("osascript not found")

    egress = AppleNotesEgress(folder_name="agent-task")
    ok = egress.create_log_note("codex-logs", "[plan] test", "body text")
    assert ok is False


@patch("apple_flow.notes_egress.subprocess.run")
def test_create_log_note_escapes_double_quotes(mock_run):
    result = MagicMock()
    result.returncode = 0
    result.stdout = "ok\n"
    result.stderr = ""
    mock_run.return_value = result

    egress = AppleNotesEgress(folder_name="agent-task")
    ok = egress.create_log_note(
        folder_name="codex-logs",
        title='[chat] He said "hello"',
        body='He said "hello" and goodbye',
    )
    assert ok is True
    script = mock_run.call_args[0][0][2]
    # Double quotes in title/body must be backslash-escaped for AppleScript
    assert '\\"hello\\"' in script
