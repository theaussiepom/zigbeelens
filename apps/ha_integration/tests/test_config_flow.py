"""Config flow tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zigbeelens.config_flow import ZigbeeLensConfigFlow, _normalize_core_url
from zigbeelens.exceptions import ZigbeeLensConnectionError


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
