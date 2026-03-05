from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from conftest import FakeConnector, FakeStore

from apple_flow.healer_memory import HealerMemoryService
from apple_flow.healer_runner import HealerRunner
from apple_flow.healer_verifier import HealerVerifier


def test_healer_memory_records_success_and_failure_lessons():
    store = FakeStore()
    memory = HealerMemoryService(store, enabled=True)
    issue = SimpleNamespace(issue_id="501", title="Fix store race", body="Touches src/apple_flow/store.py")

    memory.maybe_record_lesson(
        issue=issue,
        attempt_id="hat_success",
        final_state="pr_open",
        predicted_lock_set=["path:src/apple_flow/store.py"],
        actual_diff_set=["src/apple_flow/store.py"],
        test_summary={"targeted_tests": ["tests/test_store.py"]},
        verifier_summary={"passed": True, "summary": "Looks good"},
        failure_class="",
        failure_reason="",
    )
    memory.maybe_record_lesson(
        issue=issue,
        attempt_id="hat_failure",
        final_state="failed",
        predicted_lock_set=["path:src/apple_flow/store.py"],
        actual_diff_set=[],
        test_summary={"targeted_tests": ["tests/test_store.py"]},
        verifier_summary={},
        failure_class="tests_failed",
        failure_reason="pytest failed",
    )

    lessons = store.list_healer_lessons()
    assert len(lessons) == 2
    assert {lesson["outcome"] for lesson in lessons} == {"success", "failure"}
    assert any(lesson["guardrail"]["failure_class"] == "tests_failed" for lesson in lessons)


def test_healer_memory_retrieval_prefers_scope_overlap_and_marks_use():
    store = FakeStore()
    memory = HealerMemoryService(store, enabled=True)
    issue = SimpleNamespace(issue_id="502", title="Repair parser edge case", body="src/apple_flow/store.py")

    memory.maybe_record_lesson(
        issue=issue,
        attempt_id="hat_scope",
        final_state="pr_pending_approval",
        predicted_lock_set=["path:src/apple_flow/store.py"],
        actual_diff_set=["src/apple_flow/store.py"],
        test_summary={"targeted_tests": ["tests/test_store.py"]},
        verifier_summary={"passed": True, "summary": "pass"},
        failure_class="",
        failure_reason="",
    )
    memory.maybe_record_lesson(
        issue=SimpleNamespace(issue_id="503", title="Fix unrelated docs issue", body="README.md"),
        attempt_id="hat_other",
        final_state="pr_open",
        predicted_lock_set=["path:README.md"],
        actual_diff_set=["README.md"],
        test_summary={},
        verifier_summary={"passed": True, "summary": "pass"},
        failure_class="",
        failure_reason="",
    )

    context = memory.build_prompt_context(
        issue_text="Parser bug in src/apple_flow/store.py",
        predicted_lock_set=["path:src/apple_flow/store.py"],
    )

    assert "Relevant prior healer lessons:" in context
    assert "store.py" in context
    used = [lesson for lesson in store.healer_lessons if lesson["use_count"] > 0]
    assert len(used) == 1


def test_healer_runner_includes_learned_context_in_prompt(tmp_path):
    connector = FakeConnector()
    runner = HealerRunner(connector=connector, timeout_seconds=30)
    workspace = Path(tmp_path)

    result = runner.run_attempt(
        issue_id="600",
        issue_title="Fix issue",
        issue_body="Body",
        learned_context="Relevant prior healer lessons:\n- Keep changes small.",
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert "Keep changes small." in connector.turns[0][1]


def test_healer_verifier_includes_learned_context_in_prompt():
    connector = FakeConnector()
    verifier = HealerVerifier(connector=connector)

    verifier.verify(
        issue_id="601",
        issue_title="Fix verifier issue",
        issue_body="Body",
        diff_paths=["src/apple_flow/store.py"],
        test_summary={"full_exit_code": 0},
        proposer_output="diff --git a/x b/x",
        learned_context="Relevant prior healer lessons:\n- Preserve verified behavior.",
    )

    assert "Preserve verified behavior." in connector.turns[0][1]
