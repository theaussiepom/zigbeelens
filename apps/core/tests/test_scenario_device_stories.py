"""Scenario Device Story fixture authority via canonical build_device_story."""

from __future__ import annotations

import inspect
from dataclasses import replace

from zigbeelens.decisions.device_story import (
    DEVICE_STORY_HEADLINE_CODES,
    HeadlineCode,
    build_device_story,
)
from zigbeelens.decisions.reasons import REASON_CODES, ReasonCode
from zigbeelens.decisions.types import CoverageLabelCode, DecisionPriority, DecisionStatus
from zigbeelens.mock import device_stories as device_stories_mod
from zigbeelens.mock.device_stories import (
    apply_device_story_badges,
    build_device_stories_for_scenario,
    build_device_story_evidence_for_scenario,
    current_issue_evidence,
)
from zigbeelens.mock.fixtures import BUILDERS, NOW, get_scenario
from zigbeelens.schemas import Availability, IncidentStatus
from zigbeelens.services.device_decision_badge import device_decision_badge_from_story


def test_canonical_story_parity_for_every_builtin_scenario_device():
    for scenario_id in BUILDERS:
        raw = BUILDERS[scenario_id]()
        evidence_by_device = build_device_story_evidence_for_scenario(raw)
        finalised = get_scenario(scenario_id)

        assert len(finalised.device_stories) == len(raw.devices)
        for device in raw.devices:
            key = (device.network_id, device.ieee_address)
            evidence = evidence_by_device[key]
            expected_story = build_device_story(evidence, now=NOW)
            assert finalised.device_stories[key] == expected_story

            final_device = next(
                d
                for d in finalised.devices
                if (d.network_id, d.ieee_address) == key
            )
            assert final_device.decision == device_decision_badge_from_story(expected_story)


def test_builtin_scenario_stories_project_exact_badges():
    for scenario_id in BUILDERS:
        data = get_scenario(scenario_id)
        assert data.device_stories
        assert len(data.device_stories) == len(data.devices)
        for device in data.devices:
            key = (device.network_id, device.ieee_address)
            story = data.device_stories[key]
            assert device.decision == device_decision_badge_from_story(story)
            assert DecisionStatus(story.status)
            assert DecisionPriority(story.priority)
            assert story.headline_code in DEVICE_STORY_HEADLINE_CODES
            for reason in story.reasons:
                assert reason.code in REASON_CODES
            for item in story.coverage:
                assert item.label_code in {member.value for member in CoverageLabelCode}


def test_apply_device_story_badges_is_story_projection_only():
    raw = BUILDERS["all_ok_single_network"]()
    stories = build_device_stories_for_scenario(raw, now=NOW)
    projected = apply_device_story_badges(raw.devices, stories)
    for device in projected:
        story = stories[(device.network_id, device.ieee_address)]
        assert device.decision == device_decision_badge_from_story(story)


def test_current_issue_without_topology_gap_is_worth_reviewing():
    data = get_scenario("single_device_unavailable")
    offline = next(d for d in data.devices if d.availability == Availability.offline)
    story = data.device_stories[(offline.network_id, offline.ieee_address)]
    assert story.status == DecisionStatus.worth_reviewing
    assert story.priority == DecisionPriority.high
    assert story.headline_code == HeadlineCode.current_issue_present


def test_current_issue_with_topology_gap_is_review_first():
    raw = BUILDERS["single_device_unavailable"]()
    offline = next(d for d in raw.devices if d.availability == Availability.offline)
    evidence = current_issue_evidence(offline, topology_gap=True)
    story = build_device_story(evidence, now=NOW)
    assert story.status == DecisionStatus.review_first
    assert story.priority == DecisionPriority.high
    assert story.headline_code == HeadlineCode.current_issue_present


def test_stale_scenarios_resolve_watch_low_stale_last_seen():
    for scenario_id in ("stale_battery_devices", "stale_reporting_cluster"):
        data = get_scenario(scenario_id)
        for device in data.devices:
            story = data.device_stories[(device.network_id, device.ieee_address)]
            assert story.status == DecisionStatus.watch
            assert story.priority == DecisionPriority.low
            assert story.headline_code == HeadlineCode.stale_last_seen
            assert any(r.code == ReasonCode.last_seen_stale for r in story.reasons)


