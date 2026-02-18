from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger("apple_flow.openai_connector")


class OpenAiConnector:
    """OpenAI-compatible API connector using /v1/chat/completions.

    Works with any OpenAI-compatible endpoint: Ollama's OpenAI layer,
    Vercel AI Gateway, Groq, Together, LM Studio, vLLM, OpenRouter, etc.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        api_key: str = "",
        model: str = "llama3.3",
        timeout: float = 300.0,
        context_window: int = 3,
        system_prompt: str = "",
        max_tokens: int = 4096,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.timeout = timeout
        self.context_window = context_window
        self.system_prompt = system_prompt.strip()
        self.max_tokens = max_tokens

        # Per-sender structured message history
        self._sender_messages: dict[str, list[dict[str, str]]] = {}

        # Build default headers
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self._client = httpx.Client(
            timeout=httpx.Timeout(self.timeout),
            headers=headers,
        )

    def ensure_started(self) -> None:
        """Verify OpenAI-compatible API is reachable."""
        try:
            resp = self._client.get(f"{self.base_url}/v1/models")
            resp.raise_for_status()
            logger.info("OpenAI-compatible API reachable at %s", self.base_url)
        except Exception as exc:
            logger.warning(
                "OpenAI-compatible API not reachable at %s: %s (will retry on first request)",
                self.base_url,
                exc,
            )

    def get_or_create_thread(self, sender: str) -> str:
        """Return sender as synthetic thread ID."""
        return sender

    def reset_thread(self, sender: str) -> str:
        """Clear conversation history for a sender."""
        self._sender_messages.pop(sender, None)
        logger.info("Reset context for sender: %s", sender)
        return sender

    def run_turn(self, thread_id: str, prompt: str) -> str:
        """Execute a turn via POST /v1/chat/completions.

        Builds a messages array from conversation history, sends to the
        OpenAI-compatible endpoint, and stores the exchange.
        """
        sender = thread_id
        messages = self._build_messages(sender, prompt)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "max_tokens": self.max_tokens,
        }

        logger.info(
            "OpenAI API request: sender=%s model=%s url=%s context_items=%d",
            sender,
            self.model,
            self.base_url,
            len(self._sender_messages.get(sender, [])),
        )

        try:
            resp = self._client.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
            )

            if resp.status_code == 401:
                logger.error("OpenAI API authentication failed (401)")
                return "Error: Authentication failed. Check apple_flow_openai_api_key setting."

            if resp.status_code == 404:
                logger.error("OpenAI API model not found: %s", self.model)
                return f"Error: Model '{self.model}' not found. Check apple_flow_openai_model setting."

            if resp.status_code >= 400:
                logger.error("OpenAI API error: status=%d body=%s", resp.status_code, resp.text[:200])
                return f"Error: OpenAI-compatible API returned status {resp.status_code}. Check logs for details."

            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                logger.warning("OpenAI API returned no choices")
                return "No response generated."

            content = choices[0].get("message", {}).get("content", "").strip()

            if not content:
                logger.warning("OpenAI API returned empty content")
                content = "No response generated."

            self._store_exchange(sender, prompt, content)

            logger.info(
                "OpenAI API completed: sender=%s response_chars=%d",
                sender,
                len(content),
            )

            return content

        except httpx.TimeoutException:
            logger.error("OpenAI API timed out after %.1fs for sender=%s", self.timeout, sender)
            return f"Error: Request timed out after {int(self.timeout)}s. Try a simpler request or increase apple_flow_codex_turn_timeout_seconds."

        except httpx.ConnectError:
            logger.error("Cannot connect to OpenAI-compatible API at %s", self.base_url)
            return f"Error: Cannot connect to API at {self.base_url}. Check apple_flow_openai_base_url setting."

        except (json.JSONDecodeError, KeyError) as exc:
            logger.exception("Failed to parse OpenAI API response: %s", exc)
            return "Error: Malformed response from API. Check logs for details."

        except Exception as exc:
            logger.exception("Unexpected error during OpenAI API call: %s", exc)
            return f"Error: {type(exc).__name__}: {exc}"

    def run_turn_streaming(self, thread_id: str, prompt: str, on_progress: Any = None) -> str:
        """Execute a turn with SSE streaming, calling on_progress for each chunk.

        Falls back to regular run_turn if streaming fails.
        """
        sender = thread_id
        messages = self._build_messages(sender, prompt)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "max_tokens": self.max_tokens,
        }

        logger.info("OpenAI API request (streaming): sender=%s", sender)

        try:
            chunks: list[str] = []

            with self._client.stream(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                json=payload,
            ) as resp:
                if resp.status_code >= 400:
                    resp.read()
                    logger.error("OpenAI API streaming error: status=%d", resp.status_code)
                    return f"Error: OpenAI-compatible API returned status {resp.status_code}."

                for line in resp.iter_lines():
                    line = line.strip()
                    if not line:
                        continue

                    # SSE format: "data: {...}" or "data: [DONE]"
                    if not line.startswith("data:"):
                        continue

                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break

                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choices = data.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})
                    chunk = delta.get("content", "")
                    if chunk:
                        chunks.append(chunk)
                        if on_progress:
                            on_progress(chunk)

            content = "".join(chunks).strip()
            if not content:
                content = "No response generated."

            self._store_exchange(sender, prompt, content)
            return content

        except Exception as exc:
            logger.exception("Streaming error: %s", exc)
            return self.run_turn(thread_id, prompt)

    def shutdown(self) -> None:
        """Close the HTTP client."""
        logger.info("OpenAI connector shutdown")
        self._client.close()

    def _build_messages(self, sender: str, prompt: str) -> list[dict[str, str]]:
        """Build the messages array for the API request."""
        messages: list[dict[str, str]] = []

        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        # Include recent history
        history = self._sender_messages.get(sender, [])
        recent = history[-(self.context_window * 2):]  # pairs of user+assistant
        messages.extend(recent)

        # Add new user message
        messages.append({"role": "user", "content": prompt})

        return messages

    def _store_exchange(self, sender: str, user_message: str, assistant_response: str) -> None:
        """Store a user-assistant exchange in conversation history."""
        if sender not in self._sender_messages:
            self._sender_messages[sender] = []

        self._sender_messages[sender].append({"role": "user", "content": user_message})
        self._sender_messages[sender].append({"role": "assistant", "content": assistant_response})

        # Limit history (keep last context_window exchanges = 2x messages)
        max_messages = self.context_window * 2 * 2  # pairs * 2 messages each
        if len(self._sender_messages[sender]) > max_messages:
            self._sender_messages[sender] = self._sender_messages[sender][-max_messages:]
