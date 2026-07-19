"""Native companion panel registration and websocket summary tests."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zigbeelens.panel import (
    PANEL_WEBCOMPONENT,
    _ws_panel_summary,
    async_register_panel,
    async_unregister_panel,
)


@pytest.mark.asyncio
async def test_panel_registered_as_native_custom_panel():
    hass = MagicMock()
    hass.data = {"zigbeelens": {}}
    hass.http.async_register_static_paths = AsyncMock()
    with (
        patch("zigbeelens.panel.panel_custom.async_register_panel", new=AsyncMock()) as register,
        patch("zigbeelens.panel.websocket_api.async_register_command") as ws_register,
    ):
        await async_register_panel(hass, "entry1", "http://192.168.100.5:8377")

    register.assert_awaited_once()
    _args, kwargs = register.call_args
    assert kwargs["webcomponent_name"] == PANEL_WEBCOMPONENT
    assert kwargs["embed_iframe"] is False
    assert kwargs["frontend_url_path"] == "zigbeelens"
    assert kwargs["module_url"].endswith(".js")
    assert kwargs["config"] == {"core_url": "http://192.168.100.5:8377"}
    assert "api_token" not in kwargs["config"]
    assert "Authorization" not in json.dumps(kwargs["config"])
    ws_register.assert_called_once()
    hass.http.async_register_static_paths.assert_awaited_once()
    assert hass.data["zigbeelens"]["_panel_state"]["panel_registered"] is True


@pytest.mark.asyncio
async def test_panel_registration_never_includes_token_sentinel():
    sentinel = "zl-hacs-panel-sentinel-token-aaaaaa"
    hass = MagicMock()
    hass.data = {"zigbeelens": {}}
    hass.http.async_register_static_paths = AsyncMock()
    with (
        patch("zigbeelens.panel.panel_custom.async_register_panel", new=AsyncMock()) as register,
        patch("zigbeelens.panel.websocket_api.async_register_command"),
    ):
        await async_register_panel(hass, "entry1", "http://192.168.100.5:8377")
    blob = json.dumps(register.call_args.kwargs)
    assert sentinel not in blob
    assert register.call_args.kwargs["config"] == {
        "core_url": "http://192.168.100.5:8377"
    }


@pytest.mark.asyncio
async def test_panel_not_registered_twice_when_core_url_unchanged():
    from homeassistant.components import frontend

    hass = MagicMock()
    hass.data = {
        "zigbeelens": {"_panel_state": {"panel_registered": True}},
        frontend.DATA_PANELS: {"zigbeelens": {"config": {"core_url": "http://old"}}},
    }
    hass.http.async_register_static_paths = AsyncMock()
    with patch(
        "zigbeelens.panel.panel_custom.async_register_panel", new=AsyncMock()
    ) as register:
        await async_register_panel(hass, "entry1", "http://old")
        register.assert_not_awaited()
    assert (
        hass.data[frontend.DATA_PANELS]["zigbeelens"]["config"]["core_url"]
        == "http://old"
    )


@pytest.mark.asyncio
async def test_panel_reregisters_when_core_url_changes():
    from homeassistant.components import frontend

    hass = MagicMock()
    hass.data = {
        "zigbeelens": {"_panel_state": {"panel_registered": True}},
        frontend.DATA_PANELS: {"zigbeelens": {"config": {"core_url": "http://old"}}},
    }
    hass.http.async_register_static_paths = AsyncMock()
    with patch(
        "zigbeelens.panel.panel_custom.async_register_panel", new=AsyncMock()
    ) as register, patch("zigbeelens.panel.frontend.async_remove_panel") as remove:
        await async_register_panel(hass, "entry1", "http://localhost:8377")
        remove.assert_called_once()
        register.assert_awaited_once()


@pytest.mark.asyncio
async def test_panel_removed_on_unload():
    hass = MagicMock()
    hass.data = {
        "zigbeelens": {"_panel_state": {"panel_registered": True}},
        "frontend_panels": {"zigbeelens": object()},
    }
    with patch("zigbeelens.panel.frontend.async_remove_panel") as remove:
        await async_unregister_panel(hass, "entry1")
        remove.assert_called_once()
        assert hass.data["zigbeelens"]["_panel_state"]["panel_registered"] is False


def test_ws_panel_summary_returns_connected_payload(mock_coordinator):
    hass = MagicMock()
    hass.data = {
        "zigbeelens": {
            "entry1": {"coordinator": mock_coordinator, "client": mock_coordinator.client}
        }
    }
    connection = MagicMock()

    _ws_panel_summary(hass, connection, {"id": 7})

    connection.send_result.assert_called_once()
    msg_id, payload = connection.send_result.call_args[0]
    assert msg_id == 7
    assert payload["connected"] is True
    assert payload["core_url"] == "http://localhost:8377"
    assert payload["active_incident_count"] == 1
    assert payload["device_count"] == 10
    assert payload["networks"][0]["name"] == "Home"
    assert "shared_decisions_available" in payload
    assert "decision_contract_version" in payload
    assert "core_version_compatible" in payload
    assert "capabilities" not in payload
    assert "score" not in json.dumps(payload)
    assert "action_group" not in json.dumps(payload)
    assert "card_type" not in json.dumps(payload)
    assert "device_ieees" not in json.dumps(payload)
    # Must not leak broker URL / credentials.
    serialized = json.dumps(payload).lower()
    assert "mqtt_server" not in payload
    assert "password" not in serialized
    assert "broker" not in serialized


def test_ws_panel_summary_disconnected_is_calm():
    hass = MagicMock()
    coordinator = MagicMock()
    coordinator.last_update_success = False
    coordinator.data = None
    coordinator.last_exception = "Cannot connect to ZigbeeLens Core"
    client = MagicMock(core_url="http://192.168.100.5:8377")
    hass.data = {"zigbeelens": {"e": {"coordinator": coordinator, "client": client}}}
    connection = MagicMock()

    _ws_panel_summary(hass, connection, {"id": 1})

    _id, payload = connection.send_result.call_args[0]
    assert payload["connected"] is False
    assert payload["core_url"] == "http://192.168.100.5:8377"
    assert payload["error"] == "Cannot connect to ZigbeeLens Core"
    assert payload["networks"] == []
    assert payload["core_version_compatible"] is None
    assert payload["shared_decisions_available"] is False


@pytest.mark.asyncio
async def test_panel_reregister_when_flag_set_but_panel_missing():
    from homeassistant.components import frontend

    hass = MagicMock()
    hass.data = {
        "zigbeelens": {"_panel_state": {"panel_registered": True}},
        frontend.DATA_PANELS: {},
    }
    hass.http.async_register_static_paths = AsyncMock()
    with patch(
        "zigbeelens.panel.panel_custom.async_register_panel", new=AsyncMock()
    ) as register:
        await async_register_panel(hass, "entry1", "http://localhost:8377")
        register.assert_awaited_once()
    assert hass.data["zigbeelens"]["_panel_state"]["panel_registered"] is True


def test_ws_panel_summary_handles_bad_dashboard_data():
    hass = MagicMock()
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = MagicMock()
    coordinator.data.dashboard = "bad-shape"
    coordinator.data.health = {}
    coordinator.data.core_version = None
    coordinator.data.collector_connected = False
    coordinator.last_exception = None
    client = MagicMock(core_url="http://192.168.100.5:8377")
    hass.data = {"zigbeelens": {"e": {"coordinator": coordinator, "client": client}}}
    connection = MagicMock()

    _ws_panel_summary(hass, connection, {"id": 9})

    _id, payload = connection.send_result.call_args[0]
    assert payload["connected"] is False
    assert payload["error"] == "Panel summary unavailable"


def test_ws_panel_summary_without_coordinator():
    hass = MagicMock()
    hass.data = {"zigbeelens": {}}
    connection = MagicMock()

    _ws_panel_summary(hass, connection, {"id": 3})

    _id, payload = connection.send_result.call_args[0]
    assert payload["connected"] is False
    assert payload["networks"] == []
