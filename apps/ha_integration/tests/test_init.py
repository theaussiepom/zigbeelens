"""Unload tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zigbeelens import async_unload_entry
from zigbeelens.const import DOMAIN, PLATFORMS


@pytest.mark.asyncio
async def test_unload_removes_entities_and_panel():
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.data = {"panel_enabled": True}
    hass.data = {DOMAIN: {"entry1": {"coordinator": MagicMock(), "client": MagicMock()}}}
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

    with patch("zigbeelens.async_unregister_panel", new=AsyncMock()) as unregister, patch(
        "zigbeelens.async_clear_repairs"
    ) as clear_repairs:
        ok = await async_unload_entry(hass, entry)

    assert ok is True
    assert "entry1" not in hass.data[DOMAIN]
    unregister.assert_awaited_once_with(hass, "entry1")
    clear_repairs.assert_called_once_with(hass)
    hass.config_entries.async_unload_platforms.assert_awaited_once_with(entry, PLATFORMS)
