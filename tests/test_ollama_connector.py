"""Tests for Ollama native API connector."""

from __future__ import annotations

from unittest.mock import Mock, patch

import httpx
import pytest

from apple_flow.ollama_connector import OllamaConnector


def test_ollama_connector_implements_protocol():
    """Verify Ollama connector implements ConnectorProtocol."""
    from apple_flow.protocols import ConnectorProtocol

    connector = OllamaConnector()
    assert isinstance(connector, ConnectorProtocol)


def test_ensure_started_success():
    """Ensure started verifies API reachability."""
    connector = OllamaConnector()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.raise_for_status = Mock()

    with patch.object(connector._client, "get", return_value=mock_response) as mock_get:
        connector.ensure_started()
        mock_get.assert_called_once_with("http://localhost:11434/api/version")


def test_ensure_started_connection_error():
    """Ensure started handles connection errors gracefully."""
    connector = OllamaConnector()

    with patch.object(connector._client, "get", side_effect=httpx.ConnectError("refused")):
        # Should not raise
        connector.ensure_started()


def test_get_or_create_thread_returns_sender():
    """Thread ID should be the sender."""
    connector = OllamaConnector()
    sender = "+15551234567"

    thread_id = connector.get_or_create_thread(sender)
    assert thread_id == sender

    thread_id2 = connector.get_or_create_thread(sender)
    assert thread_id2 == sender


def test_reset_thread_clears_context():
    """Reset thread should clear conversation history."""
    connector = OllamaConnector()
    sender = "+15551234567"

    connector._sender_messages[sender] = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]

    thread_id = connector.reset_thread(sender)
    assert thread_id == sender
    assert sender not in connector._sender_messages


def test_shutdown_closes_client():
    """Shutdown should close the httpx client."""
    connector = OllamaConnector()

    with patch.object(connector._client, "close") as mock_close:
        connector.shutdown()
        mock_close.assert_called_once()


def test_run_turn_success():
    """Test successful Ollama API call."""
    connector = OllamaConnector(model="llama3.3")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "model": "llama3.3",
        "message": {"role": "assistant", "content": "Hello! How can I help?"},
        "done": True,
    }

    with patch.object(connector._client, "post", return_value=mock_response) as mock_post:
        response = connector.run_turn("+15551234567", "Hello")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")

        assert payload["model"] == "llama3.3"
        assert payload["stream"] is False
        assert payload["messages"][-1] == {"role": "user", "content": "Hello"}
        assert response == "Hello! How can I help?"


def test_run_turn_with_system_prompt():
    """Test that system prompt is included in messages."""
    connector = OllamaConnector(system_prompt="You are a helpful assistant.")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "message": {"role": "assistant", "content": "response"},
        "done": True,
    }

    with patch.object(connector._client, "post", return_value=mock_response) as mock_post:
        connector.run_turn("+15551234567", "test")

        payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert payload["messages"][0] == {"role": "system", "content": "You are a helpful assistant."}
        assert payload["messages"][-1] == {"role": "user", "content": "test"}


def test_run_turn_with_context():
    """Test that conversation history is included in subsequent messages."""
    connector = OllamaConnector(context_window=2)
    sender = "+15551234567"

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "message": {"role": "assistant", "content": "Response 1"},
        "done": True,
    }

    with patch.object(connector._client, "post", return_value=mock_response) as mock_post:
        connector.run_turn(sender, "Message 1")

        mock_response.json.return_value = {
            "message": {"role": "assistant", "content": "Response 2"},
            "done": True,
        }
        connector.run_turn(sender, "Message 2")

        # Verify context was stored
        assert len(connector._sender_messages[sender]) == 4  # 2 pairs
        assert connector._sender_messages[sender][0] == {"role": "user", "content": "Message 1"}
        assert connector._sender_messages[sender][1] == {"role": "assistant", "content": "Response 1"}

        # Verify second call included context in payload
        second_call_payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        messages = second_call_payload["messages"]
        # Should have: history (user+assistant from first turn) + new user message
        assert len(messages) == 3
        assert messages[0] == {"role": "user", "content": "Message 1"}
        assert messages[1] == {"role": "assistant", "content": "Response 1"}
        assert messages[2] == {"role": "user", "content": "Message 2"}


def test_run_turn_timeout():
    """Test timeout handling."""
    connector = OllamaConnector(timeout=10.0)

    with patch.object(connector._client, "post", side_effect=httpx.TimeoutException("timed out")):
        response = connector.run_turn("+15551234567", "test")

        assert "timed out" in response.lower()
        assert "10s" in response


def test_run_turn_connection_error():
    """Test connection error handling."""
    connector = OllamaConnector(base_url="http://localhost:11434")

    with patch.object(connector._client, "post", side_effect=httpx.ConnectError("refused")):
        response = connector.run_turn("+15551234567", "test")

        assert "Cannot connect" in response
        assert "localhost:11434" in response


def test_run_turn_http_404():
    """Test model not found handling."""
    connector = OllamaConnector(model="nonexistent-model")

    mock_response = Mock()
    mock_response.status_code = 404

    with patch.object(connector._client, "post", return_value=mock_response):
        response = connector.run_turn("+15551234567", "test")

        assert "not found" in response.lower()
        assert "nonexistent-model" in response


def test_run_turn_http_500():
    """Test generic server error handling."""
    connector = OllamaConnector()

    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch.object(connector._client, "post", return_value=mock_response):
        response = connector.run_turn("+15551234567", "test")

        assert "500" in response


def test_run_turn_empty_response():
    """Test handling of empty response content."""
    connector = OllamaConnector()

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "message": {"role": "assistant", "content": ""},
        "done": True,
    }

    with patch.object(connector._client, "post", return_value=mock_response):
        response = connector.run_turn("+15551234567", "test")

        assert response == "No response generated."


def test_context_window_limiting():
    """Test that context is limited to configured window size."""
    connector = OllamaConnector(context_window=2)
    sender = "+15551234567"

    mock_response = Mock()
    mock_response.status_code = 200

    with patch.object(connector._client, "post", return_value=mock_response):
        for i in range(5):
            mock_response.json.return_value = {
                "message": {"role": "assistant", "content": f"Response {i}"},
                "done": True,
            }
            connector.run_turn(sender, f"Message {i}")

        # context_window=2 → max 2*2*2=8 messages, but we sent 5 exchanges = 10 messages
        # Should be trimmed to 8
        assert len(connector._sender_messages[sender]) == 8
        # Most recent should be message 4
        assert connector._sender_messages[sender][-2] == {"role": "user", "content": "Message 4"}
        assert connector._sender_messages[sender][-1] == {"role": "assistant", "content": "Response 4"}
        # Message 0 should not be in history
        assert not any(m.get("content") == "Message 0" for m in connector._sender_messages[sender])


def test_base_url_trailing_slash_stripped():
    """Test that trailing slash is stripped from base_url."""
    connector = OllamaConnector(base_url="http://localhost:11434/")
    assert connector.base_url == "http://localhost:11434"
