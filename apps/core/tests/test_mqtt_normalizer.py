from zigbeelens.config.models import NetworkConfig
from zigbeelens.mqtt.models import RawMqttMessage
from zigbeelens.mqtt.normalizer import normalize_message


NETWORKS = [NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")]


def test_bridge_state_string():
    events = normalize_message(
        RawMqttMessage(topic="zigbee2mqtt/bridge/state", payload=b"online"),
        NETWORKS,
    )
    assert events[0].event_type == "bridge_state_seen"
    assert events[0].bridge_state == "online"


def test_bridge_state_json():
    events = normalize_message(
        RawMqttMessage(topic="zigbee2mqtt/bridge/state", payload=b'{"state":"offline"}'),
        NETWORKS,
    )
    assert events[0].bridge_state == "offline"


def test_bridge_devices_parsing():
    payload = b'[{"ieee_address":"0x00124b0024abcd01","friendly_name":"Laundry Plug","type":"Router"}]'
    events = normalize_message(
        RawMqttMessage(topic="zigbee2mqtt/bridge/devices", payload=payload),
        NETWORKS,
    )
    assert events[0].event_type == "device_inventory_seen"
    assert len(events[0].devices) == 1


def test_availability_json():
    events = normalize_message(
        RawMqttMessage(
            topic="zigbee2mqtt/Laundry Plug/availability",
            payload=b'{"state":"online"}',
        ),
        NETWORKS,
    )
    assert events[0].event_type == "device_availability_seen"
    assert events[0].availability == "online"


def test_malformed_json_does_not_crash():
    events = normalize_message(
        RawMqttMessage(topic="zigbee2mqtt/bridge/info", payload=b"{bad json"),
        NETWORKS,
    )
    assert events[0].event_type == "parse_error"


def test_device_payload_extracts_fields():
    events = normalize_message(
        RawMqttMessage(
            topic="zigbee2mqtt/Laundry Plug",
            payload=b'{"linkquality":76,"battery":55,"last_seen":"2026-06-14T10:00:00+10:00"}',
        ),
        NETWORKS,
    )
    assert events[0].device_fields["linkquality"] == 76
    assert events[0].device_fields["battery"] == 55


def _bridge_event(payload: dict):
    import json

    return normalize_message(
        RawMqttMessage(
            topic="zigbee2mqtt/bridge/event",
            payload=json.dumps(payload).encode(),
        ),
        NETWORKS,
    )


def test_bridge_interview_failed_from_status():
    events = _bridge_event(
        {
            "type": "device_interview",
            "data": {"ieee_address": "0xabc", "friendly_name": "Plug", "status": "failed"},
        }
    )
    assert events[0].event_type == "device_interview_failed"
    assert events[0].ieee_address == "0xabc"
    assert events[0].friendly_name == "Plug"


def test_bridge_interview_successful_from_status():
    events = _bridge_event(
        {
            "type": "device_interview",
            "data": {"ieee_address": "0xabc", "status": "successful"},
        }
    )
    assert events[0].event_type == "device_interview_success"


def test_bridge_interview_in_progress_from_status():
    events = _bridge_event(
        {
            "type": "device_interview",
            "data": {"ieee_address": "0xabc", "status": "in_progress"},
        }
    )
    assert events[0].event_type == "device_interview_started"


def test_bridge_interview_started_literal_status():
    events = _bridge_event(
        {
            "type": "device_interview",
            "data": {"ieee_address": "0xabc", "status": "started"},
        }
    )
    assert events[0].event_type == "device_interview_started"
    assert events[0].ieee_address == "0xabc"


def test_bridge_interview_without_status_starts():
    events = _bridge_event(
        {"type": "device_interview", "data": {"ieee_address": "0xabc"}}
    )
    assert events[0].event_type == "device_interview_started"


def test_unrelated_bridge_event_unchanged():
    events = _bridge_event(
        {
            "type": "device_announce",
            "data": {"ieee_address": "0xabc", "friendly_name": "Plug", "status": "failed"},
        }
    )
    assert events[0].event_type == "device_announced"