def test_low_battery_uses_actual_fixture_battery_percent():
    data = get_scenario("low_battery_cluster")
    for device in data.devices:
        story = data.device_stories[(device.network_id, device.ieee_address)]
        assert device.battery is not None
        assert device.battery <= 20
        assert story.status == DecisionStatus.watch
        assert story.priority == DecisionPriority.low
        assert story.headline_code == HeadlineCode.low_battery
        battery_reasons = [r for r in story.reasons if r.code == ReasonCode.battery_low]
        assert battery_reasons
        assert battery_reasons[0].params["battery_percent"] == device.battery


def test_weak_link_absolute_lqi_does_not_invent_declining_trend():
    data = get_scenario("weak_link_devices")
    for device in data.devices:
        story = data.device_stories[(device.network_id, device.ieee_address)]
        reason_codes = {r.code for r in story.reasons}
        assert ReasonCode.reported_lqi_declining not in reason_codes
        assert story.headline_code != HeadlineCode.reported_link_quality_changed




def test_scenario_related_unresolved_incident_ids_follow_affected_devices_only():
    data = get_scenario("single_device_unavailable")
    affected = data.incidents[0].affected_devices[0]
    affected_key = (affected.network_id, affected.ieee_address)

    story = data.device_stories[affected_key]
    assert data.incidents[0].id in story.related_unresolved_incident_ids

    unaffected_stories = [
        story
        for key, story in data.device_stories.items()
        if key != affected_key
    ]
    assert unaffected_stories
    assert all(not story.related_unresolved_incident_ids for story in unaffected_stories)


def test_scenario_watching_incidents_are_related_but_resolved_are_excluded():
    raw = BUILDERS["single_device_unavailable"]()
    incident = raw.incidents[0]
    watching = incident.model_copy(
        update={"id": "inc-watching", "status": IncidentStatus.watching}
    )
    resolved = incident.model_copy(
        update={"id": "inc-resolved", "status": IncidentStatus.resolved}
    )
    data = replace(raw, incidents=[watching, resolved])
    affected = incident.affected_devices[0]
    key = (affected.network_id, affected.ieee_address)

    evidence = build_device_story_evidence_for_scenario(data)[key]
    assert evidence.related_unresolved_incident_ids == ["inc-watching"]


def test_scenario_related_incident_ids_do_not_change_outcome():
    raw = BUILDERS["single_device_unavailable"]()
    device = raw.devices[0]
    evidence = build_device_story_evidence_for_scenario(raw)[
        (device.network_id, device.ieee_address)
    ]
    base_evidence = evidence.model_copy(update={"related_unresolved_incident_ids": []})
    with_related = evidence.model_copy(
        update={"related_unresolved_incident_ids": ["inc-context-only"]}
    )

    base_story = build_device_story(base_evidence, now=NOW)
    related_story = build_device_story(with_related, now=NOW)
    assert related_story.status == base_story.status
    assert related_story.priority == base_story.priority
    assert related_story.headline_code == base_story.headline_code
    assert related_story.reasons == base_story.reasons

def test_scenario_availability_coverage_uses_enum_values():
    data = get_scenario("single_device_unavailable")
    labels_by_availability = {}
    for device in data.devices:
        story = data.device_stories[(device.network_id, device.ieee_address)]
        availability_label = next(
            item.label_code for item in story.coverage if str(item.dimension) == "availability"
        )
        labels_by_availability[str(device.availability.value)] = availability_label
    assert labels_by_availability["offline"] == CoverageLabelCode.availability_available

    data = get_scenario("healthy")
    device = data.devices[0]
    story = data.device_stories[(device.network_id, device.ieee_address)]
    availability_label = next(
        item.label_code for item in story.coverage if str(item.dimension) == "availability"
    )
    assert availability_label == CoverageLabelCode.availability_available


    bridge = get_scenario("bridge_offline")
    device = bridge.devices[0]
    story = bridge.device_stories[(device.network_id, device.ieee_address)]
    availability_label = next(
        item.label_code for item in story.coverage if str(item.dimension) == "availability"
    )
    assert availability_label == CoverageLabelCode.availability_status_unknown


