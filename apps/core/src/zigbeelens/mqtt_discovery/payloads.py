"""Home Assistant MQTT Discovery config and state payload builders."""

from __future__ import annotations

import json
from typing import Any

from zigbeelens.mqtt_discovery.models import DiscoveryDevice, DiscoveryEntity, PublishedEntityState
from zigbeelens.mqtt_discovery.topics import availability_topic, discovery_config_topic, sanitize_object_id, state_topic
from zigbeelens.schemas import DashboardPayload, Severity


def _severity_state(value: Severity | str | None) -> str:
    if value is None:
        return "unknown"
    raw = value.value if isinstance(value, Severity) else str(value)
    if raw in ("healthy", "ok"):
        return "ok"
    if raw == "watch":
        return "watch"
    if raw in ("incident", "critical"):
        return "incident"
    if raw.startswith("Severity."):
        return raw.split(".", 1)[1]
    return raw


def _unknown_count(dashboard: DashboardPayload) -> int:
    count = 0
    for bucket in (
        dashboard.top_affected_devices,
        dashboard.recently_unstable,
        dashboard.weak_links,
        dashboard.low_batteries,
        dashboard.stale_devices,
    ):
        for device in bucket:
            if device.health.primary.value == "unknown":
                count += 1
    return count


def build_discovery_device(
    *,
    device_name: str,
    core_version: str,
    configuration_url: str | None = None,
) -> DiscoveryDevice:
    return DiscoveryDevice(
        identifiers=[["zigbeelens", "core"]],
        manufacturer="ZigbeeLens",
        name=device_name,
        model="ZigbeeLens Core",
        sw_version=core_version,
        configuration_url=configuration_url,
    )


def entity_catalog(
    *,
    topic_prefix: str,
    state_topic_prefix: str,
    object_id_prefix: str,
    availability: str,
    device: DiscoveryDevice,
) -> list[DiscoveryEntity]:
    device_payload = {
        "identifiers": device.identifiers,
        "manufacturer": device.manufacturer,
        "name": device.name,
        "model": device.model,
        "sw_version": device.sw_version,
    }
    if device.configuration_url:
        device_payload["configuration_url"] = device.configuration_url

    def _entity(
        key: str,
        component: str,
        name: str,
        state_path: str,
        *,
        device_class: str | None = None,
        state_class: str | None = None,
        unit: str | None = None,
    ) -> DiscoveryEntity:
        object_id = sanitize_object_id(f"{object_id_prefix}_{key}")
        return DiscoveryEntity(
            unique_id=f"zigbeelens_{key}",
            object_id=object_id,
            component=component,  # type: ignore[arg-type]
            name=name,
            state_topic=state_topic(state_topic_prefix, state_path),
            value_template="{{ value_json.state }}",
            json_attributes_topic=state_topic(state_topic_prefix, state_path),
            device_class=device_class,
            state_class=state_class,
            unit_of_measurement=unit,
        )

    entities = [
        _entity("overall_health", "sensor", "Overall health", "overall"),
        _entity(
            "active_incident",
            "binary_sensor",
            "Active incident",
            "active_incident",
            device_class="problem",
        ),
        _entity("incident_state", "sensor", "Incident state", "incident_state"),
        _entity(
            "unavailable_devices",
            "sensor",
            "Unavailable devices",
            "counts/unavailable_devices",
            state_class="measurement",
        ),
        _entity(
            "recently_unstable_devices",
            "sensor",
            "Recently unstable devices",
            "counts/recently_unstable_devices",
            state_class="measurement",
        ),
        _entity(
            "router_risks",
            "sensor",
            "Router risks",
            "counts/router_risks",
            state_class="measurement",
        ),
        _entity(
            "stale_devices",
            "sensor",
            "Stale devices",
            "counts/stale_devices",
            state_class="measurement",
        ),
        _entity(
            "weak_link_devices",
            "sensor",
            "Weak link devices",
            "counts/weak_link_devices",
            state_class="measurement",
        ),
        _entity(
            "low_battery_devices",
            "sensor",
            "Low battery devices",
            "counts/low_battery_devices",
            state_class="measurement",
        ),
        _entity(
            "unknown_devices",
            "sensor",
            "Unknown devices",
            "counts/unknown_devices",
            state_class="measurement",
        ),
        _entity(
            "network_count",
            "sensor",
            "Network count",
            "counts/network_count",
            state_class="measurement",
        ),
        _entity(
            "device_count",
            "sensor",
            "Device count",
            "counts/device_count",
            state_class="measurement",
        ),
        _entity(
            "mqtt_collector_connected",
            "binary_sensor",
            "MQTT collector connected",
            "collector",
            device_class="connectivity",
        ),
        _entity(
            "core_running",
            "binary_sensor",
            "Core running",
            "core_running",
            device_class="connectivity",
        ),
    ]
    return entities


