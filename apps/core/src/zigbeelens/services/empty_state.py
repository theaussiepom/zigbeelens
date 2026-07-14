"""Empty / unknown diagnostic payloads when no MQTT data exists yet."""

from __future__ import annotations

from datetime import datetime, timezone

from zigbeelens.config.models import AppConfig
from zigbeelens.schemas import (
    BridgeState,
    Confidence,
    DashboardPayload,
    DeviceHealth,
    DeviceHealthPrimary,
    DiagnosticConclusion,
    EvidenceItem,
    HealthSnapshot,
    IncidentScope,
    LimitationItem,
    NetworkSummary,
    Severity,
)
from zigbeelens.storage.repository import NetworkRow


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def empty_finding() -> DiagnosticConclusion:
    return DiagnosticConclusion(
        classification="no_data_yet",
        severity=Severity.watch,
        scope=IncidentScope.unknown,
        confidence=Confidence.low,
        summary="No Zigbee2MQTT data has been collected yet.",
        evidence=[
            EvidenceItem(
                id="ev-empty-0",
                kind="system",
                summary="MQTT collector has not started (Phase 2)",
            )
        ],
        counter_evidence=[],
        limitations=[
            LimitationItem(
                id="lim-empty-0",
                summary="No retained MQTT messages or device inventory received yet",
                detail="Configured networks are visible, but telemetry history is empty.",
            ),
            LimitationItem(
                id="lim-empty-1",
                summary="Device health cannot be assessed until data arrives",
            ),
        ],
    )


def network_summary_from_row(row: NetworkRow) -> NetworkSummary:
    unknown_health = DeviceHealth(
        primary=DeviceHealthPrimary.unknown,
        severity=Severity.watch,
        confidence=Confidence.low,
        evidence=[],
        limitations=["No device telemetry received for this network yet"],
    )
    return NetworkSummary(
        id=row.id,
        name=row.name,
        base_topic=row.base_topic,
        bridge_state=BridgeState(row.bridge_state)
            if row.bridge_state in {s.value for s in BridgeState}
            else BridgeState.unknown,
        device_count=0,
        router_count=0,
        end_device_count=0,
        unavailable_count=0,
        recently_unstable_count=0,
        weak_link_count=0,
        low_battery_count=0,
        stale_count=0,
        interview_issue_count=0,
        incident_state=Severity.watch,
        active_incident_count=0,
        recent_bridge_warnings=0,
        recent_bridge_errors=0,
        health=unknown_health,
    )


def build_empty_dashboard(config: AppConfig, networks: list[NetworkRow]) -> DashboardPayload:
    net_summaries = [network_summary_from_row(n) for n in networks]
    if not net_summaries and config.networks:
        net_summaries = [
            NetworkSummary(
                id=n.id,
                name=n.name,
                base_topic=n.base_topic,
                bridge_state=BridgeState.unknown,
                device_count=0,
                router_count=0,
                end_device_count=0,
                unavailable_count=0,
                recently_unstable_count=0,
                weak_link_count=0,
                low_battery_count=0,
                stale_count=0,
                interview_issue_count=0,
                incident_state=Severity.watch,
                active_incident_count=0,
                health=DeviceHealth(
                    primary=DeviceHealthPrimary.unknown,
                    severity=Severity.watch,
                    confidence=Confidence.low,
                    evidence=[],
                    limitations=["Awaiting MQTT data"],
                ),
            )
            for n in config.networks
        ]

    return DashboardPayload(
        generated_at=_now_iso(),
        scenario=None,
        overall_severity=Severity.watch,
        current_finding=empty_finding(),
        active_incident_count=0,
        watching_incident_count=0,
        networks=net_summaries,
        top_affected_devices=[],
        router_risks=[],
        recently_unstable=[],
        weak_links=[],
        low_batteries=[],
        stale_devices=[],
        recent_timeline=[],
        health_snapshot=HealthSnapshot(
            timestamp=_now_iso(),
            overall_severity=Severity.watch,
            overall_health=DeviceHealthPrimary.unknown,
            network_count=len(net_summaries),
            device_count=0,
            unavailable_count=0,
            incident_count=0,
            networks=[
                {
                    "network_id": n.id,
                    "severity": "watch",
                    "unavailable_count": 0,
                }
                for n in net_summaries
            ],
        ),
        shared_availability_events=[],
        model_patterns=[],
        investigation_priorities=[],
        data_coverage_warnings=[],
    )
