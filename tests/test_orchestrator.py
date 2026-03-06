"""Tests for the RelayOrchestrator."""

from typing import Any
from unittest.mock import patch

from conftest import FakeConnector, FakeEgress, FakeStore

from apple_flow.attachments import AttachmentProcessor
from apple_flow.commanding import CommandKind
from apple_flow.models import InboundMessage
from apple_flow.orchestrator import RelayOrchestrator


class ContextCapturingEgress(FakeEgress):
    def __init__(self) -> None:
        super().__init__()
        self.contexts: list[dict[str, Any] | None] = []

    def send(self, recipient: str, text: str, context: dict[str, Any] | None = None) -> None:
        self.contexts.append(context)
        super().send(recipient, text, context=context)


def test_task_command_creates_approval_request():
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
    )

    msg = InboundMessage(
        id="m1",
        sender="+15551234567",
        text="task: create a hello world project",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
    )

    result = orchestrator.handle_message(msg)
    assert result.kind is CommandKind.TASK
    assert result.approval_request_id is not None
    assert any("approve" in text.lower() for _, text in egress.messages)


def test_voice_command_creates_approval_without_planner_turn():
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
        phone_owner_number="+15551234567",
        phone_tts_engine="say",
    )

    msg = InboundMessage(
        id="m_voice_approval_1",
        sender="+15551234567",
        text="voice: hello from test",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
    )

    result = orchestrator.handle_message(msg)
    assert result.kind is CommandKind.VOICE
    assert result.approval_request_id is not None
    assert connector.turns == []
    assert any("Voice message plan" in text for _, text in egress.messages)


def test_voice_command_sends_message_on_approval():
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
        phone_owner_number="+15551234567",
        phone_tts_engine="say",
    )

    task_msg = InboundMessage(
        id="m_voice_exec_1",
        sender="+15551234567",
        text="voice: hello from test",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
    )
    task_result = orchestrator.handle_message(task_msg)
    assert task_result.approval_request_id is not None

    with patch(
        "apple_flow.apple_tools.messages_send_voice",
        return_value={
            "ok": True,
            "recipient": "+15551234567",
            "text_length": 15,
            "tts_engine": "say",
        },
    ) as send_voice_mock:
        approve_msg = InboundMessage(
            id="m_voice_exec_2",
            sender="+15551234567",
            text=f"approve {task_result.approval_request_id}",
            received_at="2026-02-16T12:01:00Z",
            is_from_me=False,
        )
        approval_result = orchestrator.handle_message(approve_msg)

    assert approval_result.kind is CommandKind.APPROVE
    assert store.get_run(task_result.run_id)["state"] == "completed"
    assert connector.turns == []
    assert any("Voice message sent" in text for _, text in egress.messages)
    send_voice_mock.assert_called_once()
    assert send_voice_mock.call_args.kwargs["recipient"] == "+15551234567"
    assert send_voice_mock.call_args.kwargs["tts_engine"] == "say"
    assert ("+15551234567", "relay: analyze attached files") in egress.marked_outbound
    assert "+15551234567" in egress.marked_attachment_outbound


def test_voice_command_requires_owner_number_config():
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
        phone_owner_number="",
    )

    msg = InboundMessage(
        id="m_voice_config_1",
        sender="+15551234567",
        text="voice: hello",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
    )
    result = orchestrator.handle_message(msg)

    assert result.kind is CommandKind.VOICE
    assert result.approval_request_id is None
    assert any("phone_owner_number" in text for _, text in egress.messages)


