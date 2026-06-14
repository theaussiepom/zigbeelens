"""Strict topic allowlist for topology network map requests."""

from __future__ import annotations

TOPOLOGY_LIMITATION = (
    "Topology is a point-in-time snapshot and may not reflect current routing."
)

CAPTURE_WARNING = (
    "Capturing a Zigbee network map asks Zigbee2MQTT to scan the mesh. "
    "On larger networks this may temporarily make Zigbee less responsive. "
    "ZigbeeLens will not change Zigbee state, but this diagnostic request can "
    "create temporary network load."
)


class UnsafeTopologyTopicError(ValueError):
    """Raised when a topology publish topic is not allowlisted."""


def networkmap_request_topic(base_topic: str) -> str:
    return f"{base_topic.strip('/')}/bridge/request/networkmap"


def networkmap_response_topic(base_topic: str) -> str:
    return f"{base_topic.strip('/')}/bridge/response/networkmap"


def is_networkmap_response_topic(topic: str, base_topic: str) -> bool:
    return topic == networkmap_response_topic(base_topic)


def validate_topology_request_topic(topic: str, *, allowed_base_topics: tuple[str, ...]) -> None:
    if not topic or "+" in topic or "#" in topic:
        raise UnsafeTopologyTopicError("Invalid topology request topic")
    if topic.endswith("/set"):
        raise UnsafeTopologyTopicError("Set topics are not allowed")
    if "/bridge/request/" not in topic:
        raise UnsafeTopologyTopicError("Only bridge/request topics are allowed for topology capture")
    if not topic.endswith("/bridge/request/networkmap"):
        raise UnsafeTopologyTopicError("Only networkmap request topic is allowed")
    for base in allowed_base_topics:
        expected = networkmap_request_topic(base)
        if topic == expected:
            return
    raise UnsafeTopologyTopicError("Network map request topic does not match a configured network")
