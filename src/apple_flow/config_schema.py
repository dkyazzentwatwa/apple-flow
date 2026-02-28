from __future__ import annotations

import json
from pathlib import Path
from typing import Any, get_origin

from .config import RelaySettings

SCHEMA_VERSION = "1"

_SECTION_ORDER: list[tuple[str, str, bool]] = [
    ("core", "Core", True),
    ("connectors", "Connectors", False),
    ("admin", "Admin API", False),
    ("imessage", "iMessage Runtime", False),
    ("mail", "Mail", False),
    ("reminders", "Reminders", False),
    ("notes", "Notes", False),
    ("calendar", "Calendar", False),
    ("attachments", "Attachments", False),
    ("execution", "Progress & Execution", False),
    ("companion", "Companion", False),
    ("memory", "Memory", False),
    ("scheduler", "Scheduler & Ambient", False),
    ("office_sync", "Office Sync", False),
]

_REQUIRED_KEYS = {
    "apple_flow_allowed_senders",
    "apple_flow_allowed_workspaces",
    "apple_flow_default_workspace",
    "apple_flow_connector",
    "apple_flow_admin_host",
    "apple_flow_admin_port",
    "apple_flow_admin_api_token",
}

_ENUM_OPTIONS: dict[str, list[str]] = {
    "apple_flow_connector": [
        "codex-cli",
        "claude-cli",
        "gemini-cli",
        "kilo-cli",
        "cline",
    ],
    "apple_flow_gemini_cli_approval_mode": ["default", "auto_edit", "yolo", "plan"],
    "apple_flow_companion_weekly_review_day": [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ],
}

_SKIP_KEYS = {
    "apple_flow_use_codex_cli",
}


def _field_to_key(field_name: str) -> str:
    return f"apple_flow_{field_name}"


def _human_label(field_name: str) -> str:
    return field_name.replace("_", " ").strip().title()


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in ("token", "secret", "password", "api_key", "service_key"))


def _section_for_key(key: str) -> str:
    if key in {
        "apple_flow_allowed_senders",
        "apple_flow_allowed_workspaces",
        "apple_flow_default_workspace",
        "apple_flow_timezone",
        "apple_flow_db_path",
        "apple_flow_poll_interval_seconds",
        "apple_flow_max_messages_per_minute",
        "apple_flow_approval_ttl_minutes",
    }:
        return "core"
    if any(
        key.startswith(prefix)
        for prefix in (
            "apple_flow_connector",
            "apple_flow_codex_",
            "apple_flow_claude_",
            "apple_flow_gemini_",
            "apple_flow_kilo_",
            "apple_flow_cline_",
        )
    ):
        return "connectors"
    if key.startswith("apple_flow_admin_"):
        return "admin"
    if any(
        key.startswith(prefix)
        for prefix in (
            "apple_flow_messages_",
            "apple_flow_process_historical",
            "apple_flow_max_startup",
            "apple_flow_startup_",
            "apple_flow_notify_",
            "apple_flow_only_poll_",
            "apple_flow_require_chat_prefix",
            "apple_flow_chat_prefix",
            "apple_flow_suppress_duplicate_",
            "apple_flow_send_startup_intro",
            "apple_flow_auto_context_messages",
            "apple_flow_inject_tools_context",
            "apple_flow_trigger_tag",
            "apple_flow_workspace_aliases",
            "apple_flow_personality_prompt",
        )
    ):
        return "imessage"
    if key.startswith("apple_flow_mail_") or key == "apple_flow_enable_mail_polling":
        return "mail"
    if key.startswith("apple_flow_reminders_") or key == "apple_flow_enable_reminders_polling":
        return "reminders"
    if key.startswith("apple_flow_notes_") or key in {
        "apple_flow_enable_notes_polling",
        "apple_flow_enable_notes_logging",
    }:
        return "notes"
    if key.startswith("apple_flow_calendar_") or key == "apple_flow_enable_calendar_polling":
        return "calendar"
    if key.startswith("apple_flow_enable_attachments") or key.startswith("apple_flow_max_attachment") or key.startswith(
        "apple_flow_attachment_temp_dir"
    ):
        return "attachments"
    if key.startswith("apple_flow_enable_progress") or key.startswith("apple_flow_progress_") or key.startswith(
        "apple_flow_execution_"
    ) or key.startswith("apple_flow_checkpoint_") or key.startswith("apple_flow_auto_resume_") or key.startswith(
        "apple_flow_run_"
    ) or key.startswith("apple_flow_max_run_") or key.startswith("apple_flow_max_resume_") or key.startswith(
        "apple_flow_codex_turn_timeout"
    ) or key.startswith("apple_flow_max_concurrent_") or key.startswith("apple_flow_enable_verifier"):
        return "execution"
    if key.startswith("apple_flow_enable_companion") or key.startswith("apple_flow_companion_") or key.startswith(
        "apple_flow_soul_file"
    ):
        return "companion"
    if key.startswith("apple_flow_enable_memory") or key.startswith("apple_flow_memory_"):
        return "memory"
    if key.startswith("apple_flow_enable_follow_ups") or key.startswith("apple_flow_default_follow_up") or key.startswith(
        "apple_flow_max_follow_up"
    ) or key.startswith("apple_flow_enable_ambient") or key.startswith("apple_flow_ambient_scan_"):
        return "scheduler"
    if key.startswith("apple_flow_enable_office_sync") or key.startswith("apple_flow_supabase_") or key.startswith(
        "apple_flow_office_sync_"
    ) or key.startswith("apple_flow_log_file_path"):
        return "office_sync"
    return "core"


def _input_type(annotation: Any) -> str:
    origin = get_origin(annotation)
    if annotation is bool:
        return "bool"
    if annotation in (int, float):
        return "number"
    if annotation is Path:
        return "path"
    if origin is list:
        return "csv"
    return "text"


def stringify_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        if all(isinstance(v, str) for v in value):
            return ",".join(v for v in value if v)
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def build_config_schema() -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    for name, field in RelaySettings.model_fields.items():
        key = _field_to_key(name)
        if key in _SKIP_KEYS:
            continue
        section_id = _section_for_key(key)
        enum_options = _ENUM_OPTIONS.get(key, [])
        sensitive = _is_sensitive(key)
        input_type = _input_type(field.annotation)
        if sensitive and input_type == "text":
            input_type = "token"
        default_raw = field.default_factory() if field.default_factory is not None else field.default
        fields.append(
            {
                "key": key,
                "name": name,
                "label": _human_label(name),
                "section_id": section_id,
                "description": field.description or "",
                "required": key in _REQUIRED_KEYS,
                "sensitive": sensitive,
                "input_type": input_type,
                "default_value": stringify_value(default_raw),
                "validation_hint": "",
                "enum_options": enum_options,
                "restart_recommended": True,
            }
        )

    section_payload = [
        {
            "id": section_id,
            "label": label,
            "order": index,
            "default_expanded": default_expanded,
        }
        for index, (section_id, label, default_expanded) in enumerate(_SECTION_ORDER)
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "sections": section_payload,
        "fields": fields,
    }
