from __future__ import annotations
from pathlib import Path

from apple_flow.healer_tracker import GitHubHealerTracker


def test_find_open_issue_by_fingerprint_uses_search(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert method == "GET"
        assert "/search/issues?q=" in path
        return {
            "items": [
                {
                    "number": 12,
                    "html_url": "https://github.com/owner/repo/issues/12",
                    "title": "sample",
                }
            ]
        }

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    result = tracker.find_open_issue_by_fingerprint("abc123")
    assert result is not None
    assert result["number"] == 12


def test_create_issue_posts_payload(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert path == "/repos/owner/repo/issues"
        assert method == "POST"
        assert body is not None
        assert body["labels"] == ["healer:ready", "kind:scan"]
        return {"number": 77, "html_url": "https://github.com/owner/repo/issues/77", "state": "open"}

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    issue = tracker.create_issue(
        title="Test failing: tests/test_a.py::test_x",
        body="details",
        labels=["healer:ready", "kind:scan"],
    )
    assert issue is not None
    assert issue["number"] == 77


def test_tracker_loads_github_token_from_project_env(monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("GITHUB_TOKEN=github_pat_testtoken123\n", encoding="utf-8")
    tracker = GitHubHealerTracker(repo_path=tmp_path)
    tracker.repo_slug = "owner/repo"

    assert tracker.token == "github_pat_testtoken123"


def test_enabled_when_gh_auth_is_available_without_token(monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    tracker = GitHubHealerTracker(repo_path=tmp_path, token="")
    tracker.repo_slug = "owner/repo"
    tracker._explicit_token = ""
    tracker._env_token = ""
    tracker._dotenv_token = ""
    tracker.token = ""
    monkeypatch.setattr(tracker, "_gh_auth_ok", lambda: True)

    assert tracker.enabled is True
    assert tracker.background_auth_available is False
    assert tracker.auth_source == "gh_cli"


def test_request_json_prefers_http_when_token_is_present(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"
    monkeypatch.setattr(
        tracker,
        "_request_json_via_http",
        lambda path, *, method="GET", body=None: {"source": "http", "path": path, "method": method},
    )
    monkeypatch.setattr(
        tracker,
        "_request_json_via_gh",
        lambda path, *, method="GET", body=None: (_ for _ in ()).throw(AssertionError("gh fallback should not run")),
    )

    payload = tracker._request_json("/repos/owner/repo/issues")

    assert payload["source"] == "http"


def test_request_json_falls_back_to_gh_when_http_fails(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"
    monkeypatch.setattr(tracker, "_gh_auth_ok", lambda: True)
    monkeypatch.setattr(tracker, "_request_json_via_http", lambda path, *, method="GET", body=None: None)
    monkeypatch.setattr(
        tracker,
        "_request_json_via_gh",
        lambda path, *, method="GET", body=None: {"source": "gh", "path": path, "method": method},
    )

    payload = tracker._request_json("/repos/owner/repo/issues")

    assert payload["source"] == "gh"


def test_auth_source_prefers_dotenv_when_env_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("GITHUB_TOKEN=github_pat_from_dotenv\n", encoding="utf-8")

    tracker = GitHubHealerTracker(repo_path=tmp_path)
    tracker.repo_slug = "owner/repo"

    assert tracker.auth_source == "token_dotenv"
    assert tracker.background_auth_available is True
