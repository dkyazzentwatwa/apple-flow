"""Tests for OpenAI-compatible API connector."""

from __future__ import annotations

from unittest.mock import Mock, patch

import httpx
import pytest

from apple_flow.openai_connector import OpenAiConnector


def test_openai_connector_implements_protocol():
    """Verify OpenAI connector implements ConnectorProtocol."""
    from apple_flow.protocols import ConnectorProtocol

    connector = OpenAiConnector()
    assert isinstance(connector, ConnectorProtocol)


def test_ensure_started_success():
    """Ensure started verifies API reachability."""
    connector = OpenAiConnector()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.raise_for_status = Mock()

    with patch.object(connector._client, "get", return_value=mock_response) as mock_get:
        connector.ensure_started()
        mock_get.assert_called_once_with("http://localhost:11434/v1/models")


def test_ensure_started_connection_error():
    """Ensure started handles connection errors gracefully."""
    connector = OpenAiConnector()

    with patch.object(connector._client, "get", side_effect=httpx.ConnectError("refused")):
        # Should not raise
        connector.ensure_started()


def test_get_or_create_thread_returns_sender():
    """Thread ID should be the sender."""
    connector = OpenAiConnector()
    sender = "+15551234567"

    thread_id = connector.get_or_create_thread(sender)
    assert thread_id == sender

    thread_id2 = connector.get_or_create_thread(sender)
    assert thread_id2 == sender


def test_reset_thread_clears_context():
    """Reset thread should clear conversation history."""
    connector = OpenAiConnector()
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
    connector = OpenAiConnector()

    with patch.object(connector._client, "close") as mock_close:
        connector.shutdown()
        mock_close.assert_called_once()


def test_run_turn_success():
    """Test successful OpenAI-compatible API call."""
    connector = OpenAiConnector(model="llama3.3")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello! How can I help?"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
    }

    with patch.object(connector._client, "post", return_value=mock_response) as mock_post:
        response = connector.run_turn("+15551234567", "Hello")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")

        assert payload["model"] == "llama3.3"
        assert payload["stream"] is False
        assert payload["max_tokens"] == 4096
        assert payload["messages"][-1] == {"role": "user", "content": "Hello"}
        assert response == "Hello! How can I help?"


def test_run_turn_with_max_tokens():
    """Test that max_tokens is included in request."""
    connector = OpenAiConnector(max_tokens=2048)

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "response"}, "finish_reason": "stop"}],
    }

    with patch.object(connector._client, "post", return_value=mock_response) as mock_post:
        connector.run_turn("+15551234567", "test")

        payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert payload["max_tokens"] == 2048


def test_run_turn_with_system_prompt():
    """Test that system prompt is included in messages."""
    connector = OpenAiConnector(system_prompt="You are a helpful assistant.")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "response"}, "finish_reason": "stop"}],
    }

    with patch.object(connector._client, "post", return_value=mock_response) as mock_post:
        connector.run_turn("+15551234567", "test")

        payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert payload["messages"][0] == {"role": "system", "content": "You are a helpful assistant."}
        assert payload["messages"][-1] == {"role": "user", "content": "test"}


def test_run_turn_with_context():
    """Test that conversation history is included in subsequent messages."""
    connector = OpenAiConnector(context_window=2)
    sender = "+15551234567"

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "Response 1"}, "finish_reason": "stop"}],
    }

    with patch.object(connector._client, "post", return_value=mock_response) as mock_post:
        connector.run_turn(sender, "Message 1")

        mock_response.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "Response 2"}, "finish_reason": "stop"}],
        }
        connector.run_turn(sender, "Message 2")

        # Verify context was stored
        assert len(connector._sender_messages[sender]) == 4
        assert connector._sender_messages[sender][0] == {"role": "user", "content": "Message 1"}
        assert connector._sender_messages[sender][1] == {"role": "assistant", "content": "Response 1"}

        # Verify second call included context in payload
        second_call_payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        messages = second_call_payload["messages"]
        assert len(messages) == 3
        assert messages[0] == {"role": "user", "content": "Message 1"}
        assert messages[1] == {"role": "assistant", "content": "Response 1"}
        assert messages[2] == {"role": "user", "content": "Message 2"}


def test_run_turn_with_api_key():
    """Test that Authorization header is set when api_key is provided."""
    connector = OpenAiConnector(api_key="sk-test-key-123")

    assert connector._client.headers.get("authorization") == "Bearer sk-test-key-123"


