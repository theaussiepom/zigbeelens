"""Zigbee2MQTT topic parsing and classification."""

from __future__ import annotations

from zigbeelens.config.models import NetworkConfig
from zigbeelens.mqtt.models import TopicClassification, TopicKind

BRIDGE_KNOWN = {
    "state": TopicKind.bridge_state,
    "info": TopicKind.bridge_info,
    "devices": TopicKind.bridge_devices,
    "event": TopicKind.bridge_event,
    "logging": TopicKind.bridge_logging,
    "health": TopicKind.bridge_health,
}

BRIDGE_IGNORED = {"request", "response", "extensions", "groups", "definitions"}


def match_network(topic: str, networks: list[NetworkConfig]) -> NetworkConfig | None:
    matches = [n for n in networks if topic == n.base_topic or topic.startswith(n.base_topic + "/")]
    if not matches:
        return None
    return max(matches, key=lambda n: len(n.base_topic))


def classify_topic(topic: str, networks: list[NetworkConfig]) -> TopicClassification | None:
    network = match_network(topic, networks)
    if network is None:
        return None

    prefix = network.base_topic + "/"
    if not topic.startswith(prefix):
        return None

    remainder = topic[len(prefix) :]
    if not remainder:
        return None

    parts = remainder.split("/")

    if parts[0] == "bridge":
        if len(parts) == 1:
            return TopicClassification(network.id, network.base_topic, TopicKind.unknown_bridge_topic)
        sub = parts[1]
        if sub in BRIDGE_IGNORED:
            return TopicClassification(
                network.id, network.base_topic, TopicKind.ignored, bridge_subtopic=sub
            )
        if sub == "request" or sub == "response":
            return TopicClassification(
                network.id, network.base_topic, TopicKind.request_topic, bridge_subtopic=sub
            )
        kind = BRIDGE_KNOWN.get(sub, TopicKind.unknown_bridge_topic)
        return TopicClassification(
            network.id, network.base_topic, kind, bridge_subtopic=sub
        )

    if len(parts) == 1:
        return TopicClassification(
            network.id, network.base_topic, TopicKind.device_payload, friendly_name=parts[0]
        )

    if len(parts) == 2 and parts[1] == "availability":
        return TopicClassification(
            network.id,
            network.base_topic,
            TopicKind.device_availability,
            friendly_name=parts[0],
        )

    return TopicClassification(network.id, network.base_topic, TopicKind.ignored)


def subscription_topics(base_topic: str, *, include_topology_response: bool = False) -> list[str]:
    topics = [
        f"{base_topic}/bridge/state",
        f"{base_topic}/bridge/info",
        f"{base_topic}/bridge/devices",
        f"{base_topic}/bridge/event",
        f"{base_topic}/bridge/logging",
        f"{base_topic}/bridge/health",
        f"{base_topic}/+/availability",
        f"{base_topic}/+",
    ]
    if include_topology_response:
        topics.append(f"{base_topic}/bridge/response/networkmap")
    return topics
