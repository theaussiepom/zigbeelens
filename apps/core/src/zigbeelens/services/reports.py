"""Report generation: scoped assembly, redaction, and rendering.

Reports are evidence-backed diagnostic snapshots, not root-cause proof. They are
always redacted before they are stored or returned. The full structured report
is produced as a :class:`ReportDetail`; JSON, YAML, and Markdown are derived from
it on demand.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Protocol

import yaml

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
from zigbeelens.services.report_redaction import Redactor, resolve_redaction
from zigbeelens.services.report_scope import ReportScopeAmbiguityError
from zigbeelens.storage.repository import ReportRow, Repository

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
    """Narrow composition entry used to assemble reports (mock or live)."""

    def compose_report_scope(
        self,
        request: ReportRequest,
        scenario: str | None = None,
        *,
        reference_now: datetime,
        include_timeline: bool,
        reporting: ReportingConfig,
    ): ...


def default_redaction_status() -> ReportRedactionStatus:
    return ReportRedactionStatus(applied=True, profile="standard", mqtt_credentials=True)


def topology_report_counts(
    repo: Repository,
    config: AppConfig,
    *,
    network_ids: list[str] | None = None,
) -> dict[str, int]:
    if not config.topology.enabled:
        return {"topology_snapshots": 0}
    if network_ids is None:
        network_ids = [network.id for network in config.networks]
    return {
        "topology_snapshots": repo.count_topology_snapshots_for_networks(network_ids)
    }


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
    """Legacy helper retained for v1 compatibility paths; unused for decision DTOs."""
    del devices, primary
    return 0


def _lens_health_summary(
    devices: list[DeviceSummary],
    *,
    overall_state: Severity | None,
) -> LensHealthSummary:
    """Legacy v1 Lens summary — empty for decision-only device payloads."""
    del devices
    counts = {bucket.value: 0 for bucket in LensBucket}
    return LensHealthSummary(
        overall_state=overall_state.value if overall_state else None,
        bucket_counts=counts,
        bucket_labels={},
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


def _enrich_incidents(incidents: list[Incident]) -> list[Incident]:
    """Identity pass — IncidentDeviceRef is already decision-only."""
    return list(incidents)


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
        scoped: list[InvestigationPrioritySummary] = []
        for priority in priorities:
            if priority.network_id != network_id:
                continue
            device_ieees = [
                ieee for ieee in priority.device_ieees if ieee.strip().lower() == target
            ]
            if not device_ieees:
                continue
            scoped.append(priority.model_copy(update={"device_ieees": device_ieees}))
        return scoped
    if scope == ReportScope.incident and affected_keys:
        filtered: list[InvestigationPrioritySummary] = []
        for priority in priorities:
            affected_on_network = {
                ieee.strip().lower()
                for nid, ieee in affected_keys
                if nid == priority.network_id
            }
            device_ieees = [
                ieee
                for ieee in priority.device_ieees
                if ieee.strip().lower() in affected_on_network
            ]
            if not device_ieees:
                continue
            filtered.append(priority.model_copy(update={"device_ieees": device_ieees}))
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


def _without_timelines(detail: ReportDetail) -> ReportDetail:
    """Clear every timeline/event collection controlled by include_timeline."""
    device_stories = [
        story.model_copy(update={"timeline": []}) for story in detail.device_stories
    ]
    incidents = [
        incident.model_copy(update={"timeline": []}) for incident in detail.incidents
    ]
    active_incidents = [
        incident.model_copy(update={"timeline": []})
        for incident in detail.active_incidents
    ]
    device_details = [
        det.model_copy(update={"recent_events": []}) for det in detail.device_details
    ]
    return detail.model_copy(
        update={
            "timeline": [],
            "events_or_timeline": [],
            "device_stories": device_stories,
            "incidents": incidents,
            "active_incidents": active_incidents,
            "device_details": device_details,
        }
    )


def _recorded_incident_interpretation(incident: Incident) -> str | None:
    """Historical Incident.interpretation when distinct from the event summary."""
    text = (incident.interpretation or "").strip()
    if not text:
        return None
    if text == (incident.summary or "").strip():
        return None
    return text


def generate_report(
    *,
    data: ReportDataSource,
    config: AppConfig,
    reporting: ReportingConfig,
    collector: dict[str, Any],
    request: ReportRequest,
    scenario: str | None = None,
    repo: Repository | None = None,
    now: datetime | None = None,
) -> ReportDetail:
    """Assemble one report via scope-first composition (Track 3F)."""
    from zigbeelens.services.report_composition import project_report_detail

    resolved = resolve_redaction(
        request.redaction,
        default_profile=reporting.default_profile,
        default_include_raw=reporting.include_raw_payloads,
    )
    reference_now = now or datetime.now(timezone.utc)
    if reference_now.tzinfo is None:
        reference_now = reference_now.replace(tzinfo=timezone.utc)

    composition = data.compose_report_scope(
        request,
        scenario,
        reference_now=reference_now,
        include_timeline=resolved.include_timeline,
        reporting=reporting,
    )
    detail = project_report_detail(
        composition,
        config=config,
        collector=collector,
        request=request,
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
        redacted = _without_timelines(redacted)
    redacted.redaction = resolved.to_status()
    redacted.scope = request.scope.value
    redacted.format = request.format.value
    # Compatibility aliases/active incidents must be built after timeline clearing.
    redacted = _apply_lens_report_sections(redacted)
    redacted.raw_counts["events_included"] = len(redacted.timeline)
    redacted.markdown_summary = render_markdown(redacted)
    return redacted


# Re-export for API/route handlers that map scope ambiguity to HTTP errors.
__all_report_errors__ = (ReportScopeAmbiguityError,)


# -- rendering -----------------------------------------------------------


_DEVICE_STORY_STATUS_ORDER = (
    "review_first",
    "worth_reviewing",
    "improve_data_coverage",
    "watch",
    "changed",
    "informational",
    "no_notable_change",
    "data_unavailable",
)


def _title(value: str) -> str:
    return value.replace("_", " ").title()


def _evidence_line(ref: dict[str, Any]) -> str:
    source = str(ref.get("source") or "")
    ref_id = ref.get("id")
    captured_at = ref.get("captured_at")
    if source == "topology_snapshot":
        parts = ["Latest stored topology snapshot"]
        if captured_at:
            parts.append(f"captured {captured_at}")
        if ref_id:
            parts.append(f"({ref_id})")
        return " · ".join(parts)
    if ref_id:
        return f"Stored evidence ({ref_id})"
    return "Stored evidence reference"


def _ordered_device_stories(detail: ReportDetail):
    order = {status: index for index, status in enumerate(_DEVICE_STORY_STATUS_ORDER)}

    def sort_key(story):
        return (
            order.get(str(story.status), len(order)),
            story.friendly_name.lower(),
            story.ieee_address,
        )

    return sorted(detail.device_stories, key=sort_key)


def _decision_list_summary(detail: ReportDetail) -> str:
    """Persisted/list summary from shared Decision output only (Version 2)."""
    from zigbeelens.presentation.report_decision_copy import headline_text

    if detail.investigation_priorities:
        return detail.investigation_priorities[0].title
    ordered = _ordered_device_stories(detail)
    if ordered:
        story = ordered[0]
        return f"{story.friendly_name} — {headline_text(story.headline_code)}"
    return "No notable Device Story decisions in this report scope."


def render_markdown_v1(detail: ReportDetail) -> str:
    """Legacy Markdown for stored Version 1 report bodies (compatibility only)."""
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
                    lines.append(
                        f"- {entity.friendly_name} "
                        f"({entity.decision.status}): {entity.decision.headline_code}"
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

    review = [
        d
        for d in detail.devices
        if str(d.decision.status)
        in {"review_first", "worth_reviewing", "watch", "improve_data_coverage"}
    ]
    if review:
        lines += [
            "",
            "## Devices to review",
            "",
            "| Device | Network | Decision | Headline |",
            "|---|---|---|---|",
        ]
        for d in review[:50]:
            lines.append(
                f"| {d.friendly_name} | {d.network_id} | {d.decision.status} | "
                f"{d.decision.headline_code} |"
            )

    lines += ["", "## Limitations", ""]
    lines += [f"- {limitation.summary}" for limitation in detail.limitations]
    lines.append("")
    return "\n".join(lines)


def render_markdown_v2(detail: ReportDetail) -> str:
    """Decision-backed Markdown for Version 2 evidence reports."""
    from zigbeelens.presentation.report_decision_copy import (
        decision_status_label,
        device_coverage_label,
        headline_text,
        limitation_text,
        reason_text,
        suggested_check_text,
        coverage_label,
    )

    lines = [
        "# ZigbeeLens evidence report",
        "",
        f"Product: {detail.product}",
        f"Version: {detail.version}",
        f"Generated: {detail.generated_at}",
        f"Scope: {_title(detail.scope)}",
        f"Mode: {detail.mode or 'unknown'}",
        f"Redaction profile: {detail.redaction_profile or detail.redaction.profile}",
        "",
        "## Summary",
        "",
        f"Networks in scope: {len(detail.networks)}",
        f"Devices in scope: {len(detail.devices)}",
        f"Incident records in scope: {len(detail.incidents)}",
    ]
    if detail.decision_summary and detail.decision_summary.status_counts:
        lines += ["", "Current Device Story decisions:"]
        for status in _DEVICE_STORY_STATUS_ORDER:
            count = detail.decision_summary.status_counts.get(status, 0)
            if count:
                lines.append(f"- {decision_status_label(status)}: {count}")
        for status, count in sorted(detail.decision_summary.status_counts.items()):
            if status not in _DEVICE_STORY_STATUS_ORDER and count:
                lines.append(f"- {decision_status_label(status)}: {count}")

    if detail.investigation_priorities:
        lines += ["", "## What to check first", ""]
        for priority in detail.investigation_priorities:
            lines.append(f"### {priority.title}")
            lines.append("")
            lines.append(priority.summary)
            lines.append(f"Network: {priority.network_id}")
            if priority.device_ieees:
                lines.append(f"Devices referenced: {len(priority.device_ieees)}")
            lines.append("")

    ordered_stories = _ordered_device_stories(detail)
    if ordered_stories:
        lines += ["## Device stories", ""]
        for story in ordered_stories:
            lines.append(f"### {story.friendly_name}")
            lines.append("")
            lines.append(f"Status: {decision_status_label(story.status)}")
            lines.append(headline_text(story.headline_code))
            if story.reasons:
                lines += ["", "Why:"]
                for reason in story.reasons:
                    code = str(reason.get("code") if isinstance(reason, dict) else reason.code)
                    params = (
                        reason.get("params") if isinstance(reason, dict) else reason.params
                    ) or {}
                    lines.append(f"- {reason_text(code, params)}")
            if story.limitations:
                lines += ["", "Data limitations:"]
                for item in story.limitations:
                    code = str(item.get("code") if isinstance(item, dict) else item.code)
                    params = (
                        item.get("params") if isinstance(item, dict) else item.params
                    ) or {}
                    lines.append(f"- {limitation_text(code, params)}")
            lines.append("")

    coverage_lines: list[str] = []
    if detail.data_coverage_warnings:
        coverage_lines.append("### Network coverage")
        coverage_lines.append("")
        for warning in detail.data_coverage_warnings:
            coverage_lines.append(
                f"- {coverage_label(warning.label_code, warning.params)} ({warning.network_id})"
            )
        coverage_lines.append("")
    device_cov_any = False
    for story in ordered_stories:
        if not story.coverage:
            continue
        if not device_cov_any:
            coverage_lines.append("### Device coverage")
            coverage_lines.append("")
            device_cov_any = True
        coverage_lines.append(f"### {story.friendly_name}")
        for item in story.coverage:
            code = str(item.get("label_code") if isinstance(item, dict) else item.label_code)
            params = (item.get("params") if isinstance(item, dict) else item.params) or {}
            coverage_lines.append(f"- {device_coverage_label(code, params)}")
        coverage_lines.append("")
    if coverage_lines:
        lines += ["## Data coverage", ""] + coverage_lines

    evidence_blocks: list[str] = []
    for story in ordered_stories:
        if not story.evidence:
            continue
        evidence_blocks.append(f"### {story.friendly_name}")
        for ref in story.evidence:
            evidence_blocks.append(f"- {_evidence_line(ref if isinstance(ref, dict) else ref.model_dump())}")
        evidence_blocks.append("")
    if evidence_blocks:
        lines += ["## Evidence", ""] + evidence_blocks

    related_incident_blocks: list[str] = []
    for story in ordered_stories:
        related_ids = list(getattr(story, "related_unresolved_incident_ids", []) or [])
        if not related_ids:
            continue
        related_incident_blocks.append(f"### {story.friendly_name}")
        for incident_id in related_ids:
            related_incident_blocks.append(f"- Related unresolved incident record ({incident_id})")
        related_incident_blocks.append("")
    if related_incident_blocks:
        lines += ["## Related incident records", ""] + related_incident_blocks

    if detail.incidents:
        lines += ["## Incident records", ""]
        for inc in detail.incidents:
            lines.append(f"### {inc.title}")
            lines.append("")
            lines.append(f"Lifecycle: {_title(inc.status.value)}")
            lines.append(f"Recorded summary: {inc.summary}")
            lines.append(f"Networks: {', '.join(inc.network_ids)}")
            lines.append(f"Opened: {inc.opened_at}")
            lines.append(f"Updated: {inc.updated_at}")
            if inc.resolved_at:
                lines.append(f"Resolved: {inc.resolved_at}")
            recorded = _recorded_incident_interpretation(inc)
            if recorded:
                lines += ["", "Recorded interpretation:", "", recorded]
            if inc.evidence:
                lines += ["", "Stored evidence:"]
                lines += [f"- {e.summary}" for e in inc.evidence]
            if inc.limitations:
                lines += ["", "Recorded limitations:"]
                lines += [f"- {limitation.summary}" for limitation in inc.limitations]
            lines.append("")

    limitation_texts: list[str] = [lim.summary for lim in detail.limitations]
    for story in ordered_stories:
        for item in story.limitations:
            code = str(item.get("code") if isinstance(item, dict) else item.code)
            params = (item.get("params") if isinstance(item, dict) else item.params) or {}
            text = limitation_text(code, params)
            if text not in limitation_texts:
                limitation_texts.append(text)
    if limitation_texts:
        lines += ["## Limitations", ""]
        lines += [f"- {text}" for text in limitation_texts]
        lines.append("")

    check_blocks: list[str] = []
    for story in ordered_stories:
        if not story.suggested_checks:
            continue
        seen: set[str] = set()
        check_blocks.append(f"### {story.friendly_name}")
        for item in story.suggested_checks:
            code = str(item.get("code") if isinstance(item, dict) else item.code)
            params = (item.get("params") if isinstance(item, dict) else item.params) or {}
            text = suggested_check_text(code, params)
            if text in seen:
                continue
            seen.add(text)
            check_blocks.append(f"- {text}")
        check_blocks.append("")
    if check_blocks:
        lines += ["## Suggested checks", ""] + check_blocks

    if detail.collector_status:
        lines += [
            "## Collector status",
            "",
            f"MQTT collector: {detail.collector_status.get('mqtt_collector', 'unknown')}",
            f"Zigbee2MQTT bridge: {detail.collector_status.get('zigbee2mqtt_bridge', 'unknown')}",
            "",
        ]

    return "\n".join(lines).rstrip() + "\n"


def render_markdown(detail: ReportDetail) -> str:
    if detail.report_version >= 2:
        return render_markdown_v2(detail)
    return render_markdown_v1(detail)


# -- serialization -------------------------------------------------------


def report_body_as_json(detail: ReportDetail) -> dict[str, Any]:
    return json.loads(detail.model_dump_json())


def report_body_as_yaml(detail: ReportDetail) -> str:
    return yaml.safe_dump(report_body_as_json(detail), sort_keys=False, allow_unicode=True)


# -- persistence ---------------------------------------------------------


def _finding_text(detail: ReportDetail) -> str:
    if detail.report_version >= 2:
        return _decision_list_summary(detail)
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
