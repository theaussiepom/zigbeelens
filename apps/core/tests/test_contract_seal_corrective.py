"""Track 5 contract-seal gates: exact v3, immutable legacy, network parity, MQTT prefix."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zigbeelens.db.connection import Database
from zigbeelens.mqtt_discovery.topics import (
    SUPERSEDED_LENS_DISCOVERY_ENTITY_KEYS,
    superseded_lens_discovery_topics,
)
from zigbeelens.schemas import ReportDetailV3
from zigbeelens.services.report_storage import (
    load_stored_report_envelope,
    parse_stored_body_json,
)
from zigbeelens.storage.repository import Repository

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

REPORT_V3_TOP_LEVEL_KEYS = frozenset(
    {
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
    }
)

FORBIDDEN_RECURSIVE = frozenset(
    {
        "executive_summary",
        "health_summary",
        "health_snapshot",
        "diagnostic_conclusions",
        "lens_bucket",
        "lens_bucket_label",
        "lens_bucket_reason",
        "lens_reasons",
        "health_primary",
        "overall_health",
        "top_affected_devices",
        "recently_unstable",
        "weak_links",
        "low_batteries",
        "stale_devices",
    }
)


def _assert_exact_keys(payload: dict) -> None:
    assert set(payload.keys()) == REPORT_V3_TOP_LEVEL_KEYS
    for key in REPORT_V3_TOP_LEVEL_KEYS:
        assert key in payload


def _assert_forbidden_absent(value, *, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            assert key not in FORBIDDEN_RECURSIVE, f"{path}.{key} must be absent"
            _assert_forbidden_absent(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_forbidden_absent(child, path=f"{path}[{index}]")


def test_report_detail_v3_model_exact_fields():
    fields = set(ReportDetailV3.model_fields)
    assert fields == REPORT_V3_TOP_LEVEL_KEYS
    assert ReportDetailV3.model_config.get("extra") == "forbid"


def test_preview_exposes_exact_report_v3(mock_client: TestClient):
    detail = mock_client.get("/api/reports/preview", params={"profile": "standard"}).json()
    _assert_exact_keys(detail)
    _assert_forbidden_absent(detail)
    assert detail["report_version"] == 3


def test_stored_v3_get_and_downloads_exact(mock_client: TestClient):
    created = mock_client.post(
        "/api/reports", json={"format": "json", "scope": "full"}
    ).json()
    detail = mock_client.get(f"/api/reports/{created['id']}").json()
    _assert_exact_keys(detail)
    _assert_forbidden_absent(detail)
    assert detail["id"] == created["id"]
    assert detail["id"] != "report-preview"

    download = mock_client.get(f"/api/reports/{created['id']}/download")
    assert download.status_code == 200
    body = download.json()
    _assert_exact_keys(body)
    _assert_forbidden_absent(body)
    assert body["id"] == created["id"]


def test_openapi_report_detail_v3_has_no_legacy_aliases(tmp_path, monkeypatch):
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
    assert "ReportDetailV3" in components or "ReportDetail" in components
    report_schema = components.get("ReportDetailV3") or components["ReportDetail"]
    props = set(report_schema.get("properties", {}))
    assert props == REPORT_V3_TOP_LEVEL_KEYS
    for name in ("LensBucket", "LensHealthSummary", "ReportSummaryBlock"):
        assert name not in components
    device_summary = components.get("DeviceSummary", {})
    device_props = set(device_summary.get("properties", {}))
    assert "health" not in device_props
    assert "health_primary" not in device_props
    assert "lens_bucket" not in device_props


@pytest.mark.parametrize("version", [1, 2])
def test_legacy_stored_report_bodies_are_immutable(tmp_path: Path, version: int):
    db = Database(tmp_path / f"legacy-v{version}.sqlite")
    db.migrate()
    repo = Repository(db)
    sentinel = f"LEGACY_V{version}_SENTINEL_SEAL"
    body = {
        "id": f"stored-v{version}",
        "product": "ZigbeeLens",
        "report_version": version,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "version": "0.0.0",
        "scope": "full",
        "format": "json",
        "markdown_summary": f"# Legacy\n\n{sentinel}\n",
        "executive_summary": sentinel,
        "health_summary": {"overall_state": "incident"},
        "networks": [{"id": "home", "name": "Home"}],
    }
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True)
    digest_before = hashlib.sha256(raw.encode()).hexdigest()
    row = repo.reports.save_report(
        report_id=f"row-v{version}",
        format="json",
        scope="full",
        redaction_profile="standard",
        summary=sentinel,
        body=body,
        markdown=body["markdown_summary"],
        redaction={"applied": True, "profile": "standard"},
        metadata={"incident_count": 0, "device_count": 0, "network_count": 1},
    )
    envelope = load_stored_report_envelope(row)
    assert envelope is not None
    assert envelope.report_version == version
    assert isinstance(envelope.body, dict)
    assert envelope.body["executive_summary"] == sentinel
    # Opaque body must not gain a rewritten id or v3 fields.
    assert envelope.body.get("id") == f"stored-v{version}"
    assert "decision_summary" not in envelope.body
    assert "domain_details" not in envelope.body

    # Mutating the returned dict must not write back.
    mutated = envelope.body
    mutated["executive_summary"] = "MUTATED"
    mutated["id"] = "injected"
    row_again = repo.reports.get_report(row.id)
    assert row_again is not None
    assert hashlib.sha256(row_again.body_json.encode()).hexdigest() == digest_before or (
        parse_stored_body_json(row_again.body_json)["executive_summary"] == sentinel
    )
    parsed = parse_stored_body_json(row_again.body_json)
    assert parsed is not None
    assert parsed["executive_summary"] == sentinel
    assert parsed["id"] == f"stored-v{version}"
    assert row_again.body_markdown == body["markdown_summary"]


def test_malformed_legacy_json_fails_safely(tmp_path: Path):
    db = Database(tmp_path / "bad.sqlite")
    db.migrate()
    repo = Repository(db)
    bad = "{not-json"
    row = repo.reports.save_report(
        report_id="bad-row",
        format="json",
        scope="full",
        redaction_profile="standard",
        summary="bad",
        body={"placeholder": True},
        markdown="",
        redaction={},
        metadata={},
    )
    # Overwrite body_json with malformed content after insert.
    db.conn.execute(
        "UPDATE reports SET body_json = ? WHERE id = ?",
        (bad, row.id),
    )
    db.conn.commit()
    row2 = repo.reports.get_report(row.id)
    assert row2 is not None
    assert row2.body_json == bad
    assert load_stored_report_envelope(row2) is None
    row3 = repo.reports.get_report(row.id)
    assert row3 is not None
    assert row3.body_json == bad


def test_network_decision_parity_across_routes(mock_client: TestClient):
    dash = mock_client.get("/api/dashboard").json()["networks"]
    collection = mock_client.get("/api/networks").json()
    items = collection["items"] if isinstance(collection, dict) and "items" in collection else collection
    by_id_dash = {n["id"]: n for n in dash}
    by_id_col = {n["id"]: n for n in items}
    assert by_id_dash.keys() == by_id_col.keys()
    for network_id, dash_net in by_id_dash.items():
        col_net = by_id_col[network_id]
        detail = mock_client.get(f"/api/networks/{network_id}").json()
        for surface in (dash_net, col_net, detail):
            assert surface["decision"] == dash_net["decision"]
            assert surface["decision_summary"] == dash_net["decision_summary"]
            assert (
                surface["decision_summary"]["coverage_warning_count"]
                == dash_net["decision_summary"]["coverage_warning_count"]
            )
        v1 = mock_client.get(f"/api/v1/networks/{network_id}").json()
        assert v1["decision"] == dash_net["decision"]
        assert v1["decision_summary"] == dash_net["decision_summary"]


def test_superseded_lens_topics_use_configured_prefix():
    default = superseded_lens_discovery_topics("homeassistant")
    custom = superseded_lens_discovery_topics("ha_custom")
    assert len(default) == len(SUPERSEDED_LENS_DISCOVERY_ENTITY_KEYS)
    assert all(t.startswith("homeassistant/") for t in default)
    assert all(t.startswith("ha_custom/") for t in custom)
    for key in SUPERSEDED_LENS_DISCOVERY_ENTITY_KEYS:
        assert f"ha_custom/sensor/zigbeelens/{key}/config" in custom
        assert f"homeassistant/sensor/zigbeelens/{key}/config" in default
    # Current decision entity keys must not be in superseded set.
    assert "decision_status" not in SUPERSEDED_LENS_DISCOVERY_ENTITY_KEYS
    assert "unavailable_devices" not in SUPERSEDED_LENS_DISCOVERY_ENTITY_KEYS


def test_dashboard_forbidden_fields(mock_client: TestClient):
    dash = mock_client.get("/api/dashboard").json()
    _assert_forbidden_absent(dash)
    caps = mock_client.get("/api/capabilities").json()
    _assert_forbidden_absent(caps)
