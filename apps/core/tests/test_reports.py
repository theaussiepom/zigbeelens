"""Phase 6: redacted diagnostic report tests."""

from __future__ import annotations

import json

import yaml
from fastapi.testclient import TestClient

from zigbeelens.config.models import AppConfig, ReportingConfig
from zigbeelens.config.redaction import REDACTED
from zigbeelens.db.connection import Database
from zigbeelens.schemas import RedactionOptions, RedactionProfile, ReportRequest, ReportScope
from zigbeelens.services.data_service import DataService
from zigbeelens.services.report_redaction import (
    Redactor,
    is_secret_key,
    resolve_redaction,
)
from zigbeelens.services.reports import generate_report
from zigbeelens.storage.repository import Repository

DEFAULT = "four_devices_same_room_unavailable"


def _mock_data_service(tmp_path) -> tuple[DataService, AppConfig]:
    db = Database(tmp_path / "reports.sqlite")
    db.migrate()
    repo = Repository(db)
    config = AppConfig()
    config.mode.mock = True
    config.mode.default_scenario = DEFAULT
    return DataService(config, repo), config


# -- format generation ---------------------------------------------------


def test_full_json_report(mock_client: TestClient):
    res = mock_client.post("/api/reports", json={"format": "json", "scope": "full"})
    assert res.status_code == 200
    summary = res.json()
    assert summary["scope"] == "full"
    assert summary["format"] == "json"
    detail = mock_client.get(f"/api/reports/{summary['id']}").json()
    assert detail["product"] == "ZigbeeLens"
    assert detail["report_version"] == 1
    assert detail["summary"]["networks_monitored"] >= 1
    assert detail["limitations"]
    assert detail["raw_counts"]["devices_included"] == len(detail["devices"])


def test_full_yaml_report_downloads(mock_client: TestClient):
    summary = mock_client.post("/api/reports", json={"format": "yaml", "scope": "full"}).json()
    res = mock_client.get(f"/api/reports/{summary['id']}/download")
    assert res.status_code == 200
    assert "yaml" in res.headers["content-type"]
    assert ".yaml" in res.headers["content-disposition"]
    parsed = yaml.safe_load(res.text)
    assert parsed["product"] == "ZigbeeLens"


def test_markdown_report_downloads(mock_client: TestClient):
    summary = mock_client.post("/api/reports", json={"format": "markdown", "scope": "full"}).json()
    res = mock_client.get(f"/api/reports/{summary['id']}/download")
    assert res.status_code == 200
    assert "markdown" in res.headers["content-type"]
    assert res.text.startswith("# ZigbeeLens diagnostic report")
    assert "## Known limitations" in res.text


def test_json_download_content_type(mock_client: TestClient):
    summary = mock_client.post("/api/reports", json={"format": "json"}).json()
    res = mock_client.get(f"/api/reports/{summary['id']}/download")
    assert "application/json" in res.headers["content-type"]
    json.loads(res.text)


# -- scoped reports ------------------------------------------------------


def test_incident_scoped_report(mock_client: TestClient):
    incidents = mock_client.get("/api/incidents").json()["items"]
    assert incidents, "default scenario should have incidents"
    incident_id = incidents[0]["id"]
    detail = mock_client.get(
        "/api/reports/preview",
        params={"scope": "incident", "incident_id": incident_id},
    ).json()
    assert detail["scope"] == "incident"
    assert len(detail["incidents"]) == 1
    assert detail["incidents"][0]["id"] == incident_id


def test_network_scoped_report(mock_client: TestClient):
    networks = mock_client.get("/api/networks").json()["items"]
    network_id = networks[0]["id"]
    detail = mock_client.get(
        "/api/reports/preview",
        params={"scope": "network", "network_id": network_id},
    ).json()
    assert detail["scope"] == "network"
    assert all(n["id"] == network_id for n in detail["networks"])
    assert all(d["network_id"] == network_id for d in detail["devices"])


def test_device_scoped_report(mock_client: TestClient):
    devices = mock_client.get("/api/devices").json()["items"]
    target = devices[0]
    detail = mock_client.get(
        "/api/reports/preview",
        params={
            "scope": "device",
            "device": target["ieee_address"],
            "network_id": target["network_id"],
        },
    ).json()
    assert detail["scope"] == "device"
    assert len(detail["devices"]) == 1
    assert len(detail["device_details"]) == 1


# -- persistence ---------------------------------------------------------


def test_report_persisted_and_listed(mock_client: TestClient):
    created = mock_client.post("/api/reports", json={"format": "json"}).json()
    listing = mock_client.get("/api/reports").json()
    assert any(item["id"] == created["id"] for item in listing)
    item = next(i for i in listing if i["id"] == created["id"])
    assert item["redaction_profile"] == "standard"
    assert item["format"] == "json"


def test_report_delete(mock_client: TestClient):
    created = mock_client.post("/api/reports", json={"format": "json"}).json()
    res = mock_client.delete(f"/api/reports/{created['id']}")
    assert res.status_code == 200
    assert mock_client.get(f"/api/reports/{created['id']}").status_code == 404


# -- redaction profiles --------------------------------------------------


def test_standard_redaction_hashes_ieee_preserves_names(mock_client: TestClient):
    detail = mock_client.get("/api/reports/preview", params={"profile": "standard"}).json()
    assert detail["redaction"]["profile"] == "standard"
    assert detail["redaction"]["ieee_addresses_hashed"] is True
    assert detail["redaction"]["friendly_names"] == "preserved"
    for d in detail["devices"]:
        assert d["ieee_address"].startswith("ieee_")


