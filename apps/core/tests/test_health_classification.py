"""Health classification engine tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from zigbeelens.config.models import AppConfig, DiagnosticsConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.diagnostics.bridge_health import classify_bridge
from zigbeelens.diagnostics.device_health import classify_device
from zigbeelens.diagnostics.models import (
    BridgeHealthState,
    DeviceHealthContext,
    HealthConfidence,
    HealthFlag,
    HealthResult,
    HealthSeverity,
    NetworkHealthState,
)
from zigbeelens.diagnostics.network_health import classify_network
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.mqtt.client import FakeMqttClient
from zigbeelens.mqtt.collector import build_collector
from zigbeelens.mqtt.ingestion import MqttIngestionService
from zigbeelens.schemas import DeviceHealthPrimary
from zigbeelens.services.payload_builder import PayloadBuilder
from zigbeelens.storage.repository import Repository, utc_now_iso


def _config(db_path: Path) -> AppConfig:
    return AppConfig(
        mode=ModeConfig(mock=False),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(db_path)),
    )


def _ctx(**kwargs) -> DeviceHealthContext:
    defaults = dict(
        network_id="home",
        ieee_address="0xabc",
        friendly_name="sensor",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
        availability="unknown",
        last_seen=None,
        last_payload_at=None,
        linkquality=None,
        battery=None,
        availability_change_count=0,
    )
    defaults.update(kwargs)
    return DeviceHealthContext(**defaults)


def _diag() -> DiagnosticsConfig:
    return DiagnosticsConfig()


def test_unknown_device_without_telemetry():
    result = classify_device(_ctx(), _diag())
    assert result.primary == HealthFlag.unknown
    assert HealthFlag.unknown in result.flags
    assert result.severity == HealthSeverity.unknown
    assert result.confidence == HealthConfidence.low
    assert any("inventory" in e.lower() for e in result.evidence)
    assert result.limitations


def test_healthy_with_availability_online():
    now = utc_now_iso()
    result = classify_device(
        _ctx(availability="online", last_payload_at=now, linkquality=80, battery=90),
        _diag(),
    )
    assert result.primary == HealthFlag.healthy
    assert result.severity == HealthSeverity.ok
    assert result.confidence == HealthConfidence.high


def test_healthy_without_availability_medium_confidence():
    now = utc_now_iso()
    result = classify_device(_ctx(last_payload_at=now, linkquality=80), _diag())
    assert result.primary == HealthFlag.healthy
    assert result.confidence == HealthConfidence.medium
    assert any("Availability is not known" in lim for lim in result.limitations)


def test_unavailable_from_offline_availability():
    result = classify_device(_ctx(availability="offline", last_payload_at=utc_now_iso()), _diag())
    assert result.primary == HealthFlag.unavailable
    assert result.severity == HealthSeverity.incident
    assert result.confidence == HealthConfidence.high


def test_recently_unstable_from_availability_changes():
    result = classify_device(_ctx(availability="online", availability_change_count=4), _diag())
    assert HealthFlag.recently_unstable in result.flags
    assert result.primary == HealthFlag.recently_unstable


def test_weak_link_threshold():
    result = classify_device(_ctx(linkquality=31, last_payload_at=utc_now_iso()), _diag())
    assert HealthFlag.weak_link in result.flags
    assert result.primary == HealthFlag.weak_link


def test_low_battery_threshold():
    result = classify_device(_ctx(battery=15, last_payload_at=utc_now_iso()), _diag())
    assert HealthFlag.low_battery in result.flags
    assert result.primary == HealthFlag.low_battery


def test_stale_reporting_mains_device():
    old = (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat()
    result = classify_device(
        _ctx(device_type="Router", power_source="Mains", last_payload_at=old),
        _diag(),
    )
    assert HealthFlag.stale_reporting in result.flags


def test_stale_reporting_battery_device():
    old = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
    result = classify_device(
        _ctx(power_source="Battery", last_payload_at=old),
        _diag(),
    )
    assert HealthFlag.stale_reporting in result.flags


def test_interview_incomplete():
    result = classify_device(_ctx(interview_state="failed"), _diag())
    assert result.primary == HealthFlag.interview_issue


def test_router_risk_from_weak_router():
    result = classify_device(
        _ctx(device_type="Router", linkquality=20, last_payload_at=utc_now_iso()),
        _diag(),
    )
    assert HealthFlag.router_risk in result.flags
    assert HealthFlag.weak_link in result.flags


def test_router_risk_unavailable_router_is_incident():
    result = classify_device(
        _ctx(device_type="Router", availability="offline"),
        _diag(),
    )
    assert result.primary == HealthFlag.unavailable
    assert HealthFlag.router_risk in result.flags


def test_primary_health_priority_order():
    old = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
    result = classify_device(
        _ctx(
            availability="offline",
            battery=10,
            linkquality=10,
            availability_change_count=5,
            last_payload_at=old,
            interview_state="failed",
        ),
        _diag(),
    )
    assert result.primary == HealthFlag.unavailable


def test_missing_battery_not_unhealthy():
    result = classify_device(_ctx(last_payload_at=utc_now_iso(), linkquality=90), _diag())
    assert HealthFlag.low_battery not in result.flags


def test_bridge_online():
    result = classify_bridge(bridge_state="online", last_updated_at=utc_now_iso(), config=_diag())
    assert result.state == BridgeHealthState.online


def test_bridge_offline():
    result = classify_bridge(bridge_state="offline", last_updated_at=utc_now_iso(), config=_diag())
    assert result.state == BridgeHealthState.offline
    assert result.severity == HealthSeverity.incident


def test_bridge_stale():
    old = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    result = classify_bridge(bridge_state="online", last_updated_at=old, config=_diag())
    assert result.state == BridgeHealthState.stale


def test_bridge_online_when_state_quiet_but_devices_active():
    old = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    result = classify_bridge(
        bridge_state="online",
        last_updated_at=old,
        last_mqtt_activity_at=utc_now_iso(),
        config=_diag(),
    )
    assert result.state == BridgeHealthState.online
    assert any("Recent device MQTT activity" in item for item in result.evidence)


def test_bridge_unknown():
    result = classify_bridge(bridge_state="unknown", last_updated_at=None, config=_diag())
    assert result.state == BridgeHealthState.unknown


def test_network_ok():
    healthy = HealthResult(primary=HealthFlag.healthy, flags=[HealthFlag.healthy])
    net, _ = classify_network(
        network_id="home",
        bridge_state="online",
        network_updated_at=utc_now_iso(),
        device_health=[healthy],
        router_devices=[],
        config=_diag(),
    )
    assert net.state == NetworkHealthState.ok


def test_network_watch():
    weak = HealthResult(primary=HealthFlag.weak_link, flags=[HealthFlag.weak_link])
    net, _ = classify_network(
        network_id="home",
        bridge_state="online",
        network_updated_at=utc_now_iso(),
        device_health=[weak],
        router_devices=[],
        config=_diag(),
    )
    assert net.state == NetworkHealthState.watch


def test_network_incident():
    offline = HealthResult(primary=HealthFlag.unavailable, flags=[HealthFlag.unavailable])
    net, _ = classify_network(
        network_id="home",
        bridge_state="online",
        network_updated_at=utc_now_iso(),
        device_health=[offline],
        router_devices=[],
        config=_diag(),
    )
    assert net.state == NetworkHealthState.incident


def test_health_snapshots_persist_on_change(tmp_path: Path):
    db = Database(tmp_path / "snap.sqlite")
    db.migrate()
    repo = Repository(db)
    config = _config(tmp_path / "snap.sqlite")
    repo.sync_networks(config.networks)
    repo.upsert_device(
        network_id="home",
        ieee_address="0x1",
        friendly_name="plug",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )
    repo.ensure_device_current_state("home", "0x1")
    repo.update_device_current_state(
        network_id="home", ieee_address="0x1", availability="offline"
    )

    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()

    cur = db.conn.execute("SELECT COUNT(*) FROM health_snapshots WHERE scope='device'")
    assert int(cur.fetchone()[0]) >= 1


def test_mqtt_to_dashboard_health(tmp_path: Path):
    db_path = tmp_path / "integration.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = _config(db_path)
    repo.sync_networks(config.networks)

    health = HealthDiagnosticService(config, repo)

    def on_recalc(network_id: str, ieee: str | None = None) -> None:
        if ieee:
            health.recalculate_device(network_id, ieee)
        else:
            health.recalculate_network(network_id)

    ingestion = MqttIngestionService(config, repo, on_health_recalc=on_recalc)
    collector = build_collector(config, repo, ingestion, client=None)
    client = FakeMqttClient(collector._handle_message)
    collector._client = client
    collector.start()

    devices = [
        {
            "ieee_address": "0x00124b0024abcd01",
            "friendly_name": "Weak Sensor",
            "type": "EndDevice",
            "power_source": "Battery",
            "interview_completed": True,
        }
    ]
    client.inject("zigbee2mqtt/bridge/state", "online")
    client.inject("zigbee2mqtt/bridge/devices", json.dumps(devices))
    client.inject("zigbee2mqtt/Weak Sensor", json.dumps({"linkquality": 25, "battery": 90}))
    client.inject("zigbee2mqtt/Weak Sensor/availability", json.dumps({"state": "online"}))

    builder = PayloadBuilder(config, repo, health)
    dash = builder.dashboard()
    assert dash.networks[0].device_count == 1
    assert dash.weak_links
    assert dash.top_affected_devices[0].health.primary == DeviceHealthPrimary.weak_link

    cur = db.conn.execute("SELECT COUNT(*) FROM health_snapshots")
    assert int(cur.fetchone()[0]) >= 1
    db.close()


def test_availability_offline_classifies_unavailable(tmp_path: Path):
    db_path = tmp_path / "offline.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = _config(db_path)
    repo.sync_networks(config.networks)
    health = HealthDiagnosticService(config, repo)

    ingestion = MqttIngestionService(
        config,
        repo,
        on_health_recalc=lambda nid, ieee: health.recalculate_device(nid, ieee)
        if ieee
        else health.recalculate_network(nid),
    )
    collector = build_collector(config, repo, ingestion, client=None)
    client = FakeMqttClient(collector._handle_message)
    collector._client = client
    collector.start()

    devices = [{"ieee_address": "0xdead", "friendly_name": "Offline Plug", "type": "Router"}]
    client.inject("zigbee2mqtt/bridge/devices", json.dumps(devices))
    client.inject("zigbee2mqtt/Offline Plug/availability", json.dumps({"state": "offline"}))

    result = health.get_device_health("home", "0xdead")
    assert result is not None
    assert result.primary == HealthFlag.unavailable
    db.close()



def test_classify_network_updated_at_uses_supplied_clock_string():
    from datetime import datetime, timezone

    from zigbeelens.config.models import DiagnosticsConfig
    from zigbeelens.diagnostics.network_health import classify_network

    now = datetime(2026, 1, 1, 12, 0, 0, 987654, tzinfo=timezone.utc)
    result, _ = classify_network(
        network_id="home",
        bridge_state="online",
        network_updated_at=now.isoformat(),
        last_mqtt_activity_at=now.isoformat(),
        device_health=[],
        router_devices=[],
        config=DiagnosticsConfig(),
        now=now,
    )
    assert result.updated_at == now.isoformat()