def test_voice_task_command_runs_task_and_sends_voice_followup():
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
        phone_owner_number="+15551234567",
        phone_tts_engine="say",
    )

    task_msg = InboundMessage(
        id="m_voice_task_exec_1",
        sender="+15551234567",
        text="voice-task: analyze my workspace",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
    )
    task_result = orchestrator.handle_message(task_msg)
    assert task_result.kind is CommandKind.VOICE_TASK
    assert task_result.approval_request_id is not None

    with patch(
        "apple_flow.apple_tools._synthesize_tts_to_audio_file",
        return_value={"ok": True, "engine": "say", "path": "/tmp/voice-task.wav"},
    ) as synth_mock:
        with patch(
            "apple_flow.apple_tools._send_imessage_attachment",
            return_value={"ok": True},
        ) as send_attachment_mock:
            with patch("pathlib.Path.unlink") as unlink_mock:
                approve_msg = InboundMessage(
                    id="m_voice_task_exec_2",
                    sender="+15551234567",
                    text=f"approve {task_result.approval_request_id}",
                    received_at="2026-02-16T12:01:00Z",
                    is_from_me=False,
                )
                approval_result = orchestrator.handle_message(approve_msg)

    assert approval_result.kind is CommandKind.APPROVE
    assert store.get_run(task_result.run_id)["state"] == "completed"
    assert connector.turns
    assert any("assistant-response" in text for _, text in egress.messages)
    synth_mock.assert_called_once()
    send_attachment_mock.assert_called_once_with("+15551234567", "/tmp/voice-task.wav")
    unlink_mock.assert_called()
    assert ("+15551234567", "relay: analyze attached files") in egress.marked_outbound
    assert "+15551234567" in egress.marked_attachment_outbound


def test_voice_task_from_notes_appends_result_and_sends_voice_followup():
    class FakeNotesEgress:
        def __init__(self):
            self.appended_notes = []
            self.moved_notes = []

        def append_result(self, note_id, result_text):
            self.appended_notes.append({
                "note_id": note_id,
                "result_text": result_text,
            })
            return True

        def move_to_archive(self, note_id, result_text, source_folder_name, archive_subfolder_name):
            self.moved_notes.append({
                "note_id": note_id,
                "result_text": result_text,
                "source_folder_name": source_folder_name,
                "archive_subfolder_name": archive_subfolder_name,
            })
            return True

    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()
    notes_egress = FakeNotesEgress()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
        notes_egress=notes_egress,
        notes_archive_folder_name="agent-archive",
        phone_owner_number="+15551234567",
        phone_tts_engine="say",
    )

    task_msg = InboundMessage(
        id="voice_note_1",
        sender="+15551234567",
        text="voice-task: summarize this note",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
        context={
            "channel": "notes",
            "note_id": "x-coredata://NOTE123",
            "note_title": "Workspace note",
            "folder_name": "agent-task",
        },
    )
    task_result = orchestrator.handle_message(task_msg)
    assert task_result.kind is CommandKind.VOICE_TASK
    assert task_result.approval_request_id is not None

    with patch(
        "apple_flow.apple_tools._synthesize_tts_to_audio_file",
        return_value={"ok": True, "engine": "say", "path": "/tmp/voice-note.wav"},
    ) as synth_mock:
        with patch(
            "apple_flow.apple_tools._send_imessage_attachment",
            return_value={"ok": True},
        ) as send_attachment_mock:
            with patch("pathlib.Path.unlink"):
                approve_msg = InboundMessage(
                    id="voice_note_2",
                    sender="+15551234567",
                    text=f"approve {task_result.approval_request_id}",
                    received_at="2026-02-16T12:01:00Z",
                    is_from_me=False,
                )
                orchestrator.handle_message(approve_msg)

    assert notes_egress.appended_notes
    assert notes_egress.moved_notes
    assert "[Apple Flow Result]" in notes_egress.moved_notes[0]["result_text"]
    synth_mock.assert_called_once()
    send_attachment_mock.assert_called_once_with("+15551234567", "/tmp/voice-note.wav")

def test_chat_requires_prefix_when_enabled():
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
        require_chat_prefix=True,
        chat_prefix="relay:",
    )

    msg = InboundMessage(
        id="m2",
        sender="+15551234567",
        text="what directory are we in?",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
    )

    result = orchestrator.handle_message(msg)
    assert result.response == "ignored_missing_chat_prefix"
    assert connector.turns == []
    assert egress.messages == []


