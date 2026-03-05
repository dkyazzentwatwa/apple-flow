"""Tests for apple_tools.py — all subprocess.run calls are mocked."""

from __future__ import annotations

import io
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
    mail_list_mailboxes,
    mail_list_unread,
    mail_move_to_label,
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
    numbers_add_sheet,
    numbers_append_rows,
    numbers_create,
    numbers_create_workbook,
    numbers_style_apply,
    pages_append,
    pages_create,
    pages_from_markdown,
    pages_template,
    pages_update_sections,
    phone_call,
    phone_call_me,
    phone_tts_in_call,
    phone_tts_say,
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

    def test_retries_transient_connection_invalid_then_succeeds(self):
        first = _err_result(
            "Connection Invalid error for service com.apple.hiservices-xpcservice.\n"
            "Error received in message reply handler: Connection invalid"
        )
        second = _ok_result("ready")
        with patch("subprocess.run", side_effect=[first, second]) as run_mock:
            with patch("apple_flow.apple_tools.time.sleep") as sleep_mock:
                assert _run_script("x") == "ready"
                assert run_mock.call_count == 2
                sleep_mock.assert_called_once()

    def test_transient_connection_invalid_exhausts_retries(self):
        transient = _err_result(
            "Connection Invalid error for service com.apple.hiservices-xpcservice.\n"
            "Error received in message reply handler: Connection invalid"
        )
        with patch("subprocess.run", side_effect=[transient] * 8) as run_mock:
            with patch("apple_flow.apple_tools.time.sleep") as sleep_mock:
                assert _run_script("x") is None
                assert run_mock.call_count == 8
                assert sleep_mock.call_count == 7


# ---------------------------------------------------------------------------
# AppleScript target resolution
# ---------------------------------------------------------------------------

class TestAppleScriptTargetResolution:
    def test_resolve_uses_bundle_id_before_name_fallback(self):
        with patch("apple_flow.apple_tools._probe_applescript_target", side_effect=[False, True]):
            result = at._resolve_applescript_app(("com.apple.A", "com.apple.B"), "App")
            assert result == 'application id "com.apple.B"'

    def test_resolve_can_use_name_fallback(self):
        with patch("apple_flow.apple_tools._probe_applescript_target", side_effect=[False, False, True]):
            result = at._resolve_applescript_app(("com.apple.A", "com.apple.B"), "App")
            assert result == 'application "App"'

    def test_resolve_candidates_returns_first_scriptable_target(self):
        with patch("apple_flow.apple_tools._probe_applescript_target", side_effect=[False, False, True]):
            result = at._resolve_applescript_target_candidates(
                (
                    'application id "com.apple.Numbers"',
                    'application id "com.apple.iWork.Numbers"',
                    'application "/Applications/Numbers Creator Studio.app"',
                ),
                fallback='application id "com.apple.Numbers"',
                app_label="Numbers",
            )
            assert result == 'application "/Applications/Numbers Creator Studio.app"'

    def test_numbers_target_tries_creator_studio_candidates(self):
        with patch("apple_flow.apple_tools._probe_applescript_target", side_effect=[False, False, True]):
            result = at._numbers_app_target()
            assert result == 'application "/Applications/Numbers Creator Studio.app"'

    def test_pages_target_tries_creator_studio_candidates(self):
        with patch("apple_flow.apple_tools._probe_applescript_target", side_effect=[False, False, True]):
            result = at._pages_app_target()
            assert result == 'application "/Applications/Pages Creator Studio.app"'

    def test_warm_pages_app_uses_first_available_target(self):
        first_fail = _err_result("missing")
        second_ok = _ok_result("")
        with patch("subprocess.run", side_effect=[first_fail, second_ok]) as run_mock:
            with patch("apple_flow.apple_tools.time.sleep") as sleep_mock:
                assert at._warm_pages_app() is True
                assert run_mock.call_count == 2
                sleep_mock.assert_called_once()


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
        for category in ("NOTES", "PAGES", "NUMBERS", "MAIL", "REMINDERS", "CALENDAR", "MESSAGES", "PHONE"):
            assert category in TOOLS_CONTEXT, f"TOOLS_CONTEXT missing category: {category}"

    def test_mentions_apple_flow_tools(self):
        assert "apple-flow tools" in TOOLS_CONTEXT


# ---------------------------------------------------------------------------
# Phone / TTS
# ---------------------------------------------------------------------------

class TestPhoneCall:
    def test_phone_call_success(self):
        with patch("subprocess.run", return_value=_ok_result("")):
            result = phone_call("+15551234567")
        assert result["ok"] is True
        assert result["uri"].startswith("tel:")

    def test_phone_call_fallbacks_to_facetime_audio(self):
        with patch("subprocess.run", side_effect=[_err_result("no tel"), _ok_result("")]):
            result = phone_call("+15551234567", app="phone")
        assert result["ok"] is True
        assert result["uri"].startswith("facetime-audio://")
        assert result["fallback_used"] is True

    def test_phone_call_rejects_invalid_number(self):
        result = phone_call("bad-number")
        assert result["ok"] is False


