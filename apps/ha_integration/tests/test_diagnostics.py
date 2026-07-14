"""Diagnostics and repairs tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from zigbeelens.coordinator import ZigbeeLensCoordinatorData, ZigbeeLensDataUpdateCoordinator
from zigbeelens.diagnostics import async_get_config_entry_diagnostics
from zigbeelens.repairs import async_manage_repairs, async_clear_repairs
from zigbeelens.const import (
    ISSUE_COLLECTOR_DISCONNECTED,
    ISSUE_CORE_UNREACHABLE,
    ISSUE_INCOMPATIBLE_VERSION,
    ISSUE_MOCK_MODE,
)


@pytest.fixture
def hass_with_coordinator(mock_coordinator):
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.version = 1
    entry.data = {"core_url": "http://user:secret@localhost:8377"}
    hass.data = {"zigbeelens": {"entry1": {"coordinator": mock_coordinator}}}

    with patch("zigbeelens.diagnostics.er.async_get") as mock_er_get:
        mock_registry = MagicMock()
        mock_er_get.return_value = mock_registry
        with patch(
            "zigbeelens.diagnostics.er.async_entries_for_config_entry",
            return_value=[MagicMock(), MagicMock()],
        ):
            yield hass, entry


@pytest.mark.asyncio
async def test_diagnostics_redacts_secrets(hass_with_coordinator):
    hass, entry = hass_with_coordinator
    payload = await async_get_config_entry_diagnostics(hass, entry)
    assert "secret" not in str(payload)
    assert "[redacted]" in payload["core_url"]
    assert payload["core_version"] == "0.1.0"
    assert payload["entity_count"] == 2
    assert "devices" not in payload


def test_repairs_core_unreachable():
    hass = MagicMock()
    coord = MagicMock(spec=ZigbeeLensDataUpdateCoordinator)
    coord.last_update_success = False
    coord.data = None

    with patch("zigbeelens.repairs.ir.async_create_issue") as create_issue:
        async_manage_repairs(hass, coord)
        assert any(
            call.args[2] == ISSUE_CORE_UNREACHABLE for call in create_issue.call_args_list
        )


def test_repairs_collector_disconnected(sample_health, sample_dashboard, sample_config_status):
    hass = MagicMock()
    coord = MagicMock(spec=ZigbeeLensDataUpdateCoordinator)
    sample_health = dict(sample_health)
    sample_health["collector"] = {"connected": False}
    coord.data = ZigbeeLensCoordinatorData(
        health=sample_health,
        dashboard=sample_dashboard,
        config_status=sample_config_status,
        core_version="0.1.0",
        collector_connected=False,
        last_update_success=True,
    )
    coord.last_update_success = True

    with patch("zigbeelens.repairs.ir.async_create_issue") as create_issue, patch(
        "zigbeelens.repairs.ir.async_delete_issue"
    ):
        async_manage_repairs(hass, coord)
        assert any(
            call.args[2] == ISSUE_COLLECTOR_DISCONNECTED for call in create_issue.call_args_list
        )


def test_repairs_mock_mode(sample_health, sample_dashboard, sample_config_status):
    hass = MagicMock()
    coord = MagicMock(spec=ZigbeeLensDataUpdateCoordinator)
    sample_health = dict(sample_health)
    sample_health["mock_mode"] = True
    coord.data = ZigbeeLensCoordinatorData(
        health=sample_health,
        dashboard=sample_dashboard,
        config_status=sample_config_status,
        core_version="0.1.0",
        collector_connected=True,
        last_update_success=True,
    )
    coord.last_update_success = True

    with patch("zigbeelens.repairs.ir.async_create_issue") as create_issue, patch(
        "zigbeelens.repairs.ir.async_delete_issue"
    ):
        async_manage_repairs(hass, coord)
        assert any(call.args[2] == ISSUE_MOCK_MODE for call in create_issue.call_args_list)


def test_repairs_incompatible_core_version(sample_health, sample_dashboard, sample_config_status):
    hass = MagicMock()
    coord = MagicMock(spec=ZigbeeLensDataUpdateCoordinator)
    coord.data = ZigbeeLensCoordinatorData(
        health=sample_health,
        dashboard=sample_dashboard,
        config_status=sample_config_status,
        core_version="0.0.1",
        collector_connected=True,
        last_update_success=True,
        core_version_compatible=False,
    )
    coord.last_update_success = True

    with patch("zigbeelens.repairs.ir.async_create_issue") as create_issue, patch(
        "zigbeelens.repairs.ir.async_delete_issue"
    ):
        async_manage_repairs(hass, coord)
        assert any(call.args[2] == ISSUE_INCOMPATIBLE_VERSION for call in create_issue.call_args_list)


def test_clear_repairs():
    hass = MagicMock()
    with patch("zigbeelens.repairs.ir.async_delete_issue") as delete_issue:
        async_clear_repairs(hass)
        assert delete_issue.call_count >= 6
