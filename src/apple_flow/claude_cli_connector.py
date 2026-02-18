from __future__ import annotations

import logging
import subprocess
from typing import Any

logger = logging.getLogger("apple_flow.claude_cli_connector")


class ClaudeCliConnector:
    """Stateless Claude CLI connector using `claude -p` for each turn.

    This connector avoids state corruption issues by spawning a fresh
    `claude -p` process for each message instead of maintaining persistent
    threads in a long-running server process.
    """

    def __init__(
        self,
        claude_command: str = "claude",
        workspace: str | None = None,
        timeout: float = 300.0,
        context_window: int = 3,
        model: str = "",
        dangerously_skip_permissions: bool = True,
    ):
        """Initialize the Claude CLI connector.

        Args:
            claude_command: Path to the claude binary (default: "claude")
            workspace: Working directory for claude -p (default: None)
            timeout: Timeout in seconds for each exec (default: 300s/5min)
            context_window: Number of recent message pairs to include as context (default: 3)
            model: Model to use (e.g., "claude-sonnet-4-6", "claude-opus-4-6"). Empty = claude default
            dangerously_skip_permissions: Pass --dangerously-skip-permissions flag (default: True)
        """
        self.claude_command = claude_command
        self.workspace = workspace
        self.timeout = timeout
        self.context_window = context_window
        self.model = model.strip()
        self.dangerously_skip_permissions = dangerously_skip_permissions

        # Store minimal conversation history per sender for context
        # Format: {"sender": ["User: ...\nAssistant: ...", ...]}
        self._sender_contexts: dict[str, list[str]] = {}

    def _build_cmd(self, full_prompt: str) -> list[str]:
        """Assemble the claude CLI command."""
        cmd = [self.claude_command]
        if self.dangerously_skip_permissions:
            cmd.append("--dangerously-skip-permissions")
        if self.model:
            cmd.extend(["--model", self.model])
        cmd.extend(["-p", full_prompt])
        return cmd

    def ensure_started(self) -> None:
        """No-op: CLI spawns fresh process for each turn."""
        pass

    def get_or_create_thread(self, sender: str) -> str:
        """Return synthetic thread ID (just the sender).

        Since we're stateless, we use the sender as the thread ID.
        """
        return sender

    def reset_thread(self, sender: str) -> str:
        """Clear conversation history and return new thread ID.

        This implements the "clear context" functionality.
        """
        self._sender_contexts.pop(sender, None)
        logger.info("Reset context for sender: %s", sender)
        return sender

    def run_turn(self, thread_id: str, prompt: str) -> str:
        """Execute a turn using `claude -p`.

        Builds a context-aware prompt from recent history, spawns a fresh
        `claude -p` process, captures output, and stores the exchange.

        Args:
            thread_id: Sender identifier (used as thread ID)
            prompt: User's message/prompt

        Returns:
            Claude's response text
        """
        sender = thread_id

        # Build context-aware prompt from recent history
        full_prompt = self._build_prompt_with_context(sender, prompt)
        cmd = self._build_cmd(full_prompt)

        logger.info(
            "Executing Claude CLI: sender=%s workspace=%s timeout=%.1fs context_items=%d",
            sender,
            self.workspace or "default",
            self.timeout,
            len(self._sender_contexts.get(sender, [])),
        )

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,  # Don't raise on non-zero exit
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                logger.error(
                    "Claude exec failed: returncode=%d stderr=%s",
                    result.returncode,
                    error_msg,
                )
                return f"Error: Claude execution failed (exit code {result.returncode}). Check logs for details."

            response = result.stdout.strip()

            if not response:
                logger.warning("Claude exec returned empty response")
                response = "No response generated."

            self._store_exchange(sender, prompt, response)

            logger.info(
                "Claude exec completed: sender=%s response_chars=%d",
                sender,
                len(response),
            )

            return response

        except subprocess.TimeoutExpired:
            logger.error(
                "Claude exec timed out after %.1fs for sender=%s",
                self.timeout,
                sender,
            )
            return f"Error: Request timed out after {int(self.timeout)}s. Try a simpler request or increase apple_flow_codex_turn_timeout_seconds."
        except FileNotFoundError:
            logger.error("Claude binary not found: %s", self.claude_command)
            return f"Error: Claude CLI not found at '{self.claude_command}'. Check apple_flow_claude_cli_command setting."
        except Exception as exc:
            logger.exception("Unexpected error during Claude exec: %s", exc)
            return f"Error: {type(exc).__name__}: {exc}"

    def run_turn_streaming(self, thread_id: str, prompt: str, on_progress: Any = None) -> str:
        """Execute a turn with line-by-line streaming, calling on_progress for each line.

        Falls back to regular run_turn if streaming fails.
        """
        sender = thread_id
        full_prompt = self._build_prompt_with_context(sender, prompt)
        cmd = self._build_cmd(full_prompt)

        logger.info("Executing Claude CLI (streaming): sender=%s", sender)

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=self.workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            output_lines: list[str] = []
            assert proc.stdout is not None
            for line in proc.stdout:
                output_lines.append(line)
                if on_progress:
                    on_progress(line)

            proc.wait(timeout=self.timeout)

            if proc.returncode != 0:
                error_msg = proc.stderr.read() if proc.stderr else "Unknown error"
                logger.error("Claude exec (streaming) failed: rc=%d", proc.returncode)
                return f"Error: Claude execution failed (exit code {proc.returncode}). {error_msg}"

            response = "".join(output_lines).strip()
            if not response:
                response = "No response generated."

            self._store_exchange(sender, prompt, response)
            return response

        except subprocess.TimeoutExpired:
            proc.kill()
            logger.error("Claude exec (streaming) timed out after %.1fs", self.timeout)
            return f"Error: Request timed out after {int(self.timeout)}s."
        except Exception as exc:
            logger.exception("Streaming exec error: %s", exc)
            # Fall back to regular execution
            return self.run_turn(thread_id, prompt)

    def shutdown(self) -> None:
        """No-op: no persistent process to shut down."""
        logger.info("Claude CLI connector shutdown (no-op)")

    def _build_prompt_with_context(self, sender: str, prompt: str) -> str:
        """Build a prompt that includes recent conversation context.

        Args:
            sender: Sender identifier
            prompt: Current user prompt

        Returns:
            Full prompt with context prepended
        """
        history = self._sender_contexts.get(sender, [])

        if not history:
            return prompt

        recent_context = history[-self.context_window:]
        context_text = "\n\n".join(recent_context)

        full_prompt = (
            f"Previous conversation context:\n{context_text}\n\n"
            f"New message:\n{prompt}"
        )

        return full_prompt

    def _store_exchange(self, sender: str, user_message: str, assistant_response: str) -> None:
        """Store a user-assistant exchange in the context history.

        Args:
            sender: Sender identifier
            user_message: User's message
            assistant_response: Assistant's response
        """
        if sender not in self._sender_contexts:
            self._sender_contexts[sender] = []

        exchange = f"User: {user_message}\nAssistant: {assistant_response}"
        self._sender_contexts[sender].append(exchange)

        # Limit history size (keep last 2x context_window to have buffer)
        max_history = self.context_window * 2
        if len(self._sender_contexts[sender]) > max_history:
            self._sender_contexts[sender] = self._sender_contexts[sender][-max_history:]
