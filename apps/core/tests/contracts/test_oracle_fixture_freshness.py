"""Canonical oracle fixture freshness and determinism (sole generation owner)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from zigbeelens.mock.fixtures import BUILDERS
from support.contracts import (  # type: ignore[import-not-found]
    ORACLE_FIXTURE,
    generate_oracle_fixture_text,
    load_oracle_fixture,
    oracle_scenarios,
)

GENERATOR_ROOT = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(GENERATOR_ROOT))
from generate_oracle_mock_fixtures import (  # noqa: E402
    ORACLE_CONTRACT_VERSION,
    build_vocabulary_manifest,
    publish_fixture_text,
    render_fixtures,
    validate_fixture_payload,
)


def test_oracle_fixture_contract_version_and_shape():
    """Cheap shape check — loads checked-in fixture only (no generation)."""
    payload = load_oracle_fixture()
    assert payload["oracle_contract_version"] == ORACLE_CONTRACT_VERSION
    assert payload["vocabulary"] == build_vocabulary_manifest()
    scenarios = oracle_scenarios(payload)
    assert set(scenarios) == set(BUILDERS)
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
        assert type(report["report_version"]) is int
        assert report["report_version"] == 3, scenario_id
        report_by_key = {
            f"{story['network_id']}|{story['ieee_address']}": story
            for story in report["device_stories"]
        }
        for raw_key, report_key in body["report_story_keys"].items():
            assert raw_key in body["device_stories"], (scenario_id, raw_key)
            assert report_key in report_by_key, (scenario_id, report_key)


def test_oracle_fixture_fresh_and_hash_seed_stable(tmp_path: Path):
    """Exactly two complete generations: prove hash-seed stability and freshness."""
    out_a = tmp_path / "oracle-a.json"
    out_b = tmp_path / "oracle-b.json"
    env_a = {**os.environ, "PYTHONHASHSEED": "1"}
    env_b = {**os.environ, "PYTHONHASHSEED": "42"}
    result_a = generate_oracle_fixture_text(output=out_a, env=env_a)
    result_b = generate_oracle_fixture_text(output=out_b, env=env_b)
    assert result_a.returncode == 0, result_a.stderr
    assert result_b.returncode == 0, result_b.stderr
    text_a = out_a.read_text(encoding="utf-8")
    text_b = out_b.read_text(encoding="utf-8")
    assert text_a == text_b
    assert text_a == ORACLE_FIXTURE.read_text(encoding="utf-8")
    assert json.loads(text_a)["oracle_contract_version"] == ORACLE_CONTRACT_VERSION


def _minimal_valid_payload() -> dict:
    vocabulary = build_vocabulary_manifest()
    return {
        "oracle_contract_version": ORACLE_CONTRACT_VERSION,
        "vocabulary": vocabulary,
        "scenarios": {
            next(iter(sorted(BUILDERS))): {
                "dashboard": {},
                "devices": [],
                "networks": [],
                "incidents": [],
                "report": {"report_version": 3, "device_stories": []},
                "device_stories": {},
                "report_story_keys": {},
                "representative_subjects": [],
            }
        },
    }


def test_publication_fails_when_builder_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    destination = tmp_path / "oracleMockScenarios.json"
    destination.write_text("KEEP\n", encoding="utf-8")

    def _boom() -> dict:
        raise RuntimeError("builder failed")

    monkeypatch.setattr(
        "generate_oracle_mock_fixtures.build_fixtures",
        _boom,
    )
    from generate_oracle_mock_fixtures import main

    assert main(["--output", str(destination)]) == 1
    assert destination.read_text(encoding="utf-8") == "KEEP\n"


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda p: p.__setitem__("scenarios", {}), "empty scenarios"),
        (
            lambda p: p["scenarios"][next(iter(p["scenarios"]))].__setitem__(
                "report", None
            ),
            "null report",
        ),
        (
            lambda p: p["scenarios"][next(iter(p["scenarios"]))]["report"].__setitem__(
                "report_version", 2
            ),
            "report_version!=3",
        ),
        (
            lambda p: p["vocabulary"].__setitem__("headline_codes", ["not-a-real-code"]),
            "vocabulary",
        ),
    ],
)
def test_publication_fails_closed_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate,
    match: str,
):
    destination = tmp_path / "oracleMockScenarios.json"
    destination.write_text("KEEP\n", encoding="utf-8")
    payload = _minimal_valid_payload()
    # Expand scenarios to full BUILDERS set for ownership check unless testing empty.
    if match != "empty scenarios":
        base = payload["scenarios"][next(iter(payload["scenarios"]))]
        payload["scenarios"] = {sid: json.loads(json.dumps(base)) for sid in BUILDERS}
        mutate(payload)
    else:
        mutate(payload)

    # Validator-specific unit check (non-publication).
    with pytest.raises(ValueError, match=match):
        validate_fixture_payload(payload)

    monkeypatch.setattr(
        "generate_oracle_mock_fixtures.build_fixtures",
        lambda: payload,
    )
    from generate_oracle_mock_fixtures import main

    assert main(["--output", str(destination)]) == 1
    assert destination.read_text(encoding="utf-8") == "KEEP\n"
    assert not destination.with_suffix(destination.suffix + ".tmp").exists()


def test_publish_only_after_validation(tmp_path: Path):
    destination = tmp_path / "oracleMockScenarios.json"
    destination.write_text("KEEP\n", encoding="utf-8")
    payload = _minimal_valid_payload()
    base = payload["scenarios"][next(iter(payload["scenarios"]))]
    payload["scenarios"] = {sid: json.loads(json.dumps(base)) for sid in BUILDERS}
    validate_fixture_payload(payload)
    text = render_fixtures(payload)
    publish_fixture_text(text, destination)
    assert destination.read_text(encoding="utf-8") == text
