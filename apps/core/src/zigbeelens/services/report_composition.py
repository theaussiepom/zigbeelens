"""Request-local report composition context (Track 3F).

One ReportRequest → one ReportScopePlan → one ReportCompositionContext.
Decision projections reuse a single Device Story batch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping

from zigbeelens import __version__
from zigbeelens.config.models import AppConfig, ReportingConfig
from zigbeelens.decisions.device_story import DeviceStory, device_stories_for_devices
from zigbeelens.schemas import (
    Confidence,
    DeviceDetail,
    DeviceDecisionBadge,
    DeviceSummary,
    DiagnosticConclusion,
    HealthSnapshot,
    Incident,
    IncidentScope,
    IncidentStatus,
    NetworkSummary,
    ReportDetail,
    ReportRequest,
    ReportScope,
    RouterRisk,
    Severity,
    TimelineEvent,
)
from zigbeelens.services.dashboard_coverage_warnings import compose_dashboard_coverage_warnings
from zigbeelens.services.dashboard_investigation_priorities import (
    compose_dashboard_investigation_priorities,
)
from zigbeelens.services.device_decision_badge import device_decision_badge_from_story
from zigbeelens.services.empty_state import empty_finding
from zigbeelens.services.live_dashboard import (
    build_health_snapshot,
    build_network_summary,
    live_finding,
)
from zigbeelens.services.payload_builder import PayloadBuilder
from zigbeelens.services.report_device_story import (
    report_decision_summary_from_stories,
    report_device_story_from_story,
)
from zigbeelens.services.report_scope import ReportScopePlan, resolve_report_scope_plan
from zigbeelens.storage.repository import DeviceRow, NetworkRow, Repository


@dataclass(frozen=True)
class ReportCompositionContext:
    """Immutable request-local composition for one report."""

    plan: ReportScopePlan
    network_rows: tuple[NetworkRow, ...]
    networks: tuple[NetworkSummary, ...]
    device_rows: tuple[DeviceRow, ...]
    devices: tuple[DeviceSummary, ...]
    stories_by_key: Mapping[tuple[str, str], DeviceStory]
    decision_badges_by_key: Mapping[tuple[str, str], DeviceDecisionBadge]
    device_details: tuple[DeviceDetail, ...]
    incident_rows: tuple[dict[str, Any], ...]
    refs_by_incident_id: Mapping[str, tuple[dict[str, str], ...]]
    incidents: tuple[Incident, ...]
    timeline: tuple[TimelineEvent, ...]
    router_risks: tuple[RouterRisk, ...]
    investigation_priorities: tuple
    data_coverage_warnings: tuple
    health_snapshot: HealthSnapshot
    diagnostic_conclusions: tuple[DiagnosticConclusion, ...]
    overall_severity: Severity
    limitations: tuple
    raw_counts: Mapping[str, int]
    finding: str


def _reference_iso(now: datetime) -> str:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.isoformat()


def _scoped_config_summary(config: AppConfig, network_ids: tuple[str, ...]) -> dict[str, Any]:
    from zigbeelens.services.reports import build_config_summary

    summary = build_config_summary(config)
    allowed = set(network_ids)
    summary["networks"] = [
        entry for entry in summary.get("networks", []) if entry.get("id") in allowed
    ]
    return summary


def _topology_count(repo: Repository, config: AppConfig, network_ids: tuple[str, ...]) -> int:
    if not config.topology.enabled:
        return 0
    return repo.count_topology_snapshots_for_networks(network_ids)


def _report_limitations_scoped(
    config: AppConfig, repo: Repository, network_ids: tuple[str, ...]
) -> list:
    from zigbeelens.schemas import LimitationItem
    from zigbeelens.services.reports import STANDARD_LIMITATIONS

    items = list(STANDARD_LIMITATIONS)
    if config.topology.enabled and _topology_count(repo, config, network_ids) > 0:
        items = [i for i in items if i.id != "lim-topology"]
        items.append(
            LimitationItem(
                id="lim-topology-age",
                summary=(
                    "Topology is a point-in-time snapshot and may not reflect current routing."
                ),
            )
        )
    ha = repo.get_ha_enrichment_status()
    if not ha.get("enabled"):
        items.append(
            LimitationItem(
                id="lim-ha-enrichment",
                summary="No Home Assistant area enrichment is available.",
            )
        )
    return items


def _empty_health_snapshot(now: datetime, network_count: int = 0) -> HealthSnapshot:
    from zigbeelens.schemas import DeviceHealthPrimary

    return HealthSnapshot(
        timestamp=_reference_iso(now),
        overall_severity=Severity.watch,
        overall_health=DeviceHealthPrimary.unknown,
        network_count=network_count,
        device_count=0,
        unavailable_count=0,
        incident_count=0,
        networks=[],
    )


_ACTIVE_LIFECYCLES = frozenset({"open", "watching"})


def _build_scope_active_incident_context(
    *,
    plan: ReportScopePlan,
    historical_rows: list[dict[str, Any]],
    refs_by_incident_id: Mapping[str, tuple[dict[str, str], ...]],
    networks_by_incident_id: Mapping[str, tuple[str, ...]],
):
    """Build scope-local active context (open/watching only) for current findings."""
    from zigbeelens.diagnostics.incidents.service import ActiveIncidentReadContext

    active_rows = [
        row
        for row in historical_rows
        if row.get("lifecycle_state") in _ACTIVE_LIFECYCLES
    ]
    if plan.scope == ReportScope.device and plan.target_network_id and plan.target_device_ieee:
        target = (plan.target_network_id, plan.target_device_ieee)
        active_rows = [
            row
            for row in active_rows
            if any(
                (ref["network_id"], ref["ieee_address"]) == target
                for ref in refs_by_incident_id.get(row["id"], ())
            )
        ]
    elif plan.scope == ReportScope.incident:
        selected = plan.target_incident_id
        active_rows = [row for row in active_rows if row["id"] == selected]

    active_ids = [row["id"] for row in active_rows]
    active_refs = MappingProxyType(
        {incident_id: refs_by_incident_id.get(incident_id, ()) for incident_id in active_ids}
    )
    affected: set[tuple[str, str]] = set()
    incident_ids_by_device: dict[tuple[str, str], list[str]] = {}
    for incident_id in active_ids:
        for ref in active_refs.get(incident_id, ()):
            key = (ref["network_id"], ref["ieee_address"])
            affected.add(key)
            incident_ids_by_device.setdefault(key, []).append(incident_id)

    active_count_by_network: dict[str, int] = {nid: 0 for nid in plan.network_ids}
    for row in active_rows:
        for network_id in networks_by_incident_id.get(row["id"], ()):
            if network_id in active_count_by_network:
                active_count_by_network[network_id] += 1
            else:
                active_count_by_network[network_id] = (
                    active_count_by_network.get(network_id, 0) + 1
                )

    return ActiveIncidentReadContext(
        incidents=tuple(active_rows),
        incidents_by_id=MappingProxyType({row["id"]: row for row in active_rows}),
        refs_by_incident_id=active_refs,
        affected_keys=frozenset(affected),
        incident_ids_by_device_key=MappingProxyType(
            {key: tuple(ids) for key, ids in incident_ids_by_device.items()}
        ),
        active_count_by_network_id=MappingProxyType(active_count_by_network),
    )


def _scoped_device_health_map(health, device_rows: list[DeviceRow]) -> dict:
    """Collect per-device health for represented devices only (no estate-wide map)."""
    mapping = {}
    for row in device_rows:
        result = health.get_device_health(row.network_id, row.ieee_address)
        if result is not None:
            mapping[(row.network_id, row.ieee_address)] = result
    return mapping


def _scoped_collector(
    collector: dict[str, Any], network_ids: tuple[str, ...]
) -> dict[str, Any]:
    """Keep global collector facts; restrict per-network identities to the plan.

    Supports both established shapes:
    - mapping keyed by network id
    - production list of ``{"network_id": ..., ...}`` entries
    """
    scoped = dict(collector)
    networks = collector.get("networks")
    allowed = set(network_ids)
    if isinstance(networks, dict):
        scoped["networks"] = {
            key: value for key, value in networks.items() if key in allowed
        }
    elif isinstance(networks, list):
        retained: list[Any] = []
        for entry in networks:
            if not isinstance(entry, dict):
                continue
            network_id = entry.get("network_id")
            if isinstance(network_id, str) and network_id in allowed:
                retained.append(entry)
        scoped["networks"] = retained
    return scoped


def _devices_by_key_for_incident_refs(
    repo: Repository,
    *,
    device_rows: list[DeviceRow],
    refs_by_incident_id: Mapping[str, tuple[dict[str, str], ...]],
    plan: ReportScopePlan,
) -> Mapping[tuple[str, str], DeviceRow]:
    """Reuse loaded device rows; fetch only genuinely missing in-scope refs."""
    devices_by_key: dict[tuple[str, str], DeviceRow] = {
        (row.network_id, row.ieee_address): row for row in device_rows
    }
    needed: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for refs in refs_by_incident_id.values():
        for ref in refs:
            key = (ref["network_id"], ref["ieee_address"])
            if plan.scope == ReportScope.network:
                if ref["network_id"] not in plan.network_ids:
                    continue
            elif plan.scope == ReportScope.device:
                if key != (plan.target_network_id, plan.target_device_ieee):
                    continue
            if key in seen:
                continue
            seen.add(key)
            if key not in devices_by_key:
                needed.append(key)
    if needed:
        devices_by_key.update(repo.get_devices_by_keys(needed))
    return MappingProxyType(devices_by_key)


def _projection_refs_for_scope(
    refs_by_incident_id: Mapping[str, tuple[dict[str, str], ...]],
    plan: ReportScopePlan,
) -> Mapping[str, tuple[dict[str, str], ...]]:
    """Limit Network/Device affected-device projection to report representation."""
    if plan.scope == ReportScope.incident or plan.scope == ReportScope.full:
        return refs_by_incident_id
    filtered: dict[str, tuple[dict[str, str], ...]] = {}
    for incident_id, refs in refs_by_incident_id.items():
        if plan.scope == ReportScope.network:
            kept = tuple(ref for ref in refs if ref["network_id"] in plan.network_ids)
        else:
            target = (plan.target_network_id, plan.target_device_ieee)
            kept = tuple(
                ref
                for ref in refs
                if (ref["network_id"], ref["ieee_address"]) == target
            )
        filtered[incident_id] = kept
    return MappingProxyType(filtered)


def compose_live_report_scope(
    builder: PayloadBuilder,
    request: ReportRequest,
    *,
    reference_now: datetime,
    include_timeline: bool,
    reporting: ReportingConfig,
) -> ReportCompositionContext:
    """Compose one scoped report context from live repository state."""
    repo = builder.repo
    config = builder.config
    plan = resolve_report_scope_plan(
        request,
        repo=repo,
        reference_now=reference_now,
        include_timeline=include_timeline,
    )
    if plan.is_empty:
        return ReportCompositionContext(
            plan=plan,
            network_rows=(),
            networks=(),
            device_rows=(),
            devices=(),
            stories_by_key=MappingProxyType({}),
            decision_badges_by_key=MappingProxyType({}),
            device_details=(),
            incident_rows=(),
            refs_by_incident_id=MappingProxyType({}),
            incidents=(),
            timeline=(),
            router_risks=(),
            investigation_priorities=(),
            data_coverage_warnings=(),
            health_snapshot=_empty_health_snapshot(reference_now),
            diagnostic_conclusions=(empty_finding(),),
            overall_severity=Severity.watch,
            limitations=tuple(_report_limitations_scoped(config, repo, ())),
            raw_counts=MappingProxyType(
                {
                    "events_included": 0,
                    "devices_included": 0,
                    "incidents_included": 0,
                    "topology_snapshots": 0,
                }
            ),
            finding="Evidence report for the selected ZigbeeLens scope.",
        )

    # --- raw rows ---------------------------------------------------------
    if plan.scope == ReportScope.full:
        network_rows = list(repo.list_networks())
        device_rows = list(repo.list_devices())
        incident_rows = list(repo.incidents.list_incidents())
    elif plan.scope == ReportScope.network:
        assert plan.target_network_id is not None
        network_rows = repo.get_networks_by_ids(plan.network_ids)
        device_rows = list(repo.list_devices(plan.target_network_id))
        incident_rows = repo.list_incident_rows_for_network_history(plan.target_network_id)
    elif plan.scope == ReportScope.incident:
        network_rows = repo.get_networks_by_ids(plan.network_ids)
        device_rows = list(repo.get_devices_by_keys(plan.device_keys).values())
        row = repo.get_incident(plan.target_incident_id or "")
        incident_rows = [row] if row else []
    else:  # device
        network_rows = repo.get_networks_by_ids(plan.network_ids)
        device_rows = list(repo.get_devices_by_keys(plan.device_keys).values())
        if plan.target_network_id and plan.target_device_ieee:
            incident_rows = repo.list_incident_rows_for_device_history(
                plan.target_network_id, plan.target_device_ieee
            )
        else:
            incident_rows = []

    networks_by_id = {row.id: row for row in network_rows}
    health = builder._ensure_device_health_for_rows(device_rows) or builder._fallback_health()
    scoped_health = _scoped_device_health_map(health, device_rows)
    complete_network_scope = plan.scope in {ReportScope.full, ReportScope.network}

    # Historical incident rows (all statuses) for ReportDetail.incidents.
    incident_ids = [row["id"] for row in incident_rows]
    refs_map = (
        repo.incidents.list_incident_devices_for_incidents(incident_ids)
        if incident_ids
        else {}
    )
    historical_refs_by_incident_id = MappingProxyType(
        {incident_id: tuple(refs_map.get(incident_id, [])) for incident_id in incident_ids}
    )
    networks_map = (
        repo.incidents.list_incident_networks_for_incidents(incident_ids)
        if incident_ids
        else {}
    )
    networks_by_incident_id = MappingProxyType(
        {
            incident_id: tuple(networks_map.get(incident_id, []))
            for incident_id in incident_ids
        }
    )
    # Projection refs: Incident/Full keep full membership; Network/Device trim.
    projection_refs_by_incident_id = _projection_refs_for_scope(
        historical_refs_by_incident_id, plan
    )

    # Scope-local active context — never global active_incident_read_context().
    active_incident_context = _build_scope_active_incident_context(
        plan=plan,
        historical_rows=incident_rows,
        refs_by_incident_id=historical_refs_by_incident_id,
        networks_by_incident_id=networks_by_incident_id,
    )

    # --- one Device Story batch ------------------------------------------
    from zigbeelens.services.network_evidence import REPORT_EVIDENCE_REQUIREMENTS
    from zigbeelens.services.network_evidence_composition import (
        compose_network_evidence_contexts,
    )

    devices_by_network_id: dict[str, list[DeviceRow]] = {}
    for row in device_rows:
        devices_by_network_id.setdefault(row.network_id, []).append(row)
    evidence_contexts = compose_network_evidence_contexts(
        repo,
        list(plan.network_ids),
        reference_now=reference_now,
        requirements_by_network={
            network_id: REPORT_EVIDENCE_REQUIREMENTS for network_id in plan.network_ids
        },
        network_rows_by_id=networks_by_id,
        devices_by_network=devices_by_network_id,
    )
    evidence_map = dict(evidence_contexts)

    stories = device_stories_for_devices(
        repo,
        device_rows,
        now=reference_now,
        network_evidence_contexts=evidence_map,
    )
    badges = {
        key: device_decision_badge_from_story(story) for key, story in stories.items()
    }

    composition = builder._device_composition_context(
        device_rows,
        include_related_incidents=plan.scope == ReportScope.device,
        incident_context=active_incident_context,
        networks_by_id=networks_by_id,
    )
    devices = builder._devices_from_rows(
        device_rows,
        summary_context=composition.summary,
        decision_badges=badges,
    )

    device_details: list[DeviceDetail] = []
    if plan.require_device_details:
        for row in device_rows:
            key = (row.network_id, row.ieee_address)
            summary = next(
                (
                    d
                    for d in devices
                    if d.network_id == row.network_id and d.ieee_address == row.ieee_address
                ),
                None,
            )
            device_details.append(
                builder._device_detail_from_row(
                    row,
                    decision_badge=badges.get(key),
                    include_events=include_timeline,
                    summary=summary,
                    summary_context=composition.summary,
                )
            )

    # --- incidents from same badge batch ---------------------------------
    if include_timeline and incident_ids:
        events_map = repo.list_events_for_incidents(incident_ids)
        events_by_incident_id = MappingProxyType(
            {
                incident_id: tuple(events_map.get(incident_id, []))
                for incident_id in incident_ids
            }
        )
    else:
        events_by_incident_id = MappingProxyType(
            {incident_id: () for incident_id in incident_ids}
        )

    devices_by_key = _devices_by_key_for_incident_refs(
        repo,
        device_rows=device_rows,
        refs_by_incident_id=projection_refs_by_incident_id,
        plan=plan,
    )

    incident_composition = builder._incident_composition_context(
        incident_rows,
        now=reference_now,
        include_events=include_timeline,
        refs_by_incident_id=projection_refs_by_incident_id,
        devices_by_key=devices_by_key,
        events_by_incident_id=events_by_incident_id,
        decision_badges_by_key=badges,
        networks_by_incident_id=networks_by_incident_id,
    )
    incidents = [
        inc
        for row in incident_rows
        if (inc := builder._incident_from_row(row, composition=incident_composition))
        is not None
    ]

    # --- timeline --------------------------------------------------------
    timeline: list[TimelineEvent] = []
    max_events = reporting.max_recent_events
    if include_timeline:
        from zigbeelens.services.payload_builder import _timeline_from_event_rows

        if plan.scope == ReportScope.full:
            event_rows = repo.list_report_timeline_events(limit=max_events)
            timeline = _timeline_from_event_rows(event_rows)
        elif plan.scope == ReportScope.network and plan.target_network_id:
            event_rows = repo.list_report_timeline_events(
                network_id=plan.target_network_id, limit=max_events
            )
            timeline = _timeline_from_event_rows(event_rows)
        elif plan.scope == ReportScope.incident and incidents:
            timeline = list(incidents[0].timeline)[:max_events]
        elif plan.scope == ReportScope.device and plan.target_network_id and plan.target_device_ieee:
            if device_details:
                timeline = list(device_details[0].recent_events)[:max_events]
            else:
                event_rows = repo.list_report_timeline_events(
                    network_id=plan.target_network_id,
                    ieee_address=plan.target_device_ieee,
                    limit=max_events,
                )
                timeline = _timeline_from_event_rows(event_rows)

    # --- network summaries / routers / finding ---------------------------
    from zigbeelens.services.report_active_severity import (
        active_severity_by_network_id,
        pick_active_incident_severity,
    )

    devices_by_network: dict[str, list[DeviceRow]] = {}
    for row in device_rows:
        devices_by_network.setdefault(row.network_id, []).append(row)

    scope_active_severity = pick_active_incident_severity(
        active_incident_context.incidents
    )
    severity_by_network = active_severity_by_network_id(
        active_incident_context.incidents,
        networks_by_incident_id,
        plan.network_ids,
    )

    networks = [
        build_network_summary(
            repo,
            row,
            health,
            builder._incident_service,
            devices=devices_by_network.get(row.id, []),
            active_incident_count=active_incident_context.active_count_by_network_id.get(
                row.id, 0
            ),
            incident_context=active_incident_context,
            complete_network_scope=complete_network_scope,
            scoped_device_health_by_key=scoped_health,
            active_incident_severity=severity_by_network.get(row.id),
        )
        for row in network_rows
    ]
    routers = builder.routers(
        devices=device_rows,
        incident_context=active_incident_context,
        health=health,
    )

    finding_conclusion = live_finding(
        repo,
        config,
        health,
        builder._incident_service,
        devices=device_rows,
        networks=network_rows,
        incident_context=active_incident_context,
        scoped_device_health_by_key=scoped_health,
    )
    health_snapshot = build_health_snapshot(
        repo,
        health,
        builder._incident_service,
        networks=network_rows,
        devices=device_rows,
        network_summaries=networks,
        incident_context=active_incident_context,
        scoped_device_health_by_key=scoped_health,
        complete_network_scope=complete_network_scope,
        active_incident_severity=scope_active_severity,
    )
    health_snapshot = health_snapshot.model_copy(
        update={
            "timestamp": _reference_iso(reference_now),
            "incident_count": sum(
                1 for row in active_incident_context.incidents
                if row.get("lifecycle_state") == "open"
            ),
        }
    )

    from zigbeelens.services.reports import (
        _filter_coverage_warnings,
        _filter_investigation_priorities,
    )

    investigation = compose_dashboard_investigation_priorities(
        repo,
        network_rows,
        now=reference_now,
        network_evidence_contexts=evidence_map,
    )
    coverage = compose_dashboard_coverage_warnings(
        repo,
        network_rows,
        config,
        route_hint_relevant_network_ids={
            item.network_id
            for item in investigation
            if item.card_type == "router_neighbourhood_review"
        },
        now=reference_now,
        network_evidence_contexts=evidence_map,
    )

    if plan.scope == ReportScope.incident and incidents:
        priority_affected_keys = {
            (ref.network_id, ref.ieee_address)
            for ref in incidents[0].affected_devices
        }
    elif plan.scope == ReportScope.device and plan.target_network_id and plan.target_device_ieee:
        priority_affected_keys = {(plan.target_network_id, plan.target_device_ieee)}
    else:
        priority_affected_keys = set(active_incident_context.affected_keys)
    investigation = _filter_investigation_priorities(
        investigation,
        scope=plan.scope,
        network_id=plan.target_network_id,
        device_ieee=plan.target_device_ieee,
        affected_keys=priority_affected_keys,
    )
    coverage = _filter_coverage_warnings(
        coverage,
        scope=plan.scope,
        network_ids=set(plan.network_ids),
    )

    conclusions: list[DiagnosticConclusion]
    if plan.scope == ReportScope.incident and incidents:
        conclusions = [incidents[0].conclusion]
    elif plan.scope == ReportScope.device and device_details:
        conclusions = [device_details[0].diagnostic]
    else:
        conclusions = [finding_conclusion]

    topology = _topology_count(repo, config, plan.network_ids)
    return ReportCompositionContext(
        plan=plan,
        network_rows=tuple(network_rows),
        networks=tuple(networks),
        device_rows=tuple(device_rows),
        devices=tuple(devices),
        stories_by_key=MappingProxyType(stories),
        decision_badges_by_key=MappingProxyType(badges),
        device_details=tuple(device_details),
        incident_rows=tuple(incident_rows),
        refs_by_incident_id=historical_refs_by_incident_id,
        incidents=tuple(incidents),
        timeline=tuple(timeline),
        router_risks=tuple(routers),
        investigation_priorities=tuple(investigation),
        data_coverage_warnings=tuple(coverage),
        health_snapshot=health_snapshot,
        diagnostic_conclusions=tuple(conclusions),
        overall_severity=finding_conclusion.severity,
        limitations=tuple(_report_limitations_scoped(config, repo, plan.network_ids)),
        raw_counts=MappingProxyType(
            {
                "events_included": len(timeline),
                "devices_included": len(devices),
                "incidents_included": len(incidents),
                "topology_snapshots": topology,
            }
        ),
        finding="Evidence report for the selected ZigbeeLens scope.",
    )


def compose_mock_report_scope(
    mock,
    request: ReportRequest,
    *,
    reference_now: datetime,
    include_timeline: bool,
    reporting: ReportingConfig,
) -> ReportCompositionContext:
    """Compose one scoped report context from scenario fixtures."""
    data = mock.data
    known_networks = tuple(n.id for n in data.networks)
    scenario_device_keys = tuple((d.network_id, d.ieee_address) for d in data.devices)
    scenario_incident_networks = {
        inc.id: tuple(inc.network_ids) for inc in data.incidents
    }
    scenario_incident_devices = {
        inc.id: tuple(
            (ref.network_id, ref.ieee_address) for ref in inc.affected_devices
        )
        for inc in data.incidents
    }
    plan = resolve_report_scope_plan(
        request,
        repo=None,
        reference_now=reference_now,
        include_timeline=include_timeline,
        known_network_ids=known_networks,
        scenario_device_keys=scenario_device_keys,
        scenario_incident_networks=scenario_incident_networks,
        scenario_incident_devices=scenario_incident_devices,
    )
    if plan.is_empty:
        return ReportCompositionContext(
            plan=plan,
            network_rows=(),
            networks=(),
            device_rows=(),
            devices=(),
            stories_by_key=MappingProxyType({}),
            decision_badges_by_key=MappingProxyType({}),
            device_details=(),
            incident_rows=(),
            refs_by_incident_id=MappingProxyType({}),
            incidents=(),
            timeline=(),
            router_risks=(),
            investigation_priorities=(),
            data_coverage_warnings=(),
            health_snapshot=_empty_health_snapshot(reference_now),
            diagnostic_conclusions=(empty_finding(),),
            overall_severity=Severity.watch,
            limitations=(),
            raw_counts=MappingProxyType(
                {
                    "events_included": 0,
                    "devices_included": 0,
                    "incidents_included": 0,
                    "topology_snapshots": 0,
                }
            ),
            finding="Evidence report for the selected ZigbeeLens scope.",
        )

    from zigbeelens.services.reports import (
        STANDARD_LIMITATIONS,
        _filter_coverage_warnings,
        _filter_investigation_priorities,
    )

    networks = [n for n in data.networks if n.id in plan.network_ids]
    if plan.scope == ReportScope.full:
        devices = list(data.devices)
        incidents = list(data.incidents)
    elif plan.scope == ReportScope.network:
        devices = [d for d in data.devices if d.network_id in plan.network_ids]
        incidents = [
            i for i in data.incidents if any(nid in i.network_ids for nid in plan.network_ids)
        ]
    elif plan.scope == ReportScope.incident:
        incidents = [i for i in data.incidents if i.id in plan.incident_ids]
        device_key_set = set(plan.device_keys)
        devices = [
            d for d in data.devices if (d.network_id, d.ieee_address) in device_key_set
        ]
    else:
        device_key_set = set(plan.device_keys)
        devices = [
            d for d in data.devices if (d.network_id, d.ieee_address) in device_key_set
        ]
        incidents = [
            i
            for i in data.incidents
            if any(
                (ref.network_id, ref.ieee_address) in device_key_set
                for ref in i.affected_devices
            )
        ]

    stories: dict[tuple[str, str], DeviceStory] = {}
    for device in devices:
        key = (device.network_id, device.ieee_address)
        story = data.device_stories.get(key)
        if story is not None:
            stories[key] = story
    badges = {
        key: device_decision_badge_from_story(story) for key, story in stories.items()
    }

    active_incidents = [
        inc for inc in incidents if inc.status in {IncidentStatus.open, IncidentStatus.watching}
    ]
    if plan.scope == ReportScope.device and plan.target_network_id and plan.target_device_ieee:
        target = (plan.target_network_id, plan.target_device_ieee)
        active_incidents = [
            inc
            for inc in active_incidents
            if any((ref.network_id, ref.ieee_address) == target for ref in inc.affected_devices)
        ]
    elif plan.scope == ReportScope.incident:
        active_incidents = [
            inc for inc in active_incidents if inc.id == plan.target_incident_id
        ]
    active_affected = {
        (ref.network_id, ref.ieee_address)
        for inc in active_incidents
        for ref in inc.affected_devices
    }
    devices = [
        d.model_copy(
            update={
                "decision": badges.get((d.network_id, d.ieee_address)),
                "incident_affected": (d.network_id, d.ieee_address) in active_affected,
            }
        )
        for d in devices
    ]

    from zigbeelens.mock.device_stories import apply_incident_device_story_badges
    from zigbeelens.mock.fixtures import device_detail_from_summary
    from zigbeelens.schemas import DeviceHealth, DeviceHealthPrimary, DeviceType
    from zigbeelens.services.report_active_severity import (
        active_severity_by_network_id,
        mock_networks_by_incident_id,
        pick_active_incident_severity,
    )

    # Project fixture-story badges onto incident refs without mutating shared fixtures.
    incidents = list(apply_incident_device_story_badges(incidents, stories))
    if plan.scope in {ReportScope.network, ReportScope.device}:
        trimmed: list[Incident] = []
        for inc in incidents:
            if plan.scope == ReportScope.network:
                kept = [
                    ref for ref in inc.affected_devices if ref.network_id in plan.network_ids
                ]
            else:
                target = (plan.target_network_id, plan.target_device_ieee)
                kept = [
                    ref
                    for ref in inc.affected_devices
                    if (ref.network_id, ref.ieee_address) == target
                ]
            trimmed.append(
                inc.model_copy(
                    update={
                        "affected_devices": kept,
                        "affected_device_count": len(kept),
                    }
                )
            )
        incidents = trimmed

    networks_by_incident = mock_networks_by_incident_id(active_incidents)
    scope_active_severity = pick_active_incident_severity(active_incidents)
    severity_by_network = active_severity_by_network_id(
        active_incidents, networks_by_incident, plan.network_ids
    )

    def _mock_scoped_network_summary(net: NetworkSummary) -> NetworkSummary:
        scoped = [d for d in devices if d.network_id == net.id]
        active_count = sum(1 for inc in active_incidents if net.id in inc.network_ids)
        unavailable = sum(
            1 for d in scoped if d.health.primary == DeviceHealthPrimary.unavailable
        )
        unstable = sum(
            1 for d in scoped if d.health.primary == DeviceHealthPrimary.recently_unstable
        )
        weak = sum(1 for d in scoped if d.health.primary == DeviceHealthPrimary.weak_link)
        low_bat = sum(
            1 for d in scoped if d.health.primary == DeviceHealthPrimary.low_battery
        )
        stale = sum(
            1 for d in scoped if d.health.primary == DeviceHealthPrimary.stale_reporting
        )
        interview_issues = sum(
            1 for d in scoped if str(d.interview_state.value) in {"failed", "in_progress"}
        )
        if net.bridge_state.value == "offline":
            incident_state = Severity.critical
        elif severity_by_network.get(net.id) is not None:
            incident_state = severity_by_network[net.id]
        elif unavailable or unstable or weak or low_bat or stale:
            incident_state = Severity.watch
        else:
            incident_state = Severity.healthy
        health_payload = DeviceHealth(
            primary=DeviceHealthPrimary.unknown,
            severity=incident_state,
            confidence=net.health.confidence,
            evidence=[f"{len(scoped)} devices in report scope"],
            limitations=[],
        )
        return net.model_copy(
            update={
                "device_count": len(scoped),
                "router_count": sum(1 for d in scoped if d.device_type == DeviceType.Router),
                "end_device_count": sum(
                    1 for d in scoped if d.device_type == DeviceType.EndDevice
                ),
                "unavailable_count": unavailable,
                "recently_unstable_count": unstable,
                "weak_link_count": weak,
                "low_battery_count": low_bat,
                "stale_count": stale,
                "interview_issue_count": interview_issues,
                "active_incident_count": active_count,
                "incident_state": incident_state,
                "health": health_payload,
            }
        )

    if plan.scope in {ReportScope.device, ReportScope.incident}:
        networks = [_mock_scoped_network_summary(net) for net in networks]
    elif plan.scope == ReportScope.network:
        # Keep factual bridge/coordinator context; align active count and state.
        networks = [_mock_scoped_network_summary(net) for net in networks]

    device_details: list[DeviceDetail] = []
    if plan.require_device_details:
        for device in devices:
            key = (device.network_id, device.ieee_address)
            detail = device_detail_from_summary(device, data)
            detail = detail.model_copy(
                update={
                    "decision": badges.get(key),
                    "incident_affected": device.incident_affected,
                    "recent_events": list(detail.recent_events) if include_timeline else [],
                }
            )
            device_details.append(detail)

    if not include_timeline:
        incidents = [inc.model_copy(update={"timeline": []}) for inc in incidents]

    max_events = reporting.max_recent_events
    timeline: list[TimelineEvent] = []
    if include_timeline:
        if plan.scope == ReportScope.full:
            timeline = list(mock.timeline())[:max_events]
        elif plan.scope == ReportScope.network and plan.target_network_id:
            timeline = list(mock.timeline(plan.target_network_id))[:max_events]
        elif plan.scope == ReportScope.incident and incidents:
            timeline = list(incidents[0].timeline)[:max_events]
        elif plan.scope == ReportScope.device and device_details:
            timeline = list(device_details[0].recent_events)[:max_events]

    all_routers = list(mock.routers())
    if plan.scope == ReportScope.full:
        routers = [r for r in all_routers if r.network_id in plan.network_ids]
    elif plan.scope == ReportScope.network:
        routers = [r for r in all_routers if r.network_id in plan.network_ids]
    elif plan.scope == ReportScope.device and plan.target_network_id and plan.target_device_ieee:
        target = (plan.target_network_id, plan.target_device_ieee)
        routers = [
            r for r in all_routers if (r.network_id, r.ieee_address) == target
        ]
    elif plan.scope == ReportScope.incident and incidents:
        affected_keys = {
            (ref.network_id, ref.ieee_address) for ref in incidents[0].affected_devices
        }
        routers = [
            r for r in all_routers if (r.network_id, r.ieee_address) in affected_keys
        ]
    else:
        routers = []

    unavailable = sum(
        1 for d in devices if d.health.primary == DeviceHealthPrimary.unavailable
    )
    network_payload = [
        {
            "network_id": n.id,
            "severity": n.incident_state.value,
            "unavailable_count": sum(
                1
                for d in devices
                if d.network_id == n.id
                and d.health.primary == DeviceHealthPrimary.unavailable
            ),
            "unknown_count": sum(
                1
                for d in devices
                if d.network_id == n.id
                and d.health.primary == DeviceHealthPrimary.unknown
            ),
        }
        for n in networks
    ]
    if any(n.bridge_state.value == "offline" for n in networks):
        scoped_severity = Severity.critical
    elif scope_active_severity is not None:
        scoped_severity = scope_active_severity
    elif unavailable:
        scoped_severity = Severity.watch
    elif any(d.health.severity not in {Severity.healthy} for d in devices):
        scoped_severity = Severity.watch
    else:
        scoped_severity = Severity.healthy
    worst_primary = DeviceHealthPrimary.healthy
    for d in devices:
        if d.health.primary == DeviceHealthPrimary.unavailable:
            worst_primary = DeviceHealthPrimary.unavailable
            break
        if d.health.primary == DeviceHealthPrimary.unknown:
            if worst_primary == DeviceHealthPrimary.healthy:
                worst_primary = DeviceHealthPrimary.unknown
            continue
        if d.health.primary != DeviceHealthPrimary.healthy:
            worst_primary = d.health.primary
    if not devices:
        worst_primary = DeviceHealthPrimary.unknown

    health_snapshot = HealthSnapshot(
        timestamp=_reference_iso(reference_now),
        overall_severity=scoped_severity,
        overall_health=worst_primary,
        network_count=len(networks),
        device_count=len(devices),
        unavailable_count=unavailable,
        incident_count=sum(1 for i in active_incidents if i.status == IncidentStatus.open),
        networks=network_payload,
    )

    if plan.scope == ReportScope.incident and incidents:
        priority_affected = {
            (ref.network_id, ref.ieee_address) for ref in incidents[0].affected_devices
        }
    elif plan.scope == ReportScope.device and plan.target_network_id and plan.target_device_ieee:
        priority_affected = {(plan.target_network_id, plan.target_device_ieee)}
    else:
        priority_affected = active_affected
    investigation = _filter_investigation_priorities(
        list(data.dashboard.investigation_priorities or []),
        scope=plan.scope,
        network_id=plan.target_network_id,
        device_ieee=plan.target_device_ieee,
        affected_keys=priority_affected,
    )
    coverage = _filter_coverage_warnings(
        list(data.dashboard.data_coverage_warnings or []),
        scope=plan.scope,
        network_ids=set(plan.network_ids),
    )

    if plan.scope == ReportScope.incident and incidents:
        conclusions = [incidents[0].conclusion]
    elif plan.scope == ReportScope.device and device_details:
        conclusions = [device_details[0].diagnostic]
    elif plan.scope == ReportScope.full:
        conclusions = [data.dashboard.current_finding]
    elif active_incidents:
        top = sorted(
            active_incidents,
            key=lambda inc: (
                0 if inc.status == IncidentStatus.open else 1,
                {
                    Severity.critical: 0,
                    Severity.incident: 1,
                    Severity.watch: 2,
                    Severity.healthy: 3,
                }.get(inc.severity, 9),
            ),
        )[0]
        conclusions = [top.conclusion]
    else:
        # Narrow Network with no active incident: derive from represented network facts.
        net = networks[0] if networks else None
        if net is not None and net.incident_state == Severity.healthy:
            conclusions = [
                DiagnosticConclusion(
                    classification="health_ok",
                    severity=Severity.healthy,
                    scope=IncidentScope.network,
                    confidence=Confidence.medium if devices else Confidence.low,
                    summary=(
                        f"ZigbeeLens is monitoring 1 network(s) with {len(devices)} known "
                        "device(s). No current health concerns were detected."
                    ),
                    evidence=[],
                    limitations=[],
                )
            ]
        elif net is not None:
            conclusions = [
                DiagnosticConclusion(
                    classification="health_signals",
                    severity=net.incident_state,
                    scope=IncidentScope.network,
                    confidence=Confidence.medium if devices else Confidence.low,
                    summary=(
                        f"Health signals detected on {net.name}. "
                        "ZigbeeLens does not yet see a correlated incident pattern."
                    ),
                    evidence=[],
                    limitations=[],
                )
            ]
        else:
            conclusions = [empty_finding()]

    return ReportCompositionContext(
        plan=plan,
        network_rows=(),
        networks=tuple(networks),
        device_rows=(),
        devices=tuple(devices),
        stories_by_key=MappingProxyType(stories),
        decision_badges_by_key=MappingProxyType(badges),
        device_details=tuple(device_details),
        incident_rows=(),
        refs_by_incident_id=MappingProxyType({}),
        incidents=tuple(incidents),
        timeline=tuple(timeline),
        router_risks=tuple(routers),
        investigation_priorities=tuple(investigation),
        data_coverage_warnings=tuple(coverage),
        health_snapshot=health_snapshot,
        diagnostic_conclusions=tuple(conclusions),
        overall_severity=scoped_severity,
        limitations=tuple(STANDARD_LIMITATIONS),
        raw_counts=MappingProxyType(
            {
                "events_included": len(timeline),
                "devices_included": len(devices),
                "incidents_included": len(incidents),
                "topology_snapshots": 0,
            }
        ),
        finding="Evidence report for the selected ZigbeeLens scope.",
    )


def project_report_detail(
    ctx: ReportCompositionContext,
    *,
    config: AppConfig,
    collector: dict[str, Any],
    request: ReportRequest,
) -> ReportDetail:
    """Project ReportCompositionContext into ReportDetail (no further data loads)."""
    from zigbeelens.services.reports import _summary_block, default_redaction_status

    report_stories = []
    for device in ctx.devices:
        story = ctx.stories_by_key.get((device.network_id, device.ieee_address))
        if story is None:
            continue
        report_stories.append(report_device_story_from_story(device=device, story=story))
    if not ctx.plan.include_timeline:
        report_stories = [
            story.model_copy(update={"timeline": []}) for story in report_stories
        ]

    story_list = [
        ctx.stories_by_key[key]
        for rs in report_stories
        if (key := (rs.network_id, rs.ieee_address)) in ctx.stories_by_key
    ]
    decision_summary = report_decision_summary_from_stories(
        story_list if story_list else report_stories
    )
    summary = _summary_block(
        overall_state=ctx.overall_severity,
        current_finding=ctx.finding,
        networks=list(ctx.networks),
        devices=list(ctx.devices),
        routers=list(ctx.router_risks),
        incidents=list(ctx.incidents),
    )
    return ReportDetail(
        id="report-preview",
        report_version=2,
        generated_at=_reference_iso(ctx.plan.reference_now),
        version=__version__,
        scope=request.scope.value,
        format=request.format.value,
        redaction=default_redaction_status(),
        summary=summary,
        decision_summary=decision_summary,
        investigation_priorities=list(ctx.investigation_priorities),
        device_stories=report_stories,
        data_coverage_warnings=list(ctx.data_coverage_warnings),
        config_summary=_scoped_config_summary(config, ctx.plan.network_ids),
        collector=_scoped_collector(collector, ctx.plan.network_ids),
        networks=list(ctx.networks),
        devices=list(ctx.devices),
        device_details=list(ctx.device_details),
        router_risks=list(ctx.router_risks),
        incidents=list(ctx.incidents),
        timeline=list(ctx.timeline),
        health_snapshot=ctx.health_snapshot,
        diagnostic_conclusions=list(ctx.diagnostic_conclusions),
        limitations=list(ctx.limitations),
        raw_counts=dict(ctx.raw_counts),
        markdown_summary="",
    )
