"""Tests for optional MQTT Discovery publishing."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from zigbeelens.config.models import (
    AppConfig,
    FeaturesConfig,
    ModeConfig,
    MqttDiscoveryConfig,
    NetworkConfig,
    StorageConfig,
)
from zigbeelens.mqtt_discovery.payloads import (
    all_discovery_entities,
    build_discovery_device,
    build_states_from_dashboard,
    discovery_config_payload,
    discovery_topic_for_entity,
    entity_catalog,
    state_payload,
)
from zigbeelens.mqtt_discovery.publisher import FakeDiscoveryPublisher
from zigbeelens.mqtt_discovery.service import MqttDiscoveryService, discovery_enabled
from zigbeelens.mqtt_discovery.topics import UnsafeMqttTopicError, sanitize_object_id, validate_publish_topic
from zigbeelens.services.data_service import DataService


def _config(db_path: Path, *, discovery: bool = True) -> AppConfig:
    return AppConfig(
        mode=ModeConfig(mock=True, default_scenario="four_devices_same_room_unavailable"),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(db_path)),
        features=FeaturesConfig(mqtt_discovery=discovery, mqtt_collector=False),
        mqtt_discovery=MqttDiscoveryConfig(enabled=True),
    )


def test_discovery_enabled_requires_both_flags():
    cfg = AppConfig(features=FeaturesConfig(mqtt_discovery=False))
    assert discovery_enabled(cfg) is False
    cfg = AppConfig(
        features=FeaturesConfig(mqtt_discovery=True),
        mqtt_discovery=MqttDiscoveryConfig(enabled=False),
    )
    assert discovery_enabled(cfg) is False
    cfg = AppConfig(
        features=FeaturesConfig(mqtt_discovery=True),
        mqtt_discovery=MqttDiscoveryConfig(enabled=True),
    )
    assert discovery_enabled(cfg) is True


@pytest.mark.parametrize(
    "topic",
    [
        "zigbee2mqtt/bridge/request/device/remove",
        "zigbee2mqtt/Lamp/set",
        "homeassistant/+/sensor/config",
        "zigbee2mqtt/bridge/state",
        "",
    ],
)
def test_validate_publish_topic_rejects_unsafe(topic: str):
    with pytest.raises(UnsafeMqttTopicError):
        validate_publish_topic(topic, zigbee_base_topics=("zigbee2mqtt",))


def test_validate_publish_topic_allows_zigbeelens_topics():
    validate_publish_topic("homeassistant/sensor/zigbeelens_overall_health/config")
    validate_publish_topic("zigbeelens/state/overall", zigbee_base_topics=("zigbee2mqtt",))


def test_sanitize_object_id():
    assert sanitize_object_id("home-2") == "home-2"
    assert sanitize_object_id("home 2!") == "home_2"


def test_overall_health_discovery_config():
    device = build_discovery_device(device_name="ZigbeeLens", core_version="0.1.0")
    entities = entity_catalog(
        topic_prefix="homeassistant",
        state_topic_prefix="zigbeelens",
        object_id_prefix="zigbeelens",
        availability="zigbeelens/status",
        device=device,
    )
    overall = next(e for e in entities if e.unique_id == "zigbeelens_overall_health")
    payload = discovery_config_payload(overall, "zigbeelens/status", device)
    assert payload["unique_id"] == "zigbeelens_overall_health"
    assert payload["state_topic"] == "zigbeelens/state/overall"
    assert payload["device"]["manufacturer"] == "ZigbeeLens"


def test_active_incident_binary_sensor_device_class():
    device = build_discovery_device(device_name="ZigbeeLens", core_version="0.1.0")
    entities = entity_catalog(
        topic_prefix="homeassistant",
        state_topic_prefix="zigbeelens",
        object_id_prefix="zigbeelens",
        availability="zigbeelens/status",
        device=device,
    )
    active = next(e for e in entities if e.unique_id == "zigbeelens_active_incident")
    payload = discovery_config_payload(active, "zigbeelens/status", device)
    assert payload["device_class"] == "problem"


def test_collector_binary_sensor_connectivity_class():
    device = build_discovery_device(device_name="ZigbeeLens", core_version="0.1.0")
    entities = entity_catalog(
        topic_prefix="homeassistant",
        state_topic_prefix="zigbeelens",
        object_id_prefix="zigbeelens",
        availability="zigbeelens/status",
        device=device,
    )
    collector = next(e for e in entities if e.unique_id == "zigbeelens_mqtt_collector_connected")
    payload = discovery_config_payload(collector, "zigbeelens/status", device)
    assert payload["device_class"] == "connectivity"


def test_per_network_unique_ids_stable(mock_dashboard):
    device = build_discovery_device(device_name="ZigbeeLens", core_version="0.1.0")
    entities = all_discovery_entities(
        topic_prefix="homeassistant",
        state_topic_prefix="zigbeelens",
        object_id_prefix="zigbeelens",
        availability="zigbeelens/status",
        device=device,
        dashboard=mock_dashboard,
    )
    ids = {e.unique_id for e in entities}
    assert "zigbeelens_network_home_health" in ids


def test_overall_state_payload(mock_dashboard):
    states = build_states_from_dashboard(
        mock_dashboard, core_version="0.1.0", collector_connected=True
    )
    payload = json.loads(state_payload(states["overall"]))
    assert payload["state"] == "incident"
    assert payload["active_incident_count"] == 1
    assert "current_finding" in payload
    assert "password" not in json.dumps(payload).lower()


def test_active_incident_on_off(mock_dashboard):
    states = build_states_from_dashboard(
        mock_dashboard, core_version="0.1.0", collector_connected=True
    )
    assert json.loads(state_payload(states["active_incident"]))["state"] == "ON"
    mock_dashboard.active_incident_count = 0
    states = build_states_from_dashboard(
        mock_dashboard, core_version="0.1.0", collector_connected=True
    )
    assert json.loads(state_payload(states["active_incident"]))["state"] == "OFF"


def test_discovery_service_publishes_configs_and_states(tmp_path: Path):
    db_path = tmp_path / "discovery.sqlite"
    config = _config(db_path, discovery=True)
    from zigbeelens.app.context import bootstrap, reset_context

    reset_context()
    with patch("zigbeelens.app.context.start_discovery", return_value=None):
        ctx = bootstrap(config=config)
    publisher = FakeDiscoveryPublisher(config=config)
    service = MqttDiscoveryService(ctx, publisher=publisher)
    service.start()

    topics = [record.topic for record in publisher.published]
    assert any(t.startswith("homeassistant/sensor/") and t.endswith("/config") for t in topics)
    assert "zigbeelens/state/overall" in topics
    assert "zigbeelens/status" in topics
    assert not any("/bridge/request/" in t for t in topics)
    assert not any(t.endswith("/set") for t in topics)
    assert service.status.published_entities_count > 0

    service.stop()
    reset_context()


def test_disabled_discovery_publishes_nothing(tmp_path: Path):
    db_path = tmp_path / "disabled.sqlite"
    config = _config(db_path, discovery=False)
    from zigbeelens.app.context import bootstrap, reset_context

    reset_context()
    ctx = bootstrap(config=config)
    assert ctx.discovery is None
    reset_context()


def test_publisher_failure_does_not_crash_core(tmp_path: Path):
    db_path = tmp_path / "fail.sqlite"
    config = _config(db_path, discovery=True)
    from zigbeelens.app.context import bootstrap, reset_context

    reset_context()
    with patch("zigbeelens.mqtt_discovery.service.SafeMqttPublisher.connect", side_effect=RuntimeError("boom")):
        ctx = bootstrap(config=config)
    assert ctx.data.dashboard() is not None
    reset_context()


def test_collector_client_still_does_not_publish(tmp_path: Path):
    from zigbeelens.db.connection import Database
    from zigbeelens.mqtt.client import FakeMqttClient
    from zigbeelens.mqtt.collector import build_collector
    from zigbeelens.mqtt.ingestion import MqttIngestionService
    from zigbeelens.storage.repository import Repository

    db_path = tmp_path / "collector.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = AppConfig(
        mode=ModeConfig(mock=False),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(db_path)),
        features=FeaturesConfig(mqtt_discovery=True),
    )
    repo.sync_networks(config.networks)
    ingestion = MqttIngestionService(config, repo)
    collector = build_collector(config, repo, ingestion, client=None)
    client = FakeMqttClient(collector._handle_message)
    collector._client = client
    collector.start()
    client.inject("zigbee2mqtt/bridge/state", "online")
    assert client.published == []
    db.close()


def test_cleanup_deletes_discovery_configs(tmp_path: Path):
    db_path = tmp_path / "cleanup.sqlite"
    config = _config(db_path, discovery=True)
    from zigbeelens.app.context import bootstrap, reset_context

    reset_context()
    with patch("zigbeelens.app.context.start_discovery", return_value=None):
        ctx = bootstrap(config=config)
    publisher = FakeDiscoveryPublisher(config=config)
    service = MqttDiscoveryService(ctx, publisher=publisher)
    service.start()
    service.cleanup_discovery_configs()
    deleted = [r for r in publisher.published if r.payload == "" and r.retain]
    assert deleted
    reset_context()


@pytest.fixture
def mock_dashboard():
    config = AppConfig(mode=ModeConfig(mock=True, default_scenario="four_devices_same_room_unavailable"))
    from zigbeelens.db.connection import Database
    from zigbeelens.diagnostics.incidents.service import IncidentDiagnosticService
    from zigbeelens.diagnostics.service import HealthDiagnosticService
    from zigbeelens.storage.repository import Repository

    db = Database(":memory:")
    db.migrate()
    repo = Repository(db)
    health = HealthDiagnosticService(config, repo)
    incidents = IncidentDiagnosticService(config, repo)
    data = DataService(config, repo, health, incidents)
    return data.dashboard()
