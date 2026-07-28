"""Phase 5D-2: Markdown presenter and Version 1 fail-closed storage proofs."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from zigbeelens.config.models import AppConfig
from zigbeelens.db.connection import Database
from zigbeelens.presentation.report_decision_copy import (
    decision_status_label,
    headline_text,
)
from zigbeelens.schemas import (
    DiagnosticConclusion,
    IncidentScope,
    LimitationItem,
    Severity,
    Confidence,
    ReportDetailV3,
)
from legacy_report_shapes import ReportSummaryBlock
from zigbeelens.services.data_service import DataService
from zigbeelens.services.report_storage import load_stored_report_envelope
from zigbeelens.services.reports import render_markdown, report_body_as_json
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.parser import parse_networkmap_payload


SCENARIO = "four_devices_same_room_unavailable"

V1_MARKDOWN = """# ZigbeeLens diagnostic report

## Executive summary

Legacy executive finding.

## Health summary

- Needs attention: 2

## Unhealthy devices

| Device | Network | Health | Lens bucket | Evidence |
|---|---|---|---|---|
| Plug | home | unavailable | needs_attention | offline |
"""


def _v1_body() -> dict:
    return {
        "id": "report-v1-fixture",
        "product": "ZigbeeLens",
        "report_version": 1,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "version": "0.0.0-test",
        "scope": "full",
        "format": "json",
        "redaction": {
            "applied": True,
            "profile": "standard",
            "mqtt_credentials": True,
            "secrets": True,
            "hostnames": False,
            "ip_addresses": False,
            "ieee_addresses_hashed": False,
            "friendly_names": "preserved",
            "network_names": "preserved",
        },
        "summary": ReportSummaryBlock(
            overall_state=Severity.incident,
            current_finding="Legacy executive finding.",
            networks_monitored=1,
            total_devices=2,
            active_incidents=1,
            watching_incidents=0,
            unavailable_devices=2,
            router_risks=0,
            stale_devices=0,
            weak_links=0,
            low_battery_devices=0,
        ).model_dump(mode="json"),
        "health_summary": {
            "vocabulary": "lens_family",
            "overall_state": "incident",
            "bucket_counts": {"needs_attention": 2},
            "bucket_labels": {"needs_attention": "Needs attention"},
        },
        "config_summary": {"mode": "mock"},
        "collector": {},
        "networks": [],
        "devices": [],
        "device_details": [],
        "router_risks": [],
        "incidents": [],
        "timeline": [],
        "health_snapshot": {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "overall_severity": "incident",
            "overall_health": "unavailable",
            "network_count": 1,
            "device_count": 2,
            "unavailable_count": 2,
            "incident_count": 1,
            "networks": [],
        },
        "diagnostic_conclusions": [
            DiagnosticConclusion(
                classification="legacy",
                severity=Severity.incident,
                scope=IncidentScope.network,
                confidence=Confidence.medium,
                summary="Legacy executive finding.",
            ).model_dump(mode="json")
        ],
        "limitations": [
            LimitationItem(id="lim-1", summary="Legacy limitation.").model_dump()
        ],
        "raw_counts": {"devices_included": 2},
        "markdown_summary": V1_MARKDOWN,
    }


def test_version3_markdown_hierarchy_and_no_legacy(mock_client: TestClient):
    detail = mock_client.get("/api/reports/preview").json()
    md = detail["markdown_summary"]
    assert detail["report_version"] == 3
    assert md.startswith("# ZigbeeLens Evidence Report")
    assert "## Decision summary" in md
    assert "## Executive summary" not in md
    assert "## Health summary" not in md
    assert "## Unhealthy devices" not in md
    assert "## Active incidents" not in md
    assert "Overall state:" not in md
    assert "Lens bucket" not in md
    positions = []
    for heading in (
        "## Decision summary",
        "## What to review first",
        "## Device Stories",
        "## Data coverage",
        "## Incidents",
        "## Scope details",
        "## Limitations",
        "## Suggested checks",
        "## Redaction",
    ):
        idx = md.find(heading)
        if idx >= 0:
            positions.append(idx)
    assert positions == sorted(positions)
    if detail["device_stories"]:
        story = detail["device_stories"][0]
        assert decision_status_label(story["status"]) in md
        assert headline_text(story["headline_code"]) in md
        assert story["status"] not in md.split(headline_text(story["headline_code"]))[0]


def test_version3_public_report_discloses_mixed_topology_layout_coverage(
    live_client: TestClient,
) -> None:
    repo = live_client.app.state.ctx.repo
    repo.upsert_device(
        network_id="home",
        ieee_address="0x03",
        friendly_name="Kitchen sensor",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )
    repo.update_device_current_state(
        network_id="home",
        ieee_address="0x03",
        availability="online",
        last_seen="2026-07-13T02:00:00+00:00",
    )

    captured_at = datetime(2026, 7, 13, 2, 0, 0, tzinfo=timezone.utc)
    for snapshot_id, when, nodes in (
        ("snap-limited", captured_at, {}),
        (
            "snap-available",
            captured_at - timedelta(days=1),
            {
                "0x01": {"type": "Coordinator"},
                "0X03": {"type": "EndDevice"},
            },
        ),
    ):
        repo.create_topology_snapshot(
            snapshot_id=snapshot_id,
            network_id="home",
            requested_by="test",
            status="pending",
            warning_acknowledged=True,
        )
        parsed = parse_networkmap_payload({"nodes": nodes, "links": []})
        repo.store_topology_parsed(snapshot_id, "home", parsed, status="complete")
        repo.db.conn.execute(
            "UPDATE topology_snapshots SET captured_at = ? WHERE snapshot_id = ?",
            (when.isoformat(), snapshot_id),
        )
    repo.db.conn.commit()

    response = live_client.get(
        "/api/reports/preview",
        params={"scope": "full", "profile": "public_safe"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["redaction"]["profile"] == "public_safe"
    topology_coverage = {
        "dimension": "historical_snapshots",
        "state": "sparse",
        "label_code": "topology_history_sparse",
        "params": {
            "observed_snapshot_count": 1,
            "complete_snapshot_count": 2,
            "available_layout_snapshot_count": 1,
            "limited_layout_snapshot_count": 1,
            "snapshot_window_count": 2,
        },
    }
    story = next(
        item
        for item in payload["device_stories"]
        if topology_coverage in item["coverage"]
    )

    detail = ReportDetailV3.model_validate(payload)
    expected = (
        "Topology history: observed in 1 of 1 available layout; "
        "1 additional capture had no usable layout"
    )
    assert expected in payload["markdown_summary"]
    assert expected in render_markdown(detail)

    body = report_body_as_json(detail)
    projected = next(
        item
        for item in next(
            report_story
            for report_story in body["device_stories"]
            if report_story["subject_id"] == story["subject_id"]
        )["coverage"]
        if item["dimension"] == "historical_snapshots"
    )
    assert projected == topology_coverage
    assert "device_ieee" not in json.dumps(projected)


def test_report_detail_v3_rejects_legacy_topology_history_params(
    mock_client: TestClient,
) -> None:
    payload = mock_client.get("/api/reports/preview").json()
    topology = next(
        coverage
        for story in payload["device_stories"]
        for coverage in story["coverage"]
        if coverage["dimension"] == "historical_snapshots"
    )
    topology["params"] = {
        "observed_snapshot_count": 0,
        "snapshot_window_count": 0,
        "limited_snapshot_count": 1,
    }

    with pytest.raises(ValidationError):
        ReportDetailV3.model_validate(payload)


def test_version1_stored_report_fails_closed(tmp_path, mock_client: TestClient):
    db = Database(tmp_path / "v1.sqlite")
    db.migrate()
    repo = Repository(db)
    body = _v1_body()
    assert body["report_version"] == 1

    row = repo.reports.save_report(
        report_id="stored-v1",
        format="json",
        scope="full",
        redaction_profile="standard",
        summary="Legacy executive finding.",
        body=body,
        markdown=V1_MARKDOWN,
        redaction=body["redaction"],
        metadata={"incident_count": 1, "device_count": 2, "network_count": 1},
    )
    config = AppConfig()
    config.mode.mock = True
    data = DataService(config, repo)
    assert data.get_stored_report(row.id) is None
    assert load_stored_report_envelope(row) is None
    # Storage row remains untouched; it is simply not a public exact-v3 summary.
    stored = repo.reports.get_report(row.id)
    assert stored is not None
    assert stored.summary == "Legacy executive finding."
    assert json.loads(stored.body_json)["report_version"] == 1


def test_version3_storage_round_trip(mock_client: TestClient):
    created = mock_client.post("/api/reports", json={"format": "json", "scope": "full"}).json()
    detail = mock_client.get(f"/api/reports/{created['id']}").json()
    assert detail["report_version"] == 3
    assert detail["decision_summary"] is not None
    assert detail["device_stories"] is not None
    assert detail["markdown_summary"].startswith("# ZigbeeLens Evidence Report")
    assert created["summary"]
    assert created["summary"] != "Legacy executive finding."

    body_md = detail["markdown_summary"]
    assert "## Health summary" not in body_md
    assert "## Unhealthy devices" not in body_md
    assert "## Decision summary" in body_md

    created_md = mock_client.post(
        "/api/reports", json={"format": "markdown", "scope": "full"}
    ).json()
    md_res = mock_client.get(f"/api/reports/{created_md['id']}/download")
    assert md_res.status_code == 200
    assert "markdown" in md_res.headers["content-type"]
    stored = mock_client.get(f"/api/reports/{created_md['id']}").json()
    assert md_res.text == stored["markdown_summary"]
    assert md_res.text.startswith("# ZigbeeLens Evidence Report")

    js = mock_client.get(f"/api/reports/{created['id']}/download")
    assert js.status_code == 200
    parsed = json.loads(js.text)
    assert parsed["report_version"] == 3


def test_incident_records_use_recorded_interpretation(mock_client: TestClient):
    incidents = mock_client.get("/api/incidents").json()["items"]
    if not incidents:
        return
    detail = mock_client.get(
        "/api/reports/preview",
        params={"scope": "incident", "incident_id": incidents[0]["id"]},
    ).json()
    md = detail["markdown_summary"]
    if detail["incidents"]:
        assert "## Incidents" in md
        assert "Lens bucket" not in md
        assert "Summary:" in md
