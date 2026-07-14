"""Shared fixtures for ZigbeeLens HA integration tests."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "custom_components"
if str(COMPONENTS) not in sys.path:
    sys.path.insert(0, str(COMPONENTS))

from zigbeelens.coordinator import ZigbeeLensCoordinatorData, ZigbeeLensDataUpdateCoordinator


@pytest.fixture
def sample_health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "uptime_seconds": 120,
        "config_loaded": True,
        "mock_mode": False,
        "database": "ok",
        "migration_version": 5,
        "collector": {
            "enabled": True,
            "connected": True,
            "subscribed_topics_count": 4,
            "last_message_at": "2026-06-14T12:00:00+00:00",
            "last_error": None,
        },
    }


@pytest.fixture
def sample_dashboard():
    return {
        "generated_at": "2026-06-14T12:00:00+00:00",
        "overall_severity": "incident",
        "active_incident_count": 1,
        "watching_incident_count": 0,
        "current_finding": {
            "classification": "correlated_device_unavailability",
            "severity": "incident",
            "scope": "mesh_segment",
            "confidence": "medium",
            "summary": "4 devices became unavailable within 94 seconds.",
            "evidence": [],
            "counter_evidence": [],
            "limitations": [],
        },
        "networks": [
            {
                "id": "home",
                "name": "Home",
                "base_topic": "zigbee2mqtt",
                "unavailable_count": 4,
                "incident_state": "incident",
                "health": {"primary": "unavailable", "severity": "incident"},
            }
        ],
        "top_affected_devices": [],
        "router_risks": [{"network_id": "home", "friendly_name": "router"}],
        "recently_unstable": [{"health": {"primary": "recently_unstable"}}],
        "weak_links": [],
        "low_batteries": [],
        "stale_devices": [],
        "recent_timeline": [],
        "investigation_priorities": [],
        "data_coverage_warnings": [],
        "health_snapshot": {
            "timestamp": "2026-06-14T12:00:00+00:00",
            "overall_severity": "incident",
            "overall_health": "unavailable",
            "network_count": 1,
            "device_count": 10,
            "unavailable_count": 4,
            "incident_count": 1,
            "networks": [],
        },
    }


@pytest.fixture
def sample_config_status():
    return {
        "version": "0.1.0",
        "uptime_seconds": 120,
        "mqtt_connected": True,
        "mqtt_server": "mqtt://broker:1883",
        "configured_networks": [{"id": "home", "name": "Home", "base_topic": "zigbee2mqtt"}],
        "storage_path": "/data/zigbeelens.sqlite",
        "storage_ready": True,
        "retention_days": 7,
        "features": {"mqtt_collector": True},
        "data_mode": "live",
        "mock_mode": False,
    }


@pytest.fixture
def mock_coordinator(sample_health, sample_dashboard, sample_config_status):
    """Coordinator stub with populated data — avoids HA frame setup in unit tests."""
    coordinator = MagicMock(spec=ZigbeeLensDataUpdateCoordinator)
    coordinator.data = ZigbeeLensCoordinatorData(
        health=sample_health,
        dashboard=sample_dashboard,
        config_status=sample_config_status,
        core_version="0.1.0",
        collector_connected=True,
        last_update_success=True,
    )
    coordinator.last_update_success = True
    coordinator.last_exception = None
    coordinator.client = MagicMock(core_url="http://localhost:8377")
    return coordinator