def per_network_entities(
    *,
    state_topic_prefix: str,
    object_id_prefix: str,
    network_id: str,
    network_name: str,
) -> list[DiscoveryEntity]:
    safe_id = sanitize_object_id(network_id)
    prefix = f"network_{safe_id}"
    return [
        DiscoveryEntity(
            unique_id=f"zigbeelens_{prefix}_health",
            object_id=sanitize_object_id(f"{object_id_prefix}_{prefix}_health"),
            component="sensor",
            name=f"{network_name} health",
            state_topic=state_topic(state_topic_prefix, f"networks/{safe_id}/health"),
            value_template="{{ value_json.state }}",
            json_attributes_topic=state_topic(state_topic_prefix, f"networks/{safe_id}/health"),
        ),
        DiscoveryEntity(
            unique_id=f"zigbeelens_{prefix}_unavailable_devices",
            object_id=sanitize_object_id(f"{object_id_prefix}_{prefix}_unavailable_devices"),
            component="sensor",
            name=f"{network_name} unavailable devices",
            state_topic=state_topic(
                state_topic_prefix, f"networks/{safe_id}/unavailable_devices"
            ),
            value_template="{{ value_json.state }}",
            json_attributes_topic=state_topic(
                state_topic_prefix, f"networks/{safe_id}/unavailable_devices"
            ),
            state_class="measurement",
        ),
        DiscoveryEntity(
            unique_id=f"zigbeelens_{prefix}_router_risks",
            object_id=sanitize_object_id(f"{object_id_prefix}_{prefix}_router_risks"),
            component="sensor",
            name=f"{network_name} router risks",
            state_topic=state_topic(state_topic_prefix, f"networks/{safe_id}/router_risks"),
            value_template="{{ value_json.state }}",
            json_attributes_topic=state_topic(state_topic_prefix, f"networks/{safe_id}/router_risks"),
            state_class="measurement",
        ),
    ]


def discovery_config_payload(entity: DiscoveryEntity, availability: str, device: DiscoveryDevice) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": entity.name,
        "unique_id": entity.unique_id,
        "object_id": entity.object_id,
        "state_topic": entity.state_topic,
        "value_template": entity.value_template,
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
        payload["json_attributes_template"] = "{{ value_json | tojson }}"
    if entity.device_class:
        payload["device_class"] = entity.device_class
    if entity.state_class:
        payload["state_class"] = entity.state_class
    if entity.unit_of_measurement:
        payload["unit_of_measurement"] = entity.unit_of_measurement
    if device.configuration_url:
        payload["device"]["configuration_url"] = device.configuration_url
    return payload


def state_payload(state: PublishedEntityState) -> str:
    body = {"state": _serialize_state(state.state), **state.attributes}
    return json.dumps(body, separators=(",", ":"))


def _serialize_state(value: str | int | float | bool) -> str | int | float:
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    return value


