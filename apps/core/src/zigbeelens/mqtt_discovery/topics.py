"""Topic construction and safety validation for MQTT Discovery."""

from __future__ import annotations

import re

from zigbeelens.mqtt_discovery.models import ComponentType

_UNSAFE_PATTERNS = ("/bridge/request/",)
_OBJECT_ID_RE = re.compile(r"[^a-zA-Z0-9_-]+")


class UnsafeMqttTopicError(ValueError):
    """Raised when a topic fails ZigbeeLens publish safety checks."""


def sanitize_object_id(value: str) -> str:
    cleaned = _OBJECT_ID_RE.sub("_", value.strip()).strip("_")
    return cleaned or "unknown"


def validate_publish_topic(topic: str, *, zigbee_base_topics: tuple[str, ...] = ()) -> None:
    """Reject topics that could mutate Zigbee2MQTT or use wildcards."""
    if not topic or not topic.strip():
        raise UnsafeMqttTopicError("Topic must not be empty")
    normalized = topic.strip()
    if "+" in normalized or "#" in normalized:
        raise UnsafeMqttTopicError("Wildcard topics are not allowed")
    if normalized.endswith("/set"):
        raise UnsafeMqttTopicError("Set topics are not allowed")
    for pattern in _UNSAFE_PATTERNS:
        if pattern in normalized:
            raise UnsafeMqttTopicError(f"Unsafe topic pattern: {pattern}")
    for base in zigbee_base_topics:
        base = base.strip("/")
        if not base:
            continue
        if normalized == base or normalized.startswith(f"{base}/"):
            raise UnsafeMqttTopicError("Publishing under Zigbee2MQTT base topics is not allowed")
    allowed_prefixes = ("homeassistant/", "zigbeelens/")
    if not any(normalized.startswith(prefix) for prefix in allowed_prefixes):
        raise UnsafeMqttTopicError("Topic must be under homeassistant/ or zigbeelens/")


def discovery_config_topic(topic_prefix: str, component: ComponentType, object_id: str) -> str:
    prefix = topic_prefix.strip("/")
    return f"{prefix}/{component}/{object_id}/config"


def availability_topic(state_topic_prefix: str) -> str:
    prefix = state_topic_prefix.strip("/")
    return f"{prefix}/status"


def state_topic(state_topic_prefix: str, path: str) -> str:
    prefix = state_topic_prefix.strip("/")
    segment = path.strip("/")
    return f"{prefix}/state/{segment}"
