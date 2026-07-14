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
