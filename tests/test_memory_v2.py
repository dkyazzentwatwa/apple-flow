"""Tests for canonical memory v2 rollout components."""

from __future__ import annotations

import time
from pathlib import Path

from apple_flow.memory_v2 import CanonicalMemoryStore, MemoryService, resolve_or_create_project_id


def test_project_id_file_is_stable(tmp_path):
    office = tmp_path / "agent-office"
    office.mkdir()

    first = resolve_or_create_project_id(office)
    second = resolve_or_create_project_id(office)

    assert first
    assert first == second
    assert (office / ".apple-flow-project").exists()


def test_store_retrieval_prefers_salience_and_recency(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    store = CanonicalMemoryStore(db_path)
    store.bootstrap()
    project_id = "p1"

    store.upsert(
        project_id=project_id,
        scope="global",
        topic="low",
        content="older low salience",
        source="test",
        salience=10,
        dedupe_key="low",
    )
    time.sleep(0.01)
    store.upsert(
        project_id=project_id,
        scope="global",
        topic="high",
        content="newer high salience",
        source="test",
        salience=90,
        dedupe_key="high",
    )

    entries = store.retrieve(project_id=project_id, scope="global")

    assert entries
    assert entries[0].topic == "high"
    assert any(entry.topic == "low" for entry in entries)
    store.close()


def test_store_prunes_expired_entries(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    store = CanonicalMemoryStore(db_path)
    store.bootstrap()
    project_id = "p2"

    store.upsert(
        project_id=project_id,
        scope="global",
        topic="expiring",
        content="ephemeral",
        source="test",
        salience=20,
        ttl_seconds=1,
        dedupe_key="expiring",
    )

    time.sleep(1.1)
    deleted = store.prune_expired(project_id=project_id)
    entries = store.retrieve(project_id=project_id, scope="global")

    assert deleted >= 1
    assert entries == []
    store.close()


def test_memory_service_backfills_from_legacy(tmp_path):
    office = tmp_path / "agent-office"
    office.mkdir()
    (office / "MEMORY.md").write_text("## Identity\n- Likes concise updates\n", encoding="utf-8")
    mem_dir = office / "60_memory"
    mem_dir.mkdir()
    (mem_dir / "deploy.md").write_text("# Deploy\n- v1 shipped\n", encoding="utf-8")

    svc = MemoryService(
        office_path=office,
        db_path=tmp_path / "memory.sqlite3",
        enabled=True,
        shadow_mode=False,
        max_context_chars=2000,
    )
    svc.backfill_from_legacy()

    context = svc.get_context_for_prompt()
    assert "Likes concise updates" in context
    assert "v1 shipped" in context

    svc.close()


def test_memory_service_legacy_fallback_when_canonical_empty(tmp_path):
    office = tmp_path / "agent-office"
    office.mkdir()
    (office / "MEMORY.md").write_text("## Goal\n- Ship safely\n", encoding="utf-8")

    svc = MemoryService(
        office_path=office,
        db_path=tmp_path / "memory.sqlite3",
        enabled=True,
        shadow_mode=False,
        include_legacy_fallback=True,
        max_context_chars=2000,
    )

    context = svc.get_context_for_prompt()
    assert "Ship safely" in context

    svc.close()
