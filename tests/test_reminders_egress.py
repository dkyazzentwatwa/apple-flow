"""Tests for Apple Reminders egress module."""

from __future__ import annotations

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
    assert len(captured_scripts) == 1
    script = captured_scripts[0]
    assert "rem_001" in script
    assert "agent-task" in script
    assert "completed of matchedReminder to true" in script


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
    assert len(captured_scripts) == 1
    script = captured_scripts[0]
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

    script = captured_scripts[0]
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
    assert len(captured_scripts) == 1
    script = captured_scripts[0]
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
