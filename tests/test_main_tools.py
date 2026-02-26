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
        "message_ids": [],
        "input_file": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_tools_mail_list_mailboxes_dispatches(monkeypatch, capsys):
    monkeypatch.setattr(
        app_main,
        "mail_list_mailboxes",
        lambda account, include_system, as_text: [
            {"mailbox": "Action", "account": account, "is_system_mailbox": False}
        ],
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
        app_main._run_tools_subcommand(_args(tool_args=["mail_move_to_label"]))
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