def test_chat_with_prefix_runs_turn():
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
        require_chat_prefix=True,
        chat_prefix="relay:",
    )

    msg = InboundMessage(
        id="m3",
        sender="+15551234567",
        text="relay: what directory are we in?",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
    )

    result = orchestrator.handle_message(msg)
    assert result.kind is CommandKind.CHAT
    assert result.response == "assistant-response"
    assert connector.turns
    assert egress.messages


def test_mail_chat_response_preserves_mail_context_for_egress():
    connector = FakeConnector()
    egress = ContextCapturingEgress()
    store = FakeStore()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
        require_chat_prefix=True,
        chat_prefix="relay:",
    )

    msg = InboundMessage(
        id="m_mail_ctx_1",
        sender="test@example.com",
        text="relay: summarize this thread",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
        context={
            "channel": "mail",
            "mail_message_id": "msg-123",
            "mail_subject_sanitized": "Deploy update",
        },
    )

    result = orchestrator.handle_message(msg)
    assert result.kind is CommandKind.CHAT
    assert result.response == "assistant-response"
    assert egress.contexts
    assert egress.contexts[-1] is not None
    assert egress.contexts[-1].get("channel") == "mail"
    assert egress.contexts[-1].get("mail_message_id") == "msg-123"


def test_clear_context_resets_sender_thread():
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
        require_chat_prefix=True,
        chat_prefix="relay:",
    )

    msg = InboundMessage(
        id="m4",
        sender="+15551234567",
        text="clear context",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
    )

    result = orchestrator.handle_message(msg)
    assert result.kind is CommandKind.CLEAR_CONTEXT
    assert any("fresh chat context" in text for _, text in egress.messages)
    assert "reset:+15551234567" in connector.created


def test_help_command_returns_command_guide():
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
    )

    msg = InboundMessage(
        id="m_help_1",
        sender="+15551234567",
        text="help",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
    )

    result = orchestrator.handle_message(msg)
    assert result.kind is CommandKind.HELP
    assert "🤖 Apple Flow help" in result.response
    assert "status <run_id|request_id>" in result.response
    assert "approve <id> <extra instructions>" in result.response
    assert "system: stop | restart" in result.response
    assert "🔧 System controls:" in result.response
    assert egress.messages


def test_system_cancel_run_cancels_jobs_and_sender_processes():
    class KillableFakeConnector(FakeConnector):
        def __init__(self):
            super().__init__()
            self.cancel_calls: list[str | None] = []

        def cancel_active_processes(self, thread_id: str | None = None) -> int:
            self.cancel_calls.append(thread_id)
            return 1

    connector = KillableFakeConnector()
    egress = FakeEgress()
    store = FakeStore()
    store.create_run(
        run_id="run_cancel_1",
        sender="+15551234567",
        intent="task",
        state="executing",
        cwd="/tmp",
        risk_level="execute",
    )
    store.enqueue_run_job(
        job_id="job_cancel_1",
        run_id="run_cancel_1",
        sender="+15551234567",
        phase="executor",
        attempt=1,
        status="running",
    )

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
    )

    msg = InboundMessage(
        id="m_cancel_1",
        sender="+15551234567",
        text="system: cancel run run_cancel_1",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
    )
    result = orchestrator.handle_message(msg)

    assert result.kind is CommandKind.SYSTEM
    assert store.get_run("run_cancel_1")["state"] == "cancelled"
    assert store.run_jobs["job_cancel_1"]["status"] == "cancelled"
    assert connector.cancel_calls == ["+15551234567"]
    assert any(event["event_type"] == "execution_cancelled" for event in store.events)
    assert any("Cancelled run `run_cancel_1`" in text for _, text in egress.messages)


