"""Tests for the `usage` command (ccusage integration)."""

import json
from unittest.mock import MagicMock, patch

from conftest import FakeConnector, FakeEgress, FakeStore

from apple_flow.commanding import CommandKind, parse_command
from apple_flow.models import InboundMessage
from apple_flow.orchestrator import RelayOrchestrator


def _make_orchestrator():
    return RelayOrchestrator(
        connector=FakeConnector(),
        egress=FakeEgress(),
        store=FakeStore(),
        allowed_workspaces=["/workspace/default"],
        default_workspace="/workspace/default",
        require_chat_prefix=False,
    )


def _msg(text: str) -> InboundMessage:
    return InboundMessage(
        id="m1", sender="+15551234567", text=text,
        received_at="2026-02-18T12:00:00Z", is_from_me=False,
    )


# --- Command parsing ---

def test_bare_usage_parses():
    cmd = parse_command("usage")
    assert cmd.kind is CommandKind.USAGE
    assert cmd.payload == ""


def test_usage_prefix_parses():
    cmd = parse_command("usage: monthly")
    assert cmd.kind is CommandKind.USAGE
    assert cmd.payload == "monthly"


def test_usage_today_parses():
    cmd = parse_command("usage: today")
    assert cmd.kind is CommandKind.USAGE
    assert cmd.payload == "today"


def test_usage_blocks_parses():
    cmd = parse_command("usage: blocks")
    assert cmd.kind is CommandKind.USAGE
    assert cmd.payload == "blocks"


# --- Handler: daily (default) ---

_DAILY_JSON = json.dumps({
    "daily": [
        {
            "date": "2026-02-17",
            "inputTokens": 1000,
            "outputTokens": 500,
            "cacheCreationTokens": 0,
            "cacheReadTokens": 0,
            "totalTokens": 1500,
            "totalCost": 0.75,
        },
        {
            "date": "2026-02-18",
            "inputTokens": 2000,
            "outputTokens": 800,
            "cacheCreationTokens": 0,
            "cacheReadTokens": 0,
            "totalTokens": 2800,
            "totalCost": 1.20,
        },
    ]
})


def test_usage_daily_default():
    orch = _make_orchestrator()
    mock_result = MagicMock()
    mock_result.stdout = _DAILY_JSON

    with patch("apple_flow.orchestrator.subprocess.run", return_value=mock_result) as mock_run:
        result = orch.handle_message(_msg("usage"))

    assert result.kind is CommandKind.USAGE
    assert "2026-02-17" in result.response
    assert "2026-02-18" in result.response
    assert "$0.75" in result.response
    assert "$1.20" in result.response
    assert "Total: $1.95" in result.response

    args = mock_run.call_args[0][0]
    assert "daily" in args
    assert "--json" in args
    assert "--since" in args


def test_usage_today():
    orch = _make_orchestrator()
    mock_result = MagicMock()
    mock_result.stdout = _DAILY_JSON

    with patch("apple_flow.orchestrator.subprocess.run", return_value=mock_result) as mock_run:
        result = orch.handle_message(_msg("usage: today"))

    assert result.kind is CommandKind.USAGE
    args = mock_run.call_args[0][0]
    assert "daily" in args
    assert "--since" in args
    # since == today (no -6 day offset)
    from datetime import UTC, datetime
    today = datetime.now(UTC).strftime("%Y%m%d")
    assert today in args


# --- Handler: monthly ---

_MONTHLY_JSON = json.dumps({
    "monthly": [
        {"month": "2026-01", "totalTokens": 5_000_000, "totalCost": 12.50},
        {"month": "2026-02", "totalTokens": 3_200_000, "totalCost": 8.00},
    ]
})


def test_usage_monthly():
    orch = _make_orchestrator()
    mock_result = MagicMock()
    mock_result.stdout = _MONTHLY_JSON

    with patch("apple_flow.orchestrator.subprocess.run", return_value=mock_result) as mock_run:
        result = orch.handle_message(_msg("usage: monthly"))

    assert result.kind is CommandKind.USAGE
    assert "2026-01" in result.response
    assert "2026-02" in result.response
    assert "$12.50" in result.response
    args = mock_run.call_args[0][0]
    assert "monthly" in args


# --- Handler: blocks ---

_BLOCKS_JSON = json.dumps({
    "blocks": [
        {
            "id": "b1",
            "startTime": "2026-02-18T10:00:00.000Z",
            "endTime": "2026-02-18T15:00:00.000Z",
            "isActive": False,
            "isGap": False,
            "totalTokens": 1_200_000,
            "costUSD": 4.50,
            "models": ["claude-sonnet-4-6"],
        },
        {
            "id": "gap1",
            "startTime": "2026-02-18T15:00:00.000Z",
            "endTime": "2026-02-18T18:00:00.000Z",
            "isActive": False,
            "isGap": True,
            "totalTokens": 0,
            "costUSD": 0,
            "models": [],
        },
    ]
})


def test_usage_blocks():
    orch = _make_orchestrator()
    mock_result = MagicMock()
    mock_result.stdout = _BLOCKS_JSON

    with patch("apple_flow.orchestrator.subprocess.run", return_value=mock_result) as mock_run:
        result = orch.handle_message(_msg("usage: blocks"))

    assert result.kind is CommandKind.USAGE
    assert "$4.50" in result.response
    assert "2026-02-18 10:00" in result.response
    # gap block should not appear
    assert "gap" not in result.response.lower()
    args = mock_run.call_args[0][0]
    assert "blocks" in args


def test_usage_active_block_tagged():
    orch = _make_orchestrator()
    mock_result = MagicMock()
    mock_result.stdout = json.dumps({
        "blocks": [
            {
                "id": "b2",
                "startTime": "2026-02-18T20:00:00.000Z",
                "endTime": "2026-02-19T01:00:00.000Z",
                "isActive": True,
                "isGap": False,
                "totalTokens": 500_000,
                "costUSD": 2.10,
                "models": ["claude-sonnet-4-6"],
            }
        ]
    })

    with patch("apple_flow.orchestrator.subprocess.run", return_value=mock_result):
        result = orch.handle_message(_msg("usage: blocks"))

    assert "[ACTIVE]" in result.response


# --- Error handling ---

def test_usage_timeout_graceful():
    import subprocess as _sp
    orch = _make_orchestrator()

    with patch("apple_flow.orchestrator.subprocess.run", side_effect=_sp.TimeoutExpired("npx", 30)):
        result = orch.handle_message(_msg("usage"))

    assert result.kind is CommandKind.USAGE
    assert "timed out" in result.response.lower()


def test_usage_no_data():
    orch = _make_orchestrator()
    mock_result = MagicMock()
    mock_result.stdout = json.dumps({"daily": []})

    with patch("apple_flow.orchestrator.subprocess.run", return_value=mock_result):
        result = orch.handle_message(_msg("usage"))

    assert "No usage data found" in result.response
