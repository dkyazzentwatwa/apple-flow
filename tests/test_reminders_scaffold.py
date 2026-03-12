from __future__ import annotations

import contextlib
import json

from apple_flow import reminders_scaffold


def test_resolve_template_returns_builtin_dev_template():
    template = reminders_scaffold.resolve_template("dev")

    assert template is not None
    assert template["lists"][0]["name"] == "dev-backlog"
    assert "issue-ready" in template["lists"][0]["sections"]


def test_resolve_template_returns_builtin_client_prefixed_lists():
    template = reminders_scaffold.resolve_template("client")

    assert template is not None
    list_names = [item["name"] for item in template["lists"]]
    assert list_names == ["client-inbox", "client-deliverables", "client-follow-ups"]


def test_resolve_template_allows_custom_template_file_override(tmp_path):
    template_file = tmp_path / "reminders-templates.json"
    template_file.write_text(
        json.dumps(
            {
                "templates": {
                    "dev": {
                        "lists": [
                            {
                                "name": "custom-board",
                                "sections": ["todo", "done"],
                                "starter_reminders": {"todo": ["Capture requirements"]},
                            }
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    template = reminders_scaffold.resolve_template("dev", template_file=str(template_file))

    assert template is not None
    assert template["lists"] == [
        {
            "name": "custom-board",
            "sections": ["todo", "done"],
            "starter_reminders": {"todo": ["Capture requirements"]},
        }
    ]


def test_scaffold_template_creates_lists_sections_and_missing_starters(monkeypatch):
    group_calls: list[tuple[str, str]] = []
    list_calls: list[tuple[str, str]] = []
    created_sections: list[tuple[str, str]] = []
    created_reminders: list[tuple[str, str, str]] = []

    monkeypatch.setattr(
        reminders_scaffold,
        "_ensure_group",
        lambda account_name, project_name: group_calls.append((account_name, project_name))
        or {"ok": True, "status": "created", "path": f"{account_name}/{project_name}"},
    )
    monkeypatch.setattr(
        reminders_scaffold,
        "_ensure_list",
        lambda group_path, list_name: list_calls.append((group_path, list_name))
        or {"ok": True, "status": "created", "path": f"{group_path}/{list_name}"},
    )
    monkeypatch.setattr(
        reminders_scaffold,
        "_list_sections",
        lambda list_path: ["todo"] if list_path.endswith("/custom-board") else [],
    )
    monkeypatch.setattr(
        reminders_scaffold,
        "_create_section",
        lambda list_path, section_name: created_sections.append((list_path, section_name)),
    )
    monkeypatch.setattr(
        reminders_scaffold,
        "_list_reminder_titles",
        lambda list_path, section_name: ["Existing starter"] if section_name == "todo" else [],
    )
    monkeypatch.setattr(
        reminders_scaffold,
        "_create_starter_reminder",
        lambda list_path, section_name, title: created_reminders.append((list_path, section_name, title)),
    )
    monkeypatch.setattr(
        reminders_scaffold,
        "resolve_template",
        lambda template_name, template_file="": {
            "lists": [
                {
                    "name": "custom-board",
                    "sections": ["todo", "done"],
                    "starter_reminders": {
                        "todo": ["Existing starter", "New starter"],
                        "done": ["Archive project"],
                    },
                }
            ]
        },
    )

    result = reminders_scaffold.scaffold_template("dev", "client-john-adams")

    assert result["ok"] is True
    assert group_calls == [("iCloud", "client-john-adams")]
    assert list_calls == [("iCloud/client-john-adams", "custom-board")]
    assert created_sections == [("iCloud/client-john-adams/custom-board", "done")]
    assert created_reminders == [
        ("iCloud/client-john-adams/custom-board", "todo", "New starter"),
        ("iCloud/client-john-adams/custom-board", "done", "Archive project"),
    ]
    assert result["group_status"] == "created"
    assert result["lists"][0]["ensure_status"] == "created"
    assert result["lists"][0]["sections_existing"] == 1
    assert result["lists"][0]["sections_created"] == 1
    assert result["lists"][0]["reminders_existing"] == 1
    assert result["lists"][0]["reminders_created"] == 2


def test_scaffold_template_wraps_mutations_in_runtime_gate(monkeypatch):
    events: list[str] = []

    @contextlib.contextmanager
    def _fake_gate(*, ttl_seconds=300.0, reason=""):
        events.append(f"enter:{reason}")
        try:
            yield
        finally:
            events.append("exit")

    monkeypatch.setattr(reminders_scaffold.reminders_runtime_gate, "reminders_live_gate", _fake_gate)
    monkeypatch.setattr(
        reminders_scaffold,
        "_ensure_group",
        lambda account_name, project_name: {"ok": True, "status": "created", "path": f"{account_name}/{project_name}"},
    )
    monkeypatch.setattr(
        reminders_scaffold,
        "_ensure_list",
        lambda group_path, list_name: {"ok": True, "status": "created", "path": f"{group_path}/{list_name}"},
    )
    monkeypatch.setattr(reminders_scaffold, "_list_sections", lambda list_path: [])
    monkeypatch.setattr(reminders_scaffold, "_create_section", lambda list_path, section_name: None)
    monkeypatch.setattr(reminders_scaffold, "_list_reminder_titles", lambda list_path, section_name: [])
    monkeypatch.setattr(reminders_scaffold, "_create_starter_reminder", lambda list_path, section_name, title: None)
    monkeypatch.setattr(
        reminders_scaffold,
        "resolve_template",
        lambda template_name, template_file="": {"lists": [{"name": "client-inbox", "sections": [], "starter_reminders": {}}]},
    )

    result = reminders_scaffold.scaffold_template("client", "client-tim-cook")

    assert result["ok"] is True
    assert events == ["enter:reminders_scaffold.scaffold_template", "exit"]


def test_list_sections_falls_back_to_ui_rows_when_accessibility_helper_returns_empty(monkeypatch):
    monkeypatch.setattr(reminders_scaffold.reminders_ax, "list_sections", lambda list_path: [])
    monkeypatch.setattr(reminders_scaffold.reminders_ax, "focus_list", lambda list_path: True)
    monkeypatch.setattr(
        reminders_scaffold,
        "_scan_rows",
        lambda list_path, max_rows=36: [
            {"row": 1, "kind": "header", "section": "new", "title": "new"},
            {"row": 2, "kind": "placeholder", "section": "new", "title": ""},
            {"row": 3, "kind": "header", "section": "active", "title": "active"},
            {"row": 4, "kind": "placeholder", "section": "active", "title": ""},
        ],
    )

    sections = reminders_scaffold._list_sections("iCloud/client-tim-cook/inbox")

    assert sections == ["new", "active"]


def test_list_reminder_titles_falls_back_to_ui_rows_when_accessibility_helper_returns_empty(monkeypatch):
    monkeypatch.setattr(
        reminders_scaffold.reminders_ax,
        "list_reminders",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(reminders_scaffold.reminders_ax, "focus_list", lambda list_path: True)
    monkeypatch.setattr(
        reminders_scaffold,
        "_scan_rows",
        lambda list_path, max_rows=36: [
            {"row": 2, "kind": "reminder", "section": "new", "title": "Capture kickoff notes"},
            {"row": 3, "kind": "reminder", "section": "active", "title": "Schedule kickoff"},
        ],
    )

    titles = reminders_scaffold._list_reminder_titles("iCloud/client-tim-cook/inbox", "new")

    assert titles == ["Capture kickoff notes"]
