from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from . import reminders_accessibility as reminders_ax
from . import reminders_runtime_gate
from .osascript_utils import run_osascript_with_recovery

_DETAIL_OUTLINE_SPEC = 'outline 1 of scroll area 1 of UI element 3 of splitter group 1 of front window'

BUILTIN_TEMPLATES: dict[str, dict[str, Any]] = {
    "dev": {
        "lists": [
            {
                "name": "dev-backlog",
                "sections": ["Inactive", "started", "issue-ready", "issue-done"],
                "starter_reminders": {
                    "Inactive": ["Capture project brief", "Break work into tasks"],
                    "started": ["Set first milestone"],
                },
            },
            {
                "name": "dev-today",
                "sections": ["next", "doing", "blocked", "done"],
                "starter_reminders": {
                    "next": ["Pick today's top task"],
                },
            },
            {
                "name": "dev-waiting",
                "sections": ["external", "scheduled", "follow-up", "done"],
                "starter_reminders": {
                    "external": ["Track external blockers"],
                },
            },
        ]
    },
    "client": {
        "lists": [
            {
                "name": "client-inbox",
                "sections": ["new", "active", "waiting", "done"],
                "starter_reminders": {
                    "new": ["Capture kickoff notes", "Capture stakeholder asks"],
                },
            },
            {
                "name": "client-deliverables",
                "sections": ["queued", "in-progress", "review", "delivered"],
                "starter_reminders": {
                    "queued": ["Draft initial deliverables plan"],
                },
            },
            {
                "name": "client-follow-ups",
                "sections": ["to-send", "waiting", "scheduled", "done"],
                "starter_reminders": {
                    "to-send": ["Send kickoff follow-up"],
                },
            },
        ]
    },
}


def _normalize_template_name(value: str) -> str:
    return (value or "").strip().lower()


def _escape_osascript(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


def _load_custom_templates(template_file: str = "") -> dict[str, dict[str, Any]]:
    path_text = (template_file or "").strip()
    if not path_text:
        return {}
    path = Path(path_text)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("templates"), dict):
        payload = payload["templates"]
    if not isinstance(payload, dict):
        return {}
    return {
        _normalize_template_name(name): spec
        for name, spec in payload.items()
        if isinstance(spec, dict)
    }


def resolve_template(template_name: str, template_file: str = "") -> dict[str, Any] | None:
    catalog = dict(BUILTIN_TEMPLATES)
    catalog.update(_load_custom_templates(template_file))
    return catalog.get(_normalize_template_name(template_name))


def _list_sections(list_path: str) -> list[str]:
    sections = reminders_ax.list_sections(list_path)
    if sections:
        return sections
    if not reminders_ax.focus_list(list_path):
        return []
    seen: list[str] = []
    for row in _scan_rows(list_path):
        section_name = str(row.get("section", "")).strip()
        if row.get("kind") in {"header", "placeholder"} and section_name and section_name not in seen:
            seen.append(section_name)
    return seen


def _ensure_group(account_name: str, project_name: str) -> dict[str, Any]:
    return reminders_ax.create_group(project_name, default_account=account_name)


def _ensure_list(group_path: str, list_name: str) -> dict[str, Any]:
    return reminders_ax.create_list(group_path, list_name)


def _list_reminder_titles(list_path: str, section_name: str) -> list[str]:
    reminders = [
        str(item.get("name", "")).strip()
        for item in reminders_ax.list_reminders(
            list_path,
            filter_completed="all",
            limit=500,
            section_name=section_name,
        )
        if str(item.get("name", "")).strip()
    ]
    if reminders:
        return reminders
    if not reminders_ax.focus_list(list_path):
        return []
    return [
        str(row.get("title", "")).strip()
        for row in _scan_rows(list_path)
        if row.get("kind") == "reminder"
        and str(row.get("section", "")).strip() == section_name
        and str(row.get("title", "")).strip()
    ]


def _ui_get(spec: str) -> str:
    result = run_osascript_with_recovery(
        f'tell application "System Events" to tell process "Reminders" to get value of {spec}',
        app_name="Reminders",
        timeout=10.0,
        max_attempts=2,
    )
    return result.stdout.strip() if result.ok else ""


def _focus_list(list_path: str) -> None:
    reminders_ax.focus_list(list_path)


def _scan_rows(list_path: str, max_rows: int = 36) -> list[dict[str, Any]]:
    _focus_list(list_path)
    rows: list[dict[str, Any]] = []
    current_section = ""
    for index in range(1, max_rows + 1):
        header = _ui_get(f'text field 1 of UI element 1 of row {index} of {_DETAIL_OUTLINE_SPEC}')
        if header:
            current_section = header
            rows.append({"row": index, "kind": "header", "section": current_section, "title": header})
            continue
        reminder = _ui_get(f'text field 1 of group 1 of UI element 1 of row {index} of {_DETAIL_OUTLINE_SPEC}')
        if reminder:
            rows.append({"row": index, "kind": "reminder", "section": current_section, "title": reminder})
            continue
        placeholder_desc = _ui_get(
            f'attribute "AXDescription" of button 1 of UI element 1 of row {index} of {_DETAIL_OUTLINE_SPEC}'
        )
        if placeholder_desc.startswith("New reminder in "):
            rows.append(
                {
                    "row": index,
                    "kind": "placeholder",
                    "section": placeholder_desc.removeprefix("New reminder in ").strip(),
                    "title": "",
                }
            )
    return rows