def test_public_safe_redacts_identifiers(mock_client: TestClient):
    detail = mock_client.get("/api/reports/preview", params={"profile": "public_safe"}).json()
    assert detail["redaction"]["profile"] == "public_safe"
    assert detail["redaction"]["friendly_names"] == "labeled"
    assert detail["redaction"]["network_names"] == "labeled"
    for d in detail["devices"]:
        assert d["friendly_name"].startswith("device_")
        assert d["ieee_address"].startswith("ieee_")
    for n in detail["networks"]:
        assert n["name"].startswith("network_")


def test_strict_redacts_host_ip_friendly_network(mock_client: TestClient):
    detail = mock_client.get("/api/reports/preview", params={"profile": "strict"}).json()
    red = detail["redaction"]
    assert red["hostnames"] is True
    assert red["ip_addresses"] is True
    assert red["friendly_names"] == "hashed"
    assert red["network_names"] == "hashed"
    for d in detail["devices"]:
        assert d["friendly_name"].startswith("device_")


def test_stable_hashes_consistent_within_report(mock_client: TestClient):
    detail = mock_client.get("/api/reports/preview", params={"profile": "public_safe"}).json()
    incidents = detail["incidents"]
    if not incidents or not incidents[0]["affected_devices"]:
        return
    affected = incidents[0]["affected_devices"][0]
    matching = [d for d in detail["devices"] if d["ieee_address"] == affected["ieee_address"]]
    assert matching, "hashed ieee in incident should match the device's hashed ieee"


# -- no secret leakage ---------------------------------------------------


def test_no_secret_leakage(mock_client: TestClient):
    for profile in ("standard", "strict", "public_safe"):
        detail = mock_client.get("/api/reports/preview", params={"profile": profile}).json()
        blob = json.dumps(detail)
        # conftest configures mqtt password "secret" and server creds.
        assert '"secret"' not in blob
        assert ":secret@" not in blob
        assert "network_key" not in blob
        server = detail["config_summary"]["mqtt"]["server"]
        assert "***" in server or "redacted" in server


def test_secret_key_detection():
    for key in (
        "password",
        "pass",
        "token",
        "secret",
        "network_key",
        "api_key",
        "access_token",
        "refresh_token",
        "authorization",
        "client_secret",
        "device_token",
    ):
        assert is_secret_key(key), key
    for key in ("linkquality", "key_press", "keyboard", "battery", "extended_pan_id", "name"):
        assert not is_secret_key(key), key


def test_public_safe_preserves_device_type_when_friendly_name_collides():
    """Friendly-name scrubbing must not corrupt enum fields like device_type."""
    resolved = resolve_redaction(RedactionOptions(profile=RedactionProfile.public_safe))
    redactor = Redactor(resolved)
    out = redactor.redact(
        {
            "networks": [],
            "devices": [
                {
                    "friendly_name": "Router",
                    "device_type": "Router",
                    "power_source": "Mains",
                    "ieee_address": "0x00158d0001a2b3c4",
                },
                {
                    "friendly_name": "Battery sensor",
                    "device_type": "EndDevice",
                    "power_source": "Battery",
                    "ieee_address": "0x00158d0005d6e7f8",
                },
            ],
        }
    )
    assert out["devices"][0]["friendly_name"].startswith("device_")
    assert out["devices"][0]["device_type"] == "Router"
    assert out["devices"][1]["device_type"] == "EndDevice"
    assert out["devices"][1]["power_source"] == "Battery"


def test_redactor_redacts_secret_keys_keeps_linkquality():
    resolved = resolve_redaction(RedactionOptions(profile=RedactionProfile.standard))
    redactor = Redactor(resolved)
    out = redactor.redact(
        {
            "networks": [],
            "password": "hunter2",
            "authorization": "Bearer xyz",
            "network_key": "0xABCDEF",
            "nested": {"api_key": "k", "linkquality": 42},
            "linkquality": 77,
        }
    )
    assert out["password"] == REDACTED
    assert out["authorization"] == REDACTED
    assert out["network_key"] == REDACTED
    assert out["nested"]["api_key"] == REDACTED
    assert out["nested"]["linkquality"] == 42
    assert out["linkquality"] == 77


# -- limits & empty / live ----------------------------------------------


def test_report_limits_enforced(tmp_path):
    data, config = _mock_data_service(tmp_path)
    reporting = ReportingConfig(max_recent_events=1)
    detail = generate_report(
        data=data,
        config=config,
        reporting=reporting,
        collector={},
        request=ReportRequest(),
        scenario=DEFAULT,
    )
    assert len(detail.timeline) <= 1


def test_mock_mode_report_still_works(mock_client: TestClient):
    detail = mock_client.get("/api/reports/preview", params={"scenario": DEFAULT}).json()
    assert detail["summary"]["total_devices"] >= 1


def test_empty_state_report_valid(live_client: TestClient):
    preview = live_client.get("/api/reports/preview").json()
    assert preview["summary"]["overall_state"]
    assert preview["limitations"]
    created = live_client.post("/api/reports", json={"format": "json"}).json()
    assert created["id"]
    fetched = live_client.get(f"/api/reports/{created['id']}")
    assert fetched.status_code == 200