def test_system_killswitch_cancels_inflight_runs():
    class KillableFakeConnector(FakeConnector):
        def __init__(self):
            super().__init__()
            self.cancel_calls: list[str | None] = []

        def cancel_active_processes(self, thread_id: str | None = None) -> int:
            self.cancel_calls.append(thread_id)
            return 2

    connector = KillableFakeConnector()
    egress = FakeEgress()
    store = FakeStore()
    store.create_run(
        run_id="run_ks_1",
        sender="+15551234567",
        intent="task",
        state="executing",
        cwd="/tmp",
        risk_level="execute",
    )
    store.create_run(
        run_id="run_ks_2",
        sender="+15557654321",
        intent="task",
        state="planning",
        cwd="/tmp",
        risk_level="execute",
    )

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
    )

    msg = InboundMessage(
        id="m_kill_1",
        sender="+15551234567",
        text="system: killswitch",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
    )
    result = orchestrator.handle_message(msg)

    assert result.kind is CommandKind.SYSTEM
    assert connector.cancel_calls == [None]
    assert store.get_run("run_ks_1")["state"] == "cancelled"
    assert store.get_run("run_ks_2")["state"] == "cancelled"
    assert any("Killed 2" in text for _, text in egress.messages)


def test_reminder_task_moves_to_archive_after_approval():
    """Test that approved reminder tasks are automatically moved to archive."""

    class FakeRemindersEgress:
        def __init__(self):
            self.moved_reminders = []

        def move_to_archive(self, reminder_id, result_text, source_list_name, archive_list_name):
            self.moved_reminders.append({
                "reminder_id": reminder_id,
                "result_text": result_text,
                "source_list_name": source_list_name,
                "archive_list_name": archive_list_name,
            })
            return True

    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()
    reminders_egress = FakeRemindersEgress()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
        reminders_egress=reminders_egress,
        reminders_archive_list_name="Archive",
    )

    # Step 1: Send a task from a reminder
    task_msg = InboundMessage(
        id="rem_task_1",
        sender="+15551234567",
        text="task: create test file",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
        context={
            "channel": "reminders",
            "reminder_id": "x-apple-reminder://ABC123",
            "reminder_name": "Create test file",
            "list_name": "agent-task",
        },
    )

    result = orchestrator.handle_message(task_msg)
    assert result.kind is CommandKind.TASK
    assert result.approval_request_id is not None
    request_id = result.approval_request_id

    # Step 2: Approve the task
    approve_msg = InboundMessage(
        id="approve_1",
        sender="+15551234567",
        text=f"approve {request_id}",
        received_at="2026-02-16T12:05:00Z",
        is_from_me=False,
    )

    approval_result = orchestrator.handle_message(approve_msg)
    assert approval_result.kind is CommandKind.APPROVE

    # Step 3: Verify the reminder was moved to archive
    assert len(reminders_egress.moved_reminders) == 1
    moved = reminders_egress.moved_reminders[0]
    assert moved["reminder_id"] == "x-apple-reminder://ABC123"
    assert moved["source_list_name"] == "agent-task"
    assert moved["archive_list_name"] == "Archive"
    assert "[Apple Flow Result]" in moved["result_text"]