class TestPhoneTts:
    def test_phone_tts_say_success(self):
        with patch("subprocess.run", return_value=_ok_result("")):
            result = phone_tts_say("hello there", voice="Samantha", rate=170)
        assert result["ok"] is True

    def test_phone_tts_say_requires_text(self):
        result = phone_tts_say("")
        assert result["ok"] is False

    def test_phone_tts_in_call_waits_then_speaks(self):
        with patch("apple_flow.apple_tools.time.sleep") as sleep_mock:
            with patch("subprocess.run", return_value=_ok_result("")):
                result = phone_tts_in_call("hello", delay_seconds=2.0)
        assert result["ok"] is True
        sleep_mock.assert_called_once_with(2.0)

    def test_phone_tts_in_call_deterministic_routes_audio(self):
        with patch(
            "apple_flow.apple_tools._synthesize_tts_to_audio_file",
            return_value={"ok": True, "engine": "say", "path": "/tmp/fake.aiff"},
        ):
            with patch(
                "apple_flow.apple_tools._route_audio_file_to_call_input",
                return_value={"ok": True, "virtual_input_device": "BlackHole 2ch", "virtual_output_device": "BlackHole 2ch"},
            ) as route_mock:
                result = phone_tts_in_call(
                    "hello from deterministic path",
                    deterministic_audio=True,
                    virtual_audio_input_device="BlackHole 2ch",
                    virtual_audio_output_device="BlackHole 2ch",
                )
        assert result["ok"] is True
        assert result["deterministic_audio"] is True
        assert result["tts_engine"] == "say"
        route_mock.assert_called_once()

    def test_phone_tts_in_call_deterministic_hard_fails_on_route_error(self):
        with patch(
            "apple_flow.apple_tools._synthesize_tts_to_audio_file",
            return_value={"ok": True, "engine": "piper", "path": "/tmp/fake.wav"},
        ):
            with patch(
                "apple_flow.apple_tools._route_audio_file_to_call_input",
                return_value={"ok": False, "error": "virtual input device not found"},
            ):
                result = phone_tts_in_call(
                    "hello from deterministic path",
                    deterministic_audio=True,
                    virtual_audio_input_device="BlackHole 2ch",
                    virtual_audio_output_device="BlackHole 2ch",
                )
        assert result["ok"] is False
        assert "virtual input device" in result["error"]


class TestPhoneCallMe:
    def test_phone_call_me_runs_all_steps(self):
        with patch("apple_flow.apple_tools.phone_tts_say", return_value={"ok": True}) as pre_mock:
            with patch("apple_flow.apple_tools.phone_call", return_value={"ok": True, "uri": "tel:+1555", "app": "phone"}):
                with patch("apple_flow.apple_tools.phone_tts_in_call", return_value={"ok": True}) as in_call_mock:
                    result = phone_call_me(
                        owner_number="+15551234567",
                        preflight_text="Starting call now.",
                        in_call_text="Hi from Apple Flow",
                    )
        assert result["ok"] is True
        pre_mock.assert_called_once()
        in_call_mock.assert_called_once()

    def test_phone_call_me_fails_when_deterministic_in_call_audio_fails(self):
        with patch("apple_flow.apple_tools.phone_call", return_value={"ok": True, "uri": "tel:+1555", "app": "phone"}):
            with patch(
                "apple_flow.apple_tools.phone_tts_in_call",
                return_value={"ok": False, "error": "virtual input device not found"},
            ):
                result = phone_call_me(
                    owner_number="+15551234567",
                    in_call_text="Hello from Apple Flow",
                    deterministic_audio=True,
                )
        assert result["ok"] is False
        assert "virtual input device not found" in result["error"]


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
# Apple Pages
# ---------------------------------------------------------------------------

class TestPagesCreate:
    def test_returns_path_on_success(self, tmp_path):
        path = tmp_path / "doc.pages"
        with patch("subprocess.run", return_value=_ok_result(str(path))):
            result = pages_create(str(path), "Title", "Body")
            assert result == str(path)

    def test_requires_absolute_path(self):
        with patch("subprocess.run", return_value=_ok_result("/tmp/x.pages")):
            assert pages_create("relative.pages", "T", "B") is None

    def test_requires_pages_extension(self):
        with patch("subprocess.run", return_value=_ok_result("/tmp/x.txt")):
            assert pages_create("/tmp/x.txt", "T", "B") is None

    def test_respects_overwrite_false(self, tmp_path):
        path = tmp_path / "exists.pages"
        path.write_text("x", encoding="utf-8")
        with patch("subprocess.run", return_value=_ok_result(str(path))):
            assert pages_create(str(path), "T", "B", overwrite=False) is None


class TestPagesAppend:
    def test_returns_true_on_ok(self, tmp_path):
        path = tmp_path / "doc.pages"
        path.write_text("x", encoding="utf-8")
        with patch("subprocess.run", return_value=_ok_result("ok")):
            assert pages_append(str(path), "hello") is True

    def test_requires_existing_target(self):
        with patch("subprocess.run", return_value=_ok_result("ok")):
            assert pages_append("/tmp/does-not-exist.pages", "hello") is False

    def test_requires_pages_extension(self, tmp_path):
        path = tmp_path / "doc.txt"
        path.write_text("x", encoding="utf-8")
        with patch("subprocess.run", return_value=_ok_result("ok")):
            assert pages_append(str(path), "hello") is False


