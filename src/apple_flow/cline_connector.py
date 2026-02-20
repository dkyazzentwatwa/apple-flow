from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

logger = logging.getLogger("apple_flow.cline_connector")


class ClineConnector:
    """Cline CLI connector using `cline -y` for agentic execution.

    This connector leverages the Cline CLI to provide full agentic tool-use
    (file reads/writes, shell commands, browser) with any model provider
    (Anthropic, OpenAI, Ollama, DeepSeek, Gemini, Groq, etc.).

    Each turn spawns a fresh `cline -y` process that auto-approves all
    actions and exits when complete.
    """

    def __init__(
        self,
        cline_command: str = "cline",
        workspace: str | None = None,
        timeout: float = 300.0,
        context_window: int = 3,
        model: str = "",
        use_json: bool = True,
        act_mode: bool = True,
    ):
        """Initialize the Cline CLI connector.

        Args:
            cline_command: Path to the cline binary (default: "cline")
            workspace: Working directory for cline -c (default: None)
            timeout: Timeout in seconds for each exec (default: 300s/5min)
            context_window: Number of recent message pairs to include as context (default: 3)
            model: Model to use (e.g., "claude-sonnet-4-5-20250929", "gpt-4o"). Empty = cline default
            use_json: Use --json flag for structured NDJSON output (default: True)
            act_mode: Use -a flag to skip plan mode and go straight to execution (default: True)
        """
        self.cline_command = cline_command
        self.workspace = workspace
        self.timeout = timeout
        self.context_window = context_window
        self.model = model.strip()
        self.use_json = use_json
        self.act_mode = act_mode

        # Store minimal conversation history per sender for context
        # Format: {"sender": ["User: ...\nAssistant: ...", ...]}
        self._sender_contexts: dict[str, list[str]] = {}

    def _build_cmd(self, full_prompt: str) -> list[str]:
        """Assemble the cline CLI command."""
        cmd = [self.cline_command, "-y"]  # auto-approve all actions
        if self.act_mode:
            cmd.append("-a")  # skip plan mode, go straight to execution
        if self.use_json:
            cmd.append("--json")
        if self.model:
            cmd.extend(["-m", self.model])
        if self.workspace:
            cmd.extend(["-c", self.workspace])
        if self.timeout:
            cmd.extend(["--timeout", str(int(self.timeout))])
        cmd.append(full_prompt)
        return cmd

    def _parse_json_output(self, raw_output: str) -> str:
        """Parse NDJSON output from cline --json and extract final text.

        Cline outputs one JSON object per line with format:
        {"type": "say"|"ask", "text": "...", "say": "text"|"completion_result"|..., "ts": ...}

        Priority: prefer the final completion_result (the actual answer) over
        intermediate say/text messages (status narration emitted during tool use).
        """
        completion_result: str = ""
        text_parts: list[str] = []

        for line in raw_output.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            if obj.get("type") != "say" or obj.get("partial", False):
                continue

            text = obj.get("text", "").strip()
            if not text:
                continue

            say = obj.get("say", "")
            if say == "completion_result":
                # This is the definitive final answer — always prefer it
                completion_result = text
            elif say == "text":
                text_parts.append(text)

        # Prefer completion_result; fall back to last intermediate say/text
        if completion_result:
            return completion_result
        if text_parts:
            return text_parts[-1]
        return ""

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
        """Execute a turn using `cline -y`.

        Builds a context-aware prompt from recent history, spawns a fresh
        `cline -y` process, captures output, and stores the exchange.
        Retries once on transient failures (exit code 1 from API errors).

        Args:
            thread_id: Sender identifier (used as thread ID)
            prompt: User's message/prompt

        Returns:
            Cline's response text
        """
        sender = thread_id
        full_prompt = self._build_prompt_with_context(sender, prompt)
        cmd = self._build_cmd(full_prompt)

        max_attempts = 2
        last_error = ""

        for attempt in range(1, max_attempts + 1):
            logger.info(
                "Executing Cline CLI: sender=%s workspace=%s timeout=%.1fs model=%s context_items=%d attempt=%d/%d",
                sender,
                self.workspace or "default",
                self.timeout,
                self.model or "default",
                len(self._sender_contexts.get(sender, [])),
                attempt,
                max_attempts,
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
                    error_detail = self._extract_error(result)
                    logger.error(
                        "Cline exec failed (attempt %d/%d): returncode=%d error=%r stdout_len=%d",
                        attempt,
                        max_attempts,
                        result.returncode,
                        error_detail[:300],
                        len(result.stdout or ""),
                    )
                    last_error = error_detail
                    if attempt < max_attempts:
                        import time as _time
                        _time.sleep(2)
                        continue
                    short_detail = (last_error[:200] + "...") if len(last_error) > 200 else last_error
                    return f"Error: Cline execution failed (exit code {result.returncode}): {short_detail}"

                # Parse response based on output mode
                if self.use_json:
                    response = self._parse_json_output(result.stdout)
                else:
                    response = result.stdout.strip()

                if not response:
                    logger.warning("Cline exec returned empty response")
                    response = "No response generated."

                self._store_exchange(sender, prompt, response)

                logger.info(
                    "Cline exec completed: sender=%s response_chars=%d",
                    sender,
                    len(response),
                )

                return response

            except subprocess.TimeoutExpired:
                logger.error(
                    "Cline exec timed out after %.1fs for sender=%s",
                    self.timeout,
                    sender,
                )
                return f"Error: Request timed out after {int(self.timeout)}s. Try a simpler request or increase apple_flow_codex_turn_timeout_seconds."
            except FileNotFoundError:
                logger.error("Cline binary not found: %s", self.cline_command)
                return f"Error: Cline CLI not found at '{self.cline_command}'. Install with: npm install -g cline"
            except Exception as exc:
                logger.exception("Unexpected error during Cline exec: %s", exc)
                return f"Error: {type(exc).__name__}: {exc}"

        # Should not reach here, but safety net
        return f"Error: Cline execution failed after {max_attempts} attempts: {last_error[:200]}"

    def _extract_error(self, result: subprocess.CompletedProcess[str]) -> str:
        """Extract a meaningful error message from a failed cline run."""
        stderr_msg = result.stderr.strip() if result.stderr else ""
        stdout_error = ""
        if result.stdout:
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if obj.get("say") == "error" or obj.get("type") == "error":
                        stdout_error = obj.get("text", "") or obj.get("error", "")
                    elif obj.get("say") == "text" and obj.get("text"):
                        stdout_error = obj["text"]
                except json.JSONDecodeError:
                    if not stdout_error:
                        stdout_error = line[:500]
        return stderr_msg or stdout_error or "no output (empty stderr + stdout)"

    def run_turn_streaming(self, thread_id: str, prompt: str, on_progress: Any = None) -> str:
        """Execute a turn with line-by-line streaming, calling on_progress for each line.

        Falls back to regular run_turn if streaming fails.
        """
        sender = thread_id
        full_prompt = self._build_prompt_with_context(sender, prompt)
        cmd = self._build_cmd(full_prompt)

        logger.info("Executing Cline CLI (streaming): sender=%s", sender)

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
                    # For JSON mode, try to extract text for progress
                    if self.use_json:
                        try:
                            obj = json.loads(line.strip())
                            if obj.get("type") == "say" and obj.get("say") == "text":
                                on_progress(obj.get("text", ""))
                        except (json.JSONDecodeError, AttributeError):
                            on_progress(line)
                    else:
                        on_progress(line)

            proc.wait(timeout=self.timeout)

            if proc.returncode != 0:
                error_msg = proc.stderr.read() if proc.stderr else "Unknown error"
                logger.error("Cline exec (streaming) failed: rc=%d", proc.returncode)
                return f"Error: Cline execution failed (exit code {proc.returncode}). {error_msg}"

            raw_output = "".join(output_lines)
            if self.use_json:
                response = self._parse_json_output(raw_output)
            else:
                response = raw_output.strip()

            if not response:
                response = "No response generated."

            self._store_exchange(sender, prompt, response)
            return response

        except subprocess.TimeoutExpired:
            proc.kill()
            logger.error("Cline exec (streaming) timed out after %.1fs", self.timeout)
            return f"Error: Request timed out after {int(self.timeout)}s."
        except Exception as exc:
            logger.exception("Streaming exec error: %s", exc)
            # Fall back to regular execution
            return self.run_turn(thread_id, prompt)

    def shutdown(self) -> None:
        """No-op: no persistent process to shut down."""
        logger.info("Cline CLI connector shutdown (no-op)")

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