def _wait_for(predicate, timeout_seconds: float = 12.0, interval_seconds: float = 0.35) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval_seconds)
    return bool(predicate())


def _create_section(list_path: str, section_name: str) -> None:
    _focus_list(list_path)
    script = (
        'tell application "System Events"\n'
        '  tell process "Reminders"\n'
        '    click menu bar item "File" of menu bar 1\n'
        '    click menu item "New Section" of menu 1 of menu bar item "File" of menu bar 1\n'
        f'    keystroke "{_escape_osascript(section_name)}"\n'
        '    key code 36\n'
        '  end tell\n'
        'end tell'
    )
    result = run_osascript_with_recovery(script, app_name="Reminders", timeout=20.0, max_attempts=2)
    if not result.ok:
        raise RuntimeError(result.detail)
    if not _wait_for(lambda: section_name in _list_sections(list_path), timeout_seconds=12.0):
        raise RuntimeError(f"section did not appear: {section_name}")


def _create_starter_reminder(list_path: str, section_name: str, title: str) -> None:
    rows = _scan_rows(list_path)
    placeholder = next(
        (row for row in rows if row["kind"] == "placeholder" and row["section"] == section_name),
        None,
    )
    if placeholder is None:
        raise RuntimeError(f"placeholder row not found for section {section_name!r}")
    script = (
        'tell application "System Events"\n'
        '  tell process "Reminders"\n'
        f'    click button 1 of UI element 1 of row {placeholder["row"]} of {_DETAIL_OUTLINE_SPEC}\n'
        f'    keystroke "{_escape_osascript(title)}"\n'
        '    key code 36\n'
        '  end tell\n'
        'end tell'
    )
    result = run_osascript_with_recovery(script, app_name="Reminders", timeout=20.0, max_attempts=2)
    if not result.ok:
        raise RuntimeError(result.detail)
    if not _wait_for(
        lambda: title in _list_reminder_titles(list_path, section_name),
        timeout_seconds=12.0,
    ):
        raise RuntimeError(f"starter reminder did not appear: {title}")


def scaffold_template(
    template_name: str,
    project_name: str,
    *,
    template_file: str = "",
    account_name: str = "iCloud",
) -> dict[str, Any]:
    resolved = resolve_template(template_name, template_file=template_file)
    if resolved is None:
        return {"ok": False, "error": f"unknown reminders template: {template_name}"}

    safe_project_name = (project_name or "").strip()
    safe_account_name = (account_name or "iCloud").strip() or "iCloud"
    if not safe_project_name:
        return {"ok": False, "error": "project name is required"}

    with reminders_runtime_gate.reminders_live_gate(reason="reminders_scaffold.scaffold_template"):
        group_result = _ensure_group(safe_account_name, safe_project_name)
        if not group_result.get("ok"):
            return {"ok": False, "error": str(group_result.get("error") or "unable to create group")}
        group_path = str(group_result.get("path") or f"{safe_account_name}/{safe_project_name}")

        output_lists: list[dict[str, Any]] = []
        for list_spec in resolved.get("lists", []):
            list_name = str(list_spec.get("name", "")).strip()
            if not list_name:
                continue
            list_result = _ensure_list(group_path, list_name)
            if not list_result.get("ok"):
                return {"ok": False, "error": str(list_result.get("error") or f"unable to create list {list_name}")}
            list_path = str(list_result.get("path") or f"{group_path}/{list_name}")
            existing_sections = _list_sections(list_path)
            sections_created = 0
            sections_existing = 0
            for section_name in list_spec.get("sections", []):
                if section_name in existing_sections:
                    sections_existing += 1
                    continue
                _create_section(list_path, section_name)
                sections_created += 1
                existing_sections.append(section_name)

            reminders_created = 0
            reminders_existing = 0
            starter_map = list_spec.get("starter_reminders", {})
            if isinstance(starter_map, dict):
                for section_name, titles in starter_map.items():
                    existing_titles = _list_reminder_titles(list_path, str(section_name))
                    for title in titles if isinstance(titles, list) else []:
                        title_text = str(title).strip()
                        if not title_text:
                            continue
                        if title_text in existing_titles:
                            reminders_existing += 1
                            continue
                        _create_starter_reminder(list_path, str(section_name), title_text)
                        reminders_created += 1
                        existing_titles.append(title_text)

            output_lists.append(
                {
                    "name": list_name,
                    "path": list_path,
                    "ensure_status": str(list_result.get("status", "")),
                    "sections_created": sections_created,
                    "sections_existing": sections_existing,
                    "reminders_created": reminders_created,
                    "reminders_existing": reminders_existing,
                }
            )

    return {
        "ok": True,
        "template": _normalize_template_name(template_name),
        "project_name": safe_project_name,
        "group_path": f"{safe_account_name}/{safe_project_name}",
        "group_status": str(group_result.get("status", "")) if output_lists else "",
        "lists": output_lists,
    }
