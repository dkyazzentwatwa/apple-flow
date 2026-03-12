"""Tests for Apple Reminders egress module."""

from __future__ import annotations

import apple_flow.reminders_accessibility as reminders_ax

from apple_flow.reminders_egress import AppleRemindersEgress


def test_complete_reminder_builds_correct_script(monkeypatch):
    """Verify complete_reminder calls osascript with the right args."""
    captured_scripts: list[str] = []

    def fake_run(args, **kwargs):
        captured_scripts.append(args[2])  # args = ["osascript", "-e", script]

        class Result:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Result()

    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)

    egress = AppleRemindersEgress(list_name="agent-task")
    result = egress.complete_reminder("rem_001", "Task completed successfully")

    assert result is True
    script = captured_scripts[-1]
    assert "rem_001" in script
    assert "agent-task" in script
    assert "completed of matchedReminder to true" in script


def test_complete_reminder_uses_resolved_nested_list_id(monkeypatch):
    captured_scripts: list[str] = []

    def fake_run(args, **kwargs):
        captured_scripts.append(args[2])

        class Result:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Result()

    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)

    egress = AppleRemindersEgress(list_name="iCloud/Linear/agent-task")
    monkeypatch.setattr(
        egress,
        "_resolve_list_selector",
        lambda selector: {
            "id": "list_dev",
            "name": "agent-task",
            "path": "iCloud/Linear/agent-task",
        },
    )
    result = egress.complete_reminder("rem_001", "Task completed successfully")

    assert result is True
    script = captured_scripts[0]
    assert 'set taskList to first list whose id is "list_dev"' in script
    assert 'set taskList to list "iCloud/Linear/agent-task"' not in script


def test_complete_reminder_returns_false_on_error(monkeypatch):
    def fake_run(args, **kwargs):
        class Result:
            returncode = 1
            stdout = "error: reminder not found"
            stderr = ""

        return Result()

    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)

    egress = AppleRemindersEgress(list_name="agent-task")
    result = egress.complete_reminder("rem_missing", "some text")

    assert result is False


def test_complete_reminder_handles_timeout(monkeypatch):
    import subprocess

    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=15)

    monkeypatch.setattr(subprocess, "run", fake_run)

    egress = AppleRemindersEgress(list_name="agent-task")
    result = egress.complete_reminder("rem_001", "text")

    assert result is False


def test_complete_reminder_handles_missing_osascript(monkeypatch):
    import subprocess

    def fake_run(args, **kwargs):
        raise FileNotFoundError("osascript not found")

    monkeypatch.setattr(subprocess, "run", fake_run)

    egress = AppleRemindersEgress(list_name="agent-task")
    result = egress.complete_reminder("rem_001", "text")

    assert result is False


def test_complete_reminder_uses_accessibility_backend_for_ax_id(monkeypatch):
    egress = AppleRemindersEgress(list_name="dev-waiting")
    monkeypatch.setattr(
        egress,
        "_resolve_list_selector",
        lambda selector: {
            "id": "",
            "name": "dev-waiting",
            "path": "iCloud/linear/dev-waiting",
            "source": "accessibility",
        },
    )
    from apple_flow import reminders_accessibility as reminders_ax

    called: dict[str, str] = {}

    def fake_complete(list_path, reminder_id, note):
        called["list_path"] = list_path
        called["reminder_id"] = reminder_id
        called["note"] = note
        return True

    monkeypatch.setattr(reminders_ax, "complete_reminder", fake_complete)

    assert egress.complete_reminder("ax://rem-001", "Task completed successfully") is True
    assert called["list_path"] == "iCloud/linear/dev-waiting"
    assert called["reminder_id"] == "ax://rem-001"


def test_annotate_reminder_builds_correct_script(monkeypatch):
    captured_scripts: list[str] = []

    def fake_run(args, **kwargs):
        captured_scripts.append(args[2])

        class Result:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Result()

    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)

    egress = AppleRemindersEgress(list_name="agent-task")
    result = egress.annotate_reminder("rem_002", "Awaiting approval")

    assert result is True
    script = captured_scripts[-1]
    assert "rem_002" in script
    assert "agent-task" in script
    # Should NOT mark as completed.
    assert "completed of matchedReminder to true" not in script


def test_annotate_reminder_returns_false_on_error(monkeypatch):
    def fake_run(args, **kwargs):
        class Result:
            returncode = 0
            stdout = "error: list not found"
            stderr = ""

        return Result()

    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)

    egress = AppleRemindersEgress(list_name="agent-task")
    result = egress.annotate_reminder("rem_002", "note text")

    assert result is False


def test_annotate_reminder_uses_accessibility_for_ax_id(monkeypatch):
    egress = AppleRemindersEgress(list_name="dev-waiting")
    monkeypatch.setattr(
        egress,
        "_resolve_list_selector",
        lambda selector: {
            "id": "",
            "name": "dev-waiting",
            "path": "iCloud/linear/dev-waiting",
            "source": "accessibility",
        },
    )

    called: dict[str, str] = {}

    def fake_annotate(list_path: str, reminder_id: str, note: str) -> bool:
        called["list_path"] = list_path
        called["reminder_id"] = reminder_id
        called["note"] = note
        return True

    monkeypatch.setattr(reminders_ax, "annotate_reminder", fake_annotate)

    result = egress.annotate_reminder("ax://dev-waiting-1", "Awaiting approval")

    assert result is True
    assert called == {
        "reminder_id": "ax://dev-waiting-1",
        "list_path": "iCloud/linear/dev-waiting",
        "note": "Awaiting approval",
    }


