"""Build live dashboard payloads from collected MQTT state and health diagnostics."""

from __future__ import annotations

from datetime import datetime, timezone

from zigbeelens.config.models import AppConfig
from zigbeelens.diagnostics.incidents.service import IncidentDiagnosticService
from zigbeelens.diagnostics.models import BridgeHealthState, HealthFlag, NetworkHealthState
from zigbeelens.diagnostics.service import HealthDiagnosticService, _map_severity
from zigbeelens.schemas import (
    BridgeState,
    Confidence,
    CoordinatorSummary,
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
from zigbeelens.services.empty_state import empty_finding
from zigbeelens.storage.repository import NetworkRow, Repository


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _network_severity(state: NetworkHealthState, bridge_offline: bool) -> Severity:
    if bridge_offline:
        return Severity.critical
    mapping = {
        NetworkHealthState.incident: Severity.incident,
        NetworkHealthState.watch: Severity.watch,
        NetworkHealthState.ok: Severity.healthy,
        NetworkHealthState.unknown: Severity.watch,
    }
    return mapping.get(state, Severity.watch)


def live_finding(
    repo: Repository,
    config: AppConfig,
    health: HealthDiagnosticService,
    incidents: IncidentDiagnosticService | None = None,
    *,
    devices: list | None = None,
    networks: list | None = None,
    incident_context=None,
) -> DiagnosticConclusion:
    if incidents:
        incident_finding = incidents.current_finding(health, context=incident_context)
        if incident_finding:
            return incident_finding

    device_rows = devices if devices is not None else repo.list_devices()
    network_rows = networks if networks is not None else repo.list_networks()
    device_health = health.all_device_health()

    unavailable = sum(
        1 for h in device_health.values() if HealthFlag.unavailable in h.flags
    )
    unstable = sum(
        1 for h in device_health.values() if HealthFlag.recently_unstable in h.flags
    )
    weak = sum(1 for h in device_health.values() if HealthFlag.weak_link in h.flags)
    stale = sum(1 for h in device_health.values() if HealthFlag.stale_reporting in h.flags)
    low_bat = sum(1 for h in device_health.values() if HealthFlag.low_battery in h.flags)
    router_risk = sum(1 for h in device_health.values() if HealthFlag.router_risk in h.flags)
    offline_bridges = sum(
        1
        for n in network_rows
        if (health.get_bridge_health(n.id) or None)
        and health.get_bridge_health(n.id).state == BridgeHealthState.offline
    )

    signal_count = unavailable + unstable + weak + stale + low_bat + router_risk

    if signal_count == 0 and offline_bridges == 0:
        summary = (
            f"ZigbeeLens is monitoring {len(network_rows)} network(s) with {len(device_rows)} known device(s). "
            "No current health concerns were detected."
        )
        severity = Severity.healthy
        classification = "health_ok"
    elif offline_bridges:
        summary = (
            f"{offline_bridges} bridge(s) report offline. "
            "Device telemetry may be incomplete until bridges reconnect."
        )
        severity = Severity.critical
        classification = "bridge_offline"
    elif unavailable:
        summary = (
            f"Health signals were detected, but ZigbeeLens does not yet see a correlated "
            f"incident pattern ({unavailable} device(s) unavailable)."
        )
        severity = Severity.watch
        classification = "health_signals_uncorrelated"
    else:
        parts = []
        if unstable:
            parts.append(f"{unstable} recently unstable")
        if router_risk:
            parts.append(f"{router_risk} router risk")
        if weak:
            parts.append(f"{weak} weak link")
        if stale:
            parts.append(f"{stale} stale")
        if low_bat:
            parts.append(f"{low_bat} low battery")
        summary = (
            f"Health signals detected ({', '.join(parts)}). "
            "ZigbeeLens does not yet see a correlated incident pattern for these signals."
        )
        severity = Severity.watch
        classification = "health_signals"

    evidence = [
        EvidenceItem(
            id="ev-live-0",
            kind="health",
            summary=f"{len(device_rows)} devices classified from MQTT telemetry",
        )
    ]
    if signal_count:
        evidence.append(
            EvidenceItem(
                id="ev-live-1",
                kind="health",
                summary=f"{signal_count} device(s) with active health flags",
            )
        )

    limitations = [
        LimitationItem(
            id="lim-live-1",
            summary="Availability may be unknown when Zigbee2MQTT availability reporting is disabled",
        ),
    ]

    return DiagnosticConclusion(
        classification=classification,
        severity=severity,
        scope=IncidentScope.network if len(network_rows) == 1 else IncidentScope.multi_network,
        confidence=Confidence.medium if device_rows else Confidence.low,
        summary=summary,
        evidence=evidence,
        limitations=limitations,
    )


def build_network_summary(
    repo: Repository,
    row: NetworkRow,
    health: HealthDiagnosticService,
    incidents: IncidentDiagnosticService | None = None,
    *,
    devices: list | None = None,
    active_incident_count: int | None = None,
    incident_context=None,
) -> NetworkSummary:
    device_rows = devices if devices is not None else repo.list_devices(row.id)
    net_health = health.get_network_health(row.id)
    bridge_health = health.get_bridge_health(row.id)

    bridge = BridgeState(row.bridge_state) if row.bridge_state in {s.value for s in BridgeState} else BridgeState.unknown
    snapshot = repo.get_latest_bridge_snapshot(row.id)
    coordinator = None
    if snapshot and snapshot.get("coordinator_ieee"):
        coordinator = CoordinatorSummary(
            ieee_address=str(snapshot["coordinator_ieee"]),
            channel=snapshot.get("channel"),
            pan_id=snapshot.get("pan_id"),
            extended_pan_id=snapshot.get("extended_pan_id"),
        )

    counts = net_health or None
    unavailable = counts.unavailable_count if counts else sum(1 for d in device_rows if d.availability == "offline")
    unstable = counts.recently_unstable_count if counts else 0
    weak = counts.weak_link_count if counts else 0
    low_bat = counts.low_battery_count if counts else 0
    stale = counts.stale_count if counts else 0
    interview_issues = sum(
        1 for d in device_rows if d.interview_state in {"failed", "in_progress"}
    )

    bridge_offline = bridge_health is not None and bridge_health.state == BridgeHealthState.offline
    incident_state = (
        _network_severity(net_health.state, bridge_offline)
        if net_health
        else (Severity.critical if bridge == BridgeState.offline else Severity.healthy)
    )

    health_payload = DeviceHealth(
        primary=DeviceHealthPrimary.unknown,
        severity=incident_state,
        confidence=Confidence(net_health.confidence.value) if net_health else Confidence.low,
        evidence=net_health.evidence[:3] if net_health else [f"{len(device_rows)} devices tracked from MQTT"],
        limitations=net_health.limitations if net_health else [],
    )

    routers = sum(1 for d in device_rows if d.device_type == "Router")
    ends = sum(1 for d in device_rows if d.device_type == "EndDevice")

    if active_incident_count is not None:
        active_incidents = active_incident_count
    elif incidents:
        active_incidents = incidents.network_active_count(row.id, context=incident_context)
    else:
        active_incidents = 0

    return NetworkSummary(
        id=row.id,
        name=row.name,
        base_topic=row.base_topic,
        bridge_state=bridge,
        coordinator=coordinator,
        device_count=len(device_rows),
        router_count=routers,
        end_device_count=ends,
        unavailable_count=unavailable,
        recently_unstable_count=unstable,
        weak_link_count=weak,
        low_battery_count=low_bat,
        stale_count=stale,
        interview_issue_count=interview_issues,
        incident_state=incident_state,
        active_incident_count=active_incidents,
        health=health_payload,
    )


def build_health_snapshot(
    repo: Repository,
    health: HealthDiagnosticService,
    incidents: IncidentDiagnosticService | None = None,
    *,
    networks: list | None = None,
    devices: list | None = None,
    network_summaries: list | None = None,
    incident_context=None,
) -> HealthSnapshot:
    network_rows = networks if networks is not None else repo.list_networks()
    device_rows = devices if devices is not None else repo.list_devices()
    device_health = health.all_device_health()
    if devices is not None:
        scoped_keys = {(row.network_id, row.ieee_address) for row in device_rows}
        device_health = {
            key: result for key, result in device_health.items() if key in scoped_keys
        }

    unavailable = sum(
        1 for h in device_health.values() if HealthFlag.unavailable in h.flags
    )

    overall = Severity.healthy
    for n in network_rows:
        net = health.get_network_health(n.id)
        if net:
            sev = _map_severity(net.severity)
            if sev == Severity.incident:
                overall = Severity.incident
                break
            if sev == Severity.watch and overall == Severity.healthy:
                overall = Severity.watch
        bridge = health.get_bridge_health(n.id)
        if bridge and bridge.state == BridgeHealthState.offline:
            overall = Severity.critical
            break

    worst_primary = DeviceHealthPrimary.healthy
    for h in device_health.values():
        if h.primary == HealthFlag.unavailable:
            worst_primary = DeviceHealthPrimary.unavailable
            break
        if h.primary != HealthFlag.healthy and h.primary != HealthFlag.unknown:
            worst_primary = DeviceHealthPrimary(h.primary.value)

    open_count, _watching = (
        incidents.count_by_status(context=incident_context) if incidents else (0, 0)
    )

    if network_summaries is not None:
        summary_by_id = {item.id: item for item in network_summaries}
        network_payload = [
            {
                "network_id": n.id,
                "severity": summary_by_id[n.id].incident_state.value
                if n.id in summary_by_id
                else Severity.healthy.value,
                "unavailable_count": (
                    health.get_network_health(n.id).unavailable_count
                    if health.get_network_health(n.id)
                    else (
                        summary_by_id[n.id].unavailable_count
                        if n.id in summary_by_id
                        else repo.count_unavailable_for_network(n.id)
                    )
                ),
                "unknown_count": (
                    health.get_network_health(n.id).unknown_count
                    if health.get_network_health(n.id)
                    else 0
                ),
            }
            for n in network_rows
        ]
    else:
        network_payload = [
            {
                "network_id": n.id,
                "severity": build_network_summary(
                    repo, n, health, incidents, incident_context=incident_context
                ).incident_state.value,
                "unavailable_count": (
                    health.get_network_health(n.id).unavailable_count
                    if health.get_network_health(n.id)
                    else repo.count_unavailable_for_network(n.id)
                ),
                "unknown_count": (
                    health.get_network_health(n.id).unknown_count
                    if health.get_network_health(n.id)
                    else 0
                ),
            }
            for n in network_rows
        ]

    return HealthSnapshot(
        timestamp=_now_iso(),
        overall_severity=overall,
        overall_health=worst_primary,
        network_count=len(network_rows),
        device_count=len(device_rows),
        unavailable_count=unavailable,
        incident_count=open_count,
        networks=network_payload,
    )


def empty_live_finding() -> DiagnosticConclusion:
    return empty_finding()
