"""Coordinator tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from zigbeelens.api import ZigbeeLensApiClient
from zigbeelens.coordinator import ZigbeeLensDataUpdateCoordinator
from zigbeelens.exceptions import ZigbeeLensConnectionError


@pytest.fixture
def mock_client(sample_health, sample_dashboard, sample_config_status):
    client = MagicMock(spec=ZigbeeLensApiClient)
    client.async_get_health = AsyncMock(return_value=sample_health)
    client.async_get_dashboard = AsyncMock(return_value=sample_dashboard)
    client.async_get_config_status = AsyncMock(return_value=sample_config_status)
    client.async_get_capabilities = AsyncMock(
        return_value={
            "product": "zigbeelens",
            "version": "0.1.13",
            "decision_contract_version": 1,
            "capabilities": {
                "shared_decisions": True,
                "companion_decision_summary": True,
            },
            "decision_surfaces": {
                "dashboard_investigation_priorities": True,
            },
        }
    )
    client.core_url = "http://localhost:8377"
    return client


def _bare_coordinator(mock_client) -> ZigbeeLensDataUpdateCoordinator:
    coordinator = ZigbeeLensDataUpdateCoordinator.__new__(ZigbeeLensDataUpdateCoordinator)
    coordinator.client = mock_client
    coordinator.last_update_success = False
    coordinator.last_exception = None
    return coordinator


@pytest.mark.asyncio
async def test_coordinator_first_refresh_success(mock_client):
    coordinator = _bare_coordinator(mock_client)
    data = await coordinator._async_update_data()
    assert data.core_version == "0.1.0"
    assert data.collector_connected is True
    assert coordinator.last_update_success is True
    assert data.shared_decisions_available is True
    assert data.decision_contract_version == 1
    assert data.core_version_compatible is True


@pytest.mark.asyncio
async def test_coordinator_tolerates_missing_capabilities(mock_client):
    from zigbeelens.exceptions import ZigbeeLensInvalidResponseError

    mock_client.async_get_capabilities = AsyncMock(
        side_effect=ZigbeeLensInvalidResponseError("missing")
    )
    coordinator = _bare_coordinator(mock_client)
    data = await coordinator._async_update_data()
    assert data.shared_decisions_available is False
    assert data.decision_contract_version == 0
    assert coordinator.last_update_success is True


@pytest.mark.asyncio
async def test_coordinator_refresh_failure(mock_client):
    mock_client.async_get_health = AsyncMock(side_effect=ZigbeeLensConnectionError("down"))
    coordinator = _bare_coordinator(mock_client)
    from homeassistant.helpers.update_coordinator import UpdateFailed

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.last_update_success is False
