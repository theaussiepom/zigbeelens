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


def _capabilities(*, version: object = 2) -> dict:
    return {
        "product": "zigbeelens",
        "version": "0.1.13",
        "decision_contract_version": version,
        "capabilities": {
            "shared_decisions": True,
            "companion_decision_summary": True,
            "decision_only_diagnostic_payloads": True,
            "report_contract_v3": True,
            "decision_mqtt_summary": True,
            "legacy_health_lens_payloads": False,
        },
        "decision_surfaces": {
            "dashboard_decision_summary": True,
            "dashboard_investigation_priorities": True,
            "dashboard_data_coverage_warnings": True,
            "network_decision_badges": True,
            "device_decision_badges": True,
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
    assert data.decision_contract_version == 2
    assert data.core_version_compatible is True


@pytest.mark.asyncio
async def test_coordinator_rejects_contract_version_1(mock_client):
    mock_client.async_get_capabilities = AsyncMock(return_value=_capabilities(version=1))
    coordinator = _bare_coordinator(mock_client)
    data = await coordinator._async_update_data()
    assert coordinator.last_update_success is True
    assert data.shared_decisions_available is False
    assert data.decision_contract_version == 1
    assert data.core_version_compatible is True
    assert coordinator.auth_failed is False


@pytest.mark.asyncio
async def test_coordinator_rejects_newer_contract(mock_client):
    mock_client.async_get_capabilities = AsyncMock(return_value=_capabilities(version=3))
    coordinator = _bare_coordinator(mock_client)
    data = await coordinator._async_update_data()
    assert data.shared_decisions_available is False
    assert data.decision_contract_version == 3
    assert coordinator.auth_failed is False


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
    assert data.decision_contract_version == 2


@pytest.mark.asyncio
async def test_coordinator_rejects_malformed_dashboard_decision_surfaces(mock_client):
    dashboard = dict(mock_client.async_get_dashboard.return_value)
    dashboard.pop("decision_summary", None)
    mock_client.async_get_dashboard = AsyncMock(return_value=dashboard)
    coordinator = _bare_coordinator(mock_client)
    data = await coordinator._async_update_data()
    assert coordinator.last_update_success is True
    assert data.decision_contract_version == 2
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


@pytest.mark.asyncio
async def test_coordinator_auth_error_still_raises_reauth(mock_client):
    mock_client.async_get_health = AsyncMock(side_effect=ZigbeeLensAuthError("401"))
    coordinator = _bare_coordinator(mock_client)
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
    assert coordinator.auth_failed is True


@pytest.mark.asyncio
async def test_coordinator_connection_error_is_update_failed(mock_client):
    mock_client.async_get_health = AsyncMock(side_effect=ZigbeeLensConnectionError("down"))
    coordinator = _bare_coordinator(mock_client)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.auth_failed is False
