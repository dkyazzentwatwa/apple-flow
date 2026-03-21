from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    script_path = ROOT / "scripts" / "notion_direct.py"
    spec = importlib.util.spec_from_file_location("notion_direct", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_workspace_spec(base_dir: Path) -> Path:
    workspace_dir = base_dir / "workspace-spec"
    pages_dir = workspace_dir / "pages"
    db_dir = workspace_dir / "databases"
    seed_dir = workspace_dir / "seed"
    pages_dir.mkdir(parents=True)
    db_dir.mkdir()
    seed_dir.mkdir()

    (pages_dir / "home.md").write_text(
        "# 3-Day AI Training Hub\n\n"
        "This workspace is the central delivery hub for the 3-day AI training program.\n\n"
        "## Quick Links\n\n"
        "- Program Overview\n"
        "- Run of Show\n",
        encoding="utf-8",
    )
    (pages_dir / "program-overview.md").write_text(
        "# Program Overview\n\n"
        "## Goals\n\n"
        "- Build the company brain\n"
        "- Train each cohort\n",
        encoding="utf-8",
    )
    (db_dir / "deliverables-schema.json").write_text(
        json.dumps(
            {
                "title": "Deliverables",
                "properties": [
                    {"name": "Name", "type": "title"},
                    {"name": "Phase", "type": "select", "options": ["Company Brain Build", "Cohort Training"]},
                    {"name": "Status", "type": "select", "options": ["Not Started", "In Progress"]},
                    {"name": "Client Facing", "type": "checkbox"},
                    {"name": "Due Date", "type": "date"},
                    {"name": "Notes", "type": "rich_text"},
                ],
                "views": [{"name": "All Deliverables"}, {"name": "By Phase"}],
            }
        ),
        encoding="utf-8",
    )
    (seed_dir / "deliverables.json").write_text(
        json.dumps(
            [
                {
                    "Name": "Lightweight questionnaire",
                    "Phase": "Company Brain Build",
                    "Status": "Not Started",
                    "Client Facing": False,
                    "Notes": "Seeded starter asset",
                }
            ]
        ),
        encoding="utf-8",
    )
    (workspace_dir / "manifest.json").write_text(
        json.dumps(
            {
                "workspace_title": "3-Day AI Training Hub",
                "workspace_intro": (
                    "This workspace is the central delivery hub for the 3-day AI training program."
                ),
                "home_file": "pages/home.md",
                "pages": [
                    {
                        "id": "program-overview",
                        "title": "Program Overview",
                        "file": "pages/program-overview.md",
                    }
                ],
                "databases": [
                    {
                        "id": "deliverables",
                        "title": "Deliverables",
                        "schema_file": "databases/deliverables-schema.json",
                        "seed_file": "seed/deliverables.json",
                    }
                ],
                "manual_views": {
                    "Deliverables": ["All Deliverables", "By Phase"],
                },
            }
        ),
        encoding="utf-8",
    )
    return workspace_dir


def test_markdown_to_blocks_skips_h1_and_maps_sections():
    notion_direct = _load_module()

    blocks = notion_direct._markdown_to_blocks(
        "# Start Here\n\n"
        "Intro paragraph.\n\n"
        "## Fastest Path\n\n"
        "- Install one connector\n"
        "- Configure .env\n\n"
        "1. Validate config\n"
        "2. Send smoke test\n"
    )

    assert [block["type"] for block in blocks] == [
        "paragraph",
        "heading_2",
        "bulleted_list_item",
        "bulleted_list_item",
        "numbered_list_item",
        "numbered_list_item",
    ]
    assert "Start Here" not in json.dumps(blocks)


def test_extract_callout_uses_suggested_callout_section():
    notion_direct = _load_module()

    callout = notion_direct._extract_callout(
        "# Notion Page Tree\n\n"
        "Root page: `Codex Flow User Guide`\n\n"
        "Suggested callout at the top of the root page:\n\n"
        "`Local files and Apple Flow runtime state are canonical.`\n"
    )

    assert callout == "Local files and Apple Flow runtime state are canonical."


def test_build_database_payload_uses_schema_properties_and_parent():
    notion_direct = _load_module()

    schema = {
        "title": "Automation Process Log",
        "properties": [
            {"name": "Title", "type": "title"},
            {"name": "Timestamp", "type": "date"},
            {"name": "Process Type", "type": "select", "options": ["Run", "Approval"]},
            {"name": "Follow-up Needed", "type": "checkbox"},
        ],
    }

    payload = notion_direct._build_database_payload("page-123", schema)

    assert payload["parent"] == {"type": "page_id", "page_id": "page-123"}
    assert payload["title"][0]["text"]["content"] == "Automation Process Log"
    assert payload["properties"]["Title"] == {"title": {}}
    assert payload["properties"]["Timestamp"] == {"date": {}}
    assert payload["properties"]["Process Type"]["select"]["options"] == [
        {"name": "Run"},
        {"name": "Approval"},
    ]
    assert payload["properties"]["Follow-up Needed"] == {"checkbox": {}}


def test_publish_guidebook_dry_run_reports_pages_and_database(tmp_path, monkeypatch):
    notion_direct = _load_module()
    guidebook_dir = tmp_path / "notion-guidebook"
    pages_dir = guidebook_dir / "pages"
    pages_dir.mkdir(parents=True)
    (pages_dir / "start-here.md").write_text("# Start Here\n\nIntro paragraph.\n", encoding="utf-8")
    (guidebook_dir / "manifest.json").write_text(
        json.dumps(
            {
                "guidebook_title": "Codex Flow User Guide",
                "pages": [
                    {
                        "title": "Start Here",
                        "file": "pages/start-here.md",
                        "purpose": "Orient operators.",
                    }
                ],
                "database": {"title": "Automation Process Log", "schema_file": "automation-process-log-schema.json"},
            }
        ),
        encoding="utf-8",
    )
    (guidebook_dir / "page-tree.md").write_text(
        "# Notion Page Tree\n\nSuggested callout at the top of the root page:\n\n"
        "`Local files are canonical.`\n",
        encoding="utf-8",
    )
    (guidebook_dir / "automation-process-log-schema.json").write_text(
        json.dumps({"title": "Automation Process Log", "properties": [{"name": "Title", "type": "title"}]}),
        encoding="utf-8",
    )

    calls: list[tuple[str, str, object | None]] = []

    def fake_request(method: str, path: str, payload=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/pages/root-page":
            return {"id": "root-page", "url": "https://example.com/root"}
        if method == "GET" and path == "/blocks/root-page/children?page_size=100":
            return {
                "results": [
                    {
                        "type": "paragraph",
                        "paragraph": {"rich_text": []},
                    }
                ]
            }
        raise AssertionError(f"unexpected request: {method} {path}")

    monkeypatch.setattr(notion_direct, "_request", fake_request)

    summary = notion_direct.publish_guidebook("root-page", str(guidebook_dir), dry_run=True)

    assert summary["dry_run"] is True
    assert summary["root_page_id"] == "root-page"
    assert summary["page_titles"] == ["Start Here"]
    assert summary["database_title"] == "Automation Process Log"
    assert any(path == "/blocks/root-page/children?page_size=100" for _, path, _ in calls)


def test_publish_guidebook_rejects_existing_child_title_collision(tmp_path, monkeypatch):
    notion_direct = _load_module()
    guidebook_dir = tmp_path / "notion-guidebook"
    pages_dir = guidebook_dir / "pages"
    pages_dir.mkdir(parents=True)
    (pages_dir / "setup.md").write_text("# Setup\n\nConfig steps.\n", encoding="utf-8")
    (guidebook_dir / "manifest.json").write_text(
        json.dumps(
            {
                "guidebook_title": "Codex Flow User Guide",
                "pages": [{"title": "Setup", "file": "pages/setup.md", "purpose": "Setup flow."}],
                "database": {"title": "Automation Process Log", "schema_file": "automation-process-log-schema.json"},
            }
        ),
        encoding="utf-8",
    )
    (guidebook_dir / "page-tree.md").write_text("# Notion Page Tree\n", encoding="utf-8")
    (guidebook_dir / "automation-process-log-schema.json").write_text(
        json.dumps({"title": "Automation Process Log", "properties": [{"name": "Title", "type": "title"}]}),
        encoding="utf-8",
    )

    def fake_request(method: str, path: str, payload=None):
        if method == "GET" and path == "/pages/root-page":
            return {"id": "root-page", "url": "https://example.com/root"}
        if method == "GET" and path == "/blocks/root-page/children?page_size=100":
            return {
                "results": [
                    {
                        "type": "child_page",
                        "child_page": {"title": "Setup"},
                    }
                ]
            }
        raise AssertionError(f"unexpected request: {method} {path}")

    monkeypatch.setattr(notion_direct, "_request", fake_request)

    with pytest.raises(SystemExit, match="already exists"):
        notion_direct.publish_guidebook("root-page", str(guidebook_dir), dry_run=True)


def test_publish_workspace_dry_run_reports_hub_pages_databases_and_views(tmp_path, monkeypatch):
    notion_direct = _load_module()
    workspace_dir = _write_workspace_spec(tmp_path)

    def fake_request(method: str, path: str, payload=None):
        if method == "GET" and path == "/pages/root-page":
            return {"id": "root-page", "url": "https://example.com/root"}
        if method == "GET" and path == "/blocks/root-page/children?page_size=100":
            return {"results": []}
        raise AssertionError(f"unexpected request: {method} {path}")

    monkeypatch.setattr(notion_direct, "_request", fake_request)

    summary = notion_direct.publish_workspace(
        "root-page",
        str(workspace_dir),
        dry_run=True,
        state_path=str(tmp_path / "state.json"),
    )

    assert summary["dry_run"] is True
    assert summary["workspace_title"] == "3-Day AI Training Hub"
    assert summary["hub_parent_id"] == "root-page"
    assert summary["page_titles"] == ["Program Overview"]
    assert summary["database_titles"] == ["Deliverables"]
    assert summary["manual_views"] == {"Deliverables": ["All Deliverables", "By Phase"]}


def test_publish_workspace_rejects_existing_hub_title_collision(tmp_path, monkeypatch):
    notion_direct = _load_module()
    workspace_dir = _write_workspace_spec(tmp_path)

    def fake_request(method: str, path: str, payload=None):
        if method == "GET" and path == "/pages/root-page":
            return {"id": "root-page", "url": "https://example.com/root"}
        if method == "GET" and path == "/blocks/root-page/children?page_size=100":
            return {"results": [{"type": "child_page", "child_page": {"title": "3-Day AI Training Hub"}}]}
        raise AssertionError(f"unexpected request: {method} {path}")

    monkeypatch.setattr(notion_direct, "_request", fake_request)

    with pytest.raises(SystemExit, match="already exists"):
        notion_direct.publish_workspace(
            "root-page",
            str(workspace_dir),
            dry_run=True,
            state_path=str(tmp_path / "state.json"),
        )


def test_publish_workspace_resumes_from_state_file_and_creates_remaining_objects(tmp_path, monkeypatch):
    notion_direct = _load_module()
    workspace_dir = _write_workspace_spec(tmp_path)
    state_file = tmp_path / "publish-state.json"
    state_file.write_text(
        json.dumps(
            {
                "workspace_id": "training-hub",
                "hub_page": {"id": "hub-page-id", "title": "3-Day AI Training Hub", "url": "https://example.com/hub"},
                "pages": {},
                "databases": {},
                "database_rows": {},
            }
        ),
        encoding="utf-8",
    )

    calls: list[tuple[str, str, object | None]] = []

    def fake_request(method: str, path: str, payload=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/pages/root-page":
            return {"id": "root-page", "url": "https://example.com/root"}
        if method == "GET" and path == "/blocks/root-page/children?page_size=100":
            return {"results": []}
        if method == "POST" and path == "/pages":
            properties = payload["properties"]
            title_prop = properties.get("title") or properties.get("Name")
            title = title_prop["title"][0]["text"]["content"]
            if title == "Program Overview":
                return {"id": "program-page-id", "url": "https://example.com/program"}
            parent = payload.get("parent", {})
            if parent.get("database_id") == "deliverables-db-id":
                return {"id": "deliverable-row-id", "url": "https://example.com/deliverable-row"}
            raise AssertionError(f"unexpected page payload: {payload}")
        if method == "PATCH" and path == "/blocks/program-page-id/children":
            return {"results": []}
        if method == "POST" and path == "/databases":
            return {"id": "deliverables-db-id", "url": "https://example.com/deliverables"}
        if method == "PATCH" and path == "/blocks/hub-page-id/children":
            return {"results": []}
        raise AssertionError(f"unexpected request: {method} {path}")

    monkeypatch.setattr(notion_direct, "_request", fake_request)
    monkeypatch.setattr(notion_direct.time, "sleep", lambda _seconds: None)

    summary = notion_direct.publish_workspace(
        "root-page",
        str(workspace_dir),
        dry_run=False,
        state_path=str(state_file),
        batch_size=1,
        sleep_seconds=0.0,
    )

    saved_state = json.loads(state_file.read_text(encoding="utf-8"))

    assert summary["created_hub_page"]["id"] == "hub-page-id"
    assert summary["created_pages"][0]["id"] == "program-page-id"
    assert summary["created_databases"][0]["id"] == "deliverables-db-id"
    assert saved_state["pages"]["program-overview"]["id"] == "program-page-id"
    assert saved_state["databases"]["deliverables"]["id"] == "deliverables-db-id"
    assert "deliverables" in saved_state["database_rows"]
    assert not any(
        method == "POST"
        and path == "/pages"
        and ((payload["properties"].get("title") or payload["properties"].get("Name"))["title"][0]["text"]["content"] == "3-Day AI Training Hub")
        for method, path, payload in calls
        if payload and payload.get("properties")
    )


def test_publish_workspace_allows_resume_when_hub_already_exists_under_root(tmp_path, monkeypatch):
    notion_direct = _load_module()
    workspace_dir = _write_workspace_spec(tmp_path)
    state_file = tmp_path / "publish-state.json"
    state_file.write_text(
        json.dumps(
            {
                "workspace_id": "training-hub",
                "hub_page": {"id": "hub-page-id", "title": "3-Day AI Training Hub", "url": "https://example.com/hub"},
                "hub_content_appended": True,
                "pages": {},
                "databases": {},
                "database_rows": {},
            }
        ),
        encoding="utf-8",
    )

    def fake_request(method: str, path: str, payload=None):
        if method == "GET" and path == "/pages/root-page":
            return {"id": "root-page", "url": "https://example.com/root"}
        if method == "GET" and path == "/blocks/root-page/children?page_size=100":
            return {"results": [{"type": "child_page", "child_page": {"title": "3-Day AI Training Hub"}}]}
        if method == "POST" and path == "/pages":
            return {"id": "program-page-id", "url": "https://example.com/program"}
        if method == "PATCH" and path == "/blocks/program-page-id/children":
            return {"results": []}
        if method == "POST" and path == "/databases":
            return {"id": "deliverables-db-id", "url": "https://example.com/deliverables"}
        raise AssertionError(f"unexpected request: {method} {path}")

    monkeypatch.setattr(notion_direct, "_request", fake_request)

    summary = notion_direct.publish_workspace(
        "root-page",
        str(workspace_dir),
        dry_run=False,
        state_path=str(state_file),
        batch_size=5,
        sleep_seconds=0.0,
    )

    assert summary["created_hub_page"]["id"] == "hub-page-id"


def test_real_training_hub_workspace_spec_loads_for_dry_run(monkeypatch):
    notion_direct = _load_module()
    workspace_dir = ROOT / "docs" / "internal" / "notion-workspaces" / "3-day-ai-training-hub"

    def fake_request(method: str, path: str, payload=None):
        if method == "GET" and path == "/pages/root-page":
            return {"id": "root-page", "url": "https://example.com/root"}
        if method == "GET" and path == "/blocks/root-page/children?page_size=100":
            return {"results": []}
        raise AssertionError(f"unexpected request: {method} {path}")

    monkeypatch.setattr(notion_direct, "_request", fake_request)

    summary = notion_direct.publish_workspace("root-page", str(workspace_dir), dry_run=True)

    assert summary["workspace_title"] == "3-Day AI Training Hub"
    assert len(summary["page_titles"]) >= 8
    assert len(summary["database_titles"]) == 8
    assert "Deliverables" in summary["manual_views"]


def test_append_blocks_chunks_requests_to_notion_limit(monkeypatch):
    notion_direct = _load_module()
    calls: list[tuple[str, str, object | None]] = []

    def fake_request(method: str, path: str, payload=None):
        calls.append((method, path, payload))
        return {"results": []}

    monkeypatch.setattr(notion_direct, "_request", fake_request)

    blocks = [notion_direct._paragraph_block(f"Item {idx}") for idx in range(205)]
    notion_direct._append_blocks("page-123", blocks)

    patch_calls = [call for call in calls if call[0] == "PATCH"]
    assert len(patch_calls) == 3
    assert [len(call[2]["children"]) for call in patch_calls] == [100, 100, 5]


def test_publish_workspace_chunks_large_home_content(tmp_path, monkeypatch):
    notion_direct = _load_module()
    workspace_dir = _write_workspace_spec(tmp_path)
    home_lines = ["# 3-Day AI Training Hub", ""]
    for idx in range(120):
        home_lines.append(f"- Quick link {idx}")
    (workspace_dir / "pages" / "home.md").write_text("\n".join(home_lines) + "\n", encoding="utf-8")

    calls: list[tuple[str, str, object | None]] = []

    def fake_request(method: str, path: str, payload=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/pages/root-page":
            return {"id": "root-page", "url": "https://example.com/root"}
        if method == "GET" and path == "/blocks/root-page/children?page_size=100":
            return {"results": []}
        if method == "POST" and path == "/pages":
            return {"id": "hub-page-id", "url": "https://example.com/hub"}
        if method == "PATCH" and path == "/blocks/hub-page-id/children":
            return {"results": []}
        if method == "POST" and path == "/databases":
            return {"id": "deliverables-db-id", "url": "https://example.com/deliverables"}
        raise AssertionError(f"unexpected request: {method} {path}")

    monkeypatch.setattr(notion_direct, "_request", fake_request)

    notion_direct.publish_workspace(
        "root-page",
        str(workspace_dir),
        dry_run=False,
        state_path=str(tmp_path / "state.json"),
        batch_size=5,
        sleep_seconds=0.0,
    )

    hub_patch_calls = [call for call in calls if call[0] == "PATCH" and call[1] == "/blocks/hub-page-id/children"]
    assert len(hub_patch_calls) >= 2
    assert all(len(call[2]["children"]) <= 100 for call in hub_patch_calls)
