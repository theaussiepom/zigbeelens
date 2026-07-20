"""Topology startup scan and periodic refresh scheduling tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from zigbeelens.app.context import bootstrap, reset_context
from zigbeelens.config.models import (
    AppConfig,
    FeaturesConfig,
    ModeConfig,
    NetworkConfig,
    StorageConfig,
    TopologyConfig,
)
from zigbeelens.mqtt.client import FakeMqttClient
from zigbeelens.mqtt.collector import build_collector
from zigbeelens.mqtt.ingestion import MqttIngestionService
from zigbeelens.topology.publisher import FakeTopologyRequestPublisher
from zigbeelens.topology.scheduler import (
    TopologyScheduler,
    bridges_ready,
    collector_ready,
    periodic_capture_allowed,
    periodic_capture_interval_seconds,
    startup_scan_allowed,
)
from zigbeelens.topology.service import TopologyService


def _published_topics(publisher: FakeTopologyRequestPublisher) -> list[str]:
    return [record.topic for record in publisher.published]

def _live_config(db_path: Path, **topology_overrides) -> AppConfig:
    topology_defaults = {
        "enabled": True,
        "startup_scan": True,
        "startup_stable_delay_seconds": 0,
        "refresh_interval_seconds": 0,
    }
    topology_defaults.update(topology_overrides)
    topology = TopologyConfig(**topology_defaults)
    return AppConfig(
        mode=ModeConfig(mock=False),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(db_path)),
        features=FeaturesConfig(mqtt_collector=True),
        topology=topology,
    )


def _attach_fake_collector(ctx, config: AppConfig) -> FakeMqttClient:
    ingestion = MqttIngestionService(config, ctx.repo)
    collector = build_collector(config, ctx.repo, ingestion, client=None)
    client = FakeMqttClient(collector._handle_message)
    collector._client = client
    collector.start()
    ctx.collector = collector
    return client


def test_topology_enabled_by_default():
    cfg = AppConfig()
    assert cfg.topology.enabled is True
    assert cfg.topology.startup_scan is True
    assert cfg.topology.startup_stable_delay_seconds == 60
    assert cfg.topology.refresh_interval_seconds == 0


def test_startup_scan_disabled_in_mock_mode():
    cfg = AppConfig(mode=ModeConfig(mock=True))
    assert startup_scan_allowed(cfg) is False


def test_no_periodic_capture_when_refresh_interval_zero():
    cfg = AppConfig(topology=TopologyConfig(enabled=True, refresh_interval_seconds=0))
    assert periodic_capture_interval_seconds(cfg) == 0
    assert periodic_capture_allowed(cfg) is False


def test_periodic_capture_uses_refresh_interval_seconds():
    cfg = AppConfig(topology=TopologyConfig(enabled=True, refresh_interval_seconds=3600))
    assert periodic_capture_interval_seconds(cfg) == 3600
    assert periodic_capture_allowed(cfg) is True


def test_startup_scan_waits_for_collector_and_bridge(tmp_path: Path):
    reset_context()
    db_path = tmp_path / "startup-wait.sqlite"
    config = _live_config(db_path)
    publisher = FakeTopologyRequestPublisher(config)

    def fake_start_collector(ctx, _broadcaster):
        return None

    with patch("zigbeelens.app.context.start_discovery", return_value=None), patch(
        "zigbeelens.app.context.start_collector", side_effect=fake_start_collector
    ), patch("zigbeelens.topology.service.start_topology_scheduler"):
        ctx = bootstrap(config=config)

    service = TopologyService(ctx, publisher=publisher)
    scheduler = TopologyScheduler(ctx, service, sleep=lambda _: None)

    assert collector_ready(ctx) is False
    assert scheduler.tick_startup() is False
    assert publisher.published == []

    client = _attach_fake_collector(ctx, config)
    assert collector_ready(ctx) is True
    assert bridges_ready(ctx) is False
    assert scheduler.tick_startup() is False
    assert publisher.published == []

    client.inject("zigbee2mqtt/bridge/state", "online")
    assert bridges_ready(ctx) is True
    assert scheduler.tick_startup() is True
    assert _published_topics(publisher) == ["zigbee2mqtt/bridge/request/networkmap"]
    reset_context()


def test_startup_scan_runs_once_after_stable_delay(tmp_path: Path, monkeypatch):
    reset_context()
    db_path = tmp_path / "startup-once.sqlite"
    config = _live_config(db_path, startup_stable_delay_seconds=30)
    publisher = FakeTopologyRequestPublisher(config)

    with patch("zigbeelens.app.context.start_discovery", return_value=None), patch(
        "zigbeelens.app.context.start_collector", return_value=None
    ), patch("zigbeelens.topology.service.start_topology_scheduler"):
        ctx = bootstrap(config=config)

    client = _attach_fake_collector(ctx, config)
    client.inject("zigbee2mqtt/bridge/state", "online")
    service = TopologyService(ctx, publisher=publisher)
    scheduler = TopologyScheduler(ctx, service, sleep=lambda _: None)

    # Monkeypatching zigbeelens.topology.scheduler.time.monotonic replaces the
    # shared stdlib time.monotonic attribute. Stop background workers first so
    # they cannot consume the fake sequence during the startup-delay ticks.
    if ctx.storage_scheduler is not None:
        ctx.storage_scheduler.stop(wait=True)
        ctx.storage_scheduler = None
    if ctx.evaluation_scheduler is not None:
        ctx.evaluation_scheduler.stop(wait=True)
        ctx.evaluation_scheduler = None

    monotonic_values = iter([100.0, 130.0, 130.0, 130.0])
    monkeypatch.setattr(
        "zigbeelens.topology.scheduler.time.monotonic",
        lambda: next(monotonic_values),
    )

    assert scheduler.tick_startup() is False
    assert publisher.published == []
    assert scheduler.tick_startup() is True
    assert _published_topics(publisher) == ["zigbee2mqtt/bridge/request/networkmap"]
    assert scheduler.tick_startup() is True
    assert _published_topics(publisher) == ["zigbee2mqtt/bridge/request/networkmap"]
    reset_context()


def test_no_immediate_startup_capture_on_bootstrap(tmp_path: Path):
    reset_context()
    db_path = tmp_path / "bootstrap-no-immediate.sqlite"
    config = _live_config(db_path)
    captured: list[str] = []

    def fake_start_collector(ctx, _broadcaster):
        client = _attach_fake_collector(ctx, config)
        client.inject("zigbee2mqtt/bridge/state", "online")
        return ctx.collector

    def capture_scheduler(_ctx, _service):
        captured.append("scheduler_started")
        return None

    with patch("zigbeelens.app.context.start_discovery", return_value=None), patch(
        "zigbeelens.app.context.start_collector", side_effect=fake_start_collector
    ), patch("zigbeelens.topology.service.start_topology_scheduler", side_effect=capture_scheduler):
        bootstrap(config=config)

    assert captured == ["scheduler_started"]
    reset_context()
