"""Config flow tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.components import frontend
from homeassistant.core import HomeAssistant

from zigbeelens.config_flow import (
    ZigbeeLensConfigFlow,
    ZigbeeLensOptionsFlow,
    _normalize_core_url,
)
from zigbeelens.const import CONF_CORE_URL, CONF_PANEL_ENABLED, CONF_SCAN_INTERVAL, CONF_VERIFY_SSL
from zigbeelens.exceptions import ZigbeeLensConnectionError
from zigbeelens.panel import PANEL_URL_PATH, async_update_panel_core_url


def test_normalize_core_url():
    assert _normalize_core_url("http://localhost:8377/") == "http://localhost:8377"


def test_normalize_core_url_invalid():
    with pytest.raises(ValueError):
        _normalize_core_url("not-a-url")


@pytest.mark.asyncio
async def test_config_flow_success():
    flow = ZigbeeLensConfigFlow()
    flow.hass = MagicMock()
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()

    with patch(
        "zigbeelens.config_flow._validate_core",
        new=AsyncMock(return_value={"status": "ok"}),
    ):
        result = await flow.async_step_user(
            {
                "core_url": "http://localhost:8377",
                "verify_ssl": False,
                "panel_enabled": True,
            }
        )

    assert result["type"] == "create_entry"
    assert result["data"]["core_url"] == "http://localhost:8377"


@pytest.mark.asyncio
async def test_config_flow_cannot_connect():
    flow = ZigbeeLensConfigFlow()
    flow.hass = MagicMock()
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()

    with patch(
        "zigbeelens.config_flow._validate_core",
        new=AsyncMock(side_effect=ZigbeeLensConnectionError("down")),
    ):
        result = await flow.async_step_user(
            {
                "core_url": "http://localhost:8377",
                "verify_ssl": False,
                "panel_enabled": True,
            }
        )

    assert result["type"] == "form"
    assert result["errors"]["base"] == "cannot_connect"


@pytest.mark.asyncio
async def test_options_flow_updates_core_url_and_reloads():
    hass = MagicMock(spec=HomeAssistant)
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    hass.config_entries.async_reload = AsyncMock()

    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.data = {
        CONF_CORE_URL: "http://192.168.100.5:8377",
        CONF_VERIFY_SSL: False,
        CONF_PANEL_ENABLED: True,
    }
    entry.options = {CONF_SCAN_INTERVAL: 60}

    flow = ZigbeeLensOptionsFlow(entry)
    flow.hass = hass

    with patch(
        "zigbeelens.config_flow._validate_core",
        new=AsyncMock(return_value={"status": "ok"}),
    ):
        result = await flow.async_step_init(
            {
                "core_url": "https://zigbeelens.theaussiepom.me",
                "verify_ssl": True,
                "panel_enabled": True,
                "scan_interval": 90,
            }
        )

    assert result["type"] == "create_entry"
    hass.config_entries.async_update_entry.assert_called_once()
    update_kwargs = hass.config_entries.async_update_entry.call_args.kwargs
    assert update_kwargs["unique_id"] == "https://zigbeelens.theaussiepom.me"
    assert update_kwargs["data"][CONF_CORE_URL] == "https://zigbeelens.theaussiepom.me"
    assert update_kwargs["options"][CONF_SCAN_INTERVAL] == 90
    hass.config_entries.async_reload.assert_awaited_once_with("entry1")


def test_translation_strings_mention_https_embed_guidance():
    import json
    from pathlib import Path

    strings = json.loads(
        (Path(__file__).resolve().parents[1] / "custom_components/zigbeelens/strings.json").read_text(
            encoding="utf-8"
        )
    )
    user_desc = strings["config"]["step"]["user"]["description"]
    options_desc = strings["options"]["step"]["init"]["description"]
    assert "HTTP is fine" in user_desc
    assert "embedded dashboard view" in user_desc
    assert "HTTPS Core URL" in options_desc or "HTTPS address" in options_desc


def test_update_panel_core_url():
    hass = MagicMock()
    hass.data = {frontend.DATA_PANELS: {PANEL_URL_PATH: {"config": {"core_url": "http://old"}}}}
    async_update_panel_core_url(hass, "https://zigbeelens.theaussiepom.me")
    assert (
        hass.data[frontend.DATA_PANELS][PANEL_URL_PATH]["config"]["core_url"]
        == "https://zigbeelens.theaussiepom.me"
    )
