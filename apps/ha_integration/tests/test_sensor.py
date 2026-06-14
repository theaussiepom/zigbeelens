"""Entity tests."""

from __future__ import annotations

from zigbeelens.binary_sensor import ZigbeeLensBinarySensor, BINARY_SENSORS
from zigbeelens.sensor import ZigbeeLensSensor, SUMMARY_SENSORS, _unknown_device_count


def test_overall_health_sensor(mock_coordinator):
    sensor = ZigbeeLensSensor(mock_coordinator, "entry1", SUMMARY_SENSORS[0])
    assert sensor.native_value == "incident"
    attrs = sensor.extra_state_attributes
    assert "current_finding" in attrs
    assert "top_affected_devices" not in attrs


def test_active_incident_binary_sensor(mock_coordinator):
    sensor = ZigbeeLensBinarySensor(mock_coordinator, "entry1", BINARY_SENSORS[0])
    assert sensor.is_on is True
    attrs = sensor.extra_state_attributes
    assert attrs["active_incident_count"] == 1


def test_collector_binary_sensor(mock_coordinator):
    sensor = ZigbeeLensBinarySensor(mock_coordinator, "entry1", BINARY_SENSORS[2])
    assert sensor.is_on is True


def test_unavailable_devices_count(mock_coordinator):
    sensor = ZigbeeLensSensor(
        mock_coordinator,
        "entry1",
        next(d for d in SUMMARY_SENSORS if d.key == "unavailable_devices"),
    )
    assert sensor.native_value == 4


def test_unique_ids_stable(mock_coordinator):
    sensor = ZigbeeLensSensor(mock_coordinator, "entry1", SUMMARY_SENSORS[0])
    assert sensor.unique_id == "entry1_overall_health"


def test_unknown_device_count_helper():
    dashboard = {
        "top_affected_devices": [{"health": {"primary": "unknown"}}],
        "recently_unstable": [],
        "weak_links": [],
        "low_batteries": [],
        "stale_devices": [],
    }
    assert _unknown_device_count(dashboard) == 1