class TestPagesFromMarkdown:
    def test_requires_existing_input_file(self, tmp_path):
        missing = tmp_path / "missing.md"
        result = pages_from_markdown(str(missing))
        assert result["ok"] is False
        assert "input file not found" in result["error"]

    def test_default_output_path_and_success(self, tmp_path):
        source = tmp_path / "proposal.md"
        source.write_text("# Title\n\nHello **world**", encoding="utf-8")
        (tmp_path / "proposal.pages").write_text("existing", encoding="utf-8")

        with patch("subprocess.run", return_value=_ok_result("")) as run_mock:
            with patch("apple_flow.apple_tools._warm_pages_app", return_value=True):
                with patch("apple_flow.apple_tools._pages_app_target", return_value='application id "com.apple.Pages"'):
                    with patch("apple_flow.apple_tools._run_script", return_value="ok"):
                        result = pages_from_markdown(str(source), overwrite=True)

        assert result["ok"] is True
        assert result["output_path"].endswith("proposal.pages")
        assert result["stats"]["headings"] == 1
        assert result["stats"]["paragraphs"] == 1
        assert run_mock.call_count >= 1

    def test_respects_overwrite_false(self, tmp_path):
        source = tmp_path / "doc.md"
        source.write_text("hello", encoding="utf-8")
        output = tmp_path / "doc.pages"
        output.write_text("existing", encoding="utf-8")

        result = pages_from_markdown(str(source), output_path=str(output), overwrite=False)
        assert result["ok"] is False
        assert "overwrite=false" in result["error"]

    def test_returns_error_when_textutil_fails(self, tmp_path):
        source = tmp_path / "doc.md"
        source.write_text("# X", encoding="utf-8")

        with patch("subprocess.run", return_value=_err_result("textutil failed")):
            with patch("apple_flow.apple_tools._warm_pages_app", return_value=True):
                with patch("apple_flow.apple_tools._run_script", return_value="ok"):
                    result = pages_from_markdown(str(source), overwrite=True)

        assert result["ok"] is False
        assert "textutil failed" in result["error"]

    def test_includes_table_stats(self, tmp_path):
        source = tmp_path / "table.md"
        source.write_text(
            "| Plan | Price |\n| --- | --- |\n| Core | $100 |\n",
            encoding="utf-8",
        )
        (tmp_path / "table.pages").write_text("existing", encoding="utf-8")

        with patch("subprocess.run", return_value=_ok_result("")):
            with patch("apple_flow.apple_tools._warm_pages_app", return_value=True):
                with patch("apple_flow.apple_tools._pages_app_target", return_value='application id "com.apple.Pages"'):
                    with patch("apple_flow.apple_tools._run_script", return_value="ok"):
                        result = pages_from_markdown(str(source), overwrite=True)

        assert result["ok"] is True
        assert result["stats"]["table_count"] == 1

    def test_accepts_stdin_input(self, tmp_path):
        output = tmp_path / "stdin.pages"
        output.write_text("existing", encoding="utf-8")
        md = io.StringIO("# Live Report\n\n- point one\n- point two\n")

        with patch("sys.stdin", md):
            with patch("subprocess.run", return_value=_ok_result("")):
                with patch("apple_flow.apple_tools._warm_pages_app", return_value=True):
                    with patch("apple_flow.apple_tools._pages_app_target", return_value='application id "com.apple.Pages"'):
                        with patch("apple_flow.apple_tools._run_script", return_value="ok"):
                            result = pages_from_markdown("-", output_path=str(output), overwrite=True)

        assert result["ok"] is True
        assert result["input_path"] == "<stdin>"
        assert result["output_path"] == str(output)

    def test_rejects_empty_stdin(self):
        with patch("sys.stdin", io.StringIO("")):
            result = pages_from_markdown("-", output_path="/tmp/empty.pages", overwrite=True)
        assert result["ok"] is False
        assert "stdin markdown input is empty" in result["error"]

    def test_supports_theme_export_and_qa(self, tmp_path):
        source = tmp_path / "research.md"
        source.write_text(
            "# AI Agents\n\nSee [Paper](https://example.com/paper).\n",
            encoding="utf-8",
        )
        output = tmp_path / "research.pages"
        output.write_text("existing", encoding="utf-8")

        with patch("subprocess.run", return_value=_ok_result("")):
            with patch("apple_flow.apple_tools._warm_pages_app", return_value=True):
                with patch("apple_flow.apple_tools._pages_app_target", return_value='application id "com.apple.Pages"'):
                    with patch("apple_flow.apple_tools._run_script", return_value="ok"):
                        result = pages_from_markdown(
                            str(source),
                            output_path=str(output),
                            theme="corporate",
                            toc="on",
                            citations="on",
                            images="off",
                            qa=True,
                            export="pdf",
                            overwrite=True,
                        )

        assert result["ok"] is True
        assert result["theme"] == "corporate"
        assert result["options"]["toc"] is True
        assert "qa_report" in result
        assert result["qa_report"]["word_count"] > 0
        assert result["exports"]["pdf"].endswith(".pdf")

    def test_toc_uses_native_pages_insertion(self, tmp_path):
        source = tmp_path / "guide.md"
        source.write_text(
            "# Title\n\n## One\n\nBody.\n\n## Two\n\nMore.\n\n## Three\n\nMore.\n\n## Four\n\nMore.\n\n## Five\n\nMore.\n\n## Six\n\nMore.\n",
            encoding="utf-8",
        )
        output = tmp_path / "guide.pages"
        output.write_text("existing", encoding="utf-8")

        with patch("subprocess.run", return_value=_ok_result("")):
            with patch("apple_flow.apple_tools._warm_pages_app", return_value=True):
                with patch("apple_flow.apple_tools._pages_app_target", return_value='application id "com.apple.Pages"'):
                    with patch("apple_flow.apple_tools._run_script", return_value="ok"):
                        with patch("apple_flow.apple_tools._insert_native_pages_toc", return_value=True) as toc_mock:
                            result = pages_from_markdown(
                                str(source),
                                output_path=str(output),
                                toc="on",
                                overwrite=True,
                            )

        assert result["ok"] is True
        assert result["options"]["toc"] is True
        assert result["options"]["toc_native_inserted"] is True
        toc_mock.assert_called_once()

    def test_page_break_marker_updates_stats(self, tmp_path):
        source = tmp_path / "breaks.md"
        source.write_text("# One\n\n[[PB]]\n\n# Two\n", encoding="utf-8")
        output = tmp_path / "breaks.pages"
        output.write_text("existing", encoding="utf-8")

        with patch("subprocess.run", return_value=_ok_result("")):
            with patch("apple_flow.apple_tools._warm_pages_app", return_value=True):
                with patch("apple_flow.apple_tools._pages_app_target", return_value='application id "com.apple.Pages"'):
                    with patch("apple_flow.apple_tools._run_script", return_value="ok"):
                        result = pages_from_markdown(
                            str(source),
                            output_path=str(output),
                            page_break_marker="[[PB]]",
                            overwrite=True,
                        )

        assert result["ok"] is True
        assert result["stats"]["page_breaks"] >= 1


