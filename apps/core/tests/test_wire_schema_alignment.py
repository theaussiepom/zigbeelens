"""Track 5 wire-schema alignment: required fields, OpenAPI, stored malformed v3."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from zigbeelens.db.connection import Database
from zigbeelens.schemas import (
    DecisionCountSummary,
    DeviceDecisionBadge,
    ReportDetailV3,
    ReportDomainDetailsV3,
    ReportDeviceStory,
    ReportRedactionStatus,
)
from zigbeelens.services.report_storage import load_stored_report_envelope
from zigbeelens.storage.repository import Repository

from report_v3_helpers import (
    empty_decision_summary,
    empty_domain_details,
    empty_story_collections,
    full_redaction_status,
    minimal_report_v3,
)

REPORT_V3_REQUIRED = [
    "id",
    "product",
    "report_version",
    "generated_at",
    "version",
    "scope",
    "format",
    "redaction",
    "config_summary",
    "decision_summary",
    "investigation_priorities",
    "device_stories",
    "data_coverage_warnings",
    "incidents",
    "collector_status",
    "domain_details",
    "events_or_timeline",
    "limitations",
    "raw_counts",
    "markdown_summary",
]


def test_decision_badge_requires_coverage_label_codes():
    with pytest.raises(ValidationError):
        DeviceDecisionBadge.model_validate(
            {
                "status": "watch",
                "priority": "low",
                "headline_code": "device_watch",
            }
        )


def test_decision_count_summary_requires_all_fields():
    base = empty_decision_summary().model_dump(mode="json")
    for key in (
        "subject_count",
        "overall_status",
        "highest_priority",
        "status_counts",
        "priority_counts",
        "coverage_warning_count",
    ):
        payload = dict(base)
        del payload[key]
        with pytest.raises(ValidationError):
            DecisionCountSummary.model_validate(payload)


@pytest.mark.parametrize("field", REPORT_V3_REQUIRED)
def test_report_detail_v3_rejects_missing_top_level_field(field: str):
    payload = minimal_report_v3().model_dump(mode="json")
    del payload[field]
    with pytest.raises(ValidationError):
        ReportDetailV3.model_validate(payload)


def test_report_domain_details_requires_all_fields():
    base = empty_domain_details().model_dump(mode="json")
    for key in (
        "networks",
        "devices",
        "device_details",
        "router_risks",
        "topology_snapshot_count",
    ):
        payload = dict(base)
        del payload[key]
        with pytest.raises(ValidationError):
            ReportDomainDetailsV3.model_validate(payload)


def test_report_redaction_requires_all_fields():
    base = full_redaction_status().model_dump(mode="json")
    for key in base:
        payload = dict(base)
        del payload[key]
        with pytest.raises(ValidationError):
            ReportRedactionStatus.model_validate(payload)


def test_report_device_story_requires_collections():
    base = {
        "network_id": "home",
        "ieee_address": "0x1",
        "friendly_name": "Sensor",
        "subject_type": "device",
        "subject_id": "home:0x1",
        "status": "watch",
        "priority": "low",
        "headline_code": "device_watch",
        **empty_story_collections(),
    }
    ReportDeviceStory.model_validate(base)
    for key in (
        "reasons",
        "evidence",
        "limitations",
        "suggested_checks",
        "coverage",
        "related_unresolved_incident_ids",
        "timeline",
    ):
        payload = copy.deepcopy(base)
        del payload[key]
        with pytest.raises(ValidationError):
            ReportDeviceStory.model_validate(payload)


def test_report_detail_v3_rejects_invalid_scope_format_and_raw_counts():
    with pytest.raises(ValidationError):
        minimal_report_v3(scope="all")
    with pytest.raises(ValidationError):
        minimal_report_v3(format="xml")
    with pytest.raises(ValidationError):
        ReportDetailV3.model_validate(
            {
                **minimal_report_v3().model_dump(mode="json"),
                "raw_counts": {"devices_included": "1"},
            }
        )
    with pytest.raises(ValidationError):
        ReportDetailV3.model_validate(
            {
                **minimal_report_v3().model_dump(mode="json"),
                "raw_counts": {"devices_included": 1.0},
            }
        )
    with pytest.raises(ValidationError):
        ReportDetailV3.model_validate(
            {
                **minimal_report_v3().model_dump(mode="json"),
                "raw_counts": {"devices_included": True},
            }
        )


def test_malformed_stored_v3_missing_field_fails_safely(tmp_path: Path):
    db = Database(tmp_path / "missing-v3.sqlite")
    db.migrate()
    repo = Repository(db)
    body = minimal_report_v3().model_dump(mode="json")
    del body["domain_details"]
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True)
    row = repo.reports.save_report(
        report_id="missing-domain",
        format="json",
        scope="full",
        redaction_profile="standard",
        summary="bad",
        body=body,
        markdown="",
        redaction={},
        metadata={},
    )
    assert load_stored_report_envelope(row) is None
    stored = repo.reports.get_report(row.id)
    assert stored is not None
    assert stored.body_json == raw or json.loads(stored.body_json)["id"] == body["id"]
    assert "domain_details" not in json.loads(stored.body_json)


def test_openapi_required_arrays_for_exact_wire_shapes(tmp_path, monkeypatch):
    from zigbeelens.app.context import reset_context
    from zigbeelens.main import create_app

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
server:
  host: 127.0.0.1
  port: 8377
mode:
  mock: true
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
storage:
  path: {tmp_path / "openapi.sqlite"}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(config_path))
    monkeypatch.setenv("ZIGBEELENS_OPENAPI_ENABLED", "true")
    reset_context()
    with TestClient(create_app(str(config_path))) as client:
        schema = client.get("/openapi.json").json()
    reset_context()
    components = schema["components"]["schemas"]

    report = components.get("ReportDetailV3") or components["ReportDetail"]
    assert set(report.get("required", [])) == set(REPORT_V3_REQUIRED)

    domain = components["ReportDomainDetailsV3"]
    assert set(domain.get("required", [])) == {
        "networks",
        "devices",
        "device_details",
        "router_risks",
        "topology_snapshot_count",
    }

    story = components["ReportDeviceStory"]
    for key in (
        "reasons",
        "evidence",
        "limitations",
        "suggested_checks",
        "coverage",
        "related_unresolved_incident_ids",
        "timeline",
    ):
        assert key in story.get("required", [])

    badge = components.get("DeviceDecisionBadge") or components["DecisionBadge"]
    assert "coverage_label_codes" in badge.get("required", [])

    summary = components["DecisionCountSummary"]
    for key in (
        "status_counts",
        "priority_counts",
        "coverage_warning_count",
    ):
        assert key in summary.get("required", [])

    # Recursive forbidden fields stay absent.
    for name in ("LensBucket", "LensHealthSummary", "ReportSummaryBlock"):
        assert name not in components