def test_note_task_moves_to_archive_after_approval():
    """Test that approved note tasks are automatically moved to archive subfolder."""

    class FakeNotesEgress:
        def __init__(self):
            self.moved_notes = []

        def move_to_archive(self, note_id, result_text, source_folder_name, archive_subfolder_name):
            self.moved_notes.append({
                "note_id": note_id,
                "result_text": result_text,
                "source_folder_name": source_folder_name,
                "archive_subfolder_name": archive_subfolder_name,
            })
            return True

    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()
    notes_egress = FakeNotesEgress()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
        notes_egress=notes_egress,
        notes_archive_folder_name="codex-archive",
    )

    # Step 1: Send a task from a note
    task_msg = InboundMessage(
        id="note_task_1",
        sender="+15551234567",
        text="task: create test file",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
        context={
            "channel": "notes",
            "note_id": "x-coredata://NOTE123",
            "note_title": "Create test file",
            "folder_name": "codex-task",
        },
    )

    result = orchestrator.handle_message(task_msg)
    assert result.kind is CommandKind.TASK
    assert result.approval_request_id is not None
    request_id = result.approval_request_id

    # Step 2: Approve the task
    approve_msg = InboundMessage(
        id="approve_1",
        sender="+15551234567",
        text=f"approve {request_id}",
        received_at="2026-02-16T12:05:00Z",
        is_from_me=False,
    )

    approval_result = orchestrator.handle_message(approve_msg)
    assert approval_result.kind is CommandKind.APPROVE

    # Step 3: Verify the note was moved to archive subfolder
    assert len(notes_egress.moved_notes) == 1
    moved = notes_egress.moved_notes[0]
    assert moved["note_id"] == "x-coredata://NOTE123"
    assert moved["source_folder_name"] == "codex-task"
    assert moved["archive_subfolder_name"] == "codex-archive"
    assert "[Apple Flow Result]" in moved["result_text"]


def test_note_task_writes_approval_breadcrumb_before_completion():
    class FakeNotesEgress:
        def __init__(self):
            self.appended = []
            self.moved_notes = []

        def append_result(self, note_id, result_text):
            self.appended.append({"note_id": note_id, "result_text": result_text})
            return True

        def move_to_archive(self, note_id, result_text, source_folder_name, archive_subfolder_name):
            self.moved_notes.append({
                "note_id": note_id,
                "result_text": result_text,
                "source_folder_name": source_folder_name,
                "archive_subfolder_name": archive_subfolder_name,
            })
            return True

    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()
    notes_egress = FakeNotesEgress()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
        notes_egress=notes_egress,
        notes_archive_folder_name="codex-archive",
    )

    task_msg = InboundMessage(
        id="note_task_approval_breadcrumb",
        sender="+15551234567",
        text="task: create test file",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
        context={
            "channel": "notes",
            "note_id": "x-coredata://NOTE123",
            "note_title": "Create test file",
            "folder_name": "codex-task",
        },
    )
    result = orchestrator.handle_message(task_msg)
    request_id = result.approval_request_id
    assert request_id is not None

    approve_msg = InboundMessage(
        id="approve_breadcrumb_1",
        sender="+15551234567",
        text=f"approve {request_id}",
        received_at="2026-02-16T12:05:00Z",
        is_from_me=False,
    )
    orchestrator.handle_message(approve_msg)

    assert len(notes_egress.appended) == 1
    assert notes_egress.appended[0]["note_id"] == "x-coredata://NOTE123"
    assert "Approved in iMessage" in notes_egress.appended[0]["result_text"]


def test_calendar_post_approval_annotates_event():
    """Regression: calendar_egress.annotate_event() must be called (not write_result)."""
    class FakeCalendarEgress:
        def __init__(self):
            self.annotated = []

        def annotate_event(self, event_id, result_text):
            self.annotated.append({"event_id": event_id, "result_text": result_text})
            return True

    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()
    cal_egress = FakeCalendarEgress()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
        calendar_egress=cal_egress,
    )

    task_msg = InboundMessage(
        id="cal_task_1",
        sender="+15551234567",
        text="task: deploy service",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
        context={
            "channel": "calendar",
            "event_id": "EVT-ABC-123",
            "event_summary": "Deploy service",
            "calendar_name": "codex-task",
        },
    )

    result = orchestrator.handle_message(task_msg)
    request_id = result.approval_request_id

    approve_msg = InboundMessage(
        id="approve_cal_1",
        sender="+15551234567",
        text=f"approve {request_id}",
        received_at="2026-02-16T12:05:00Z",
        is_from_me=False,
    )
    orchestrator.handle_message(approve_msg)

    assert len(cal_egress.annotated) == 1
    assert cal_egress.annotated[0]["event_id"] == "EVT-ABC-123"
    assert "[Apple Flow Result]" in cal_egress.annotated[0]["result_text"]


