from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

logger = logging.getLogger("apple_flow.healer_tracker")


@dataclass(slots=True, frozen=True)
class HealerIssue:
    issue_id: str
    repo: str
    title: str
    body: str
    author: str
    labels: list[str]
    priority: int
    html_url: str


@dataclass(slots=True, frozen=True)
class PullRequestResult:
    number: int
    state: str
    html_url: str


class GitHubHealerTracker:
    """Minimal GitHub issue + PR adapter for autonomous healer flows."""

    def __init__(self, *, repo_path: Path, token: str | None = None) -> None:
        self.repo_path = Path(repo_path).resolve()
        self._explicit_token = (token or "").strip()
        self._env_token = os.getenv("GITHUB_TOKEN", "").strip()
        self._dotenv_token = self._load_token_from_env_file().strip()
        self.token = (
            self._explicit_token
            or self._env_token
            or self._dotenv_token
        ).strip()
        self.repo_slug = self._infer_repo_slug(self.repo_path)
        self._gh_auth_ok_cache: bool | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.repo_slug and (self._gh_auth_ok() or self.token))

    @property
    def background_auth_available(self) -> bool:
        return bool(self.repo_slug and self.token)

    @property
    def auth_source(self) -> str:
        if self._explicit_token or self._env_token:
            return "token_env"
        if self._dotenv_token:
            return "token_dotenv"
        if self.repo_slug and self._gh_auth_ok():
            return "gh_cli"
        return "none"

    def list_ready_issues(
        self,
        *,
        required_labels: list[str],
        trusted_actors: list[str],
        limit: int = 20,
    ) -> list[HealerIssue]:
        if not self.enabled:
            return []
        labels_query = ",".join(sorted({label.strip() for label in required_labels if label.strip()}))
        payload = self._request_json(
            f"/repos/{self.repo_slug}/issues?state=open&per_page={int(max(1, limit))}"
            + (f"&labels={quote(labels_query)}" if labels_query else "")
        )
        trusted = {actor.strip().lower() for actor in trusted_actors if actor.strip()}
        out: list[HealerIssue] = []
        for item in payload if isinstance(payload, list) else []:
            if not isinstance(item, dict):
                continue
            if "pull_request" in item:
                continue
            author = str(((item.get("user") or {}).get("login")) or "").strip()
            if trusted and author.lower() not in trusted:
                continue
            label_names = [
                str((label or {}).get("name") or "").strip()
                for label in (item.get("labels") or [])
                if isinstance(label, dict)
            ]
            if required_labels and not all(req in label_names for req in required_labels):
                continue
            issue = HealerIssue(
                issue_id=str(item.get("number")),
                repo=self.repo_slug,
                title=str(item.get("title") or ""),
                body=str(item.get("body") or ""),
                author=author,
                labels=label_names,
                priority=self._priority_from_labels(label_names),
                html_url=str(item.get("html_url") or ""),
            )
            out.append(issue)
        return out

    def issue_has_label(self, *, issue_id: str, label: str) -> bool:
        if not self.enabled:
            return False
        payload = self._request_json(f"/repos/{self.repo_slug}/issues/{quote(issue_id)}")
        if not isinstance(payload, dict):
            return False
        labels = [
            str((entry or {}).get("name") or "").strip()
            for entry in (payload.get("labels") or [])
            if isinstance(entry, dict)
        ]
        return label in labels

    def find_open_issue_by_fingerprint(self, fingerprint: str) -> dict[str, Any] | None:
        if not self.enabled or not fingerprint.strip():
            return None
        query = (
            f"repo:{self.repo_slug} is:issue is:open "
            f"\"flow-healer-fingerprint: `{fingerprint.strip()}`\""
        )
        payload = self._request_json(
            f"/search/issues?q={quote(query)}&per_page=1"
        )
        if not isinstance(payload, dict):
            return None
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            return None
        item = items[0] if isinstance(items[0], dict) else {}
        number = int(item.get("number") or 0)
        if number <= 0:
            return None
        return {
            "number": number,
            "html_url": str(item.get("html_url") or ""),
            "title": str(item.get("title") or ""),
        }

    def create_issue(self, *, title: str, body: str, labels: list[str] | None = None) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        payload = self._request_json(
            f"/repos/{self.repo_slug}/issues",
            method="POST",
            body={
                "title": title,
                "body": body,
                "labels": labels or [],
            },
        )
        if not isinstance(payload, dict):
            return None
        number = int(payload.get("number") or 0)
        if number <= 0:
            return None
        return {
            "number": number,
            "html_url": str(payload.get("html_url") or ""),
            "state": str(payload.get("state") or "open"),
        }

    def open_or_update_pr(
        self,
        *,
        issue_id: str,
        branch: str,
        title: str,
        body: str,
        base: str = "main",
    ) -> PullRequestResult | None:
        if not self.enabled:
            return None

        existing = self._request_json(
            f"/repos/{self.repo_slug}/pulls?state=open&head={quote(self.repo_slug.split('/')[0] + ':' + branch)}"
        )
        if isinstance(existing, list) and existing:
            pr = existing[0] if isinstance(existing[0], dict) else {}
            return PullRequestResult(
                number=int(pr.get("number") or 0),
                state=str(pr.get("state") or "open"),
                html_url=str(pr.get("html_url") or ""),
            )

        payload = self._request_json(
            f"/repos/{self.repo_slug}/pulls",
            method="POST",
            body={
                "title": title,
                "body": body,
                "head": branch,
                "base": base,
            },
        )
        if not isinstance(payload, dict):
            return None
        return PullRequestResult(
            number=int(payload.get("number") or 0),
            state=str(payload.get("state") or "open"),
            html_url=str(payload.get("html_url") or ""),
        )

    def get_pr_state(self, *, pr_number: int) -> str:
        if not self.enabled or pr_number <= 0:
            return ""
        payload = self._request_json(f"/repos/{self.repo_slug}/pulls/{int(pr_number)}")
        if not isinstance(payload, dict):
            return ""
        if bool(payload.get("merged")):
            return "merged"
        mergeable_state = str(payload.get("mergeable_state") or "")
        if mergeable_state == "dirty":
            return "conflict"
        return str(payload.get("state") or "")

    def _request_json(self, path: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
        if self.token:
            payload = self._request_json_via_http(path, method=method, body=body)
            if payload is not None:
                return payload
        if self._gh_auth_ok():
            payload = self._request_json_via_gh(path, method=method, body=body)
            if payload is not None:
                return payload
        return {}

    def _request_json_via_gh(self, path: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> Any | None:
        route = path.lstrip("/")
        if not route:
            return None

        cmd = [
            "gh",
            "api",
            route,
            "--method",
            method.upper(),
            "--header",
            "Accept: application/vnd.github+json",
        ]
        payload = None
        if body is not None:
            payload = json.dumps(body)
            cmd.extend(["--header", "Content-Type: application/json", "--input", "-"])

        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                input=payload,
                timeout=20,
            )
        except Exception as exc:
            logger.warning("gh api %s %s failed to start: %s", method, path, exc)
            return None

        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            logger.warning("gh api %s %s failed: %s", method, path, detail[:300])
            return None

        raw = (proc.stdout or "").strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("gh api returned non-JSON response for %s %s", method, path)
            return None

    def _request_json_via_http(self, path: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> Any | None:
        url = f"https://api.github.com{path}"
        data: bytes | None = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = Request(url, method=method, data=data)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "apple-flow-healer")
        req.add_header("Authorization", f"Bearer {self.token}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            logger.warning("GitHub API %s %s failed: %s", method, path, exc)
            return None
        except URLError as exc:
            logger.warning("GitHub API network error for %s %s: %s", method, path, exc)
            return None
        except json.JSONDecodeError:
            logger.warning("GitHub API returned non-JSON response for %s %s", method, path)
            return None

    def _gh_auth_ok(self) -> bool:
        if self._gh_auth_ok_cache is not None:
            return self._gh_auth_ok_cache
        if shutil.which("gh") is None:
            self._gh_auth_ok_cache = False
            return False
        try:
            proc = subprocess.run(
                ["gh", "auth", "status", "--hostname", "github.com"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            self._gh_auth_ok_cache = False
            return False
        self._gh_auth_ok_cache = proc.returncode == 0
        return self._gh_auth_ok_cache

    def _load_token_from_env_file(self) -> str:
        candidates = [
            Path.cwd() / ".env",
            self.repo_path / ".env",
            Path(__file__).resolve().parents[2] / ".env",
        ]
        for candidate in candidates:
            try:
                if not candidate.exists():
                    continue
                for line in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or not stripped.startswith("GITHUB_TOKEN="):
                        continue
                    return stripped.split("=", 1)[1].strip().strip('"').strip("'")
            except OSError:
                logger.debug("Failed reading .env for GitHub token at %s", candidate, exc_info=True)
        return ""

    @staticmethod
    def _priority_from_labels(labels: list[str]) -> int:
        lowered = {label.lower() for label in labels}
        if "severity:critical" in lowered or "priority:p0" in lowered:
            return 0
        if "priority:p1" in lowered:
            return 10
        if "priority:p2" in lowered:
            return 20
        return 100

    @staticmethod
    def _infer_repo_slug(repo_path: Path) -> str:
        try:
            proc = subprocess.run(
                ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode != 0:
                return ""
            raw = (proc.stdout or "").strip()
            # Supports https://github.com/owner/repo(.git) and git@github.com:owner/repo(.git)
            match = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?$", raw)
            if not match:
                return ""
            owner = match.group("owner").strip()
            repo = match.group("repo").strip()
            if not owner or not repo:
                return ""
            return f"{owner}/{repo}"
        except Exception:
            return ""
