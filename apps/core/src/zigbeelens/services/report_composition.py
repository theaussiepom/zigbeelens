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
    DeviceDetail,
    DeviceDecisionBadge,
    DeviceSummary,
    DiagnosticConclusion,
    HealthSnapshot,
    Incident,
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

    # Active incident context restricted to selected incident rows where useful.
    incident_ids = [row["id"] for row in incident_rows]
    refs_map = (
        repo.incidents.list_incident_devices_for_incidents(incident_ids)
        if incident_ids
        else {}
    )
    refs_by_incident_id = MappingProxyType(
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

    # --- one Device Story batch ------------------------------------------
    stories = device_stories_for_devices(repo, device_rows, now=reference_now)
    badges = {
        key: device_decision_badge_from_story(story) for key, story in stories.items()
    }

    # Device summaries from the same badges / scoped networks.
    incident_affected = frozenset(
        (ref["network_id"], ref["ieee_address"])
        for refs in refs_by_incident_id.values()
        for ref in refs
    )
    # For full/network scopes, also mark currently active membership so related
    # presentation stays consistent with dashboard vocabulary when available.
    if builder._incident_service is not None and plan.scope in {
        ReportScope.full,
        ReportScope.network,
    }:
        active_ctx = builder._incident_service.active_incident_read_context()
        incident_affected = frozenset(active_ctx.affected_keys)

    from zigbeelens.diagnostics.incidents.service import ActiveIncidentReadContext

    scoped_incident_context = ActiveIncidentReadContext(
        incidents=tuple(incident_rows),
        incidents_by_id=MappingProxyType({row["id"]: row for row in incident_rows}),
        refs_by_incident_id=refs_by_incident_id,
        affected_keys=incident_affected,
        incident_ids_by_device_key=MappingProxyType({}),
        active_count_by_network_id=MappingProxyType(
            {
                nid: sum(
                    1
                    for row in incident_rows
                    if row.get("lifecycle_state") in {"open", "watching"}
                    and nid in networks_by_incident_id.get(row["id"], ())
                )
                for nid in plan.network_ids
            }
        ),
    )

    composition = builder._device_composition_context(
        device_rows,
        include_related_incidents=plan.scope == ReportScope.device,
        incident_context=scoped_incident_context,
        networks_by_id=networks_by_id,
    )
    # Inject story-derived badges; do not call device_decision_badges_for_devices.
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

    # Existing devices for incident refs (may include missing devices as absent).
    ref_keys: list[tuple[str, str]] = []
    seen_ref_keys: set[tuple[str, str]] = set()
    for refs in refs_by_incident_id.values():
        for ref in refs:
            key = (ref["network_id"], ref["ieee_address"])
            if key in seen_ref_keys:
                continue
            seen_ref_keys.add(key)
            ref_keys.append(key)
    devices_by_key = MappingProxyType(
        {**repo.get_devices_by_keys(ref_keys), **{(r.network_id, r.ieee_address): r for r in device_rows}}
    )

    incident_composition = builder._incident_composition_context(
        incident_rows,
        now=reference_now,
        include_events=include_timeline,
        refs_by_incident_id=refs_by_incident_id,
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
    devices_by_network: dict[str, list[DeviceRow]] = {}
    for row in device_rows:
        devices_by_network.setdefault(row.network_id, []).append(row)

    networks = [
        build_network_summary(
            repo,
            row,
            health,
            builder._incident_service,
            devices=devices_by_network.get(row.id, []),
            active_incident_count=scoped_incident_context.active_count_by_network_id.get(
                row.id, 0
            ),
            incident_context=scoped_incident_context,
        )
        for row in network_rows
    ]
    routers = builder.routers(
        devices=device_rows,
        incident_context=scoped_incident_context,
        health=health,
    )

    finding_conclusion = live_finding(
        repo,
        config,
        health,
        builder._incident_service,
        devices=device_rows,
        networks=network_rows,
        incident_context=scoped_incident_context,
    )
    health_snapshot = build_health_snapshot(
        repo,
        health,
        builder._incident_service,
        networks=network_rows,
        devices=device_rows,
        network_summaries=networks,
        incident_context=scoped_incident_context,
    )
    health_snapshot = health_snapshot.model_copy(
        update={
            "timestamp": _reference_iso(reference_now),
            "incident_count": sum(
                1 for i in incidents if i.status == IncidentStatus.open
            ),
        }
    )

    from zigbeelens.services.reports import (
        _filter_coverage_warnings,
        _filter_investigation_priorities,
    )

    investigation = compose_dashboard_investigation_priorities(repo, network_rows)
    coverage = compose_dashboard_coverage_warnings(
        repo,
        network_rows,
        config,
        route_hint_relevant_network_ids={
            item.network_id
            for item in investigation
            if item.card_type == "router_neighbourhood_review"
        },
    )

    affected_keys = {
        (ref.network_id, ref.ieee_address)
        for incident in incidents
        for ref in incident.affected_devices
    }
    investigation = _filter_investigation_priorities(
        investigation,
        scope=plan.scope,
        network_id=plan.target_network_id,
        device_ieee=plan.target_device_ieee,
        affected_keys=affected_keys,
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
        refs_by_incident_id=refs_by_incident_id,
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
    devices = [
        d.model_copy(update={"decision": badges.get((d.network_id, d.ieee_address))})
        for d in devices
    ]

    from zigbeelens.mock.fixtures import device_detail_from_summary

    device_details: list[DeviceDetail] = []
    if plan.require_device_details:
        for device in devices:
            key = (device.network_id, device.ieee_address)
            detail = device_detail_from_summary(device, data)
            detail = detail.model_copy(
                update={
                    "decision": badges.get(key),
                    "recent_events": list(detail.recent_events) if include_timeline else [],
                }
            )
            device_details.append(detail)

    if include_timeline:
        for idx, incident in enumerate(incidents):
            incidents[idx] = incident
    else:
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

    router_network_ids = set(plan.network_ids)
    routers = [r for r in mock.routers() if r.network_id in router_network_ids]

    dashboard = data.dashboard
    health_snapshot = dashboard.health_snapshot.model_copy(
        update={
            "timestamp": _reference_iso(reference_now),
            "network_count": len(networks),
            "device_count": len(devices),
            "incident_count": sum(1 for i in incidents if i.status == IncidentStatus.open),
            "networks": [
                entry
                for entry in (dashboard.health_snapshot.networks or [])
                if entry.get("network_id") in plan.network_ids
            ],
        }
    )

    investigation = _filter_investigation_priorities(
        list(dashboard.investigation_priorities or []),
        scope=plan.scope,
        network_id=plan.target_network_id,
        device_ieee=plan.target_device_ieee,
        affected_keys={
            (ref.network_id, ref.ieee_address)
            for incident in incidents
            for ref in incident.affected_devices
        },
    )
    coverage = _filter_coverage_warnings(
        list(dashboard.data_coverage_warnings or []),
        scope=plan.scope,
        network_ids=set(plan.network_ids),
    )

    if plan.scope == ReportScope.incident and incidents:
        conclusions = [incidents[0].conclusion]
    elif plan.scope == ReportScope.device and device_details:
        conclusions = [device_details[0].diagnostic]
    else:
        conclusions = [dashboard.current_finding]

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
        overall_severity=dashboard.overall_severity,
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
        collector=collector,
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
