"""Scenario Device Story evidence fixtures (Phase 5B).

Fixtures declare DeviceStoryEvidence only. Canonical build_device_story()
resolves status, priority, and headline. Do not derive outcomes from legacy
health or lens fields.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from zigbeelens.decisions.device_coverage import (
    build_device_coverage,
    build_device_coverage_evidence,
)
from zigbeelens.decisions.device_story import (
    DeviceStory,
    DeviceStoryEvidence,
    DeviceStoryModelPatternContext,
    build_device_story,
)
from zigbeelens.decisions.lqi_trend import LqiTrend
from zigbeelens.decisions.reporting_rhythm import ReportingRhythm
from zigbeelens.decisions.topology_facts import TopologyFactCode
from zigbeelens.decisions.types import EvidenceFact
from zigbeelens.schemas import Availability, DeviceSummary, Incident, IncidentStatus
from zigbeelens.services.device_decision_badge import device_decision_badge_from_story
from zigbeelens.topology.device_compare import COVERAGE_UNKNOWN

if TYPE_CHECKING:
    from zigbeelens.mock.fixtures import ScenarioData

_CURRENT_ISSUE_SCENARIOS = frozenset(
    {
        "single_device_unavailable",
        "four_devices_same_room_unavailable",
        "one_network_incident_other_network_ok",
        "router_risk_candidate",
    }
)

_STALE_SCENARIOS = frozenset(
    {
        "stale_battery_devices",
        "stale_reporting_cluster",
    }
)


def _parse_device_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed



def _availability_value(value: Availability | str | None) -> str | None:
    if isinstance(value, Availability):
        return value.value
    if isinstance(value, str):
        return value
    return None

def device_story_evidence(
    device: DeviceSummary,
    *,
    has_current_issue: bool = False,
    availability_tracking_enabled: bool = True,
    latest_availability_coverage: str | None = None,
    topology_facts: list[EvidenceFact] | None = None,
    recent_missing_link_count: int = 0,
    last_known_link_count: int = 0,
    route_hints_available: bool = False,
    latest_snapshot_id: str | None = None,
    latest_snapshot_captured_at: datetime | None = None,
    network_has_usable_ha_areas: bool = True,
    reporting_rhythm: ReportingRhythm | None = None,
    lqi_trend: LqiTrend | None = None,
    model_pattern: DeviceStoryModelPatternContext | None = None,
    related_unresolved_incident_ids: list[str] | None = None,
) -> DeviceStoryEvidence:
    """Build DeviceStoryEvidence from scenario device facts plus explicit overrides."""
    availability = _availability_value(device.availability)
    coverage = build_device_coverage(
        build_device_coverage_evidence(
            device_row=device,
            tracking_enabled=availability_tracking_enabled,
            device_snapshots=[
                {
                    "battery": device.battery,
                    "linkquality": device.linkquality,
                    "captured_at": device.last_payload_at or device.last_seen,
                }
            ],
            availability_changes=[{"to_state": availability}]
            if latest_availability_coverage is not None
            else [],
            topology_observed_snapshot_count=1 if latest_snapshot_id else 0,
            topology_snapshot_window_count=1 if latest_snapshot_id else 0,
            ha_enrichment={"area_name": device.ha_area} if device.ha_area else None,
        )
    )

    return DeviceStoryEvidence(
        network_id=device.network_id,
        device_ieee=device.ieee_address,
        friendly_name=device.friendly_name,
        availability=availability,
        last_seen=_parse_device_ts(device.last_seen),
        last_payload_at=_parse_device_ts(device.last_payload_at),
        linkquality=device.linkquality,
        battery=device.battery,
        has_current_issue=has_current_issue,
        related_unresolved_incident_ids=list(related_unresolved_incident_ids or []),
        availability_tracking_enabled=availability_tracking_enabled,
        latest_availability_coverage=latest_availability_coverage,
        topology_facts=list(topology_facts or []),
        recent_missing_link_count=recent_missing_link_count,
        last_known_link_count=last_known_link_count,
        route_hints_available=route_hints_available,
        latest_snapshot_id=latest_snapshot_id,
        latest_snapshot_captured_at=latest_snapshot_captured_at,
        ha_area=device.ha_area,
        network_has_usable_ha_areas=network_has_usable_ha_areas,
        reporting_rhythm=reporting_rhythm,
        lqi_trend=lqi_trend,
        model_pattern=model_pattern,
        coverage=coverage,
    )


def current_issue_evidence(
    device: DeviceSummary,
    *,
    topology_gap: bool = False,
    **overrides: Any,
) -> DeviceStoryEvidence:
    """Offline/current-issue scenario evidence. Topology gap is never implied."""
    gap_kwargs: dict[str, Any] = {}
    if topology_gap:
        gap_kwargs = {
            "recent_missing_link_count": overrides.pop("recent_missing_link_count", 1),
            "last_known_link_count": overrides.pop("last_known_link_count", 1),
            "topology_facts": overrides.pop(
                "topology_facts",
                [
                    EvidenceFact(code=TopologyFactCode.device_no_latest_links, params={}),
                    EvidenceFact(
                        code=TopologyFactCode.device_has_selected_snapshot_links,
                        params={},
                    ),
                ],
            ),
        }
    return device_story_evidence(
        device,
        has_current_issue=True,
        **gap_kwargs,
        **overrides,
    )


def tracking_off_evidence(device: DeviceSummary, **overrides: Any) -> DeviceStoryEvidence:
    return device_story_evidence(
        device,
        availability_tracking_enabled=False,
        latest_availability_coverage=overrides.pop(
            "latest_availability_coverage", COVERAGE_UNKNOWN
        ),
        **overrides,
    )


def apply_device_story_badges(
    devices: list[DeviceSummary],
    stories: dict[tuple[str, str], DeviceStory],
) -> list[DeviceSummary]:
    """Project DeviceDecisionBadge onto each device from its canonical story."""
    updated: list[DeviceSummary] = []
    for device in devices:
        key = (device.network_id, device.ieee_address)
        story = stories.get(key)
        if story is None:
            updated.append(device)
            continue
        updated.append(
            device.model_copy(
                update={"decision": device_decision_badge_from_story(story)}
            )
        )
    return updated


def apply_incident_device_story_badges(
    incidents: list[Incident],
    stories: dict[tuple[str, str], DeviceStory],
) -> list[Incident]:
    """Project DeviceDecisionBadge onto incident affected-device refs from stories."""
    updated: list[Incident] = []
    for incident in incidents:
        new_affected = []
        for ref in incident.affected_devices:
            key = (ref.network_id, ref.ieee_address)
            story = stories.get(key)
            decision = (
                device_decision_badge_from_story(story) if story is not None else None
            )
            new_affected.append(ref.model_copy(update={"decision": decision}))
        updated.append(
            incident.model_copy(update={"affected_devices": new_affected})
        )
    return updated



def _related_incident_ids_by_device(
    incidents: list[Incident],
) -> dict[tuple[str, str], list[str]]:
    related: dict[tuple[str, str], list[str]] = {}
    unresolved = {IncidentStatus.open, IncidentStatus.watching}
    for incident in incidents:
        if incident.status not in unresolved:
            continue
        for ref in incident.affected_devices:
            key = (ref.network_id, ref.ieee_address)
            related.setdefault(key, []).append(incident.id)
    return related

def build_device_story_evidence_for_scenario(
    data: ScenarioData,
) -> dict[tuple[str, str], DeviceStoryEvidence]:
    """Map scenario devices to explicit DeviceStoryEvidence (facts only)."""
    evidence_by_device: dict[tuple[str, str], DeviceStoryEvidence] = {}
    sid = data.id
    related_incident_ids_by_device = _related_incident_ids_by_device(data.incidents)

    def with_related(
        device: DeviceSummary, **kwargs: Any
    ) -> DeviceStoryEvidence:
        key = (device.network_id, device.ieee_address)
        return device_story_evidence(
            device,
            related_unresolved_incident_ids=related_incident_ids_by_device.get(key, []),
            **kwargs,
        )

    for device in data.devices:
        key = (device.network_id, device.ieee_address)

        if sid in _CURRENT_ISSUE_SCENARIOS:
            evidence_by_device[key] = with_related(
                device,
                has_current_issue=device.availability == Availability.offline,
            )
            continue

        if sid in _STALE_SCENARIOS:
            evidence_by_device[key] = with_related(device)
            continue

        if sid == "low_battery_cluster":
            evidence_by_device[key] = with_related(device)
            continue

        if sid == "weak_link_devices":
            # Preserve factual linkquality; do not invent LQI trend evidence.
            evidence_by_device[key] = with_related(device)
            continue

        if sid == "interview_failures":
            # interview_state is Detail metadata, not Device Story evidence.
            evidence_by_device[key] = with_related(device)
            continue

        if sid == "unknown_insufficient_data":
            evidence_by_device[key] = tracking_off_evidence(
                device,
                related_unresolved_incident_ids=related_incident_ids_by_device.get(key, []),
            )
            continue

        if sid == "bridge_offline":
            # Bridge outage leaves availability status unknown; tracking itself
            # is not configured off.
            evidence_by_device[key] = with_related(
                device,
                latest_availability_coverage=COVERAGE_UNKNOWN,
            )
            continue

        evidence_by_device[key] = with_related(device)

    return evidence_by_device


def build_device_stories_for_scenario(
    data: ScenarioData,
    *,
    now: datetime,
) -> dict[tuple[str, str], DeviceStory]:
    """Resolve scenario Device Stories through the canonical decision engine."""
    evidence_by_device = build_device_story_evidence_for_scenario(data)
    return {
        key: build_device_story(evidence, now=now)
        for key, evidence in evidence_by_device.items()
    }


def finalize_scenario_device_stories(
    data: ScenarioData,
    *,
    now: datetime,
) -> ScenarioData:
    """Attach canonical Device Stories and project decision badges onto devices."""
    stories = build_device_stories_for_scenario(data, now=now)
    devices = apply_device_story_badges(data.devices, stories)
    incidents = apply_incident_device_story_badges(data.incidents, stories)
    return replace(
        data,
        devices=devices,
        device_stories=stories,
        incidents=incidents,
    )
