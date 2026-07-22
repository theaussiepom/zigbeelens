"""Structural OpenAPI checks for critical decision/report contracts (no full snapshot)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zigbeelens.app.context import reset_context
from zigbeelens.decisions.types import DecisionPriority, DecisionStatus
from zigbeelens.main import create_app


@pytest.fixture
def openapi_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
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
    return schema


def test_openapi_decision_badge_and_summary_required(openapi_schema: dict):
    components = openapi_schema["components"]["schemas"]
    badge = components.get("DeviceDecisionBadge") or components["DecisionBadge"]
    for key in (
        "status",
        "priority",
        "headline_code",
        "coverage_label_codes",
    ):
        assert key in badge.get("required", []), key

    summary = components["DecisionCountSummary"]
    for key in (
        "subject_count",
        "overall_status",
        "highest_priority",
        "status_counts",
        "priority_counts",
        "coverage_warning_count",
    ):
        assert key in summary.get("required", []), key


def test_openapi_status_priority_enums(openapi_schema: dict):
    components = openapi_schema["components"]["schemas"]
    status_schema = components.get("DecisionStatus")
    priority_schema = components.get("DecisionPriority")
    if status_schema and "enum" in status_schema:
        assert set(status_schema["enum"]) == {m.value for m in DecisionStatus}
    if priority_schema and "enum" in priority_schema:
        assert set(priority_schema["enum"]) == {m.value for m in DecisionPriority}


def test_openapi_report_v3_and_incident_required(openapi_schema: dict):
    components = openapi_schema["components"]["schemas"]
    report = components.get("ReportDetailV3") or components["ReportDetail"]
    for key in (
        "report_version",
        "device_stories",
        "domain_details",
        "decision_summary",
        "redaction",
    ):
        assert key in report.get("required", []) or key in report.get("properties", {})

    story = components["ReportDeviceStory"]
    for key in (
        "network_id",
        "ieee_address",
        "status",
        "priority",
        "headline_code",
        "reasons",
        "limitations",
        "suggested_checks",
        "coverage",
    ):
        assert key in story.get("required", []), key

    incident = components.get("Incident")
    assert incident is not None
    for key in ("id", "type", "status", "severity", "scope"):
        assert key in incident.get("required", []), key


def test_openapi_incident_order_enum_and_security_posture(openapi_schema: dict):
    paths = openapi_schema["paths"]
    incidents = paths.get("/api/incidents") or paths.get("/api/v1/incidents")
    assert incidents is not None
    params = incidents["get"].get("parameters") or []
    order = next((p for p in params if p.get("name") == "order"), None)
    if order is not None:
        schema = order.get("schema") or {}
        enum = schema.get("enum")
        if enum is not None:
            assert set(enum) == {"lifecycle", "recent"}

    # Fallback root HTML auth scheme must not expose ingress remote-user API key.
    security_schemes = openapi_schema.get("components", {}).get("securitySchemes", {})
    for name, scheme in security_schemes.items():
        assert "remote-user" not in name.lower()
        assert "x-remote-user" not in str(scheme).lower()

    assert "/" not in paths or "get" not in (paths.get("/") or {})
