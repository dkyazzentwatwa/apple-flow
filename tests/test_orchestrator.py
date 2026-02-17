"""Tests for the RelayOrchestrator."""

from conftest import FakeConnector, FakeEgress, FakeStore

from apple_flow.commanding import CommandKind
from apple_flow.models import InboundMessage
from apple_flow.orchestrator import RelayOrchestrator


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
    assert any("Approve with" in text for _, text in egress.messages)


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
            "list_name": "Codex Tasks",
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
    assert moved["source_list_name"] == "Codex Tasks"
    assert moved["archive_list_name"] == "Archive"
    assert "[Codex Result]" in moved["result_text"]


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
    assert "[Codex Result]" in moved["result_text"]


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
    assert "[Codex Result]" in cal_egress.annotated[0]["result_text"]


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
    run = store.get_run(result.run_id)
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
