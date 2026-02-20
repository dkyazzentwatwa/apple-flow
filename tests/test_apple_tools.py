"""Tests for apple_tools.py — all subprocess.run calls are mocked."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import apple_flow.apple_tools as at
from apple_flow.apple_tools import (
    TOOLS_CONTEXT,
    _format_output,
    _parse_delimited_output,
    _parse_json_output,
    _run_script,
    calendar_create,
    calendar_list_calendars,
    calendar_list_events,
    calendar_search,
    mail_get_content,
    mail_list_unread,
    mail_search,
    mail_send,
    messages_list_recent_chats,
    messages_search,
    notes_append,
    notes_create,
    notes_get_content,
    notes_list,
    notes_list_folders,
    notes_search,
    reminders_complete,
    reminders_create,
    reminders_list,
    reminders_list_lists,
    reminders_search,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok_result(stdout: str) -> MagicMock:
    """Build a mock subprocess.CompletedProcess with returncode=0."""
    r = MagicMock()
    r.returncode = 0
    r.stdout = stdout
    r.stderr = ""
    return r


def _err_result(stderr: str = "boom") -> MagicMock:
    """Build a mock subprocess.CompletedProcess with returncode=1."""
    r = MagicMock()
    r.returncode = 1
    r.stdout = ""
    r.stderr = stderr
    return r


def _notes_tab(items: list[dict]) -> str:
    return "\n".join(
        "\t".join([i.get("id", ""), i.get("name", ""), i.get("preview", ""), i.get("modification_date", "")])
        for i in items
    )


def _make_notes(n: int = 2) -> list[dict]:
    return [
        {"id": f"id-{i}", "name": f"Note {i}", "preview": f"Body {i}", "modification_date": "2026-01-0{i}"}
        for i in range(1, n + 1)
    ]


# ---------------------------------------------------------------------------
# _run_script
# ---------------------------------------------------------------------------

class TestRunScript:
    def test_returns_stdout_on_success(self):
        with patch("subprocess.run", return_value=_ok_result("hello")):
            result = _run_script("tell application")
            assert result == "hello"

    def test_returns_none_on_nonzero_returncode(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert _run_script("x") is None

    def test_returns_none_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osascript", 30)):
            assert _run_script("x") is None

    def test_returns_none_on_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert _run_script("x") is None

    def test_returns_none_on_unexpected_exception(self):
        with patch("subprocess.run", side_effect=RuntimeError("oops")):
            assert _run_script("x") is None


# ---------------------------------------------------------------------------
# _parse_json_output
# ---------------------------------------------------------------------------

class TestParseJsonOutput:
    def test_parses_valid_json(self):
        raw = '[{"id": "1", "name": "Test"}]'
        assert _parse_json_output(raw) == [{"id": "1", "name": "Test"}]

    def test_empty_string_returns_empty(self):
        assert _parse_json_output("") == []

    def test_none_returns_empty(self):
        assert _parse_json_output(None) == []

    def test_empty_array_returns_empty(self):
        assert _parse_json_output("[]") == []

    def test_invalid_json_returns_empty(self):
        assert _parse_json_output("{not valid") == []

    def test_cleans_control_chars(self):
        raw = '[{"id": "1\x01\x02", "name": "test"}]'
        result = _parse_json_output(raw)
        assert result[0]["id"] == "1  "


# ---------------------------------------------------------------------------
# _parse_delimited_output
# ---------------------------------------------------------------------------

class TestParseDelimitedOutput:
    def test_parses_valid_tab_delimited(self):
        raw = "id-1\tNote 1\tpreview\t2026-01-01"
        result = _parse_delimited_output(raw, ["id", "name", "preview", "modification_date"])
        assert result == [{"id": "id-1", "name": "Note 1", "preview": "preview", "modification_date": "2026-01-01"}]

    def test_parses_multiple_records(self):
        raw = "id-1\tNote 1\tpreview\t2026-01-01\nid-2\tNote 2\tbody\t2026-01-02"
        result = _parse_delimited_output(raw, ["id", "name", "preview", "modification_date"])
        assert len(result) == 2
        assert result[1]["name"] == "Note 2"

    def test_skips_lines_with_wrong_field_count(self):
        raw = "id-1\ttoo-few-fields"
        result = _parse_delimited_output(raw, ["id", "name", "preview", "modification_date"])
        assert result == []

    def test_empty_string_returns_empty(self):
        assert _parse_delimited_output("", ["id", "name"]) == []

    def test_none_returns_empty(self):
        assert _parse_delimited_output(None, ["id", "name"]) == []

    def test_mixed_valid_and_invalid_lines(self):
        raw = "bad-line\nid-1\tName\tpreview\t2026-01-01\nalso-bad"
        result = _parse_delimited_output(raw, ["id", "name", "preview", "modification_date"])
        assert len(result) == 1
        assert result[0]["id"] == "id-1"


# ---------------------------------------------------------------------------
# _format_output
# ---------------------------------------------------------------------------

class TestFormatOutput:
    def test_returns_list_when_not_as_text(self):
        data = [{"name": "A"}, {"name": "B"}]
        result = _format_output(data, as_text=False)
        assert result == data

    def test_returns_string_when_as_text(self):
        data = [{"name": "Alpha"}, {"name": "Beta"}]
        result = _format_output(data, as_text=True)
        assert isinstance(result, str)
        assert "Alpha" in result
        assert "Beta" in result

    def test_returns_empty_string_for_empty_data(self):
        assert _format_output([], as_text=True) == ""

    def test_custom_format_fn(self):
        data = [{"name": "X", "date": "2026"}]
        result = _format_output(data, as_text=True, format_fn=lambda x: f"{x['name']}|{x['date']}")
        assert result == "X|2026"


# ---------------------------------------------------------------------------
# TOOLS_CONTEXT
# ---------------------------------------------------------------------------

class TestToolsContext:
    def test_nonempty(self):
        assert TOOLS_CONTEXT
        assert len(TOOLS_CONTEXT) > 100

    def test_mentions_all_categories(self):
        for category in ("NOTES", "MAIL", "REMINDERS", "CALENDAR", "MESSAGES"):
            assert category in TOOLS_CONTEXT, f"TOOLS_CONTEXT missing category: {category}"

    def test_mentions_apple_flow_tools(self):
        assert "apple-flow tools" in TOOLS_CONTEXT


# ---------------------------------------------------------------------------
# Apple Notes
# ---------------------------------------------------------------------------

class TestNotesListFolders:
    def test_returns_folder_names(self):
        with patch("subprocess.run", return_value=_ok_result("Work|||Personal|||Archive")):
            result = notes_list_folders()
            assert result == ["Work", "Personal", "Archive"]

    def test_returns_empty_on_failure(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert notes_list_folders() == []

    def test_returns_empty_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osascript", 30)):
            assert notes_list_folders() == []

    def test_returns_empty_on_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert notes_list_folders() == []


class TestNotesList:
    def test_returns_notes_list(self):
        notes = _make_notes(3)
        raw = _notes_tab(notes)
        with patch("subprocess.run", return_value=_ok_result(raw)):
            result = notes_list()
            assert isinstance(result, list)
            assert len(result) == 3
            assert result[0]["name"] == "Note 1"

    def test_as_text_returns_string_with_name(self):
        notes = _make_notes(2)
        raw = _notes_tab(notes)
        with patch("subprocess.run", return_value=_ok_result(raw)):
            result = notes_list(as_text=True)
            assert isinstance(result, str)
            assert "Note 1" in result

    def test_returns_empty_on_failure(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert notes_list() == []

    def test_returns_empty_on_malformed_input(self):
        with patch("subprocess.run", return_value=_ok_result("id-1\ttoo-few-fields")):
            assert notes_list() == []


class TestNotesSearch:
    def test_filters_by_query_name(self):
        notes = [
            {"id": "1", "name": "project alpha", "preview": "details", "modification_date": ""},
            {"id": "2", "name": "random note", "preview": "stuff", "modification_date": ""},
            {"id": "3", "name": "project beta", "preview": "more", "modification_date": ""},
        ]
        raw = _notes_tab(notes)
        with patch("subprocess.run", return_value=_ok_result(raw)):
            result = notes_search("project")
            assert isinstance(result, list)
            assert len(result) == 2
            assert all("project" in n["name"] for n in result)

    def test_filters_by_preview(self):
        notes = [
            {"id": "1", "name": "untitled", "preview": "contains keyword here", "modification_date": ""},
            {"id": "2", "name": "other", "preview": "nothing here", "modification_date": ""},
        ]
        raw = _notes_tab(notes)
        with patch("subprocess.run", return_value=_ok_result(raw)):
            result = notes_search("keyword")
            assert len(result) == 1

    def test_case_insensitive(self):
        notes = [{"id": "1", "name": "IMPORTANT Note", "preview": "", "modification_date": ""}]
        raw = _notes_tab(notes)
        with patch("subprocess.run", return_value=_ok_result(raw)):
            result = notes_search("important")
            assert len(result) == 1

    def test_as_text_returns_string(self):
        notes = [{"id": "1", "name": "My Note", "preview": "content", "modification_date": ""}]
        raw = _notes_tab(notes)
        with patch("subprocess.run", return_value=_ok_result(raw)):
            result = notes_search("note", as_text=True)
            assert isinstance(result, str)
            assert "My Note" in result

    def test_returns_empty_on_failure(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert notes_search("q") == []


class TestNotesGetContent:
    def test_returns_content_string(self):
        with patch("subprocess.run", return_value=_ok_result("Full note body here.")):
            result = notes_get_content("My Note")
            assert result == "Full note body here."

    def test_returns_empty_on_failure(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert notes_get_content("Missing") == ""

    def test_returns_empty_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osascript", 30)):
            assert notes_get_content("x") == ""


class TestNotesCreate:
    def test_returns_id_on_success(self):
        with patch("subprocess.run", return_value=_ok_result("x-coredata://abc123")):
            result = notes_create("Title", "Body")
            assert result == "x-coredata://abc123"

    def test_returns_none_on_error(self):
        with patch("subprocess.run", return_value=_ok_result("error: something went wrong")):
            assert notes_create("T", "B") is None

    def test_returns_none_on_failure(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert notes_create("T", "B") is None

    def test_returns_none_on_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert notes_create("T", "B") is None


class TestNotesAppend:
    def test_returns_true_on_ok(self):
        with patch("subprocess.run", return_value=_ok_result("ok")):
            assert notes_append("My Note", "new text") is True

    def test_returns_false_on_not_found(self):
        with patch("subprocess.run", return_value=_ok_result("error: note not found")):
            assert notes_append("Missing Note", "text") is False

    def test_returns_false_on_failure(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert notes_append("x", "y") is False

    def test_returns_false_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osascript", 30)):
            assert notes_append("x", "y") is False

    def test_returns_false_on_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert notes_append("x", "y") is False


# ---------------------------------------------------------------------------
# Apple Mail
# ---------------------------------------------------------------------------

def _mail_tab(items: list[dict]) -> str:
    return "\n".join(
        "\t".join([i.get("id", ""), i.get("sender", ""), i.get("subject", ""), i.get("body_preview", ""), i.get("date", ""), i.get("read", "")])
        for i in items
    )


def _make_mails(n: int = 2) -> list[dict]:
    return [
        {
            "id": str(i),
            "sender": f"user{i}@example.com",
            "subject": f"Subject {i}",
            "body_preview": f"Body {i}",
            "date": "2026-01-01",
            "read": "false",
        }
        for i in range(1, n + 1)
    ]


class TestMailListUnread:
    def test_returns_list(self):
        mails = _make_mails(3)
        with patch("subprocess.run", return_value=_ok_result(_mail_tab(mails))):
            result = mail_list_unread()
            assert isinstance(result, list)
            assert len(result) == 3

    def test_as_text_returns_string_with_sender(self):
        mails = _make_mails(1)
        with patch("subprocess.run", return_value=_ok_result(_mail_tab(mails))):
            result = mail_list_unread(as_text=True)
            assert isinstance(result, str)
            assert "user1@example.com" in result

    def test_returns_empty_on_failure(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert mail_list_unread() == []

    def test_returns_empty_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osascript", 30)):
            assert mail_list_unread() == []

    def test_returns_empty_on_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert mail_list_unread() == []

    def test_returns_empty_on_malformed_input(self):
        with patch("subprocess.run", return_value=_ok_result("id-1\ttoo-few-fields")):
            assert mail_list_unread() == []


class TestMailSearch:
    def test_filters_by_subject(self):
        mails = [
            {"id": "1", "sender": "a@b.com", "subject": "Invoice #123", "body_preview": "", "date": "", "read": "false"},
            {"id": "2", "sender": "x@y.com", "subject": "Hello World", "body_preview": "", "date": "", "read": "false"},
        ]
        with patch("subprocess.run", return_value=_ok_result(_mail_tab(mails))):
            result = mail_search("invoice")
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["subject"] == "Invoice #123"

    def test_filters_by_sender(self):
        mails = [
            {"id": "1", "sender": "boss@work.com", "subject": "Re: stuff", "body_preview": "", "date": "", "read": "false"},
            {"id": "2", "sender": "friend@personal.com", "subject": "Hi", "body_preview": "", "date": "", "read": "false"},
        ]
        with patch("subprocess.run", return_value=_ok_result(_mail_tab(mails))):
            result = mail_search("work.com")
            assert len(result) == 1

    def test_filters_by_body_preview(self):
        mails = [
            {"id": "1", "sender": "a@b.com", "subject": "Greet", "body_preview": "contains keyword here", "date": "", "read": "false"},
            {"id": "2", "sender": "a@b.com", "subject": "Other", "body_preview": "nothing special", "date": "", "read": "false"},
        ]
        with patch("subprocess.run", return_value=_ok_result(_mail_tab(mails))):
            result = mail_search("keyword")
            assert len(result) == 1

    def test_returns_empty_on_failure(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert mail_search("q") == []


class TestMailGetContent:
    def test_returns_content(self):
        with patch("subprocess.run", return_value=_ok_result("Full email body text here.")):
            result = mail_get_content("msg-id-123")
            assert result == "Full email body text here."

    def test_returns_empty_on_failure(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert mail_get_content("x") == ""

    def test_returns_empty_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osascript", 30)):
            assert mail_get_content("x") == ""


class TestMailSend:
    def test_returns_true_on_ok(self):
        with patch("subprocess.run", return_value=_ok_result("ok")):
            assert mail_send("to@test.com", "Subject", "Body") is True

    def test_returns_false_on_error(self):
        with patch("subprocess.run", return_value=_ok_result("error: failed to send")):
            assert mail_send("to@test.com", "S", "B") is False

    def test_returns_false_on_failure(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert mail_send("to@test.com", "S", "B") is False

    def test_returns_false_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osascript", 30)):
            assert mail_send("to@test.com", "S", "B") is False

    def test_returns_false_on_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert mail_send("to@test.com", "S", "B") is False


# ---------------------------------------------------------------------------
# Apple Reminders
# ---------------------------------------------------------------------------

def _rem_tab(items: list[dict]) -> str:
    return "\n".join(
        "\t".join([i.get("id", ""), i.get("name", ""), i.get("body", ""), i.get("due_date", ""), i.get("completed", ""), i.get("list", "")])
        for i in items
    )


def _make_reminders(n: int = 2) -> list[dict]:
    return [
        {
            "id": str(i),
            "name": f"Task {i}",
            "body": f"Notes {i}",
            "due_date": "",
            "completed": "false",
            "list": "Reminders",
        }
        for i in range(1, n + 1)
    ]


class TestRemindersListLists:
    def test_returns_list_names(self):
        with patch("subprocess.run", return_value=_ok_result("Reminders|||Work|||Personal")):
            result = reminders_list_lists()
            assert result == ["Reminders", "Work", "Personal"]

    def test_returns_empty_on_failure(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert reminders_list_lists() == []

    def test_returns_empty_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osascript", 30)):
            assert reminders_list_lists() == []


class TestRemindersList:
    def test_returns_list(self):
        rems = _make_reminders(3)
        with patch("subprocess.run", return_value=_ok_result(_rem_tab(rems))):
            result = reminders_list()
            assert isinstance(result, list)
            assert len(result) == 3

    def test_as_text_contains_name(self):
        rems = _make_reminders(2)
        with patch("subprocess.run", return_value=_ok_result(_rem_tab(rems))):
            result = reminders_list(as_text=True)
            assert isinstance(result, str)
            assert "Task 1" in result

    def test_returns_empty_on_failure(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert reminders_list() == []

    def test_returns_empty_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osascript", 30)):
            assert reminders_list() == []

    def test_returns_empty_on_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert reminders_list() == []

    def test_returns_empty_on_malformed_input(self):
        with patch("subprocess.run", return_value=_ok_result("id-1\ttoo-few-fields")):
            assert reminders_list() == []


class TestRemindersSearch:
    def test_filters_by_name(self):
        rems = [
            {"id": "1", "name": "buy groceries", "body": "", "due_date": "", "completed": "false", "list": ""},
            {"id": "2", "name": "dentist appointment", "body": "", "due_date": "", "completed": "false", "list": ""},
            {"id": "3", "name": "buy milk", "body": "", "due_date": "", "completed": "false", "list": ""},
        ]
        with patch("subprocess.run", return_value=_ok_result(_rem_tab(rems))):
            result = reminders_search("buy")
            assert isinstance(result, list)
            assert len(result) == 2

    def test_filters_by_body(self):
        rems = [
            {"id": "1", "name": "meeting", "body": "discuss project alpha", "due_date": "", "completed": "false", "list": ""},
            {"id": "2", "name": "lunch", "body": "with team", "due_date": "", "completed": "false", "list": ""},
        ]
        with patch("subprocess.run", return_value=_ok_result(_rem_tab(rems))):
            result = reminders_search("project")
            assert len(result) == 1

    def test_case_insensitive(self):
        rems = [{"id": "1", "name": "URGENT Task", "body": "", "due_date": "", "completed": "false", "list": ""}]
        with patch("subprocess.run", return_value=_ok_result(_rem_tab(rems))):
            assert len(reminders_search("urgent")) == 1

    def test_returns_empty_on_failure(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert reminders_search("q") == []


class TestRemindersCreate:
    def test_returns_id_on_success(self):
        with patch("subprocess.run", return_value=_ok_result("x-apple-id://rem-123")):
            result = reminders_create("Buy milk", list_name="Shopping")
            assert result == "x-apple-id://rem-123"

    def test_returns_none_on_error(self):
        with patch("subprocess.run", return_value=_ok_result("error: list not found")):
            assert reminders_create("Task") is None

    def test_returns_none_on_failure(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert reminders_create("Task") is None

    def test_returns_none_on_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert reminders_create("Task") is None


class TestRemindersComplete:
    def test_returns_true_on_ok(self):
        with patch("subprocess.run", return_value=_ok_result("ok")):
            assert reminders_complete("rem-id-1", "Reminders") is True

    def test_returns_false_on_error(self):
        with patch("subprocess.run", return_value=_ok_result("error: not found")):
            assert reminders_complete("rem-id-1", "Reminders") is False

    def test_returns_false_on_failure(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert reminders_complete("rem-id-1", "Reminders") is False

    def test_returns_false_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osascript", 30)):
            assert reminders_complete("rem-id-1", "Reminders") is False

    def test_returns_false_on_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert reminders_complete("rem-id-1", "Reminders") is False


# ---------------------------------------------------------------------------
# Apple Calendar
# ---------------------------------------------------------------------------

def _evt_tab(items: list[dict]) -> str:
    return "\n".join(
        "\t".join([i.get("id", ""), i.get("summary", ""), i.get("description", ""), i.get("start_date", ""), i.get("end_date", ""), i.get("calendar", "")])
        for i in items
    )


def _make_events(n: int = 2) -> list[dict]:
    return [
        {
            "id": f"uid-{i}",
            "summary": f"Event {i}",
            "description": f"Desc {i}",
            "start_date": f"2026-02-{10+i}",
            "end_date": f"2026-02-{10+i}",
            "calendar": "Work",
        }
        for i in range(1, n + 1)
    ]


class TestCalendarListCalendars:
    def test_returns_calendar_names(self):
        with patch("subprocess.run", return_value=_ok_result("Work|||Home|||Holidays")):
            result = calendar_list_calendars()
            assert result == ["Work", "Home", "Holidays"]

    def test_returns_empty_on_failure(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert calendar_list_calendars() == []

    def test_returns_empty_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osascript", 30)):
            assert calendar_list_calendars() == []

    def test_returns_empty_on_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert calendar_list_calendars() == []


class TestCalendarListEvents:
    def test_returns_events(self):
        evts = _make_events(3)
        with patch("subprocess.run", return_value=_ok_result(_evt_tab(evts))):
            result = calendar_list_events()
            assert isinstance(result, list)
            assert len(result) == 3
            assert result[0]["summary"] == "Event 1"

    def test_as_text_contains_summary(self):
        evts = _make_events(2)
        with patch("subprocess.run", return_value=_ok_result(_evt_tab(evts))):
            result = calendar_list_events(as_text=True)
            assert isinstance(result, str)
            assert "Event 1" in result

    def test_returns_empty_on_failure(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert calendar_list_events() == []

    def test_returns_empty_on_malformed_input(self):
        with patch("subprocess.run", return_value=_ok_result("id-1\ttoo-few-fields")):
            assert calendar_list_events() == []

    def test_returns_empty_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osascript", 30)):
            assert calendar_list_events() == []

    def test_returns_empty_on_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert calendar_list_events() == []


class TestCalendarSearch:
    def test_filters_by_summary(self):
        evts = [
            {"id": "1", "summary": "Team Standup", "description": "", "start_date": "", "end_date": "", "calendar": ""},
            {"id": "2", "summary": "Doctor Visit", "description": "", "start_date": "", "end_date": "", "calendar": ""},
            {"id": "3", "summary": "Team Retrospective", "description": "", "start_date": "", "end_date": "", "calendar": ""},
        ]
        with patch("subprocess.run", return_value=_ok_result(_evt_tab(evts))):
            result = calendar_search("team")
            assert isinstance(result, list)
            assert len(result) == 2

    def test_filters_by_description(self):
        evts = [
            {"id": "1", "summary": "Lunch", "description": "discuss quarterly targets", "start_date": "", "end_date": "", "calendar": ""},
            {"id": "2", "summary": "Gym", "description": "morning workout", "start_date": "", "end_date": "", "calendar": ""},
        ]
        with patch("subprocess.run", return_value=_ok_result(_evt_tab(evts))):
            result = calendar_search("quarterly")
            assert len(result) == 1

    def test_case_insensitive(self):
        evts = [{"id": "1", "summary": "BOARD MEETING", "description": "", "start_date": "", "end_date": "", "calendar": ""}]
        with patch("subprocess.run", return_value=_ok_result(_evt_tab(evts))):
            assert len(calendar_search("board")) == 1

    def test_returns_empty_on_failure(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert calendar_search("q") == []


class TestCalendarCreate:
    def test_returns_uid_on_success(self):
        with patch("subprocess.run", return_value=_ok_result("UID-abc-123")):
            result = calendar_create("Meeting", "2026-03-01 09:00")
            assert result == "UID-abc-123"

    def test_returns_none_on_error(self):
        with patch("subprocess.run", return_value=_ok_result("error: calendar not found")):
            assert calendar_create("Event", "2026-03-01") is None

    def test_returns_none_on_failure(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert calendar_create("Event", "2026-03-01") is None

    def test_returns_none_on_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert calendar_create("Event", "2026-03-01") is None


# ---------------------------------------------------------------------------
# iMessage (SQLite mocked)
# ---------------------------------------------------------------------------

class TestMessagesListRecentChats:
    def test_returns_chats(self):
        # Mock the sqlite3 connection
        mock_conn = MagicMock()
        mock_rows = [
            {"handle": "+15551234567", "service": "iMessage"},
            {"handle": "+15559876543", "service": "SMS"},
        ]
        mock_conn.execute.return_value.fetchall.return_value = [
            _sqlite_row(r) for r in mock_rows
        ]
        with patch.object(at, "_messages_connect", return_value=mock_conn):
            result = messages_list_recent_chats()
            assert isinstance(result, list)
            assert len(result) == 2
            assert result[0]["handle"] == "+15551234567"

    def test_as_text_returns_string(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            _sqlite_row({"handle": "+15551234567", "service": "iMessage"}),
        ]
        with patch.object(at, "_messages_connect", return_value=mock_conn):
            result = messages_list_recent_chats(as_text=True)
            assert isinstance(result, str)
            assert "+15551234567" in result

    def test_returns_empty_when_db_unavailable(self):
        with patch.object(at, "_messages_connect", return_value=None):
            assert messages_list_recent_chats() == []

    def test_returns_empty_on_query_failure(self):
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("no such table")
        with patch.object(at, "_messages_connect", return_value=mock_conn):
            assert messages_list_recent_chats() == []


class TestMessagesSearch:
    def test_returns_messages(self):
        mock_conn = MagicMock()
        mock_rows = [
            {"handle": "+15551234567", "text": "hello world", "date": 123456789},
        ]
        mock_conn.execute.return_value.fetchall.return_value = [
            _sqlite_row(r) for r in mock_rows
        ]
        with patch.object(at, "_messages_connect", return_value=mock_conn):
            result = messages_search("hello")
            assert isinstance(result, list)
            assert len(result) == 1
            assert "hello" in result[0]["text"]

    def test_as_text_returns_string(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            _sqlite_row({"handle": "+15551234567", "text": "test message", "date": 0}),
        ]
        with patch.object(at, "_messages_connect", return_value=mock_conn):
            result = messages_search("test", as_text=True)
            assert isinstance(result, str)
            assert "+15551234567" in result

    def test_returns_empty_when_db_unavailable(self):
        with patch.object(at, "_messages_connect", return_value=None):
            result = messages_search("q")
            assert result == []

    def test_returns_empty_on_query_failure(self):
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("no such column")
        with patch.object(at, "_messages_connect", return_value=mock_conn):
            assert messages_search("q") == []


# ---------------------------------------------------------------------------
# Connector prompt injection
# ---------------------------------------------------------------------------

class TestConnectorToolsContextInjection:
    """Verify that ClaudeCliConnector and CodexCliConnector inject TOOLS_CONTEXT."""

    def test_claude_connector_injects_tools_context(self):
        from apple_flow.claude_cli_connector import ClaudeCliConnector

        conn = ClaudeCliConnector(inject_tools_context=True)
        prompt = conn._build_prompt_with_context("sender", "do something")
        assert "apple-flow tools" in prompt

    def test_claude_connector_no_injection_when_disabled(self):
        from apple_flow.claude_cli_connector import ClaudeCliConnector

        conn = ClaudeCliConnector(inject_tools_context=False)
        prompt = conn._build_prompt_with_context("sender", "do something")
        assert "apple-flow tools" not in prompt

    def test_codex_connector_injects_tools_context(self):
        from apple_flow.codex_cli_connector import CodexCliConnector

        conn = CodexCliConnector(inject_tools_context=True)
        prompt = conn._build_prompt_with_context("sender", "do something")
        assert "apple-flow tools" in prompt

    def test_codex_connector_no_injection_when_disabled(self):
        from apple_flow.codex_cli_connector import CodexCliConnector

        conn = CodexCliConnector(inject_tools_context=False)
        prompt = conn._build_prompt_with_context("sender", "do something")
        assert "apple-flow tools" not in prompt

    def test_claude_connector_with_history_and_tools_context(self):
        from apple_flow.claude_cli_connector import ClaudeCliConnector

        conn = ClaudeCliConnector(inject_tools_context=True, context_window=3)
        conn._sender_contexts["sender"] = ["User: hi\nAssistant: hello"]
        prompt = conn._build_prompt_with_context("sender", "next message")
        assert "apple-flow tools" in prompt
        assert "Previous conversation context" in prompt
        assert "next message" in prompt

    def test_codex_connector_with_history_and_tools_context(self):
        from apple_flow.codex_cli_connector import CodexCliConnector

        conn = CodexCliConnector(inject_tools_context=True, context_window=3)
        conn._sender_contexts["sender"] = ["User: hi\nAssistant: hello"]
        prompt = conn._build_prompt_with_context("sender", "next message")
        assert "apple-flow tools" in prompt
        assert "Previous conversation context" in prompt


# ---------------------------------------------------------------------------
# Helpers for sqlite3.Row mocking
# ---------------------------------------------------------------------------

def _sqlite_row(data: dict) -> MagicMock:
    """Return a mock that behaves like sqlite3.Row for dict key access."""
    row = MagicMock()
    row.__getitem__ = lambda self, key: data[key]
    row.keys = lambda: data.keys()
    return row
