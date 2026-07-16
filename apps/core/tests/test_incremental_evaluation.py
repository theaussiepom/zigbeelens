from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from zigbeelens.config.models import AppConfig, DiagnosticsConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.diagnostics.coordinator import EvaluationCoordinator, EvaluationResult, PeriodicEvaluationScheduler
from zigbeelens.diagnostics.incidents.models import IncidentType
from zigbeelens.diagnostics.incidents.service import IncidentDiagnosticService
from zigbeelens.diagnostics.models import HealthFlag
from zigbeelens.diagnostics.service import HealthDiagnosticService, NetworkEvaluationSnapshot
from zigbeelens.mqtt.ingestion import MqttIngestionService
from zigbeelens.mqtt.models import NormalizedMqttEvent, RawMqttMessage
from zigbeelens.mqtt.normalizer import normalize_message
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.parser import ParsedTopology, ParsedTopologyLink, ParsedTopologyNode
from types import MappingProxyType
import json


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.value = now

    def now(self) -> datetime:
        return self.value

    def advance(self, **kwargs) -> None:
        self.value = self.value + timedelta(**kwargs)


def _config(path: Path) -> AppConfig:
    return AppConfig(
        mode=ModeConfig(mock=False),
        networks=[
            NetworkConfig(id="home", name="Home", base_topic="z2m-home"),
            NetworkConfig(id="office", name="Office", base_topic="z2m-office"),
        ],
        storage=StorageConfig(path=str(path)),
        diagnostics=DiagnosticsConfig(
            incident_watch_window_minutes=5,
            incident_resolution_grace_minutes=5,
            correlated_min_devices=2,
            network_wide_min_devices=3,
            stale_cluster_min_devices=2,
            low_battery_cluster_min_devices=3,
            low_battery_percent=20,
            battery_stale_after_hours=24,
            mains_stale_after_hours=12,
        ),
    )


def _repo(tmp_path: Path) -> tuple[AppConfig, Repository]:
    cfg = _config(tmp_path / "incr.sqlite")
    db = Database(cfg.storage.path)
    db.migrate()
    repo = Repository(db)
    repo.sync_networks(cfg.networks)
    return cfg, repo


def _seed(
    repo: Repository,
    network: str,
    ieee: str,
    *,
    availability: str = "online",
    battery: int | None = 80,
    device_type: str = "EndDevice",
    power_source: str = "Battery",
    interview_state: str = "successful",
    last_payload_at: str | None = None,
    manufacturer: str | None = "Acme",
    model: str | None = "Model-1",
    friendly_name: str | None = None,
    linkquality: int | None = None,
) -> None:
    repo.upsert_device(
        network_id=network,
        ieee_address=ieee,
        friendly_name=friendly_name or ieee,
        device_type=device_type,
        power_source=power_source,
        manufacturer=manufacturer,
        model=model,
        interview_state=interview_state,
    )
    repo.ensure_device_current_state(network, ieee)
    repo.update_device_current_state(
        network_id=network,
        ieee_address=ieee,
        availability=availability,
        battery=battery,
        last_payload_at=last_payload_at,
        last_seen=last_payload_at,
        linkquality=linkquality,
    )


def _seed_router_topology(repo: Repository, network: str, router_ieee: str, children: list[str]) -> None:
    snapshot_id = f"{network}-topo-latest"
    repo.create_topology_snapshot(
        snapshot_id=snapshot_id,
        network_id=network,
        requested_by="test",
        status="pending",
        warning_acknowledged=True,
    )
    nodes = [
        ParsedTopologyNode(
            ieee_address=router_ieee,
            friendly_name=router_ieee,
            node_type="Router",
            depth=1,
            lqi=90,
        ),
        *[
            ParsedTopologyNode(
                ieee_address=child,
                friendly_name=child,
                node_type="EndDevice",
                depth=2,
                lqi=70,
            )
            for child in children
        ],
    ]
    links = [
        ParsedTopologyLink(
            source_ieee=router_ieee,
            target_ieee=child,
            source_type="Router",
            target_type="EndDevice",
            linkquality=70,
            relationship="Child",
            route_count=1,
        )
        for child in children
    ]
    parsed = ParsedTopology(
        nodes=nodes,
        links=links,
        router_count=1,
        end_device_count=len(children),
        link_count=len(links),
        raw_redacted={"test": True},
    )
    repo.store_topology_parsed(snapshot_id, network, parsed, status="complete")


def _ingest_with_eval(
    cfg: AppConfig,
    repo: Repository,
    coord: EvaluationCoordinator,
    topic: str,
    payload: str | bytes,
) -> None:
    def on_health(nid: str, ieee: str | None = None) -> None:
        if ieee:
            coord.evaluate_device(nid, ieee)
        elif nid:
            coord.evaluate_network(nid)
        else:
            coord.evaluate_all()

    service = MqttIngestionService(cfg, repo, on_health_recalc=on_health)
    raw = payload if isinstance(payload, (bytes, bytearray)) else payload.encode()
    for event in normalize_message(RawMqttMessage(topic=topic, payload=raw), cfg.networks):
        service.ingest(event)


def _offline_change(repo: Repository, network: str, ieee: str, at: datetime) -> None:
    repo.db.conn.execute(
        """
        INSERT INTO availability_changes (network_id, ieee_address, from_state, to_state, changed_at)
        VALUES (?, ?, 'online', 'offline', ?)
        """,
        (network, ieee, at.isoformat()),
    )
    repo.db.conn.commit()


def _coordinator(cfg: AppConfig, repo: Repository, clock: FakeClock):
    health = HealthDiagnosticService(cfg, repo)
    incidents = IncidentDiagnosticService(cfg, repo)
    events: list[str] = []
    dashboards: list[str] = []
    coord = EvaluationCoordinator(
        health,
        incidents,
        clock=clock,
        on_event=events.append,
        on_dashboard_required=lambda: dashboards.append("dashboard"),
    )
    return coord, health, incidents, events, dashboards


def _semantic_device(result) -> tuple:
    return (
        result.primary,
        tuple(result.flags),
        result.severity,
        result.confidence,
        result.summary,
        tuple(result.evidence),
        tuple(result.counter_evidence),
        tuple(result.limitations),
    )


def _semantic_network(result) -> tuple:
    return (
        result.state,
        result.severity,
        result.confidence,
        result.summary,
        tuple(result.evidence),
        tuple(result.limitations),
        result.unavailable_count,
        result.recently_unstable_count,
        result.router_risk_count,
        result.stale_count,
        result.weak_link_count,
        result.low_battery_count,
        result.unknown_count,
    )


def _semantic_bridge(result) -> tuple:
    return (
        result.state,
        result.severity,
        result.confidence,
        result.summary,
        tuple(result.evidence),
        tuple(result.limitations),
    )


