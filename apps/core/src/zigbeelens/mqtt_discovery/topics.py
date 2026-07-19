"""Topic construction and safety validation for MQTT Discovery."""

from __future__ import annotations

import re

from zigbeelens.mqtt_discovery.models import ComponentType

_UNSAFE_PATTERNS = ("/bridge/request/",)
_OBJECT_ID_RE = re.compile(r"[^a-zA-Z0-9_-]+")
PRODUCT = "zigbeelens"


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
    allowed_prefixes = ("homeassistant/", f"{PRODUCT}/")
    if not any(normalized.startswith(prefix) for prefix in allowed_prefixes):
        raise UnsafeMqttTopicError(f"Topic must be under homeassistant/ or {PRODUCT}/")


def discovery_config_topic(
    topic_prefix: str,
    component: ComponentType,
    entity_key: str,
    *,
    product: str = PRODUCT,
) -> str:
    prefix = topic_prefix.strip("/")
    return f"{prefix}/{component}/{product}/{entity_key}/config"


def availability_topic(state_topic_prefix: str) -> str:
    prefix = state_topic_prefix.strip("/")
    return f"{prefix}/status"


def summary_state_topic(state_topic_prefix: str, entity_key: str) -> str:
    prefix = state_topic_prefix.strip("/")
    return f"{prefix}/summary/{entity_key}/state"


def summary_attributes_topic(state_topic_prefix: str, entity_key: str) -> str:
    prefix = state_topic_prefix.strip("/")
    return f"{prefix}/summary/{entity_key}/attributes"


# Superseded Track-4 Lens nested discovery config topics (tombstone on start).
# Do not reuse these entity keys for different semantics.
SUPERSEDED_LENS_DISCOVERY_TOPICS: tuple[str, ...] = (
    "homeassistant/sensor/zigbeelens/health/config",
    "homeassistant/sensor/zigbeelens/issues/config",
    "homeassistant/sensor/zigbeelens/needs_attention/config",
    "homeassistant/sensor/zigbeelens/recently_unstable/config",
    "homeassistant/sensor/zigbeelens/diagnostics_limited/config",
)

# Legacy discovery topics from the pre-clean flat MQTT model (for manual cleanup).
LEGACY_DISCOVERY_TOPICS: tuple[str, ...] = (
    "homeassistant/sensor/zigbeelens_overall_health/config",
    "homeassistant/binary_sensor/zigbeelens_active_incident/config",
    "homeassistant/sensor/zigbeelens_incident_state/config",
    "homeassistant/sensor/zigbeelens_unavailable_devices/config",
    "homeassistant/sensor/zigbeelens_recently_unstable_devices/config",
    "homeassistant/sensor/zigbeelens_router_risks/config",
    "homeassistant/sensor/zigbeelens_stale_devices/config",
    "homeassistant/sensor/zigbeelens_weak_link_devices/config",
    "homeassistant/sensor/zigbeelens_low_battery_devices/config",
    "homeassistant/sensor/zigbeelens_unknown_devices/config",
    "homeassistant/sensor/zigbeelens_network_count/config",
    "homeassistant/sensor/zigbeelens_device_count/config",
    "homeassistant/binary_sensor/zigbeelens_mqtt_collector_connected/config",
    "homeassistant/binary_sensor/zigbeelens_core_running/config",
)
