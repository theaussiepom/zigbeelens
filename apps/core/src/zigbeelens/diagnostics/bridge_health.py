"""Bridge health classification."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from zigbeelens.config.models import DiagnosticsConfig
from zigbeelens.diagnostics.models import (
    BridgeHealthResult,
    BridgeHealthState,
    HealthConfidence,
    HealthSeverity,
)


def classify_bridge(
    *,
    bridge_state: str,
    last_updated_at: str | None,
    config: DiagnosticsConfig,
    last_mqtt_activity_at: str | None = None,
    now: datetime | None = None,
) -> BridgeHealthResult:
    now = now or datetime.now(timezone.utc)

    if bridge_state == "offline":
        return BridgeHealthResult(
            state=BridgeHealthState.offline,
            severity=HealthSeverity.incident,
            confidence=HealthConfidence.high,
            summary="The Zigbee2MQTT bridge is offline.",
            evidence=["Latest bridge state is offline"],
            limitations=["Device telemetry may be stale while the bridge is offline"],
            updated_at=now.isoformat(),
        )

    if bridge_state == "online":
        stale = _is_stale(last_updated_at, config.bridge_stale_after_minutes, now)
        activity_recent = last_mqtt_activity_at is not None and not _is_stale(
            last_mqtt_activity_at, config.bridge_stale_after_minutes, now
        )
        if stale and activity_recent:
            return BridgeHealthResult(
                state=BridgeHealthState.online,
                severity=HealthSeverity.ok,
                confidence=HealthConfidence.high,
                summary="The Zigbee2MQTT bridge is online.",
                evidence=[
                    "Latest bridge state is online",
                    "Recent device MQTT activity observed on this network",
                ],
                limitations=[
                    "Zigbee2MQTT publishes bridge/state only on changes, not periodically",
                ],
                updated_at=now.isoformat(),
            )
        if stale:
            return BridgeHealthResult(
                state=BridgeHealthState.stale,
                severity=HealthSeverity.watch,
                confidence=HealthConfidence.medium,
                summary="Bridge state has not updated recently.",
                evidence=[f"Bridge was last updated more than {config.bridge_stale_after_minutes} minutes ago"],
                limitations=["The bridge may still be online without publishing state"],
                updated_at=now.isoformat(),
            )
        return BridgeHealthResult(
            state=BridgeHealthState.online,
            severity=HealthSeverity.ok,
            confidence=HealthConfidence.high,
            summary="The Zigbee2MQTT bridge is online.",
            evidence=["Latest bridge state is online"],
            updated_at=now.isoformat(),
        )

    return BridgeHealthResult(
        state=BridgeHealthState.unknown,
        severity=HealthSeverity.unknown,
        confidence=HealthConfidence.low,
        summary="No bridge state has been observed yet.",
        evidence=["No bridge state has been observed"],
        limitations=["MQTT collection may not have started or retained bridge state may be missing"],
        updated_at=now.isoformat(),
    )


def _is_stale(last_updated_at: str | None, minutes: int, now: datetime) -> bool:
    if not last_updated_at:
        return False
    try:
        ts = datetime.fromisoformat(last_updated_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    return now - ts > timedelta(minutes=minutes)
