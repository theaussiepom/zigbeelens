from zigbeelens.config.models import NetworkConfig
from zigbeelens.mqtt.models import TopicKind
from zigbeelens.mqtt.topics import classify_topic, match_network, subscription_topics


NETWORKS = [
    NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
    NetworkConfig(id="home2", name="Home 2", base_topic="zigbee2mqtt-home2"),
]


def test_classify_bridge_state():
    c = classify_topic("zigbee2mqtt/bridge/state", NETWORKS)
    assert c is not None
    assert c.network_id == "home"
    assert c.kind == TopicKind.bridge_state


def test_classify_device_payload():
    c = classify_topic("zigbee2mqtt/Kitchen Sensor", NETWORKS)
    assert c.kind == TopicKind.device_payload
    assert c.friendly_name == "Kitchen Sensor"


def test_classify_availability():
    c = classify_topic("zigbee2mqtt/Kitchen Sensor/availability", NETWORKS)
    assert c.kind == TopicKind.device_availability


def test_bridge_not_device_payload():
    c = classify_topic("zigbee2mqtt/bridge/state", NETWORKS)
    assert c.kind != TopicKind.device_payload


def test_request_topic_ignored():
    c = classify_topic("zigbee2mqtt/bridge/request/permit_join", NETWORKS)
    assert c.kind == TopicKind.ignored


def test_multi_network_longest_base_topic_match():
    net = match_network("zigbee2mqtt-home2/bridge/state", NETWORKS)
    assert net is not None
    assert net.id == "home2"


def test_subscription_topics_per_network():
    topics = subscription_topics("zigbee2mqtt")
    assert "zigbee2mqtt/bridge/state" in topics
    assert "zigbee2mqtt/+" in topics
    assert "zigbee2mqtt/+/availability" in topics
