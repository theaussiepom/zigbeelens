"""Binary sensor platform for ZigbeeLens."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry

from .compatibility import nonneg_int_not_bool
from .const import DOMAIN
from .coordinator import ZigbeeLensDataUpdateCoordinator
from .entity import ZigbeeLensEntity

BINARY_SENSORS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="active_incident",
        translation_key="active_incident",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    BinarySensorEntityDescription(
        key="core_connected",
        translation_key="core_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    BinarySensorEntityDescription(
        key="mqtt_collector_connected",
        translation_key="mqtt_collector_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ZigbeeLensDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    async_add_entities(
        ZigbeeLensBinarySensor(coordinator, entry.entry_id, description)
        for description in BINARY_SENSORS
    )


class ZigbeeLensBinarySensor(ZigbeeLensEntity, BinarySensorEntity):
    """ZigbeeLens summary binary sensor."""

    entity_description: BinarySensorEntityDescription

    def __init__(
        self,
        coordinator: ZigbeeLensDataUpdateCoordinator,
        entry_id: str,
        description: BinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry_id, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return False
        key = self.entity_description.key
        if key == "active_incident":
            if "active_incident_count" not in self.dashboard:
                return None
            active = nonneg_int_not_bool(self.dashboard.get("active_incident_count"))
            if active is None:
                return None
            return active > 0
        if key == "core_connected":
            return self.coordinator.last_update_success
        if key == "mqtt_collector_connected":
            return self.coordinator.data.collector_connected
        return None

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {}
        key = self.entity_description.key
        if key == "active_incident":
            decision = self.dashboard.get("decision_summary") or {}
            return {
                "active_incident_count": self.dashboard.get("active_incident_count"),
                "watching_incident_count": self.dashboard.get("watching_incident_count"),
                "overall_decision_status": (
                    decision.get("overall_status") if isinstance(decision, dict) else None
                ),
            }
        if key == "core_connected":
            return {
                "core_url": self.coordinator.client.core_url,
                "core_version": self.coordinator.data.core_version,
                "last_update_success": self.coordinator.last_update_success,
                "collector_connected": self.coordinator.data.collector_connected,
            }
        if key == "mqtt_collector_connected":
            collector = self.health.get("collector") or {}
            last_error = collector.get("last_error")
            return {
                "last_message_at": collector.get("last_message_at"),
                "subscribed_topics_count": collector.get("subscribed_topics_count"),
                "last_error": "[redacted]" if last_error else None,
            }
        return {}
