"""Coordinator tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from zigbeelens.api import ZigbeeLensApiClient
from zigbeelens.coordinator import ZigbeeLensDataUpdateCoordinator
from zigbeelens.exceptions import (
    ZigbeeLensAuthError,
    ZigbeeLensConnectionError,
    ZigbeeLensInvalidResponseError,
)


def _capabilities(*, version: object = 1) -> dict:
    return {
        "product": "zigbeelens",
        "version": "0.1.13",
        "decision_contract_version": version,
        "capabilities": {
            "shared_decisions": True,
            "companion_decision_summary": True,
        },
        "decision_surfaces": {
            "dashboard_investigation_priorities": True,
            "dashboard_data_coverage_warnings": True,
        },
    }


@pytest.fixture
def mock_client(sample_health, sample_dashboard, sample_config_status):
    client = MagicMock(spec=ZigbeeLensApiClient)
    client.async_get_health = AsyncMock(return_value=sample_health)
    client.async_get_dashboard = AsyncMock(return_value=sample_dashboard)
    client.async_get_config_status = AsyncMock(return_value=sample_config_status)
    client.async_get_capabilities = AsyncMock(return_value=_capabilities())
    client.core_url = "http://localhost:8377"
    return client


def _bare_coordinator(mock_client) -> ZigbeeLensDataUpdateCoordinator:
    coordinator = ZigbeeLensDataUpdateCoordinator.__new__(ZigbeeLensDataUpdateCoordinator)
    coordinator.client = mock_client
    coordinator.last_update_success = False
    coordinator.last_exception = None
    coordinator.auth_failed = False
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
async def test_coordinator_rejects_contract_version_2(mock_client):
    mock_client.async_get_capabilities = AsyncMock(return_value=_capabilities(version=2))
    coordinator = _bare_coordinator(mock_client)
    data = await coordinator._async_update_data()
    assert coordinator.last_update_success is True
    assert data.shared_decisions_available is False
    assert data.decision_contract_version == 2
    assert data.core_version_compatible is True


@pytest.mark.asyncio
async def test_coordinator_tolerates_missing_capabilities(mock_client):
    mock_client.async_get_capabilities = AsyncMock(
        side_effect=ZigbeeLensInvalidResponseError("missing")
    )
    coordinator = _bare_coordinator(mock_client)
    data = await coordinator._async_update_data()
    assert data.shared_decisions_available is False
    assert data.decision_contract_version == 0
    assert coordinator.last_update_success is True


@pytest.mark.asyncio
async def test_coordinator_gates_decisions_when_core_incompatible(
    mock_client, sample_health
):
    sample_health = dict(sample_health)
    sample_health["version"] = "0.0.1"
    mock_client.async_get_health = AsyncMock(return_value=sample_health)
    coordinator = _bare_coordinator(mock_client)
    data = await coordinator._async_update_data()
    assert data.core_version_compatible is False
    assert data.shared_decisions_available is False
    assert data.decision_contract_version == 1


@pytest.mark.asyncio
async def test_coordinator_rejects_malformed_dashboard_decision_surfaces(mock_client):
    dashboard = dict(mock_client.async_get_dashboard.return_value)
    dashboard.pop("investigation_priorities", None)
    mock_client.async_get_dashboard = AsyncMock(return_value=dashboard)
    coordinator = _bare_coordinator(mock_client)
    data = await coordinator._async_update_data()
    assert coordinator.last_update_success is True
    assert data.decision_contract_version == 1
    assert data.shared_decisions_available is False
    assert data.core_version_compatible is True


@pytest.mark.asyncio
async def test_coordinator_accepts_valid_empty_decision_lists(mock_client):
    dashboard = dict(mock_client.async_get_dashboard.return_value)
    dashboard["investigation_priorities"] = []
    dashboard["data_coverage_warnings"] = []
    mock_client.async_get_dashboard = AsyncMock(return_value=dashboard)
    coordinator = _bare_coordinator(mock_client)
    data = await coordinator._async_update_data()
    assert data.shared_decisions_available is True
    mock_client.async_get_health = AsyncMock(side_effect=ZigbeeLensConnectionError("down"))
    coordinator = _bare_coordinator(mock_client)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.last_update_success is False
    assert coordinator.auth_failed is False


@pytest.mark.asyncio
async def test_coordinator_health_401_raises_auth_failed(mock_client):
    mock_client.async_get_health = AsyncMock(
        side_effect=ZigbeeLensAuthError("Authentication required")
    )
    coordinator = _bare_coordinator(mock_client)
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
    assert coordinator.auth_failed is True
    assert coordinator.last_exception == "Authentication required"
    assert "Bearer" not in (coordinator.last_exception or "")


@pytest.mark.asyncio
async def test_coordinator_dashboard_401_raises_auth_failed(mock_client):
    mock_client.async_get_dashboard = AsyncMock(
        side_effect=ZigbeeLensAuthError("Authentication required")
    )
    coordinator = _bare_coordinator(mock_client)
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
    assert coordinator.auth_failed is True


@pytest.mark.asyncio
async def test_coordinator_capabilities_401_raises_auth_failed(mock_client):
    mock_client.async_get_capabilities = AsyncMock(
        side_effect=ZigbeeLensAuthError("Authentication required")
    )
    coordinator = _bare_coordinator(mock_client)
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
    assert coordinator.auth_failed is True
