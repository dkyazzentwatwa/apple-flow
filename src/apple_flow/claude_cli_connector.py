from __future__ import annotations

import logging
import subprocess
import threading
from typing import Any

from .apple_tools import TOOLS_CONTEXT
from .process_registry import ManagedProcessRegistry

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
        tools: list[str] | None = None,
        allowed_tools: list[str] | None = None,
        inject_tools_context: bool = True,
        system_prompt: str = "",
    ):
        """Initialize the Claude CLI connector.

        Args:
            claude_command: Path to the claude binary (default: "claude")
            workspace: Working directory for claude -p (default: None)
            timeout: Timeout in seconds for each exec (default: 300s/5min)
            context_window: Number of recent message pairs to include as context (default: 3)
            model: Model to use (e.g., "claude-sonnet-4-6", "claude-opus-4-6"). Empty = claude default
            dangerously_skip_permissions: Pass --dangerously-skip-permissions flag (default: True)
            tools: Optional tool set passed via --tools (e.g. ["default", "WebSearch"])
            allowed_tools: Optional allowlist passed via --allowedTools (e.g. ["WebSearch"])
            inject_tools_context: Include TOOLS_CONTEXT in the --system prompt (default: True)
            system_prompt: Personality/system instructions passed via --system (default: "")
        """
        self.claude_command = claude_command
        self.workspace = workspace
        self.timeout = timeout
        self.context_window = context_window
        self.model = model.strip()
        self.dangerously_skip_permissions = dangerously_skip_permissions
        self.tools = [t.strip() for t in (tools or []) if t and t.strip()]
        self.allowed_tools = [t.strip() for t in (allowed_tools or []) if t and t.strip()]
        self.inject_tools_context = inject_tools_context
        self.system_prompt = system_prompt.strip()
        self.soul_prompt: str = ""
        self._processes = ManagedProcessRegistry("claude-cli")

        # Store minimal conversation history per sender for context
        # Format: {"sender": ["User: ...\nAssistant: ...", ...]}
        self._sender_contexts: dict[str, list[str]] = {}
        self._contexts_lock = threading.Lock()

        # Cache the system prompt (constant after init)
        self._cached_system_prompt: str = self._build_system_prompt()

    def set_soul_prompt(self, soul_prompt: str) -> None:
        """Set the SOUL.md content and rebuild the cached system prompt."""
        self.soul_prompt = soul_prompt.strip()
        self._cached_system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """Build the system context block from soul + personality + TOOLS_CONTEXT."""
        parts = []
        if self.soul_prompt:
            parts.append(self.soul_prompt)
        if self.system_prompt:
            parts.append(self.system_prompt)
        if self.inject_tools_context:
            parts.append(TOOLS_CONTEXT)
        return "\n\n".join(parts)

    def _build_cmd(self, full_prompt: str) -> list[str]:
        """Assemble the claude CLI command."""
        cmd = [self.claude_command]
        if self.dangerously_skip_permissions:
            cmd.append("--dangerously-skip-permissions")
        if self.model:
            cmd.extend(["--model", self.model])
        if self.tools:
            cmd.extend(["--tools", ",".join(self.tools)])
        if self.allowed_tools:
            cmd.extend(["--allowedTools", ",".join(self.allowed_tools)])
        if self._cached_system_prompt:
            cmd.extend(["--append-system-prompt", self._cached_system_prompt])
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
        with self._contexts_lock:
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

        with self._contexts_lock:
            ctx_len = len(self._sender_contexts.get(sender, []))
        logger.info(
            "Executing Claude CLI: sender=%s workspace=%s timeout=%.1fs context_items=%d",
            sender,
            self.workspace or "default",
            self.timeout,
            ctx_len,
        )

        proc: subprocess.Popen[str] | None = None
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=self.workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            self._processes.register(sender, proc)
            stdout, stderr = proc.communicate(timeout=self.timeout)
            returncode = int(proc.returncode or 0)

            if returncode != 0:
                error_msg = stderr.strip() if stderr else "Unknown error"
                logger.error(
                    "Claude exec failed: returncode=%d stderr=%s",
                    returncode,
                    error_msg,
                )
                return f"Error: Claude execution failed (exit code {returncode}). Check logs for details."

            response = stdout.strip()

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
            if proc is not None:
                self._processes.terminate(proc)
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
        finally:
            if proc is not None:
                self._processes.unregister(proc)

    def run_turn_streaming(self, thread_id: str, prompt: str, on_progress: Any = None) -> str:
        """Execute a turn with line-by-line streaming, calling on_progress for each line.

        Falls back to regular run_turn if streaming fails.
        """
        sender = thread_id
        full_prompt = self._build_prompt_with_context(sender, prompt)
        cmd = self._build_cmd(full_prompt)

        logger.info("Executing Claude CLI (streaming): sender=%s", sender)

        proc: subprocess.Popen[str] | None = None
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=self.workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            self._processes.register(sender, proc)

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
            if proc is not None:
                self._processes.terminate(proc)
            logger.error("Claude exec (streaming) timed out after %.1fs", self.timeout)
            return f"Error: Request timed out after {int(self.timeout)}s."
        except Exception as exc:
            logger.exception("Streaming exec error: %s", exc)
            # Fall back to regular execution
            return self.run_turn(thread_id, prompt)
        finally:
            if proc is not None:
                self._processes.unregister(proc)

    def shutdown(self) -> None:
        """No-op: no persistent process to shut down."""
        logger.info("Claude CLI connector shutdown (no-op)")

    def cancel_active_processes(self, thread_id: str | None = None) -> int:
        """Cancel active Claude subprocesses for one sender or globally."""
        return self._processes.cancel(thread_id)

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

        if history:
            recent_context = history[-self.context_window :]
            context_text = "\n\n".join(recent_context)
            parts.append(f"Previous conversation context:\n{context_text}")

        if self.inject_tools_context:
            parts.append(TOOLS_CONTEXT)

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