def test_note_context_key_note_title_is_used():
    """Regression: source_context should read note_title not note_name from context."""
    from conftest import FakeConnector, FakeEgress, FakeStore

    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
    )

    msg = InboundMessage(
        id="note_ctx_1",
        sender="+15551234567",
        text="task: write tests",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
        context={
            "channel": "notes",
            "note_id": "x-coredata://NOTE456",
            "note_title": "Write tests",   # ingress sets note_title
            "folder_name": "codex-task",
        },
    )

    result = orchestrator.handle_message(msg)
    store.get_run(result.run_id)
    src = store.get_run_source_context(result.run_id)
    assert src is not None
    assert src["note_name"] == "Write tests"   # orchestrator stores it as note_name


def test_calendar_context_key_event_summary_is_used():
    """Regression: source_context should read event_summary not event_name from context."""
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
    )

    msg = InboundMessage(
        id="cal_ctx_1",
        sender="+15551234567",
        text="task: run backups",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
        context={
            "channel": "calendar",
            "event_id": "EVT-XYZ",
            "event_summary": "Run backups",   # ingress sets event_summary
            "calendar_name": "codex-task",
        },
    )

    result = orchestrator.handle_message(msg)
    src = store.get_run_source_context(result.run_id)
    assert src is not None
    assert src["event_name"] == "Run backups"   # orchestrator stores it as event_name


# --- Natural Language UX tests ---


def _make_orchestrator(**kwargs):
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()
    defaults = dict(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
    )
    defaults.update(kwargs)
    orch = RelayOrchestrator(**defaults)
    return orch, connector, egress, store


def test_natural_language_chat_without_prefix():
    """Bare message processed when require_chat_prefix=False."""
    orch, connector, egress, _ = _make_orchestrator(require_chat_prefix=False)

    msg = InboundMessage(
        id="nl_1",
        sender="+15551234567",
        text="what's in this repo?",
        received_at="2026-02-18T10:00:00Z",
        is_from_me=False,
    )
    result = orch.handle_message(msg)
    assert result.kind is CommandKind.CHAT
    assert result.response == "assistant-response"
    assert connector.turns
    assert egress.messages


def test_natural_language_mutating_auto_promotes():
    """A bare mutating message enters the approval workflow without task: prefix."""
    orch, connector, egress, store = _make_orchestrator(require_chat_prefix=False)

    msg = InboundMessage(
        id="nl_2",
        sender="+15551234567",
        text="create a Python script to parse CSV files",
        received_at="2026-02-18T10:00:00Z",
        is_from_me=False,
    )
    result = orch.handle_message(msg)
    assert result.kind is CommandKind.TASK
    assert result.approval_request_id is not None
    assert any("Here's my plan" in text for _, text in egress.messages)


def test_mail_channel_mutating_chat_does_not_auto_promote():
    """Mail channel uses explicit task:/project: for approval-required actions."""
    orch, connector, egress, _ = _make_orchestrator(require_chat_prefix=False)

    msg = InboundMessage(
        id="nl_mail_1",
        sender="user@example.com",
        text="create a Python script to parse CSV files",
        received_at="2026-02-18T10:00:00Z",
        is_from_me=False,
        context={"channel": "mail"},
    )
    result = orch.handle_message(msg)
    assert result.kind is CommandKind.CHAT
    assert result.approval_request_id is None
    assert connector.turns
    assert egress.messages


def test_mail_channel_explicit_task_still_requires_approval():
    orch, _, egress, _ = _make_orchestrator(require_chat_prefix=False)

    msg = InboundMessage(
        id="nl_mail_2",
        sender="user@example.com",
        text="task: create a Python script to parse CSV files",
        received_at="2026-02-18T10:00:00Z",
        is_from_me=False,
        context={"channel": "mail"},
    )
    result = orch.handle_message(msg)
    assert result.kind is CommandKind.TASK
    assert result.approval_request_id is not None


