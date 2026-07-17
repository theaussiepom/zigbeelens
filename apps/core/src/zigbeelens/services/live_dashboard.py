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
    scoped_device_health_by_key: dict | None = None,
) -> DiagnosticConclusion:
    if incidents:
        incident_finding = incidents.current_finding(health, context=incident_context)
        if incident_finding:
            return incident_finding

    device_rows = devices if devices is not None else repo.list_devices()
    network_rows = networks if networks is not None else repo.list_networks()
    if scoped_device_health_by_key is not None:
        device_health = scoped_device_health_by_key
    else:
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
        if (bridge := health.get_bridge_health(n.id)) is not None
        and bridge.state == BridgeHealthState.offline
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


def _counts_from_scoped_device_health(
    device_rows: list,
    scoped_device_health_by_key: dict | None,
) -> tuple[int, int, int, int, int]:
    """Derive compatibility counts from represented devices only."""
    unavailable = 0
    unstable = 0
    weak = 0
    low_bat = 0
    stale = 0
    for row in device_rows:
        key = (row.network_id, row.ieee_address)
        result = (
            scoped_device_health_by_key.get(key)
            if scoped_device_health_by_key is not None
            else None
        )
        if result is None:
            if getattr(row, "availability", None) == "offline":
                unavailable += 1
            continue
        flags = result.flags or []
        if HealthFlag.unavailable in flags:
            unavailable += 1
        if HealthFlag.recently_unstable in flags:
            unstable += 1
        if HealthFlag.weak_link in flags:
            weak += 1
        if HealthFlag.low_battery in flags:
            low_bat += 1
        if HealthFlag.stale_reporting in flags:
            stale += 1
    return unavailable, unstable, weak, low_bat, stale


def build_network_summary(
    repo: Repository,
    row: NetworkRow,
    health: HealthDiagnosticService,
    incidents: IncidentDiagnosticService | None = None,
    *,
    devices: list | None = None,
    active_incident_count: int | None = None,
    incident_context=None,
    complete_network_scope: bool = True,
    scoped_device_health_by_key: dict | None = None,
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

    interview_issues = sum(
        1 for d in device_rows if d.interview_state in {"failed", "in_progress"}
    )
    if complete_network_scope and net_health is not None:
        unavailable = net_health.unavailable_count
        unstable = net_health.recently_unstable_count
        weak = net_health.weak_link_count
        low_bat = net_health.low_battery_count
        stale = net_health.stale_count
    else:
        unavailable, unstable, weak, low_bat, stale = _counts_from_scoped_device_health(
            device_rows, scoped_device_health_by_key
        )

    bridge_offline = bridge_health is not None and bridge_health.state == BridgeHealthState.offline
    if complete_network_scope and net_health is not None:
        incident_state = _network_severity(net_health.state, bridge_offline)
    elif bridge_offline or bridge == BridgeState.offline:
        incident_state = Severity.critical
    elif active_incident_count:
        incident_state = Severity.incident
    elif unavailable or unstable or weak or low_bat or stale:
        incident_state = Severity.watch
    else:
        incident_state = Severity.healthy

    health_payload = DeviceHealth(
        primary=DeviceHealthPrimary.unknown,
        severity=incident_state,
        confidence=(
            Confidence(net_health.confidence.value)
            if complete_network_scope and net_health
            else Confidence.low
        ),
        evidence=(
            net_health.evidence[:3]
            if complete_network_scope and net_health
            else [f"{len(device_rows)} devices in report scope"]
        ),
        limitations=net_health.limitations if complete_network_scope and net_health else [],
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
    scoped_device_health_by_key: dict | None = None,
    complete_network_scope: bool = True,
) -> HealthSnapshot:
    network_rows = networks if networks is not None else repo.list_networks()
    device_rows = devices if devices is not None else repo.list_devices()
    if scoped_device_health_by_key is not None:
        device_health = scoped_device_health_by_key
    else:
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
    if complete_network_scope:
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
    else:
        for n in network_rows:
            bridge = health.get_bridge_health(n.id)
            if bridge and bridge.state == BridgeHealthState.offline:
                overall = Severity.critical
                break
        if overall != Severity.critical and incident_context is not None:
            if any(
                row.get("lifecycle_state") == "open"
                for row in incident_context.incidents
            ):
                overall = Severity.incident
            elif incident_context.incidents and overall == Severity.healthy:
                overall = Severity.watch
        if overall == Severity.healthy and unavailable:
            overall = Severity.watch
        elif overall == Severity.healthy:
            for h in device_health.values():
                if h.primary not in {HealthFlag.healthy, HealthFlag.unknown}:
                    overall = Severity.watch
                    break

    worst_primary = DeviceHealthPrimary.healthy
    for h in device_health.values():
        if h.primary == HealthFlag.unavailable:
            worst_primary = DeviceHealthPrimary.unavailable
            break
        if h.primary != HealthFlag.healthy and h.primary != HealthFlag.unknown:
            worst_primary = DeviceHealthPrimary(h.primary.value)
    if not device_health and not complete_network_scope:
        worst_primary = DeviceHealthPrimary.unknown

    open_count, _watching = (
        incidents.count_by_status(context=incident_context) if incidents else (0, 0)
    )

    if network_summaries is not None:
        summary_by_id = {item.id: item for item in network_summaries}
        network_payload = []
        for n in network_rows:
            summary = summary_by_id.get(n.id)
            if summary is not None:
                unavailable_count = summary.unavailable_count
                severity = summary.incident_state.value
            elif complete_network_scope and (net := health.get_network_health(n.id)):
                unavailable_count = net.unavailable_count
                severity = Severity.healthy.value
            else:
                unavailable_count = 0
                severity = Severity.healthy.value
            unknown_count = 0
            if complete_network_scope:
                net = health.get_network_health(n.id)
                unknown_count = net.unknown_count if net else 0
            network_payload.append(
                {
                    "network_id": n.id,
                    "severity": severity,
                    "unavailable_count": unavailable_count,
                    "unknown_count": unknown_count,
                }
            )
    else:
        network_payload = [
            {
                "network_id": n.id,
                "severity": build_network_summary(
                    repo,
                    n,
                    health,
                    incidents,
                    incident_context=incident_context,
                    complete_network_scope=complete_network_scope,
                    scoped_device_health_by_key=scoped_device_health_by_key,
                ).incident_state.value,
                "unavailable_count": (
                    health.get_network_health(n.id).unavailable_count
                    if complete_network_scope and health.get_network_health(n.id)
                    else sum(
                        1
                        for d in device_rows
                        if d.network_id == n.id and d.availability == "offline"
                    )
                ),
                "unknown_count": (
                    health.get_network_health(n.id).unknown_count
                    if complete_network_scope and health.get_network_health(n.id)
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
