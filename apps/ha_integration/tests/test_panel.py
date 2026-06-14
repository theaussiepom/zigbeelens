"""Panel registration tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from zigbeelens.panel import async_register_panel, async_unregister_panel


@pytest.mark.asyncio
async def test_panel_registered_when_enabled():
    hass = MagicMock()
    hass.data = {"zigbeelens": {}}
    with patch("zigbeelens.panel.frontend.async_register_built_in_panel") as register:
        await async_register_panel(hass, "entry1", "http://localhost:8377")
        register.assert_called_once()
        assert hass.data["zigbeelens"]["entry1"]["panel_registered"] is True


@pytest.mark.asyncio
async def test_panel_not_registered_twice():
    hass = MagicMock()
    hass.data = {"zigbeelens": {"entry1": {"panel_registered": True}}}
    with patch("zigbeelens.panel.frontend.async_register_built_in_panel") as register:
        await async_register_panel(hass, "entry1", "http://localhost:8377")
        register.assert_not_called()


@pytest.mark.asyncio
async def test_panel_removed_on_unload():
    hass = MagicMock()
    hass.data = {"zigbeelens": {"entry1": {"panel_registered": True}}}
    with patch("zigbeelens.panel.frontend.async_remove_panel") as remove:
        await async_unregister_panel(hass, "entry1")
        remove.assert_called_once()
        assert hass.data["zigbeelens"]["entry1"]["panel_registered"] is False
