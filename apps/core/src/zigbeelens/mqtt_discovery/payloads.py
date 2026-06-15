"""Home Assistant MQTT Discovery config and state payload builders."""

from __future__ import annotations

import json
from typing import Any

from zigbeelens.mqtt_discovery.models import DiscoveryDevice, DiscoveryEntity, PublishedEntityState
from zigbeelens.mqtt_discovery.topics import (
    PRODUCT,
    discovery_config_topic,
    summary_attributes_topic,
    summary_state_topic,
)
from zigbeelens.presentation.lens_mqtt import SummaryEntityState, build_summary_entities
from zigbeelens.schemas import DashboardPayload

SUMMARY_ENTITY_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("health", "ZigbeeLens Health"),
    ("issues", "ZigbeeLens Issues"),
    ("unavailable", "ZigbeeLens Unavailable Devices"),
    ("needs_attention", "ZigbeeLens Needs Attention"),
    ("recently_unstable", "ZigbeeLens Recently Unstable"),
    ("diagnostics_limited", "ZigbeeLens Diagnostics Limited"),
)


def build_discovery_device(
    *,
    device_name: str,
    core_version: str,
    configuration_url: str | None = None,
) -> DiscoveryDevice:
    return DiscoveryDevice(
        identifiers=["zigbeelens_core"],
        manufacturer="ZigbeeLens",
        name=device_name,
        model="ZigbeeLens Core",
        sw_version=core_version,
        configuration_url=configuration_url,
    )


def _summary_discovery_entity(
    summary: SummaryEntityState,
    topic_prefix: str,
    state_topic_prefix: str,
) -> DiscoveryEntity:
    del topic_prefix
    object_id = f"{PRODUCT}_{summary.key}"
    return DiscoveryEntity(
        unique_id=object_id,
        object_id=object_id,
        component="sensor",
        name=summary.name,
        state_topic=summary_state_topic(state_topic_prefix, summary.key),
        value_template="",
        json_attributes_topic=summary_attributes_topic(state_topic_prefix, summary.key),
    )


def summary_entity_catalog(
    *,
    topic_prefix: str,
    state_topic_prefix: str,
    device: DiscoveryDevice,
) -> list[DiscoveryEntity]:
    del device
    entities: list[DiscoveryEntity] = []
    for entity_key, name in SUMMARY_ENTITY_DEFINITIONS:
        summary = SummaryEntityState(key=entity_key, name=name, state="", attributes={})
        entities.append(_summary_discovery_entity(summary, topic_prefix, state_topic_prefix))
    return entities


def entity_catalog(
    *,
    topic_prefix: str,
    state_topic_prefix: str,
    object_id_prefix: str,
    availability: str,
    device: DiscoveryDevice,
) -> list[DiscoveryEntity]:
    del object_id_prefix, availability
    return summary_entity_catalog(
        topic_prefix=topic_prefix,
        state_topic_prefix=state_topic_prefix,
        device=device,
    )


def discovery_config_payload(entity: DiscoveryEntity, availability: str, device: DiscoveryDevice) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": entity.name,
        "unique_id": entity.unique_id,
        "object_id": entity.object_id,
        "state_topic": entity.state_topic,
        "availability_topic": availability,
        "payload_available": "online",
        "payload_not_available": "offline",
        "device": {
            "identifiers": device.identifiers,
            "manufacturer": device.manufacturer,
            "name": device.name,
            "model": device.model,
            "sw_version": device.sw_version,
        },
    }
    if entity.json_attributes_topic:
        payload["json_attributes_topic"] = entity.json_attributes_topic
    if entity.state_class:
        payload["state_class"] = entity.state_class
    if device.configuration_url:
        payload["device"]["configuration_url"] = device.configuration_url
    return payload


def discovery_topic_for_entity(topic_prefix: str, entity: DiscoveryEntity) -> str:
    entity_key = entity.object_id.removeprefix(f"{PRODUCT}_")
    return discovery_config_topic(topic_prefix, entity.component, entity_key)


def state_payload(state: PublishedEntityState) -> str:
    return str(state.state)


def attributes_payload(state: PublishedEntityState) -> str:
    return json.dumps(state.attributes, separators=(",", ":"))


def build_states_from_dashboard(
    dashboard: DashboardPayload,
    *,
    core_version: str,
    collector_connected: bool,
    mock_mode: bool = False,
) -> dict[str, PublishedEntityState]:
    summaries = build_summary_entities(
        dashboard,
        core_version=core_version,
        collector_connected=collector_connected,
        mock_mode=mock_mode,
    )
    return {
        summary.key: PublishedEntityState(state=summary.state, attributes=summary.attributes)
        for summary in summaries
    }


def all_discovery_entities(
    *,
    topic_prefix: str,
    state_topic_prefix: str,
    object_id_prefix: str,
    availability: str,
    device: DiscoveryDevice,
    dashboard: DashboardPayload,
) -> list[DiscoveryEntity]:
    del dashboard, object_id_prefix, availability
    return summary_entity_catalog(
        topic_prefix=topic_prefix,
        state_topic_prefix=state_topic_prefix,
        device=device,
    )
