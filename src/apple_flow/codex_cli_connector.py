from __future__ import annotations

import logging
import subprocess
import threading
from typing import Any

from .apple_tools import TOOLS_CONTEXT

logger = logging.getLogger("apple_flow.cli_connector")


class CodexCliConnector:
    """Stateless Codex CLI connector using `codex exec` for each turn.

    This connector avoids state corruption issues by spawning a fresh
    `codex exec` process for each message instead of maintaining persistent
    threads in a long-running app-server process.
    """

    def __init__(
        self,
        codex_command: str = "codex",
        workspace: str | None = None,
        timeout: float = 300.0,
        context_window: int = 3,
        model: str = "",
        inject_tools_context: bool = True,
    ):
        """Initialize the CLI connector.

        Args:
            codex_command: Path to the codex binary (default: "codex")
            workspace: Working directory for codex exec (default: None)
            timeout: Timeout in seconds for each exec (default: 300s/5min)
            context_window: Number of recent message pairs to include as context (default: 3)
            model: Model to use (e.g., "sonnet", "opus", "haiku"). Empty = use codex default
            inject_tools_context: Prepend TOOLS_CONTEXT to prompts so AI knows apple-flow tools (default: True)
        """
        self.codex_command = codex_command
        self.workspace = workspace
        self.timeout = timeout
        self.context_window = context_window
        self.model = model.strip()
        self.inject_tools_context = inject_tools_context

        # Store minimal conversation history per sender for context
        # Format: {"sender": ["User: ...\nAssistant: ...", ...]}
        self._sender_contexts: dict[str, list[str]] = {}
        self._contexts_lock = threading.Lock()

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
        with self._contexts_lock:
            self._sender_contexts.pop(sender, None)
        logger.info("Reset context for sender: %s", sender)
        return sender

    def run_turn(self, thread_id: str, prompt: str) -> str:
        """Execute a turn using `codex exec`.

        Builds a context-aware prompt from recent history, spawns a fresh
        `codex exec` process, captures output, and stores the exchange.

        Args:
            thread_id: Sender identifier (used as thread ID)
            prompt: User's message/prompt

        Returns:
            Codex's response text
        """
        sender = thread_id

        # Build context-aware prompt from recent history
        full_prompt = self._build_prompt_with_context(sender, prompt)

        # Build command with --skip-git-repo-check and --yolo flags
        # (relay has its own workspace security via allowed_workspaces
        # and approval workflow, so we bypass codex's sandbox)
        cmd = [self.codex_command, "exec", "--skip-git-repo-check", "--yolo"]
        if self.model:
            cmd.extend(["-m", self.model])
        cmd.append(full_prompt)

        with self._contexts_lock:
            ctx_len = len(self._sender_contexts.get(sender, []))
        logger.info(
            "Executing codex CLI: sender=%s workspace=%s timeout=%.1fs context_items=%d",
            sender,
            self.workspace or "default",
            self.timeout,
            ctx_len,
        )

        try:
            # Execute subprocess with timeout
            result = subprocess.run(
                cmd,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,  # Don't raise on non-zero exit
            )

            # Check for errors
            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                logger.error(
                    "Codex exec failed: returncode=%d stderr=%s",
                    result.returncode,
                    error_msg,
                )
                return f"Error: Codex execution failed (exit code {result.returncode}). Check logs for details."

            # Get response
            response = result.stdout.strip()

            if not response:
                logger.warning("Codex exec returned empty response")
                response = "No response generated."

            # Store this exchange in context history
            self._store_exchange(sender, prompt, response)

            logger.info(
                "Codex exec completed: sender=%s response_chars=%d",
                sender,
                len(response),
            )

            return response

        except subprocess.TimeoutExpired:
            logger.error(
                "Codex exec timed out after %.1fs for sender=%s",
                self.timeout,
                sender,
            )
            return f"Error: Request timed out after {int(self.timeout)}s. Try a simpler request or increase apple_flow_codex_turn_timeout_seconds."
        except FileNotFoundError:
            logger.error("Codex binary not found: %s", self.codex_command)
            return f"Error: Codex CLI not found at '{self.codex_command}'. Check apple_flow_codex_cli_command setting."
        except Exception as exc:
            logger.exception("Unexpected error during codex exec: %s", exc)
            return f"Error: {type(exc).__name__}: {exc}"

    def run_turn_streaming(self, thread_id: str, prompt: str, on_progress: Any = None) -> str:
        """Execute a turn with line-by-line streaming, calling on_progress for each line.

        Falls back to regular run_turn if streaming fails.
        """
        sender = thread_id
        full_prompt = self._build_prompt_with_context(sender, prompt)
        cmd = [self.codex_command, "exec", "--skip-git-repo-check", "--yolo"]
        if self.model:
            cmd.extend(["-m", self.model])
        cmd.append(full_prompt)

        logger.info("Executing codex CLI (streaming): sender=%s", sender)

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
                logger.error("Codex exec (streaming) failed: rc=%d", proc.returncode)
                return f"Error: Codex execution failed (exit code {proc.returncode}). {error_msg}"

            response = "".join(output_lines).strip()
            if not response:
                response = "No response generated."

            self._store_exchange(sender, prompt, response)
            return response

        except subprocess.TimeoutExpired:
            proc.kill()
            logger.error("Codex exec (streaming) timed out after %.1fs", self.timeout)
            return f"Error: Request timed out after {int(self.timeout)}s."
        except Exception as exc:
            logger.exception("Streaming exec error: %s", exc)
            # Fall back to regular execution
            return self.run_turn(thread_id, prompt)

    def shutdown(self) -> None:
        """No-op: no persistent process to shut down."""
        logger.info("CLI connector shutdown (no-op)")

    def _build_prompt_with_context(self, sender: str, prompt: str) -> str:
        """Build a prompt that includes recent conversation context.

        Args:
            sender: Sender identifier
            prompt: Current user prompt

        Returns:
            Full prompt with context prepended (and TOOLS_CONTEXT header if enabled)
        """
        with self._contexts_lock:
            history = list(self._sender_contexts.get(sender, []))

        parts: list[str] = []

        if self.inject_tools_context:
            parts.append(TOOLS_CONTEXT)

        if history:
            recent_context = history[-self.context_window:]
            context_text = "\n\n".join(recent_context)
            parts.append(f"Previous conversation context:\n{context_text}")

        parts.append(f"New message:\n{prompt}" if history or self.inject_tools_context else prompt)

        return "\n\n".join(parts)

    def _store_exchange(self, sender: str, user_message: str, assistant_response: str) -> None:
        """Store a user-assistant exchange in the context history.

        Args:
            sender: Sender identifier
            user_message: User's message
            assistant_response: Assistant's response
        """
        exchange = f"User: {user_message}\nAssistant: {assistant_response}"
        max_history = self.context_window * 2
        with self._contexts_lock:
            if sender not in self._sender_contexts:
                self._sender_contexts[sender] = []
            self._sender_contexts[sender].append(exchange)
            # Limit history size (keep last 2x context_window to have buffer)
            if len(self._sender_contexts[sender]) > max_history:
                self._sender_contexts[sender] = self._sender_contexts[sender][-max_history:]