def test_annotate_reminder_uses_accessibility_backend_for_ax_id(monkeypatch):
    egress = AppleRemindersEgress(list_name="dev-waiting")
    monkeypatch.setattr(
        egress,
        "_resolve_list_selector",
        lambda selector: {
            "id": "",
            "name": "dev-waiting",
            "path": "iCloud/linear/dev-waiting",
            "source": "accessibility",
        },
    )
    from apple_flow import reminders_accessibility as reminders_ax

    called: dict[str, str] = {}

    def fake_annotate(list_path, reminder_id, note):
        called["list_path"] = list_path
        called["reminder_id"] = reminder_id
        called["note"] = note
        return True

    monkeypatch.setattr(reminders_ax, "annotate_reminder", fake_annotate)

    assert egress.annotate_reminder("ax://rem-002", "Awaiting approval") is True
    assert called["list_path"] == "iCloud/linear/dev-waiting"
    assert called["reminder_id"] == "ax://rem-002"


def test_escapes_special_characters_in_text(monkeypatch):
    captured_scripts: list[str] = []

    def fake_run(args, **kwargs):
        captured_scripts.append(args[2])

        class Result:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Result()

    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)

    egress = AppleRemindersEgress()
    egress.complete_reminder("rem_esc", 'Text with "quotes" and \\backslashes\\')

    script = captured_scripts[-1]
    # Verify special characters are escaped.
    assert '\\"' in script or "quotes" in script


def test_move_to_archive_builds_correct_script(monkeypatch):
    """Verify move_to_archive calls osascript with the right args."""
    captured_scripts: list[str] = []

    def fake_run(args, **kwargs):
        captured_scripts.append(args[2])  # args = ["osascript", "-e", script]

        class Result:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Result()

    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)

    egress = AppleRemindersEgress(list_name="agent-task")
    result = egress.move_to_archive(
        reminder_id="rem_003",
        result_text="Task executed successfully",
        source_list_name="agent-task",
        archive_list_name="Archive",
    )

    assert result is True
    script = captured_scripts[-1]
    assert "rem_003" in script
    assert "agent-task" in script
    assert "Archive" in script
    assert "completed of matchedReminder to true" in script
    assert "move matchedReminder to archiveList" in script


def test_move_to_archive_returns_false_on_error(monkeypatch):
    def fake_run(args, **kwargs):
        class Result:
            returncode = 1
            stdout = "error: archive list not found"
            stderr = ""

        return Result()

    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)

    egress = AppleRemindersEgress(list_name="agent-task")
    result = egress.move_to_archive(
        reminder_id="rem_004",
        result_text="Some result",
        source_list_name="agent-task",
        archive_list_name="NonExistentArchive",
    )

    assert result is False


def test_move_to_archive_handles_timeout(monkeypatch):
    import subprocess

    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=15)

    monkeypatch.setattr(subprocess, "run", fake_run)

    egress = AppleRemindersEgress(list_name="agent-task")
    result = egress.move_to_archive(
        reminder_id="rem_005",
        result_text="text",
        source_list_name="agent-task",
        archive_list_name="Archive",
    )

    assert result is False


def test_move_to_archive_uses_accessibility_for_ax_id(monkeypatch):
    egress = AppleRemindersEgress(list_name="dev-waiting")

    def fake_resolve(selector: str) -> dict[str, str]:
        if selector == "dev-waiting":
            return {
                "id": "",
                "name": "dev-waiting",
                "path": "iCloud/linear/dev-waiting",
                "source": "accessibility",
            }
        return {
            "id": "",
            "name": "agent-archive",
            "path": "iCloud/linear/agent-archive",
            "source": "accessibility",
        }

    monkeypatch.setattr(egress, "_resolve_list_selector", fake_resolve)

    called: dict[str, str] = {}

    def fake_move(reminder_id: str, source_list_path: str, archive_list_path: str, result_text: str) -> bool:
        called["reminder_id"] = reminder_id
        called["source_list_path"] = source_list_path
        called["archive_list_path"] = archive_list_path
        called["result_text"] = result_text
        return True

    monkeypatch.setattr(reminders_ax, "move_to_archive", fake_move)

    result = egress.move_to_archive(
        reminder_id="ax://dev-waiting-1",
        result_text="Done",
        source_list_name="dev-waiting",
        archive_list_name="agent-archive",
    )

    assert result is True
    assert called == {
        "reminder_id": "ax://dev-waiting-1",
        "source_list_path": "iCloud/linear/dev-waiting",
        "archive_list_path": "iCloud/linear/agent-archive",
        "result_text": "Done",
    }


def test_move_to_archive_uses_accessibility_backend_for_ax_id(monkeypatch):
    egress = AppleRemindersEgress(list_name="dev-waiting")
    resolved = {
        "id": "",
        "name": "dev-waiting",
        "path": "iCloud/linear/dev-waiting",
        "source": "accessibility",
    }
    archive = {
        "id": "",
        "name": "Archive",
        "path": "iCloud/Archive",
        "source": "applescript",
    }
    monkeypatch.setattr(
        egress,
        "_resolve_list_selector",
        lambda selector: resolved if selector == "dev-waiting" else archive,
    )
    from apple_flow import reminders_accessibility as reminders_ax

    called: dict[str, str] = {}

    def fake_move(reminder_id, source_list_path, archive_list_path, result_text):
        called["reminder_id"] = reminder_id
        called["source_list_path"] = source_list_path
        called["archive_list_path"] = archive_list_path
        called["result_text"] = result_text
        return True

    monkeypatch.setattr(reminders_ax, "move_to_archive", fake_move)

    assert egress.move_to_archive("ax://rem-003", "done", "dev-waiting", "Archive") is True
    assert called["source_list_path"] == "iCloud/linear/dev-waiting"
    assert called["archive_list_path"] == "iCloud/Archive"