class TestPagesUpdateSections:
    def test_merges_requested_sections_and_renders(self, tmp_path):
        base = tmp_path / "base.md"
        base.write_text(
            "# Overview\n\nOld intro.\n\n## Scope\n\nOld scope.\n\n## Timeline\n\nOld timeline.\n",
            encoding="utf-8",
        )
        updates = tmp_path / "updates.md"
        updates.write_text(
            "## Scope\n\nNew scope details.\n\n## Risks\n\nNew risk note.\n",
            encoding="utf-8",
        )
        output = tmp_path / "merged.pages"
        output.write_text("existing", encoding="utf-8")

        with patch("subprocess.run", return_value=_ok_result("")):
            with patch("apple_flow.apple_tools._warm_pages_app", return_value=True):
                with patch("apple_flow.apple_tools._pages_app_target", return_value='application id "com.apple.Pages"'):
                    with patch("apple_flow.apple_tools._run_script", return_value="ok"):
                        result = pages_update_sections(
                            str(base),
                            str(updates),
                            str(output),
                            sections="Scope,Risks",
                            overwrite=True,
                        )

        assert result["ok"] is True
        assert result["merge"]["applied_sections"] == ["Scope"]
        assert result["merge"]["appended_sections"] == ["Risks"]

    def test_rewrites_relative_images_from_base_and_updates(self, tmp_path):
        base_dir = tmp_path / "base"
        updates_dir = tmp_path / "updates"
        (base_dir / "images").mkdir(parents=True)
        (updates_dir / "assets").mkdir(parents=True)
        (base_dir / "images" / "base.png").write_bytes(b"base")
        (updates_dir / "assets" / "update.png").write_bytes(b"update")

        base = base_dir / "base.md"
        base.write_text(
            "# Overview\n\n![base](images/base.png)\n",
            encoding="utf-8",
        )
        updates = updates_dir / "updates.md"
        updates.write_text(
            "## Addendum\n\n![update](assets/update.png)\n",
            encoding="utf-8",
        )
        output = tmp_path / "merged.pages"

        captured: dict[str, str] = {}

        def _fake_render(markdown_text, **kwargs):
            captured["markdown"] = markdown_text
            return {"ok": True, "warnings": []}

        with patch("apple_flow.apple_tools._render_pages_markdown", side_effect=_fake_render):
            result = pages_update_sections(
                str(base),
                str(updates),
                str(output),
                overwrite=True,
            )

        assert result["ok"] is True
        assert str((base_dir / "images" / "base.png").resolve()) in captured["markdown"]
        assert str((updates_dir / "assets" / "update.png").resolve()) in captured["markdown"]


class TestPagesTemplate:
    def test_creates_research_template(self, tmp_path):
        output = tmp_path / "research-template.md"
        result = pages_template("research", str(output))
        assert result["ok"] is True
        assert output.exists()
        assert "# Executive Summary" in output.read_text(encoding="utf-8")

    def test_rejects_unknown_template(self):
        result = pages_template("unknown-template")
        assert result["ok"] is False
        assert "unsupported template type" in result["error"]


# ---------------------------------------------------------------------------
# Apple Numbers
# ---------------------------------------------------------------------------