def build_states_from_dashboard(
    dashboard: DashboardPayload,
    *,
    core_version: str,
    collector_connected: bool,
) -> dict[str, PublishedEntityState]:
    hs = dashboard.health_snapshot
    finding = dashboard.current_finding.summary
    overall = PublishedEntityState(
        state=_severity_state(dashboard.overall_severity),
        attributes={
            "current_finding": finding,
            "active_incident_count": dashboard.active_incident_count,
            "networks_monitored": hs.network_count,
            "total_devices": hs.device_count,
            "unavailable_devices": hs.unavailable_count,
            "router_risks": len(dashboard.router_risks),
            "stale_devices": len(dashboard.stale_devices),
            "weak_link_devices": len(dashboard.weak_links),
            "low_battery_devices": len(dashboard.low_batteries),
            "core_version": core_version,
        },
    )
    active = PublishedEntityState(
        state=dashboard.active_incident_count > 0,
        attributes={
            "active_incident_count": dashboard.active_incident_count,
            "highest_severity": dashboard.overall_severity.value,
            "top_incident_summary": finding,
            "current_finding": finding,
        },
    )
    incident_state = PublishedEntityState(
        state=(
            "incident"
            if dashboard.active_incident_count > 0
            else "watch"
            if dashboard.watching_incident_count > 0
            else "none"
        ),
        attributes={
            "open": dashboard.active_incident_count,
            "watching": dashboard.watching_incident_count,
            "recently_resolved": 0,
            "highest_severity": dashboard.overall_severity.value,
        },
    )
    counts = {
        "unavailable_devices": hs.unavailable_count,
        "recently_unstable_devices": len(dashboard.recently_unstable),
        "router_risks": len(dashboard.router_risks),
        "stale_devices": len(dashboard.stale_devices),
        "weak_link_devices": len(dashboard.weak_links),
        "low_battery_devices": len(dashboard.low_batteries),
        "unknown_devices": _unknown_count(dashboard),
        "network_count": hs.network_count,
        "device_count": hs.device_count,
    }
    states: dict[str, PublishedEntityState] = {
        "overall": overall,
        "active_incident": active,
        "incident_state": incident_state,
        "core_running": PublishedEntityState(state=True),
        "collector": PublishedEntityState(
            state=collector_connected,
            attributes={
                "last_message_at": None,
                "subscribed_topics_count": None,
                "last_error": None,
            },
        ),
    }
    for key, value in counts.items():
        states[f"counts/{key}"] = PublishedEntityState(
            state=value,
            attributes={
                "total_devices": hs.device_count,
                "networks_monitored": hs.network_count,
            },
        )
    return states


def build_network_states(dashboard: DashboardPayload) -> dict[str, PublishedEntityState]:
    states: dict[str, PublishedEntityState] = {}
    for network in dashboard.networks:
        safe_id = sanitize_object_id(network.id)
        router_risks = len([r for r in dashboard.router_risks if r.network_id == network.id])
        states[f"networks/{safe_id}/health"] = PublishedEntityState(
            state=_severity_state(network.incident_state),
            attributes={
                "network_id": network.id,
                "display_name": network.name,
                "base_topic": network.base_topic,
                "bridge_state": network.bridge_state.value,
                "active_incident_count": network.active_incident_count,
                "device_count": network.device_count,
                "unavailable_devices": network.unavailable_count,
                "router_risks": router_risks,
                "stale_devices": network.stale_count,
                "weak_link_devices": network.weak_link_count,
                "low_battery_devices": network.low_battery_count,
                "last_bridge_seen": None,
            },
        )
        states[f"networks/{safe_id}/unavailable_devices"] = PublishedEntityState(
            state=network.unavailable_count,
            attributes={"network_id": network.id, "device_count": network.device_count},
        )
        states[f"networks/{safe_id}/router_risks"] = PublishedEntityState(
            state=router_risks,
            attributes={"network_id": network.id},
        )
    return states


def all_discovery_entities(
    *,
    topic_prefix: str,
    state_topic_prefix: str,
    object_id_prefix: str,
    availability: str,
    device: DiscoveryDevice,
    dashboard: DashboardPayload,
) -> list[DiscoveryEntity]:
    entities = entity_catalog(
        topic_prefix=topic_prefix,
        state_topic_prefix=state_topic_prefix,
        object_id_prefix=object_id_prefix,
        availability=availability,
        device=device,
    )
    for network in dashboard.networks:
        entities.extend(
            per_network_entities(
                state_topic_prefix=state_topic_prefix,
                object_id_prefix=object_id_prefix,
                network_id=network.id,
                network_name=network.name,
            )
        )
    return entities


def discovery_topic_for_entity(topic_prefix: str, entity: DiscoveryEntity) -> str:
    return discovery_config_topic(topic_prefix, entity.component, entity.object_id)
