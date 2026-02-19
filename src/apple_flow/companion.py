"""Companion loop — proactive observations, daily digest, and weekly review.

The companion periodically scans the user's environment (calendar, reminders,
approvals, agent-office inbox) and sends synthesized, natural-language messages
via iMessage.  It also handles daily digest (morning briefing) and weekly
review sub-loops.

All reads are non-mutating; outbound messages go through the existing egress
with dedup/chunking support.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .config import RelaySettings
    from .memory import FileMemory
    from .protocols import ConnectorProtocol, EgressProtocol, StoreProtocol
    from .scheduler import FollowUpScheduler

logger = logging.getLogger("apple_flow.companion")


class CompanionLoop:
    """Proactive companion that observes the user's environment and sends updates."""

    def __init__(
        self,
        connector: ConnectorProtocol,
        egress: EgressProtocol,
        store: StoreProtocol,
        owner: str,
        soul_prompt: str,
        office_path: Path | None,
        config: RelaySettings,
        scheduler: FollowUpScheduler | None = None,
        memory: FileMemory | None = None,
    ):
        self.connector = connector
        self.egress = egress
        self.store = store
        self.owner = owner
        self.soul_prompt = soul_prompt
        self.office_path = office_path
        self.config = config
        self.scheduler = scheduler
        self.memory = memory

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run_forever(self, is_shutdown: Callable[[], bool]) -> None:
        """Run observation + digest + weekly review loops concurrently."""
        tasks = [self._observation_loop(is_shutdown)]
        if self.config.companion_enable_daily_digest:
            tasks.append(self._daily_digest_loop(is_shutdown))
        if self.config.enable_companion:
            tasks.append(self._weekly_review_loop(is_shutdown))
        await asyncio.gather(*tasks)

    # ------------------------------------------------------------------
    # Observation loop
    # ------------------------------------------------------------------

    async def _observation_loop(self, is_shutdown: Callable[[], bool]) -> None:
        logger.info("Companion observation loop started (poll=%.0fs)", self.config.companion_poll_interval_seconds)
        while not is_shutdown():
            try:
                await asyncio.to_thread(self._check_and_notify)
            except Exception as exc:
                logger.exception("Companion observation error: %s", exc)
            await asyncio.sleep(self.config.companion_poll_interval_seconds)

    def _check_and_notify(self) -> None:
        """Gather observations, synthesize a message, and send if warranted."""
        if self._is_muted():
            return
        if self._is_quiet_hours():
            return
        if self._is_rate_limited():
            return

        observations = self._gather_observations()

        # Check scheduled follow-ups
        if self.scheduler:
            due_actions = self.scheduler.check_due()
            for action in due_actions:
                observations.append(
                    f"Scheduled follow-up ({action['action_type']}): {action.get('payload', {}).get('summary', 'check-in')}"
                )
                self.scheduler.mark_fired(action["action_id"])

        if not observations:
            return

        message = self._synthesize_message(observations)
        if message:
            self.egress.send(self.owner, message)
            self._record_proactive_send()
            self._log_to_office("observation", observations, message)

    def _gather_observations(self) -> list[str]:
        """Collect notable observations from the user's environment."""
        observations: list[str] = []

        # 1. Stale approvals
        try:
            pending = self.store.list_pending_approvals()
            stale_minutes = self.config.companion_stale_approval_minutes
            for approval in pending:
                created_at = approval.get("created_at", "")
                if created_at:
                    try:
                        created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        age_minutes = (datetime.now(created_dt.tzinfo) - created_dt).total_seconds() / 60
                        if age_minutes >= stale_minutes:
                            req_id = approval.get("request_id", "?")
                            preview = (approval.get("command_preview", "") or "")[:80].replace("\n", " ")
                            observations.append(
                                f"Stale approval {req_id} ({int(age_minutes)} min old): {preview}"
                            )
                    except (ValueError, TypeError):
                        pass
        except Exception as exc:
            logger.debug("Failed to check approvals: %s", exc)

        # 2. Upcoming calendar events — only within lookahead window, cooldown per event
        try:
            from . import apple_tools
            lookahead = self.config.companion_calendar_lookahead_minutes
            events = apple_tools.calendar_list_events(days_ahead=1, limit=20)
            if isinstance(events, list):
                now = datetime.now()
                cutoff = now + timedelta(minutes=lookahead)
                for evt in events:
                    start_str = evt.get("start_date", "")
                    summary = evt.get("summary", "")
                    if not (start_str and summary):
                        continue
                    try:
                        start_dt = datetime.fromisoformat(start_str)
                        if not (now <= start_dt <= cutoff):
                            continue
                    except (ValueError, TypeError):
                        continue
                    cooldown_key = f"companion_evt_{summary[:40]}_{start_str[:16]}"
                    if self.store.get_state(cooldown_key):
                        continue
                    self.store.set_state(cooldown_key, "1")
                    minutes_away = int((start_dt - now).total_seconds() / 60)
                    observations.append(f"Upcoming event in {minutes_away}m: {summary}")
        except Exception as exc:
            logger.debug("Failed to check calendar: %s", exc)

        # 3. Overdue reminders — due < now, scoped to reminders_list_name, cooldown per item
        try:
            from . import apple_tools
            reminders = apple_tools.reminders_list(filter="incomplete", limit=20)
            if isinstance(reminders, list):
                now = datetime.now()
                for rem in reminders:
                    due = rem.get("due_date", "")
                    name = rem.get("name", "")
                    list_name = rem.get("list", "")
                    if not (due and name):
                        continue
                    # Scope to the configured reminders list
                    if list_name and list_name != self.config.reminders_list_name:
                        continue
                    try:
                        due_dt = datetime.fromisoformat(due)
                        if due_dt >= now:
                            continue
                    except (ValueError, TypeError):
                        continue
                    cooldown_key = f"companion_rem_{name[:40]}_{due[:10]}"
                    if self.store.get_state(cooldown_key):
                        continue
                    self.store.set_state(cooldown_key, "1")
                    observations.append(f"Overdue reminder: {name} (was due: {due[:10]})")
        except Exception as exc:
            logger.debug("Failed to check reminders: %s", exc)

        # 5. Office inbox check
        if self.office_path:
            inbox_path = self.office_path / "00_inbox" / "inbox.md"
            if inbox_path.exists():
                try:
                    content = inbox_path.read_text(encoding="utf-8")
                    unchecked = self._count_untriaged_inbox_items(content)
                    if unchecked > 0:
                        observations.append(f"{unchecked} untriaged item(s) in agent-office inbox")
                except Exception as exc:
                    logger.debug("Failed to read office inbox: %s", exc)

        # 6. Cross-channel intelligence — group related items by keyword overlap
        observations = self._cross_channel_correlate(observations)

        return observations

    @staticmethod
    def _count_untriaged_inbox_items(content: str) -> int:
        """Count unchecked markdown tasks in real inbox entries.

        If an ``## Entries`` section exists, only count task lines in that section
        so template examples (for example in ``## Entry Format``) are ignored.
        Otherwise, fall back to counting unchecked task lines across the file.
        """
        unchecked_pattern = re.compile(r"^\s*-\s\[\s\]\s+")
        lines = content.splitlines()

        # Prefer scoped counting within the Entries section when present.
        in_entries = False
        saw_entries_header = False
        scoped_count = 0
        for raw_line in lines:
            line = raw_line.strip()
            if line.lower() == "## entries":
                saw_entries_header = True
                in_entries = True
                continue
            if in_entries and line.startswith("## "):
                in_entries = False
            if in_entries and unchecked_pattern.match(raw_line):
                scoped_count += 1

        if saw_entries_header:
            return scoped_count

        # Backward-compatible fallback for older inbox formats.
        return sum(1 for line in lines if unchecked_pattern.match(line))

    def _cross_channel_correlate(self, observations: list[str]) -> list[str]:
        """Detect related items across channels and annotate them."""
        if len(observations) < 2:
            return observations

        # Extract keywords (3+ char words) from each observation
        keyword_map: dict[str, list[int]] = {}
        for idx, obs in enumerate(observations):
            words = set(
                w.lower() for w in obs.split()
                if len(w) >= 4 and w.isalpha()
            )
            # Skip very common words
            words -= {"with", "from", "this", "that", "have", "been", "will", "your", "task", "item"}
            for word in words:
                keyword_map.setdefault(word, []).append(idx)

        # Find clusters (keywords appearing in 2+ observations)
        clustered_indices: set[int] = set()
        cluster_keywords: list[str] = []
        for keyword, indices in keyword_map.items():
            if len(indices) >= 2:
                clustered_indices.update(indices)
                cluster_keywords.append(keyword)

        if not clustered_indices or not cluster_keywords:
            return observations

        # Annotate the first observation in the cluster with a cross-channel note
        result = list(observations)
        first_idx = min(clustered_indices)
        related_count = len(clustered_indices) - 1
        keywords_str = ", ".join(sorted(set(cluster_keywords))[:3])
        result[first_idx] += f" [related to {related_count} other item(s) — keywords: {keywords_str}]"
        return result

    def _synthesize_message(self, observations: list[str]) -> str:
        """Pass observations to the AI for natural-language synthesis."""
        obs_text = "\n".join(f"- {obs}" for obs in observations)

        # Include memory context if available
        memory_context = ""
        if self.memory:
            try:
                memory_context = self.memory.get_context_for_prompt()
                if memory_context:
                    memory_context = f"\n\nUser memory context:\n{memory_context}"
            except Exception:
                pass

        synthesis_prompt = (
            "You are the user's AI companion. Based on these observations about their environment, "
            "compose a brief, helpful message. Be conversational, not robotic. Only mention things "
            "that seem worth mentioning. If nothing is truly notable, return exactly the word EMPTY "
            "(nothing else).\n\n"
            f"Observations:\n{obs_text}{memory_context}"
        )

        try:
            thread_id = self.connector.get_or_create_thread(f"__companion__{self.owner}")
            response = self.connector.run_turn(thread_id, synthesis_prompt)
            if response.strip().upper() == "EMPTY":
                return ""
            return response.strip()
        except Exception as exc:
            logger.warning("Companion synthesis failed: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # Daily digest
    # ------------------------------------------------------------------

    async def _daily_digest_loop(self, is_shutdown: Callable[[], bool]) -> None:
        logger.info("Daily digest loop started (time=%s)", self.config.companion_digest_time)
        while not is_shutdown():
            try:
                if self._is_digest_time() and not self._digest_sent_today():
                    digest = await asyncio.to_thread(self._build_daily_digest)
                    if digest:
                        self.egress.send(self.owner, digest)
                        self.store.set_state("companion_last_digest_date", date.today().isoformat())
                        self._write_daily_note(digest)
                        self._log_to_office("daily_digest", [], digest)
                        logger.info("Daily digest sent")
            except Exception as exc:
                logger.exception("Daily digest error: %s", exc)
            await asyncio.sleep(60)  # Check every minute

    def _is_digest_time(self) -> bool:
        """Check if current time matches the configured digest time (within 1 minute)."""
        try:
            parts = self.config.companion_digest_time.split(":")
            target = time(int(parts[0]), int(parts[1]))
            now = datetime.now().time()
            return abs(
                (now.hour * 60 + now.minute) - (target.hour * 60 + target.minute)
            ) <= 1
        except (ValueError, IndexError):
            return False

    def _digest_sent_today(self) -> bool:
        last = self.store.get_state("companion_last_digest_date")
        return last == date.today().isoformat()

    def _build_daily_digest(self) -> str:
        """Gather information and produce a morning briefing."""
        sections: list[str] = []

        # Today's calendar events
        try:
            from . import apple_tools
            events = apple_tools.calendar_list_events(days_ahead=1, limit=10)
            if isinstance(events, list) and events:
                lines = ["Today's calendar:"]
                for evt in events:
                    lines.append(f"  - {evt.get('start_date', '?')} {evt.get('summary', '')}")
                sections.append("\n".join(lines))
        except Exception:
            pass

        # Incomplete reminders
        try:
            from . import apple_tools
            reminders = apple_tools.reminders_list(filter="incomplete", limit=10)
            if isinstance(reminders, list) and reminders:
                lines = [f"Open reminders ({len(reminders)}):"]
                for rem in reminders[:5]:
                    due = f" (due: {rem['due_date']})" if rem.get("due_date") else ""
                    lines.append(f"  - {rem.get('name', '?')}{due}")
                if len(reminders) > 5:
                    lines.append(f"  ... and {len(reminders) - 5} more")
                sections.append("\n".join(lines))
        except Exception:
            pass

        # Pending approvals
        try:
            pending = self.store.list_pending_approvals()
            if pending:
                lines = [f"Pending approvals ({len(pending)}):"]
                for a in pending:
                    lines.append(f"  - {a.get('request_id', '?')}: {(a.get('command_preview', '') or '')[:60]}")
                sections.append("\n".join(lines))
        except Exception:
            pass

        # Yesterday's stats
        try:
            if hasattr(self.store, "get_stats"):
                stats = self.store.get_stats()
                sections.append(
                    f"Stats: {stats.get('total_messages', '?')} messages, "
                    f"{stats.get('active_sessions', '?')} sessions"
                )
        except Exception:
            pass

        # Memory context
        if self.memory:
            try:
                mem = self.memory.read_durable()
                if mem:
                    sections.append(f"Memory snapshot:\n{mem[:500]}")
            except Exception:
                pass

        if not sections:
            return ""

        gathered = "\n\n".join(sections)
        synthesis_prompt = (
            "You are the user's AI companion delivering a morning briefing. "
            "Synthesize these items into a concise, friendly daily digest. "
            "Start with the most actionable items. Keep it short for iMessage.\n\n"
            f"{gathered}"
        )

        try:
            thread_id = self.connector.get_or_create_thread(f"__digest__{self.owner}")
            return self.connector.run_turn(thread_id, synthesis_prompt).strip()
        except Exception as exc:
            logger.warning("Digest synthesis failed: %s", exc)
            return ""

    def _write_daily_note(self, digest: str) -> None:
        """Write digest to agent-office/10_daily/YYYY-MM-DD.md."""
        if not self.office_path:
            return
        daily_dir = self.office_path / "10_daily"
        if not daily_dir.exists():
            return
        note_path = daily_dir / f"{date.today().isoformat()}.md"
        try:
            template_path = self.office_path / "templates" / "daily-note.md"
            if template_path.exists():
                content = template_path.read_text(encoding="utf-8")
                content = content.replace("{{date}}", date.today().isoformat())
            else:
                content = f"# Daily Note — {date.today().isoformat()}\n\n"
            content += f"\n## Morning Briefing\n{digest}\n"
            note_path.write_text(content, encoding="utf-8")
            logger.info("Daily note written to %s", note_path)
        except Exception as exc:
            logger.warning("Failed to write daily note: %s", exc)

    # ------------------------------------------------------------------
    # Weekly review
    # ------------------------------------------------------------------

    async def _weekly_review_loop(self, is_shutdown: Callable[[], bool]) -> None:
        logger.info(
            "Weekly review loop started (day=%s, time=%s)",
            self.config.companion_weekly_review_day,
            self.config.companion_weekly_review_time,
        )
        while not is_shutdown():
            try:
                if self._is_weekly_review_time() and not self._weekly_review_sent_this_week():
                    review = await asyncio.to_thread(self._build_weekly_review)
                    if review:
                        self.egress.send(self.owner, review)
                        self.store.set_state(
                            "companion_last_weekly_review",
                            datetime.now().strftime("%Y-W%W"),
                        )
                        self._log_to_office("weekly_review", [], review)
                        logger.info("Weekly review sent")
            except Exception as exc:
                logger.exception("Weekly review error: %s", exc)
            await asyncio.sleep(60)

    def _is_weekly_review_time(self) -> bool:
        now = datetime.now()
        day_name = now.strftime("%A").lower()
        if day_name != self.config.companion_weekly_review_day.lower():
            return False
        try:
            parts = self.config.companion_weekly_review_time.split(":")
            target = time(int(parts[0]), int(parts[1]))
            return abs(
                (now.time().hour * 60 + now.time().minute) - (target.hour * 60 + target.minute)
            ) <= 1
        except (ValueError, IndexError):
            return False

    def _weekly_review_sent_this_week(self) -> bool:
        last = self.store.get_state("companion_last_weekly_review")
        return last == datetime.now().strftime("%Y-W%W")

    def _build_weekly_review(self) -> str:
        """Gather information and produce a weekly review summary."""
        sections: list[str] = []

        try:
            if hasattr(self.store, "get_stats"):
                stats = self.store.get_stats()
                runs = stats.get("runs_by_state", {})
                completed = runs.get("completed", 0)
                failed = runs.get("failed", 0)
                denied = runs.get("denied", 0)
                sections.append(
                    f"Week stats: {stats.get('total_messages', '?')} messages, "
                    f"{completed} completed, {failed} failed, {denied} denied"
                )
        except Exception:
            pass

        try:
            pending = self.store.list_pending_approvals()
            if pending:
                sections.append(f"Open items: {len(pending)} pending approvals")
        except Exception:
            pass

        if self.memory:
            try:
                mem = self.memory.read_durable()
                if mem:
                    sections.append(f"Memory:\n{mem[:500]}")
            except Exception:
                pass

        if not sections:
            return ""

        gathered = "\n\n".join(sections)
        synthesis_prompt = (
            "You are the user's AI companion delivering a weekly review. "
            "Synthesize these items into a concise summary of the week. "
            "Highlight wins, open items, and suggestions for next week.\n\n"
            f"{gathered}"
        )

        try:
            thread_id = self.connector.get_or_create_thread(f"__weekly__{self.owner}")
            return self.connector.run_turn(thread_id, synthesis_prompt).strip()
        except Exception as exc:
            logger.warning("Weekly review synthesis failed: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # Rate limiting & quiet hours
    # ------------------------------------------------------------------

    def _is_muted(self) -> bool:
        return self.store.get_state("companion_muted") == "true"

    def _is_quiet_hours(self) -> bool:
        try:
            now = datetime.now().time()
            start_parts = self.config.companion_quiet_hours_start.split(":")
            end_parts = self.config.companion_quiet_hours_end.split(":")
            quiet_start = time(int(start_parts[0]), int(start_parts[1]))
            quiet_end = time(int(end_parts[0]), int(end_parts[1]))

            if quiet_start <= quiet_end:
                # Same-day range (e.g. 13:00–17:00)
                return quiet_start <= now <= quiet_end
            else:
                # Overnight range (e.g. 22:00–07:00)
                return now >= quiet_start or now <= quiet_end
        except (ValueError, IndexError):
            return False

    def _is_rate_limited(self) -> bool:
        """Check if we've exceeded the max proactive messages per hour."""
        key = "companion_proactive_hour_count"
        hour_key = "companion_proactive_hour"
        current_hour = datetime.now().strftime("%Y-%m-%d-%H")

        stored_hour = self.store.get_state(hour_key)
        if stored_hour != current_hour:
            # New hour, reset counter
            self.store.set_state(hour_key, current_hour)
            self.store.set_state(key, "0")
            return False

        count_str = self.store.get_state(key) or "0"
        try:
            count = int(count_str)
        except ValueError:
            count = 0
        return count >= self.config.companion_max_proactive_per_hour

    def _record_proactive_send(self) -> None:
        key = "companion_proactive_hour_count"
        hour_key = "companion_proactive_hour"
        current_hour = datetime.now().strftime("%Y-%m-%d-%H")
        # Ensure hour key is set
        self.store.set_state(hour_key, current_hour)
        count_str = self.store.get_state(key) or "0"
        try:
            count = int(count_str)
        except ValueError:
            count = 0
        self.store.set_state(key, str(count + 1))

    # ------------------------------------------------------------------
    # Office logging
    # ------------------------------------------------------------------

    def _log_to_office(self, action: str, observations: list[str], message: str) -> None:
        """Append a log entry to agent-office/90_logs/automation-log.md."""
        if not self.office_path:
            return
        log_path = self.office_path / "90_logs" / "automation-log.md"
        if not log_path.exists():
            return
        try:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            obs_count = len(observations)
            msg_preview = message[:80].replace("\n", " ")
            entry = f"- {now_str} | companion | {action} | {obs_count} obs | {msg_preview}\n"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception as exc:
            logger.debug("Failed to log to office: %s", exc)
