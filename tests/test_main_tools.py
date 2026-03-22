from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import apple_flow.__main__ as app_main


def _args(**kwargs):
    defaults = {
        "tool_args": [],
        "list_tools": False,
        "text": False,
        "limit": 20,
        "pretty": False,
        "folder": None,
        "account": None,
        "mailbox": None,
        "days": None,
        "list": None,
        "filter": None,
        "due": None,
        "cal": None,
        "calendar_name": None,
        "end": None,
        "include_system": None,
        "label": None,
        "sheet": None,
        "table": None,
        "position": None,
        "theme": None,
        "style": None,
        "title_page": None,
        "toc": None,
        "citations": None,
        "images": None,
        "image_max_width": None,
        "page_break_marker": None,
        "qa": None,
        "export": None,
        "sections": None,
        "overwrite": None,
        "message_ids": [],
        "input_file": None,
        "template_file": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_tools_mail_list_mailboxes_dispatches(monkeypatch, capsys):
    monkeypatch.setattr(
        app_main,
        "mail_list_mailboxes",
        lambda account, include_system, as_text: [{"mailbox": "Action", "account": account, "is_system_mailbox": False}],
    )

    app_main._run_tools_subcommand(
        _args(
            tool_args=["mail_list_mailboxes"],
            account="david@techtiff.ai",
            include_system="false",
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["mailbox"] == "Action"


def test_tools_mail_move_to_label_requires_label_and_ids(capsys):
    with pytest.raises(SystemExit) as exc:
        app_main._run_tools_subcommand(
            _args(tool_args=["mail_move_to_label"])
        )
    assert exc.value.code == 1
    assert "Usage: apple-flow tools mail_move_to_label" in capsys.readouterr().err


def test_tools_mail_move_to_label_dispatches(monkeypatch, capsys):
    monkeypatch.setattr(
        app_main,
        "mail_move_to_label",
        lambda message_ids, label, account, source_mailbox: {
            "attempted": len(message_ids),
            "moved": len(message_ids),
            "failed": 0,
            "destination_mailbox": "Focus",
            "results": [{"message_id": m, "status": "moved"} for m in message_ids],
        },
    )

    app_main._run_tools_subcommand(
        _args(
            tool_args=["mail_move_to_label"],
            account="david@techtiff.ai",
            mailbox="INBOX",
            label="focus",
            message_ids=["abc-123"],
        )
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["moved"] == 1
    assert payload["destination_mailbox"] == "Focus"


def test_tools_mail_move_to_label_accepts_input_file(monkeypatch, capsys, tmp_path: Path):
    input_file = tmp_path / "message_ids.json"
    input_file.write_text(
        json.dumps([{"message_id": "m-1"}, {"message_id": "m-2"}, "m-3"]),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        app_main,
        "mail_move_to_label",
        lambda message_ids, label, account, source_mailbox: {
            "attempted": len(message_ids),
            "moved": len(message_ids),
            "failed": 0,
            "destination_mailbox": "Action",
            "results": [{"message_id": m, "status": "moved"} for m in message_ids],
        },
    )

    app_main._run_tools_subcommand(
        _args(
            tool_args=["mail_move_to_label"],
            account="david@techtiff.ai",
            mailbox="INBOX",
            label="action",
            input_file=str(input_file),
        )
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["attempted"] == 3
    assert payload["moved"] == 3


def test_tools_pages_create_dispatches(monkeypatch, capsys):
    monkeypatch.setattr(
        app_main,
        "pages_create",
        lambda file_path, title, body, overwrite: file_path if overwrite else "no-overwrite",
    )

    app_main._run_tools_subcommand(
        _args(
            tool_args=["pages_create", "/tmp/test.pages", "Title", "Body"],
            overwrite="true",
        )
    )
    assert capsys.readouterr().out.strip('" \n') == "/tmp/test.pages"


def test_tools_pages_from_markdown_dispatches(monkeypatch, capsys):
    monkeypatch.setattr(
        app_main,
        "pages_from_markdown",
        lambda input_path, output_path, style, overwrite, **kwargs: {
            "ok": True,
            "input_path": input_path,
            "output_path": output_path or "/tmp/inferred.pages",
            "style": style,
            "theme": kwargs.get("theme"),
            "toc": kwargs.get("toc"),
            "overwrite": overwrite,
        },
    )

    app_main._run_tools_subcommand(
        _args(
            tool_args=["pages_from_markdown", "/tmp/source.md", "/tmp/out.pages"],
            style="neutral",
            theme="corporate",
            toc="on",
            export="pdf",
            overwrite="true",
        )
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["input_path"] == "/tmp/source.md"
    assert payload["output_path"] == "/tmp/out.pages"
    assert payload["style"] == "neutral"
    assert payload["theme"] == "corporate"
    assert payload["toc"] == "on"
    assert payload["overwrite"] is True


def test_tools_pages_from_markdown_requires_input(capsys):
    with pytest.raises(SystemExit) as exc:
        app_main._run_tools_subcommand(_args(tool_args=["pages_from_markdown"]))
    assert exc.value.code == 1
    assert "Usage: apple-flow tools pages_from_markdown" in capsys.readouterr().err


def test_tools_pages_update_sections_dispatches(monkeypatch, capsys):
    monkeypatch.setattr(
        app_main,
        "pages_update_sections",
        lambda base_input_path, updates_path, output_path, **kwargs: {
            "ok": True,
            "base": base_input_path,
            "updates": updates_path,
            "output": output_path,
            "sections": kwargs.get("sections"),
            "theme": kwargs.get("theme"),
        },
    )

    app_main._run_tools_subcommand(
        _args(
            tool_args=["pages_update_sections", "/tmp/base.md", "/tmp/updates.md", "/tmp/out.pages"],
            sections="Executive Summary,Recommendations",
            theme="proposal",
            overwrite="true",
        )
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["sections"] == "Executive Summary,Recommendations"
    assert payload["theme"] == "proposal"


def test_tools_pages_update_sections_requires_args(capsys):
    with pytest.raises(SystemExit) as exc:
        app_main._run_tools_subcommand(_args(tool_args=["pages_update_sections", "/tmp/base.md"]))
    assert exc.value.code == 1
    assert "Usage: apple-flow tools pages_update_sections" in capsys.readouterr().err


def test_tools_pages_template_dispatches(monkeypatch, capsys):
    monkeypatch.setattr(
        app_main,
        "pages_template",
        lambda template_type, output_path="", overwrite=False: {
            "ok": True,
            "template_type": template_type,
            "output_path": output_path or "/tmp/default-template.md",
            "overwrite": overwrite,
        },
    )

    app_main._run_tools_subcommand(
        _args(
            tool_args=["pages_template", "research", "/tmp/research-template.md"],
            overwrite="true",
        )
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["template_type"] == "research"
    assert payload["output_path"] == "/tmp/research-template.md"
    assert payload["overwrite"] is True


def test_tools_reminders_create_dispatches(monkeypatch, capsys):
    monkeypatch.setattr(
        app_main,
        "reminders_create",
        lambda name, list_name="Reminders", due_date="": {
            "ok": True,
            "name": name,
            "list_name": list_name,
            "due_date": due_date,
        },
    )

    app_main._run_tools_subcommand(
        _args(
            tool_args=["reminders_create", "Buy milk"],
            list="agent-task",
            due="2026-03-22",
        )
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "ok": True,
        "name": "Buy milk",
        "list_name": "agent-task",
        "due_date": "2026-03-22",
    }


def test_tools_reminders_complete_dispatches(monkeypatch, capsys):
    monkeypatch.setattr(app_main, "reminders_complete", lambda reminder_id, list_name: True)

    app_main._run_tools_subcommand(
        _args(
            tool_args=["reminders_complete", "rem-1"],
            list="agent-task",
        )
    )
    assert capsys.readouterr().out.strip() == "true"


def test_tools_numbers_create_requires_json_headers(capsys):
    with pytest.raises(SystemExit) as exc:
        app_main._run_tools_subcommand(
            _args(tool_args=["numbers_create", "/tmp/test.numbers", "not-json"])
        )
    assert exc.value.code == 1
    assert "JSON array of headers" in capsys.readouterr().err


def test_tools_numbers_create_workbook_dispatches(monkeypatch, capsys):
    monkeypatch.setattr(
        app_main,
        "numbers_create_workbook",
        lambda file_path, workbook_spec, overwrite: {
            "ok": True,
            "path": file_path,
            "workbook": workbook_spec,
            "overwrite": overwrite,
        },
    )

    app_main._run_tools_subcommand(
        _args(
            tool_args=[
                "numbers_create_workbook",
                "/tmp/test.numbers",
                '{"sheets":[{"sheet_name":"Transactions","headers":["Date","Item","Amount"]}]}',
            ],
            overwrite="true",
        )
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["workbook"]["sheets"][0]["sheet_name"] == "Transactions"
    assert payload["overwrite"] is True


def test_tools_numbers_create_workbook_requires_object(capsys):
    with pytest.raises(SystemExit) as exc:
        app_main._run_tools_subcommand(
            _args(
                tool_args=[
                    "numbers_create_workbook",
                    "/tmp/test.numbers",
                    "[]",
                ]
            )
        )
    assert exc.value.code == 1
    assert "workbook_json to be a JSON object" in capsys.readouterr().err


def test_tools_numbers_add_sheet_dispatches(monkeypatch, capsys):
    monkeypatch.setattr(
        app_main,
        "numbers_add_sheet",
        lambda file_path, sheet_spec: {"ok": True, "path": file_path, "sheet": sheet_spec},
    )

    app_main._run_tools_subcommand(
        _args(
            tool_args=[
                "numbers_add_sheet",
                "/tmp/test.numbers",
                '{"sheet_name":"Summary","headers":["Metric","Value"]}',
            ]
        )
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["sheet"]["sheet_name"] == "Summary"


def test_tools_numbers_add_sheet_requires_object(capsys):
    with pytest.raises(SystemExit) as exc:
        app_main._run_tools_subcommand(
            _args(
                tool_args=[
                    "numbers_add_sheet",
                    "/tmp/test.numbers",
                    "[]",
                ]
            )
        )
    assert exc.value.code == 1
    assert "sheet_json to be a JSON object" in capsys.readouterr().err


def test_tools_numbers_append_rows_dispatches(monkeypatch, capsys):
    monkeypatch.setattr(
        app_main,
        "numbers_append_rows",
        lambda file_path, rows, sheet_name, table_name, insert_position: {
            "ok": True,
            "path": file_path,
            "rows": rows,
            "sheet": sheet_name,
            "table": table_name,
            "position": insert_position,
        },
    )

    app_main._run_tools_subcommand(
        _args(
            tool_args=["numbers_append_rows", "/tmp/test.numbers", '[["a",1],["b",2]]'],
            sheet="Sheet 1",
            table="Table 1",
            position="after-data",
        )
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["rows"] == [["a", 1], ["b", 2]]
    assert payload["position"] == "after-data"


def test_tools_numbers_append_rows_defaults_position_to_after_data(monkeypatch, capsys):
    captured: dict[str, str] = {}

    def _fake_numbers_append_rows(file_path, rows, sheet_name, table_name, insert_position):
        captured["position"] = insert_position
        return {"ok": True, "position": insert_position}

    monkeypatch.setattr(app_main, "numbers_append_rows", _fake_numbers_append_rows)

    app_main._run_tools_subcommand(
        _args(
            tool_args=["numbers_append_rows", "/tmp/test.numbers", '[["coffee",15]]'],
            sheet="Sheet 1",
            table="Table 1",
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["position"] == "after-data"
    assert captured["position"] == "after-data"


@pytest.mark.parametrize("position", ["after-headers", "at-end"])
def test_tools_numbers_append_rows_passes_position_variants(monkeypatch, capsys, position):
    monkeypatch.setattr(
        app_main,
        "numbers_append_rows",
        lambda file_path, rows, sheet_name, table_name, insert_position: {
            "ok": True,
            "position": insert_position,
        },
    )

    app_main._run_tools_subcommand(
        _args(
            tool_args=["numbers_append_rows", "/tmp/test.numbers", '[["a",1]]'],
            sheet="Sheet 1",
            table="Table 1",
            position=position,
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["position"] == position


def test_tools_numbers_style_apply_dispatches(monkeypatch, capsys):
    monkeypatch.setattr(
        app_main,
        "numbers_style_apply",
        lambda file_path, target, style, sheet_name, table_name: {
            "ok": True,
            "path": file_path,
            "target": target,
            "style": style,
            "sheet": sheet_name,
            "table": table_name,
        },
    )

    app_main._run_tools_subcommand(
        _args(
            tool_args=[
                "numbers_style_apply",
                "/tmp/test.numbers",
                '{"scope":"range","start_row":2,"end_row":4,"start_column":1,"end_column":3}',
                '{"font_size":12,"alignment":"center"}',
            ],
            sheet="Sheet 1",
            table="Table 1",
        )
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["target"]["scope"] == "range"
    assert payload["style"]["font_size"] == 12


def test_tools_numbers_style_apply_requires_json_objects(capsys):
    with pytest.raises(SystemExit) as exc:
        app_main._run_tools_subcommand(
            _args(
                tool_args=[
                    "numbers_style_apply",
                    "/tmp/test.numbers",
                    "[]",
                    '{"font_size":12}',
                ]
            )
        )
    assert exc.value.code == 1
    assert "target_json to be a JSON object" in capsys.readouterr().err


def test_tools_numbers_style_apply_invalid_style_json(capsys):
    with pytest.raises(SystemExit) as exc:
        app_main._run_tools_subcommand(
            _args(
                tool_args=[
                    "numbers_style_apply",
                    "/tmp/test.numbers",
                    '{"scope":"table"}',
                    "{not-json}",
                ]
            )
        )
    assert exc.value.code == 1
    assert "Invalid style_json" in capsys.readouterr().err
