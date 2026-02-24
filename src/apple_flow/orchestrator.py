from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

from .approval import ApprovalHandler, OrchestrationResult
from .commanding import CommandKind, ParsedCommand, is_likely_mutating, parse_command
from .commands import COMMAND_HANDLERS
from .models import InboundMessage
from .notes_logging import log_to_notes
from .protocols import ConnectorProtocol, EgressProtocol, StoreProtocol

logger = logging.getLogger("apple_flow.orchestrator")

if TYPE_CHECKING:
    from .memory import FileMemory
    from .office_sync import OfficeSyncer
    from .scheduler import FollowUpScheduler

_SEP = "━" * 30
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


class RelayOrchestrator:
    def __init__(
        self,
        connector: ConnectorProtocol,
        egress: EgressProtocol,
        store: StoreProtocol,
        allowed_workspaces: list[str],
        default_workspace: str,
        approval_ttl_minutes: int = 20,
        require_chat_prefix: bool = True,
        chat_prefix: str = "relay:",
        workspace_aliases: dict[str, str] | None = None,
        auto_context_messages: int = 0,
        enable_progress_streaming: bool = False,
        progress_update_interval_seconds: float = 30.0,
        enable_verifier: bool = False,
        enable_attachments: bool = False,
        personality_prompt: str = "",
        reminders_egress: Any = None,
        reminders_archive_list_name: str = "Archive",
        notes_egress: Any = None,
        notes_archive_folder_name: str = "codex-archive",
        calendar_egress: Any = None,
        shutdown_callback: Callable[[], None] | None = None,
        log_notes_egress: Any = None,
        notes_log_folder_name: str = "codex-logs",
        memory: FileMemory | None = None,
        scheduler: FollowUpScheduler | None = None,
        office_syncer: OfficeSyncer | None = None,
        log_file_path: str | None = None,
        approval_sender_override: str = "",
    ):
        self.connector = connector
        self.egress = egress
        self.store = store
        self.allowed_workspaces = [str(Path(p).resolve()) for p in allowed_workspaces]
        self._allowed_workspace_set: frozenset[Path] = frozenset(
            Path(p) for p in self.allowed_workspaces
        )
        self.default_workspace = str(Path(default_workspace).resolve())
        self.require_chat_prefix = require_chat_prefix
        self.chat_prefix = (chat_prefix or "relay:").strip()
        self.workspace_aliases = workspace_aliases or {}
        self.auto_context_messages = auto_context_messages
        self.enable_attachments = enable_attachments
        self.personality_prompt = personality_prompt
        self.shutdown_callback = shutdown_callback
        self.log_notes_egress = log_notes_egress
        self.notes_log_folder_name = notes_log_folder_name
        self.memory = memory
        self.office_syncer = office_syncer
        self.log_file_path = log_file_path

        self._approval = ApprovalHandler(
            connector=connector,
            egress=egress,
            store=store,
            approval_ttl_minutes=approval_ttl_minutes,
            enable_progress_streaming=enable_progress_streaming,
            progress_update_interval_seconds=progress_update_interval_seconds,
            enable_verifier=enable_verifier,
            reminders_egress=reminders_egress,
            reminders_archive_list_name=reminders_archive_list_name,
            notes_egress=notes_egress,
            notes_archive_folder_name=notes_archive_folder_name,
            calendar_egress=calendar_egress,
            scheduler=scheduler,
            log_notes_egress=log_notes_egress,
            notes_log_folder_name=notes_log_folder_name,
            approval_sender_override=approval_sender_override,
        )

    # --- Workspace Resolution ---

    def _resolve_workspace(self, alias: str) -> str:
        if not alias:
            return self.default_workspace
        resolved = self.workspace_aliases.get(alias)
        if resolved and self._is_workspace_allowed(resolved):
            return resolved
        return self.default_workspace

    # --- Main Handler ---

    def handle_message(self, message: InboundMessage) -> OrchestrationResult:
        dedupe_hash = f"{message.sender}:{message.id}"
        inserted = True
        if hasattr(self.store, "record_message"):
            inserted = self.store.record_message(
                message_id=message.id,
                sender=message.sender,
                text=message.text,
                received_at=message.received_at,
                dedupe_hash=dedupe_hash,
            )
        if not inserted:
            return OrchestrationResult(kind=CommandKind.STATUS, response="duplicate")

        raw_text = message.text.strip()
        if not raw_text:
            return OrchestrationResult(kind=CommandKind.CHAT, response="ignored_empty")

        command = parse_command(raw_text)
        if command.kind is CommandKind.CHAT and self.require_chat_prefix:
            if not raw_text.lower().startswith(self.chat_prefix.lower()):
                return OrchestrationResult(kind=CommandKind.CHAT, response="ignored_missing_chat_prefix")
            command = ParsedCommand(
                kind=CommandKind.CHAT,
                payload=raw_text[len(self.chat_prefix) :].strip(),
            )
            if not command.payload:
                hint = (
                    f"Use `{self.chat_prefix} <message>` for general chat.\n"
                    "Or use `idea:`, `plan:`, `task:`, `project:`, `health`, `history:`, or `usage`."
                )
                self.egress.send(message.sender, hint)
                return OrchestrationResult(kind=CommandKind.CHAT, response=hint)
        elif command.kind is CommandKind.CHAT and not self.require_chat_prefix:
            if raw_text.lower().startswith(self.chat_prefix.lower()):
                stripped = raw_text[len(self.chat_prefix) :].strip()
                command = ParsedCommand(kind=CommandKind.CHAT, payload=stripped, workspace=command.workspace)

        if command.kind in COMMAND_HANDLERS:
            response = COMMAND_HANDLERS[command.kind].handle(self, message, command)
            return OrchestrationResult(kind=command.kind, response=response)

        if command.kind in {CommandKind.APPROVE, CommandKind.DENY}:
            return self._approval.resolve(message.sender, command.kind, command.payload)

        # Natural language mode: auto-promote bare CHAT messages with mutating intent to TASK
        if (
            command.kind is CommandKind.CHAT
            and not self.require_chat_prefix
            and is_likely_mutating(command.payload)
        ):
            command = ParsedCommand(kind=CommandKind.TASK, payload=command.payload, workspace=command.workspace)

        workspace = self._resolve_workspace(command.workspace)

        thread_id = self.connector.get_or_create_thread(message.sender)
        self.store.upsert_session(message.sender, thread_id, command.kind.value)

        if command.kind in {CommandKind.TASK, CommandKind.PROJECT}:
            return self._approval.handle_approval_required(
                message, command.kind, thread_id, command.payload, workspace,
                default_workspace=self.default_workspace,
                is_workspace_allowed=self._is_workspace_allowed,
            )

        prompt = self._build_non_mutating_prompt(command.kind, command.payload, workspace)
        prompt = self._inject_auto_context(message.sender, prompt)
        prompt = self._inject_attachment_context(message, prompt)
        prompt = self._inject_memory_context(prompt)

        response = self.connector.run_turn(thread_id, prompt)
        self.egress.send(message.sender, response)
        self._log_to_notes(command.kind.value, message.sender, command.payload, response)
        return OrchestrationResult(kind=command.kind, response=response)


    def _inject_auto_context(self, sender: str, prompt: str) -> str:
        if self.auto_context_messages <= 0:
            return prompt
        if not hasattr(self.store, "recent_messages"):
            return prompt
        recent = self.store.recent_messages(sender, limit=self.auto_context_messages)
        if not recent:
            return prompt
        context_lines = []
        for msg in reversed(recent):
            context_lines.append(f"[{msg.get('received_at', '?')}] {msg.get('text', '')[:200]}")
        context_block = "\n".join(context_lines)
        return f"Recent conversation history:\n{context_block}\n\n{prompt}"

    # --- Memory Context Injection ---

    def _inject_memory_context(self, prompt: str) -> str:
        if not self.memory:
            return prompt
        try:
            context = self.memory.get_context_for_prompt()
            if context:
                return f"Persistent memory context:\n{context}\n\n{prompt}"
        except Exception:
            logger.debug("Failed to inject memory context", exc_info=True)
        return prompt

    # --- Attachment Context ---

    def _inject_attachment_context(self, message: InboundMessage, prompt: str) -> str:
        if not self.enable_attachments:
            return prompt
        attachments = message.context.get("attachments", [])
        if not attachments:
            return prompt
        attachment_lines = []
        for att in attachments:
            filename = att.get("filename", "unknown")
            mime = att.get("mime_type", "unknown")
            path = att.get("path", "")
            attachment_lines.append(f"  - {filename} ({mime}) at {path}")
        attachment_block = "\n".join(attachment_lines)
        return f"{prompt}\n\nAttached files:\n{attachment_block}"

    # --- Notes Logging (delegated) ---

    def _log_to_notes(self, kind: str, sender: str, request: str, response: str) -> None:
        log_to_notes(self.log_notes_egress, self.notes_log_folder_name, kind, sender, request, response)

    # --- Prompt Building ---

    def _build_unified_prompt(self, payload: str, workspace: str | None = None) -> str:
        return payload

    def _build_non_mutating_prompt(self, kind: CommandKind, payload: str, workspace: str | None = None) -> str:
        if kind is CommandKind.IDEA:
            return f"brainstorm mode: generate options, trade-offs, and recommendation. request={payload}"
        if kind is CommandKind.PLAN:
            return f"planning mode: create a stepwise implementation plan with acceptance criteria. goal={payload}"
        return self._build_unified_prompt(payload, workspace)

    def _is_workspace_allowed(self, candidate: str) -> bool:
        target = Path(candidate).resolve()
        for allowed_path in self._allowed_workspace_set:
            if allowed_path == target or allowed_path in target.parents:
                return True
        return False

    @staticmethod
    def _parse_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            return None

    def _create_event(self, run_id: str, step: str, event_type: str, payload: dict[str, Any]) -> None:
        if hasattr(self.store, "create_event"):
            self.store.create_event(
                event_id=f"evt_{uuid4().hex[:12]}",
                run_id=run_id,
                step=step,
                event_type=event_type,
                payload=payload,
            )
