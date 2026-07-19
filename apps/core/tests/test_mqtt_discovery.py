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
    attributes_payload,
    build_discovery_device,
    build_states_from_dashboard,
    discovery_config_payload,
    discovery_topic_for_entity,
    entity_catalog,
    state_payload,
)
from zigbeelens.mqtt_discovery.publisher import FakeDiscoveryPublisher
from zigbeelens.mqtt_discovery.service import MqttDiscoveryService, discovery_enabled
from zigbeelens.mqtt_discovery.topics import (
    LEGACY_DISCOVERY_TOPICS,
    UnsafeMqttTopicError,
    sanitize_object_id,
    validate_publish_topic,
)
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
    validate_publish_topic("homeassistant/sensor/zigbeelens/decision_status/config")
    validate_publish_topic(
        "zigbeelens/summary/decision_status/state", zigbee_base_topics=("zigbee2mqtt",)
    )


def test_sanitize_object_id():
    assert sanitize_object_id("home-2") == "home-2"
    assert sanitize_object_id("home 2!") == "home_2"


def test_decision_discovery_config_uses_clean_topic_pattern():
    device = build_discovery_device(device_name="ZigbeeLens", core_version="0.1.0")
    entities = entity_catalog(
        topic_prefix="homeassistant",
        state_topic_prefix="zigbeelens",
        object_id_prefix="zigbeelens",
        availability="zigbeelens/status",
        device=device,
    )
    decision = next(e for e in entities if e.unique_id == "zigbeelens_decision_status")
    payload = discovery_config_payload(decision, "zigbeelens/status", device)
    assert payload["unique_id"] == "zigbeelens_decision_status"
    assert payload["state_topic"] == "zigbeelens/summary/decision_status/state"
    assert payload["json_attributes_topic"] == "zigbeelens/summary/decision_status/attributes"
    assert payload["device"]["identifiers"] == ["zigbeelens_core"]
    assert discovery_topic_for_entity("homeassistant", decision) == (
        "homeassistant/sensor/zigbeelens/decision_status/config"
    )


def test_summary_entity_catalog_has_six_global_entities():
    device = build_discovery_device(device_name="ZigbeeLens", core_version="0.1.0")
    entities = entity_catalog(
        topic_prefix="homeassistant",
        state_topic_prefix="zigbeelens",
        object_id_prefix="zigbeelens",
        availability="zigbeelens/status",
        device=device,
    )
    assert len(entities) == 6
    assert {entity.unique_id for entity in entities} == {
        "zigbeelens_decision_status",
        "zigbeelens_review_first",
        "zigbeelens_worth_reviewing",
        "zigbeelens_coverage_warnings",
        "zigbeelens_active_incidents",
        "zigbeelens_unavailable",
    }


def test_decision_state_payload_attributes(mock_dashboard):
    states = build_states_from_dashboard(
        mock_dashboard,
        core_version="0.1.0",
        collector_connected=True,
        mock_mode=True,
    )
    decision_state = states["decision_status"]
    assert decision_state.state in {
        "review_first",
        "worth_reviewing",
        "improve_data_coverage",
        "watch",
        "changed",
        "informational",
        "no_notable_change",
        "data_unavailable",
    }
    attrs = json.loads(attributes_payload(decision_state))
    assert attrs["product"] == "zigbeelens"
    assert attrs["version"] == "0.1.0"
    assert attrs["decision_contract_version"] == 2
    assert "lens_bucket" not in attrs
    assert attrs["redaction_profile"] == "public_safe"
    assert "password" not in json.dumps(attrs).lower()


def test_count_entities_use_numeric_state_when_observable(mock_dashboard):
    states = build_states_from_dashboard(
        mock_dashboard,
        core_version="0.1.0",
        collector_connected=True,
        mock_mode=True,
    )
    assert state_payload(states["review_first"]).isdigit() or state_payload(
        states["review_first"]
    ) == "unknown"


def test_count_entities_unknown_when_collector_offline_live_mode(mock_dashboard):
    states = build_states_from_dashboard(
        mock_dashboard,
        core_version="0.1.0",
        collector_connected=False,
        mock_mode=False,
    )
    assert state_payload(states["review_first"]) == "unknown"
    assert state_payload(states["unavailable"]) == "unknown"
    assert state_payload(states["decision_status"]) == "data_unavailable"


def test_discovery_service_publishes_clean_topics(tmp_path: Path):
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
    assert "homeassistant/sensor/zigbeelens/decision_status/config" in topics
    assert "zigbeelens/summary/decision_status/state" in topics
    assert "zigbeelens/summary/decision_status/attributes" in topics
    assert "zigbeelens/status" in topics
    # Superseded Lens configs must be tombstoned (empty retained).
    from zigbeelens.mqtt_discovery.topics import SUPERSEDED_LENS_DISCOVERY_TOPICS

    for topic in SUPERSEDED_LENS_DISCOVERY_TOPICS:
        assert topic in topics
    assert not any("/bridge/request/" in t for t in topics)
    assert not any(t.endswith("/set") for t in topics)
    assert service.status.published_entities_count == 6

    service.stop()
    reset_context()


def test_legacy_discovery_topics_documented():
    assert "homeassistant/sensor/zigbeelens_overall_health/config" in LEGACY_DISCOVERY_TOPICS
    from zigbeelens.mqtt_discovery.topics import SUPERSEDED_LENS_DISCOVERY_TOPICS

    assert "homeassistant/sensor/zigbeelens/health/config" in SUPERSEDED_LENS_DISCOVERY_TOPICS


def test_custom_discovery_prefix_tombstones_superseded_lens(tmp_path: Path):
    from zigbeelens.app.context import bootstrap, reset_context
    from zigbeelens.mqtt_discovery.topics import (
        SUPERSEDED_LENS_DISCOVERY_ENTITY_KEYS,
        superseded_lens_discovery_topics,
    )

    db_path = tmp_path / "custom-prefix.sqlite"
    config = _config(db_path, discovery=True)
    config.mqtt_discovery.topic_prefix = "ha_custom"
    reset_context()
    ctx = bootstrap(config=config)
    publisher = FakeDiscoveryPublisher(config=config)
    service = MqttDiscoveryService(ctx, publisher=publisher)
    service.start()

    topics = [record.topic for record in publisher.published]
    expected = superseded_lens_discovery_topics("ha_custom")
    assert len(expected) == len(SUPERSEDED_LENS_DISCOVERY_ENTITY_KEYS)
    for topic in expected:
        assert topic in topics
        assert topic.startswith("ha_custom/")
        retained_empty = [
            r for r in publisher.published if r.topic == topic and r.payload == "" and r.retain
        ]
        assert retained_empty
    # Default-prefix superseded topics must not be the only cleanup path.
    assert "homeassistant/sensor/zigbeelens/health/config" not in topics
    # Current decision entities remain under the configured prefix.
    assert "ha_custom/sensor/zigbeelens/decision_status/config" in topics
    assert not any("/bridge/request/" in t for t in topics)
    assert not any(t.endswith("/set") for t in topics)
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