class TestNumbersCreate:
    def test_returns_path_on_success(self, tmp_path):
        path = tmp_path / "sheet.numbers"
        with patch("subprocess.run", return_value=_ok_result(str(path))):
            result = numbers_create(str(path), headers=["Name", "Score"])
            assert result == str(path)

    def test_requires_headers(self, tmp_path):
        path = tmp_path / "sheet.numbers"
        with patch("subprocess.run", return_value=_ok_result(str(path))):
            assert numbers_create(str(path), headers=[]) is None

    def test_requires_numbers_extension(self):
        with patch("subprocess.run", return_value=_ok_result("/tmp/x.txt")):
            assert numbers_create("/tmp/x.txt", headers=["A"]) is None

    def test_expands_columns_for_wide_headers(self, tmp_path):
        path = tmp_path / "sheet.numbers"
        captured: dict[str, str] = {}

        def _capture(*args, **kwargs):
            cmd = args[0]
            captured["script"] = cmd[2]
            return _ok_result(str(path))

        with patch("subprocess.run", side_effect=_capture):
            result = numbers_create(str(path), headers=[f"H{i}" for i in range(1, 11)])

        assert result == str(path)
        script = captured.get("script", "")
        assert "set requiredCols to 10" in script
        assert "make new column at end of columns" in script


class TestNumbersAppendRows:
    def test_returns_structured_success(self, tmp_path):
        path = tmp_path / "sheet.numbers"
        path.write_text("x", encoding="utf-8")
        with patch("subprocess.run", return_value=_ok_result("ok|2|1")):
            result = numbers_append_rows(str(path), [["a", 1], ["b", 2]])
            assert result["ok"] is True
            assert result["inserted_rows"] == 2
            assert result["start_row"] == 2

    def test_after_headers_uses_insert_before_anchor_logic(self, tmp_path):
        path = tmp_path / "sheet.numbers"
        path.write_text("x", encoding="utf-8")
        captured: dict[str, str] = {}

        def _capture(*args, **kwargs):
            cmd = args[0]
            captured["script"] = cmd[2]
            return _ok_result("ok|2|2")

        with patch("subprocess.run", side_effect=_capture):
            result = numbers_append_rows(str(path), [["new", 5]], insert_position="after-headers")

        assert result["ok"] is True
        assert result["insert_position"] == "after-headers"
        assert result["start_row"] == 2
        script = captured.get("script", "")
        assert 'if "after-headers" is "after-headers" then' in script
        assert "set anchorRow to row insertionRow" in script
        assert "set targetRow to make new row at before anchorRow" in script

    def test_after_data_uses_last_data_scan_and_reuses_existing_blank_rows(self, tmp_path):
        path = tmp_path / "sheet.numbers"
        path.write_text("x", encoding="utf-8")
        captured: dict[str, str] = {}

        def _capture(*args, **kwargs):
            cmd = args[0]
            captured["script"] = cmd[2]
            return _ok_result("ok|3|4")

        with patch("subprocess.run", side_effect=_capture):
            result = numbers_append_rows(str(path), [["coffee", 15], ["burger", 30]], insert_position="after-data")

        assert result["ok"] is True
        assert result["start_row"] == 3
        assert result["insert_after_row"] == 4
        script = captured.get("script", "")
        assert "repeat with r from dataStartRow to totalRows" in script
        assert "set cellVal to value of cell c of row r" in script
        assert "set targetRow to row insertionRow" in script

    def test_at_end_always_appends_new_rows(self, tmp_path):
        path = tmp_path / "sheet.numbers"
        path.write_text("x", encoding="utf-8")
        captured: dict[str, str] = {}

        def _capture(*args, **kwargs):
            cmd = args[0]
            captured["script"] = cmd[2]
            return _ok_result("ok|10|11")

        with patch("subprocess.run", side_effect=_capture):
            result = numbers_append_rows(str(path), [["x"], ["y"]], insert_position="at-end")

        assert result["ok"] is True
        assert result["start_row"] == 10
        assert result["insert_after_row"] == 11
        assert result["inserted_rows"] == 2
        script = captured.get("script", "")
        assert 'else if "at-end" is "at-end" then' in script
        assert "set insertionRow to totalRows + 1" in script
        assert "set targetRow to make new row at end of rows" in script

    def test_requires_existing_file(self):
        result = numbers_append_rows("/tmp/missing.numbers", [["x"]])
        assert result["ok"] is False

    def test_rejects_invalid_insert_position(self, tmp_path):
        path = tmp_path / "sheet.numbers"
        path.write_text("x", encoding="utf-8")
        result = numbers_append_rows(str(path), [["x"]], insert_position="middle")
        assert result["ok"] is False

    def test_expands_columns_for_wide_rows(self, tmp_path):
        path = tmp_path / "sheet.numbers"
        path.write_text("x", encoding="utf-8")
        captured: dict[str, str] = {}

        def _capture(*args, **kwargs):
            cmd = args[0]
            captured["script"] = cmd[2]
            return _ok_result("ok|2|2")

        with patch("subprocess.run", side_effect=_capture):
            result = numbers_append_rows(str(path), [[1, 2, 3, 4, 5, 6, 7, 8, 9]])

        assert result["ok"] is True
        script = captured.get("script", "")
        assert "set requiredCols to 9" in script
        assert "make new column at end of columns" in script


