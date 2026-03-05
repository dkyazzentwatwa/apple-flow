from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from .healer_tracker import GitHubHealerTracker

logger = logging.getLogger("apple_flow.healer_scan")

_SEVERITY_ORDER = {
    "low": 10,
    "medium": 20,
    "high": 30,
    "critical": 40,
}


@dataclass(slots=True, frozen=True)
class ScanFinding:
    fingerprint: str
    scan_type: str
    severity: str
    title: str
    body: str
    payload: dict[str, Any]


class FlowHealerScanner:
    """Runs deterministic repo checks and optionally opens deduped GitHub issues."""

    def __init__(
        self,
        *,
        repo_path: Path,
        store: Any,
        tracker: GitHubHealerTracker | None,
        severity_threshold: str,
        max_issues_per_run: int,
        default_labels: list[str],
        enable_issue_creation: bool,
        lightweight: bool = False,
    ) -> None:
        self.repo_path = Path(repo_path).expanduser().resolve()
        self.store = store
        self.tracker = tracker
        self.severity_threshold = (severity_threshold or "medium").strip().lower()
        self.max_issues_per_run = max(1, int(max_issues_per_run))
        self.default_labels = [label.strip() for label in default_labels if label.strip()]
        self.enable_issue_creation = bool(enable_issue_creation)
        self.lightweight = bool(lightweight)

    def run_scan(self, *, dry_run: bool) -> dict[str, Any]:
        run_id = f"scan_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        if hasattr(self.store, "create_scan_run"):
            self.store.create_scan_run(run_id=run_id, dry_run=dry_run)

        findings: list[ScanFinding] = []
        check_failures: list[str] = []
        findings.extend(self._run_harness_eval(check_failures))
        if not self.lightweight:
            findings.extend(self._run_pytest_suite(check_failures))

        included: list[ScanFinding] = [
            finding for finding in findings if self._passes_threshold(finding.severity)
        ]
        created: list[dict[str, Any]] = []
        deduped = 0
        skipped_budget = 0

        for finding in included:
            existing = self.store.get_scan_finding(finding.fingerprint) if hasattr(self.store, "get_scan_finding") else None
            existing_issue_number = int(existing.get("issue_number") or 0) if existing else 0

            open_issue = None
            if self.tracker and self.tracker.enabled:
                open_issue = self.tracker.find_open_issue_by_fingerprint(finding.fingerprint)
                if open_issue:
                    deduped += 1
                    if hasattr(self.store, "upsert_scan_finding"):
                        self.store.upsert_scan_finding(
                            fingerprint=finding.fingerprint,
                            scan_type=finding.scan_type,
                            severity=finding.severity,
                            title=finding.title,
                            status="deduped_open",
                            payload=finding.payload,
                            issue_number=int(open_issue["number"]),
                        )
                    continue
            elif existing_issue_number:
                deduped += 1
                if hasattr(self.store, "upsert_scan_finding"):
                    self.store.upsert_scan_finding(
                        fingerprint=finding.fingerprint,
                        scan_type=finding.scan_type,
                        severity=finding.severity,
                        title=finding.title,
                        status="deduped_record",
                        payload=finding.payload,
                        issue_number=existing_issue_number,
                    )
                continue

            if not dry_run and self.enable_issue_creation:
                if len(created) >= self.max_issues_per_run:
                    skipped_budget += 1
                    if hasattr(self.store, "upsert_scan_finding"):
                        self.store.upsert_scan_finding(
                            fingerprint=finding.fingerprint,
                            scan_type=finding.scan_type,
                            severity=finding.severity,
                            title=finding.title,
                            status="skipped_budget",
                            payload=finding.payload,
                        )
                    continue
                if self.tracker and self.tracker.enabled:
                    labels = list(dict.fromkeys([*self.default_labels, "healer:ready"]))
                    created_issue = self.tracker.create_issue(
                        title=finding.title,
                        body=self._issue_body(finding),
                        labels=labels,
                    )
                    if created_issue:
                        created.append(created_issue)
                        if hasattr(self.store, "upsert_scan_finding"):
                            self.store.upsert_scan_finding(
                                fingerprint=finding.fingerprint,
                                scan_type=finding.scan_type,
                                severity=finding.severity,
                                title=finding.title,
                                status="open",
                                payload=finding.payload,
                                issue_number=int(created_issue["number"]),
                            )
                        continue

            if hasattr(self.store, "upsert_scan_finding"):
                self.store.upsert_scan_finding(
                    fingerprint=finding.fingerprint,
                    scan_type=finding.scan_type,
                    severity=finding.severity,
                    title=finding.title,
                    status="detected" if dry_run else "queued_manual",
                    payload=finding.payload,
                )

        summary = {
            "run_id": run_id,
            "dry_run": dry_run,
            "lightweight": self.lightweight,
            "findings_total": len(findings),
            "findings_over_threshold": len(included),
            "created_issues": created,
            "deduped_count": deduped,
            "skipped_budget_count": skipped_budget,
            "failed_checks": check_failures,
            "severity_threshold": self.severity_threshold,
        }
        if hasattr(self.store, "finish_scan_run"):
            self.store.finish_scan_run(run_id=run_id, status="completed", summary=summary)
        return summary

    def _run_harness_eval(self, check_failures: list[str]) -> list[ScanFinding]:
        with NamedTemporaryFile(prefix="flow-healer-harness-", suffix=".json", delete=False) as tmp:
            json_path = Path(tmp.name)

        cmd = ["python3", "scripts/harness_eval_pack.py", "--json-out", str(json_path)]
        proc = subprocess.run(
            cmd,
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
            check=False,
            timeout=1200,
        )
        findings: list[ScanFinding] = []
        report = self._read_json_file(json_path)
        json_path.unlink(missing_ok=True)

        if proc.returncode == 0:
            return findings

        check_failures.append("harness_eval_pack")
        for result in report.get("results", []):
            if not isinstance(result, dict) or bool(result.get("passed")):
                continue
            eval_id = str(result.get("eval_id") or "unknown")
            risk = str(result.get("risk") or "").strip()
            payload = {
                "eval_id": eval_id,
                "risk": risk,
                "selectors": result.get("selectors") or [],
                "kpis": result.get("kpis") or [],
                "output_tail": str(result.get("output_tail") or "")[-3000:],
                "returncode": int(result.get("returncode") or 1),
            }
            findings.append(
                ScanFinding(
                    fingerprint=self._fingerprint("harness", eval_id),
                    scan_type="harness",
                    severity="high",
                    title=f"Harness eval failing: {eval_id}",
                    body=(
                        f"Harness risk eval `{eval_id}` failed.\n\n"
                        f"Risk: {risk or 'n/a'}\n"
                        f"KPI tags: {', '.join(str(k) for k in payload['kpis']) or 'n/a'}\n\n"
                        "See payload for selectors + output tail."
                    ),
                    payload=payload,
                )
            )

        if findings:
            return findings
        fallback_tail = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()[-2000:]
        return [
            ScanFinding(
                fingerprint=self._fingerprint("harness", "harness_eval_pack_exit"),
                scan_type="harness",
                severity="high",
                title="Harness eval pack failed to run cleanly",
                body="Harness eval pack exited non-zero without parseable per-case failures.",
                payload={"output_tail": fallback_tail, "returncode": proc.returncode},
            )
        ]

    def _run_pytest_suite(self, check_failures: list[str]) -> list[ScanFinding]:
        cmd = ["pytest", "-q"]
        proc = subprocess.run(
            cmd,
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
            check=False,
            timeout=1800,
        )
        if proc.returncode == 0:
            return []

        check_failures.append("pytest")
        output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        selectors = self._extract_failed_pytest_selectors(output)
        findings: list[ScanFinding] = []
        if not selectors:
            return [
                ScanFinding(
                    fingerprint=self._fingerprint("pytest", "suite_failed"),
                    scan_type="pytest",
                    severity="high",
                    title="Pytest suite failed",
                    body="`pytest -q` returned non-zero without explicit FAILED test selectors.",
                    payload={"output_tail": output[-3000:], "returncode": proc.returncode},
                )
            ]

        for selector in selectors[:20]:
            findings.append(
                ScanFinding(
                    fingerprint=self._fingerprint("pytest", selector),
                    scan_type="pytest",
                    severity="high",
                    title=f"Test failing: {selector}",
                    body=(
                        "A CI-style local pytest scan found this failing selector.\n\n"
                        f"- Selector: `{selector}`\n"
                        "- Command: `pytest -q`\n"
                        "- Source: Flow Healer scan pipeline"
                    ),
                    payload={"selector": selector, "returncode": proc.returncode},
                )
            )
        return findings

    def _issue_body(self, finding: ScanFinding) -> str:
        payload_json = json.dumps(finding.payload, indent=2)
        return (
            f"{finding.body}\n\n"
            "### Automation Metadata\n"
            f"- scan_type: `{finding.scan_type}`\n"
            f"- severity: `{finding.severity}`\n"
            f"- flow-healer-fingerprint: `{finding.fingerprint}`\n\n"
            "```json\n"
            f"{payload_json}\n"
            "```\n"
        )

    def _passes_threshold(self, severity: str) -> bool:
        value = _SEVERITY_ORDER.get((severity or "").strip().lower(), _SEVERITY_ORDER["medium"])
        threshold = _SEVERITY_ORDER.get(self.severity_threshold, _SEVERITY_ORDER["medium"])
        return value >= threshold

    @staticmethod
    def _extract_failed_pytest_selectors(output: str) -> list[str]:
        selectors: list[str] = []
        for line in output.splitlines():
            stripped = line.strip()
            if not stripped.startswith("FAILED "):
                continue
            content = stripped[7:].strip()
            selector = content.split(" - ", 1)[0].strip()
            if selector and selector not in selectors:
                selectors.append(selector)
        return selectors

    @staticmethod
    def _fingerprint(scan_type: str, stable_input: str) -> str:
        digest = hashlib.sha256(f"{scan_type}:{stable_input}".encode("utf-8")).hexdigest()
        return digest[:24]

    @staticmethod
    def _read_json_file(path: Path) -> dict[str, Any]:
        try:
            raw = path.read_text(encoding="utf-8")
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return payload
            return {}
        except Exception:
            logger.warning("Could not read harness JSON report from %s", path)
            return {}
