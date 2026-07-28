"""Topology startup scan and periodic refresh scheduling tests."""

from __future__ import annotations

from itertools import product
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

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
    get_topology_scheduler,
    periodic_capture_allowed,
    periodic_capture_interval_seconds,
    start_topology_scheduler,
    startup_scan_allowed,
    stop_topology_scheduler,
)
from zigbeelens.topology.service import (
    TopologyService,
    get_topology_service,
    manual_capture_allowed,
    start_topology,
    stop_topology,
    topology_status_dict,
)


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


@pytest.mark.parametrize(
    (
        "enabled",
        "refresh_interval",
        "automatic_capture",
        "collector_is_ready",
        "networks_present",
    ),
    list(product((False, True), (0, 60), (False, True), (False, True), (False, True))),
)
def test_topology_scheduler_lifecycle_cross_product(
    tmp_path: Path,
    enabled: bool,
    refresh_interval: int,
    automatic_capture: bool,
    collector_is_ready: bool,
    networks_present: bool,
):
    stop_topology()
    cfg = _live_config(
        tmp_path / "scheduler-cross-product.sqlite",
        enabled=enabled,
        startup_scan=True,
        refresh_interval_seconds=refresh_interval,
        automatic_capture_enabled=automatic_capture,
    )
    cfg.features.automatic_network_map = automatic_capture
    if not networks_present:
        cfg.networks = []

    repo = MagicMock()
    network_rows = (
        [SimpleNamespace(id="home", name="Home", bridge_state="online")]
        if networks_present
        else []
    )
    repo.list_networks.return_value = network_rows
    repo.get_latest_topology_snapshots_for_networks.return_value = {}
    repo.get_network.return_value = network_rows[0] if network_rows else None
    collector = None
    if collector_is_ready:
        collector = SimpleNamespace(
            status=lambda: SimpleNamespace(enabled=True, connected=True)
        )
    ctx = SimpleNamespace(config=cfg, repo=repo, collector=collector)
    publisher = FakeTopologyRequestPublisher(cfg)
    service = TopologyService(
        ctx,
        publisher=publisher,
    )

    expected_periodic = enabled and (
        refresh_interval > 0 or automatic_capture
    )
    expected_startup = enabled and networks_present
    expected_scheduler = expected_periodic or expected_startup
    assert periodic_capture_allowed(cfg) is expected_periodic
    assert startup_scan_allowed(cfg) is expected_startup
    assert collector_ready(ctx) is collector_is_ready

    thread = MagicMock()
    thread.is_alive.return_value = False
    try:
        with patch(
            "zigbeelens.topology.scheduler.threading.Thread",
            return_value=thread,
        ) as thread_factory:
            scheduler = start_topology_scheduler(ctx, service)
        assert (scheduler is not None) is expected_scheduler
        assert thread_factory.called is expected_scheduler
        assert thread.start.called is expected_scheduler
        assert (get_topology_scheduler() is not None) is expected_scheduler

        if not enabled:
            status = topology_status_dict(ctx)
            assert status["enabled"] is False
            assert status["manual_capture_enabled"] is False
            assert status["automatic_capture_enabled"] is False
            assert service.status.capture_in_progress is False
            assert publisher.published == []
    finally:
        stop_topology_scheduler(wait=True)
    assert get_topology_scheduler() is None


@pytest.mark.parametrize(
    (
        "refresh_interval",
        "legacy_feature",
        "legacy_topology",
        "startup_scan",
        "manual_feature",
        "manual_topology",
    ),
    list(
        product(
            (0, 60),
            (False, True),
            (False, True),
            (False, True),
            (False, True),
            (False, True),
        )
    ),
)
def test_disabled_topology_owns_zero_scheduler_status_and_capture_cross_product(
    tmp_path: Path,
    refresh_interval: int,
    legacy_feature: bool,
    legacy_topology: bool,
    startup_scan: bool,
    manual_feature: bool,
    manual_topology: bool,
):
    cfg = _live_config(
        tmp_path / "disabled-cross-product.sqlite",
        enabled=False,
        startup_scan=startup_scan,
        refresh_interval_seconds=refresh_interval,
        automatic_capture_enabled=legacy_topology,
        manual_capture_enabled=manual_topology,
    )
    cfg.features.automatic_network_map = legacy_feature
    cfg.features.manual_network_map = manual_feature
    ctx = SimpleNamespace(config=cfg, repo=MagicMock())
    ctx.repo.list_networks.return_value = []

    assert periodic_capture_interval_seconds(cfg) == 0
    assert periodic_capture_allowed(cfg) is False
    assert startup_scan_allowed(cfg) is False
    assert manual_capture_allowed(cfg) is False

    publisher = FakeTopologyRequestPublisher(cfg)
    service = TopologyService(ctx, publisher=publisher)
    scheduler = TopologyScheduler(ctx, service)
    scheduler.start()
    assert scheduler._thread is None
    assert start_topology_scheduler(ctx, service) is None
    assert get_topology_scheduler() is None
    with pytest.raises(PermissionError, match="disabled"):
        service.request_capture("home", confirmed=True)
    with pytest.raises(PermissionError, match="disabled"):
        service.request_system_capture("home", requested_by="startup_scan")
    with pytest.raises(PermissionError, match="disabled"):
        service.request_system_capture("home", requested_by="periodic_refresh")
    assert publisher.published == []

    try:
        assert start_topology(ctx) is None
        assert get_topology_service() is None
        assert topology_status_dict(ctx) == {
            "enabled": False,
            "manual_capture_enabled": False,
            "automatic_capture_enabled": False,
            "capture_in_progress": False,
            "last_capture_error": None,
            "networks": [],
        }
    finally:
        stop_topology()


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
