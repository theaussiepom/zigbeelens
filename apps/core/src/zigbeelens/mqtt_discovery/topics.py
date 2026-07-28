"""Topic construction and safety validation for MQTT Discovery."""

from __future__ import annotations

import re

from zigbeelens.mqtt_discovery.models import ComponentType

_UNSAFE_PATTERNS = ("/bridge/request/",)
_OBJECT_ID_RE = re.compile(r"[^a-zA-Z0-9_-]+")
PRODUCT = "zigbeelens"


class UnsafeMqttTopicError(ValueError):
    """Raised when a topic fails ZigbeeLens publish safety checks."""


def _validate_mqtt_topic_text(topic: str) -> None:
    """Enforce MQTT's bounded UTF-8 topic-name representation."""
    try:
        encoded = topic.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise UnsafeMqttTopicError("Topic must be valid UTF-8") from exc
    if len(encoded) > 65_535:
        raise UnsafeMqttTopicError("Topic exceeds the MQTT UTF-8 length limit")
    if any(
        codepoint == 0
        or codepoint < 0x20
        or 0x7F <= codepoint <= 0x9F
        or 0xFDD0 <= codepoint <= 0xFDEF
        or codepoint & 0xFFFF in {0xFFFE, 0xFFFF}
        for codepoint in map(ord, topic)
    ):
        raise UnsafeMqttTopicError(
            "Topic contains a forbidden MQTT Unicode code point"
        )


def sanitize_object_id(value: str) -> str:
    cleaned = _OBJECT_ID_RE.sub("_", value.strip()).strip("_")
    return cleaned or "unknown"


def validate_publish_topic(
    topic: str,
    *,
    zigbee_base_topics: tuple[str, ...] = (),
    discovery_topic_prefix: str | None = None,
    allowed_topic_prefixes: tuple[str, ...] = (),
) -> None:
    """Reject topics that could mutate Zigbee2MQTT or use wildcards."""
    if not topic or not topic.strip():
        raise UnsafeMqttTopicError("Topic must not be empty")
    _validate_mqtt_topic_text(topic)
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
    allowed = ["homeassistant/", f"{PRODUCT}/"]
    if discovery_topic_prefix:
        custom = discovery_topic_prefix.strip("/")
        if custom:
            allowed.append(f"{custom}/")
    for configured_prefix in allowed_topic_prefixes:
        custom = configured_prefix.strip("/")
        if custom:
            allowed.append(f"{custom}/")
    if not any(normalized.startswith(prefix) for prefix in allowed):
        raise UnsafeMqttTopicError(
            f"Topic must be under homeassistant/, {PRODUCT}/, or the configured discovery prefix"
        )


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


def validated_availability_topic(
    state_topic_prefix: str,
    *,
    zigbee_base_topics: tuple[str, ...] = (),
) -> str:
    """Build and validate the exact Discovery availability/LWT topic.

    This is the single production owner for the topic used by the real
    publisher, the fake publisher, and the Discovery service payloads.
    """
    prefix = state_topic_prefix
    if not prefix or prefix != prefix.strip():
        raise UnsafeMqttTopicError("State topic prefix must be nonempty and canonical")
    _validate_mqtt_topic_text(f"{prefix}/status")
    segments = prefix.split("/")
    if any(not segment or segment != segment.strip() for segment in segments):
        raise UnsafeMqttTopicError("State topic prefix contains malformed separators")
    if any(segment in {".", ".."} for segment in segments):
        raise UnsafeMqttTopicError("State topic prefix contains a traversal segment")
    if any("+" in segment or "#" in segment for segment in segments):
        raise UnsafeMqttTopicError("Wildcard topics are not allowed")
    if any(segment.casefold() == "set" for segment in segments):
        raise UnsafeMqttTopicError("Set topic segments are not allowed")
    lowered_segments = tuple(segment.casefold() for segment in segments)
    if any(
        lowered_segments[index : index + 2] == ("bridge", "request")
        for index in range(len(lowered_segments) - 1)
    ):
        raise UnsafeMqttTopicError("Bridge request topic segments are not allowed")

    for raw_base in zigbee_base_topics:
        base = raw_base.strip().strip("/")
        if not base:
            continue
        if (
            prefix == base
            or prefix.startswith(f"{base}/")
            or base.startswith(f"{prefix}/")
        ):
            raise UnsafeMqttTopicError(
                "State topic prefix must not overlap a Zigbee2MQTT base topic"
            )

    topic = f"{prefix}/status"
    validate_publish_topic(
        topic,
        zigbee_base_topics=zigbee_base_topics,
        allowed_topic_prefixes=(prefix,),
    )
    return topic


def summary_state_topic(state_topic_prefix: str, entity_key: str) -> str:
    prefix = state_topic_prefix.strip("/")
    return f"{prefix}/summary/{entity_key}/state"


def summary_attributes_topic(state_topic_prefix: str, entity_key: str) -> str:
    prefix = state_topic_prefix.strip("/")
    return f"{prefix}/summary/{entity_key}/attributes"


# Superseded Track-4 Lens nested discovery entity keys (tombstone on start).
# Topics are built with the configured mqtt_discovery.topic_prefix.
# Do not reuse these entity keys for different semantics.
SUPERSEDED_LENS_DISCOVERY_ENTITY_KEYS: tuple[str, ...] = (
    "health",
    "issues",
    "needs_attention",
    "recently_unstable",
    "diagnostics_limited",
)


def superseded_lens_discovery_topics(topic_prefix: str) -> tuple[str, ...]:
    """Discovery config topics for superseded Lens entities under the active prefix."""
    return tuple(
        discovery_config_topic(topic_prefix, "sensor", key)
        for key in SUPERSEDED_LENS_DISCOVERY_ENTITY_KEYS
    )


# Backward-compatible default-prefix constant for docs/tests that expect full topics.
SUPERSEDED_LENS_DISCOVERY_TOPICS: tuple[str, ...] = superseded_lens_discovery_topics(
    "homeassistant"
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
