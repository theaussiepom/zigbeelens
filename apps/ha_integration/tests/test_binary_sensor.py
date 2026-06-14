"""Binary sensor tests."""

from __future__ import annotations

from zigbeelens.binary_sensor import ZigbeeLensBinarySensor, BINARY_SENSORS
from zigbeelens.coordinator import ZigbeeLensCoordinatorData


def test_core_connected_binary_sensor(mock_coordinator):
    sensor = ZigbeeLensBinarySensor(mock_coordinator, "entry1", BINARY_SENSORS[1])
    assert sensor.is_on is True
    attrs = sensor.extra_state_attributes
    assert attrs["core_url"] == "http://localhost:8377"


def test_active_incident_off_when_none(mock_coordinator, sample_health, sample_config_status):
    dashboard = dict(mock_coordinator.data.dashboard)
    dashboard["active_incident_count"] = 0
    mock_coordinator.data = ZigbeeLensCoordinatorData(
        health=sample_health,
        dashboard=dashboard,
        config_status=sample_config_status,
        core_version="0.1.0",
        collector_connected=True,
        last_update_success=True,
    )
    sensor = ZigbeeLensBinarySensor(mock_coordinator, "entry1", BINARY_SENSORS[0])
    assert sensor.is_on is False