def test_task_approval_flow_includes_attachment_block_in_planner_and_executor(tmp_path):
    attachment = tmp_path / "notes.txt"
    attachment.write_text("deploy checklist: 1) backup 2) migrate", encoding="utf-8")

    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()
    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
        enable_attachments=True,
        attachment_processor=AttachmentProcessor(),
    )

    msg = InboundMessage(
        id="att_task_1",
        sender="+15551234567",
        text="task: deploy service",
        received_at="2026-03-02T12:00:00Z",
        is_from_me=False,
        context={
            "attachments": [
                {
                    "filename": "notes.txt",
                    "mime_type": "text/plain",
                    "path": str(attachment),
                    "size_bytes": "64",
                }
            ]
        },
    )
    result = orchestrator.handle_message(msg)
    assert result.approval_request_id is not None
    assert "Attached files (processed):" in connector.turns[0][1]
    assert "deploy checklist" in connector.turns[0][1]

    source_context = store.get_run_source_context(result.run_id)
    assert source_context is not None
    assert "attachment_prompt_block" in source_context
    assert "notes.txt" in source_context["attachment_prompt_block"]

    approve_msg = InboundMessage(
        id="att_task_2",
        sender="+15551234567",
        text=f"approve {result.approval_request_id}",
        received_at="2026-03-02T12:01:00Z",
        is_from_me=False,
    )
    orchestrator.handle_message(approve_msg)
    assert "Attached files (processed):" in connector.turns[1][1]
    assert "deploy checklist" in connector.turns[1][1]
    assert any("Here's my plan" in text for _, text in egress.messages)


def test_personality_prompt_injected():
    """Custom personality_prompt is stored on the orchestrator and passed to the connector."""
    custom_prompt = "You are a pirate. Arr."
    orch, connector, egress, _ = _make_orchestrator(
        require_chat_prefix=False,
        personality_prompt=custom_prompt,
    )
    assert orch.personality_prompt == custom_prompt

    msg = InboundMessage(
        id="nl_3",
        sender="+15551234567",
        text="tell me about tides",
        received_at="2026-02-18T10:00:00Z",
        is_from_me=False,
    )
    result = orch.handle_message(msg)
    assert result.kind is CommandKind.CHAT
    assert connector.turns


def test_relay_prefix_stripped_in_natural_mode():
    """relay: prefix still works in natural mode; prefix is stripped before routing."""
    orch, connector, egress, _ = _make_orchestrator(
        require_chat_prefix=False,
        chat_prefix="relay:",
    )

    msg = InboundMessage(
        id="nl_4",
        sender="+15551234567",
        text="relay: tell me a joke",
        received_at="2026-02-18T10:00:00Z",
        is_from_me=False,
    )
    result = orch.handle_message(msg)
    assert result.kind is CommandKind.CHAT
    # Payload should have relay: stripped; connector should have received the bare message
    assert connector.turns
    sent_prompt = connector.turns[0][1]
    assert "relay:" not in sent_prompt.lower()


def test_approve_bare_word_still_works():
    """approve <id> works without any prefix in natural mode."""
    orch, connector, egress, store = _make_orchestrator(require_chat_prefix=False)

    # First create an approval via task:
    task_msg = InboundMessage(
        id="nl_5a",
        sender="+15551234567",
        text="task: write a hello world script",
        received_at="2026-02-18T10:00:00Z",
        is_from_me=False,
    )
    result = orch.handle_message(task_msg)
    request_id = result.approval_request_id
    assert request_id is not None

    # Now approve it bare-word (no prefix)
    approve_msg = InboundMessage(
        id="nl_5b",
        sender="+15551234567",
        text=f"approve {request_id}",
        received_at="2026-02-18T10:05:00Z",
        is_from_me=False,
    )
    approval_result = orch.handle_message(approve_msg)
    assert approval_result.kind is CommandKind.APPROVE
