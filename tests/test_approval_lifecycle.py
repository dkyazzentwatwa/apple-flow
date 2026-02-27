"""Approval lifecycle reliability and checkpoint/resume tests."""

from dataclasses import dataclass, field

from conftest import FakeEgress, FakeStore

from apple_flow.models import InboundMessage
from apple_flow.orchestrator import RelayOrchestrator


@dataclass
class SequenceConnector:
    """Connector with deterministic planner/executor outputs."""

    created: list[str] = field(default_factory=list)
    turns: list[tuple[str, str]] = field(default_factory=list)
    executor_outputs: list[str] = field(default_factory=list)
    raise_on_executor: bool = False
    executor_attempts: int = 0

    def get_or_create_thread(self, sender: str) -> str:
        self.created.append(sender)
        return "thread_approval"

    def reset_thread(self, sender: str) -> str:
        return "thread_reset"

    def run_turn(self, thread_id: str, prompt: str) -> str:
        self.turns.append((thread_id, prompt))
        if "planner mode" in prompt:
            return "PLAN: execute task safely"
        if "verifier mode" in prompt:
            return "VERIFIED"
        if "executor mode" in prompt:
            self.executor_attempts += 1
            if self.raise_on_executor:
                raise RuntimeError("executor crashed")
            if self.executor_outputs:
                idx = min(self.executor_attempts - 1, len(self.executor_outputs) - 1)
                return self.executor_outputs[idx]
            return "assistant-response"
        return "assistant-response"

    def ensure_started(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


@dataclass
class StreamingProgressConnector(SequenceConnector):
    stream_calls: list[tuple[str, str]] = field(default_factory=list)

    def run_turn_streaming(self, thread_id: str, prompt: str, on_progress=None) -> str:
        self.stream_calls.append((thread_id, prompt))
        if on_progress:
            on_progress("step 1: starting\n")
            on_progress("step 2: working\n")
        self.executor_attempts += 1
        return "stream-final-result"


class FailOnSubstringEgress(FakeEgress):
    """Egress that fails when a specific substring appears."""

    def __init__(self, failure_substring: str) -> None:
        super().__init__()
        self.failure_substring = failure_substring

    def send(self, recipient: str, text: str) -> None:
        self.messages.append((recipient, text))
        if self.failure_substring and self.failure_substring in text:
            raise RuntimeError("egress failure")


@dataclass
class CapturingRunExecutor:
    queued: list[dict[str, str]] = field(default_factory=list)

    def enqueue(
        self,
        *,
        run_id: str,
        sender: str,
        request_id: str,
        attempt: int,
        extra_instructions: str,
        approval_sender: str,
        plan_summary: str,
        phase: str = "executor",
    ) -> str:
        self.queued.append(
            {
                "run_id": run_id,
                "sender": sender,
                "request_id": request_id,
                "attempt": str(attempt),
                "extra_instructions": extra_instructions,
                "approval_sender": approval_sender,
                "plan_summary": plan_summary,
                "phase": phase,
            }
        )
        return "job_123"


def _make_orchestrator(
    connector,
    egress=None,
    store=None,
    *,
    enable_progress_streaming=False,
    progress_update_interval_seconds=30.0,
    checkpoint_on_timeout=True,
    max_resume_attempts=5,
):
    return RelayOrchestrator(
        connector=connector,
        egress=egress or FakeEgress(),
        store=store or FakeStore(),
        allowed_workspaces=["/workspace/default"],
        default_workspace="/workspace/default",
        require_chat_prefix=False,
        enable_progress_streaming=enable_progress_streaming,
        progress_update_interval_seconds=progress_update_interval_seconds,
        checkpoint_on_timeout=checkpoint_on_timeout,
        max_resume_attempts=max_resume_attempts,
    )


def _create_task_and_request_id(orch: RelayOrchestrator) -> tuple[str, str]:
    task_msg = InboundMessage(
        id="task_1",
        sender="+15551234567",
        text="task: ship it",
        received_at="2026-02-17T12:00:00Z",
        is_from_me=False,
    )
    task_result = orch.handle_message(task_msg)
    assert task_result.run_id is not None
    assert task_result.approval_request_id is not None
    return task_result.run_id, task_result.approval_request_id


def test_connector_exception_after_approval_marks_failed_and_notifies():
    connector = SequenceConnector(raise_on_executor=True)
    store = FakeStore()
    egress = FakeEgress()
    orch = _make_orchestrator(connector=connector, egress=egress, store=store)
    run_id, request_id = _create_task_and_request_id(orch)

    approve_msg = InboundMessage(
        id="approve_1",
        sender="+15551234567",
        text=f"approve {request_id}",
        received_at="2026-02-17T12:01:00Z",
        is_from_me=False,
    )
    result = orch.handle_message(approve_msg)

    assert result.run_id == run_id
    assert "internal error" in (result.response or "").lower()
    assert store.get_run(run_id)["state"] == "failed"
    assert any("internal error" in text.lower() for _, text in egress.messages)
    assert any(
        event["run_id"] == run_id and event["event_type"] == "execution_failed"
        for event in store.events
    )


def test_final_send_failure_does_not_abort_completed_run():
    connector = SequenceConnector(executor_outputs=["assistant-response"])
    store = FakeStore()
    egress = FailOnSubstringEgress("assistant-response")
    orch = _make_orchestrator(connector=connector, egress=egress, store=store)
    run_id, request_id = _create_task_and_request_id(orch)

    approve_msg = InboundMessage(
        id="approve_2",
        sender="+15551234567",
        text=f"approve {request_id}",
        received_at="2026-02-17T12:01:00Z",
        is_from_me=False,
    )
    result = orch.handle_message(approve_msg)

    assert result.response == "assistant-response"
    assert store.get_run(run_id)["state"] == "completed"
    assert any(
        event["run_id"] == run_id and event["event_type"] == "completed"
        for event in store.events
    )


def test_progress_send_failure_does_not_abort_execution():
    connector = StreamingProgressConnector()
    store = FakeStore()
    egress = FailOnSubstringEgress("[Progress]")
    orch = _make_orchestrator(
        connector=connector,
        egress=egress,
        store=store,
        enable_progress_streaming=True,
        progress_update_interval_seconds=0.0,
    )
    run_id, request_id = _create_task_and_request_id(orch)

    approve_msg = InboundMessage(
        id="approve_3",
        sender="+15551234567",
        text=f"approve {request_id}",
        received_at="2026-02-17T12:01:00Z",
        is_from_me=False,
    )
    result = orch.handle_message(approve_msg)

    assert result.response == "stream-final-result"
    assert store.get_run(run_id)["state"] == "completed"
    assert len(connector.stream_calls) == 1


def test_timeout_creates_checkpoint_and_resume_continues_same_run():
    connector = SequenceConnector(executor_outputs=["timed out after 300s", "done after resume"])
    store = FakeStore()
    egress = FakeEgress()
    orch = _make_orchestrator(
        connector=connector,
        egress=egress,
        store=store,
        checkpoint_on_timeout=True,
        max_resume_attempts=5,
    )
    run_id, first_request_id = _create_task_and_request_id(orch)

    first_approve = InboundMessage(
        id="approve_4",
        sender="+15551234567",
        text=f"approve {first_request_id}",
        received_at="2026-02-17T12:01:00Z",
        is_from_me=False,
    )
    first_result = orch.handle_message(first_approve)

    assert first_result.run_id == run_id
    assert first_result.approval_request_id is not None
    assert first_result.approval_request_id != first_request_id
    assert store.get_run(run_id)["state"] == "awaiting_approval"
    assert "checkpoint" in (first_result.response or "").lower()

    checkpoint_request_id = first_result.approval_request_id
    resume_approve = InboundMessage(
        id="approve_5",
        sender="+15551234567",
        text=f"approve {checkpoint_request_id} continue with cached token",
        received_at="2026-02-17T12:02:00Z",
        is_from_me=False,
    )
    resume_result = orch.handle_message(resume_approve)

    assert resume_result.run_id == run_id
    assert "done after resume" in (resume_result.response or "")


def test_execution_prompt_includes_user_requested_mail_labels():
    connector = SequenceConnector(executor_outputs=["done"])
    store = FakeStore()
    egress = FakeEgress()
    orch = _make_orchestrator(connector=connector, egress=egress, store=store)

    task_msg = InboundMessage(
        id="task_mail_labels",
        sender="+15551234567",
        text="task: search unread emails and triage. labels: Focus, Noise, Action, Delete",
        received_at="2026-02-17T12:00:00Z",
        is_from_me=False,
    )
    task_result = orch.handle_message(task_msg)
    assert task_result.approval_request_id is not None

    approve_msg = InboundMessage(
        id="approve_mail_labels",
        sender="+15551234567",
        text=f"approve {task_result.approval_request_id}",
        received_at="2026-02-17T12:01:00Z",
        is_from_me=False,
    )
    orch.handle_message(approve_msg)

    exec_prompts = [prompt for _, prompt in connector.turns if "executor mode" in prompt]
    assert exec_prompts, "expected at least one executor prompt"
    assert "When triaging Apple Mail, only use these labels: Focus, Noise, Action, Delete." in exec_prompts[0]
    assert store.get_run(task_result.run_id)["state"] == "completed"


def test_repeated_timeout_honors_max_resume_attempts_and_fails():
    connector = SequenceConnector(executor_outputs=["timed out", "timed out", "timed out"])
    store = FakeStore()
    orch = _make_orchestrator(
        connector=connector,
        store=store,
        checkpoint_on_timeout=True,
        max_resume_attempts=2,
    )
    run_id, first_request_id = _create_task_and_request_id(orch)

    first_approve = InboundMessage(
        id="approve_6",
        sender="+15551234567",
        text=f"approve {first_request_id}",
        received_at="2026-02-17T12:01:00Z",
        is_from_me=False,
    )
    first_result = orch.handle_message(first_approve)
    assert first_result.approval_request_id is not None

    second_approve = InboundMessage(
        id="approve_7",
        sender="+15551234567",
        text=f"approve {first_result.approval_request_id}",
        received_at="2026-02-17T12:02:00Z",
        is_from_me=False,
    )
    second_result = orch.handle_message(second_approve)

    assert "execution failed" in (second_result.response or "").lower()
    assert store.get_run(run_id)["state"] == "failed"
    assert store.count_run_events(run_id, "checkpoint_created") == 1
    assert store.count_run_events(run_id, "execution_started") == 2
    assert store.list_pending_approvals() == []


def test_approve_enqueues_background_execution_when_executor_attached():
    connector = SequenceConnector(executor_outputs=["should-not-run-inline"])
    store = FakeStore()
    egress = FakeEgress()
    orch = _make_orchestrator(connector=connector, egress=egress, store=store)
    run_executor = CapturingRunExecutor()
    orch.set_run_executor(run_executor)

    run_id, request_id = _create_task_and_request_id(orch)
    approve_msg = InboundMessage(
        id="approve_async_1",
        sender="+15551234567",
        text=f"approve {request_id} with extra detail",
        received_at="2026-02-17T12:01:00Z",
        is_from_me=False,
    )
    result = orch.handle_message(approve_msg)

    assert result.run_id == run_id
    assert "Queued execution" in (result.response or "")
    assert f"run `{run_id}`" in (result.response or "")
    assert store.get_run(run_id)["state"] == "queued"
    assert len(run_executor.queued) == 1
    queued = run_executor.queued[0]
    assert queued["request_id"] == request_id
    assert queued["extra_instructions"] == "with extra detail"
    # No inline executor turns should happen in the approve path.
    assert connector.executor_attempts == 0
