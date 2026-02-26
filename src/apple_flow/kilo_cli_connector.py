from __future__ import annotations

import logging
import subprocess
import threading
from typing import Any

from .apple_tools import TOOLS_CONTEXT
from .process_registry import ManagedProcessRegistry

logger = logging.getLogger("apple_flow.kilo_cli_connector")


class KiloCliConnector:
    """Stateless Kilo CLI connector using `kilo run --auto` for each turn.

    This connector avoids state corruption issues by spawning a fresh
    `kilo run` process for each message instead of maintaining persistent
    threads in a long-running app-server process.
    """

    def __init__(
        self,
        kilo_command: str = "kilo",
        workspace: str | None = None,
        timeout: float = 300.0,
        context_window: int = 10,
        model: str = "",
        inject_tools_context: bool = True,
        system_prompt: str = "",
    ):
        """Initialize the Kilo CLI connector.

        Args:
            kilo_command: Path to the kilo binary (default: "kilo")
            workspace: Working directory for kilo run (default: None)
            timeout: Timeout in seconds for each run (default: 300s/5min)
            context_window: Number of recent message pairs to include as context (default: 10)
            model: Model to use (e.g., "google/gemini-3-flash-preview"). Empty = kilo default
            inject_tools_context: Prepend TOOLS_CONTEXT to prompts (default: True)
            system_prompt: Personality/system instructions (default: "")
        """
        self.kilo_command = kilo_command
        self.workspace = workspace
        self.timeout = timeout
        self.context_window = context_window
        self.model = model.strip()
        self.inject_tools_context = inject_tools_context
        self.system_prompt = system_prompt.strip()
        self.soul_prompt: str = ""
        self._processes = ManagedProcessRegistry("kilo-cli")

        # Store minimal conversation history per sender for context
        # Format: {"sender": ["User: ...\nAssistant: ...", ...]}
        self._sender_contexts: dict[str, list[str]] = {}
        self._contexts_lock = threading.Lock()

    def set_soul_prompt(self, soul_prompt: str) -> None:
        """Set the companion identity prompt, prepended before everything else."""
        self.soul_prompt = soul_prompt.strip()

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

    def _build_cmd(self) -> list[str]:
        """Assemble the kilo CLI command."""
        # Use --auto to bypass interactive approvals for tools in the connector
        # (apple-flow has its own approval gate at the orchestrator level)
        cmd = [self.kilo_command, "run", "--auto"]
        if self.model:
            cmd.extend(["--model", self.model])
        return cmd

    def run_turn(self, thread_id: str, prompt: str) -> str:
        """Execute a turn using `kilo run --auto`.

        Builds a context-aware prompt from recent history, spawns a fresh
        `kilo run` process, captures output, and stores the exchange.

        Args:
            thread_id: Sender identifier (used as thread ID)
            prompt: User's message/prompt

        Returns:
            Kilo's response text
        """
        sender = thread_id

        # Build context-aware prompt from recent history
        full_prompt = self._build_prompt_with_context(sender, prompt)
        cmd = self._build_cmd()

        with self._contexts_lock:
            ctx_len = len(self._sender_contexts.get(sender, []))
        logger.info(
            "Executing Kilo CLI: sender=%s workspace=%s timeout=%.1fs context_items=%d",
            sender,
            self.workspace or "default",
            self.timeout,
            ctx_len,
        )

        proc: subprocess.Popen[str] | None = None
        try:
            # We use stdin to pass the prompt to avoid shell command line length limits
            proc = subprocess.Popen(
                cmd,
                cwd=self.workspace,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            self._processes.register(sender, proc)
            stdout, stderr = proc.communicate(input=full_prompt, timeout=self.timeout)
            returncode = int(proc.returncode or 0)

            # Check for errors
            if returncode != 0:
                error_msg = stderr.strip() if stderr else "Unknown error"
                logger.error(
                    "Kilo run failed: returncode=%d stderr=%s",
                    returncode,
                    error_msg,
                )
                return f"Error: Kilo execution failed (exit code {returncode}). Check logs for details."

            # Get response from stdout. Kilo's stderr contains headers like "> code · google/..."
            response = stdout.strip()

            if not response:
                logger.warning("Kilo run returned empty response")
                response = "No response generated."

            # Store this exchange in context history
            self._store_exchange(sender, prompt, response)

            logger.info(
                "Kilo run completed: sender=%s response_chars=%d",
                sender,
                len(response),
            )

            return response

        except subprocess.TimeoutExpired:
            if proc is not None:
                self._processes.terminate(proc)
            logger.error(
                "Kilo run timed out after %.1fs for sender=%s",
                self.timeout,
                sender,
            )
            return f"Error: Request timed out after {int(self.timeout)}s. Try a simpler request or increase apple_flow_codex_turn_timeout_seconds."
        except FileNotFoundError:
            logger.error("Kilo binary not found: %s", self.kilo_command)
            return f"Error: Kilo CLI not found at '{self.kilo_command}'. Check apple_flow_kilo_cli_command setting."
        except Exception as exc:
            logger.exception("Unexpected error during kilo run: %s", exc)
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
        cmd = self._build_cmd()

        logger.info("Executing Kilo CLI (streaming): sender=%s", sender)

        proc: subprocess.Popen[str] | None = None
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=self.workspace,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            self._processes.register(sender, proc)

            output_lines: list[str] = []
            
            # Since we're using stdin, we need to send the full_prompt first
            # but for streaming, Popen.stdin might be tricky if we want to pipe input and then read output
            # Communicate is usually better for piping input, but it buffers.
            # We'll use a thread to write to stdin and the main thread to read stdout.
            def _write_input():
                try:
                    assert proc is not None
                    assert proc.stdin is not None
                    proc.stdin.write(full_prompt)
                    proc.stdin.close()
                except Exception:
                    pass

            writer_thread = threading.Thread(target=_write_input, daemon=True)
            writer_thread.start()

            assert proc.stdout is not None
            for line in proc.stdout:
                output_lines.append(line)
                if on_progress:
                    on_progress(line)

            proc.wait(timeout=self.timeout)

            if proc.returncode != 0:
                error_msg = proc.stderr.read() if proc.stderr else "Unknown error"
                logger.error("Kilo run (streaming) failed: rc=%d", proc.returncode)
                return f"Error: Kilo execution failed (exit code {proc.returncode}). {error_msg}"

            response = "".join(output_lines).strip()
            if not response:
                response = "No response generated."

            self._store_exchange(sender, prompt, response)
            return response

        except subprocess.TimeoutExpired:
            if proc is not None:
                self._processes.terminate(proc)
            logger.error("Kilo run (streaming) timed out after %.1fs", self.timeout)
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
        logger.info("Kilo CLI connector shutdown (no-op)")

    def cancel_active_processes(self, thread_id: str | None = None) -> int:
        """Cancel active Kilo subprocesses for one sender or globally."""
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

        if self.soul_prompt:
            parts.append(self.soul_prompt)
        
        if self.system_prompt:
            parts.append(self.system_prompt)

        # Keep Kilo responses user-facing for iMessage and avoid exposing
        # planning/tool narration that looks like internal reasoning.
        parts.append(
            "Response rules:\n"
            "- Return only the final answer to the user.\n"
            "- Do not narrate plans, internal reasoning, or tool checks.\n"
            "- If tools are needed, use them silently and report only outcomes.\n"
            "- Keep replies concise and natural for iMessage."
        )

        if self.inject_tools_context:
            parts.append(TOOLS_CONTEXT)

        if history:
            recent_context = history[-self.context_window:]
            context_text = "\n\n".join(recent_context)
            parts.append(f"Previous conversation context:\n{context_text}")

        parts.append(f"New message:\n{prompt}" if history or self.inject_tools_context or self.soul_prompt or self.system_prompt else prompt)

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
