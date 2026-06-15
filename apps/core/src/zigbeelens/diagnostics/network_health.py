"""Network health aggregation."""

from __future__ import annotations

from datetime import datetime, timezone

from zigbeelens.diagnostics.bridge_health import classify_bridge
from zigbeelens.diagnostics.models import (
    BridgeHealthResult,
    HealthConfidence,
    HealthFlag,
    HealthResult,
    HealthSeverity,
    NetworkHealthResult,
    NetworkHealthState,
)
from zigbeelens.config.models import DiagnosticsConfig


def classify_network(
    *,
    network_id: str,
    bridge_state: str,
    network_updated_at: str | None,
    last_mqtt_activity_at: str | None = None,
    device_health: list[HealthResult],
    router_devices: list[tuple[str, HealthResult]],
    config: DiagnosticsConfig,
) -> tuple[NetworkHealthResult, BridgeHealthResult]:
    now = datetime.now(timezone.utc).isoformat()
    bridge = classify_bridge(
        bridge_state=bridge_state,
        last_updated_at=network_updated_at,
        last_mqtt_activity_at=last_mqtt_activity_at,
        config=config,
    )

    unavailable = sum(1 for h in device_health if HealthFlag.unavailable in h.flags)
    unstable = sum(1 for h in device_health if HealthFlag.recently_unstable in h.flags)
    router_risk = sum(1 for h in device_health if HealthFlag.router_risk in h.flags)
    stale = sum(1 for h in device_health if HealthFlag.stale_reporting in h.flags)
    weak = sum(1 for h in device_health if HealthFlag.weak_link in h.flags)
    low_bat = sum(1 for h in device_health if HealthFlag.low_battery in h.flags)
    unknown = sum(1 for h in device_health if h.primary == HealthFlag.unknown)
    router_unavail = sum(
        1 for _, h in router_devices if HealthFlag.unavailable in h.flags
    )

    evidence = [f"{len(device_health)} devices known in inventory"]
    limitations: list[str] = []

    if bridge.state.value == "offline":
        state = NetworkHealthState.incident
        severity = HealthSeverity.incident
        summary = "Bridge is offline on this network."
        evidence.append("Zigbee2MQTT bridge state is offline")
    elif unavailable > 0 or router_unavail > 0:
        state = NetworkHealthState.incident
        severity = HealthSeverity.incident
        summary = f"{unavailable} device(s) unavailable on this network."
        evidence.append(f"{unavailable} unavailable device(s)")
    elif unstable or router_risk or weak or stale or low_bat:
        state = NetworkHealthState.watch
        severity = HealthSeverity.watch
        summary = "Health signals detected on this network."
        if unstable:
            evidence.append(f"{unstable} recently unstable device(s)")
        if router_risk:
            evidence.append(f"{router_risk} router risk candidate(s)")
    elif not device_health:
        state = NetworkHealthState.unknown
        severity = HealthSeverity.unknown
        summary = "No devices observed on this network yet."
        limitations.append("Waiting for bridge device inventory over MQTT")
    elif bridge.state.value == "unknown":
        state = NetworkHealthState.unknown
        severity = HealthSeverity.unknown
        summary = "Bridge state is unknown."
    else:
        state = NetworkHealthState.ok
        severity = HealthSeverity.ok
        summary = "No current health concerns detected on this network."

    return NetworkHealthResult(
        state=state,
        severity=severity,
        confidence=HealthConfidence.medium if device_health else HealthConfidence.low,
        summary=summary,
        evidence=evidence,
        limitations=limitations,
        unavailable_count=unavailable,
        recently_unstable_count=unstable,
        router_risk_count=router_risk,
        stale_count=stale,
        weak_link_count=weak,
        low_battery_count=low_bat,
        unknown_count=unknown,
        updated_at=now,
    ), bridge