def test_run_turn_no_auth_header_when_no_key():
    """Test that no Authorization header when api_key is empty."""
    connector = OpenAiConnector(api_key="")

    assert "authorization" not in connector._client.headers


def test_run_turn_timeout():
    """Test timeout handling."""
    connector = OpenAiConnector(timeout=10.0)

    with patch.object(connector._client, "post", side_effect=httpx.TimeoutException("timed out")):
        response = connector.run_turn("+15551234567", "test")

        assert "timed out" in response.lower()
        assert "10s" in response


def test_run_turn_connection_error():
    """Test connection error handling."""
    connector = OpenAiConnector(base_url="http://localhost:11434")

    with patch.object(connector._client, "post", side_effect=httpx.ConnectError("refused")):
        response = connector.run_turn("+15551234567", "test")

        assert "Cannot connect" in response
        assert "localhost:11434" in response


def test_run_turn_http_401():
    """Test authentication failure handling."""
    connector = OpenAiConnector()

    mock_response = Mock()
    mock_response.status_code = 401

    with patch.object(connector._client, "post", return_value=mock_response):
        response = connector.run_turn("+15551234567", "test")

        assert "Authentication failed" in response


def test_run_turn_http_404():
    """Test model not found handling."""
    connector = OpenAiConnector(model="nonexistent-model")

    mock_response = Mock()
    mock_response.status_code = 404

    with patch.object(connector._client, "post", return_value=mock_response):
        response = connector.run_turn("+15551234567", "test")

        assert "not found" in response.lower()
        assert "nonexistent-model" in response


def test_run_turn_http_500():
    """Test generic server error handling."""
    connector = OpenAiConnector()

    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch.object(connector._client, "post", return_value=mock_response):
        response = connector.run_turn("+15551234567", "test")

        assert "500" in response


def test_run_turn_empty_choices():
    """Test handling of empty choices array."""
    connector = OpenAiConnector()

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": []}

    with patch.object(connector._client, "post", return_value=mock_response):
        response = connector.run_turn("+15551234567", "test")

        assert response == "No response generated."


def test_run_turn_empty_content():
    """Test handling of empty response content."""
    connector = OpenAiConnector()

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}],
    }

    with patch.object(connector._client, "post", return_value=mock_response):
        response = connector.run_turn("+15551234567", "test")

        assert response == "No response generated."


def test_context_window_limiting():
    """Test that context is limited to configured window size."""
    connector = OpenAiConnector(context_window=2)
    sender = "+15551234567"

    mock_response = Mock()
    mock_response.status_code = 200

    with patch.object(connector._client, "post", return_value=mock_response):
        for i in range(5):
            mock_response.json.return_value = {
                "choices": [{"message": {"role": "assistant", "content": f"Response {i}"}, "finish_reason": "stop"}],
            }
            connector.run_turn(sender, f"Message {i}")

        # context_window=2 → max 2*2*2=8 messages
        assert len(connector._sender_messages[sender]) == 8
        # Most recent should be message 4
        assert connector._sender_messages[sender][-2] == {"role": "user", "content": "Message 4"}
        assert connector._sender_messages[sender][-1] == {"role": "assistant", "content": "Response 4"}
        # Message 0 should not be in history
        assert not any(m.get("content") == "Message 0" for m in connector._sender_messages[sender])


def test_base_url_trailing_slash_stripped():
    """Test that trailing slash is stripped from base_url."""
    connector = OpenAiConnector(base_url="http://localhost:11434/")
    assert connector.base_url == "http://localhost:11434"


def test_vercel_ai_gateway_configuration():
    """Test Vercel AI Gateway-style configuration."""
    connector = OpenAiConnector(
        base_url="https://gateway.ai.vercel.app/v1",
        api_key="vercel-key-123",
        model="meta-llama/llama-3.3-70b",
    )

    assert connector.base_url == "https://gateway.ai.vercel.app/v1"
    assert connector.model == "meta-llama/llama-3.3-70b"
    assert connector._client.headers.get("authorization") == "Bearer vercel-key-123"


def test_groq_configuration():
    """Test Groq API configuration."""
    connector = OpenAiConnector(
        base_url="https://api.groq.com/openai",
        api_key="gsk_test_key",
        model="llama-3.3-70b-versatile",
    )

    assert connector.base_url == "https://api.groq.com/openai"
    assert connector.model == "llama-3.3-70b-versatile"
    assert connector._client.headers.get("authorization") == "Bearer gsk_test_key"