class TestNumbersWorkbook:
    def test_add_sheet_returns_structured_success(self, tmp_path):
        path = tmp_path / "book.numbers"
        path.write_text("x", encoding="utf-8")
        with patch("subprocess.run", return_value=_ok_result("ok|2")):
            result = numbers_add_sheet(
                str(path),
                {
                    "sheet_name": "Summary",
                    "table_name": "SummaryTable",
                    "headers": ["Metric", "Value"],
                    "rows": [["Total", 45], ["Count", 2]],
                },
            )
        assert result["ok"] is True
        assert result["sheet_name"] == "Summary"
        assert result["rows_inserted"] == 2

    def test_add_sheet_prefers_row_2_before_appending(self, tmp_path):
        path = tmp_path / "book.numbers"
        path.write_text("x", encoding="utf-8")
        captured: dict[str, str] = {}

        def _capture(*args, **kwargs):
            cmd = args[0]
            captured["script"] = cmd[2]
            return _ok_result("ok|1")

        with patch("subprocess.run", side_effect=_capture):
            result = numbers_add_sheet(
                str(path),
                {
                    "sheet_name": "Summary",
                    "table_name": "SummaryTable",
                    "headers": ["Metric", "Value"],
                    "rows": [["Total", 45]],
                },
            )

        assert result["ok"] is True
        script = captured.get("script", "")
        assert "set insertionRow to 2" in script
        assert "if insertionRow <= totalRows then" in script
        assert "set targetRow to row insertionRow" in script
        assert "set insertionRow to insertionRow + 1" in script

    def test_add_sheet_rejects_bad_spec(self, tmp_path):
        path = tmp_path / "book.numbers"
        path.write_text("x", encoding="utf-8")
        result = numbers_add_sheet(str(path), {"sheet_name": "", "headers": []})
        assert result["ok"] is False
        assert "sheet_name" in result["error"] or "headers" in result["error"]

    def test_create_workbook_uses_create_and_add_sheet(self, tmp_path):
        path = tmp_path / "book.numbers"
        with patch("apple_flow.apple_tools.numbers_create", return_value=str(path)) as create_mock:
            with patch("apple_flow.apple_tools.numbers_append_rows", return_value={"ok": True, "inserted_rows": 1}) as append_mock:
                with patch("apple_flow.apple_tools.numbers_add_sheet", return_value={"ok": True, "rows_inserted": 2}) as add_mock:
                    result = numbers_create_workbook(
                        str(path),
                        {
                            "sheets": [
                                {
                                    "sheet_name": "Transactions",
                                    "table_name": "Tx",
                                    "headers": ["Date", "Item", "Amount"],
                                    "rows": [["2026-03-04", "Coffee", 15]],
                                },
                                {
                                    "sheet_name": "Summary",
                                    "table_name": "Summary",
                                    "headers": ["Metric", "Value"],
                                    "rows": [["Total", 15], ["Count", 1]],
                                },
                            ]
                        },
                        overwrite=True,
                    )

        assert result["ok"] is True
        assert result["sheets_created"] == 2
        assert result["rows_inserted_total"] == 3
        create_mock.assert_called_once()
        append_mock.assert_called_once()
        add_mock.assert_called_once()

    def test_create_workbook_rejects_duplicate_sheet_names(self, tmp_path):
        path = tmp_path / "book.numbers"
        result = numbers_create_workbook(
            str(path),
            {
                "sheets": [
                    {"sheet_name": "Summary", "headers": ["A"]},
                    {"sheet_name": "summary", "headers": ["B"]},
                ]
            },
        )
        assert result["ok"] is False
        assert "duplicate sheet_name" in result["error"]


class TestNumbersStyleApply:
    def test_requires_existing_file(self):
        result = numbers_style_apply(
            "/tmp/missing.numbers",
            target={"scope": "table"},
            style={"font_size": 12},
        )
        assert result["ok"] is False

    def test_rejects_invalid_target_scope(self, tmp_path):
        path = tmp_path / "sheet.numbers"
        path.write_text("x", encoding="utf-8")
        result = numbers_style_apply(
            str(path),
            target={"scope": "grid"},
            style={"font_size": 12},
        )
        assert result["ok"] is False
        assert "target_json.scope" in result["error"]

    def test_rejects_unknown_style_key(self, tmp_path):
        path = tmp_path / "sheet.numbers"
        path.write_text("x", encoding="utf-8")
        result = numbers_style_apply(
            str(path),
            target={"scope": "table"},
            style={"theme": "sunset"},
        )
        assert result["ok"] is False
        assert "unsupported style key" in result["error"]

    def test_rejects_column_width_for_row_scope(self, tmp_path):
        path = tmp_path / "sheet.numbers"
        path.write_text("x", encoding="utf-8")
        result = numbers_style_apply(
            str(path),
            target={"scope": "row", "index": 2},
            style={"column_width": 140},
        )
        assert result["ok"] is False
        assert "column_width is not supported for row target scope" in result["error"]

    def test_normalizes_8bit_rgb_to_16bit_in_script(self, tmp_path):
        path = tmp_path / "sheet.numbers"
        path.write_text("x", encoding="utf-8")
        captured: dict[str, str] = {}

        def _capture(*args, **kwargs):
            cmd = args[0]
            captured["script"] = cmd[2]
            return _ok_result("ok|1|0|0")

        with patch("subprocess.run", side_effect=_capture):
            result = numbers_style_apply(
                str(path),
                target={"scope": "cell", "row": 2, "column": 1},
                style={"background_color": [255, 0, 128]},
            )

        assert result["ok"] is True
        script = captured.get("script", "")
        assert "set background color of cellRef to {65535, 0, 32896}" in script

    def test_range_scope_builds_expected_loop_and_counts(self, tmp_path):
        path = tmp_path / "sheet.numbers"
        path.write_text("x", encoding="utf-8")
        captured: dict[str, str] = {}

        def _capture(*args, **kwargs):
            cmd = args[0]
            captured["script"] = cmd[2]
            return _ok_result("ok|6|3|2")

        with patch("subprocess.run", side_effect=_capture):
            result = numbers_style_apply(
                str(path),
                target={
                    "scope": "range",
                    "start_row": 2,
                    "end_row": 4,
                    "start_column": 1,
                    "end_column": 2,
                },
                style={
                    "text_color": [0, 0, 65535],
                    "font_size": 12,
                    "alignment": "center",
                    "row_height": 28,
                    "column_width": 120,
                    "text_wrap": True,
                    "number_format": "currency",
                },
            )

        assert result["ok"] is True
        assert result["cells_touched"] == 6
        assert result["rows_resized"] == 3
        assert result["columns_resized"] == 2
        script = captured.get("script", "")
        assert "set rangeRowCount to (4 - 2) + 1" in script
        assert "set rangeColCount to (2 - 1) + 1" in script
        assert "set text wrap of cellRef to true" in script
        assert "set format of cellRef to currency" in script


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


