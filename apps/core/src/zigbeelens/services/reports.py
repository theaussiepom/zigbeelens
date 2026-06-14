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
    DeviceDetail,
    DeviceHealthPrimary,
    DeviceSummary,
    IncidentStatus,
    LimitationItem,
    ReportDetail,
    ReportRedactionStatus,
    ReportRequest,
    ReportScope,
    ReportSummary,
    ReportSummaryBlock,
    Severity,
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
    all_devices = data.devices(scenario)
    all_routers = data.routers(scenario)
    all_incidents = data.incidents(scenario)
    timeline = list(data.timeline(scenario))[: reporting.max_recent_events]

    networks = all_networks
    devices = all_devices
    routers = all_routers
    incidents = all_incidents
    device_details: list[DeviceDetail] = []
    finding = dashboard.current_finding.summary
    conclusions = [dashboard.current_finding]

    if request.scope == ReportScope.network and request.network_id:
        nid = request.network_id
        networks = [n for n in all_networks if n.id == nid]
        devices = [d for d in all_devices if d.network_id == nid]
        routers = [r for r in all_routers if r.network_id == nid]
        incidents = [i for i in all_incidents if nid in i.network_ids]
        timeline = [e for e in timeline if e.network_id == nid]
    elif request.scope == ReportScope.incident and request.incident_id:
        inc = data.incident(request.incident_id, scenario)
        incidents = [inc] if inc else []
        net_ids = set(inc.network_ids) if inc else set()
        networks = [n for n in all_networks if n.id in net_ids]
        affected = {
            (ref.network_id, ref.ieee_address)
            for i in incidents
            for ref in i.affected_devices
        }
        devices = [d for d in all_devices if (d.network_id, d.ieee_address) in affected]
        routers = [r for r in all_routers if r.network_id in net_ids]
        timeline = list(inc.timeline) if inc else []
        for d in devices:
            det = data.device(d.network_id, d.ieee_address, scenario)
            if det:
                device_details.append(det)
        if inc:
            finding = inc.summary
            conclusions = [inc.conclusion]
    elif request.scope == ReportScope.device and request.device:
        match = [
            d
            for d in all_devices
            if d.ieee_address == request.device
            and (request.network_id is None or d.network_id == request.network_id)
        ]
        det = data.device(match[0].network_id, match[0].ieee_address, scenario) if match else None
        if det:
            device_details = [det]
            devices = [_as_summary(det)]
            networks = [n for n in all_networks if n.id == det.network_id]
            routers = [r for r in all_routers if r.network_id == det.network_id]
            incidents = [
                i
                for i in all_incidents
                if any(
                    ref.ieee_address == det.ieee_address and ref.network_id == det.network_id
                    for ref in i.affected_devices
                )
            ]
            timeline = list(det.recent_events)[: reporting.max_recent_events]
            finding = det.diagnostic.summary
            conclusions = [det.diagnostic]
        else:
            networks, devices, routers, incidents, timeline = [], [], [], [], []

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
        generated_at=utc_now_iso(),
        version=__version__,
        scope=request.scope.value,
        format=request.format.value,
        redaction=default_redaction_status(),
        summary=summary,
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
        f"Generated: {detail.generated_at}",
        f"Scope: {_title(detail.scope)}",
        f"Redaction: {detail.redaction.profile}",
        "",
        "## Summary",
        "",
    ]
    if s:
        lines += [
            f"Overall state: {_title(s.overall_state.value)}",
            f"Networks monitored: {s.networks_monitored}",
            f"Devices monitored: {s.total_devices}",
            f"Active incidents: {s.active_incidents}",
            "",
            "Current finding:",
            s.current_finding,
        ]

    active = [i for i in detail.incidents if i.status != IncidentStatus.resolved]
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
            if inc.evidence:
                lines += ["", "Evidence:"]
                lines += [f"- {e.summary}" for e in inc.evidence]
            if inc.limitations:
                lines += ["", "Limitations:"]
                lines += [f"- {limitation.summary}" for limitation in inc.limitations]

    unhealthy = [d for d in detail.devices if d.health.severity != Severity.healthy]
    if unhealthy:
        lines += [
            "",
            "## Unhealthy devices",
            "",
            "| Device | Network | Health | Evidence |",
            "|---|---|---|---|",
        ]
        for d in unhealthy[:50]:
            evidence = d.health.evidence[0] if d.health.evidence else ""
            lines.append(
                f"| {d.friendly_name} | {d.network_id} | {d.health.primary.value} | {evidence} |"
            )

    lines += ["", "## Known limitations", ""]
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
    row = repo.save_report(
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
