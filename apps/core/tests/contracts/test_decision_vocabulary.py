"""Canonical Decision vocabulary inventory — registries are authority."""

from __future__ import annotations

from zigbeelens.decisions.device_story import (
    DEVICE_STORY_HEADLINE_CODES,
    CheckCode,
    HeadlineCode,
    LimitationCode,
)
from zigbeelens.decisions.reasons import REASON_CODES, ReasonCode
from zigbeelens.decisions.types import (
    CoverageDimension,
    CoverageLabelCode,
    CoverageState,
    DecisionPriority,
    DecisionStatus,
)
from support.contracts import load_oracle_fixture, oracle_scenarios  # type: ignore[import-not-found]


def test_status_and_priority_registries_are_non_empty():
    assert {m.value for m in DecisionStatus}
    assert {m.value for m in DecisionPriority}


def test_code_registries_match_enum_members():
    assert DEVICE_STORY_HEADLINE_CODES == {m.value for m in HeadlineCode}
    assert REASON_CODES == {m.value for m in ReasonCode}
    assert {m.value for m in LimitationCode}
    assert {m.value for m in CheckCode}
    assert {m.value for m in CoverageLabelCode}
    assert {m.value for m in CoverageDimension}
    assert {m.value for m in CoverageState}


def test_oracle_emitted_codes_are_in_registries():
    statuses = {m.value for m in DecisionStatus}
    priorities = {m.value for m in DecisionPriority}
    headlines = {m.value for m in HeadlineCode}
    reasons = {m.value for m in ReasonCode}
    limitations = {m.value for m in LimitationCode}
    checks = {m.value for m in CheckCode}
    labels = {m.value for m in CoverageLabelCode}
    dimensions = {m.value for m in CoverageDimension}
    states = {m.value for m in CoverageState}

    for scenario_id, body in oracle_scenarios(load_oracle_fixture()).items():
        for key, story in body["device_stories"].items():
            assert story["status"] in statuses, (scenario_id, key, story["status"])
            assert story["priority"] in priorities, (scenario_id, key, story["priority"])
            assert story["headline_code"] in headlines, (
                scenario_id,
                key,
                story["headline_code"],
            )
            for reason in story.get("reasons") or []:
                assert reason["code"] in reasons, (scenario_id, key, reason["code"])
            for limitation in story.get("limitations") or []:
                assert limitation["code"] in limitations, (
                    scenario_id,
                    key,
                    limitation["code"],
                )
            for check in story.get("suggested_checks") or []:
                assert check["code"] in checks, (scenario_id, key, check["code"])
            for item in story.get("coverage") or []:
                assert item["dimension"] in dimensions, (scenario_id, key, item)
                assert item["state"] in states, (scenario_id, key, item)
                assert item["label_code"] in labels, (scenario_id, key, item)

        for story in body["report"].get("device_stories") or []:
            assert story["status"] in statuses
            assert story["priority"] in priorities
            assert story["headline_code"] in headlines
