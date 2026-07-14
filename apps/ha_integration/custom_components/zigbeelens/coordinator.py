"""DataUpdateCoordinator for ZigbeeLens Core."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ZigbeeLensApiClient
from .compatibility import (
    core_version_compatible,
    decision_contract_version,
    supports_companion_decisions,
)
from .const import DOMAIN
from .exceptions import ZigbeeLensApiError, ZigbeeLensInvalidResponseError

_LOGGER = logging.getLogger(__name__)


@dataclass
class ZigbeeLensCoordinatorData:
    """Coordinator snapshot used by entities and repairs."""

    health: dict[str, Any]
    dashboard: dict[str, Any]
    config_status: dict[str, Any]
    core_version: str
    collector_connected: bool
    last_update_success: bool
    last_exception: str | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)
    decision_contract_version: int = 0
    shared_decisions_available: bool = False
    core_version_compatible: bool = True


class ZigbeeLensDataUpdateCoordinator(DataUpdateCoordinator[ZigbeeLensCoordinatorData]):
    """Fetch summary data from ZigbeeLens Core."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ZigbeeLensApiClient,
        scan_interval: int,
        config_entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
            config_entry=config_entry,
        )
        self.client = client
        self.last_update_success = False
        self.last_exception: str | None = None

    async def _async_update_data(self) -> ZigbeeLensCoordinatorData:
        try:
            health = await self.client.async_get_health()
            dashboard = await self.client.async_get_dashboard()
            config_status = await self.client.async_get_config_status()
        except ZigbeeLensApiError as err:
            self.last_update_success = False
            self.last_exception = str(err)
            raise UpdateFailed(str(err)) from err

        capabilities: dict[str, Any] = {}
        try:
            capabilities = await self.client.async_get_capabilities()
        except ZigbeeLensInvalidResponseError as err:
            # Older Core without capabilities / decision contract — soft degrade.
            _LOGGER.debug("Core capabilities unavailable: %s", err)
        except ZigbeeLensApiError as err:
            _LOGGER.debug("Core capabilities fetch failed: %s", err)

        collector = health.get("collector") or {}
        connected = bool(collector.get("connected"))
        core_version = str(health.get("version", ""))
        version_compatible = core_version_compatible(core_version)
        contract_supported = supports_companion_decisions(capabilities)
        self.last_update_success = True
        self.last_exception = None

        return ZigbeeLensCoordinatorData(
            health=health,
            dashboard=dashboard,
            config_status=config_status,
            core_version=core_version,
            collector_connected=connected,
            last_update_success=True,
            last_exception=None,
            capabilities=capabilities,
            decision_contract_version=decision_contract_version(capabilities),
            shared_decisions_available=version_compatible and contract_supported,
            core_version_compatible=version_compatible,
        )
