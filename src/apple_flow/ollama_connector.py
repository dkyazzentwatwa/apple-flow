from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger("apple_flow.ollama_connector")


class OllamaConnector:
    """Ollama native API connector using /api/chat.

    Sends HTTP requests to a local Ollama instance for each turn.
    For cloud models or agentic execution, use the Cline connector instead
    (connector="cline"), which supports Ollama and many other providers
    with full tool-use capabilities.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.3",
        timeout: float = 300.0,
        context_window: int = 3,
        system_prompt: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model.strip()
        self.timeout = timeout
        self.context_window = context_window
        self.system_prompt = system_prompt.strip()

        # Per-sender structured message history
        # Format: {"sender": [{"role": "user", "content": "..."}, ...]}
        self._sender_messages: dict[str, list[dict[str, str]]] = {}

        self._client = httpx.Client(
            timeout=httpx.Timeout(self.timeout),
        )

    def ensure_started(self) -> None:
        """Verify Ollama API is reachable."""
        try:
            resp = self._client.get(f"{self.base_url}/api/version")
            resp.raise_for_status()
            logger.info("Ollama API reachable at %s", self.base_url)
        except Exception as exc:
            logger.warning(
                "Ollama API not reachable at %s: %s (will retry on first request)",
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
        """Execute a turn via POST /api/chat.

        Builds a messages array from conversation history, sends to Ollama,
        and stores the exchange.
        """
        sender = thread_id
        messages = self._build_messages(sender, prompt)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }

        logger.info(
            "Ollama API request: sender=%s model=%s url=%s context_items=%d",
            sender,
            self.model,
            self.base_url,
            len(self._sender_messages.get(sender, [])),
        )

        try:
            resp = self._client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )

            if resp.status_code == 404:
                logger.error("Ollama model not found: %s", self.model)
                return f"Error: Model '{self.model}' not found. Run 'ollama pull {self.model}' or check apple_flow_ollama_model setting."

            if resp.status_code >= 400:
                logger.error("Ollama API error: status=%d body=%s", resp.status_code, resp.text[:200])
                return f"Error: Ollama API returned status {resp.status_code}. Check logs for details."

            data = resp.json()
            content = data.get("message", {}).get("content", "").strip()

            if not content:
                logger.warning("Ollama API returned empty response")
                content = "No response generated."

            self._store_exchange(sender, prompt, content)

            logger.info(
                "Ollama API completed: sender=%s response_chars=%d",
                sender,
                len(content),
            )

            return content

        except httpx.TimeoutException:
            logger.error("Ollama API timed out after %.1fs for sender=%s", self.timeout, sender)
            return f"Error: Request timed out after {int(self.timeout)}s. Try a simpler request or increase apple_flow_codex_turn_timeout_seconds."

        except httpx.ConnectError:
            logger.error("Cannot connect to Ollama at %s", self.base_url)
            return f"Error: Cannot connect to Ollama at {self.base_url}. Is Ollama running? Check apple_flow_ollama_base_url setting."

        except (json.JSONDecodeError, KeyError) as exc:
            logger.exception("Failed to parse Ollama response: %s", exc)
            return "Error: Malformed response from Ollama API. Check logs for details."

        except Exception as exc:
            logger.exception("Unexpected error during Ollama API call: %s", exc)
            return f"Error: {type(exc).__name__}: {exc}"

    def run_turn_streaming(self, thread_id: str, prompt: str, on_progress: Any = None) -> str:
        """Execute a turn with streaming, calling on_progress for each chunk.

        Falls back to regular run_turn if streaming fails.
        """
        sender = thread_id
        messages = self._build_messages(sender, prompt)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }

        logger.info("Ollama API request (streaming): sender=%s", sender)

        try:
            chunks: list[str] = []

            with self._client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload,
            ) as resp:
                if resp.status_code >= 400:
                    resp.read()
                    logger.error("Ollama API streaming error: status=%d", resp.status_code)
                    return f"Error: Ollama API returned status {resp.status_code}."

                for line in resp.iter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        chunks.append(chunk)
                        if on_progress:
                            on_progress(chunk)

                    if data.get("done", False):
                        break

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
        logger.info("Ollama connector shutdown")
        self._client.close()

    def _build_messages(self, sender: str, prompt: str) -> list[dict[str, str]]:
        """Build the messages array for the API request.

        Includes optional system prompt, recent conversation history,
        and the new user message.
        """
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
