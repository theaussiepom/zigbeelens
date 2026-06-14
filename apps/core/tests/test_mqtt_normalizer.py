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
