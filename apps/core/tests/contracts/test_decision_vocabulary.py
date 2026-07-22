"""Canonical Decision vocabulary — Core registries via oracle vocabulary manifest."""

from __future__ import annotations

import sys
from pathlib import Path

from zigbeelens.decisions.device_story import (
    DEVICE_STORY_HEADLINE_CODES,
    CheckCode,
    LimitationCode,
)
from zigbeelens.decisions.reasons import REASON_CODES
from zigbeelens.decisions.types import (
    CoverageDimension,
    CoverageLabelCode,
    CoverageState,
    DecisionPriority,
    DecisionStatus,
)
from support.contracts import load_oracle_fixture, oracle_scenarios  # type: ignore[import-not-found]

GENERATOR_ROOT = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(GENERATOR_ROOT))
from generate_oracle_mock_fixtures import build_vocabulary_manifest  # noqa: E402


def test_vocabulary_manifest_equals_core_registries():
    expected = {
        "decision_statuses": sorted(m.value for m in DecisionStatus),
        "decision_priorities": sorted(m.value for m in DecisionPriority),
        "headline_codes": sorted(DEVICE_STORY_HEADLINE_CODES),
        "reason_codes": sorted(REASON_CODES),
        "limitation_codes": sorted(m.value for m in LimitationCode),
        "suggested_check_codes": sorted(m.value for m in CheckCode),
        "coverage_dimensions": sorted(m.value for m in CoverageDimension),
        "coverage_states": sorted(m.value for m in CoverageState),
        "coverage_label_codes": sorted(m.value for m in CoverageLabelCode),
    }
    assert build_vocabulary_manifest() == expected
    payload = load_oracle_fixture()
    assert payload["vocabulary"] == expected


def test_oracle_emitted_codes_are_subsets_of_manifest():
    payload = load_oracle_fixture()
    vocab = payload["vocabulary"]
    for scenario_id, body in oracle_scenarios(payload).items():
        for key, story in body["device_stories"].items():
            assert story["status"] in vocab["decision_statuses"], (scenario_id, key)
            assert story["priority"] in vocab["decision_priorities"], (scenario_id, key)
            assert story["headline_code"] in vocab["headline_codes"], (scenario_id, key)
            for reason in story.get("reasons") or []:
                assert reason["code"] in vocab["reason_codes"], (scenario_id, key)
            for limitation in story.get("limitations") or []:
                assert limitation["code"] in vocab["limitation_codes"], (
                    scenario_id,
                    key,
                )
            for check in story.get("suggested_checks") or []:
                assert check["code"] in vocab["suggested_check_codes"], (
                    scenario_id,
                    key,
                )
            for item in story.get("coverage") or []:
                assert item["dimension"] in vocab["coverage_dimensions"]
                assert item["state"] in vocab["coverage_states"]
                assert item["label_code"] in vocab["coverage_label_codes"]
