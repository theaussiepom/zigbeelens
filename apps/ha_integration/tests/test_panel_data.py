"""Tests for the redacted companion-panel summary builder."""

from __future__ import annotations

import json
from pathlib import Path

from zigbeelens.coordinator import ZigbeeLensCoordinatorData
from zigbeelens.panel_data import build_panel_summary

PANEL_JS = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "zigbeelens"
    / "panel"
    / "zigbeelens-panel.js"
)


def _data(sample_health, sample_dashboard, sample_config_status):
    return ZigbeeLensCoordinatorData(
        health=sample_health,
        dashboard=sample_dashboard,
        config_status=sample_config_status,
        core_version="0.1.0",
        collector_connected=True,
        last_update_success=True,
    )


def test_summary_connected_has_expected_fields(
    sample_health, sample_dashboard, sample_config_status
):
    data = _data(sample_health, sample_dashboard, sample_config_status)
    summary = build_panel_summary(data, core_url="http://192.168.100.5:8377", connected=True)

    assert summary["connected"] is True
    assert summary["core_url"] == "http://192.168.100.5:8377"
    assert summary["core_version"] == "0.1.0"
    assert summary["overall_health"] == "incident"
    assert summary["active_incident_count"] == 1
    assert summary["network_count"] == 1
    assert summary["device_count"] == 10
    assert summary["unavailable_devices"] == 4
    assert summary["router_risks"] == 1
    assert summary["collector_connected"] is True
    assert summary["current_finding"].startswith("4 devices")
    assert summary["networks"][0] == {
        "id": "home",
        "name": "Home",
        "bridge_state": "unknown",
        "device_count": 0,
        "unavailable_devices": 4,
        "router_risks": 1,
        "health": "incident",
    }


def test_summary_excludes_secrets(sample_health, sample_dashboard, sample_config_status):
    config_status = dict(sample_config_status)
    config_status["mqtt_server"] = "mqtt://user:supersecret@broker:1883"
    data = _data(sample_health, sample_dashboard, config_status)

    summary = build_panel_summary(data, core_url="http://core:8377", connected=True)
    serialized = json.dumps(summary).lower()

    assert "mqtt_server" not in summary
    assert "supersecret" not in serialized
    assert "broker" not in serialized
    assert "password" not in serialized


def test_summary_disconnected_is_calm():
    summary = build_panel_summary(
        None,
        core_url="http://192.168.100.5:8377",
        connected=False,
        last_exception="boom",
    )
    assert summary["connected"] is False
    assert summary["core_url"] == "http://192.168.100.5:8377"
    assert summary["error"] == "boom"
    assert summary["networks"] == []
    assert summary["device_count"] == 0


def test_panel_frontend_asset_default_summary_with_optional_embed():
    source = PANEL_JS.read_text(encoding="utf-8")
    assert PANEL_JS.exists()
    assert 'customElements.define("zigbeelens-panel"' in source
    assert "Try Embedded View" in source
    assert "Back to Summary" in source
    assert 'this._view = "summary"' in source
    assert 'target="_blank"' in source
    assert 'rel="noopener noreferrer"' in source
    assert "zigbeelens/panel_summary" in source
    assert "canEmbedDashboard" in source
    # Iframe exists only for optional embedded view, not on initial summary load.
    assert "<iframe" in source.lower()
    assert "embed_blocked" in source
