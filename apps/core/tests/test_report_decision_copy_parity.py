"""Parity tests for report decision copy presenter vs shared fixture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from zigbeelens.presentation.report_decision_copy import (
    coverage_label,
    decision_status_label,
    device_coverage_label,
    headline_text,
    limitation_text,
    reason_text,
    suggested_check_text,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[3] / "packages" / "shared" / "decision-copy-parity.json"
)

KIND_TO_FN = {
    "status": decision_status_label,
    "headline": headline_text,
    "reason": reason_text,
    "limitation": limitation_text,
    "suggested_check": suggested_check_text,
    "coverage": coverage_label,
    "device_coverage": device_coverage_label,
}


def _load_cases() -> list[dict[str, Any]]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return payload["cases"]


@pytest.mark.parametrize(
    "case",
    _load_cases(),
    ids=lambda case: f"{case['kind']}:{case['code']}:{json.dumps(case.get('params', {}), sort_keys=True)}",
)
def test_report_decision_copy_parity(case: dict[str, Any]) -> None:
    kind = case["kind"]
    code = case["code"]
    params = case.get("params", {})
    expected = case["expected"]

    fn = KIND_TO_FN[kind]
    if kind in {"status", "headline"}:
        actual = fn(code)
    else:
        actual = fn(code, params)

    assert actual == expected


def test_topology_history_unavailable_copy() -> None:
    params = {
        "observed_snapshot_count": 0,
        "complete_snapshot_count": 2,
        "available_layout_snapshot_count": 0,
        "limited_layout_snapshot_count": 2,
        "snapshot_window_count": 2,
    }
    assert (
        coverage_label("topology_history_unavailable", params)
        == "Topology history: layout unavailable"
    )
    assert (
        device_coverage_label("topology_history_unavailable", params)
        == "Topology history: 2 captures have no usable layouts"
    )


@pytest.mark.parametrize(
    ("code", "params", "expected"),
    [
        (
            "topology_history_not_observed",
            {
                "observed_snapshot_count": 0,
                "complete_snapshot_count": 0,
                "available_layout_snapshot_count": 0,
                "limited_layout_snapshot_count": 0,
                "snapshot_window_count": 0,
            },
            "Topology history: no complete captures",
        ),
        (
            "topology_history_unavailable",
            {
                "observed_snapshot_count": 0,
                "complete_snapshot_count": 1,
                "available_layout_snapshot_count": 0,
                "limited_layout_snapshot_count": 1,
                "snapshot_window_count": 1,
            },
            "Topology history: 1 capture has no usable layout",
        ),
        (
            "topology_history_sparse",
            {
                "observed_snapshot_count": 1,
                "complete_snapshot_count": 2,
                "available_layout_snapshot_count": 1,
                "limited_layout_snapshot_count": 1,
                "snapshot_window_count": 2,
            },
            (
                "Topology history: observed in 1 of 1 available layout; "
                "1 additional capture had no usable layout"
            ),
        ),
        (
            "topology_history_sparse",
            {
                "observed_snapshot_count": 0,
                "complete_snapshot_count": 2,
                "available_layout_snapshot_count": 1,
                "limited_layout_snapshot_count": 1,
                "snapshot_window_count": 2,
            },
            (
                "Topology history: observed in 0 of 1 available layout; "
                "1 additional capture had no usable layout"
            ),
        ),
        (
            "topology_history_sparse",
            {
                "observed_snapshot_count": 2,
                "complete_snapshot_count": 5,
                "available_layout_snapshot_count": 3,
                "limited_layout_snapshot_count": 2,
                "snapshot_window_count": 5,
            },
            (
                "Topology history: observed in 2 of 3 available layouts; "
                "2 additional captures had no usable layouts"
            ),
        ),
        (
            "topology_history_not_observed",
            {
                "observed_snapshot_count": 0,
                "complete_snapshot_count": 2,
                "available_layout_snapshot_count": 2,
                "limited_layout_snapshot_count": 0,
                "snapshot_window_count": 2,
            },
            "Topology history: observed in 0 of 2 available layouts",
        ),
        (
            "topology_history_available",
            {
                "observed_snapshot_count": 2,
                "complete_snapshot_count": 2,
                "available_layout_snapshot_count": 2,
                "limited_layout_snapshot_count": 0,
                "snapshot_window_count": 2,
            },
            "Topology history: observed in 2 of 2 available layouts",
        ),
    ],
)
def test_device_topology_history_copy_matrix(
    code: str,
    params: dict[str, int],
    expected: str,
) -> None:
    assert device_coverage_label(code, params) == expected


@pytest.mark.parametrize(
    "params",
    [
        {},
        {
            "observed_snapshot_count": -1,
            "complete_snapshot_count": 0,
            "available_layout_snapshot_count": 0,
            "limited_layout_snapshot_count": 0,
            "snapshot_window_count": 0,
        },
        {
            "observed_snapshot_count": False,
            "complete_snapshot_count": 0,
            "available_layout_snapshot_count": 0,
            "limited_layout_snapshot_count": 0,
            "snapshot_window_count": 0,
        },
        {
            "observed_snapshot_count": 0,
            "complete_snapshot_count": 2,
            "available_layout_snapshot_count": 1,
            "limited_layout_snapshot_count": 0,
            "snapshot_window_count": 2,
        },
        {
            "observed_snapshot_count": 2,
            "complete_snapshot_count": 1,
            "available_layout_snapshot_count": 1,
            "limited_layout_snapshot_count": 0,
            "snapshot_window_count": 1,
        },
    ],
)
def test_device_topology_history_copy_fails_conservatively(
    params: dict[str, object],
) -> None:
    for code in (
        "topology_history_available",
        "topology_history_sparse",
        "topology_history_not_observed",
        "topology_history_unavailable",
    ):
        copy = device_coverage_label(code, params)
        assert copy == "Topology history: coverage unknown"
        assert "available" not in copy
        assert "every" not in copy


def test_device_topology_history_copy_rejects_code_count_mismatch() -> None:
    all_available = {
        "observed_snapshot_count": 2,
        "complete_snapshot_count": 2,
        "available_layout_snapshot_count": 2,
        "limited_layout_snapshot_count": 0,
        "snapshot_window_count": 2,
    }
    assert (
        device_coverage_label("topology_history_sparse", all_available)
        == "Topology history: coverage unknown"
    )
