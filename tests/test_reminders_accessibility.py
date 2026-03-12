from unittest.mock import patch

from apple_flow import reminders_accessibility as ra


def test_create_reminder_retries_with_menu_trigger_when_button_trigger_missing():
    calls: list[dict] = []

    def _fake_run_helper(payload, timeout=20.0):
        del timeout
        calls.append(payload)
        if len(calls) == 1:
            return {"ok": False, "error": "unable to trigger new reminder"}
        return {"ok": True}

    with patch("apple_flow.reminders_accessibility._run_helper", side_effect=_fake_run_helper):
        reminder_id = ra.create_reminder(
            "iCloud/linear/dev-backlog",
            "Buy milk",
            section_name="Inactive",
        )

    assert reminder_id is not None
    assert len(calls) == 2
    assert "trigger_strategy" not in calls[0]
    assert calls[1]["trigger_strategy"] == "menu"
    assert calls[1]["section_name"] == "Inactive"


def test_create_reminder_falls_back_to_system_events_on_helper_failure():
    with (
        patch(
            "apple_flow.reminders_accessibility._run_helper",
            return_value={"ok": False, "error": "new reminder row did not appear"},
        ),
        patch(
            "apple_flow.reminders_accessibility._create_reminder_via_system_events",
            return_value=True,
        ) as fallback_mock,
    ):
        reminder_id = ra.create_reminder(
            "iCloud/linear/dev-backlog",
            "[test] item",
            section_name="Inactive",
        )

    assert reminder_id is not None
    fallback_mock.assert_called_once_with(
        "iCloud/linear/dev-backlog",
        "[test] item",
        section_name="Inactive",
    )


def test_list_sections_returns_helper_sections():
    with patch(
        "apple_flow.reminders_accessibility._run_helper",
        return_value={"ok": True, "sections": ["Inactive", "issue-ready"]},
    ) as helper_mock:
        sections = ra.list_sections("iCloud/linear/dev-backlog")

    assert sections == ["Inactive", "issue-ready"]
    helper_mock.assert_called_once()


def test_create_group_returns_exists_for_existing_real_group():
    with (
        patch("apple_flow.reminders_accessibility._run_helper", return_value={"ok": False, "error": "helper unavailable"}),
        patch(
            "apple_flow.reminders_accessibility._find_group_row",
            return_value={"row": 18, "label": "client-tim-cook", "description": "cell", "name": "client-tim-cook", "parent_group": "", "is_group": True},
        )
    ):
        result = ra.create_group("client-tim-cook", default_account="iCloud")

    assert result == {"ok": True, "status": "exists", "path": "iCloud/client-tim-cook"}


def test_create_group_prefers_helper_when_available():
    with (
        patch("apple_flow.reminders_accessibility._find_group_row", return_value=None),
        patch(
            "apple_flow.reminders_accessibility._run_helper",
            return_value={"ok": True, "status": "created", "path": "iCloud/client-tim-cook"},
        ),
        patch("apple_flow.reminders_accessibility._find_top_level_list_row") as flat_row_mock,
    ):
        result = ra.create_group("client-tim-cook", default_account="iCloud")

    assert result == {"ok": True, "status": "created", "path": "iCloud/client-tim-cook"}
    flat_row_mock.assert_not_called()


def test_create_group_returns_helper_error_without_legacy_scan():
    with (
        patch(
            "apple_flow.reminders_accessibility._run_helper",
            return_value={"ok": False, "error": "new group menu item not found"},
        ),
        patch("apple_flow.reminders_accessibility._find_group_row", side_effect=AssertionError("legacy scan should not run")),
    ):
        result = ra.create_group("client-tim-cook", default_account="iCloud")

    assert result == {"ok": False, "error": "new group menu item not found"}


def test_create_list_returns_exists_for_existing_nested_row():
    with (
        patch("apple_flow.reminders_accessibility._run_helper", return_value={"ok": False, "error": "helper unavailable"}),
        patch(
            "apple_flow.reminders_accessibility._find_nested_list_row",
            return_value={"row": 22, "label": "", "description": "inbox, 0 reminders, List badge, Blue, 0 reminders, in group client-tim-cook", "name": "inbox", "parent_group": "client-tim-cook", "is_group": False},
        )
    ):
        result = ra.create_list("iCloud/client-tim-cook", "inbox")

    assert result == {"ok": True, "status": "exists", "path": "iCloud/client-tim-cook/inbox"}


def test_create_list_prefers_helper_when_available():
    with (
        patch("apple_flow.reminders_accessibility._find_nested_list_row", return_value=None),
        patch(
            "apple_flow.reminders_accessibility._run_helper",
            return_value={"ok": True, "status": "created", "path": "iCloud/client-tim-cook/client-inbox"},
        ),
        patch("apple_flow.reminders_accessibility._find_group_row") as group_row_mock,
    ):
        result = ra.create_list("iCloud/client-tim-cook", "client-inbox")

    assert result == {"ok": True, "status": "created", "path": "iCloud/client-tim-cook/client-inbox"}
    group_row_mock.assert_not_called()


def test_create_list_returns_helper_error_without_legacy_scan_when_helper_is_available():
    with (
        patch("apple_flow.reminders_accessibility._run_helper", return_value={"ok": False, "error": "parent group not found"}),
        patch("apple_flow.reminders_accessibility._helper_list_path_exists", return_value=False),
        patch("apple_flow.reminders_accessibility._dismiss_reminders_sheet"),
        patch("apple_flow.reminders_accessibility._delete_top_level_list_by_name") as delete_mock,
    ):
        result = ra.create_list("iCloud/client-tim-cook", "client-inbox")

    assert result == {"ok": False, "error": "parent group not found"}
    delete_mock.assert_not_called()


