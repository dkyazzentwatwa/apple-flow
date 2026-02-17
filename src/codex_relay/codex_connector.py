from __future__ import annotations

import json
import logging
import select
import subprocess
import threading
import time
import uuid
from typing import Any

logger = logging.getLogger("codex_relay.connector")


class CodexAppServerConnector:
    """JSON-RPC connector to a managed Codex App Server subprocess."""

    def __init__(self, command: list[str], turn_timeout_seconds: float = 90.0):
        self.command = command
        self.turn_timeout_seconds = turn_timeout_seconds
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._sender_threads: dict[str, str] = {}
        self._id_counter = 0
        self._initialized = False
        self._stderr_thread: threading.Thread | None = None
        self._shutdown_requested = False

    def ensure_started(self) -> None:
        if self._process and self._process.poll() is None:
            return

        self._process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._initialized = False
        self._shutdown_requested = False

        # Start stderr reader thread
        self._stderr_thread = threading.Thread(
            target=self._stderr_reader,
            daemon=True,
            name="codex-stderr-reader",
        )
        self._stderr_thread.start()

    def _stderr_reader(self) -> None:
        """Background thread to read and log stderr from the Codex subprocess."""
        if self._process is None or self._process.stderr is None:
            return

        try:
            for line in self._process.stderr:
                if self._shutdown_requested:
                    break
                line = line.rstrip()
                if line:
                    logger.warning("Codex subprocess: %s", line)
        except Exception as exc:
            if not self._shutdown_requested:
                logger.debug("Stderr reader stopped: %s", exc)

    def shutdown(self) -> None:
        """Gracefully shut down the Codex subprocess."""
        self._shutdown_requested = True
        with self._lock:
            if self._process is not None:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    logger.warning("Codex subprocess did not terminate, killing")
                    self._process.kill()
                    self._process.wait(timeout=2.0)
                except Exception as exc:
                    logger.warning("Error shutting down Codex subprocess: %s", exc)
                finally:
                    self._process = None
                    self._initialized = False

    def _next_id(self) -> int:
        self._id_counter += 1
        return self._id_counter

    @staticmethod
    def _format_rpc_error(error_obj: Any) -> str:
        return f"Codex RPC error: {error_obj}"

    def _send_jsonrpc_locked(self, method: str, params: dict[str, Any], timeout_seconds: float = 15.0) -> dict[str, Any]:
        self.ensure_started()
        assert self._process is not None
        assert self._process.stdin is not None
        assert self._process.stdout is not None

        request_id = self._next_id()
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        self._process.stdin.write(json.dumps(payload) + "\n")
        self._process.stdin.flush()

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            ready, _, _ = select.select([self._process.stdout], [], [], 0.5)
            if not ready:
                continue
            line = self._process.stdout.readline()
            if not line:
                continue
            event = json.loads(line)
            if event.get("id") != request_id:
                continue
            if "error" in event:
                raise RuntimeError(self._format_rpc_error(event["error"]))
            return event.get("result", {})

        raise RuntimeError(f"Timeout waiting for Codex RPC response: method={method}")

    def _drain_stdout_locked(self, max_seconds: float = 0.2) -> int:
        """
        Drain already-buffered events before starting a new turn.
        This avoids consuming stale events from a previous turn as if they were new.
        """
        self.ensure_started()
        assert self._process is not None
        assert self._process.stdout is not None

        drained = 0
        deadline = time.time() + max_seconds
        while time.time() < deadline:
            ready, _, _ = select.select([self._process.stdout], [], [], 0.02)
            if not ready:
                continue
            line = self._process.stdout.readline()
            if not line:
                continue
            drained += 1
        return drained

    def _initialize_locked(self) -> None:
        if self._initialized:
            return
        self._send_jsonrpc_locked(
            "initialize",
            {
                "clientInfo": {
                    "name": "codex-relay",
                    "version": "0.1.0",
                }
            },
            timeout_seconds=60.0,  # Give Codex more time to start up
        )
        self._initialized = True

    def get_or_create_thread(self, sender: str) -> str:
        if sender in self._sender_threads:
            return self._sender_threads[sender]

        with self._lock:
            self.ensure_started()
            self._initialize_locked()

            thread_id: str | None = None
            try:
                result = self._send_jsonrpc_locked("thread/start", {})
                thread_id = result.get("thread", {}).get("id")
            except RuntimeError as exc:
                error_text = str(exc)
                if "unknown variant `thread/start`" not in error_text:
                    raise

            if not thread_id:
                try:
                    result = self._send_jsonrpc_locked("newConversation", {})
                    thread_id = result.get("conversationId")
                except RuntimeError:
                    result = self._send_jsonrpc_locked("create_thread", {})
                    thread_id = result.get("thread_id") or result.get("id")

            if not thread_id:
                thread_id = str(uuid.uuid4())

            self._sender_threads[sender] = thread_id
            return thread_id

    def reset_thread(self, sender: str) -> str:
        with self._lock:
            self._sender_threads.pop(sender, None)
        return self.get_or_create_thread(sender)

    def run_turn(self, thread_id: str, prompt: str) -> str:
        with self._lock:
            self.ensure_started()
            self._initialize_locked()
            assert self._process is not None
            assert self._process.stdin is not None
            assert self._process.stdout is not None

            self._drain_stdout_locked()
            request_id = self._next_id()
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "turn/start",
                "params": {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": prompt}],
                },
            }
            self._process.stdin.write(json.dumps(payload) + "\n")
            self._process.stdin.flush()

            content_buffer: list[str] = []
            last_agent_message = ""
            ack_seen = False
            saw_assistant_activity = False
            expected_task_id: str | None = None
            deadline = time.time() + self.turn_timeout_seconds

            while time.time() < deadline:
                ready, _, _ = select.select([self._process.stdout], [], [], 0.5)
                if not ready:
                    continue

                line = self._process.stdout.readline()
                if not line:
                    continue

                event = json.loads(line)

                if event.get("id") == request_id:
                    ack_seen = True
                    if "error" in event:
                        err = event["error"]
                        msg = str(err)
                        if "unknown variant `turn/start`" in msg:
                            return self._run_turn_legacy_locked(thread_id, prompt)
                        raise RuntimeError(self._format_rpc_error(err))
                    result = event.get("result", {})
                    if isinstance(result, dict):
                        task_id = result.get("taskId") or result.get("task_id") or result.get("id")
                        if isinstance(task_id, str) and task_id.strip():
                            expected_task_id = task_id
                    continue

                method = event.get("method", "")
                params = event.get("params", {})
                conversation_id = params.get("conversationId")
                if conversation_id and conversation_id != thread_id:
                    continue

                msg = params.get("msg", {})
                msg_type = msg.get("type") if isinstance(msg, dict) else None
                event_task_id = None
                if isinstance(params, dict):
                    event_task_id = params.get("taskId") or params.get("task_id")
                if event_task_id is None and isinstance(msg, dict):
                    event_task_id = msg.get("id") or msg.get("taskId") or msg.get("task_id")
                if expected_task_id and event_task_id and event_task_id != expected_task_id:
                    continue

                if method == "codex/event/agent_message_content_delta":
                    delta = msg.get("delta", "") if isinstance(msg, dict) else ""
                    if delta:
                        saw_assistant_activity = True
                        content_buffer.append(delta)
                elif method == "codex/event/agent_message":
                    if isinstance(msg, dict):
                        text = msg.get("message") or msg.get("text") or ""
                        if text:
                            saw_assistant_activity = True
                            last_agent_message = text
                elif method == "codex/event/task_complete" or msg_type == "task_complete":
                    if not saw_assistant_activity and not content_buffer and not last_agent_message:
                        # Likely stale completion from a previous turn; keep waiting for activity.
                        continue
                    if isinstance(msg, dict):
                        final = msg.get("last_agent_message") or ""
                        if final:
                            return str(final).strip()
                    if last_agent_message:
                        return last_agent_message.strip()
                    if content_buffer:
                        return "".join(content_buffer).strip()
                    if ack_seen:
                        return "Done."

            if last_agent_message:
                return last_agent_message.strip()
            if content_buffer:
                return "".join(content_buffer).strip()
            return "No response captured before timeout."

    def _run_turn_legacy_locked(self, thread_id: str, prompt: str) -> str:
        assert self._process is not None
        assert self._process.stdin is not None
        assert self._process.stdout is not None

        self._drain_stdout_locked()
        request_id = self._next_id()
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "create_turn",
            "params": {
                "thread_id": thread_id,
                "message": prompt,
            },
        }
        self._process.stdin.write(json.dumps(payload) + "\n")
        self._process.stdin.flush()

        text_fragments: list[str] = []
        deadline = time.time() + self.turn_timeout_seconds
        while time.time() < deadline:
            ready, _, _ = select.select([self._process.stdout], [], [], 0.5)
            if not ready:
                continue
            line = self._process.stdout.readline()
            if not line:
                continue
            event = json.loads(line)

            if event.get("id") == request_id and "error" in event:
                raise RuntimeError(f"Codex create_turn error: {event['error']}")

            if event.get("method") != "event":
                continue

            params = event.get("params", {})
            event_type = params.get("type")
            if event_type == "assistant_message_delta":
                content = params.get("content", "")
                if content:
                    text_fragments.append(content)
            elif event_type == "turn_complete":
                break

        return "".join(text_fragments).strip() or "Done."
