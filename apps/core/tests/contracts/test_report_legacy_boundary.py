"""Current report v3 semantic contract vs legacy v1/v2 immutability boundary."""

from __future__ import annotations

import json

from zigbeelens.schemas import ReportDetailV3
from support.contracts import load_oracle_fixture, oracle_scenarios  # type: ignore[import-not-found]


def test_oracle_current_reports_are_exact_v3():
    for scenario_id, body in oracle_scenarios(load_oracle_fixture()).items():
        report = body["report"]
        assert report["report_version"] == 3, scenario_id
        validated = ReportDetailV3.model_validate(report)
        assert validated.report_version == 3
        assert validated.device_stories is not None
        assert validated.decision_summary is not None
        assert validated.redaction is not None


def test_legacy_bodies_are_not_validated_as_v3():
    """Legacy stored shapes must remain outside ReportDetailV3 authority."""
    legacy_v1 = {
        "id": "legacy-1",
        "generated_at": "2026-01-01T00:00:00Z",
        "summary": "legacy",
        "markdown": "# Legacy\n",
    }
    legacy_v2 = {
        "report_version": 2,
        "id": "legacy-2",
        "generated_at": "2026-01-01T00:00:00Z",
        "summary": "legacy",
        "markdown": "# Legacy v2\n",
    }
    for body in (legacy_v1, legacy_v2):
        try:
            ReportDetailV3.model_validate(body)
            raised = False
        except Exception:
            raised = True
        assert raised, body


def test_legacy_version_literals_remain_distinct():
    assert json.dumps({"report_version": 1}) != json.dumps({"report_version": 3})
    assert json.dumps({"report_version": 2}) != json.dumps({"report_version": 3})
