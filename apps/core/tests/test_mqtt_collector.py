from __future__ import annotations

import json
from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.mqtt.client import FakeMqttClient
from zigbeelens.mqtt.collector import build_collector, collector_enabled
from zigbeelens.mqtt.ingestion import MqttIngestionService
from zigbeelens.services.payload_builder import PayloadBuilder
from zigbeelens.storage.repository import Repository


def _config(db_path: Path) -> AppConfig:
    return AppConfig(
        mode=ModeConfig(mock=False),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(db_path)),
    )


def _run_collector(repo: Repository, config: AppConfig) -> FakeMqttClient:
    ingestion = MqttIngestionService(config, repo)
    collector = build_collector(config, repo, ingestion, client=None)
    client = FakeMqttClient(collector._handle_message)
    collector._client = client
    collector.start()
    return client


def test_collector_disabled_in_mock_mode():
    config = AppConfig(mode=ModeConfig(mock=True))
    assert collector_enabled(config) is False


def test_collector_enabled_in_live_mode():
    config = AppConfig(mode=ModeConfig(mock=False))
    assert collector_enabled(config) is True


def test_no_publish_from_fake_client(tmp_path: Path):
    db_path = tmp_path / "collector.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = _config(db_path)
    repo.sync_networks(config.networks)
    client = _run_collector(repo, config)
    assert client.published == []
    client.inject("zigbee2mqtt/bridge/state", "online")
    net = repo.get_network("home")
    assert net is not None
    assert net.bridge_state == "online"
    db.close()


def test_device_inventory_and_payload_flow(tmp_path: Path):
    db_path = tmp_path / "flow.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = _config(db_path)
    repo.sync_networks(config.networks)
    client = _run_collector(repo, config)

    devices = [
        {
            "ieee_address": "0x00124b0024abcd01",
            "friendly_name": "Laundry Plug",
            "type": "Router",
            "power_source": "Mains (single phase)",
            "interview_completed": True,
        }
    ]
    client.inject("zigbee2mqtt/bridge/devices", json.dumps(devices))
    client.inject(
        "zigbee2mqtt/Laundry Plug",
        json.dumps({"linkquality": 76, "battery": 55, "last_seen": "2026-06-14T10:00:00Z"}),
    )
    client.inject("zigbee2mqtt/Laundry Plug/availability", json.dumps({"state": "online"}))

    device = repo.get_device("home", "0x00124b0024abcd01")
    assert device is not None
    assert device.friendly_name == "Laundry Plug"
    assert device.linkquality == 76
    assert device.availability == "online"

    builder = PayloadBuilder(config, repo)
    dash = builder.dashboard()
    assert dash.networks[0].device_count == 1
    assert len(dash.recent_timeline) > 0
    db.close()


def test_unresolved_payload_reconciled_after_inventory(tmp_path: Path):
    db_path = tmp_path / "reconcile.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = _config(db_path)
    repo.sync_networks(config.networks)
    client = _run_collector(repo, config)

    client.inject(
        "zigbee2mqtt/Laundry Plug",
        json.dumps({"linkquality": 40}),
    )
    assert repo.count_devices() == 0

    devices = [{"ieee_address": "0xabc", "friendly_name": "Laundry Plug", "type": "EndDevice"}]
    client.inject("zigbee2mqtt/bridge/devices", json.dumps(devices))

    device = repo.get_device("home", "0xabc")
    assert device is not None
    assert device.linkquality == 40
    db.close()


def test_duplicate_friendly_name_same_network(tmp_path: Path):
    db_path = tmp_path / "dup.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = _config(db_path)
    repo.sync_networks(config.networks)
    client = _run_collector(repo, config)

    devices = [
        {"ieee_address": "0x1", "friendly_name": "Sensor", "type": "EndDevice"},
        {"ieee_address": "0x2", "friendly_name": "Sensor", "type": "EndDevice"},
    ]
    client.inject("zigbee2mqtt/bridge/devices", json.dumps(devices))
    client.inject("zigbee2mqtt/Sensor", json.dumps({"linkquality": 10}))

    assert repo.get_device("home", "0x1").linkquality is None
    assert repo.get_device("home", "0x2").linkquality is None
    db.close()


def test_events_stored_in_sqlite(tmp_path: Path):
    db_path = tmp_path / "events.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = _config(db_path)
    repo.sync_networks(config.networks)
    client = _run_collector(repo, config)
    client.inject("zigbee2mqtt/bridge/state", "online")
    assert repo.count_events() >= 1
    db.close()
