"""Tests for AdminClient."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from apple_flow.admin_client import AdminClient


def _mock_response(json_data, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


# --- __init__ ---

def test_init_defaults():
    client = AdminClient()
    assert client.base_url == "http://127.0.0.1:8787"
    assert client.timeout == 10.0


def test_init_custom():
    client = AdminClient(base_url="http://localhost:9000/", timeout=5.0)
    assert client.base_url == "http://localhost:9000"  # trailing slash stripped
    assert client.timeout == 5.0


# --- pending_approvals ---

def test_pending_approvals_success():
    expected = [{"request_id": "req_1", "summary": "do stuff"}]
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = _mock_response(expected)

        client = AdminClient()
        result = client.pending_approvals()

    assert result == expected
    mock_client.get.assert_called_once_with("http://127.0.0.1:8787/approvals/pending")


def test_pending_approvals_error():
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = _mock_response({}, status_code=500)

        client = AdminClient()
        with pytest.raises(httpx.HTTPStatusError):
            client.pending_approvals()


# --- override_approval ---

def test_override_approval_success():
    expected = {"status": "approved"}
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = _mock_response(expected)

        client = AdminClient()
        result = client.override_approval("req_1", "approved")

    assert result == expected
    mock_client.post.assert_called_once_with(
        "http://127.0.0.1:8787/approvals/req_1/override",
        json={"status": "approved"},
    )


def test_override_approval_not_found():
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = _mock_response({}, status_code=404)

        client = AdminClient()
        with pytest.raises(httpx.HTTPStatusError):
            client.override_approval("bad_id", "approved")


# --- list_sessions ---

def test_list_sessions_success():
    expected = [{"sender": "+15551234567", "thread_id": "t1"}]
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = _mock_response(expected)

        client = AdminClient()
        result = client.list_sessions()

    assert result == expected
    mock_client.get.assert_called_once_with("http://127.0.0.1:8787/sessions")


# --- audit_events ---

def test_audit_events_default_limit():
    expected = [{"event_id": "e1", "event_type": "approved"}]
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = _mock_response(expected)

        client = AdminClient()
        result = client.audit_events()

    assert result == expected
    mock_client.get.assert_called_once_with(
        "http://127.0.0.1:8787/audit/events", params={"limit": 200}
    )


def test_audit_events_custom_limit():
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = _mock_response([])

        client = AdminClient()
        client.audit_events(limit=50)

    mock_client.get.assert_called_once_with(
        "http://127.0.0.1:8787/audit/events", params={"limit": 50}
    )


# --- health ---

def test_health_success():
    expected = {"status": "ok", "session_count": 1}
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = _mock_response(expected)

        client = AdminClient()
        result = client.health()

    assert result == expected
    mock_client.get.assert_called_once_with("http://127.0.0.1:8787/health")


def test_health_timeout():
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("timeout")

        client = AdminClient()
        with pytest.raises(httpx.TimeoutException):
            client.health()


def test_timeout_passed_to_client():
    """Verify timeout is forwarded to httpx.Client."""
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = _mock_response({})

        client = AdminClient(timeout=3.0)
        client.health()

    mock_client_cls.assert_called_once_with(timeout=3.0)
