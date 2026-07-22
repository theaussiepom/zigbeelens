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


def test_list_detail_download_omit_non_v3_rows(mock_client: TestClient):
    """Saved-report list is an exact-v3 read boundary (same as detail/download)."""
    created = mock_client.post("/api/reports", json={"scope": "full", "format": "json"})
    assert created.status_code == 200
    good_id = created.json()["id"]

    ctx = mock_client.app.state.ctx
    for report_id, body in (
        ("bad-missing", {"id": "bad-missing"}),
        ("bad-v1", {"id": "bad-v1", "report_version": 1, "markdown_summary": "old"}),
        ("bad-string3", {"id": "bad-string3", "report_version": "3"}),
        ("bad-malformed-meta", {"report_version": 3, "product": "ZigbeeLens"}),
    ):
        ctx.repo.reports.save_report(
            report_id=report_id,
            format="json",
            scope="full",
            redaction_profile="standard",
            summary="should-not-list",
            body=body,
            markdown="old",
            redaction={},
            metadata={"incident_count": 9, "device_count": 9, "network_count": 9},
        )

    for prefix in ("/api", "/api/v1"):
        listed = mock_client.get(f"{prefix}/reports")
        assert listed.status_code == 200
        ids = {row["id"] for row in listed.json()}
        assert good_id in ids
        assert "bad-missing" not in ids
        assert "bad-v1" not in ids
        assert "bad-string3" not in ids
        assert "bad-malformed-meta" not in ids
        for bad_id in ("bad-missing", "bad-v1", "bad-string3", "bad-malformed-meta"):
            assert mock_client.get(f"{prefix}/reports/{bad_id}").status_code == 404
            assert (
                mock_client.get(f"{prefix}/reports/{bad_id}/download").status_code == 404
            )
            # Rows remain stored until explicitly deleted.
            assert ctx.repo.reports.get_report(bad_id) is not None

    # Valid list row derives counts from validated v3 body, not bogus metadata.
    good_row = next(row for row in listed.json() if row["id"] == good_id)
    assert good_row["summary"]
    assert isinstance(good_row["device_count"], int)


def test_list_redaction_applied_owned_by_validated_body(mock_client: TestClient):
    """Public list redaction_applied follows body.redaction.applied, not a hardcode."""
    from report_v3_helpers import full_redaction_status, minimal_report_v3

    detail = minimal_report_v3(
        id="redact-applied-false",
        redaction=full_redaction_status(applied=False),
        markdown_summary="# ZigbeeLens Evidence Report\n",
    )
    body = detail.model_dump(mode="json")
    ctx = mock_client.app.state.ctx
    ctx.repo.reports.save_report(
        report_id=detail.id,
        format="json",
        scope="full",
        redaction_profile="standard",
        summary="fixture",
        body=body,
        markdown=detail.markdown_summary,
        redaction=body["redaction"],
        metadata={},
    )
    assert load_stored_report_envelope(ctx.repo.reports.get_report(detail.id)) is not None

    generated = mock_client.post("/api/reports", json={"scope": "full", "format": "json"})
    assert generated.status_code == 200
    assert generated.json()["redaction_applied"] is True

    for prefix in ("/api", "/api/v1"):
        listed = mock_client.get(f"{prefix}/reports")
        assert listed.status_code == 200
        row = next(item for item in listed.json() if item["id"] == detail.id)
        assert row["redaction_applied"] is False
        fetched = mock_client.get(f"{prefix}/reports/{detail.id}")
        assert fetched.status_code == 200
        assert fetched.json()["redaction"]["applied"] is False
        ReportDetailV3.model_validate(fetched.json())


def test_list_uses_validated_body_over_stale_row_metadata(mock_client: TestClient):
    created = mock_client.post(
        "/api/reports",
        json={
            "scope": "network",
            "network_id": "home",
            "format": "markdown",
            "redaction": {"profile": "public_safe", "hash_ieee_addresses": False},
        },
    )
    assert created.status_code == 200
    report_id = created.json()["id"]
    detail = mock_client.get(f"/api/reports/{report_id}").json()
    assert detail["format"] == "markdown"
    assert detail["scope"] == "network"
    assert detail["redaction"]["profile"] == "public_safe"

    ctx = mock_client.app.state.ctx
    ctx.repo.db.conn.execute(
        """
        UPDATE reports
        SET format = ?,
            scope = ?,
            redaction_profile = ?,
            generated_at = ?,
            metadata_json = ?
        WHERE id = ?
        """,
        (
            "json",
            "full",
            "standard",
            "1999-01-01T00:00:00+00:00",
            '{"incident_count": 9, "device_count": 9, "network_count": 9}',
            report_id,
        ),
    )
    ctx.repo.db.conn.commit()

    for prefix in ("/api", "/api/v1"):
        listed = mock_client.get(f"{prefix}/reports")
        assert listed.status_code == 200
        row = next(item for item in listed.json() if item["id"] == report_id)
        assert row["format"] == "markdown"
        assert row["scope"] == "network"
        assert row["redaction_profile"] == "public_safe"
        assert row["generated_at"] == detail["generated_at"]
        assert row["incident_count"] == len(detail["incidents"])
        assert row["device_count"] != 9
        assert row["network_count"] != 9

        fetched = mock_client.get(f"{prefix}/reports/{report_id}")
        assert fetched.status_code == 200
        assert fetched.json()["format"] == "markdown"
        assert fetched.json()["scope"] == "network"
        assert fetched.json()["generated_at"] == detail["generated_at"]


def test_row_body_id_mismatch_fails_closed(mock_client: TestClient):
    created = mock_client.post("/api/reports", json={"scope": "full", "format": "json"})
    assert created.status_code == 200
    report_id = created.json()["id"]
    detail = mock_client.get(f"/api/reports/{report_id}").json()

    mismatched = dict(detail)
    mismatched["id"] = "body-id-does-not-match-row"
    ctx = mock_client.app.state.ctx
    ctx.repo.db.conn.execute(
        "UPDATE reports SET body_json = ? WHERE id = ?",
        (__import__("json").dumps(mismatched), report_id),
    )
    ctx.repo.db.conn.commit()
    assert ctx.repo.reports.get_report(report_id) is not None

    for prefix in ("/api", "/api/v1"):
        listed_ids = {row["id"] for row in mock_client.get(f"{prefix}/reports").json()}
        assert report_id not in listed_ids
        assert mock_client.get(f"{prefix}/reports/{report_id}").status_code == 404
        assert (
            mock_client.get(f"{prefix}/reports/{report_id}/download").status_code == 404
        )
