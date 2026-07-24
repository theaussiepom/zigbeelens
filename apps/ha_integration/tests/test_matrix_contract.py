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
