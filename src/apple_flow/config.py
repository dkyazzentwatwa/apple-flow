from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("apple_flow.config")


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
    timezone: str = ""  # e.g. "America/Los_Angeles"; empty = system local timezone
    db_path: Path = Path.home() / ".apple-flow" / "relay.db"
    poll_interval_seconds: float = 2.0
    approval_ttl_minutes: int = 20
    max_messages_per_minute: int = 30

    # Legacy setting kept for migration messaging only; ignored for connector selection.
    use_codex_cli: bool = True
    codex_cli_command: str = "codex"
    codex_cli_context_window: int = 10
    codex_cli_model: str = ""  # e.g., "gpt-5.3-codex" (empty = use codex default)

    # Connector selection.
    connector: str = ""  # "codex-cli" | "claude-cli" | "gemini-cli" | "kilo-cli" | "cline" | "ollama"

    # Claude CLI connector settings (used when connector="claude-cli")
    claude_cli_command: str = "claude"
    claude_cli_dangerously_skip_permissions: bool = True
    claude_cli_context_window: int = 10
    claude_cli_model: str = ""  # e.g. "claude-sonnet-4-6", "claude-opus-4-6"
    claude_cli_tools: list[str] = Field(default_factory=list)  # e.g. ["default", "WebSearch"]
    claude_cli_allowed_tools: list[str] = Field(default_factory=list)  # e.g. ["WebSearch"]

    # Kilo CLI connector settings (used when connector="kilo-cli")
    kilo_cli_command: str = "kilo"
    kilo_cli_context_window: int = 10
    kilo_cli_model: str = ""  # e.g. "google/gemini-3-flash-preview" (empty = kilo default)

    # Cline CLI connector settings (used when connector="cline")
    cline_command: str = "cline"
    cline_context_window: int = 3
    cline_model: str = ""  # e.g. "kimi-k2", "gpt-4o" (empty = cline default)
    cline_use_json: bool = True
    cline_act_mode: bool = True  # skip plan mode for faster responses

    # Gemini CLI connector settings (used when connector="gemini-cli")
    gemini_cli_command: str = "gemini"
    gemini_cli_context_window: int = 10
    gemini_cli_model: str = "gemini-3-flash-preview"
    gemini_cli_approval_mode: str = "yolo"  # default | auto_edit | yolo | plan

    # Ollama connector settings (used when connector="ollama")
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:4b"
    ollama_context_window: int = 10
    ollama_num_ctx: int = 4096
    ollama_temperature: float = 0.2
    ollama_enable_thinking: bool = False
    ollama_auto_pull_model: bool = True
    ollama_tool_timeout_seconds: float = 120.0
    ollama_max_tool_iterations: int = 8
    ollama_max_tool_output_chars: int = 12000

    admin_host: str = "127.0.0.1"
    admin_port: int = 8787
    admin_api_token: str = ""  # shared-secret token for admin API auth (empty = no auth)

    messages_db_path: Path = Path.home() / "Library" / "Messages" / "chat.db"
    process_historical_on_first_start: bool = False
    max_startup_replay_rows: int = 50
    startup_catchup_window_seconds: int = 60
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
    # File aliases for prompt references via @f:<alias>
    file_aliases: str = ""  # JSON dict: '{"context-bank":"/path/to/MEMORY.md"}'

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
    mail_response_subject: str = "AGENT:"
    mail_signature: str = "\n\n—\nApple Flow 🤖, Your 24/7 Assistant"

    # Apple Reminders integration settings
    enable_reminders_polling: bool = False
    reminders_list_name: str = "agent-task"
    reminders_archive_list_name: str = "agent-archive"
    reminders_owner: str = ""
    reminders_auto_approve: bool = False
    reminders_poll_interval_seconds: float = 5.0
    reminders_due_delay_seconds: int = 60

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

    # Phone call + TTS settings (local-assisted callback flow)
    phone_owner_number: str = ""
    phone_preferred_app: str = "phone"  # phone | facetime
    phone_tts_voice: str = ""
    phone_tts_rate: float = 180.0
    phone_tts_engine: str = "auto"  # auto | say | piper
    phone_piper_command: str = "piper"
    phone_piper_model_path: str = ""
    phone_in_call_tts_delay_seconds: float = 4.0
    phone_enable_in_call_tts: bool = True
    phone_deterministic_in_call_audio: bool = False
    phone_virtual_audio_input_device: str = "BlackHole 2ch"
    phone_virtual_audio_output_device: str = "BlackHole 2ch"
    phone_audio_switch_command: str = "SwitchAudioSource"
    phone_audio_play_command: str = "afplay"
    phone_audio_route_settle_seconds: float = 0.8

    # Progress streaming for long tasks
    enable_progress_streaming: bool = True
    progress_update_interval_seconds: float = 30.0
    execution_heartbeat_seconds: float = 120.0
    checkpoint_on_timeout: bool = True
    max_resume_attempts: int = 5
    auto_resume_on_timeout: bool = False
    run_worker_count: int = 4
    run_job_lease_seconds: int = 180
    run_recovery_scan_seconds: float = 30.0
    max_run_wall_clock_seconds: int = 14_400

    # Executor / verifier behaviour
    enable_verifier: bool = False  # run a verification turn after execution (adds latency)

    # Autonomous healer (GitHub issue-driven remediation loop)
    enable_autonomous_healer: bool = False
    healer_mode: str = "guarded_pr"  # guarded_pr | auto_merge_low_risk | full_auto
    healer_repo_path: str = ""
    healer_poll_interval_seconds: float = 120.0
    healer_max_concurrent_issues: int = 2
    healer_retry_budget: int = 8
    healer_backoff_initial_seconds: int = 60
    healer_backoff_max_seconds: int = 3600
    healer_circuit_breaker_failure_rate: float = 0.5
    healer_circuit_breaker_window: int = 20
    healer_sandbox_mode: str = "docker"  # docker (phase-1 default/supported)
    healer_issue_required_labels: list[str] = Field(default_factory=lambda: ["healer:ready"])
    healer_trusted_actors: list[str] = Field(default_factory=list)
    healer_max_wall_clock_seconds_per_issue: int = 1800
    healer_max_diff_files: int = 20
    healer_max_diff_lines: int = 1200
    healer_max_failed_tests_allowed: int = 0
    healer_pr_actions_require_approval: bool = True
    healer_pr_required_label: str = "healer:pr-approved"
    healer_learning_enabled: bool = False
    healer_scan_enable_issue_creation: bool = True
    healer_scan_max_issues_per_run: int = 5
    healer_scan_severity_threshold: str = "medium"  # low | medium | high | critical
    healer_scan_default_labels: list[str] = Field(default_factory=lambda: ["healer:ready", "kind:scan"])
    healer_scan_notes_log: bool = False
    enable_healer_scheduled_scans: bool = False
    healer_daily_scan_time: str = "06:00"
    healer_weekly_deep_scan_day: str = "sunday"
    healer_weekly_deep_scan_time: str = "04:00"
    healer_scheduled_scan_owner: str = ""
    healer_scan_artifacts_dir: str = "logs/scans"
    healer_schedule_poll_seconds: float = 60.0

    # File attachment settings
    enable_attachments: bool = False
    max_attachment_size_mb: int = 10
    attachment_temp_dir: str = "/tmp/apple_flow_attachments"
    attachment_max_files_per_message: int = 6
    attachment_max_text_chars_per_file: int = 6000
    attachment_max_total_text_chars: int = 24000
    attachment_enable_image_ocr: bool = True

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
    enable_memory_v2: bool = False
    memory_v2_shadow_mode: bool = False
    memory_v2_migrate_on_start: bool = True
    memory_v2_db_path: str = ""  # empty -> <agent-office>/.apple-flow-memory.sqlite3
    memory_v2_scope: str = "global"
    memory_v2_maintenance_interval_seconds: float = 3600.0
    memory_max_storage_mb: int = 256
    memory_v2_include_legacy_fallback: bool = True

    # Follow-up scheduler
    enable_follow_ups: bool = False
    default_follow_up_hours: float = 2.0
    max_follow_up_nudges: int = 3

    # Ambient scanning (passive context enrichment)
    enable_ambient_scanning: bool = False
    ambient_scan_interval_seconds: float = 900.0

    # Log file path (used by `logs` command to tail the daemon log)
    log_file_path: str = "logs/apple-flow.err.log"

    # Agent-office → Supabase sync
    enable_office_sync: bool = False
    supabase_url: str = "http://localhost:54321"
    supabase_service_key: str = ""
    office_sync_interval_seconds: float = 3600.0

    # CSV audit logging (analytics-friendly mirror of structured events)
    enable_csv_audit_log: bool = True
    csv_audit_log_path: str = "agent-office/90_logs/events.csv"
    csv_audit_include_headers_if_missing: bool = True

    # Markdown automation log mirror (human-readable, optional)
    enable_markdown_automation_log: bool = False

    # Weekly review
    companion_weekly_review_day: str = "sunday"
    companion_weekly_review_time: str = "20:00"

    @field_validator(
        "allowed_senders",
        "allowed_workspaces",
        "mail_allowed_senders",
        "claude_cli_tools",
        "claude_cli_allowed_tools",
        "healer_issue_required_labels",
        "healer_trusted_actors",
        "healer_scan_default_labels",
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

    @field_validator(
        "admin_port",
        "enable_memory",
        "enable_memory_v2",
        "memory_v2_shadow_mode",
        "memory_v2_migrate_on_start",
        "memory_v2_include_legacy_fallback",
        "enable_autonomous_healer",
        "healer_pr_actions_require_approval",
        "healer_learning_enabled",
        "healer_scan_enable_issue_creation",
        "healer_scan_notes_log",
        "enable_healer_scheduled_scans",
        "healer_daily_scan_time",
        "healer_weekly_deep_scan_day",
        "healer_weekly_deep_scan_time",
        "healer_scheduled_scan_owner",
        "healer_scan_artifacts_dir",
        "healer_schedule_poll_seconds",
        "enable_csv_audit_log",
        "csv_audit_include_headers_if_missing",
        "enable_markdown_automation_log",
        "phone_preferred_app",
        "phone_tts_rate",
        "phone_tts_engine",
        "phone_piper_command",
        "phone_piper_model_path",
        "phone_in_call_tts_delay_seconds",
        "phone_enable_in_call_tts",
        "phone_deterministic_in_call_audio",
        "phone_virtual_audio_input_device",
        "phone_virtual_audio_output_device",
        "phone_audio_switch_command",
        "phone_audio_play_command",
        "phone_audio_route_settle_seconds",
        mode="before",
    )
    @classmethod
    def _empty_string_uses_default(cls, value: Any, info: ValidationInfo) -> Any:
        if value == "":
            field = cls.model_fields.get(info.field_name)
            if field is not None:
                return field.default
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

    @field_validator("timezone", mode="after")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        if not value:
            return value
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(
                f"Invalid timezone {value!r}. Use an IANA timezone like 'America/Los_Angeles'."
            ) from exc
        return value

    @field_validator("healer_mode", mode="after")
    @classmethod
    def _validate_healer_mode(cls, value: str) -> str:
        allowed = {"guarded_pr", "auto_merge_low_risk", "full_auto"}
        normalized = (value or "").strip().lower()
        if normalized in allowed:
            return normalized
        raise ValueError(f"Invalid healer_mode {value!r}. Allowed: {', '.join(sorted(allowed))}")

    @field_validator("healer_sandbox_mode", mode="after")
    @classmethod
    def _validate_healer_sandbox_mode(cls, value: str) -> str:
        allowed = {"docker"}
        normalized = (value or "").strip().lower()
        if normalized in allowed:
            return normalized
        raise ValueError(f"Invalid healer_sandbox_mode {value!r}. Allowed: {', '.join(sorted(allowed))}")

    @field_validator("healer_scan_severity_threshold", mode="after")
    @classmethod
    def _validate_healer_scan_severity_threshold(cls, value: str) -> str:
        allowed = {"low", "medium", "high", "critical"}
        normalized = (value or "").strip().lower()
        if normalized in allowed:
            return normalized
        raise ValueError(
            f"Invalid healer_scan_severity_threshold {value!r}. Allowed: {', '.join(sorted(allowed))}"
        )

    @field_validator("healer_daily_scan_time", "healer_weekly_deep_scan_time", mode="after")
    @classmethod
    def _validate_healer_schedule_time(cls, value: str) -> str:
        normalized = (value or "").strip()
        parts = normalized.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid time {value!r}. Use HH:MM (24-hour), for example '06:00'.")
        try:
            hour = int(parts[0])
            minute = int(parts[1])
        except ValueError as exc:
            raise ValueError(f"Invalid time {value!r}. Use HH:MM (24-hour), for example '06:00'.") from exc
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError(f"Invalid time {value!r}. Use HH:MM (24-hour), for example '06:00'.")
        return f"{hour:02d}:{minute:02d}"

    @field_validator("healer_weekly_deep_scan_day", mode="after")
    @classmethod
    def _validate_healer_weekly_day(cls, value: str) -> str:
        allowed = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
        normalized = (value or "").strip().lower()
        if normalized in allowed:
            return normalized
        raise ValueError(
            f"Invalid healer_weekly_deep_scan_day {value!r}. Allowed: {', '.join(sorted(allowed))}"
        )

    @field_validator("phone_preferred_app", mode="after")
    @classmethod
    def _validate_phone_preferred_app(cls, value: str) -> str:
        allowed = {"phone", "facetime"}
        normalized = (value or "").strip().lower()
        if normalized in allowed:
            return normalized
        raise ValueError(f"Invalid phone_preferred_app {value!r}. Allowed: {', '.join(sorted(allowed))}")

    @field_validator("phone_tts_engine", mode="after")
    @classmethod
    def _validate_phone_tts_engine(cls, value: str) -> str:
        allowed = {"auto", "say", "piper"}
        normalized = (value or "").strip().lower()
        if normalized in allowed:
            return normalized
        raise ValueError(f"Invalid phone_tts_engine {value!r}. Allowed: {', '.join(sorted(allowed))}")

    @field_validator("db_path", "messages_db_path", mode="after")
    @classmethod
    def _validate_absolute_paths(cls, value: Path, info: ValidationInfo) -> Path:
        if value.is_absolute():
            return value

        examples = {
            "db_path": "/Users/<user>/.apple-flow/relay.db",
            "messages_db_path": "/Users/<user>/Library/Messages/chat.db",
        }
        example = examples.get(info.field_name, "/absolute/path")
        raise ValueError(
            f"{info.field_name} must be an absolute path. "
            f"Do not use '~' or relative paths. Example: {example}"
        )

    def get_connector_type(self) -> str:
        """Return active connector type, auto-migrating deprecated values."""
        connector = (self.connector or "").strip()
        if connector == "codex-app-server":
            return "codex-cli"
        if connector:
            return connector
        return "codex-cli"

    def get_connector_warnings(self) -> list[str]:
        """Return one-time migration warnings for deprecated connector config."""
        warnings: list[str] = []
        if (self.connector or "").strip() == "codex-app-server":
            warnings.append(
                "Deprecated connector 'codex-app-server' detected; auto-migrating to 'codex-cli'. "
                "Please update apple_flow_connector in .env."
            )
        if not (self.connector or "").strip() and self.use_codex_cli is False:
            warnings.append(
                "Legacy key apple_flow_use_codex_cli=false is deprecated and ignored; "
                "defaulting connector to 'codex-cli'."
            )
        for warning in warnings:
            logger.warning(warning)
        return warnings

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

    def get_file_aliases(self) -> dict[str, str]:
        """Parse file_aliases JSON string into an alias->absolute-filepath dict."""
        if not self.file_aliases:
            return {}
        try:
            aliases = json.loads(self.file_aliases)
            if isinstance(aliases, dict):
                return {k: str(Path(v).resolve()) for k, v in aliases.items()}
        except (json.JSONDecodeError, TypeError):
            pass
        return {}
