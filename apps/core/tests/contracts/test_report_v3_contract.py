"""One current ReportDetailV3 contract suite (no legacy compatibility)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from zigbeelens.schemas import ReportDetailV3, ReportRequest
from zigbeelens.services.report_storage import load_stored_report_envelope
from zigbeelens.services.reports import generate_report, store_report
from zigbeelens.storage.repository import Repository
from zigbeelens.db.connection import Database
from zigbeelens.config.models import AppConfig
from zigbeelens.services.data_service import DataService
from support.contracts import load_oracle_fixture, oracle_scenarios  # type: ignore[import-not-found]


def test_oracle_current_reports_are_exact_v3():
    for scenario_id, body in oracle_scenarios(load_oracle_fixture()).items():
        report = body["report"]
        assert type(report["report_version"]) is int
        assert report["report_version"] == 3, scenario_id
        validated = ReportDetailV3.model_validate(report)
        assert validated.report_version == 3
        assert validated.device_stories is not None
        assert validated.decision_summary is not None
        assert validated.redaction is not None


@pytest.mark.parametrize(
    "raw",
    [None, 1, 2, "1", "2", "3", True, 3.0, 4, -1, 1.5],
)
def test_non_v3_bodies_fail_closed(tmp_path, raw):
    db = Database(tmp_path / "reject.sqlite")
    db.migrate()
    repo = Repository(db)
    body: dict = {"id": "x", "markdown_summary": "nope"}
    if raw is not None:
        body["report_version"] = raw
    row = repo.reports.save_report(
        report_id="r1",
        format="json",
        scope="full",
        redaction_profile="standard",
        summary="s",
        body=body,
        markdown="nope",
        redaction={},
        metadata={},
    )
    assert load_stored_report_envelope(row) is None


@pytest.mark.parametrize(
    "params",
    [
        {"scope": "full", "format": "json", "profile": "standard"},
        {"scope": "full", "format": "yaml", "profile": "public_safe"},
        {"scope": "full", "format": "markdown", "profile": "strict"},
        {"scope": "network", "format": "json", "profile": "standard", "network_id": "home"},
    ],
)
def test_current_generation_matrix(mock_client: TestClient, params: dict):
    preview = mock_client.get("/api/reports/preview", params=params)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert type(body["report_version"]) is int
    assert body["report_version"] == 3
    ReportDetailV3.model_validate(body)


def test_current_device_and_incident_scopes(mock_client: TestClient):
    devices = mock_client.get("/api/devices").json()["items"]
    assert devices
    device = devices[0]
    preview = mock_client.get(
        "/api/reports/preview",
        params={
            "scope": "device",
            "network_id": device["network_id"],
            "device": device["ieee_address"],
            "format": "json",
            "profile": "standard",
        },
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["report_version"] == 3

    incidents = mock_client.get("/api/incidents").json()["items"]
    if not incidents:
        pytest.skip("no incidents in default mock")
    preview = mock_client.get(
        "/api/reports/preview",
        params={
            "scope": "incident",
            "incident_id": incidents[0]["id"],
            "format": "json",
            "profile": "standard",
        },
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["report_version"] == 3


def test_report_crud_exact_v3(mock_client: TestClient):
    created = mock_client.post("/api/reports", json={"scope": "full", "format": "json"})
    assert created.status_code == 200
    report_id = created.json()["id"]
    detail = mock_client.get(f"/api/reports/{report_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["report_version"] == 3
    ReportDetailV3.model_validate(body)
    download = mock_client.get(f"/api/reports/{report_id}/download")
    assert download.status_code == 200
    listed = mock_client.get("/api/reports")
    assert listed.status_code == 200
    assert any(row["id"] == report_id for row in listed.json())
    deleted = mock_client.delete(f"/api/reports/{report_id}")
    assert deleted.status_code == 200
    assert mock_client.get(f"/api/reports/{report_id}").status_code == 404


def test_manual_non_v3_row_not_readable_after_migration(tmp_path):
    db = Database(tmp_path / "manual.sqlite")
    db.migrate()
    repo = Repository(db)
    config = AppConfig()
    config.mode.mock = True
    data = DataService(config, repo)
    detail = generate_report(
        data=data,
        config=config,
        reporting=config.reporting,
        collector={},
        request=ReportRequest(),
        scenario="bridge_offline",
        repo=repo,
    )
    row = store_report(repo, detail, ReportRequest())
    assert load_stored_report_envelope(row) is not None

    repo.reports.save_report(
        report_id="legacy-insert",
        format="json",
        scope="full",
        redaction_profile="standard",
        summary="legacy",
        body={"report_version": 1, "markdown_summary": "old"},
        markdown="old",
        redaction={},
        metadata={},
    )
    bad = repo.reports.get_report("legacy-insert")
    assert load_stored_report_envelope(bad) is None
