"""Canonical oracle fixture freshness and determinism (Core-owned)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from support.contracts import (  # type: ignore[import-not-found]
    ORACLE_FIXTURE,
    generate_oracle_fixture_text,
    load_oracle_fixture,
    oracle_scenarios,
)


def test_oracle_fixture_contract_version_and_shape():
    payload = load_oracle_fixture()
    assert payload["oracle_contract_version"] == 1
    scenarios = oracle_scenarios(payload)
    assert sorted(scenarios) == sorted(scenarios.keys())
    for scenario_id, body in scenarios.items():
        for key in (
            "dashboard",
            "devices",
            "networks",
            "incidents",
            "report",
            "device_stories",
            "report_story_keys",
            "representative_subjects",
        ):
            assert key in body, (scenario_id, key)
        report = body["report"]
        assert report is not None, scenario_id
        assert report["report_version"] == 3, scenario_id
        assert isinstance(body["device_stories"], dict)
        assert isinstance(body["report_story_keys"], dict)
        assert isinstance(body["representative_subjects"], list)
        report_by_key = {
            f"{story['network_id']}|{story['ieee_address']}": story
            for story in report["device_stories"]
        }
        for raw_key, report_key in body["report_story_keys"].items():
            assert raw_key in body["device_stories"], (scenario_id, raw_key)
            assert report_key in report_by_key, (scenario_id, report_key)
            api_story = body["device_stories"][raw_key]
            report_story = report_by_key[report_key]
            assert api_story["status"] == report_story["status"]
            assert api_story["priority"] == report_story["priority"]
            assert api_story["headline_code"] == report_story["headline_code"]


def test_oracle_fixture_matches_generation(tmp_path: Path):
    generated = tmp_path / "oracleMockScenarios.json"
    result = generate_oracle_fixture_text(output=generated)
    assert result.returncode == 0, result.stderr
    assert generated.read_text(encoding="utf-8") == ORACLE_FIXTURE.read_text(
        encoding="utf-8"
    )


def test_oracle_fixture_check_mode_passes():
    result = generate_oracle_fixture_text(check=True)
    assert result.returncode == 0, result.stderr


def test_oracle_generation_is_byte_stable_across_hash_seeds(tmp_path: Path):
    outputs: list[str] = []
    for seed in ("0", "1", "42"):
        out = tmp_path / f"oracle-{seed}.json"
        env = {**os.environ, "PYTHONHASHSEED": seed}
        result = generate_oracle_fixture_text(output=out, env=env)
        assert result.returncode == 0, result.stderr
        outputs.append(out.read_text(encoding="utf-8"))
    assert outputs[0] == outputs[1] == outputs[2]
    assert json.loads(outputs[0])["oracle_contract_version"] == 1
