"""HA integration setup/unload behaviour."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zigbeelens import async_setup_entry, async_unload_entry
from zigbeelens.const import CONF_PANEL_ENABLED, DOMAIN, PLATFORMS


def _entry(*, panel_enabled: bool = True):
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.data = {
        "core_url": "http://127.0.0.1:8377",
        "verify_ssl": False,
        CONF_PANEL_ENABLED: panel_enabled,
    }
    entry.options = {"scan_interval": 60}
    return entry


@pytest.mark.asyncio
async def test_unload_always_unregisters_panel():
    hass = MagicMock()
    entry = _entry(panel_enabled=False)
    hass.data = {DOMAIN: {"entry1": {"coordinator": MagicMock(), "client": MagicMock()}}}
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

    with patch("zigbeelens.async_unregister_panel", new=AsyncMock()) as unregister, patch(
        "zigbeelens.async_clear_repairs"
    ):
        ok = await async_unload_entry(hass, entry)

    assert ok is True
    unregister.assert_awaited_once_with(hass, "entry1")


@pytest.mark.asyncio
async def test_setup_with_panel_disabled_unregisters_panel():
    hass = MagicMock()
    entry = _entry(panel_enabled=False)
    client = MagicMock()
    client.core_url = "http://127.0.0.1:8377"
    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    coordinator.async_add_listener = MagicMock(return_value=lambda: None)

    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)

    with patch("zigbeelens.async_get_clientsession", return_value=MagicMock()), patch(
        "zigbeelens.ZigbeeLensApiClient", return_value=client
    ), patch(
        "zigbeelens.ZigbeeLensDataUpdateCoordinator", return_value=coordinator
    ), patch("zigbeelens.async_register_panel", new=AsyncMock()) as register, patch(
        "zigbeelens.async_unregister_panel", new=AsyncMock()
    ) as unregister, patch("zigbeelens.async_manage_repairs"):
        ok = await async_setup_entry(hass, entry)

    assert ok is True
    register.assert_not_awaited()
    unregister.assert_awaited_once_with(hass, "entry1")


@pytest.mark.asyncio
async def test_setup_with_panel_enabled_registers_panel():
    hass = MagicMock()
    entry = _entry(panel_enabled=True)
    client = MagicMock()
    client.core_url = "http://127.0.0.1:8377"
    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    coordinator.async_add_listener = MagicMock(return_value=lambda: None)

    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)

    with patch("zigbeelens.async_get_clientsession", return_value=MagicMock()), patch(
        "zigbeelens.ZigbeeLensApiClient", return_value=client
    ), patch(
        "zigbeelens.ZigbeeLensDataUpdateCoordinator", return_value=coordinator
    ), patch("zigbeelens.async_register_panel", new=AsyncMock()) as register, patch(
        "zigbeelens.async_unregister_panel", new=AsyncMock()
    ) as unregister, patch("zigbeelens.async_manage_repairs"):
        ok = await async_setup_entry(hass, entry)

    assert ok is True
    register.assert_awaited_once_with(hass, "entry1", client.core_url)
    unregister.assert_not_awaited()