def test_create_group_deletes_flat_top_level_conflict_before_creating_group():
    delete_calls: list[str] = []
    system_events_scripts: list[str] = []
    state = {"group_exists": False, "flat_exists": True}

    def _group_row(name: str):
        if name == "client-tim-cook" and state["group_exists"]:
            return {"row": 18, "label": name, "description": "cell", "name": name, "parent_group": "", "is_group": True}
        return None

    def _flat_row(name: str):
        if name == "client-tim-cook" and state["flat_exists"]:
            return {"row": 26, "label": "", "description": "client-tim-cook, 0 reminders, List badge, Blue", "name": name, "parent_group": "", "is_group": False}
        return None

    def _run_system_events(script: str, timeout: float = 20.0):
        del timeout
        system_events_scripts.append(script)
        if "New Group" in script:
            return {"ok": True, "stdout": "", "error": ""}
        if "key code 36" in script:
            state["group_exists"] = True
            return {"ok": True, "stdout": "", "error": ""}
        raise AssertionError(f"unexpected system events script: {script}")

    with (
        patch("apple_flow.reminders_accessibility._run_helper", return_value={"ok": False, "error": "helper unavailable"}),
        patch("apple_flow.reminders_accessibility._find_group_row", side_effect=_group_row),
        patch("apple_flow.reminders_accessibility._find_top_level_list_row", side_effect=_flat_row),
        patch("apple_flow.reminders_accessibility._delete_top_level_list_by_name", side_effect=lambda name: delete_calls.append(name) or state.update({"flat_exists": False}) or True),
        patch("apple_flow.reminders_accessibility._run_system_events", side_effect=_run_system_events),
        patch("apple_flow.reminders_accessibility._selected_sidebar_row", return_value=18),
    ):
        result = ra.create_group("client-tim-cook", default_account="iCloud")

    assert result == {"ok": True, "status": "created", "path": "iCloud/client-tim-cook"}
    assert delete_calls == ["client-tim-cook"]
    assert any("New Group" in script for script in system_events_scripts)


def test_create_list_cleans_up_unexpected_top_level_on_helper_failure():
    deleted: list[str] = []

    def _path_exists(path: str, default_account: str = "") -> bool:
        del default_account
        if path == "iCloud/client-inbox":
            return True
        return False

    with (
        patch("apple_flow.reminders_accessibility._run_helper", return_value={"ok": False, "error": "list did not appear"}),
        patch("apple_flow.reminders_accessibility._helper_list_path_exists", side_effect=_path_exists),
        patch("apple_flow.reminders_accessibility._dismiss_reminders_sheet"),
        patch("apple_flow.reminders_accessibility._delete_top_level_list_by_name", side_effect=lambda name: deleted.append(name) or True),
    ):
        result = ra.create_list("iCloud/client-tim-cook", "client-inbox")

    assert result == {"ok": False, "error": "list did not appear"}
    assert deleted == ["client-inbox"]


def test_create_list_returns_helper_unavailable_when_nested_list_not_found():
    with (
        patch("apple_flow.reminders_accessibility._run_helper", return_value={"ok": False, "error": "helper unavailable"}),
        patch("apple_flow.reminders_accessibility._helper_list_path_exists", return_value=False),
        patch("apple_flow.reminders_accessibility._find_nested_list_row", return_value=None),
        patch("apple_flow.reminders_accessibility._dismiss_reminders_sheet"),
    ):
        result = ra.create_list("iCloud/client-tim-cook", "client-inbox")

    assert result == {"ok": False, "error": "helper unavailable"}


def test_list_catalog_passes_include_groups_flag_to_helper():
    with patch(
        "apple_flow.reminders_accessibility._run_helper",
        return_value={"ok": True, "lists": [{"path": "iCloud/client-tim-cook", "kind": "group"}]},
    ) as helper_mock:
        result = ra.list_catalog(default_account="iCloud", include_groups=True)

    assert result == [{"path": "iCloud/client-tim-cook", "kind": "group"}]
    helper_mock.assert_called_once()
    helper_payload = helper_mock.call_args[0][0]
    assert helper_payload["action"] == "catalog"
    assert helper_payload["include_groups"] is True


def test_create_section_returns_created_status():
    with patch(
        "apple_flow.reminders_accessibility._run_helper",
        return_value={"ok": True, "status": "created", "section_name": "Inactive"},
    ):
        result = ra.create_section("iCloud/linear/dev-backlog", "Inactive")

    assert result == {"ok": True, "status": "created", "section_name": "Inactive"}


def test_create_section_validates_name_and_surfaces_helper_error():
    assert ra.create_section("iCloud/linear/dev-backlog", "   ") == {
        "ok": False,
        "error": "section name is required",
    }

    with patch(
        "apple_flow.reminders_accessibility._run_helper",
        return_value={"ok": False, "error": "new section menu item not found"},
    ):
        result = ra.create_section("iCloud/linear/dev-backlog", "Inactive")

    assert result == {"ok": False, "error": "new section menu item not found"}


def test_create_section_uses_system_events_fallback_for_focus_errors():
    with (
        patch("apple_flow.reminders_accessibility.list_sections", return_value=[]),
        patch(
            "apple_flow.reminders_accessibility._run_helper",
            return_value={"ok": False, "error": "unable to set section name"},
        ),
        patch(
            "apple_flow.reminders_accessibility._create_section_via_system_events",
            return_value={"ok": True, "status": "created", "section_name": "Inactive"},
        ) as fallback_mock,
    ):
        result = ra.create_section("iCloud/linear/dev-backlog", "Inactive")

    assert result == {"ok": True, "status": "created", "section_name": "Inactive"}
    fallback_mock.assert_called_once_with("iCloud/linear/dev-backlog", "Inactive")
