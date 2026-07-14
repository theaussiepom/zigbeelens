"""Report generation: scoped assembly, redaction, and rendering.

Reports are evidence-backed diagnostic snapshots, not root-cause proof. They are
always redacted before they are stored or returned. The full structured report
is produced as a :class:`ReportDetail`; JSON, YAML, and Markdown are derived from
it on demand.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

import yaml

from zigbeelens import __version__
from zigbeelens.config.models import AppConfig, ReportingConfig
from zigbeelens.config.redaction import redact_mqtt_server
from zigbeelens.schemas import (
    DataCoverageWarningSummary,
    DeviceDetail,
    DeviceHealthPrimary,
    DeviceSummary,
    Incident,
    IncidentDeviceRef,
    IncidentStatus,
    InvestigationPrioritySummary,
    LensHealthSummary,
    LimitationItem,
    ReportDetail,
    ReportRedactionStatus,
    ReportRequest,
    ReportScope,
    ReportSummary,
    ReportSummaryBlock,
    Severity,
)
from zigbeelens.presentation.lens_buckets import BUCKET_LABELS, LensBucket
from zigbeelens.services.report_device_story import (
    report_decision_summary_from_stories,
    report_device_story_from_story,
)
from zigbeelens.services.report_redaction import Redactor, resolve_redaction
from zigbeelens.storage.repository import ReportRow, Repository, utc_now_iso

STANDARD_LIMITATIONS: list[LimitationItem] = [
    LimitationItem(
        id="lim-telemetry",
        summary="ZigbeeLens uses observed MQTT and Zigbee2MQTT telemetry.",
    ),
    LimitationItem(id="lim-root-cause", summary="ZigbeeLens does not prove root cause."),
    LimitationItem(id="lim-readonly", summary="ZigbeeLens does not mutate Zigbee state."),
    LimitationItem(
        id="lim-topology",
        summary=(
            "Topology-dependent conclusions require a topology snapshot, "
            "which may not be available."
        ),
    ),
]


class ReportDataSource(Protocol):
    """Subset of DataService used to assemble reports (mock or live)."""

    def dashboard(self, scenario: str | None = None): ...
    def networks(self, scenario: str | None = None): ...
    def devices(self, scenario: str | None = None, network_id: str | None = None): ...
    def report_device_context(
        self,
        scenario: str | None = None,
        *,
        network_id: str | None = None,
        device_keys: set[tuple[str, str]] | None = None,
        now=None,
    ): ...
    def device(self, network_id: str, ieee_address: str, scenario: str | None = None): ...
    def routers(self, scenario: str | None = None): ...
    def incidents(self, scenario: str | None = None): ...
    def incident(self, incident_id: str, scenario: str | None = None): ...
    def timeline(self, scenario: str | None = None, network_id: str | None = None): ...


def default_redaction_status() -> ReportRedactionStatus:
    return ReportRedactionStatus(applied=True, profile="standard", mqtt_credentials=True)


def topology_report_counts(repo: Repository, config: AppConfig) -> dict[str, int]:
    if not config.topology.enabled:
        return {"topology_snapshots": 0}
    total = 0
    for network in config.networks:
        total += len(repo.list_topology_snapshots(network.id))
    return {"topology_snapshots": total}


def _report_limitations(config: AppConfig, repo: Repository) -> list[LimitationItem]:
    items = list(STANDARD_LIMITATIONS)
    if config.topology.enabled and topology_report_counts(repo, config)["topology_snapshots"] > 0:
        items = [i for i in items if i.id != "lim-topology"]
        items.append(
            LimitationItem(
                id="lim-topology-age",
                summary="Topology is a point-in-time snapshot and may not reflect current routing.",
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


def build_config_summary(config: AppConfig) -> dict[str, Any]:
    return {
        "mode": "mock" if config.mode.mock else "live",
        "mqtt": {
            "server": redact_mqtt_server(config.mqtt.server, config.mqtt.username),
            "username": config.mqtt.username or None,
            "client_id": config.mqtt.client_id,
        },
        "networks": [
            {"id": n.id, "name": n.name, "base_topic": n.base_topic} for n in config.networks
        ],
        "storage": {
            "path": config.storage.path,
            "retention_days": config.storage.retention_days,
        },
        "diagnostics": config.diagnostics.model_dump(),
        "features": config.features.model_dump(),
        "reporting": config.reporting.model_dump(),
    }


def _count_primary(devices: list[DeviceSummary], primary: DeviceHealthPrimary) -> int:
    return sum(1 for d in devices if d.health.primary == primary)


def _lens_health_summary(
    devices: list[DeviceSummary],
    *,
    overall_state: Severity | None,
) -> LensHealthSummary:
    counts = {bucket.value: 0 for bucket in LensBucket}
    for device in devices:
        bucket = device.lens_bucket if device.lens_bucket in counts else LensBucket.unknown.value
        counts[bucket] += 1
    labels = {
        bucket: BUCKET_LABELS[LensBucket(bucket)]
        for bucket, count in counts.items()
        if count > 0
    }
    return LensHealthSummary(
        overall_state=overall_state.value if overall_state else None,
        bucket_counts=counts,
        bucket_labels=labels,
    )


def _collector_status_summary(collector: dict[str, Any], mode: str | None) -> dict[str, Any]:
    enabled = bool(collector.get("enabled"))
    connected = bool(collector.get("connected"))
    subscribed = int(collector.get("subscribed_topics_count") or 0)
    if not enabled:
        mqtt_state = "disabled"
        bridge_state = "not_observed"
    elif connected:
        mqtt_state = "connected"
        bridge_state = "observed" if subscribed > 0 else "not_observed"
    else:
        mqtt_state = "disconnected"
        bridge_state = "not_observed"
    return {
        **collector,
        "data_mode": mode,
        "mqtt_collector": mqtt_state,
        "zigbee2mqtt_bridge": bridge_state,
    }


def _domain_details(detail: ReportDetail) -> dict[str, Any]:
    return {
        "networks": detail.networks,
        "devices": detail.devices,
        "router_risks": detail.router_risks,
        "device_details": detail.device_details,
        "topology_snapshots": detail.raw_counts.get("topology_snapshots", 0),
    }


def _enrich_incident_entity(ref: IncidentDeviceRef) -> IncidentDeviceRef:
    return ref.model_copy(
        update={
            "name": ref.name or ref.friendly_name,
            "classification": ref.classification or ref.lens_bucket,
            "reason": ref.reason or ref.lens_bucket_reason or ref.lens_bucket_label,
        }
    )


def _enrich_incidents(incidents: list[Incident]) -> list[Incident]:
    enriched: list[Incident] = []
    for incident in incidents:
        enriched.append(
            incident.model_copy(
                update={
                    "affected_devices": [
                        _enrich_incident_entity(ref) for ref in incident.affected_devices
                    ]
                }
            )
        )
    return enriched


def _apply_report_compatibility_sections(detail: ReportDetail) -> ReportDetail:
    """Populate compatibility metadata without using Lens as report authority."""
    mode = detail.config_summary.get("mode")
    active = _enrich_incidents(
        [inc for inc in detail.incidents if inc.status != IncidentStatus.resolved]
    )
    incidents = _enrich_incidents(detail.incidents)
    # Version 2 Decision reports do not use Lens/executive prose as authority.
    if detail.report_version >= 2:
        executive = None
        health_summary = None
    else:
        executive = None
        if detail.summary and detail.summary.current_finding:
            executive = detail.summary.current_finding
        elif detail.diagnostic_conclusions:
            executive = detail.diagnostic_conclusions[0].summary
        overall = (
            detail.summary.overall_state
            if detail.summary
            else detail.health_snapshot.overall_severity
        )
        health_summary = _lens_health_summary(detail.devices, overall_state=overall)
    return detail.model_copy(
        update={
            "site": None,
            "mode": mode,
            "redaction_profile": detail.redaction.profile,
            "executive_summary": executive,
            "health_summary": health_summary,
            "incidents": incidents,
            "active_incidents": active,
            "collector_status": _collector_status_summary(detail.collector, mode),
            "events_or_timeline": detail.timeline,
            "domain_details": _domain_details(detail),
        }
    )


def _apply_lens_report_sections(detail: ReportDetail) -> ReportDetail:
    """Backward-compatible alias for report compatibility metadata."""
    return _apply_report_compatibility_sections(detail)


def _summary_block(
    *,
    overall_state: Severity,
    current_finding: str,
    networks,
    devices: list[DeviceSummary],
    routers,
    incidents,
) -> ReportSummaryBlock:
    return ReportSummaryBlock(
        overall_state=overall_state,
        current_finding=current_finding,
        networks_monitored=len(networks),
        total_devices=len(devices),
        active_incidents=sum(1 for i in incidents if i.status == IncidentStatus.open),
        watching_incidents=sum(1 for i in incidents if i.status == IncidentStatus.watching),
        unavailable_devices=_count_primary(devices, DeviceHealthPrimary.unavailable),
        router_risks=len(routers),
        stale_devices=_count_primary(devices, DeviceHealthPrimary.stale_reporting),
        weak_links=_count_primary(devices, DeviceHealthPrimary.weak_link),
        low_battery_devices=_count_primary(devices, DeviceHealthPrimary.low_battery),
    )


def _as_summary(device: DeviceDetail | DeviceSummary) -> DeviceSummary:
    return DeviceSummary.model_validate(device.model_dump())


def _filter_investigation_priorities(
    priorities: list[InvestigationPrioritySummary],
    *,
    scope: ReportScope,
    network_id: str | None,
    device_ieee: str | None,
    affected_keys: set[tuple[str, str]],
) -> list[InvestigationPrioritySummary]:
    if scope == ReportScope.full:
        return list(priorities)
    if scope == ReportScope.network and network_id:
        return [p for p in priorities if p.network_id == network_id]
    if scope == ReportScope.device and network_id and device_ieee:
        target = device_ieee.strip().lower()
        return [
            p
            for p in priorities
            if p.network_id == network_id
            and any(ieee.strip().lower() == target for ieee in p.device_ieees)
        ]
    if scope == ReportScope.incident and affected_keys:
        filtered: list[InvestigationPrioritySummary] = []
        for priority in priorities:
            affected_on_network = {
                ieee.strip().lower()
                for nid, ieee in affected_keys
                if nid == priority.network_id
            }
            device_norm = {ieee.strip().lower() for ieee in priority.device_ieees}
            if affected_on_network & device_norm:
                filtered.append(priority)
        return filtered
    return []


def _filter_coverage_warnings(
    warnings: list[DataCoverageWarningSummary],
    *,
    scope: ReportScope,
    network_ids: set[str],
) -> list[DataCoverageWarningSummary]:
    if scope == ReportScope.full:
        return list(warnings)
    return [w for w in warnings if w.network_id in network_ids]


def _assemble(
    *,
    data: ReportDataSource,
    config: AppConfig,
    reporting: ReportingConfig,
    collector: dict[str, Any],
    request: ReportRequest,
    scenario: str | None,
    repo: Repository | None = None,
) -> ReportDetail:
    dashboard = data.dashboard(scenario)
    all_networks = data.networks(scenario)
    all_routers = data.routers(scenario)
    all_incidents = data.incidents(scenario)
    timeline = list(data.timeline(scenario))[: reporting.max_recent_events]

    networks = all_networks
    routers = all_routers
    incidents = all_incidents
    device_details: list[DeviceDetail] = []
    device_keys: set[tuple[str, str]] | None = None
    context_network_id: str | None = None
    target_device_ieee: str | None = None
    finding = "Evidence report for the selected ZigbeeLens scope."
    conclusions = [dashboard.current_finding]

    if request.scope == ReportScope.network and request.network_id:
        nid = request.network_id
        context_network_id = nid
        networks = [n for n in all_networks if n.id == nid]
        routers = [r for r in all_routers if r.network_id == nid]
        incidents = [i for i in all_incidents if nid in i.network_ids]
        timeline = [e for e in timeline if e.network_id == nid]
    elif request.scope == ReportScope.incident and request.incident_id:
        inc = data.incident(request.incident_id, scenario)
        incidents = [inc] if inc else []
        net_ids = set(inc.network_ids) if inc else set()
        networks = [n for n in all_networks if n.id in net_ids]
        device_keys = {
            (ref.network_id, ref.ieee_address)
            for i in incidents
            for ref in i.affected_devices
        }
        routers = [r for r in all_routers if r.network_id in net_ids]
        timeline = list(inc.timeline) if inc else []
        if inc:
            conclusions = [inc.conclusion]
    elif request.scope == ReportScope.device and request.device:
        # Prefer explicit network + device identity; do not compose full inventory.
        if request.network_id:
            context_network_id = request.network_id
            device_keys = {(request.network_id, request.device)}
            target_device_ieee = request.device
        else:
            # Fallback: resolve from inventory once when network was omitted.
            inventory = data.devices(scenario)
            match = [d for d in inventory if d.ieee_address == request.device]
            if match:
                context_network_id = match[0].network_id
                device_keys = {(match[0].network_id, match[0].ieee_address)}
                target_device_ieee = match[0].ieee_address
            else:
                device_keys = set()

    device_ctx = data.report_device_context(
        scenario,
        network_id=context_network_id,
        device_keys=device_keys,
    )
    devices = device_ctx.devices
    stories = device_ctx.stories

    if request.scope == ReportScope.incident and device_keys is not None:
        devices = [
            d for d in devices if (d.network_id, d.ieee_address) in device_keys
        ]
        for d in devices:
            det = data.device(d.network_id, d.ieee_address, scenario)
            if det:
                device_details.append(det)
    elif request.scope == ReportScope.device:
        if devices:
            det = data.device(devices[0].network_id, devices[0].ieee_address, scenario)
            if det:
                device_details = [det]
                devices = [_as_summary(det)]
                networks = [n for n in all_networks if n.id == det.network_id]
                routers = [r for r in all_routers if r.network_id == det.network_id]
                incidents = [
                    i
                    for i in all_incidents
                    if any(
                        ref.ieee_address == det.ieee_address
                        and ref.network_id == det.network_id
                        for ref in i.affected_devices
                    )
                ]
                timeline = list(det.recent_events)[: reporting.max_recent_events]
                conclusions = [det.diagnostic]
                target_device_ieee = det.ieee_address
                context_network_id = det.network_id
            else:
                networks, devices, routers, incidents, timeline = [], [], [], [], []
                stories = {}
        else:
            networks, devices, routers, incidents, timeline = [], [], [], [], []
            stories = {}

    report_stories = []
    for device in devices:
        story = stories.get((device.network_id, device.ieee_address))
        if story is None:
            continue
        report_stories.append(
            report_device_story_from_story(device=device, story=story)
        )

    affected_keys: set[tuple[str, str]] = set()
    if request.scope == ReportScope.incident:
        affected_keys = {
            (ref.network_id, ref.ieee_address)
            for i in incidents
            for ref in i.affected_devices
        }

    scoped_network_ids = {n.id for n in networks}
    if request.scope == ReportScope.device and context_network_id:
        scoped_network_ids = {context_network_id}
    elif request.scope == ReportScope.incident:
        scoped_network_ids = {nid for nid, _ in affected_keys} | {
            n for i in incidents for n in i.network_ids
        }

    investigation_priorities = _filter_investigation_priorities(
        list(dashboard.investigation_priorities or []),
        scope=request.scope,
        network_id=context_network_id,
        device_ieee=target_device_ieee,
        affected_keys=affected_keys,
    )

    data_coverage_warnings = _filter_coverage_warnings(
        list(dashboard.data_coverage_warnings or []),
        scope=request.scope,
        network_ids=scoped_network_ids,
    )

    story_list = [
        stories[key]
        for rs in report_stories
        if (key := (rs.network_id, rs.ieee_address)) in stories
    ]
    decision_summary = report_decision_summary_from_stories(
        story_list if story_list else report_stories
    )

    summary = _summary_block(
        overall_state=dashboard.overall_severity,
        current_finding=finding,
        networks=networks,
        devices=devices,
        routers=routers,
        incidents=incidents,
    )

    return ReportDetail(
        id="report-preview",
        report_version=2,
        generated_at=utc_now_iso(),
        version=__version__,
        scope=request.scope.value,
        format=request.format.value,
        redaction=default_redaction_status(),
        summary=summary,
        decision_summary=decision_summary,
        investigation_priorities=investigation_priorities,
        device_stories=report_stories,
        data_coverage_warnings=data_coverage_warnings,
        config_summary=build_config_summary(config),
        collector=collector,
        networks=networks,
        devices=devices,
        device_details=device_details,
        router_risks=routers,
        incidents=incidents,
        timeline=timeline,
        health_snapshot=dashboard.health_snapshot,
        diagnostic_conclusions=conclusions,
        limitations=_report_limitations(config, repo) if repo else list(STANDARD_LIMITATIONS),
        raw_counts={
            "events_included": len(timeline),
            "devices_included": len(devices),
            "incidents_included": len(incidents),
            **(topology_report_counts(repo, config) if repo else {"topology_snapshots": 0}),
        },
        markdown_summary="",
    )


def generate_report(
    *,
    data: ReportDataSource,
    config: AppConfig,
    reporting: ReportingConfig,
    collector: dict[str, Any],
    request: ReportRequest,
    scenario: str | None = None,
    repo: Repository | None = None,
) -> ReportDetail:
    detail = _assemble(
        data=data,
        config=config,
        reporting=reporting,
        collector=collector,
        request=request,
        scenario=scenario,
        repo=repo,
    )
    resolved = resolve_redaction(
        request.redaction,
        default_profile=reporting.default_profile,
        default_include_raw=reporting.include_raw_payloads,
    )
    redactor = Redactor(resolved)
    dumped = detail.model_dump(mode="json")
    # The redaction-status block is metadata about redaction (and contains
    # boolean fields whose names resemble secret keys); it is replaced below,
    # so exclude it from the secret-scrubbing walk.
    dumped.pop("redaction", None)
    redacted_dict = redactor.redact(dumped)
    redacted_dict["redaction"] = default_redaction_status().model_dump()
    redacted = ReportDetail.model_validate(redacted_dict)

    if not resolved.include_timeline:
        redacted.timeline = []
    redacted.redaction = resolved.to_status()
    redacted.scope = request.scope.value
    redacted.format = request.format.value
    redacted.raw_counts["events_included"] = len(redacted.timeline)
    redacted = _apply_lens_report_sections(redacted)
    redacted.markdown_summary = render_markdown(redacted)
    return redacted


# -- rendering -----------------------------------------------------------


def _title(value: str) -> str:
    return value.replace("_", " ").title()


def render_markdown(detail: ReportDetail) -> str:
    s = detail.summary
    lines = [
        "# ZigbeeLens diagnostic report",
        "",
        f"Product: {detail.product}",
        f"Version: {detail.version}",
        f"Generated: {detail.generated_at}",
        f"Scope: {_title(detail.scope)}",
        f"Mode: {detail.mode or 'unknown'}",
        f"Redaction profile: {detail.redaction_profile or detail.redaction.profile}",
        "",
        "## Executive summary",
        "",
    ]
    if detail.executive_summary:
        lines.append(detail.executive_summary)
    elif s:
        lines.append(s.current_finding)

    if detail.health_summary and detail.health_summary.bucket_counts:
        lines += ["", "## Health summary", ""]
        for bucket, count in sorted(detail.health_summary.bucket_counts.items()):
            if count <= 0:
                continue
            label = detail.health_summary.bucket_labels.get(
                bucket,
                BUCKET_LABELS.get(LensBucket(bucket), bucket.replace("_", " ").title()),
            )
            lines.append(f"- {label}: {count}")

    if s:
        lines += [
            "",
            "## Summary counts",
            "",
            f"Overall state: {_title(s.overall_state.value)}",
            f"Networks monitored: {s.networks_monitored}",
            f"Devices monitored: {s.total_devices}",
            f"Active incidents: {s.active_incidents}",
        ]

    active = detail.active_incidents or [
        i for i in detail.incidents if i.status != IncidentStatus.resolved
    ]
    if active:
        lines += ["", "## Active incidents"]
        for inc in active:
            lines += [
                "",
                f"### {inc.title}",
                "",
                f"Severity: {_title(inc.severity.value)}",
                f"Scope: {_title(inc.scope.value)}",
                f"Confidence: {_title(inc.confidence.value)}",
                f"Network: {', '.join(inc.network_ids)}",
                f"Affected devices: {inc.affected_device_count}",
            ]
            if inc.affected_devices:
                lines += ["", "Affected entities:"]
                for entity in inc.affected_devices[:20]:
                    reason = entity.reason or entity.lens_bucket_reason or entity.lens_bucket_label
                    lines.append(
                        f"- {entity.name or entity.friendly_name} "
                        f"({entity.classification or entity.lens_bucket}): {reason}"
                    )
            if inc.evidence:
                lines += ["", "Evidence:"]
                lines += [f"- {e.summary}" for e in inc.evidence]
            if inc.limitations:
                lines += ["", "Limitations:"]
                lines += [f"- {limitation.summary}" for limitation in inc.limitations]

    if detail.collector_status:
        lines += [
            "",
            "## Collector status",
            "",
            f"MQTT collector: {detail.collector_status.get('mqtt_collector', 'unknown')}",
            f"Zigbee2MQTT bridge: {detail.collector_status.get('zigbee2mqtt_bridge', 'unknown')}",
        ]

    unhealthy = [d for d in detail.devices if d.health.severity != Severity.healthy]
    if unhealthy:
        lines += [
            "",
            "## Unhealthy devices",
            "",
            "| Device | Network | Health | Lens bucket | Evidence |",
            "|---|---|---|---|---|",
        ]
        for d in unhealthy[:50]:
            evidence = d.health.evidence[0] if d.health.evidence else ""
            lines.append(
                f"| {d.friendly_name} | {d.network_id} | {d.health.primary.value} | "
                f"{d.lens_bucket_label} | {evidence} |"
            )

    lines += ["", "## Limitations", ""]
    lines += [f"- {limitation.summary}" for limitation in detail.limitations]
    lines.append("")
    return "\n".join(lines)


# -- serialization -------------------------------------------------------


def report_body_as_json(detail: ReportDetail) -> dict[str, Any]:
    return json.loads(detail.model_dump_json())


def report_body_as_yaml(detail: ReportDetail) -> str:
    return yaml.safe_dump(report_body_as_json(detail), sort_keys=False, allow_unicode=True)


# -- persistence ---------------------------------------------------------


def _finding_text(detail: ReportDetail) -> str:
    if detail.summary and detail.summary.current_finding:
        return detail.summary.current_finding
    if detail.diagnostic_conclusions:
        return detail.diagnostic_conclusions[0].summary
    return "ZigbeeLens diagnostic report"


def store_report(repo: Repository, detail: ReportDetail, request: ReportRequest) -> ReportRow:
    metadata = {
        "incident_count": len(detail.incidents),
        "device_count": len(detail.devices),
        "network_count": len(detail.networks),
        "version": detail.version,
        "topology_snapshots": detail.raw_counts.get("topology_snapshots", 0),
        "home_assistant_enrichment": repo.get_ha_enrichment_status(),
    }
    row = repo.reports.save_report(
        report_id=None,
        format=request.format.value,
        scope=detail.scope,
        redaction_profile=detail.redaction.profile,
        summary=_finding_text(detail),
        body=report_body_as_json(detail),
        markdown=detail.markdown_summary,
        redaction=detail.redaction.model_dump(),
        metadata=metadata,
    )
    detail.id = row.id
    return row


def summary_from_detail(row: ReportRow, detail: ReportDetail) -> ReportSummary:
    return ReportSummary(
        id=row.id,
        generated_at=row.generated_at,
        redaction_applied=True,
        incident_count=len(detail.incidents),
        device_count=len(detail.devices),
        network_count=len(detail.networks),
        summary=_finding_text(detail),
        format=row.format,
        scope=row.scope,
        redaction_profile=row.redaction_profile,
    )


def summary_from_row(row: ReportRow) -> ReportSummary:
    meta: dict[str, Any] = {}
    try:
        meta = json.loads(row.metadata_json) if row.metadata_json else {}
    except (ValueError, TypeError):
        meta = {}
    return ReportSummary(
        id=row.id,
        generated_at=row.generated_at,
        redaction_applied=True,
        incident_count=int(meta.get("incident_count", 0)),
        device_count=int(meta.get("device_count", 0)),
        network_count=int(meta.get("network_count", 0)),
        summary=row.summary,
        format=row.format,
        scope=row.scope,
        redaction_profile=row.redaction_profile,
    )
