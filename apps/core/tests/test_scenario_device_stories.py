"""Scenario Device Story fixture authority (Phase 5B scenario parity)."""

from __future__ import annotations

import inspect

from zigbeelens.decisions.device_story import DEVICE_STORY_HEADLINE_CODES
from zigbeelens.decisions.reasons import REASON_CODES
from zigbeelens.decisions.types import DecisionPriority, DecisionStatus
from zigbeelens.mock import device_stories as device_stories_mod
from zigbeelens.mock.device_stories import (
    apply_device_story_badges,
    build_device_stories_for_scenario,
)
from zigbeelens.mock.fixtures import BUILDERS, get_scenario
from zigbeelens.services.device_decision_badge import device_decision_badge_from_story


def test_builtin_scenario_stories_project_exact_badges():
    for scenario_id in BUILDERS:
        data = get_scenario(scenario_id)
        assert data.device_stories, f"{scenario_id} missing device stories"
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


def test_scenario_outcome_spread_uses_stable_vocabulary():
    seen: set[str] = set()
    for scenario_id in BUILDERS:
        for story in get_scenario(scenario_id).device_stories.values():
            seen.add(str(story.status))
    for required in {
        "review_first",
        "worth_reviewing",
        "watch",
        "improve_data_coverage",
        "no_notable_change",
        "informational",
    }:
        assert required in seen


def test_apply_device_story_badges_is_story_projection_only():
    data = get_scenario("all_ok_single_network")
    stories = build_device_stories_for_scenario(data)
    projected = apply_device_story_badges(data.devices, stories)
    for device, previous in zip(projected, data.devices, strict=True):
        assert device.decision == previous.decision
        story = stories[(device.network_id, device.ieee_address)]
        assert device.decision == device_decision_badge_from_story(story)


def test_mock_device_story_module_does_not_use_legacy_health_helpers():
    source = inspect.getsource(device_stories_mod)
    forbidden = (
        "health_result_to_device_health",
        "lens_presentation_for_health",
        "DeviceHealthPrimary",
        "enrich_device_summary",
        "lens_bucket",
    )
    for name in forbidden:
        assert name not in source, name
