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
    use_codex_cli: bool = True  # Use CLI instead of app-server (default: true)
    codex_cli_command: str = "codex"  # Path to codex binary
    codex_cli_context_window: int = 3  # Number of recent exchanges to include as context

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
    codex_turn_timeout_seconds: float = 300.0  # 5 minutes for Codex to respond

    @field_validator("allowed_senders", "allowed_workspaces", mode="before")
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
