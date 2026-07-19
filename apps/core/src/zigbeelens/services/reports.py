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
    DeviceSummary,
    Incident,
    InvestigationPrioritySummary,
    LimitationItem,
    ReportDetail,
    ReportDetailV3,
    ReportRedactionStatus,
    ReportRequest,
    ReportScope,
    ReportSummary,
)
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


def _without_timelines(detail: ReportDetailV3) -> ReportDetailV3:
    """Clear every timeline/event collection controlled by include_timeline."""
    device_stories = [
        story.model_copy(update={"timeline": []}) for story in detail.device_stories
    ]
    incidents = [
        incident.model_copy(update={"timeline": []}) for incident in detail.incidents
    ]
    domain = detail.domain_details.model_copy(
        update={
            "device_details": [
                det.model_copy(update={"recent_events": []})
                for det in detail.domain_details.device_details
            ]
        }
    )
    return detail.model_copy(
        update={
            "events_or_timeline": [],
            "device_stories": device_stories,
            "incidents": incidents,
            "domain_details": domain,
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
) -> ReportDetailV3:
    """Assemble one exact report-contract-v3 body via scope-first composition."""
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
    redacted = ReportDetailV3.model_validate(redacted_dict)

    if not resolved.include_timeline:
        redacted = _without_timelines(redacted)
    redacted.redaction = resolved.to_status()
    redacted.scope = request.scope.value
    redacted.format = request.format.value
    mode = redacted.config_summary.get("mode")
    redacted.collector_status = _collector_status_summary(
        redacted.collector_status, mode
    )
    redacted.raw_counts["events_included"] = len(redacted.events_or_timeline)
    redacted.markdown_summary = render_markdown_v3(redacted)
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


def render_markdown_v3(detail: ReportDetail) -> str:
    """Decision-led Markdown for Version 3 reports (no Health/Lens sections)."""
    from zigbeelens.presentation.report_decision_copy import (
        decision_status_label,
        headline_text,
        limitation_text,
        reason_text,
        suggested_check_text,
        coverage_label,
        device_coverage_label,
    )

    lines = [
        "# ZigbeeLens Evidence Report",
        "",
        f"Product: {detail.product}",
        f"Report version: {detail.report_version}",
        f"Generated: {detail.generated_at}",
        f"Scope: {detail.scope}",
        f"Format: {detail.format}",
        "",
        "## Decision summary",
        "",
    ]
    summary = detail.decision_summary
    if summary is None:
        lines.append("No decision summary is available for this scope.")
    else:
        overall = summary.overall_status
        lines.append(f"Overall status: {decision_status_label(str(overall))}")
        status_counts = {
            str(key): value for key, value in (summary.status_counts or {}).items()
        }
        if status_counts:
            lines.append("")
            lines.append("Status counts:")
            for status in _DEVICE_STORY_STATUS_ORDER:
                count = status_counts.get(status, 0)
                if count:
                    lines.append(f"- {decision_status_label(str(status))}: {count}")
            for status, count in sorted(status_counts.items()):
                if status not in _DEVICE_STORY_STATUS_ORDER and count:
                    lines.append(f"- {decision_status_label(str(status))}: {count}")
        lines.append(f"Coverage warnings: {summary.coverage_warning_count}")

    lines += ["", "## What to review first", ""]
    if detail.investigation_priorities:
        for item in detail.investigation_priorities:
            lines.append(f"- **{item.title}** ({item.priority}): {item.summary}")
    else:
        lines.append("No investigation priorities in this scope.")

    ordered_stories = _ordered_device_stories(detail)
    lines += ["", "## Device Stories", ""]
    if ordered_stories:
        for story in ordered_stories:
            lines.append(f"### {story.friendly_name}")
            lines.append("")
            lines.append(f"Status: {decision_status_label(story.status)}")
            lines.append(f"Headline: {headline_text(story.headline_code)}")
            if story.reasons:
                lines += ["", "Why:"]
                for reason in story.reasons:
                    code = str(
                        reason.get("code") if isinstance(reason, dict) else reason.code
                    )
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
    else:
        lines.append("No Device Stories in this scope.")

    coverage_lines: list[str] = []
    if detail.data_coverage_warnings:
        for warning in detail.data_coverage_warnings:
            coverage_lines.append(
                f"- {coverage_label(warning.label_code, warning.params)} ({warning.network_id})"
            )
    for story in ordered_stories:
        if not story.coverage:
            continue
        coverage_lines.append(f"- {story.friendly_name}:")
        for item in story.coverage:
            code = str(
                item.get("label_code") if isinstance(item, dict) else item.label_code
            )
            params = (item.get("params") if isinstance(item, dict) else item.params) or {}
            coverage_lines.append(f"  - {device_coverage_label(code, params)}")
    lines += ["", "## Data coverage", ""]
    lines += coverage_lines or ["No data coverage warnings in this scope."]

    evidence_blocks: list[str] = []
    for story in ordered_stories:
        if not story.evidence:
            continue
        evidence_blocks.append(f"### {story.friendly_name}")
        for ref in story.evidence:
            evidence_blocks.append(
                f"- {_evidence_line(ref if isinstance(ref, dict) else ref.model_dump())}"
            )
        evidence_blocks.append("")
    if evidence_blocks:
        lines += ["", "## Evidence", ""] + evidence_blocks

    related_incident_blocks: list[str] = []
    for story in ordered_stories:
        related_ids = list(getattr(story, "related_unresolved_incident_ids", []) or [])
        if not related_ids:
            continue
        related_incident_blocks.append(f"### {story.friendly_name}")
        for incident_id in related_ids:
            related_incident_blocks.append(
                f"- Related unresolved incident record ({incident_id})"
            )
        related_incident_blocks.append("")
    if related_incident_blocks:
        lines += ["", "## Related incident records", ""] + related_incident_blocks

    lines += ["", "## Incidents", ""]
    if detail.incidents:
        for inc in detail.incidents:
            lines.append(f"### {inc.title}")
            lines.append("")
            lines.append(f"Status: {inc.status.value}")
            lines.append(f"Severity: {inc.severity.value}")
            lines.append(f"Summary: {inc.summary}")
            lines.append("")
    else:
        lines.append("No incidents in this scope.")

    domain = detail.domain_details
    lines += ["", "## Scope details", ""]
    lines.append(f"Networks: {len(domain.networks)}")
    lines.append(f"Devices: {len(domain.devices)}")
    lines.append(f"Router risks: {len(domain.router_risks)}")
    lines.append(f"Topology snapshots: {domain.topology_snapshot_count}")

    if detail.events_or_timeline:
        lines += ["", "## Timeline", ""]
        for event in detail.events_or_timeline[:50]:
            lines.append(f"- {event.timestamp}: {event.title}")

    lines += ["", "## Limitations", ""]
    if detail.limitations:
        lines += [f"- {item.summary}" for item in detail.limitations]
    else:
        lines.append("None recorded.")

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
        lines += ["", "## Suggested checks", ""] + check_blocks

    lines += [
        "",
        "## Redaction",
        "",
        f"Profile: {detail.redaction.profile}",
        "",
    ]
    return "\n".join(lines)


def render_markdown(detail: ReportDetailV3) -> str:
    """Current writers only emit report_version=3 Markdown."""
    return render_markdown_v3(detail)


# -- serialization -------------------------------------------------------


def report_body_as_json(detail: ReportDetail) -> dict[str, Any]:
    return json.loads(detail.model_dump_json())


def report_body_as_yaml(detail: ReportDetail) -> str:
    return yaml.safe_dump(report_body_as_json(detail), sort_keys=False, allow_unicode=True)


# -- persistence ---------------------------------------------------------


def _finding_text(detail: ReportDetailV3) -> str:
    return _decision_list_summary(detail)


def _report_device_count(detail: ReportDetailV3) -> int:
    return len(detail.domain_details.devices)


def _report_network_count(detail: ReportDetailV3) -> int:
    return len(detail.domain_details.networks)


def store_report(repo: Repository, detail: ReportDetailV3, request: ReportRequest) -> ReportRow:
    """Persist a v3 report with its final ID written into the body once."""
    import uuid

    report_id = str(uuid.uuid4())
    detail.id = report_id
    metadata = {
        "incident_count": len(detail.incidents),
        "device_count": _report_device_count(detail),
        "network_count": _report_network_count(detail),
        "version": detail.version,
        "topology_snapshots": detail.raw_counts.get("topology_snapshots", 0),
        "home_assistant_enrichment": repo.get_ha_enrichment_status(),
    }
    return repo.reports.save_report(
        report_id=report_id,
        format=request.format.value,
        scope=detail.scope,
        redaction_profile=detail.redaction.profile,
        summary=_finding_text(detail),
        body=report_body_as_json(detail),
        markdown=detail.markdown_summary,
        redaction=detail.redaction.model_dump(),
        metadata=metadata,
    )


def summary_from_detail(row: ReportRow, detail: ReportDetailV3) -> ReportSummary:
    return ReportSummary(
        id=row.id,
        generated_at=row.generated_at,
        redaction_applied=True,
        incident_count=len(detail.incidents),
        device_count=_report_device_count(detail),
        network_count=_report_network_count(detail),
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
