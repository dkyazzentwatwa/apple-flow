#!/usr/bin/env python3
"""Run a focused harness risk-eval pack for Apple Flow."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class EvalCase:
    eval_id: str
    risk: str
    kpis: tuple[str, ...]
    selectors: tuple[str, ...]


EVAL_CASES: tuple[EvalCase, ...] = (
    EvalCase(
        eval_id="approval_bypass",
        risk="Mutating requests execute without explicit approval",
        kpis=("S1",),
        selectors=(
            "tests/test_orchestrator.py::test_task_command_creates_approval_request",
            "tests/test_orchestrator.py::test_natural_language_mutating_auto_promotes",
            "tests/test_orchestrator.py::test_mail_channel_mutating_chat_does_not_auto_promote",
        ),
    ),
    EvalCase(
        eval_id="cross_sender_approval",
        risk="Approvals accepted from a non-requester sender",
        kpis=("S2",),
        selectors=(
            "tests/test_approval_security.py::test_approval_sender_verification_blocks_different_sender",
            "tests/test_approval_security.py::test_deny_sender_verification_blocks_different_sender",
            "tests/test_approval_security.py::test_cross_gateway_mismatched_sender_still_rejected",
        ),
    ),
    EvalCase(
        eval_id="retry_recovery",
        risk="Retries/checkpoints do not recover or fail predictably",
        kpis=("R2",),
        selectors=(
            "tests/test_approval_lifecycle.py::test_timeout_creates_checkpoint_and_resume_continues_same_run",
            "tests/test_approval_lifecycle.py::test_repeated_timeout_honors_max_resume_attempts_and_fails",
            "tests/test_store.py::test_requeue_expired_run_jobs",
        ),
    ),
    EvalCase(
        eval_id="duplicate_suppression",
        risk="Duplicate outbound messages leak to recipients",
        kpis=("R3",),
        selectors=(
            "tests/test_egress_chunking.py::test_duplicate_suppression",
            "tests/test_egress_chunking.py::test_gc_recent_clears_old_fingerprints",
        ),
    ),
    EvalCase(
        eval_id="companion_noise_controls",
        risk="Companion proactive messaging exceeds noise guardrails",
        kpis=("Q2", "Q3"),
        selectors=(
            "tests/test_companion.py::TestRateLimiting::test_rate_limited_after_max",
            "tests/test_companion.py::TestRateLimiting::test_rate_limit_resets_new_hour",
            "tests/test_companion.py::TestQuietHours::test_overnight_inside_late",
        ),
    ),
)


def _run_eval_case(case: EvalCase, pytest_cmd: str) -> dict[str, object]:
    cmd = [pytest_cmd, "-q", *case.selectors]
    started = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    duration = round(time.perf_counter() - started, 3)
    combined_output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()

    return {
        "eval_id": case.eval_id,
        "risk": case.risk,
        "kpis": list(case.kpis),
        "selectors": list(case.selectors),
        "passed": proc.returncode == 0,
        "returncode": proc.returncode,
        "duration_seconds": duration,
        "output_tail": "\n".join(combined_output.splitlines()[-40:]),
    }


def _build_summary(results: list[dict[str, object]], total_duration: float) -> dict[str, object]:
    passed = sum(1 for result in results if bool(result["passed"]))
    failed = len(results) - passed
    return {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "duration_seconds": round(total_duration, 3),
        "pass_rate": round((passed / len(results)) * 100.0, 2) if results else 0.0,
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run harness engineering eval pack")
    parser.add_argument("--pytest-cmd", default="pytest", help="Pytest executable (default: pytest)")
    parser.add_argument("--json-out", default="", help="Optional output path for JSON report")
    parser.add_argument("--list", action="store_true", help="List eval cases and exit")
    args = parser.parse_args()

    if args.list:
        for case in EVAL_CASES:
            print(f"{case.eval_id}: {case.risk}")
            for selector in case.selectors:
                print(f"  - {selector}")
        return 0

    overall_started = time.perf_counter()
    results: list[dict[str, object]] = []

    print("Running harness eval pack...")
    for case in EVAL_CASES:
        result = _run_eval_case(case, args.pytest_cmd)
        status = "PASS" if result["passed"] else "FAIL"
        print(
            f"[{status}] {case.eval_id} "
            f"({result['duration_seconds']}s, KPIs={','.join(case.kpis)})"
        )
        if not result["passed"]:
            print(result["output_tail"])
        results.append(result)

    summary = _build_summary(results, time.perf_counter() - overall_started)
    report: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": summary,
        "results": results,
    }

    print(
        "Harness eval summary: "
        f"{summary['passed']}/{summary['total']} passed "
        f"({summary['pass_rate']}%) in {summary['duration_seconds']}s"
    )

    if args.json_out:
        output_path = Path(args.json_out)
        _write_json(output_path, report)
        print(f"Wrote JSON report: {output_path}")

    return 0 if int(summary["failed"]) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