def _incident_semantic_dump(repo: Repository) -> dict[str, tuple]:
    """Compare incidents by dedup_key. Excludes generated IDs and timestamps."""
    out: dict[str, tuple] = {}
    for row in repo.incidents.list_incidents():
        devices = frozenset(
            (d["network_id"], d["ieee_address"], d["role"])
            for d in repo.incidents.list_incident_devices(row["id"])
        )
        out[row["dedup_key"]] = (
            row["incident_type"],
            row["lifecycle_state"],
            row["severity"],
            row["scope"],
            row["confidence"],
            row["title"],
            row["summary"],
            row["explanation"],
            row["evidence_json"],
            row["counter_evidence_json"],
            row["limitations_json"],
            devices,
        )
    return out


def _cache_semantic_dump(health: HealthDiagnosticService) -> tuple:
    state = health._state
    devices = {
        key: _semantic_device(value) for key, value in sorted(state.devices.items())
    }
    networks = {
        key: _semantic_network(value) for key, value in sorted(state.networks.items())
    }
    bridges = {
        key: _semantic_bridge(value) for key, value in sorted(state.bridges.items())
    }
    return (devices, networks, bridges)


def test_evaluate_device_uses_complete_universe_fallback(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed(repo, "home", "0x1", availability="offline")
    _seed(repo, "office", "0x2", availability="online")
    _offline_change(repo, "home", "0x1", clock.now())
    coord, health, _, _, _ = _coordinator(cfg, repo, clock)

    result = coord.evaluate_device("home", "0x1")
    assert set(result.network_ids) == {"home", "office"}
    assert health.has_complete_network_cache(["home", "office"])
    assert health.get_device_health("office", "0x2") is not None


def test_missing_configured_network_triggers_atomic_evaluate_all(tmp_path: Path, monkeypatch):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed(repo, "home", "0x1")
    _seed(repo, "office", "0x2")
    coord, health, _, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()
    del coord._snapshots_by_network["office"]

    calls: list[str] = []
    original = health.evaluate_all

    def spy(*, now):
        calls.append("all")
        return original(now=now)

    monkeypatch.setattr(health, "evaluate_all", spy)
    correlated: list[list[str]] = []
    original_sync = coord.incidents.correlate_and_sync

    def sync_spy(snapshots, *, now):
        correlated.append([s.network_id for s in snapshots])
        return original_sync(snapshots, now=now)

    monkeypatch.setattr(coord.incidents, "correlate_and_sync", sync_spy)
    result = coord.evaluate_device("home", "0x1", now=clock.now())
    assert calls == ["all"]
    assert set(result.network_ids) == {"home", "office"}
    assert correlated == [["home", "office"]]
    assert set(coord._snapshots_by_network) == {"home", "office"}


def test_extra_cached_removed_network_triggers_atomic_evaluate_all(tmp_path: Path, monkeypatch):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed(repo, "home", "0x1")
    _seed(repo, "office", "0xo")
    coord, health, _, events, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()
    assert "office" in health._state.networks
    assert any(key[0] == "office" for key in health._state.devices)

    repo.db.conn.execute("DELETE FROM networks WHERE id = ?", ("office",))
    repo.db.conn.commit()

    calls: list[str] = []
    original = health.evaluate_all

    def spy(*, now):
        calls.append("all")
        return original(now=now)

    monkeypatch.setattr(health, "evaluate_all", spy)
    correlated: list[list[str]] = []
    original_sync = coord.incidents.correlate_and_sync

    def sync_spy(snapshots, *, now):
        correlated.append([s.network_id for s in snapshots])
        return original_sync(snapshots, now=now)

    monkeypatch.setattr(coord.incidents, "correlate_and_sync", sync_spy)
    events.clear()
    result = coord.evaluate_device("home", "0x1", now=clock.now())

    assert calls == ["all"]
    assert set(result.network_ids) == {"home"}
    assert correlated == [["home"]]
    assert set(coord._snapshots_by_network) == {"home"}
    assert set(health._state.networks) == {"home"}
    assert set(health._state.bridges) == {"home"}
    assert all(key[0] == "home" for key in health._state.devices)


def test_incomplete_snapshot_falls_back_without_partial_construction(
    tmp_path: Path, monkeypatch
):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed(repo, "home", "0x1")
    _seed(repo, "home", "0x2")
    _seed(repo, "office", "0xo")
    coord, health, _, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()
    snapshot = coord._snapshots_by_network["home"]

    cases = {
        "missing_target": MappingProxyType(
            {key: value for key, value in snapshot.device_results.items() if key[1] != "0x1"}
        ),
        "missing_nontarget": MappingProxyType(
            {key: value for key, value in snapshot.device_results.items() if key[1] != "0x2"}
        ),
        "extra_key": MappingProxyType(
            {
                **dict(snapshot.device_results),
                ("home", "0xghost"): snapshot.device_results[("home", "0x1")],
            }
        ),
    }

    for label, broken_results in cases.items():
        broken = NetworkEvaluationSnapshot(
            network_id=snapshot.network_id,
            network_name=snapshot.network_name,
            bridge_state=snapshot.bridge_state,
            evaluated_at=snapshot.evaluated_at,
            devices=snapshot.devices,
            device_results=broken_results,
            network_result=snapshot.network_result,
            bridge_result=snapshot.bridge_result,
            health_changed=False,
        )
        assert (
            health.evaluate_device_from_snapshot(broken, "0x1", now=clock.now()) is None
        ), label

    sync_calls: list[int] = []
    original_sync = coord.incidents.correlate_and_sync

    def sync_spy(snapshots, *, now):
        sync_calls.append(len(snapshots))
        return original_sync(snapshots, now=now)

    monkeypatch.setattr(coord.incidents, "correlate_and_sync", sync_spy)
    full_calls: list[str] = []
    original_network = health.evaluate_network

    def network_spy(network_id: str, *, now):
        full_calls.append(network_id)
        return original_network(network_id, now=now)

    monkeypatch.setattr(health, "evaluate_network", network_spy)
    coord._snapshots_by_network["home"] = NetworkEvaluationSnapshot(
        network_id=snapshot.network_id,
        network_name=snapshot.network_name,
        bridge_state=snapshot.bridge_state,
        evaluated_at=snapshot.evaluated_at,
        devices=snapshot.devices,
        device_results=cases["missing_nontarget"],
        network_result=snapshot.network_result,
        bridge_result=snapshot.bridge_result,
        health_changed=False,
    )
    result = coord.evaluate_device("home", "0x1", now=clock.now())
    assert full_calls == ["home"]
    assert sync_calls == [2]
    assert set(coord._snapshots_by_network["home"].device_results) == {
        ("home", "0x1"),
        ("home", "0x2"),
    }
    assert result.network_ids == ("home",)


def test_complete_snapshot_still_uses_incremental_path(tmp_path: Path, monkeypatch):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed(repo, "home", "0x1")
    _seed(repo, "home", "0x2")
    _seed(repo, "office", "0xo")
    coord, health, _, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()
    incr_calls: list[str] = []
    full_calls: list[str] = []
    original_incr = health.evaluate_device_from_snapshot
    original_full = health.evaluate_network

    def incr_spy(snapshot, ieee_address, *, now):
        incr_calls.append(ieee_address)
        return original_incr(snapshot, ieee_address, now=now)

    def full_spy(network_id, *, now):
        full_calls.append(network_id)
        return original_full(network_id, now=now)

    monkeypatch.setattr(health, "evaluate_device_from_snapshot", incr_spy)
    monkeypatch.setattr(health, "evaluate_network", full_spy)
    coord.evaluate_device("home", "0x1", now=clock.now())
    assert incr_calls == ["0x1"]
    assert full_calls == []


def test_evaluate_device_unknown_network_is_noop(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed(repo, "home", "0x1")
    coord, _, _, events, dashboards = _coordinator(cfg, repo, clock)
    coord.evaluate_all()
    events.clear()
    dashboards.clear()

    result = coord.evaluate_device("missing", "0x1")
    assert result.network_ids == tuple()
    assert result.health_changed is False
    assert result.incident_events == tuple()
    assert events == []
    assert dashboards == []


def test_target_missing_from_snapshot_falls_back_to_full_network(tmp_path: Path, monkeypatch):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed(repo, "home", "0x1")
    _seed(repo, "home", "0x2")
    _seed(repo, "office", "0x3")
    coord, health, _, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()

    _seed(repo, "home", "0xnew")
    calls: list[str] = []
    original = health.evaluate_network

    def spy(network_id: str, *, now):
        calls.append(network_id)
        return original(network_id, now=now)

    monkeypatch.setattr(health, "evaluate_network", spy)
    result = coord.evaluate_device("home", "0xnew", now=clock.now())
    assert calls == ["home"]
    assert health.get_device_health("home", "0xnew") is not None
    assert result.network_ids == ("home",)


def test_incremental_path_does_not_list_all_devices(tmp_path: Path, monkeypatch):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed(repo, "home", "0x1")
    _seed(repo, "home", "0x2")
    _seed(repo, "office", "0x3")
    coord, health, _, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()

    list_calls: list[str] = []
    original = repo.list_devices

    def spy(network_id: str | None = None):
        list_calls.append(network_id or "*")
        return original(network_id)

    monkeypatch.setattr(repo, "list_devices", spy)
    list_calls.clear()
    coord.evaluate_device("home", "0x1", now=clock.now())
    assert list_calls == []


def test_availability_offline_opens_incident_same_cycle(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed(repo, "home", "0x1", availability="online")
    _seed(repo, "office", "0x2", availability="online")
    coord, health, _, events, dashboards = _coordinator(cfg, repo, clock)
    coord.evaluate_all()
    events.clear()
    dashboards.clear()

    repo.update_device_current_state(network_id="home", ieee_address="0x1", availability="offline")
    _offline_change(repo, "home", "0x1", clock.now())
    result = coord.evaluate_device("home", "0x1", now=clock.now())

    assert HealthFlag.unavailable in health.get_device_health("home", "0x1").flags
    active = repo.incidents.list_active_incidents()
    assert len(active) == 1
    assert active[0]["incident_type"] == IncidentType.single_device_unavailable.value
    assert result.dashboard_update_required is True
    assert "dashboard" in dashboards


def test_availability_online_moves_incident_to_watching_same_cycle(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed(repo, "home", "0x1", availability="offline")
    _seed(repo, "office", "0x2", availability="online")
    _offline_change(repo, "home", "0x1", clock.now())
    coord, health, _, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()
    assert repo.incidents.list_active_incidents()

    repo.update_device_current_state(network_id="home", ieee_address="0x1", availability="online")
    coord.evaluate_device("home", "0x1", now=clock.now())

    assert health.get_device_health("home", "0x1").primary == HealthFlag.healthy
    watching = [
        row
        for row in repo.incidents.list_incidents()
        if row["lifecycle_state"] == "watching"
    ]
    assert len(watching) == 1


def test_low_battery_cluster_membership_updates_exactly(tmp_path: Path, monkeypatch):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    for ieee in ("0xa", "0xb", "0xc"):
        _seed(repo, "home", ieee, battery=10)
    _seed(repo, "home", "0xtarget", battery=50)
    _seed(repo, "office", "0xo", battery=80)
    coord, health, _, events, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()
    active = [
        row
        for row in repo.incidents.list_active_incidents()
        if row["incident_type"] == IncidentType.low_battery_cluster.value
    ]
    assert len(active) == 1
    incident_id = active[0]["id"]
    before = {
        row["ieee_address"] for row in repo.incidents.list_incident_devices(incident_id)
    }
    assert before == {"0xa", "0xb", "0xc"}
    assert health.get_network_health("home").low_battery_count == 3

    context_keys: list[tuple[str, str]] = []
    original_build = HealthDiagnosticService._build_context

    def build_spy(service, row, bridge_state, network_updated_at=None):
        context_keys.append((row.network_id, row.ieee_address))
        return original_build(service, row, bridge_state, network_updated_at=network_updated_at)

    monkeypatch.setattr(HealthDiagnosticService, "_build_context", build_spy)
    repo.update_device_current_state(network_id="home", ieee_address="0xtarget", battery=5)
    context_keys.clear()
    events.clear()
    coord.evaluate_device("home", "0xtarget", now=clock.now())

    assert context_keys == [("home", "0xtarget")]
    active = [
        row
        for row in repo.incidents.list_active_incidents()
        if row["incident_type"] == IncidentType.low_battery_cluster.value
    ]
    assert len(active) == 1
    assert active[0]["id"] == incident_id
    after = {
        row["ieee_address"] for row in repo.incidents.list_incident_devices(incident_id)
    }
    assert after == {"0xa", "0xb", "0xc", "0xtarget"}
    assert health.get_network_health("home").low_battery_count == 4
    assert events.count("incident_opened") == 0
    assert events.count("incident_updated") >= 1

    repo.update_device_current_state(network_id="home", ieee_address="0xtarget", battery=55)
    events.clear()
    coord.evaluate_device("home", "0xtarget", now=clock.now())
    active = [
        row
        for row in repo.incidents.list_active_incidents()
        if row["incident_type"] == IncidentType.low_battery_cluster.value
    ]
    assert len(active) == 1
    assert active[0]["id"] == incident_id
    restored = {
        row["ieee_address"] for row in repo.incidents.list_incident_devices(incident_id)
    }
    assert restored == {"0xa", "0xb", "0xc"}
    assert health.get_network_health("home").low_battery_count == 3
    assert events.count("incident_opened") == 0
    assert events.count("incident_updated") >= 1


def test_interview_failure_and_recovery_via_mqtt_ingestion(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed(
        repo,
        "home",
        "0xr",
        device_type="Router",
        power_source="Mains",
        interview_state="successful",
        battery=None,
        friendly_name="Router-1",
        manufacturer="Acme",
        model="R1",
    )
    _seed(repo, "office", "0xo")
    coord, health, _, events, dashboards = _coordinator(cfg, repo, clock)
    coord.evaluate_all(now=clock.now())
    events.clear()
    dashboards.clear()

    failed_payload = json.dumps(
        {
            "type": "device_interview",
            "data": {"ieee_address": "0xr", "friendly_name": "Router-1", "status": "failed"},
        }
    )
    _ingest_with_eval(cfg, repo, coord, "z2m-home/bridge/event", failed_payload)

    device = repo.get_device("home", "0xr")
    assert device is not None
    assert device.device_type == "Router"
    assert device.power_source == "Mains"
    assert device.interview_state == "failed"
    assert device.manufacturer == "Acme"
    assert device.model == "R1"
    assert HealthFlag.interview_issue in health.get_device_health("home", "0xr").flags
    active = [
        row
        for row in repo.incidents.list_active_incidents()
        if row["incident_type"] == IncidentType.interview_failure.value
    ]
    assert len(active) == 1
    incident_id = active[0]["id"]
    members = {
        row["ieee_address"] for row in repo.incidents.list_incident_devices(incident_id)
    }
    assert members == {"0xr"}
    assert "dashboard" in dashboards
    assert any(event.startswith("incident_") for event in events)

    events.clear()
    dashboards.clear()
    success_payload = json.dumps(
        {
            "type": "device_interview",
            "data": {"ieee_address": "0xr", "friendly_name": "Router-1", "status": "successful"},
        }
    )
    _ingest_with_eval(cfg, repo, coord, "z2m-home/bridge/event", success_payload)
    device = repo.get_device("home", "0xr")
    assert device.interview_state == "successful"
    assert HealthFlag.interview_issue not in health.get_device_health("home", "0xr").flags
    active = [
        row
        for row in repo.incidents.list_active_incidents()
        if row["incident_type"] == IncidentType.interview_failure.value
    ]
    assert len(active) == 1
    assert active[0]["id"] == incident_id
    assert active[0]["lifecycle_state"] == "watching"
    assert events.count("incident_opened") == 0


def test_interview_event_without_friendly_name_preserves_identity(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed(
        repo,
        "home",
        "0x1",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
        friendly_name="Keep-Me",
        manufacturer="Globex",
        model="G2",
    )
    _seed(repo, "office", "0xo")
    coord, _, _, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()
    payload = json.dumps(
        {"type": "device_interview", "data": {"ieee_address": "0x1", "status": "failed"}}
    )
    _ingest_with_eval(cfg, repo, coord, "z2m-home/bridge/event", payload)
    device = repo.get_device("home", "0x1")
    assert device.friendly_name == "Keep-Me"
    assert device.device_type == "EndDevice"
    assert device.power_source == "Battery"
    assert device.manufacturer == "Globex"
    assert device.model == "G2"
    assert device.interview_state == "failed"


def test_non_interview_bridge_event_does_not_reset_identity(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed(
        repo,
        "home",
        "0x1",
        device_type="Router",
        power_source="Mains",
        interview_state="successful",
        friendly_name="Stable-Router",
        manufacturer="Acme",
        model="R9",
        battery=None,
    )
    _seed(repo, "office", "0xo")
    coord, _, _, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()
    payload = json.dumps(
        {
            "type": "device_announce",
            "data": {"ieee_address": "0x1", "friendly_name": "Stable-Router"},
        }
    )
    _ingest_with_eval(cfg, repo, coord, "z2m-home/bridge/event", payload)
    device = repo.get_device("home", "0x1")
    assert device.device_type == "Router"
    assert device.power_source == "Mains"
    assert device.interview_state == "successful"
    assert device.manufacturer == "Acme"
    assert device.model == "R9"


def test_router_target_parity_with_topology_evidence(tmp_path: Path, monkeypatch):
    cfg_a, repo_a = _repo(tmp_path / "a")
    cfg_b, repo_b = _repo(tmp_path / "b")
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    for repo in (repo_a, repo_b):
        _seed(repo, "home", "0xr", device_type="Router", power_source="Mains", battery=None, linkquality=90)
        _seed(repo, "home", "0xc1", battery=80)
        _seed(repo, "home", "0xc2", battery=80)
        _seed(repo, "office", "0xo")
        repo.update_network_bridge_state("home", "online")
        _seed_router_topology(repo, "home", "0xr", ["0xc1", "0xc2"])

    clock_a = FakeClock(now)
    clock_b = FakeClock(now)
    coord_a, health_a, _, _, _ = _coordinator(cfg_a, repo_a, clock_a)
    coord_b, health_b, _, _, _ = _coordinator(cfg_b, repo_b, clock_b)
    coord_a.evaluate_all(now=now)
    coord_b.evaluate_all(now=now)

    enrichment_calls: list[tuple[str, str]] = []
    import zigbeelens.topology.enrichment as enrichment

    original = enrichment.enrich_router_risk

    def spy(repo, network_id, router_ieee, affected_ieees=None):
        enrichment_calls.append((network_id, router_ieee))
        return original(repo, network_id, router_ieee, affected_ieees)

    monkeypatch.setattr(enrichment, "enrich_router_risk", spy)

    repo_a.update_device_current_state(network_id="home", ieee_address="0xr", linkquality=20)
    repo_b.update_device_current_state(network_id="home", ieee_address="0xr", linkquality=20)
    enrichment_calls.clear()
    coord_a.evaluate_device("home", "0xr", now=now)
    assert enrichment_calls
    assert set(enrichment_calls) == {("home", "0xr")}

    enrichment_calls.clear()
    coord_b.evaluate_network("home", now=now)
    assert ("home", "0xr") in enrichment_calls
    assert all(call == ("home", "0xr") for call in enrichment_calls)

    target_a = health_a.get_device_health("home", "0xr")
    target_b = health_b.get_device_health("home", "0xr")
    assert _semantic_device(target_a) == _semantic_device(target_b)
    assert any("linked devices" in item for item in target_a.evidence)
    assert any("topology" in item.lower() or "routing" in item.lower() for item in target_a.limitations)
    assert _semantic_network(health_a.get_network_health("home")) == _semantic_network(
        health_b.get_network_health("home")
    )
    assert _semantic_bridge(health_a.get_bridge_health("home")) == _semantic_bridge(
        health_b.get_bridge_health("home")
    )
    assert _cache_semantic_dump(health_a) == _cache_semantic_dump(health_b)


@pytest.mark.parametrize(
    "mutate",
    [
        "payload",
        "offline",
        "online",
        "low_battery",
        "interview",
        "noop",
        "network_affecting",
        "non_network_affecting",
    ],
)
def test_incremental_versus_full_semantic_parity(tmp_path: Path, mutate: str):
    cfg_a, repo_a = _repo(tmp_path / f"a-{mutate}")
    cfg_b, repo_b = _repo(tmp_path / f"b-{mutate}")
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    def seed(repo: Repository) -> None:
        _seed(repo, "home", "0x1", availability="online", battery=50, linkquality=80)
        _seed(repo, "home", "0x2", availability="online", battery=80, linkquality=80)
        _seed(repo, "office", "0x3", availability="online")
        if mutate == "online":
            repo.update_device_current_state(
                network_id="home", ieee_address="0x1", availability="offline"
            )
            _offline_change(repo, "home", "0x1", now)

    seed(repo_a)
    seed(repo_b)
    coord_a, health_a, _, _, _ = _coordinator(cfg_a, repo_a, FakeClock(now))
    coord_b, health_b, _, _, _ = _coordinator(cfg_b, repo_b, FakeClock(now))
    coord_a.evaluate_all(now=now)
    coord_b.evaluate_all(now=now)

    def apply(repo: Repository) -> None:
        if mutate == "payload":
            repo.update_device_current_state(
                network_id="home", ieee_address="0x1", linkquality=90, battery=55
            )
        elif mutate == "offline":
            repo.update_device_current_state(
                network_id="home", ieee_address="0x1", availability="offline"
            )
            _offline_change(repo, "home", "0x1", now)
        elif mutate == "online":
            repo.update_device_current_state(
                network_id="home", ieee_address="0x1", availability="online"
            )
        elif mutate == "low_battery":
            repo.update_device_current_state(network_id="home", ieee_address="0x1", battery=5)
        elif mutate == "interview":
            repo.upsert_device(
                network_id="home",
                ieee_address="0x1",
                friendly_name="0x1",
                device_type="EndDevice",
                power_source="Battery",
                manufacturer="Acme",
                model="Model-1",
                interview_state="failed",
            )
        elif mutate == "noop":
            pass
        elif mutate == "network_affecting":
            repo.update_device_current_state(
                network_id="home", ieee_address="0x1", availability="offline"
            )
            _offline_change(repo, "home", "0x1", now)
        elif mutate == "non_network_affecting":
            repo.update_device_current_state(
                network_id="home", ieee_address="0x1", linkquality=88
            )

    apply(repo_a)
    apply(repo_b)
    coord_a.evaluate_device("home", "0x1", now=now)
    coord_b.evaluate_network("home", now=now)

    for ieee in ("0x1", "0x2"):
        assert _semantic_device(health_a.get_device_health("home", ieee)) == _semantic_device(
            health_b.get_device_health("home", ieee)
        )
    assert _semantic_network(health_a.get_network_health("home")) == _semantic_network(
        health_b.get_network_health("home")
    )
    assert _semantic_bridge(health_a.get_bridge_health("home")) == _semantic_bridge(
        health_b.get_bridge_health("home")
    )
    assert _cache_semantic_dump(health_a) == _cache_semantic_dump(health_b)
    # Exclusions: generated incident IDs and opened_at/updated_at/resolved_at timestamps.
    assert _incident_semantic_dump(repo_a) == _incident_semantic_dump(repo_b)


def test_device_ordering_preserved_after_incremental_replace(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    for ieee in ("0xa", "0xb", "0xc"):
        _seed(repo, "home", ieee)
    _seed(repo, "office", "0xo")
    coord, health, _, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()
    before = [row.ieee_address for row in coord._snapshots_by_network["home"].devices]

    repo.update_device_current_state(network_id="home", ieee_address="0xb", battery=5)
    coord.evaluate_device("home", "0xb", now=clock.now())
    after = [row.ieee_address for row in coord._snapshots_by_network["home"].devices]
    assert after == before


def test_atomic_cache_publication_never_shows_partial_network(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed(repo, "home", "0x1", battery=80)
    _seed(repo, "home", "0x2", battery=80)
    _seed(repo, "office", "0x3")
    coord, health, _, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()

    before_target = health.get_device_health("home", "0x1")
    before_network = health.get_network_health("home")
    assert before_target is not None and before_network is not None
    assert HealthFlag.low_battery not in before_target.flags
    assert before_network.low_battery_count == 0

    release = threading.Event()
    entered = threading.Event()
    mismatches: list[str] = []

    original = health.evaluate_device_from_snapshot

    def blocked(snapshot, ieee_address, *, now):
        entered.set()
        assert release.wait(timeout=5)
        return original(snapshot, ieee_address, now=now)

    health.evaluate_device_from_snapshot = blocked  # type: ignore[method-assign]

    def writer() -> None:
        repo.update_device_current_state(network_id="home", ieee_address="0x1", battery=5)
        coord.evaluate_device("home", "0x1", now=clock.now())

    thread = threading.Thread(target=writer)
    thread.start()
    assert entered.wait(timeout=5)

    state = health._state
    home_devices = [key for key in state.devices if key[0] == "home"]
    assert len(home_devices) == 2
    assert "home" in state.networks and "home" in state.bridges
    mid_target = health.get_device_health("home", "0x1")
    mid_network = health.get_network_health("home")
    assert mid_target is not None and mid_network is not None
    assert HealthFlag.low_battery not in mid_target.flags
    assert mid_network.low_battery_count == 0
    assert _semantic_device(mid_target) == _semantic_device(before_target)
    assert _semantic_network(mid_network) == _semantic_network(before_network)
    flagged = sum(
        1
        for key in home_devices
        if HealthFlag.low_battery in state.devices[key].flags
    )
    if flagged != mid_network.low_battery_count:
        mismatches.append("pre-publish target/network mismatch")

    release.set()
    thread.join(timeout=5)
    assert not thread.is_alive()

    after_target = health.get_device_health("home", "0x1")
    after_network = health.get_network_health("home")
    assert after_target is not None and after_network is not None
    assert HealthFlag.low_battery in after_target.flags
    assert after_network.low_battery_count == 1
    state = health._state
    home_devices = [key for key in state.devices if key[0] == "home"]
    assert len(home_devices) == 2
    assert "home" in state.networks and "home" in state.bridges
    flagged = sum(
        1
        for key in home_devices
        if HealthFlag.low_battery in state.devices[key].flags
    )
    if flagged != after_network.low_battery_count:
        mismatches.append("post-publish target/network mismatch")
    assert mismatches == []


def test_concurrent_device_events_serialize_and_chain_snapshots(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed(repo, "home", "0x1", battery=80)
    _seed(repo, "home", "0x2", battery=80)
    _seed(repo, "office", "0x3")
    coord, health, _, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()

    order: list[str] = []
    a_started = threading.Event()
    release_a = threading.Event()
    errors: list[BaseException] = []

    original = health.evaluate_device_from_snapshot

    def tracked(snapshot: NetworkEvaluationSnapshot, ieee_address: str, *, now):
        order.append(f"enter:{ieee_address}:{snapshot.device_results[('home', '0x1')].summary}")
        if ieee_address == "0x1":
            a_started.set()
            assert release_a.wait(timeout=5)
        result = original(snapshot, ieee_address, now=now)
        order.append(f"exit:{ieee_address}")
        return result

    health.evaluate_device_from_snapshot = tracked  # type: ignore[method-assign]

    def worker_a() -> None:
        try:
            repo.update_device_current_state(network_id="home", ieee_address="0x1", battery=5)
            coord.evaluate_device("home", "0x1", now=clock.now())
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def worker_b() -> None:
        try:
            assert a_started.wait(timeout=5)
            repo.update_device_current_state(network_id="home", ieee_address="0x2", battery=4)
            coord.evaluate_device("home", "0x2", now=clock.now())
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t_a = threading.Thread(target=worker_a)
    t_b = threading.Thread(target=worker_b)
    t_a.start()
    t_b.start()
    assert a_started.wait(timeout=5)
    release_a.set()
    t_a.join(timeout=5)
    t_b.join(timeout=5)
    assert errors == []
    assert order[0].startswith("enter:0x1:")
    assert "exit:0x1" in order
    assert order.index("exit:0x1") < next(i for i, item in enumerate(order) if item.startswith("enter:0x2:"))
    assert HealthFlag.low_battery in health.get_device_health("home", "0x1").flags
    assert HealthFlag.low_battery in health.get_device_health("home", "0x2").flags


def test_periodic_reconciles_non_target_stale_after_incremental(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    start = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    clock = FakeClock(start)
    stale_iso = (start - timedelta(hours=20)).isoformat()
    _seed(repo, "home", "0xkeep", last_payload_at=stale_iso, battery=80)
    _seed(repo, "home", "0xtarget", battery=80, last_payload_at=start.isoformat())
    _seed(repo, "office", "0xo")
    coord, health, _, _, dashboards = _coordinator(cfg, repo, clock)
    coord.evaluate_all(now=start)
    assert health.get_device_health("home", "0xkeep").primary == HealthFlag.healthy

    clock.advance(hours=5)
    later = clock.now()
    repo.update_device_current_state(network_id="home", ieee_address="0xtarget", battery=5)
    coord.evaluate_device("home", "0xtarget", now=later)
    assert HealthFlag.stale_reporting not in health.get_device_health("home", "0xkeep").flags

    scheduler = PeriodicEvaluationScheduler(coord, interval_seconds=300.0)
    dashboards.clear()
    result = scheduler.run_once(now=later)
    assert HealthFlag.stale_reporting in health.get_device_health("home", "0xkeep").flags
    assert result.dashboard_update_required is True
    assert dashboards == ["dashboard"]


def test_incremental_and_periodic_overlap_serialize_through_coordinator(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed(repo, "home", "0x1", battery=80)
    _seed(repo, "home", "0x2", battery=80)
    _seed(repo, "office", "0xo")
    coord, health, _, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()

    order: list[str] = []
    incremental_started = threading.Event()
    release_incremental = threading.Event()
    errors: list[BaseException] = []
    original_device = health.evaluate_device_from_snapshot
    original_all = health.evaluate_all

    def tracked_device(snapshot: NetworkEvaluationSnapshot, ieee_address: str, *, now):
        order.append(f"incremental:{ieee_address}")
        incremental_started.set()
        assert release_incremental.wait(timeout=5)
        return original_device(snapshot, ieee_address, now=now)

    def tracked_all(*, now):
        order.append("periodic")
        return original_all(now=now)

    health.evaluate_device_from_snapshot = tracked_device  # type: ignore[method-assign]
    health.evaluate_all = tracked_all  # type: ignore[method-assign]

    def worker_incremental() -> None:
        try:
            repo.update_device_current_state(network_id="home", ieee_address="0x1", battery=5)
            coord.evaluate_device("home", "0x1", now=clock.now())
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def worker_periodic() -> None:
        try:
            assert incremental_started.wait(timeout=5)
            PeriodicEvaluationScheduler(coord, interval_seconds=300.0).run_once(now=clock.now())
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t_a = threading.Thread(target=worker_incremental)
    t_b = threading.Thread(target=worker_periodic)
    t_a.start()
    t_b.start()
    assert incremental_started.wait(timeout=5)
    release_incremental.set()
    t_a.join(timeout=5)
    t_b.join(timeout=5)
    assert errors == []
    assert order == ["incremental:0x1", "periodic"]
    assert HealthFlag.low_battery in health.get_device_health("home", "0x1").flags


def test_one_dashboard_schedule_per_coherent_incremental_cycle(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed(repo, "home", "0x1", availability="online", battery=80)
    _seed(repo, "office", "0xo")
    coord, health, _, events, dashboards = _coordinator(cfg, repo, clock)
    coord.evaluate_all()
    dashboards.clear()
    events.clear()
    repo.update_device_current_state(network_id="home", ieee_address="0x1", availability="offline")
    _offline_change(repo, "home", "0x1", clock.now())
    result = coord.evaluate_device("home", "0x1", now=clock.now())
    assert result.dashboard_update_required is True
    assert dashboards == ["dashboard"]
    assert any(event.startswith("incident_") for event in events)


def test_mqtt_lifecycle_routes_device_events_incrementally(tmp_path: Path, monkeypatch):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed(repo, "home", "0x1", availability="online")
    _seed(repo, "office", "0x2")
    coord, health, _, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()

    device_calls: list[tuple[str, str]] = []
    network_calls: list[str] = []
    original_device = coord.evaluate_device
    original_network = coord.evaluate_network

    def device_spy(network_id: str, ieee_address: str, *, now=None):
        device_calls.append((network_id, ieee_address))
        return original_device(network_id, ieee_address, now=now or clock.now())

    def network_spy(network_id: str, *, now=None):
        network_calls.append(network_id)
        return original_network(network_id, now=now or clock.now())

    monkeypatch.setattr(coord, "evaluate_device", device_spy)
    monkeypatch.setattr(coord, "evaluate_network", network_spy)

    def on_health_recalc(network_id: str, ieee_address: str | None = None) -> None:
        if ieee_address:
            coord.evaluate_device(network_id, ieee_address)
        elif network_id:
            coord.evaluate_network(network_id)
        else:
            coord.evaluate_all()

    svc = MqttIngestionService(cfg, repo, on_health_recalc=on_health_recalc)
    svc.ingest(
        NormalizedMqttEvent(
            event_type="device_payload_seen",
            network_id="home",
            title="payload",
            summary="payload",
            friendly_name="0x1",
            device_fields={"linkquality": 70, "battery": 40},
            raw_payload_redacted="{}",
        )
    )
    assert device_calls == [("home", "0x1")]
    assert network_calls == []

    device_calls.clear()
    svc.ingest(
        NormalizedMqttEvent(
            event_type="device_inventory_seen",
            network_id="home",
            title="inventory",
            summary="inventory",
            devices=[
                {
                    "ieee_address": "0x1",
                    "friendly_name": "0x1",
                    "type": "EndDevice",
                    "power_source": "Battery",
                    "interview_completed": True,
                }
            ],
        )
    )
    assert device_calls == []
    assert network_calls == ["home"]


def test_bridge_device_join_refreshes_network_snapshot_membership(
    tmp_path: Path, monkeypatch
):
    """Joining a device must refresh the network snapshot before later incremental eval."""
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed(repo, "home", "0x1", availability="online")
    _seed(repo, "office", "0x2")
    coord, health, _, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all(now=clock.now())
    assert health.get_device_health("home", "0xnew") is None

    network_calls: list[str] = []
    device_calls: list[tuple[str, str]] = []
    original_network = coord.evaluate_network
    original_device = coord.evaluate_device

    def network_spy(network_id: str, *, now=None):
        network_calls.append(network_id)
        return original_network(network_id, now=now or clock.now())

    def device_spy(network_id: str, ieee_address: str, *, now=None):
        device_calls.append((network_id, ieee_address))
        return original_device(network_id, ieee_address, now=now or clock.now())

    monkeypatch.setattr(coord, "evaluate_network", network_spy)
    monkeypatch.setattr(coord, "evaluate_device", device_spy)

    def on_health_recalc(network_id: str, ieee_address: str | None = None) -> None:
        if ieee_address:
            coord.evaluate_device(network_id, ieee_address)
        elif network_id:
            coord.evaluate_network(network_id)
        else:
            coord.evaluate_all()

    svc = MqttIngestionService(cfg, repo, on_health_recalc=on_health_recalc)
    svc.ingest(
        NormalizedMqttEvent(
            event_type="device_joined",
            network_id="home",
            title="joined",
            summary="joined",
            ieee_address="0xnew",
            friendly_name="New Device",
            raw_payload_redacted="{}",
        )
    )
    assert network_calls == ["home"]
    assert device_calls == []
    assert repo.get_device("home", "0xnew") is not None
    assert health.get_device_health("home", "0xnew") is not None

    # Later incremental evaluation of an existing device must see the new member.
    network_calls.clear()
    device_calls.clear()
    list_calls: list[str] = []
    original_list = repo.list_devices

    def list_spy(network_id: str | None = None):
        list_calls.append(network_id or "*")
        return original_list(network_id)

    monkeypatch.setattr(repo, "list_devices", list_spy)
    list_calls.clear()
    coord.evaluate_device("home", "0x1", now=clock.now())
    assert device_calls == [("home", "0x1")]
    assert network_calls == []
    assert list_calls == []
    snapshots = coord._complete_snapshots(coord._configured_network_ids())
    assert snapshots is not None
    home = next(item for item in snapshots if item.network_id == "home")
    assert any(row.ieee_address == "0xnew" for row in home.devices)


def test_bridge_device_leave_and_announce_refresh_network(
    tmp_path: Path, monkeypatch
):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed(repo, "home", "0x1")
    _seed(repo, "office", "0xo")
    coord, _, _, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all(now=clock.now())

    network_calls: list[str] = []
    original_network = coord.evaluate_network

    def network_spy(network_id: str, *, now=None):
        network_calls.append(network_id)
        return original_network(network_id, now=now or clock.now())

    monkeypatch.setattr(coord, "evaluate_network", network_spy)

    def on_health_recalc(network_id: str, ieee_address: str | None = None) -> None:
        if ieee_address:
            coord.evaluate_device(network_id, ieee_address)
        elif network_id:
            coord.evaluate_network(network_id)

    svc = MqttIngestionService(cfg, repo, on_health_recalc=on_health_recalc)
    for event_type in ("device_announced", "device_left"):
        network_calls.clear()
        svc.ingest(
            NormalizedMqttEvent(
                event_type=event_type,
                network_id="home",
                title=event_type,
                summary=event_type,
                ieee_address="0x1",
                friendly_name="0x1",
                raw_payload_redacted="{}",
            )
        )
        assert network_calls == ["home"], event_type

    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    for ieee in ("0x1", "0x2", "0x3"):
        _seed(repo, "home", ieee, availability="offline")
        _offline_change(repo, "home", ieee, clock.now())
    _seed(repo, "office", "0xo")
    coord, _, _, events, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()
    active = [
        row
        for row in repo.incidents.list_active_incidents()
        if row["incident_type"]
        in {
            IncidentType.network_wide_instability.value,
            IncidentType.correlated_device_unavailability.value,
        }
    ]
    assert len(active) == 1
    incident = active[0]
    incident_id = incident["id"]
    incident_type = incident["incident_type"]
    before_devices = {
        (row["ieee_address"], row["role"])
        for row in repo.incidents.list_incident_devices(incident_id)
    }
    assert {ieee for ieee, _ in before_devices} == {"0x1", "0x2", "0x3"}

    events.clear()
    repo.update_device_current_state(network_id="home", ieee_address="0x3", availability="online")
    coord.evaluate_device("home", "0x3", now=clock.now())

    active = [
        row
        for row in repo.incidents.list_active_incidents()
        if row["id"] == incident_id or row["incident_type"] == incident_type
    ]
    assert len(active) == 1
    assert active[0]["id"] == incident_id
    assert active[0]["incident_type"] == incident_type
    assert active[0]["lifecycle_state"] == "open"
    after_devices = {
        (row["ieee_address"], row["role"])
        for row in repo.incidents.list_incident_devices(incident_id)
    }
    assert {ieee for ieee, _ in after_devices} == {"0x1", "0x2"}
    assert {role for _, role in after_devices} == {role for _, role in before_devices}
    assert events.count("incident_opened") == 0
    assert events.count("incident_updated") == 1


def _opposite_name_id_repo(tmp_path: Path) -> tuple[AppConfig, Repository]:
    """Networks whose name order is opposite their ID order."""
    cfg = AppConfig(
        mode=ModeConfig(mock=False),
        networks=[
            NetworkConfig(id="z-net", name="Alpha", base_topic="z2m-alpha"),
            NetworkConfig(id="a-net", name="Zulu", base_topic="z2m-zulu"),
        ],
        storage=StorageConfig(path=str(tmp_path / "order.sqlite")),
        diagnostics=DiagnosticsConfig(
            incident_watch_window_minutes=5,
            incident_resolution_grace_minutes=5,
            correlated_min_devices=2,
            network_wide_min_devices=3,
            stale_cluster_min_devices=2,
            low_battery_cluster_min_devices=3,
            low_battery_percent=20,
            battery_stale_after_hours=24,
            mains_stale_after_hours=12,
        ),
    )
    db = Database(cfg.storage.path)
    db.migrate()
    repo = Repository(db)
    repo.sync_networks(cfg.networks)
    return cfg, repo


def test_canonical_snapshot_order_stable_across_evaluation_modes(tmp_path: Path):
    cfg, repo = _opposite_name_id_repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    name_order = [row.id for row in repo.list_networks()]
    assert name_order == ["z-net", "a-net"]
    canonical = ("a-net", "z-net")
    assert tuple(sorted(name_order)) == canonical

    _seed(repo, "a-net", "0xa1")
    _seed(repo, "a-net", "0xa2")
    _seed(repo, "z-net", "0xz1")
    _seed(repo, "z-net", "0xz2")
    repo.update_network_bridge_state("a-net", "offline")
    repo.update_network_bridge_state("z-net", "offline")

    coord, health, incidents, events, _ = _coordinator(cfg, repo, clock)

    def snapshot_ids() -> tuple[str, ...]:
        return tuple(
            snapshot.network_id
            for snapshot in EvaluationCoordinator._ordered_snapshots(
                coord._snapshots_by_network.values()
            )
        )

    def multi_candidate():
        snaps = EvaluationCoordinator._ordered_snapshots(coord._snapshots_by_network.values())
        candidates = incidents._engine.correlate(snaps, now=clock.now())
        return next(
            candidate
            for candidate in candidates
            if candidate.incident_type == IncidentType.multi_network_instability
        )

    def incident_timeline(incident_id: str) -> list[dict]:
        return [
            row
            for row in repo.list_events(limit=500)
            if row.get("incident_id") == incident_id
        ]

    first = coord.evaluate_all(now=clock.now())
    assert snapshot_ids() == canonical
    assert first.network_ids == canonical

    multi = [
        row
        for row in repo.incidents.list_active_incidents()
        if row["incident_type"] == IncidentType.multi_network_instability.value
    ]
    assert len(multi) == 1
    incident = multi[0]
    incident_id = incident["id"]
    summary = incident["summary"]
    candidate = multi_candidate()
    candidate_network_ids = list(candidate.network_ids)
    assert candidate_network_ids == list(canonical)
    assert "Zulu" in summary and "Alpha" in summary
    assert summary.index("Zulu") < summary.index("Alpha")

    timeline_before = incident_timeline(incident_id)
    assert timeline_before
    event_networks = {row["network_id"] for row in timeline_before if row["event_type"] == "incident_opened"}
    assert event_networks == {"a-net"}

    events.clear()
    repo.update_device_current_state(network_id="a-net", ieee_address="0xa1", battery=79)
    incremental = coord.evaluate_device("a-net", "0xa1", now=clock.now())
    assert snapshot_ids() == canonical
    assert events.count("incident_updated") == 0

    second = coord.evaluate_all(now=clock.now())
    assert snapshot_ids() == canonical
    assert second.network_ids == canonical
    assert incremental.network_ids == ("a-net",)

    multi_after = [
        row
        for row in repo.incidents.list_active_incidents()
        if row["incident_type"] == IncidentType.multi_network_instability.value
    ]
    assert len(multi_after) == 1
    assert multi_after[0]["id"] == incident_id
    assert multi_after[0]["summary"] == summary
    assert list(multi_candidate().network_ids) == candidate_network_ids
    timeline_after = incident_timeline(incident_id)
    assert len(timeline_after) == len(timeline_before)
    assert events.count("incident_updated") == 0
    assert {
        row["network_id"] for row in timeline_after if row["event_type"] == "incident_opened"
    } == event_networks
    assert health.has_complete_network_cache(canonical)


def test_implicit_evaluation_time_captured_after_lock_acquisition(tmp_path: Path):
    from zigbeelens.diagnostics.clock import utc_iso

    cfg, repo = _repo(tmp_path)
    start = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    clock = FakeClock(start)
    _seed(repo, "home", "0x1", battery=80)
    _seed(repo, "home", "0x2", battery=80)
    _seed(repo, "office", "0x3")
    coord, health, _, events, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all(now=start)

    for ieee in ("0xa", "0xb", "0xc"):
        _seed(repo, "home", ieee, battery=10)
    coord.evaluate_all(now=start)
    active = [
        row
        for row in repo.incidents.list_active_incidents()
        if row["incident_type"] == IncidentType.low_battery_cluster.value
    ]
    assert len(active) == 1
    incident_id = active[0]["id"]
    events.clear()

    waiting = threading.Event()
    real_lock = coord._lock

    class ObservingLock:
        def acquire(self, blocking=True, timeout=-1):
            waiting.set()
            return real_lock.acquire(blocking, timeout)

        def release(self):
            return real_lock.release()

        def __enter__(self):
            self.acquire()
            return self

        def __exit__(self, *args):
            self.release()

    coord._lock = ObservingLock()  # type: ignore[assignment]
    assert real_lock.acquire(timeout=1)

    results: list[EvaluationResult] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            repo.update_device_current_state(network_id="home", ieee_address="0x1", battery=5)
            results.append(coord.evaluate_device("home", "0x1"))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    assert waiting.wait(timeout=5)
    assert thread.is_alive()

    advanced = start + timedelta(minutes=7)
    clock.value = advanced
    real_lock.release()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert errors == []
    assert len(results) == 1

    expected_iso = utc_iso(advanced)
    result = results[0]
    assert result.evaluated_at == advanced
    refreshed = coord._snapshots_by_network["home"]
    assert refreshed.evaluated_at == advanced
    target = health.get_device_health("home", "0x1")
    assert target is not None
    assert target.updated_at == expected_iso
    persisted = repo.get_latest_health_snapshot("device", "home", "0x1")
    assert persisted is not None
    assert persisted["captured_at"] == expected_iso
    assert events.count("incident_updated") >= 1
    incident = next(row for row in repo.incidents.list_incidents() if row["id"] == incident_id)
    assert incident["updated_at"] == expected_iso
    assert incident["updated_at"] > utc_iso(start)


def test_queued_evaluations_cannot_store_older_lifecycle_timestamp(tmp_path: Path):
    from zigbeelens.diagnostics.clock import utc_iso

    cfg, repo = _repo(tmp_path)
    start = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    clock = FakeClock(start)
    for ieee in ("0xa", "0xb", "0xc"):
        _seed(repo, "home", ieee, battery=10)
    _seed(repo, "home", "0x1", battery=50)
    _seed(repo, "home", "0x2", battery=50)
    _seed(repo, "office", "0xo")
    coord, _, _, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all(now=start)
    active = [
        row
        for row in repo.incidents.list_active_incidents()
        if row["incident_type"] == IncidentType.low_battery_cluster.value
    ]
    assert len(active) == 1
    incident_id = active[0]["id"]

    first_started = threading.Event()
    release_first = threading.Event()
    second_waiting = threading.Event()
    real_lock = coord._lock
    acquire_count = 0
    acquire_gate = threading.Lock()

    class ObservingLock:
        def acquire(self, blocking=True, timeout=-1):
            nonlocal acquire_count
            with acquire_gate:
                acquire_count += 1
                count = acquire_count
            if count == 2:
                second_waiting.set()
            return real_lock.acquire(blocking, timeout)

        def release(self):
            return real_lock.release()

        def __enter__(self):
            self.acquire()
            return self

        def __exit__(self, *args):
            self.release()

    original = coord.health.evaluate_device_from_snapshot

    def gated(snapshot, ieee_address, *, now):
        if ieee_address == "0x1":
            first_started.set()
            assert release_first.wait(timeout=5)
        return original(snapshot, ieee_address, now=now)

    coord._lock = ObservingLock()  # type: ignore[assignment]
    coord.health.evaluate_device_from_snapshot = gated  # type: ignore[method-assign]

    errors: list[BaseException] = []

    def worker_first() -> None:
        try:
            repo.update_device_current_state(network_id="home", ieee_address="0x1", battery=5)
            coord.evaluate_device("home", "0x1")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def worker_second() -> None:
        try:
            assert first_started.wait(timeout=5)
            repo.update_device_current_state(network_id="home", ieee_address="0x2", battery=4)
            coord.evaluate_device("home", "0x2")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=worker_first)
    t2 = threading.Thread(target=worker_second)
    t1.start()
    assert first_started.wait(timeout=5)
    t2.start()
    assert second_waiting.wait(timeout=5)

    later = start + timedelta(minutes=3)
    clock.value = later
    release_first.set()
    t1.join(timeout=5)
    t2.join(timeout=5)
    assert errors == []
    assert not t1.is_alive()
    assert not t2.is_alive()

    incident = next(row for row in repo.incidents.list_incidents() if row["id"] == incident_id)
    assert incident["updated_at"] == utc_iso(later)
    assert incident["updated_at"] > utc_iso(start)