class TestMailListMailboxes:
    def test_returns_mailboxes_without_system_by_default(self):
        raw = "Action\tdavid@techtiff.ai\nINBOX\tdavid@techtiff.ai\nFocus\tdavid@techtiff.ai"
        with patch("subprocess.run", return_value=_ok_result(raw)):
            result = mail_list_mailboxes(account="david@techtiff.ai")
            assert isinstance(result, list)
            assert [row["mailbox"] for row in result] == ["Action", "Focus"]

    def test_parses_recursive_rows_with_path_and_mailbox_id(self):
        raw = (
            "Projects\tdavid@techtiff.ai\tProjects\tmb-1\n"
            "Focus\tdavid@techtiff.ai\tProjects/Focus\tmb-2\n"
            "INBOX\tdavid@techtiff.ai\tINBOX\tmb-3"
        )
        with patch("subprocess.run", return_value=_ok_result(raw)):
            result = mail_list_mailboxes(account="david@techtiff.ai")
            assert isinstance(result, list)
            assert len(result) == 2
            assert result[0]["mailbox"] == "Projects"
            assert result[1]["mailbox"] == "Focus"
            assert result[1]["path"] == "Projects/Focus"
            assert result[1]["mailbox_id"] == "mb-2"

    def test_include_system_true_keeps_system_mailboxes(self):
        raw = "Action\tdavid@techtiff.ai\nINBOX\tdavid@techtiff.ai"
        with patch("subprocess.run", return_value=_ok_result(raw)):
            result = mail_list_mailboxes(account="david@techtiff.ai", include_system=True)
            assert isinstance(result, list)
            assert [row["mailbox"] for row in result] == ["Action", "INBOX"]
            assert result[1]["is_system_mailbox"] is True

    def test_as_text_returns_string(self):
        raw = "Action\tdavid@techtiff.ai"
        with patch("subprocess.run", return_value=_ok_result(raw)):
            result = mail_list_mailboxes(account="david@techtiff.ai", as_text=True)
            assert isinstance(result, str)
            assert "Action" in result

    def test_returns_empty_on_failure(self):
        with patch("subprocess.run", return_value=_err_result()):
            assert mail_list_mailboxes() == []

    def test_returns_empty_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osascript", 30)):
            assert mail_list_mailboxes() == []

    def test_returns_empty_on_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert mail_list_mailboxes() == []


