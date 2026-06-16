"""Topology snapshot safety and parsing tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from zigbeelens.config.models import AppConfig, FeaturesConfig, ModeConfig, NetworkConfig, StorageConfig, TopologyConfig
from zigbeelens.mqtt.models import RawMqttMessage
from zigbeelens.storage.repository import Repository, utc_now_iso
from zigbeelens.topology.parser import parse_networkmap_payload
from zigbeelens.topology.publisher import FakeTopologyRequestPublisher
from zigbeelens.topology.service import TopologyService, manual_capture_allowed
from zigbeelens.topology.topics import (
    CAPTURE_WARNING,
    UnsafeTopologyTopicError,
    networkmap_request_topic,
    validate_topology_request_topic,
)


def _config(db_path: Path, *, topology_enabled: bool = True) -> AppConfig:
    return AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(db_path)),
        features=FeaturesConfig(manual_network_map=topology_enabled, automatic_network_map=False),
        topology=TopologyConfig(
            enabled=topology_enabled,
            manual_capture_enabled=topology_enabled,
            automatic_capture_enabled=False,
            startup_scan=False,
            capture_on_incident=False,
        ),
    )


def test_manual_capture_disabled_by_default():
    cfg = AppConfig()
    assert manual_capture_allowed(cfg) is False


def test_networkmap_request_allowed_only_for_configured_network():
    with pytest.raises(UnsafeTopologyTopicError):
        validate_topology_request_topic(
            "homeassistant/sensor/x/config",
            allowed_base_topics=("zigbee2mqtt",),
        )
    with pytest.raises(UnsafeTopologyTopicError):
        validate_topology_request_topic(
            "zigbee2mqtt/bridge/request/device/remove",
            allowed_base_topics=("zigbee2mqtt",),
        )
    with pytest.raises(UnsafeTopologyTopicError):
        validate_topology_request_topic(
            "zigbee2mqtt/Lamp/set",
            allowed_base_topics=("zigbee2mqtt",),
        )
    validate_topology_request_topic(
        networkmap_request_topic("zigbee2mqtt"),
        allowed_base_topics=("zigbee2mqtt",),
    )


def test_parse_networkmap_nodes_and_links():
    payload = {
        "nodes": {
            "0x00124b0024abcd01": {"type": "Coordinator", "friendly_name": "Coordinator"},
            "0x00124b0024abcd02": {"type": "Router", "friendly_name": "Hall Router"},
            "0x00124b0024abcd03": {"type": "EndDevice", "friendly_name": "Lamp"},
        },
        "links": [
            {"source": "0x00124b0024abcd02", "target": "0x00124b0024abcd03", "linkquality": 110}
        ],
    }
    parsed = parse_networkmap_payload(payload)
    assert len(parsed.nodes) == 3
    assert parsed.link_count == 1
    assert parsed.router_count >= 1


def test_capture_blocked_without_confirmation(tmp_path: Path):
    from zigbeelens.app.context import bootstrap, reset_context

    reset_context()
    cfg = _config(tmp_path / "topo.sqlite")
    with patch("zigbeelens.app.context.start_discovery", return_value=None):
        ctx = bootstrap(config=cfg)
    service = TopologyService(ctx, publisher=FakeTopologyRequestPublisher(cfg))
    with pytest.raises(ValueError, match="network map"):
        service.request_capture("home", confirmed=False)
    reset_context()


def test_capture_blocked_when_disabled(tmp_path: Path):
    from zigbeelens.app.context import bootstrap, reset_context

    reset_context()
    cfg = _config(tmp_path / "disabled.sqlite", topology_enabled=False)
    with patch("zigbeelens.app.context.start_discovery", return_value=None):
        ctx = bootstrap(config=cfg)
    service = TopologyService(ctx, publisher=FakeTopologyRequestPublisher(cfg))
    with pytest.raises(PermissionError):
        service.request_capture("home", confirmed=True)
    reset_context()


def test_no_automatic_capture_on_startup(tmp_path: Path):
    from zigbeelens.app.context import bootstrap, reset_context

    reset_context()
    cfg = _config(tmp_path / "startup.sqlite")
    publisher = FakeTopologyRequestPublisher(cfg)
    with patch("zigbeelens.app.context.start_discovery", return_value=None):
        ctx = bootstrap(config=cfg)
    service = TopologyService(ctx, publisher=publisher)
    assert publisher.published == []
    assert service.status.capture_in_progress is False
    reset_context()


def test_topology_response_stored(tmp_path: Path):
    from zigbeelens.app.context import bootstrap, reset_context
    from zigbeelens.db.connection import Database

    db_path = tmp_path / "response.sqlite"
    cfg = _config(db_path)
    reset_context()
    with patch("zigbeelens.app.context.start_discovery", return_value=None):
        ctx = bootstrap(config=cfg)
    publisher = FakeTopologyRequestPublisher(cfg)
    service = TopologyService(ctx, publisher=publisher)
    service.request_capture("home", confirmed=True)
    payload = json.dumps(
        {
            "nodes": {
                "0x00124b0024abcd02": {"type": "Router"},
                "0x00124b0024abcd03": {"type": "EndDevice"},
            },
            "links": [{"source": "0x00124b0024abcd02", "target": "0x00124b0024abcd03"}],
        }
    ).encode()
    message = RawMqttMessage(
        topic="zigbee2mqtt/bridge/response/networkmap",
        payload=payload,
        retained=False,
        received_at=utc_now_iso(),
    )
    assert service.try_handle_response(message) is True
    latest = ctx.repo.get_latest_topology_snapshot("home")
    assert latest is not None
    assert latest["link_count"] == 1
    reset_context()


def test_topology_handler_error_clears_pending(tmp_path: Path):
    from unittest.mock import patch

    from zigbeelens.app.context import bootstrap, reset_context
    from zigbeelens.mqtt.models import RawMqttMessage

    db_path = tmp_path / "handler-error.sqlite"
    cfg = _config(db_path)
    reset_context()
    with patch("zigbeelens.app.context.start_discovery", return_value=None):
        ctx = bootstrap(config=cfg)
    publisher = FakeTopologyRequestPublisher(cfg)
    service = TopologyService(ctx, publisher=publisher)
    service.request_capture("home", confirmed=True)

    message = RawMqttMessage(
        topic="zigbee2mqtt/bridge/response/networkmap",
        payload=b'{"nodes": {}, "links": []}',
        retained=False,
        received_at=utc_now_iso(),
    )
    with patch.object(ctx.repo, "store_topology_parsed", side_effect=RuntimeError("db fail")):
        assert service.try_handle_response(message) is False
    assert service.status.capture_in_progress is False

    service.request_capture("home", confirmed=True)
    assert service.status.capture_in_progress is True
    reset_context()


def test_stale_pending_capture_cleared_on_retry(tmp_path: Path, monkeypatch):
    from zigbeelens.app.context import bootstrap, reset_context
    from zigbeelens.topology import service as topology_service_module

    db_path = tmp_path / "stale-pending.sqlite"
    cfg = _config(db_path)
    reset_context()
    monkeypatch.setattr(topology_service_module, "PENDING_CAPTURE_TIMEOUT_SECONDS", 0)
    with patch("zigbeelens.app.context.start_discovery", return_value=None):
        ctx = bootstrap(config=cfg)
    publisher = FakeTopologyRequestPublisher(cfg)
    service = TopologyService(ctx, publisher=publisher)
    service.request_capture("home", confirmed=True)
    assert service.status.capture_in_progress is True

    service.request_capture("home", confirmed=True)
    assert service.status.capture_in_progress is True
    reset_context()


def test_correlator_topology_evidence_not_root_cause(tmp_path: Path):
    from zigbeelens.db.connection import Database
    from zigbeelens.diagnostics.incidents.correlator import IncidentCorrelationEngine
    from zigbeelens.diagnostics.service import HealthDiagnosticService

    db = Database(tmp_path / "corr.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = _config(tmp_path / "corr.sqlite")
    repo.sync_networks(cfg.networks)
    snapshot_id = "snap1"
    repo.create_topology_snapshot(
        snapshot_id=snapshot_id,
        network_id="home",
        requested_by="test",
        status="complete",
        warning_acknowledged=True,
    )
    parsed = parse_networkmap_payload(
        {
            "nodes": {
                "0x00124b0024abcd02": {"type": "Router", "friendly_name": "Router"},
                "0x00124b0024abcd03": {"type": "EndDevice"},
                "0x00124b0024abcd04": {"type": "EndDevice"},
            },
            "links": [
                {"source": "0x00124b0024abcd02", "target": "0x00124b0024abcd03"},
                {"source": "0x00124b0024abcd02", "target": "0x00124b0024abcd04"},
            ],
        }
    )
    repo.store_topology_parsed(snapshot_id, "home", parsed, status="complete")

    health = HealthDiagnosticService(cfg, repo)
    engine = IncidentCorrelationEngine(cfg, repo)
    candidates = engine.correlate(health)
    text = json.dumps([c.evidence for c in candidates])
    assert "caused" not in text.lower()
    assert "suggests" in text.lower() or "topology" in text.lower() or candidates == []
    db.close()
