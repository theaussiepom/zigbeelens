"""Phase 6: redacted diagnostic report tests."""

from __future__ import annotations

import json

import yaml
from fastapi.testclient import TestClient

from zigbeelens.config.models import AppConfig, ReportingConfig
from zigbeelens.config.redaction import REDACTED
from zigbeelens.db.connection import Database
from zigbeelens.schemas import RedactionOptions, RedactionProfile, ReportRequest
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
    assert detail["report_version"] == 3
    assert detail["decision_summary"]["subject_count"] >= 0
    assert detail["limitations"]
    domain_devices = detail["domain_details"]["devices"]
    assert detail["raw_counts"]["devices_included"] == len(domain_devices)
    assert "health_snapshot" not in detail
    assert "executive_summary" not in detail


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
    assert res.text.startswith("# ZigbeeLens Evidence Report")
    assert "## Decision summary" in res.text
    assert "## Executive summary" not in res.text
    assert "## Health summary" not in res.text
    assert "## Unhealthy devices" not in res.text
    assert "## Limitations" in res.text


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
    networks = detail["domain_details"]["networks"]
    devices = detail["domain_details"]["devices"]
    assert all(n["id"] == network_id for n in networks)
    assert all(d["network_id"] == network_id for d in devices)


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
    assert len(detail["domain_details"]["devices"]) == 1
    assert len(detail["domain_details"]["device_details"]) == 1


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
    for d in detail["domain_details"]["devices"]:
        assert d["ieee_address"].startswith("ieee_")


def test_public_safe_redacts_identifiers(mock_client: TestClient):
    detail = mock_client.get("/api/reports/preview", params={"profile": "public_safe"}).json()
    assert detail["redaction"]["profile"] == "public_safe"
    assert detail["redaction"]["friendly_names"] == "labeled"
    assert detail["redaction"]["network_names"] == "labeled"
    for d in detail["domain_details"]["devices"]:
        assert d["friendly_name"].startswith("device_")
        assert d["ieee_address"].startswith("ieee_")
    for n in detail["domain_details"]["networks"]:
        assert n["name"].startswith("network_")


def test_strict_redacts_host_ip_friendly_network(mock_client: TestClient):
    detail = mock_client.get("/api/reports/preview", params={"profile": "strict"}).json()
    red = detail["redaction"]
    assert red["hostnames"] is True
    assert red["ip_addresses"] is True
    assert red["friendly_names"] == "hashed"
    assert red["network_names"] == "hashed"
    for d in detail["domain_details"]["devices"]:
        assert d["friendly_name"].startswith("device_")


def test_stable_hashes_consistent_within_report(mock_client: TestClient):
    detail = mock_client.get("/api/reports/preview", params={"profile": "public_safe"}).json()
    incidents = detail["incidents"]
    if not incidents or not incidents[0]["affected_devices"]:
        return
    affected = incidents[0]["affected_devices"][0]
    matching = [
        d
        for d in detail["domain_details"]["devices"]
        if d["ieee_address"] == affected["ieee_address"]
    ]
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


