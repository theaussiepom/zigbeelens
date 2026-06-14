"""Models for MQTT Discovery publishing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ComponentType = Literal["sensor", "binary_sensor"]


@dataclass(frozen=True)
class DiscoveryDevice:
    identifiers: list[list[str]]
    manufacturer: str
    name: str
    model: str
    sw_version: str | None = None
    configuration_url: str | None = None


@dataclass(frozen=True)
class DiscoveryEntity:
    unique_id: str
    object_id: str
    component: ComponentType
    name: str
    state_topic: str
    value_template: str
    json_attributes_topic: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    unit_of_measurement: str | None = None
    icon: str | None = None


@dataclass
class PublishedEntityState:
    state: str | int | float | bool
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class MqttDiscoveryStatus:
    enabled: bool = False
    connected: bool = False
    published_entities_count: int = 0
    last_publish_at: str | None = None
    last_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "connected": self.connected,
            "published_entities_count": self.published_entities_count,
            "last_publish_at": self.last_publish_at,
            "last_error": self.last_error,
        }
