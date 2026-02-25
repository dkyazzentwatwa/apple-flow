from __future__ import annotations

import logging
import subprocess
import threading
from typing import Any

from .apple_tools import TOOLS_CONTEXT

logger = logging.getLogger("apple_flow.gemini_cli_connector")


class GeminiCliConnector:
    """Stateless Gemini CLI connector using `gemini -p` for each turn."""

    def __init__(
        self,
        gemini_command: str = "gemini",
        workspace: str | None = None,
        timeout: float = 300.0,
        context_window: int = 10,
        model: str = "gemini-3-flash-preview",
        inject_tools_context: bool = True,
        system_prompt: str = "",
    ):
        self.gemini_command = gemini_command
        self.workspace = workspace
        self.timeout = timeout
        self.context_window = context_window
        self.model = model.strip()
        self.inject_tools_context = inject_tools_context
        self.system_prompt = system_prompt.strip()
        self.soul_prompt: str = ""

        # Format: {"sender": ["User: ...\nAssistant: ...", ...]}
        self._sender_contexts: dict[str, list[str]] = {}
        self._contexts_lock = threading.Lock()

    def set_soul_prompt(self, soul_prompt: str) -> None:
        """Set companion identity prompt prepended before turn content."""
        self.soul_prompt = soul_prompt.strip()

    def ensure_started(self) -> None:
        """No-op: CLI spawns a fresh process per turn."""
        pass

    def get_or_create_thread(self, sender: str) -> str:
        """Return synthetic thread id (sender)."""
        return sender

    def reset_thread(self, sender: str) -> str:
        """Clear sender context and return sender thread id."""
        with self._contexts_lock:
            self._sender_contexts.pop(sender, None)
        logger.info("Reset context for sender: %s", sender)
        return sender

    def _build_cmd(self, full_prompt: str) -> list[str]:
        """Assemble the gemini CLI command."""
        cmd = [self.gemini_command]
        if self.model:
            cmd.extend(["--model", self.model])
        cmd.extend(["-p", full_prompt])
        return cmd

    def run_turn(self, thread_id: str, prompt: str) -> str:
        """Execute a turn using `gemini -p`."""
        sender = thread_id
        full_prompt = self._build_prompt_with_context(sender, prompt)
        cmd = self._build_cmd(full_prompt)

        with self._contexts_lock:
            ctx_len = len(self._sender_contexts.get(sender, []))
        logger.info(
            "Executing Gemini CLI: sender=%s workspace=%s timeout=%.1fs context_items=%d",
            sender,
            self.workspace or "default",
            self.timeout,
            ctx_len,
        )

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                logger.error(
                    "Gemini exec failed: returncode=%d stderr=%s",
                    result.returncode,
                    error_msg,
                )
                return f"Error: Gemini execution failed (exit code {result.returncode}). Check logs for details."

            response = result.stdout.strip()
            if not response:
                logger.warning("Gemini exec returned empty response")
                response = "No response generated."

            self._store_exchange(sender, prompt, response)
            logger.info(
                "Gemini exec completed: sender=%s response_chars=%d",
                sender,
                len(response),
            )
            return response

        except subprocess.TimeoutExpired:
            logger.error(
                "Gemini exec timed out after %.1fs for sender=%s",
                self.timeout,
                sender,
            )
            return f"Error: Request timed out after {int(self.timeout)}s. Try a simpler request or increase apple_flow_codex_turn_timeout_seconds."
        except FileNotFoundError:
            logger.error("Gemini binary not found: %s", self.gemini_command)
            return (
                f"Error: Gemini CLI not found at '{self.gemini_command}'. "
                "Install with: npm install -g @google/gemini-cli"
            )
        except Exception as exc:
            logger.exception("Unexpected error during Gemini exec: %s", exc)
            return f"Error: {type(exc).__name__}: {exc}"

    def run_turn_streaming(self, thread_id: str, prompt: str, on_progress: Any = None) -> str:
        """Execute a turn with line-by-line streaming."""
        sender = thread_id
        full_prompt = self._build_prompt_with_context(sender, prompt)
        cmd = self._build_cmd(full_prompt)

        logger.info("Executing Gemini CLI (streaming): sender=%s", sender)

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
                logger.error("Gemini exec (streaming) failed: rc=%d", proc.returncode)
                return f"Error: Gemini execution failed (exit code {proc.returncode}). {error_msg}"

            response = "".join(output_lines).strip()
            if not response:
                response = "No response generated."

            self._store_exchange(sender, prompt, response)
            return response

        except subprocess.TimeoutExpired:
            proc.kill()
            logger.error("Gemini exec (streaming) timed out after %.1fs", self.timeout)
            return f"Error: Request timed out after {int(self.timeout)}s."
        except Exception as exc:
            logger.exception("Gemini streaming exec error: %s", exc)
            return self.run_turn(thread_id, prompt)

    def shutdown(self) -> None:
        """No-op: no persistent process to shut down."""
        logger.info("Gemini CLI connector shutdown (no-op)")

    def _build_prompt_with_context(self, sender: str, prompt: str) -> str:
        with self._contexts_lock:
            history = list(self._sender_contexts.get(sender, []))

        parts: list[str] = []

        if self.soul_prompt:
            parts.append(self.soul_prompt)

        if self.system_prompt:
            parts.append(self.system_prompt)

        # Keep Gemini responses user-facing for iMessage and avoid exposing
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

        parts.append(f"New message:\n{prompt}" if history or self.inject_tools_context else prompt)
        return "\n\n".join(parts)

    def _store_exchange(self, sender: str, user_message: str, assistant_response: str) -> None:
        exchange = f"User: {user_message}\nAssistant: {assistant_response}"
        max_history = self.context_window * 2
        with self._contexts_lock:
            if sender not in self._sender_contexts:
                self._sender_contexts[sender] = []
            self._sender_contexts[sender].append(exchange)
            if len(self._sender_contexts[sender]) > max_history:
                self._sender_contexts[sender] = self._sender_contexts[sender][-max_history:]
