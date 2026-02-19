from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RelaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="apple_flow_",
        extra="ignore",
        env_file=".env",
        enable_decoding=False,
    )

    allowed_senders: list[str] = Field(default_factory=list)
    allowed_workspaces: list[str] = Field(default_factory=list)

    default_workspace: str = str(Path.home())
    db_path: Path = Path.home() / ".codex" / "relay.db"
    poll_interval_seconds: float = 2.0
    approval_ttl_minutes: int = 20
    max_messages_per_minute: int = 30

    codex_app_server_cmd: list[str] = Field(default_factory=lambda: ["codex", "app-server"])

    # CLI connector settings (preferred over app-server)
    use_codex_cli: bool = True
    codex_cli_command: str = "codex"
    codex_cli_context_window: int = 10
    codex_cli_model: str = ""  # e.g., "gpt-5.3-codex" (empty = use codex default)

    # Connector selection (overrides use_codex_cli when set)
    connector: str = ""  # "codex-cli" | "claude-cli" | "codex-app-server"

    # Claude CLI connector settings (used when connector="claude-cli")
    claude_cli_command: str = "claude"
    claude_cli_dangerously_skip_permissions: bool = True
    claude_cli_context_window: int = 10
    claude_cli_model: str = ""  # e.g. "claude-sonnet-4-6", "claude-opus-4-6"
    claude_cli_tools: list[str] = Field(default_factory=list)  # e.g. ["default", "WebSearch"]
    claude_cli_allowed_tools: list[str] = Field(default_factory=list)  # e.g. ["WebSearch"]

    admin_host: str = "127.0.0.1"
    admin_port: int = 8787

    messages_db_path: Path = Path.home() / "Library" / "Messages" / "chat.db"
    process_historical_on_first_start: bool = False
    max_startup_replay_rows: int = 50
    notify_blocked_senders: bool = False
    notify_rate_limited_senders: bool = False
    only_poll_allowed_senders: bool = True
    require_chat_prefix: bool = False
    chat_prefix: str = "relay:"
    suppress_duplicate_outbound_seconds: float = 90.0
    send_startup_intro: bool = True
    codex_turn_timeout_seconds: float = 300.0
    max_concurrent_ai_calls: int = 4

    # Workspace aliases for multi-workspace routing
    workspace_aliases: str = ""  # JSON dict: '{"web-app":"/path/to/web-app"}'

    # AI personality prompt (injected as system context for all chat turns)
    personality_prompt: str = (
        "You are an AI assistant embedded in Apple Flow, accessible via iMessage on macOS. "
        "You have access to the user's coding workspace at {workspace}. "
        "Respond naturally to any request — creative writing, coding, analysis, questions, or anything else. "
        "For simple requests, reply directly and concisely. For complex or multi-step work, describe your plan clearly. "
        "If you need to create, edit, or delete files, first describe your plan and ask the user to approve before acting. "
        "Keep responses concise for iMessage — avoid walls of text. Use plain text over heavy markdown. "
        "Do not announce yourself as an AI or include unnecessary preamble."
    )

    # Conversation memory: auto-inject recent messages into prompts
    auto_context_messages: int = 10  # 0 = disabled

    # Apple Tools context: inject TOOLS_CONTEXT into AI prompts so the AI knows apple-flow tools exist
    inject_tools_context: bool = True

    # Apple Mail integration settings
    enable_mail_polling: bool = False
    mail_poll_account: str = ""
    mail_poll_mailbox: str = "INBOX"
    mail_from_address: str = ""
    mail_allowed_senders: list[str] = Field(default_factory=list)
    mail_max_age_days: int = 2
    mail_signature: str = "\n\n—\nApple Flow 🤖, Your 24/7 Assistant"

    # Apple Reminders integration settings
    enable_reminders_polling: bool = False
    reminders_list_name: str = "agent-task"
    reminders_archive_list_name: str = "Archive"
    reminders_owner: str = ""
    reminders_auto_approve: bool = False
    reminders_poll_interval_seconds: float = 5.0

    # Global trigger tag: items without this tag are skipped across all channels.
    # Empty string = disabled (process everything — backward compatible).
    trigger_tag: str = "!!agent"

    # Apple Notes integration settings
    enable_notes_polling: bool = False
    notes_folder_name: str = "agent-task"
    notes_archive_folder_name: str = "agent-archive"
    notes_owner: str = ""
    notes_auto_approve: bool = False
    notes_poll_interval_seconds: float = 10.0
    notes_fetch_timeout_seconds: float = 20.0
    notes_fetch_retries: int = 1
    notes_fetch_retry_delay_seconds: float = 1.5

    # Notes logging (write-only, independent of notes polling)
    enable_notes_logging: bool = False
    notes_log_folder_name: str = "agent-logs"

    # Apple Calendar integration settings
    enable_calendar_polling: bool = False
    calendar_name: str = "agent-schedule"
    calendar_owner: str = ""
    calendar_auto_approve: bool = False
    calendar_poll_interval_seconds: float = 30.0
    calendar_lookahead_minutes: int = 5

    # Progress streaming for long tasks
    enable_progress_streaming: bool = False
    progress_update_interval_seconds: float = 30.0

    # File attachment settings
    enable_attachments: bool = False
    max_attachment_size_mb: int = 10
    attachment_temp_dir: str = "/tmp/apple_flow_attachments"

    # --- Companion Layer (autonomous proactive assistant) ---

    # Agent Office: workspace directory with SOUL.md, MEMORY.md, templates, logs
    soul_file: str = "agent-office/SOUL.md"  # relative to repo root or absolute path

    # Companion loop: proactive observations
    enable_companion: bool = False
    companion_poll_interval_seconds: float = 300.0
    companion_max_proactive_per_hour: int = 4
    companion_quiet_hours_start: str = "22:00"
    companion_quiet_hours_end: str = "07:00"
    companion_stale_approval_minutes: int = 30
    companion_calendar_lookahead_minutes: int = 60

    # Daily digest (morning briefing)
    companion_enable_daily_digest: bool = False
    companion_digest_time: str = "08:00"

    # File-based memory (agent-office)
    enable_memory: bool = False
    memory_max_context_chars: int = 2000

    # Follow-up scheduler
    enable_follow_ups: bool = False
    default_follow_up_hours: float = 2.0
    max_follow_up_nudges: int = 3

    # Ambient scanning (passive context enrichment)
    enable_ambient_scanning: bool = False
    ambient_scan_interval_seconds: float = 900.0

    # Weekly review
    companion_weekly_review_day: str = "sunday"
    companion_weekly_review_time: str = "20:00"

    @field_validator(
        "allowed_senders",
        "allowed_workspaces",
        "mail_allowed_senders",
        "claude_cli_tools",
        "claude_cli_allowed_tools",
        mode="before",
    )
    @classmethod
    def _parse_csv_or_json_list(cls, value: Any) -> Any:
        if isinstance(value, list):
            return value
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return json.loads(stripped)
            return [part.strip() for part in stripped.split(",") if part.strip()]
        return value

    @field_validator("codex_app_server_cmd", mode="before")
    @classmethod
    def _parse_command(cls, value: Any) -> Any:
        if isinstance(value, list):
            return value
        if value is None:
            return ["codex", "app-server"]
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return ["codex", "app-server"]
            if stripped.startswith("["):
                return json.loads(stripped)
            return [part.strip() for part in stripped.split(" ") if part.strip()]
        return value

    @field_validator("allowed_workspaces", mode="after")
    @classmethod
    def _resolve_workspace_paths(cls, value: list[str]) -> list[str]:
        """Resolve workspace paths to absolute paths."""
        return [str(Path(p).resolve()) for p in value]

    @field_validator("default_workspace", mode="after")
    @classmethod
    def _resolve_default_workspace(cls, value: str) -> str:
        """Resolve default workspace to absolute path."""
        return str(Path(value).resolve())

    def get_connector_type(self) -> str:
        """Return the active connector type string.

        Honors the explicit `connector` field first; falls back to the legacy
        `use_codex_cli` boolean for backwards compatibility.
        """
        if self.connector:
            return self.connector
        return "codex-cli" if self.use_codex_cli else "codex-app-server"

    def get_workspace_aliases(self) -> dict[str, str]:
        """Parse workspace_aliases JSON string into a dict."""
        if not self.workspace_aliases:
            return {}
        try:
            aliases = json.loads(self.workspace_aliases)
            if isinstance(aliases, dict):
                return {k: str(Path(v).resolve()) for k, v in aliases.items()}
        except (json.JSONDecodeError, TypeError):
            pass
        return {}
