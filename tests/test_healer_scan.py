from __future__ import annotations

from pathlib import Path

from apple_flow.healer_scan import FlowHealerScanner, ScanFinding


class _FakeTracker:
    def __init__(self) -> None:
        self.enabled = True
        self.created: list[dict[str, object]] = []

    def find_open_issue_by_fingerprint(self, _fingerprint: str):
        return None

    def create_issue(self, *, title: str, body: str, labels: list[str]):
        number = 100 + len(self.created)
        issue = {"number": number, "html_url": f"https://github.com/o/r/issues/{number}", "title": title}
        self.created.append({"title": title, "body": body, "labels": labels, "issue": issue})
        return issue


def test_extract_failed_pytest_selectors():
    output = """
===================== FAILURES =====================
FAILED tests/test_a.py::test_alpha - AssertionError: nope
FAILED tests/test_b.py::test_beta - ValueError: bad
2 failed, 42 passed in 1.23s
"""
    selectors = FlowHealerScanner._extract_failed_pytest_selectors(output)
    assert selectors == ["tests/test_a.py::test_alpha", "tests/test_b.py::test_beta"]


def test_run_scan_creates_issues_over_threshold(monkeypatch, fake_store):
    tracker = _FakeTracker()
    scanner = FlowHealerScanner(
        repo_path=Path("/tmp"),
        store=fake_store,
        tracker=tracker,
        severity_threshold="medium",
        max_issues_per_run=5,
        default_labels=["healer:ready", "kind:scan"],
        enable_issue_creation=True,
    )

    def fake_harness(_check_failures):
        return [
            ScanFinding(
                fingerprint="fp_h1",
                scan_type="harness",
                severity="high",
                title="Harness eval failing: approval_bypass",
                body="body",
                payload={"eval_id": "approval_bypass"},
            )
        ]

    def fake_pytest(_check_failures):
        return [
            ScanFinding(
                fingerprint="fp_p1",
                scan_type="pytest",
                severity="high",
                title="Test failing: tests/test_x.py::test_y",
                body="body",
                payload={"selector": "tests/test_x.py::test_y"},
            )
        ]

    monkeypatch.setattr(scanner, "_run_harness_eval", fake_harness)
    monkeypatch.setattr(scanner, "_run_pytest_suite", fake_pytest)
    summary = scanner.run_scan(dry_run=False)

    assert summary["findings_total"] == 2
    assert len(summary["created_issues"]) == 2
    assert tracker.created[0]["labels"] == ["healer:ready", "kind:scan"]
    assert "flow-healer-fingerprint" in str(tracker.created[0]["body"])


def test_run_scan_dedupes_existing_open_issue(monkeypatch, fake_store):
    class _DedupTracker(_FakeTracker):
        def find_open_issue_by_fingerprint(self, fingerprint: str):
            if fingerprint == "fp_existing":
                return {"number": 44, "html_url": "https://github.com/o/r/issues/44"}
            return None

    tracker = _DedupTracker()
    scanner = FlowHealerScanner(
        repo_path=Path("/tmp"),
        store=fake_store,
        tracker=tracker,
        severity_threshold="medium",
        max_issues_per_run=5,
        default_labels=["healer:ready"],
        enable_issue_creation=True,
    )

    def fake_harness(_check_failures):
        return [
            ScanFinding(
                fingerprint="fp_existing",
                scan_type="harness",
                severity="high",
                title="Harness eval failing: retry_recovery",
                body="body",
                payload={},
            )
        ]

    monkeypatch.setattr(scanner, "_run_harness_eval", fake_harness)
    monkeypatch.setattr(scanner, "_run_pytest_suite", lambda _check_failures: [])
    summary = scanner.run_scan(dry_run=False)

    assert summary["deduped_count"] == 1
    assert summary["created_issues"] == []
    finding = fake_store.get_scan_finding("fp_existing")
    assert finding is not None
    assert finding["issue_number"] == 44
