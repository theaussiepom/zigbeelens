from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zigbeelens.app.context import reset_context
from zigbeelens.main import create_app


def write_config(
    path: Path,
    *,
    mock: bool = True,
    db_path: Path | None = None,
    mqtt_collector: bool | None = None,
    topology_enabled: bool = False,
) -> None:
    db = db_path or (path.parent / "test.sqlite")
    if mqtt_collector is None:
        mqtt_collector = not mock
    path.write_text(
        f"""
server:
  host: 127.0.0.1
  port: 8377
mode:
  mock: {"true" if mock else "false"}
  default_scenario: four_devices_same_room_unavailable
mqtt:
  server: mqtt://zigbeelens:secret@localhost:1883
  username: zigbeelens
  password: secret
  client_id: zigbeelens-test
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
  - id: home2
    name: Home 2
    base_topic: zigbee2mqtt-home2
storage:
  path: {db}
  retention_days: 30
diagnostics:
  incident_window_seconds: 180
  stale_after_hours: 24
  low_battery_percent: 20
  weak_link_threshold: 40
  flapping_threshold: 3
  recently_unstable_window_hours: 24
  bridge_stale_after_minutes: 10
  mains_stale_after_hours: 12
  battery_stale_after_hours: 48
  incident_watch_window_minutes: 30
  incident_resolution_grace_minutes: 5
  network_wide_device_percent: 25
  network_wide_min_devices: 5
  correlated_min_devices: 2
  stale_cluster_min_devices: 3
  low_battery_cluster_min_devices: 3
  interview_failure_min_devices: 2
features:
  mqtt_collector: {"true" if mqtt_collector else "false"}
  mqtt_discovery: true
  bridge_logs: true
  device_payload_history: true
  manual_network_map: true
  automatic_network_map: false
topology:
  enabled: {"true" if topology_enabled else "false"}
  manual_capture_enabled: {"true" if topology_enabled else "false"}
  automatic_capture_enabled: false
""".strip(),
        encoding="utf-8",
    )


@pytest.fixture
def topology_client(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    write_config(
        config_path,
        mock=True,
        db_path=tmp_path / "topo.sqlite",
        topology_enabled=True,
    )
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(config_path))
    reset_context()
    app = create_app(str(config_path))
    with TestClient(app) as client:
        yield client
    reset_context()


@pytest.fixture
def mock_client(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    write_config(config_path, mock=True, db_path=tmp_path / "mock.sqlite")
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(config_path))
    reset_context()
    app = create_app(str(config_path))
    with TestClient(app) as client:
        yield client
    reset_context()


@pytest.fixture
def live_client(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    write_config(config_path, mock=False, db_path=tmp_path / "live.sqlite", mqtt_collector=False)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(config_path))
    reset_context()
    app = create_app(str(config_path))
    with TestClient(app) as client:
        yield client
    reset_context()
