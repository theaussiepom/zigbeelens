"""Explicit coded Device Story fixtures for scenario/mock mode (Phase 5B).

Stories are declared by fixture authors using stable Decision Engine codes.
Presenters map those codes to user-facing copy. Do not derive status from
legacy health or lens fields.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from zigbeelens.decisions.coverage import (
    availability_tracking_off,
    battery_history_available,
    last_seen_available,
    last_seen_unknown,
)
from zigbeelens.decisions.device_story import (
    DEVICE_STORY_HEADLINE_CODES,
    CheckCode,
    DeviceStory,
    HeadlineCode,
    LimitationCode,
)
from zigbeelens.decisions.reasons import ReasonCode
from zigbeelens.decisions.types import (
    CoverageDimension,
    CoverageLabelCode,
    CoverageState,
    DataCoverage,
    DecisionLimitation,
    DecisionPriority,
    DecisionReason,
    DecisionStatus,
    EvidenceReference,
    SuggestedCheck,
)
from zigbeelens.schemas import Availability, DeviceSummary
from zigbeelens.services.device_decision_badge import device_decision_badge_from_story

if TYPE_CHECKING:
    from zigbeelens.mock.fixtures import ScenarioData


def device_story(
    ieee: str,
    *,
    status: DecisionStatus,
    priority: DecisionPriority,
    headline_code: HeadlineCode,
    reasons: list[DecisionReason] | None = None,
    evidence: list[EvidenceReference] | None = None,
    limitations: list[DecisionLimitation] | None = None,
    suggested_checks: list[SuggestedCheck] | None = None,
    coverage: list[DataCoverage] | None = None,
) -> DeviceStory:
    """Build one coded Device Story for a scenario fixture device."""
    code = str(headline_code)
    if code not in DEVICE_STORY_HEADLINE_CODES:
        raise ValueError(f"Unknown Device Story headline code: {code}")
    return DeviceStory(
        subject_type="device",
        subject_id=ieee,
        status=status,
        priority=priority,
        headline_code=code,
        reasons=list(reasons or []),
        evidence=list(evidence or []),
        limitations=list(limitations or []),
        suggested_checks=list(suggested_checks or []),
        coverage=list(coverage or []),
        timeline=[],
    )


def no_notable_story(ieee: str) -> DeviceStory:
    return device_story(
        ieee,
        status=DecisionStatus.no_notable_change,
        priority=DecisionPriority.none,
        headline_code=HeadlineCode.no_notable_signals,
        limitations=[
            DecisionLimitation(code=LimitationCode.route_hints_not_live_routing, params={})
        ],
        coverage=[last_seen_available(), battery_history_available()],
    )


def current_issue_story(ieee: str) -> DeviceStory:
    return device_story(
        ieee,
        status=DecisionStatus.review_first,
        priority=DecisionPriority.high,
        headline_code=HeadlineCode.current_issue_present,
        reasons=[DecisionReason(code=ReasonCode.current_issue_present, params={})],
        evidence=[
            EvidenceReference(
                source="device_current_state",
                id=ieee,
                captured_at=None,
                label="availability",
            )
        ],
        limitations=[
            DecisionLimitation(
                code=LimitationCode.availability_limits_interpretation, params={}
            )
        ],
        suggested_checks=[
            SuggestedCheck(code=CheckCode.confirm_powered, params={}),
            SuggestedCheck(code=CheckCode.confirm_reporting_in_z2m, params={}),
        ],
        coverage=[last_seen_available()],
    )


def coverage_gap_story(ieee: str) -> DeviceStory:
    return device_story(
        ieee,
        status=DecisionStatus.improve_data_coverage,
        priority=DecisionPriority.medium,
        headline_code=HeadlineCode.data_coverage_gaps,
        reasons=[
            DecisionReason(code=ReasonCode.availability_tracking_off, params={}),
            DecisionReason(code=ReasonCode.availability_status_unknown, params={}),
        ],
        limitations=[
            DecisionLimitation(
                code=LimitationCode.availability_limits_interpretation, params={}
            )
        ],
        suggested_checks=[
            SuggestedCheck(code=CheckCode.enable_availability_reporting, params={})
        ],
        coverage=[availability_tracking_off(), last_seen_unknown()],
    )


def stale_story(ieee: str) -> DeviceStory:
    return device_story(
        ieee,
        status=DecisionStatus.watch,
        priority=DecisionPriority.medium,
        headline_code=HeadlineCode.stale_last_seen,
        reasons=[DecisionReason(code=ReasonCode.last_seen_stale, params={})],
        suggested_checks=[
            SuggestedCheck(code=CheckCode.confirm_reporting_in_z2m, params={})
        ],
        coverage=[last_seen_available()],
    )


def low_battery_story(ieee: str) -> DeviceStory:
    return device_story(
        ieee,
        status=DecisionStatus.watch,
        priority=DecisionPriority.medium,
        headline_code=HeadlineCode.low_battery,
        reasons=[DecisionReason(code=ReasonCode.battery_low, params={"battery": 12})],
        suggested_checks=[
            SuggestedCheck(code=CheckCode.check_battery_level, params={})
        ],
        coverage=[battery_history_available()],
    )


def weak_link_story(ieee: str) -> DeviceStory:
    return device_story(
        ieee,
        status=DecisionStatus.watch,
        priority=DecisionPriority.low,
        headline_code=HeadlineCode.reported_link_quality_changed,
        reasons=[DecisionReason(code=ReasonCode.reported_lqi_low, params={"linkquality": 28})],
        limitations=[
            DecisionLimitation(
                code=LimitationCode.reported_lqi_not_path_failure, params={}
            )
        ],
        coverage=[
            DataCoverage(
                dimension=CoverageDimension.linkquality,
                state=CoverageState.available,
                label_code=CoverageLabelCode.lqi_history_available,
                params={},
            )
        ],
    )


def worth_reviewing_story(ieee: str) -> DeviceStory:
    return device_story(
        ieee,
        status=DecisionStatus.worth_reviewing,
        priority=DecisionPriority.high,
        headline_code=HeadlineCode.current_issue_present,
        reasons=[DecisionReason(code=ReasonCode.current_issue_present, params={})],
        suggested_checks=[
            SuggestedCheck(code=CheckCode.confirm_powered, params={}),
            SuggestedCheck(code=CheckCode.confirm_reporting_in_z2m, params={}),
        ],
        coverage=[last_seen_available()],
    )


def informational_story(ieee: str) -> DeviceStory:
    return device_story(
        ieee,
        status=DecisionStatus.informational,
        priority=DecisionPriority.low,
        headline_code=HeadlineCode.data_coverage_gaps,
        reasons=[DecisionReason(code=ReasonCode.ha_areas_not_linked, params={})],
        coverage=[
            DataCoverage(
                dimension=CoverageDimension.ha_enrichment,
                state=CoverageState.not_configured,
                label_code=CoverageLabelCode.ha_areas_not_linked,
                params={},
            )
        ],
    )


def apply_device_story_badges(
    devices: list[DeviceSummary],
    stories: dict[tuple[str, str], DeviceStory],
) -> list[DeviceSummary]:
    """Project DeviceDecisionBadge onto each device from its explicit story."""
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


def _all_no_notable(devices: list[DeviceSummary]) -> dict[tuple[str, str], DeviceStory]:
    return {
        (d.network_id, d.ieee_address): no_notable_story(d.ieee_address)
        for d in devices
    }


def _stories_by_availability(
    devices: list[DeviceSummary],
    *,
    offline_story: DeviceStory | None = None,
) -> dict[tuple[str, str], DeviceStory]:
    """Offline devices get current-issue; others no-notable (explicit fixture choice)."""
    stories: dict[tuple[str, str], DeviceStory] = {}
    for d in devices:
        if d.availability == Availability.offline:
            stories[(d.network_id, d.ieee_address)] = (
                offline_story.model_copy(update={"subject_id": d.ieee_address})
                if offline_story is not None
                else current_issue_story(d.ieee_address)
            )
        else:
            stories[(d.network_id, d.ieee_address)] = no_notable_story(d.ieee_address)
    return stories


def build_device_stories_for_scenario(data: ScenarioData) -> dict[tuple[str, str], DeviceStory]:
    """Declare coded stories for each built-in scenario by scenario id."""
    devices = data.devices
    sid = data.id

    if sid in {"all_ok_single_network", "all_ok_multi_network"}:
        return _all_no_notable(devices)

    if sid in {
        "single_device_unavailable",
        "four_devices_same_room_unavailable",
        "one_network_incident_other_network_ok",
        "bridge_offline",
    }:
        return _stories_by_availability(devices)

    if sid == "router_risk_candidate":
        stories: dict[tuple[str, str], DeviceStory] = {}
        for d in devices:
            key = (d.network_id, d.ieee_address)
            if d.availability == Availability.offline:
                stories[key] = current_issue_story(d.ieee_address)
            elif "router" in d.friendly_name.lower() or d.device_type.value == "Router":
                stories[key] = worth_reviewing_story(d.ieee_address)
            else:
                stories[key] = no_notable_story(d.ieee_address)
        return stories

    if sid in {"stale_battery_devices", "stale_reporting_cluster"}:
        return {
            (d.network_id, d.ieee_address): stale_story(d.ieee_address) for d in devices
        }

    if sid == "low_battery_cluster":
        return {
            (d.network_id, d.ieee_address): (
                low_battery_story(d.ieee_address)
                if d.battery is not None and d.battery <= 20
                else no_notable_story(d.ieee_address)
            )
            for d in devices
        }

    if sid == "interview_failures":
        return {
            (d.network_id, d.ieee_address): (
                informational_story(d.ieee_address)
                if d.ieee_address == "0x00158d0009a1b2c3"
                else no_notable_story(d.ieee_address)
            )
            for d in devices
        }

    if sid == "unknown_insufficient_data":
        return {
            (d.network_id, d.ieee_address): coverage_gap_story(d.ieee_address)
            for d in devices
        }

    if sid == "multiple_networks_unstable":
        return {
            (d.network_id, d.ieee_address): worth_reviewing_story(d.ieee_address)
            for d in devices
        }

    if sid == "weak_link_devices":
        return {
            (d.network_id, d.ieee_address): (
                weak_link_story(d.ieee_address)
                if d.linkquality is not None and d.linkquality < 50
                else no_notable_story(d.ieee_address)
            )
            for d in devices
        }

    return _all_no_notable(devices)


def finalize_scenario_device_stories(data: ScenarioData) -> ScenarioData:
    """Attach explicit Device Stories and project decision badges onto devices."""
    stories = build_device_stories_for_scenario(data)
    devices = apply_device_story_badges(data.devices, stories)
    return replace(data, devices=devices, device_stories=stories)