def test_interview_failures_do_not_fabricate_ha_coverage():
    data = get_scenario("interview_failures")
    assert len(data.devices) == 1
    device = data.devices[0]
    story = data.device_stories[(device.network_id, device.ieee_address)]
    reason_codes = {r.code for r in story.reasons}
    coverage_codes = {item.label_code for item in story.coverage}
    assert ReasonCode.ha_areas_not_linked in reason_codes
    assert CoverageLabelCode.ha_areas_not_linked in coverage_codes
    assert story.status == DecisionStatus.informational


def test_bridge_offline_does_not_claim_availability_tracking_is_off():
    from zigbeelens.topology.device_compare import COVERAGE_UNKNOWN

    raw = BUILDERS["bridge_offline"]()
    evidence_by_device = build_device_story_evidence_for_scenario(raw)
    data = get_scenario("bridge_offline")
    assert data.devices

    for device in data.devices:
        key = (device.network_id, device.ieee_address)
        evidence = evidence_by_device[key]
        assert evidence.availability_tracking_enabled is True
        assert evidence.latest_availability_coverage == COVERAGE_UNKNOWN

        story = data.device_stories[key]
        reason_codes = {reason.code for reason in story.reasons}
        coverage_codes = {item.label_code for item in story.coverage}

        assert ReasonCode.availability_tracking_off not in reason_codes
        assert CoverageLabelCode.availability_tracking_off not in coverage_codes
        assert ReasonCode.availability_status_unknown in reason_codes
        assert CoverageLabelCode.availability_status_unknown in coverage_codes

        expected = build_device_story(evidence, now=NOW)
        assert story == expected


def test_coverage_honesty_across_builtin_scenarios():
    for scenario_id in BUILDERS:
        raw = BUILDERS[scenario_id]()
        evidence_by_device = build_device_story_evidence_for_scenario(raw)
        data = get_scenario(scenario_id)

        for device in data.devices:
            key = (device.network_id, device.ieee_address)
            story = data.device_stories[key]
            evidence = evidence_by_device[key]
            coverage_codes = {item.label_code for item in story.coverage}
            reason_codes = {r.code for r in story.reasons}
            limitation_codes = {item.code for item in story.limitations}

            assert CoverageLabelCode.battery_history_available not in coverage_codes

            if evidence.latest_snapshot_id is None:
                assert "route_hints_not_live_routing" not in limitation_codes
                assert ReasonCode.route_hints_unavailable not in reason_codes

            if evidence.network_has_usable_ha_areas and evidence.ha_area is None:
                assert ReasonCode.ha_areas_not_linked in reason_codes
                assert CoverageLabelCode.ha_areas_not_linked in coverage_codes

            for item in story.coverage:
                assert item.label_code in {member.value for member in CoverageLabelCode}

    unknown = get_scenario("unknown_insufficient_data")
    story = next(iter(unknown.device_stories.values()))
    reason_codes = {r.code for r in story.reasons}
    assert ReasonCode.availability_tracking_off in reason_codes
    assert story.status == DecisionStatus.improve_data_coverage


def test_mock_device_story_module_does_not_use_legacy_health_helpers():
    source = inspect.getsource(device_stories_mod)
    forbidden = (
        "health_result_to_device_health",
        "lens_presentation_for_health",
        "DeviceHealthPrimary",
        "enrich_device_summary",
        "lens_bucket",
        "_resolve_story_outcome",
        "DecisionStatus.",
        "HeadlineCode.",
    )
    for name in forbidden:
        assert name not in source, name


def test_mock_module_does_not_declare_final_story_outcomes():
    source = inspect.getsource(device_stories_mod)
    assert "status=DecisionStatus" not in source
    assert "priority=DecisionPriority" not in source
    assert "headline_code=" not in source or "build_device_story" in source
    assert "def no_notable_story" not in source
    assert "def current_issue_story" not in source
    assert "def weak_link_story" not in source
    # Evidence helpers may exist; final outcome templates must not.
    assert "device_story_evidence(" in source
    assert "build_device_story(" in source