class TestMailMoveToLabel:
    def test_moves_message_with_exact_label(self):
        raw_mailboxes = "Action\tdavid@techtiff.ai\nFocus\tdavid@techtiff.ai\nINBOX\tdavid@techtiff.ai"
        with patch("subprocess.run", side_effect=[_ok_result(raw_mailboxes), _ok_result("ok_exclusive")]):
            result = mail_move_to_label(["123"], label="Focus", account="david@techtiff.ai", source_mailbox="INBOX")
            assert result["attempted"] == 1
            assert result["moved"] == 1
            assert result["inbox_removed"] == 1
            assert result["destination_mailbox"] == "Focus"
            assert result["results"][0]["status"] == "moved"

    def test_resolves_alias_label(self):
        raw_mailboxes = "Action\tdavid@techtiff.ai\nFocus\tdavid@techtiff.ai"
        with patch("subprocess.run", side_effect=[_ok_result(raw_mailboxes), _ok_result("ok_exclusive")]):
            result = mail_move_to_label(["123"], label="focus", account="david@techtiff.ai")
            assert result["moved"] == 1
            assert result["destination_mailbox"] == "Focus"

    def test_resolves_unambiguous_partial_label(self):
        raw_mailboxes = "Focus\tdavid@techtiff.ai\nAction\tdavid@techtiff.ai"
        with patch("subprocess.run", side_effect=[_ok_result(raw_mailboxes), _ok_result("ok_exclusive")]):
            result = mail_move_to_label(["123"], label="foc", account="david@techtiff.ai")
            assert result["moved"] == 1
            assert result["destination_mailbox"] == "Focus"

    def test_resolves_label_using_mailbox_path(self):
        raw_mailboxes = "Focus\tdavid@techtiff.ai\tWork/Focus\tmb-42"
        with patch("subprocess.run", side_effect=[_ok_result(raw_mailboxes), _ok_result("ok_exclusive")]):
            result = mail_move_to_label(["123"], label="Work/Focus", account="david@techtiff.ai")
            assert result["moved"] == 1
            assert result["destination_mailbox"] == "Focus"
            assert result["destination_path"] == "Work/Focus"

    def test_reports_when_message_stays_in_source_after_move(self):
        raw_mailboxes = "Focus\tdavid@techtiff.ai\nINBOX\tdavid@techtiff.ai"
        with patch("subprocess.run", side_effect=[_ok_result(raw_mailboxes), _ok_result("ok_labeled")]):
            result = mail_move_to_label(["123"], label="focus", account="david@techtiff.ai")
            assert result["attempted"] == 1
            assert result["moved"] == 1
            assert result["inbox_removed"] == 0
            assert result["results"][0]["status"] == "moved_inbox_retained"

    def test_uses_numeric_id_selector_for_digits(self):
        raw_mailboxes = "Focus\tdavid@techtiff.ai\nINBOX\tdavid@techtiff.ai"
        captured_scripts: list[str] = []

        def fake_run(cmd, capture_output, text, timeout):
            script = cmd[2]
            captured_scripts.append(script)
            if len(captured_scripts) == 1:
                return _ok_result(raw_mailboxes)
            return _ok_result("ok_exclusive")

        with patch("subprocess.run", side_effect=fake_run):
            result = mail_move_to_label(["21702"], label="focus", account="david@techtiff.ai")

        assert result["moved"] == 1
        assert len(captured_scripts) >= 2
        assert "first message of sourceBox whose id is 21702" in captured_scripts[1]
        assert "whose id is 21702" in captured_scripts[1]
        assert 'whose id as text is "21702"' not in captured_scripts[1]

    def test_uses_text_id_selector_for_nonnumeric_ids(self):
        raw_mailboxes = "Focus\tdavid@techtiff.ai\nINBOX\tdavid@techtiff.ai"
        captured_scripts: list[str] = []

        def fake_run(cmd, capture_output, text, timeout):
            script = cmd[2]
            captured_scripts.append(script)
            if len(captured_scripts) == 1:
                return _ok_result(raw_mailboxes)
            return _ok_result("ok_exclusive")

        with patch("subprocess.run", side_effect=fake_run):
            result = mail_move_to_label(["msg-abc"], label="focus", account="david@techtiff.ai")

        assert result["moved"] == 1
        assert len(captured_scripts) >= 2
        assert 'first message of sourceBox whose id as text is "msg-abc"' in captured_scripts[1]
        assert 'whose id as text is "msg-abc"' in captured_scripts[1]

    def test_returns_error_for_ambiguous_label(self):
        raw_mailboxes = "Focus\tdavid@techtiff.ai\nFollow Ups\tdavid@techtiff.ai"
        with patch("subprocess.run", return_value=_ok_result(raw_mailboxes)):
            result = mail_move_to_label(["123"], label="fo", account="david@techtiff.ai")
            assert result["moved"] == 0
            assert result["failed"] == 1
            assert result["destination_mailbox"] is None
            assert "suggestions" in result

    def test_returns_error_for_no_match_with_suggestions(self):
        raw_mailboxes = "Action\tdavid@techtiff.ai\nFocus\tdavid@techtiff.ai\nNoise\tdavid@techtiff.ai"
        with patch("subprocess.run", return_value=_ok_result(raw_mailboxes)):
            result = mail_move_to_label(["123"], label="urgent", account="david@techtiff.ai")
            assert result["moved"] == 0
            assert result["failed"] == 1
            assert result["destination_mailbox"] is None
            assert "Action" in result.get("suggestions", [])

    def test_handles_missing_message(self):
        raw_mailboxes = "Focus\tdavid@techtiff.ai\nINBOX\tdavid@techtiff.ai"
        with patch("subprocess.run", side_effect=[_ok_result(raw_mailboxes), _ok_result("error: not found")]):
            result = mail_move_to_label(["missing-id"], label="focus", account="david@techtiff.ai")
            assert result["attempted"] == 1
            assert result["moved"] == 0
            assert result["failed"] == 1
            assert result["results"][0]["status"] == "failed"

    def test_handles_timeout_without_raising(self):
        raw_mailboxes = "Focus\tdavid@techtiff.ai\nINBOX\tdavid@techtiff.ai"
        with patch("subprocess.run", side_effect=[_ok_result(raw_mailboxes), subprocess.TimeoutExpired("osascript", 30)]):
            result = mail_move_to_label(["123"], label="focus", account="david@techtiff.ai")
            assert result["attempted"] == 1
            assert result["moved"] == 0
            assert result["failed"] == 1
            assert result["results"][0]["status"] == "failed"


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
