from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RelaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="codex_relay_",
        extra="ignore",
        env_file=".env",
        enable_decoding=False,
    )

    allowed_senders: list[str] = Field(default_factory=list)
    allowed_workspaces: list[str] = Field(default_factory=list)

    default_workspace: str = "/Users/cypher/Public/code/codex-flow"
    db_path: Path = Path.home() / ".codex" / "relay.db"
    poll_interval_seconds: float = 2.0
    approval_ttl_minutes: int = 20
    max_messages_per_minute: int = 30

    codex_app_server_cmd: list[str] = Field(default_factory=lambda: ["codex", "app-server"])

    # CLI connector settings (preferred over app-server)
    use_codex_cli: bool = True
    codex_cli_command: str = "codex"
    codex_cli_context_window: int = 3

    admin_host: str = "127.0.0.1"
    admin_port: int = 8787

    messages_db_path: Path = Path.home() / "Library" / "Messages" / "chat.db"
    process_historical_on_first_start: bool = False
    max_startup_replay_rows: int = 50
    notify_blocked_senders: bool = False
    notify_rate_limited_senders: bool = False
    only_poll_allowed_senders: bool = True
    require_chat_prefix: bool = True
    chat_prefix: str = "relay:"
    suppress_duplicate_outbound_seconds: float = 90.0
    send_startup_intro: bool = True
    codex_turn_timeout_seconds: float = 300.0

    # Workspace aliases for multi-workspace routing
    workspace_aliases: str = ""  # JSON dict: '{"web-app":"/path/to/web-app"}'

    # Conversation memory: auto-inject recent messages into prompts
    auto_context_messages: int = 0  # 0 = disabled

    # Apple Mail integration settings
    enable_mail_polling: bool = False
    mail_poll_account: str = ""
    mail_poll_mailbox: str = "INBOX"
    mail_from_address: str = ""
    mail_allowed_senders: list[str] = Field(default_factory=list)
    mail_max_age_days: int = 2
    mail_signature: str = "\n\n—\nCodex 🤖, Your 24/7 Assistant"

    # Apple Reminders integration settings
    enable_reminders_polling: bool = False
    reminders_list_name: str = "Codex Tasks"
    reminders_owner: str = ""
    reminders_auto_approve: bool = False
    reminders_poll_interval_seconds: float = 5.0

    # Apple Notes integration settings
    enable_notes_polling: bool = False
    notes_folder_name: str = "Codex Inbox"
    notes_owner: str = ""
    notes_auto_approve: bool = False
    notes_poll_interval_seconds: float = 10.0

    # Apple Calendar integration settings
    enable_calendar_polling: bool = False
    calendar_name: str = "Codex Schedule"
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
    attachment_temp_dir: str = "/tmp/codex_relay_attachments"

    # Voice memo settings (convert responses to audio via macOS TTS)
    enable_voice_memos: bool = False
    voice_memo_voice: str = "Samantha"
    voice_memo_max_chars: int = 2000
    voice_memo_send_text_too: bool = True

    @field_validator("allowed_senders", "allowed_workspaces", "mail_allowed_senders", mode="before")
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