def test_ha_metadata_redaction_profiles_and_free_text_are_safe():
    raw = {
        "networks": [],
        "devices": [
            {
                "friendly_name": "z2m_kitchen_lamp",
                "home_assistant_name": "Kitchen Lamp",
                "home_assistant_area_name": "Kitchen",
                "ha_area": "Kitchen",
                "ieee_address": "0x00124b0024abc999",
                "ha_device_name": "Kitchen Lamp",
                "area_name": "Kitchen",
                "area_id": "area-kitchen",
                "ha_device_id": "ha-registry-kitchen",
                "entity_id": "light.kitchen_lamp",
                "narrative": (
                    "Kitchen Lamp in Kitchen uses area-kitchen, "
                    "ha-registry-kitchen, light.kitchen_lamp and "
                    "0x00124b0024abc999."
                ),
            }
        ],
    }
    prohibited_identifiers = (
        "area-kitchen",
        "ha-registry-kitchen",
        "light.kitchen_lamp",
        "0x00124b0024abc999",
    )

    for profile in (
        RedactionProfile.standard,
        RedactionProfile.strict,
        RedactionProfile.public_safe,
    ):
        resolved = resolve_redaction(RedactionOptions(profile=profile))
        out = Redactor(resolved, salt="ha-redaction-test").redact(raw)
        device = out["devices"][0]
        blob = json.dumps(out)
        for identifier in prohibited_identifiers:
            assert identifier not in blob
        assert device["area_id"].startswith("area_id_")
        assert device["ha_device_id"].startswith("ha_device_")
        assert device["entity_id"].startswith("entity_")
        assert device["ieee_address"].startswith("ieee_")
        assert device["ha_area"] == device["home_assistant_area_name"]

        if profile is RedactionProfile.standard:
            assert device["home_assistant_name"] == "Kitchen Lamp"
            assert device["home_assistant_area_name"] == "Kitchen"
        elif profile is RedactionProfile.strict:
            assert device["home_assistant_name"].startswith("device_")
            assert device["home_assistant_area_name"].startswith("area_")
            assert "Kitchen Lamp" not in blob
            assert "Kitchen" not in blob
        else:
            assert device["home_assistant_name"].startswith("device_")
            assert device["home_assistant_area_name"].startswith("area_")
            for prohibited in ("Kitchen Lamp", "Kitchen"):
                assert prohibited not in blob


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


def test_redactor_redacts_password_only_mqtt_userinfo():
    sentinel = "report-credential-sentinel"
    resolved = resolve_redaction(RedactionOptions(profile=RedactionProfile.standard))
    redactor = Redactor(resolved)
    out = redactor.redact(
        {
            "networks": [],
            "config_summary": {
                "mqtt": {
                    "server": f"mqtt://:{sentinel}@broker:1883",
                    "mqtt_server": f"mqtt://:{sentinel}@broker:1883/path",
                }
            },
        }
    )
    blob = json.dumps(out)
    assert sentinel not in blob
    server = out["config_summary"]["mqtt"]["server"]
    mqtt_server = out["config_summary"]["mqtt"]["mqtt_server"]
    assert sentinel not in server
    assert sentinel not in mqtt_server
    assert "broker" in server
    assert "1883" in server
    assert "***" in server


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
    timeline = detail.events_or_timeline or []
    assert len(timeline) <= 1


def test_mock_mode_report_still_works(mock_client: TestClient):
    detail = mock_client.get("/api/reports/preview", params={"scenario": DEFAULT}).json()
    assert detail["raw_counts"]["devices_included"] >= 1
    assert detail["decision_summary"] is not None


def test_empty_state_report_valid(live_client: TestClient):
    preview = live_client.get("/api/reports/preview").json()
    assert preview["decision_summary"]["overall_status"]
    assert preview["limitations"]
    created = live_client.post("/api/reports", json={"format": "json"}).json()
    assert created["id"]
    fetched = live_client.get(f"/api/reports/{created['id']}")
    assert fetched.status_code == 200


def test_v3_report_canonical_fields(mock_client: TestClient):
    detail = mock_client.get("/api/reports/preview", params={"profile": "public_safe"}).json()
    assert detail["product"] == "ZigbeeLens"
    assert detail["version"]
    assert detail["generated_at"]
    assert detail["redaction"]["profile"] == "public_safe"
    assert detail["config_summary"]["mode"] in {"mock", "live"}
    assert detail["report_version"] == 3
    for forbidden in (
        "executive_summary",
        "health_summary",
        "summary",
        "timeline",
        "networks",
        "devices",
        "health_snapshot",
        "diagnostic_conclusions",
        "site",
        "mode",
        "redaction_profile",
        "active_incidents",
        "collector",
        "router_risks",
        "device_details",
    ):
        assert forbidden not in detail
    assert detail["decision_summary"] is not None
    assert detail["device_stories"]
    assert detail["collector_status"]["mqtt_collector"] in {
        "connected",
        "disconnected",
        "disabled",
    }
    assert detail["domain_details"]["networks"]
    assert detail["events_or_timeline"] is not None
    if detail["incidents"]:
        entity = detail["incidents"][0]["affected_devices"][0]
        assert entity.get("decision")
        assert "lens_bucket" not in entity
        assert "health_primary" not in entity
    blob = json.dumps(detail)
    assert '"secret"' not in blob
    assert ":secret@" not in blob
