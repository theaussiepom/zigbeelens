"""Empty / unknown diagnostic payloads when no MQTT data exists yet."""

from __future__ import annotations

from datetime import datetime, timezone

from zigbeelens.config.models import AppConfig
from zigbeelens.decisions.types import DecisionPriority, DecisionStatus
from zigbeelens.schemas import (
    BridgeState,
    Confidence,
    DashboardPayload,
    DecisionCountSummary,
    DeviceDecisionBadge,
    DiagnosticConclusion,
    EvidenceItem,
    IncidentScope,
    LimitationItem,
    NetworkSummary,
    Severity,
)
from zigbeelens.storage.repository import NetworkRow


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def empty_finding() -> DiagnosticConclusion:
    """Internal diagnostic conclusion for empty estates (not a public Dashboard field)."""
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
                summary="Device decisions cannot be assessed until data arrives",
            ),
        ],
    )


def _empty_network_decision() -> tuple[DeviceDecisionBadge, DecisionCountSummary]:
    summary = DecisionCountSummary(
        subject_count=0,
        overall_status=DecisionStatus.data_unavailable,
        highest_priority=DecisionPriority.none,
        status_counts={},
        priority_counts={},
        coverage_warning_count=0,
    )
    decision = DeviceDecisionBadge(
        status=DecisionStatus.data_unavailable,
        priority=DecisionPriority.none,
        headline_code="network_data_unavailable",
        coverage_label_codes=[],
    )
    return decision, summary


def network_summary_from_row(row: NetworkRow) -> NetworkSummary:
    decision, decision_summary = _empty_network_decision()
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
        active_incident_severity=None,
        active_incident_count=0,
        recent_bridge_warnings=0,
        recent_bridge_errors=0,
        decision=decision,
        decision_summary=decision_summary,
    )


def build_empty_dashboard(config: AppConfig, networks: list[NetworkRow]) -> DashboardPayload:
    net_summaries = [network_summary_from_row(n) for n in networks]
    if not net_summaries and config.networks:
        decision, decision_summary = _empty_network_decision()
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
                active_incident_severity=None,
                active_incident_count=0,
                decision=decision,
                decision_summary=decision_summary,
            )
            for n in config.networks
        ]

    empty_summary = DecisionCountSummary(
        subject_count=0,
        overall_status=DecisionStatus.data_unavailable,
        highest_priority=DecisionPriority.none,
        status_counts={},
        priority_counts={},
        coverage_warning_count=0,
    )
    return DashboardPayload(
        generated_at=_now_iso(),
        scenario=None,
        active_incident_count=0,
        watching_incident_count=0,
        network_count=len(net_summaries),
        device_count=0,
        unavailable_device_count=0,
        networks=net_summaries,
        router_risks=[],
        recent_timeline=[],
        decision_summary=empty_summary,
        shared_availability_events=[],
        model_patterns=[],
        investigation_priorities=[],
        data_coverage_warnings=[],
    )
