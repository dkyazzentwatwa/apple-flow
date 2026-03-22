"""Tests for Apple Reminders egress module."""

from __future__ import annotations

from apple_flow.reminders_egress import AppleRemindersEgress


def test_complete_reminder_builds_correct_script(monkeypatch):
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
    result = egress.complete_reminder("rem_001", "Task completed successfully")

    assert result is True
    script = captured_scripts[-1]
    assert "rem_001" in script
    assert "agent-task" in script
    assert "completed of matchedReminder to true" in script


def test_complete_reminder_uses_resolved_list_id(monkeypatch):
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
    monkeypatch.setattr(
        egress,
        "_resolve_list_selector",
        lambda selector: {
            "id": "list_dev",
            "name": "agent-task",
            "path": "agent-task",
            "source": "applescript",
        },
    )
    result = egress.complete_reminder("rem_001", "Task completed successfully")

    assert result is True
    script = captured_scripts[0]
    assert 'set taskList to first list whose id is "list_dev"' in script


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


def test_move_to_archive_builds_correct_script(monkeypatch):
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
    result = egress.move_to_archive("rem_003", "done", "agent-task", "agent-archive")

    assert result is True
    script = captured_scripts[-1]
    assert "rem_003" in script
    assert 'set sourceList to list "agent-task"' in script
    assert 'set archiveList to list "agent-archive"' in script
    assert "move matchedReminder to archiveList" in script


def test_move_to_archive_returns_false_on_error(monkeypatch):
    def fake_run(args, **kwargs):
        class Result:
            returncode = 1
            stdout = "error: archive list missing"
            stderr = ""

        return Result()

    import subprocess

    monkeypatch.setattr(subprocess, "run", fake_run)

    egress = AppleRemindersEgress(list_name="agent-task")
    result = egress.move_to_archive("rem_003", "done", "agent-task", "agent-archive")

    assert result is False
