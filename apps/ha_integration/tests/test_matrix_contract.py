"""Contract tests for the exact Home Assistant compatibility matrix."""

from __future__ import annotations

import json
import re
from pathlib import Path

INTEGRATION_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_MATRIX = {
    "reviewed_on": "2026-07-23",
    "lanes": [
        {
            "name": "minimum",
            "homeassistant": "2025.1.0",
            "python": "3.12",
            "requirements": "requirements-test-minimum.txt",
        },
        {
            "name": "current",
            "homeassistant": "2026.7.3",
            "python": "3.14",
            "requirements": "requirements-test-current.txt",
        },
    ],
}

EXPECTED_REQUIRED_SCHEDULER_TESTS = [
    "test_enrichment_scheduler_runtime.py::"
    "test_default_debounce_registry_event_runs_on_hass_loop_and_stops_cleanly",
    "test_enrichment_scheduler_runtime.py::"
    "test_default_retry_runs_on_hass_loop_and_stop_cancels_pending_retry",
    "test_enrichment_scheduler_runtime.py::"
    "test_default_periodic_reconciliation_runs_on_hass_loop_without_overlap_and_stops",
]


def _requirement_lines(name: str) -> list[str]:
    return [
        line.strip()
        for line in (INTEGRATION_ROOT / name).read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_matrix_contains_only_exact_reviewed_lanes() -> None:
    matrix = json.loads(
        (INTEGRATION_ROOT / "ha-test-matrix.json").read_text(encoding="utf-8")
    )

    assert matrix == EXPECTED_MATRIX


def test_common_requirements_do_not_select_home_assistant() -> None:
    assert not any(
        re.match(r"(?i)^homeassistant(?:$|[\s\[<>=!~;])", requirement)
        for requirement in _requirement_lines("requirements-test.txt")
    )


def test_lane_requirements_inherit_common_and_pin_home_assistant() -> None:
    assert _requirement_lines("requirements-test-minimum.txt") == [
        "-r requirements-test.txt",
        "homeassistant==2025.1.0",
    ]
    assert _requirement_lines("requirements-test-current.txt") == [
        "-r requirements-test.txt",
        "homeassistant==2026.7.3",
    ]


def test_both_exact_lanes_execute_required_real_scheduler_regressions() -> None:
    runner = INTEGRATION_ROOT / "scripts" / "test-ha-integration-matrix.sh"
    if not runner.is_file():
        runner = (
            INTEGRATION_ROOT.parents[1]
            / "scripts"
            / "test-ha-integration-matrix.sh"
        )
    script = runner.read_text(encoding="utf-8")
    run_lane = script.split("run_lane() {", 1)[1].split(
        'if [[ "${LANE}" == "all" ]]',
        1,
    )[0]

    for node_id in EXPECTED_REQUIRED_SCHEDULER_TESTS:
        assert node_id in script
    assert '"${REQUIRED_SCHEDULER_TESTS[@]}"' in run_lane
    assert '--junitxml="${required_scheduler_junit}"' in run_lane
    assert "PYTHONASYNCIODEBUG=1" in run_lane
    assert 'ZIGBEELENS_HA_TEST_COMPONENTS="${SCHEDULER_COMPONENTS}"' in run_lane
    assert "staged scheduler integration provenance does not equal HEAD" in script
    assert "SOURCE_COMMIT" in script
    assert '"tests": 3, "failures": 0, "errors": 0, "skipped": 0' in run_lane
    assert run_lane.index('"${REQUIRED_SCHEDULER_TESTS[@]}"') < run_lane.index(
        '"${venv}/bin/python" -m pytest -q "${HA_DIR}"'
    )
    assert "run_lane minimum" in script
    assert "run_lane current" in script
