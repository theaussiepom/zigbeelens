"""MQTT collector data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TopicKind(str, Enum):
    bridge_state = "bridge_state"
    bridge_info = "bridge_info"
    bridge_devices = "bridge_devices"
    bridge_event = "bridge_event"
    bridge_logging = "bridge_logging"
    bridge_health = "bridge_health"
    device_availability = "device_availability"
    device_payload = "device_payload"
    unknown_bridge_topic = "unknown_bridge_topic"
    ignored = "ignored"
    request_topic = "request_topic"


@dataclass
class TopicClassification:
    network_id: str
    base_topic: str
    kind: TopicKind
    friendly_name: str | None = None
    bridge_subtopic: str | None = None


@dataclass
class RawMqttMessage:
    topic: str
    payload: bytes
    retained: bool = False
    received_at: str = ""


@dataclass
class NormalizedMqttEvent:
    event_type: str
    network_id: str
    title: str
    summary: str
    severity: str = "watch"
    ieee_address: str | None = None
    friendly_name: str | None = None
    bridge_state: str | None = None
    availability: str | None = None
    devices: list[dict[str, Any]] = field(default_factory=list)
    device_fields: dict[str, Any] = field(default_factory=dict)
    bridge_info: dict[str, Any] = field(default_factory=dict)
    log_level: str | None = None
    log_message: str | None = None
    raw_payload_redacted: str | None = None
    parse_error: str | None = None
    emit_dashboard: bool = False


@dataclass
class NetworkSubscriptionStatus:
    network_id: str
    base_topic: str
    subscribed: bool = False


@dataclass
class MqttCollectorStatus:
    enabled: bool = False
    connected: bool = False
    subscribed_topics_count: int = 0
    last_message_at: str | None = None
    last_error: str | None = None
    networks: list[NetworkSubscriptionStatus] = field(default_factory=list)
