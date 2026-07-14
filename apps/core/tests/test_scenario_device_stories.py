"""Scenario Device Story fixture authority via canonical build_device_story."""

from __future__ import annotations

import inspect

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
from zigbeelens.schemas import Availability
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


def test_interview_failures_do_not_fabricate_ha_coverage():
    data = get_scenario("interview_failures")
    assert len(data.devices) == 1
    device = data.devices[0]
    story = data.device_stories[(device.network_id, device.ieee_address)]
    reason_codes = {r.code for r in story.reasons}
    coverage_codes = {item.label_code for item in story.coverage}
    assert ReasonCode.ha_areas_not_linked not in reason_codes
    assert CoverageLabelCode.ha_areas_not_linked not in coverage_codes
    assert story.status == DecisionStatus.no_notable_change


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
                assert ReasonCode.ha_areas_not_linked not in reason_codes
                assert CoverageLabelCode.ha_areas_not_linked not in coverage_codes

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
