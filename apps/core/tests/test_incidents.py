"""Incident correlation tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from zigbeelens.config.models import AppConfig, DiagnosticsConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.diagnostics.incidents.correlator import IncidentCorrelationEngine, NetworkContext
from zigbeelens.diagnostics.incidents.lifecycle import IncidentLifecycleManager
from zigbeelens.diagnostics.incidents.models import IncidentCandidate, IncidentLifecycle, IncidentType
from zigbeelens.diagnostics.incidents.service import IncidentDiagnosticService
from zigbeelens.diagnostics.models import BridgeHealthState, HealthFlag, HealthResult, HealthSeverity
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.mqtt.client import FakeMqttClient
from zigbeelens.mqtt.collector import build_collector
from zigbeelens.mqtt.ingestion import MqttIngestionService
from zigbeelens.schemas import Confidence, IncidentScope, Severity
from zigbeelens.services.payload_builder import PayloadBuilder
from zigbeelens.storage.repository import Repository, utc_now_iso


def _config(db_path: Path, **diag_overrides) -> AppConfig:
    diag = DiagnosticsConfig(**diag_overrides)
    return AppConfig(
        mode=ModeConfig(mock=False),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(db_path)),
        diagnostics=diag,
    )


def _seed_device(repo: Repository, ieee: str, name: str, **state) -> None:
    repo.upsert_device(
        network_id="home",
        ieee_address=ieee,
        friendly_name=name,
        device_type=state.get("device_type", "EndDevice"),
        power_source=state.get("power_source", "Battery"),
        interview_state=state.get("interview_state", "successful"),
    )
    repo.ensure_device_current_state("home", ieee)
    if "availability" in state:
        repo.update_device_current_state(
            network_id="home", ieee_address=ieee, availability=state["availability"]
        )


def _offline_transition(repo: Repository, ieee: str, minutes_ago: float = 1) -> None:
    ts = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
    repo.db.conn.execute(
        """
        INSERT INTO availability_changes (network_id, ieee_address, from_state, to_state, changed_at)
        VALUES ('home', ?, 'online', 'offline', ?)
        """,
        (ieee, ts),
    )
    repo.db.conn.commit()


def _health_stub(primary: HealthFlag, flags: list[HealthFlag] | None = None) -> HealthResult:
    flags = flags or [primary]
    return HealthResult(primary=primary, flags=flags, severity=HealthSeverity.incident)


class FakeHealth:
    def __init__(self, mapping: dict[tuple[str, str], HealthResult], bridge=None, network=None):
        self.mapping = mapping
        self._bridge = bridge
        self._network = network

    def get_device_health(self, network_id: str, ieee: str):
        return self.mapping.get((network_id, ieee))

    def get_bridge_health(self, network_id: str):
        return self._bridge

    def get_network_health(self, network_id: str):
        return self._network

    def all_device_health(self):
        return dict(self.mapping)


def test_single_device_unavailable_rule():
    from zigbeelens.storage.repository import DeviceRow

    cfg = DiagnosticsConfig()
    engine = IncidentCorrelationEngine(AppConfig(diagnostics=cfg), Repository(Database(":memory:")))
    ctx = NetworkContext(
        network_id="home",
        network_name="Home",
        bridge_state="online",
        bridge_health_state=BridgeHealthState.online,
        devices=[
            DeviceRow("home", "0x1", "plug", "EndDevice", "Battery", None, None, "successful", "offline")
        ],
        device_health={("home", "0x1"): _health_stub(HealthFlag.unavailable)},
        offline_cluster={"0x1": utc_now_iso()},
    )
    results = engine._network_unavailability_rules(ctx, [])
    assert len(results) == 1
    assert results[0].incident_type == IncidentType.single_device_unavailable


def test_correlated_devices_rule():
    cfg = DiagnosticsConfig(correlated_min_devices=2)
    from zigbeelens.storage.repository import DeviceRow

    engine = IncidentCorrelationEngine(AppConfig(diagnostics=cfg), Repository(Database(":memory:")))
    now = utc_now_iso()
    ctx = NetworkContext(
        network_id="home",
        network_name="Home",
        bridge_state="online",
        bridge_health_state=BridgeHealthState.online,
        devices=[
            DeviceRow("home", "0x1", "a", "EndDevice", "Battery", None, None, "successful", "offline"),
            DeviceRow("home", "0x2", "b", "EndDevice", "Battery", None, None, "successful", "offline"),
        ],
        device_health={
            ("home", "0x1"): _health_stub(HealthFlag.unavailable),
            ("home", "0x2"): _health_stub(HealthFlag.unavailable),
        },
        offline_cluster={"0x1": now, "0x2": now},
    )
    results = engine._network_unavailability_rules(ctx, [])
    assert any(r.incident_type == IncidentType.correlated_device_unavailability for r in results)


def test_bridge_offline_rule():
    engine = IncidentCorrelationEngine(AppConfig(), Repository(Database(":memory:")))
    ctx = NetworkContext(
        network_id="home",
        network_name="Home",
        bridge_state="offline",
        bridge_health_state=BridgeHealthState.offline,
        devices=[],
        device_health={},
        offline_cluster={},
    )
    results = engine._bridge_offline_rules([ctx])
    assert results[0].incident_type == IncidentType.bridge_offline


def test_network_wide_rule():
    cfg = DiagnosticsConfig(network_wide_min_devices=3)
    from zigbeelens.storage.repository import DeviceRow

    engine = IncidentCorrelationEngine(AppConfig(diagnostics=cfg), Repository(Database(":memory:")))
    devices = [
        DeviceRow("home", f"0x{i}", f"d{i}", "EndDevice", "Battery", None, None, "successful", "offline")
        for i in range(3)
    ]
    ctx = NetworkContext(
        network_id="home",
        network_name="Home",
        bridge_state="online",
        bridge_health_state=BridgeHealthState.online,
        devices=devices,
        device_health={(d.network_id, d.ieee_address): _health_stub(HealthFlag.unavailable) for d in devices},
        offline_cluster={d.ieee_address: utc_now_iso() for d in devices},
    )
    results = engine._network_unavailability_rules(ctx, [])
    assert any(r.incident_type == IncidentType.network_wide_instability for r in results)


def test_lifecycle_deduplication(tmp_path: Path):
    db = Database(tmp_path / "dedup.sqlite")
    db.migrate()
    repo = Repository(db)
    config = _config(tmp_path / "dedup.sqlite")
    lifecycle = IncidentLifecycleManager(config, repo)
    candidate = IncidentCandidate(
        dedup_key="single_unavailable:home:0x1",
        incident_type=IncidentType.single_device_unavailable,
        scope=IncidentScope.device,
        severity=Severity.incident,
        confidence=Confidence.high,
        title="Test",
        summary="One device unavailable",
        explanation="Isolated device pattern",
        network_ids=["home"],
    )
    events1 = lifecycle.sync([candidate])
    events2 = lifecycle.sync([candidate])
    assert "incident_opened" in events1
    assert "incident_opened" not in events2
    assert repo.list_incidents()[0]["lifecycle_state"] == IncidentLifecycle.open.value


def test_bridge_offline_suppresses_device_incidents(tmp_path: Path):
    db = Database(tmp_path / "suppress.sqlite")
    db.migrate()
    repo = Repository(db)
    repo.sync_networks([NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")])
    config = _config(tmp_path / "suppress.sqlite")
    health = HealthDiagnosticService(config, repo)
    incidents = IncidentDiagnosticService(config, repo)
    repo.update_network_bridge_state("home", "offline")
    _seed_device(repo, "0x1", "plug", availability="offline")
    _offline_transition(repo, "0x1")
    health.recalculate_all()
    incidents.correlate_and_sync(health)
    types = {row["incident_type"] for row in repo.list_active_incidents()}
    assert IncidentType.bridge_offline.value in types
    assert IncidentType.single_device_unavailable.value not in types


def test_mqtt_single_device_incident(tmp_path: Path):
    db_path = tmp_path / "mqtt_single.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = _config(db_path)
    repo.sync_networks(config.networks)
    health = HealthDiagnosticService(config, repo)
    incidents = IncidentDiagnosticService(config, repo)

    def on_recalc(nid: str, ieee: str | None = None) -> None:
        if ieee:
            health.recalculate_device(nid, ieee)
        else:
            health.recalculate_network(nid)
        incidents.correlate_and_sync(health)

    ingestion = MqttIngestionService(config, repo, on_health_recalc=on_recalc)
    collector = build_collector(config, repo, ingestion, client=None)
    client = FakeMqttClient(collector._handle_message)
    collector._client = client
    collector.start()

    devices = [{"ieee_address": "0xabc", "friendly_name": "Plug", "type": "EndDevice"}]
    client.inject("zigbee2mqtt/bridge/state", "online")
    client.inject("zigbee2mqtt/bridge/devices", json.dumps(devices))
    client.inject("zigbee2mqtt/Plug/availability", json.dumps({"state": "offline"}))

    active = repo.list_active_incidents()
    assert len(active) == 1
    assert active[0]["incident_type"] == IncidentType.single_device_unavailable.value

    builder = PayloadBuilder(config, repo, health, incidents)
    dash = builder.dashboard()
    assert dash.active_incident_count == 1
    assert "isolated" in dash.current_finding.summary.lower() or "unavailable" in dash.current_finding.summary.lower()


def test_correlated_incident_integration(tmp_path: Path):
    db_path = tmp_path / "mqtt_corr.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = _config(db_path, correlated_min_devices=2, incident_window_seconds=600)
    repo.sync_networks(config.networks)
    health = HealthDiagnosticService(config, repo)
    incidents = IncidentDiagnosticService(config, repo)

    devices = [
        {"ieee_address": "0x1", "friendly_name": "A", "type": "EndDevice"},
        {"ieee_address": "0x2", "friendly_name": "B", "type": "EndDevice"},
    ]
    repo.sync_networks(config.networks)
    def on_recalc(nid: str, ieee: str | None = None) -> None:
        if ieee:
            health.recalculate_device(nid, ieee)
        else:
            health.recalculate_network(nid)
        incidents.correlate_and_sync(health)

    ingestion = MqttIngestionService(config, repo, on_health_recalc=on_recalc)
    collector = build_collector(config, repo, ingestion, client=None)
    client = FakeMqttClient(collector._handle_message)
    collector._client = client
    collector.start()
    client.inject("zigbee2mqtt/bridge/state", "online")
    client.inject("zigbee2mqtt/bridge/devices", json.dumps(devices))
    client.inject("zigbee2mqtt/A/availability", json.dumps({"state": "offline"}))
    client.inject("zigbee2mqtt/B/availability", json.dumps({"state": "offline"}))

    active = repo.list_active_incidents()
    assert any(i["incident_type"] == IncidentType.correlated_device_unavailability.value for i in active)


def test_mock_scenarios_unchanged(mock_client):
    resp = mock_client.get("/api/dashboard?scenario=four_devices_same_room_unavailable")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_incident_count"] == 1
    assert len(data["top_affected_devices"]) >= 1


def test_empty_state_unchanged(live_client):
    resp = live_client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_incident_count"] == 0
