from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from unittest.mock import patch

import pytest

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.diagnostics.clock import Clock
from zigbeelens.diagnostics.coordinator import EvaluationCoordinator
from zigbeelens.diagnostics.incidents.models import AffectedDevice
from zigbeelens.diagnostics.incidents.service import IncidentDiagnosticService
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.enrichment.ha import MatchResult
from zigbeelens.mqtt.ingestion import MqttIngestionService
from zigbeelens.mqtt.models import RawMqttMessage
from zigbeelens.mqtt.normalizer import normalize_message
from zigbeelens.schemas import ReportRequest, ReportScope
from zigbeelens.services.data_service import DataService
from zigbeelens.services.evidence_graph import EvidenceGraphService
from zigbeelens.services.payload_builder import PayloadBuilder
from zigbeelens.storage.incident_collection import build_incident_collection_query
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.parser import ParsedTopology, ParsedTopologyLink, ParsedTopologyNode

from .expected_baselines import (
    EXPECTED_BASELINES,
    EXPECTED_PHASE_BASELINES,
    TRACK_3A_COMMIT_TOTALS,
    TRACK_3B_OPERATION_TOTALS,
    TRACK_3B_PHASE_BASELINES,
    TRACK_3C_READ_EXECUTE_TOTALS,
)
from .query_instrumentation import OperationMeasurement, PhaseAccumulator, install_counter, measure_operation

REFERENCE_TIME = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
REFERENCE_ISO = REFERENCE_TIME.isoformat()


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return REFERENCE_TIME.replace(tzinfo=None)
        return REFERENCE_TIME.astimezone(tz)

    @classmethod
    def utcnow(cls):
        return REFERENCE_TIME.replace(tzinfo=None)


class FutureDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        future = REFERENCE_TIME + timedelta(days=3650)
        if tz is None:
            return future.replace(tzinfo=None)
        return future.astimezone(tz)


class FakeClock(Clock):
    def __init__(self, value: datetime = REFERENCE_TIME) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


@dataclass
class PerfFixture:
    name: str
    config: AppConfig
    db: Database
    repo: Repository
    health: HealthDiagnosticService
    incidents: IncidentDiagnosticService
    coordinator: EvaluationCoordinator
    counter: object
    device_counts: dict[str, int]
    target_device: tuple[str, str]
    active_incident_id: str
    clock: FakeClock

    def assert_integrity(self) -> None:
        assert len(self.repo.list_networks()) == len(self.device_counts)
        assert self.repo.count_devices() == sum(self.device_counts.values())
        assert self.repo.count_events() >= (160 if self.name == "beast" else 130)
        active = self.repo.incidents.get_incident(self.active_incident_id)
        assert active is not None and active["lifecycle_state"] == "open"
        assert self.repo.incidents.list_incident_devices(self.active_incident_id)
        _assert_target_exercises_historical_topology_fallback(self)


def _assert_target_exercises_historical_topology_fallback(fx: PerfFixture) -> None:
    network_id, target_ieee = fx.target_device
    device = fx.repo.get_device(network_id, target_ieee)
    assert device is not None and device.device_type == "EndDevice", (
        "performance target must be the configured Home EndDevice"
    )
    latest = fx.repo.topology.get_latest_topology_snapshot(network_id)
    assert latest is not None, "performance target requires a latest topology snapshot"
    latest_snapshot_id = latest["snapshot_id"]
    latest_nodes = fx.repo.topology.list_topology_nodes(latest_snapshot_id)
    assert all(row["ieee_address"] != target_ieee for row in latest_nodes), (
        "performance target must exercise the historical-topology fallback path: "
        "target unexpectedly appears in latest topology nodes"
    )
    latest_links = fx.repo.topology.list_topology_links(latest_snapshot_id)
    assert all(
        target_ieee not in {row["source_ieee"], row["target_ieee"]} for row in latest_links
    ), (
        "performance target must exercise the historical-topology fallback path: "
        "target unexpectedly appears in latest topology links"
    )
    earlier = [
        row
        for row in fx.repo.topology.list_topology_snapshots(network_id)
        if row["snapshot_id"] != latest_snapshot_id and row["status"] == "complete"
    ]
    assert any(
        any(
            node["ieee_address"] == target_ieee
            for node in fx.repo.topology.list_topology_nodes(row["snapshot_id"])
        )
        for row in earlier
    ), "performance target must be present in earlier topology nodes"
    assert any(
        any(
            target_ieee in {link["source_ieee"], link["target_ieee"]}
            for link in fx.repo.topology.list_topology_links(row["snapshot_id"])
        )
        for row in earlier
    ), "performance target must have an earlier topology link for historical fallback"


@contextmanager
def deterministic_fixture(tmp_path: Path, name: str):
    counts = {"home": 20} if name == "compact" else {"home": 120, "office": 44}
    db_path = tmp_path / f"{name}.sqlite"
    networks = [NetworkConfig(id=n, name=n.title(), base_topic=f"z2m/{n}") for n in counts]
    cfg = AppConfig(
        mode=ModeConfig(mock=False), networks=networks, storage=StorageConfig(path=str(db_path))
    )
    db = Database(cfg.storage.path)
    try:
        db.migrate()
        repo = Repository(db)
        with _fixed_repo_time():
            repo.sync_networks(cfg.networks)
            devices = _seed_estate(repo, name, counts)
            target_device = ("home", devices["home"][5])
            _seed_topology(
                repo,
                counts,
                devices,
                missing_latest_by_network={"home": target_device[1]},
            )
            _seed_ha(repo, devices)
            active_incident_id = _seed_incidents(repo, counts, devices)
            _seed_filter_after_limit_events(repo, devices, active_incident_id)
            health = HealthDiagnosticService(cfg, repo)
            incidents = IncidentDiagnosticService(cfg, repo)
            clock = FakeClock()
            coord = EvaluationCoordinator(health, incidents, clock=clock)
            coord.evaluate_all(now=clock.now())
            repo.update_incident(
                incident_id=active_incident_id,
                lifecycle_state="open",
                updated_at=REFERENCE_ISO,
                resolved_at=None,
            )
            for i in range(30):
                repo.insert_event(
                    event_id=f"fixture-extra-{name}-{i}",
                    network_id="home",
                    ieee_address=None,
                    event_type="audit",
                    severity="healthy",
                    title="extra",
                    summary="extra",
                    occurred_at=(REFERENCE_TIME - timedelta(hours=3, minutes=i)).isoformat(),
                )
        counter = install_counter(repo)
        counter.reset()
        fixture = PerfFixture(
            name=name,
            config=cfg,
            db=db,
            repo=repo,
            health=health,
            incidents=incidents,
            coordinator=coord,
            counter=counter,
            device_counts=counts,
            target_device=target_device,
            active_incident_id=active_incident_id,
            clock=clock,
        )
        fixture.assert_integrity()
        yield fixture
    finally:
        db.close()


@contextmanager
def _frozen_time():
    patches = [
        patch("zigbeelens.storage.repository.utc_now_iso", return_value=REFERENCE_ISO),
        patch("zigbeelens.services.reports.utc_now_iso", return_value=REFERENCE_ISO),
    ]
    for module in (
        "zigbeelens.storage.repository",
        "zigbeelens.services.payload_builder",
        "zigbeelens.services.data_service",
        "zigbeelens.decisions.device_story",
        "zigbeelens.decisions.availability_event_groups",
        "zigbeelens.decisions.topology_facts",
        "zigbeelens.decisions.model_pattern",
        "zigbeelens.services.dashboard_shared_availability",
        "zigbeelens.services.dashboard_model_patterns",
        "zigbeelens.topology.history",
        "zigbeelens.topology.passive_hints",
        "zigbeelens.topology.device_stats",
        "zigbeelens.topology.investigations",
        "zigbeelens.diagnostics.device_health",
        "zigbeelens.diagnostics.bridge_health",
        "zigbeelens.diagnostics.network_health",
        "zigbeelens.diagnostics.incidents.lifecycle",
    ):
        patches.append(patch(f"{module}.datetime", FrozenDateTime))
    try:
        for active_patch in patches:
            active_patch.start()
        yield
    finally:
        for active_patch in reversed(patches):
            active_patch.stop()


_fixed_repo_time = _frozen_time


def _seed_estate(repo: Repository, name: str, counts: dict[str, int]) -> dict[str, list[str]]:
    all_devices: dict[str, list[str]] = {}
    for net, count in counts.items():
        net_code = 1 if net == "home" else 2
        all_devices[net] = []
        for i in range(count):
            ieee = f"0x{net_code:02x}{i:014x}"
            all_devices[net].append(ieee)
            typ = "Coordinator" if i == 0 else ("Router" if i % 4 == 0 else "EndDevice")
            repo.upsert_device(
                network_id=net,
                ieee_address=ieee,
                friendly_name=f"{net}-Device-{i:03d}",
                device_type=typ,
                power_source="Mains" if typ != "EndDevice" or i % 3 == 0 else "Battery",
                manufacturer="Acme" if i % 2 else "Globex",
                model=f"Model-{i % 7}",
                interview_state="failed" if i == 3 else "successful",
            )
            repo.update_device_current_state(
                network_id=net,
                ieee_address=ieee,
                availability="offline" if i % 17 == 0 else "online",
                last_seen=(REFERENCE_TIME - timedelta(minutes=i)).isoformat(),
                last_payload_at=(REFERENCE_TIME - timedelta(minutes=i)).isoformat(),
                linkquality=45 + (i % 55),
                battery=(9 if i % 19 == 0 else 80 - (i % 30)),
            )
            snapshot_count = 6 if i % 5 == 0 else (3 if i % 3 == 0 else 1)
            for j in range(snapshot_count):
                repo.insert_device_snapshot(
                    network_id=net,
                    ieee_address=ieee,
                    availability="online" if j % 2 == 0 else "offline",
                    last_seen=(REFERENCE_TIME - timedelta(hours=j, minutes=i)).isoformat(),
                    last_payload_at=(REFERENCE_TIME - timedelta(hours=j, minutes=i)).isoformat(),
                    linkquality=40 + ((i + j) % 60),
                    battery=max(1, 90 - i % 40 - j),
                    payload_json=json.dumps({"fixture": True}),
                )
                repo.insert_metric_sample(net, ieee, "linkquality", float(40 + ((i + j) % 60)))
                repo.insert_metric_sample(net, ieee, "battery", float(max(1, 90 - i % 40 - j)))
            for j in range(2):
                repo.insert_availability_change(
                    net, ieee, "online", "offline" if j == 0 else "online"
                )
    return all_devices


def _seed_topology(
    repo: Repository,
    counts: dict[str, int],
    devices: dict[str, list[str]],
    *,
    missing_latest_by_network: dict[str, str],
) -> None:
    for net in counts:
        devs = devices[net]
        coordinator = devs[0]
        routers = [d for idx, d in enumerate(devs) if idx and idx % 4 == 0][:8]
        end_devices = [d for idx, d in enumerate(devs) if idx and idx % 4 != 0][:20]
        for snap in range(10):
            snapshot_id = f"{net}-snap-{snap:02d}"
            repo.create_topology_snapshot(
                snapshot_id=snapshot_id,
                network_id=net,
                requested_by="fixture",
                status="pending",
                warning_acknowledged=True,
            )
            missing_latest = missing_latest_by_network.get(net) if snap == 9 else None
            node_ieees = [coordinator, *routers, *end_devices]
            if missing_latest:
                node_ieees = [ieee for ieee in node_ieees if ieee != missing_latest]
            nodes = [
                ParsedTopologyNode(
                    ieee_address=ieee,
                    friendly_name=f"{net}-{idx}",
                    node_type="Coordinator"
                    if ieee == coordinator
                    else ("Router" if ieee in routers else "EndDevice"),
                    depth=0 if ieee == coordinator else 1 + (idx % 4),
                    lqi=80 - (idx % 30),
                )
                for idx, ieee in enumerate(node_ieees)
            ]
            links: list[ParsedTopologyLink] = []
            for idx, router in enumerate(routers):
                links.append(
                    ParsedTopologyLink(
                        source_ieee=coordinator,
                        target_ieee=router,
                        source_type="Coordinator",
                        target_type="Router",
                        linkquality=95 - idx,
                        route_count=idx % 3,
                    )
                )
            for idx, end in enumerate(end_devices):
                parent = routers[idx % len(routers)] if routers else coordinator
                if missing_latest and (parent == missing_latest or end == missing_latest):
                    continue
                links.append(
                    ParsedTopologyLink(
                        source_ieee=parent,
                        target_ieee=end,
                        source_type="Router",
                        target_type="EndDevice",
                        linkquality=60 + (idx % 30),
                        relationship="Child",
                        route_count=1 if idx % 5 == 0 else None,
                    )
                )
            parsed = ParsedTopology(
                nodes=nodes,
                links=links,
                router_count=len(routers),
                end_device_count=len(end_devices),
                link_count=len(links),
                raw_redacted={"fixture": True, "snapshot": snap},
            )
            repo.store_topology_parsed(snapshot_id, net, parsed, status="complete")
            captured_at = (REFERENCE_TIME - timedelta(minutes=9 - snap)).isoformat()
            repo.db.conn.execute(
                "UPDATE topology_snapshots SET captured_at = ? WHERE snapshot_id = ?",
                (captured_at, snapshot_id),
            )
            repo.db.conn.commit()


def _seed_ha(repo: Repository, devices: dict[str, list[str]]) -> None:
    matches = []
    for net, devs in devices.items():
        for idx, ieee in enumerate(devs):
            if idx % 3 == 0:
                matches.append(
                    MatchResult(
                        net,
                        ieee,
                        f"ha-{net}-{idx}",
                        f"HA {idx}",
                        f"area-{idx % 4}",
                        f"Area {idx % 4}",
                        f"sensor.{net}_{idx}",
                        "high",
                    )
                )
    repo.replace_ha_device_enrichment(matches)
    repo.update_ha_enrichment_status(
        enabled=True, matched_devices=len(matches), source="fixture", last_push_at=REFERENCE_ISO
    )


def _seed_incident_history_estate(repo: Repository) -> None:
    """Deterministic 1500-incident history estate for Track 3E scaling gates."""
    devices_home = [f"0xHIST{i:04d}" for i in range(40)]
    for ieee in devices_home:
        repo.upsert_device(
            network_id="home",
            ieee_address=ieee,
            friendly_name=f"Hist {ieee}",
            device_type="EndDevice",
            power_source="Battery",
            interview_state="successful",
        )
    equal_ts = (REFERENCE_TIME - timedelta(days=1)).isoformat()
    for index in range(1500):
        incident_id = f"hist-res-{index:04d}"
        updated_at = (
            equal_ts
            if index < 20
            else (REFERENCE_TIME - timedelta(minutes=index)).isoformat()
        )
        if index < 8:
            state = "open"
        elif index < 16:
            state = "watching"
        else:
            state = "resolved"
        repo.insert_incident(
            incident_id=incident_id,
            dedup_key=f"hist:{incident_id}",
            incident_type="device_offline",
            lifecycle_state=state,
            severity="incident",
            scope="device",
            confidence="medium",
            title=incident_id,
            summary=incident_id,
            explanation="history fixture",
            evidence=["history evidence"],
            counter_evidence=[],
            limitations=[],
            opened_at=updated_at,
            updated_at=updated_at,
        )
        if state == "resolved":
            repo.update_incident(
                incident_id=incident_id,
                lifecycle_state="resolved",
                resolved_at=updated_at,
                updated_at=updated_at,
            )
        if index % 17 == 0:
            refs: list[AffectedDevice] = []
        elif index % 19 == 0:
            refs = [AffectedDevice("home", "0xMISSING", role="primary")]
        elif index % 23 == 0:
            repo.upsert_device(
                network_id="office",
                ieee_address="0xOFFICE01",
                friendly_name="Office hist",
                device_type="EndDevice",
                power_source="Battery",
                interview_state="successful",
            )
            refs = [
                AffectedDevice("home", devices_home[index % 40], role="primary"),
                AffectedDevice("office", "0xOFFICE01", role="secondary"),
            ]
        elif index % 11 == 0:
            refs = [
                AffectedDevice("home", devices_home[offset % 40], role="primary")
                for offset in range(12)
            ]
        else:
            refs = [AffectedDevice("home", devices_home[index % 40], role="primary")]
        if refs:
            repo.replace_incident_devices(incident_id, refs)


@contextmanager
def history_fixture(tmp_path: Path):
    with deterministic_fixture(tmp_path, "compact") as fx:
        with _fixed_repo_time():
            _seed_incident_history_estate(fx.repo)
        fx.counter.reset()
        yield fx


def _seed_incidents(repo: Repository, counts: dict[str, int], devices: dict[str, list[str]]) -> str:
    active_id = "inc-open-home"
    for net in counts:
        for suffix, state in (("open", "open"), ("watch", "watching"), ("resolved", "resolved")):
            incident_id = active_id if net == "home" and suffix == "open" else f"inc-{suffix}-{net}"
            repo.insert_incident(
                incident_id=incident_id,
                dedup_key=f"fixture:{incident_id}",
                incident_type="correlated_device_unavailability",
                lifecycle_state=state,
                severity="incident" if state == "open" else "watch",
                scope="network",
                confidence="medium",
                title=f"{state} fixture incident",
                summary="fixture incident",
                explanation="fixture incident",
                evidence=["fixture evidence"],
                counter_evidence=[],
                limitations=[],
                opened_at=REFERENCE_ISO,
                updated_at=REFERENCE_ISO,
            )
            affected = [AffectedDevice(net, ieee) for ieee in devices[net][1:4]]
            repo.replace_incident_devices(incident_id, affected)
            repo.insert_event(
                event_id=f"event-{incident_id}",
                network_id=net,
                ieee_address=affected[0].ieee_address,
                event_type="incident_lifecycle",
                severity="watch",
                title="Incident lifecycle",
                summary="Incident lifecycle",
                incident_id=incident_id,
                occurred_at=REFERENCE_ISO,
            )
    return active_id


def _seed_filter_after_limit_events(
    repo: Repository, devices: dict[str, list[str]], incident_id: str
) -> None:
    target_network, target_ieee = "home", devices["home"][5]
    old = (REFERENCE_TIME - timedelta(days=2)).isoformat()
    repo.insert_event(
        event_id="older-target-device-event",
        network_id=target_network,
        ieee_address=target_ieee,
        event_type="device_payload_seen",
        severity="healthy",
        title="old target",
        summary="old target",
        occurred_at=old,
    )
    repo.insert_event(
        event_id="older-target-incident-event",
        network_id=target_network,
        ieee_address=None,
        incident_id=incident_id,
        event_type="incident_lifecycle",
        severity="watch",
        title="old incident",
        summary="old incident",
        occurred_at=old,
    )
    for i in range(125):
        ts = (REFERENCE_TIME - timedelta(minutes=i)).isoformat()
        repo.insert_event(
            event_id=f"newer-unrelated-global-{i}",
            network_id="home",
            ieee_address=devices["home"][1],
            event_type="audit",
            severity="healthy",
            title="new",
            summary="new",
            occurred_at=ts,
        )
    latest_network = repo.list_events("home", limit=20)
    latest_global = repo.list_events(limit=100)
    assert all(row["id"] != "older-target-device-event" for row in latest_network)
    assert all(row["id"] != "older-target-incident-event" for row in latest_global)


def _ingest(fx: PerfFixture, topic: str, payload: str) -> None:
    phases = getattr(fx, "phases", None)

    def on_health(nid: str, ieee: str | None) -> None:
        if phases is not None:
            phases.on_callback_entry()
        try:
            if ieee:
                fx.coordinator.evaluate_device(nid, ieee, now=fx.clock.now())
            elif nid:
                fx.coordinator.evaluate_network(nid, now=fx.clock.now())
            else:
                fx.coordinator.evaluate_all(now=fx.clock.now())
        finally:
            if phases is not None:
                phases.on_callback_exit()

    service = MqttIngestionService(
        fx.config,
        fx.repo,
        on_health_recalc=on_health,
    )
    with _fixed_repo_time():
        for event in normalize_message(
            RawMqttMessage(topic=topic, payload=payload), fx.config.networks
        ):
            service.ingest(event)


def _builder(fx: PerfFixture) -> PayloadBuilder:
    return PayloadBuilder(fx.config, fx.repo, fx.health, fx.incidents, fx.coordinator)


def _data(fx: PerfFixture) -> DataService:
    return DataService(fx.config, fx.repo, fx.health, fx.incidents, fx.coordinator)


Operation = Callable[[PerfFixture], None]


def _inventory_refresh_payload(fx: PerfFixture, network_id: str) -> str:
    rows = fx.repo.list_devices(network_id)
    expected = fx.device_counts[network_id]
    assert len(rows) == expected
    payload = [
        {
            "ieee_address": row.ieee_address,
            "friendly_name": row.friendly_name,
            "type": row.device_type,
            "power_source": row.power_source,
            "manufacturer": "RefreshCo" if idx % 2 == 0 else row.manufacturer,
            "model_id": f"RefreshModel-{idx % 5}",
            "interview_completed": idx % 11 != 0,
        }
        for idx, row in enumerate(rows)
    ]
    return json.dumps(payload)


def _compact_inventory_refresh(fx: PerfFixture) -> None:
    _ingest(fx, "z2m/home/bridge/devices", _inventory_refresh_payload(fx, "home"))
    assert fx.repo.count_devices_for_network("home") == 20
    assert fx.repo.count_devices() == 20


def _beast_inventory_refresh(fx: PerfFixture) -> None:
    _ingest(fx, "z2m/home/bridge/devices", _inventory_refresh_payload(fx, "home"))
    _ingest(fx, "z2m/office/bridge/devices", _inventory_refresh_payload(fx, "office"))
    assert fx.repo.count_devices_for_network("home") == 120
    assert fx.repo.count_devices_for_network("office") == 44
    assert fx.repo.count_devices() == 164


def _payload_ingest(fx: PerfFixture) -> None:
    # Target EndDevice at home index 5 — topic is deterministic; avoid an extra get_device
    # lookup inside the measured window that would inflate Track 3B ingestion executes.
    _ingest(
        fx,
        "z2m/home/home-Device-005",
        json.dumps({"last_seen": REFERENCE_ISO, "linkquality": 99, "battery": 55}),
    )


def _availability_ingest(fx: PerfFixture) -> None:
    # One availability transition on Home Device-002 (list_devices order index 2).
    _ingest(
        fx,
        "z2m/home/home-Device-002/availability",
        json.dumps({"state": "offline"}),
    )


def _operations() -> dict[str, tuple[str, Operation, bool]]:
    return {
        "payload_ingestion": ("compact", _payload_ingest, False),
        "payload_ingestion_beast": ("beast", _payload_ingest, False),
        "availability_ingestion": ("compact", _availability_ingest, False),
        "availability_ingestion_beast": ("beast", _availability_ingest, False),
        "inventory_ingestion_compact": ("compact", _compact_inventory_refresh, False),
        "dashboard": ("compact", lambda fx: _builder(fx).dashboard(), True),
        "devices": ("compact", lambda fx: _builder(fx).devices(), True),
        "evidence_graph": ("compact", lambda fx: EvidenceGraphService(fx.repo).build("home"), True),
        "incident_list": (
            "compact",
            lambda fx: _builder(fx).incidents_page(build_incident_collection_query()),
            True,
        ),
        "incident_list_history": (
            "history",
            lambda fx: _builder(fx).incidents_page(build_incident_collection_query(limit=50)),
            True,
        ),
        "incident_detail": (
            "compact",
            lambda fx: _builder(fx).incident(fx.active_incident_id),
            True,
        ),
        "device_detail": (
            "compact",
            lambda fx: _builder(fx).device_detail(*fx.target_device),
            True,
        ),
        "report_full": (
            "compact",
            lambda fx: _data(fx).report_preview(request=ReportRequest(scope=ReportScope.full)),
            True,
        ),
        "report_network": (
            "compact",
            lambda fx: _data(fx).report_preview(
                request=ReportRequest(scope=ReportScope.network, network_id="home")
            ),
            True,
        ),
        "report_incident": (
            "compact",
            lambda fx: _data(fx).report_preview(
                request=ReportRequest(scope=ReportScope.incident, incident_id=fx.active_incident_id)
            ),
            True,
        ),
        "report_device": (
            "compact",
            lambda fx: _data(fx).report_preview(
                request=ReportRequest(
                    scope=ReportScope.device, network_id="home", device=fx.target_device[1]
                )
            ),
            True,
        ),
        "dashboard_beast": ("beast", lambda fx: _builder(fx).dashboard(), True),
        "devices_beast": ("beast", lambda fx: _builder(fx).devices(), True),
        "inventory_ingestion_beast": ("beast", _beast_inventory_refresh, False),
    }


def _measure_isolated(tmp_path: Path, operation_name: str) -> OperationMeasurement:
    fixture_name, op, _readonly = _operations()[operation_name]
    if fixture_name == "history":
        with history_fixture(tmp_path) as fx:
            with _frozen_time():
                return measure_operation(
                    operation_name, fixture_name, "warm", fx.counter.stats, lambda: op(fx)
                )
    with deterministic_fixture(tmp_path, fixture_name) as fx:
        fx.assert_integrity()
        with _frozen_time():
            return measure_operation(
                operation_name, fixture_name, "warm", fx.counter.stats, lambda: op(fx)
            )


@pytest.mark.parametrize("operation_name", sorted(_operations()))
def test_operation_baseline_matches_snapshot(tmp_path: Path, operation_name: str):
    measured = _measure_isolated(tmp_path, operation_name)
    expected = EXPECTED_BASELINES[operation_name]
    assert measured.execute_count == expected["execute_count"]
    assert measured.executemany_count == expected["executemany_count"]
    assert measured.commit_count == expected["commit_count"]
    assert measured.rollback_count == expected["rollback_count"]
    assert dict(measured.category_counts) == expected["category_counts"]
    assert [
        {"statement": item.statement, "count": item.count}
        for item in measured.top_repeated_statements
    ] == expected["top_repeated_statements"]
    if _operations()[operation_name][2]:
        assert measured.commit_count == 0
        assert measured.rollback_count == 0
    assert measured.category_counts.get("other", 0) == expected["category_counts"].get("other", 0)


def test_target_device_exercises_historical_topology_fallback(tmp_path: Path):
    with deterministic_fixture(tmp_path, "compact") as fx:
        _assert_target_exercises_historical_topology_fallback(fx)


def test_device_detail_and_report_device_operations_use_target_device(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    with deterministic_fixture(tmp_path, "compact") as fx:
        seen: dict[str, object] = {}

        def fake_device_detail(builder, network_id, ieee_address):
            seen["device_detail"] = (network_id, ieee_address)
            return None

        def fake_report_preview(service, scenario=None, request=None, collector=None):
            seen["report_device"] = (request.network_id, request.device)
            return None

        monkeypatch.setattr(PayloadBuilder, "device_detail", fake_device_detail)
        monkeypatch.setattr(DataService, "report_preview", fake_report_preview)
        _operations()["device_detail"][1](fx)
        _operations()["report_device"][1](fx)
        assert seen["device_detail"] == fx.target_device
        assert seen["report_device"] == fx.target_device


def test_filter_after_limit_reproduction_shape(tmp_path: Path):
    with deterministic_fixture(tmp_path, "beast") as fx:
        latest_network = fx.repo.list_events("home", limit=20)
        latest_global = fx.repo.list_events(limit=100)
        assert all(row["id"] != "older-target-device-event" for row in latest_network)
        assert all(row["id"] != "older-target-incident-event" for row in latest_global)


def test_fixture_timestamps_do_not_exceed_reference_time(tmp_path: Path):
    with deterministic_fixture(tmp_path, "beast") as fx:
        checks = {
            "events": "occurred_at",
            "device_snapshots": "captured_at",
            "metric_samples": "sampled_at",
            "availability_changes": "changed_at",
            "topology_snapshots": "captured_at",
            "incidents": "updated_at",
        }
        for table, column in checks.items():
            row = fx.repo.db.conn.execute(f"SELECT MAX({column}) AS max_ts FROM {table}").fetchone()
            assert row["max_ts"] <= REFERENCE_ISO


def test_frozen_time_makes_read_measurement_independent_of_host_clock(tmp_path: Path):
    normal = _measure_isolated(tmp_path / "normal", "dashboard")
    with (
        patch("zigbeelens.storage.repository.datetime", FutureDateTime),
        patch("zigbeelens.services.payload_builder.datetime", FutureDateTime),
        patch("zigbeelens.decisions.device_story.datetime", FutureDateTime),
    ):
        future = _measure_isolated(tmp_path / "future", "dashboard")
    assert future.execute_count == normal.execute_count
    assert future.executemany_count == normal.executemany_count
    assert future.commit_count == normal.commit_count
    assert future.rollback_count == normal.rollback_count
    assert future.category_counts == normal.category_counts


def test_high_level_architectural_spies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: dict[str, int] = {}
    story_context_networks: list[str] = []
    snapshot_load_keys: list[tuple[str, str]] = []
    availability_load_keys: list[tuple[str, str]] = []
    topology_link_snapshot_ids: list[str] = []
    report_batch_scopes: list[tuple[str | None, int | None]] = []

    def count(name: str) -> None:
        calls[name] = calls.get(name, 0) + 1

    import zigbeelens.decisions.device_story as ds
    import zigbeelens.services.evidence_graph as eg

    original_network_context = ds.load_device_story_network_context
    original_snapshots = Repository.list_device_snapshots
    original_availability = Repository.list_availability_changes
    original_topology_links = Repository.list_topology_links
    original_devices = PayloadBuilder.devices
    original_eval = EvaluationCoordinator.evaluate_network
    original_report_context = DataService.report_device_context

    def network_context_spy(repo, network_id, *args, **kwargs):
        story_context_networks.append(network_id)
        return original_network_context(repo, network_id, *args, **kwargs)

    def snapshots_spy(repo, network_id, ieee_address, *args, **kwargs):
        snapshot_load_keys.append((network_id, ieee_address))
        return original_snapshots(repo, network_id, ieee_address, *args, **kwargs)

    def availability_spy(repo, network_id, ieee_address, *args, **kwargs):
        availability_load_keys.append((network_id, ieee_address))
        return original_availability(repo, network_id, ieee_address, *args, **kwargs)

    def topology_links_spy(repo, snapshot_id, *args, **kwargs):
        topology_link_snapshot_ids.append(snapshot_id)
        return original_topology_links(repo, snapshot_id, *args, **kwargs)

    def eval_spy(*args, **kwargs):
        count("evaluate_network")
        return original_eval(*args, **kwargs)

    def report_context_spy(service, scenario=None, **kwargs):
        keys = kwargs.get("device_keys")
        report_batch_scopes.append(
            (kwargs.get("network_id"), len(keys) if keys is not None else None)
        )
        return original_report_context(service, scenario, **kwargs)

    def devices_fail(*args, **kwargs):
        raise AssertionError("report/incident detail must not call public devices inventory path")

    monkeypatch.setattr(ds, "load_device_story_network_context", network_context_spy)
    monkeypatch.setattr(Repository, "list_device_snapshots", snapshots_spy)
    monkeypatch.setattr(Repository, "list_availability_changes", availability_spy)
    monkeypatch.setattr(Repository, "list_topology_links", topology_links_spy)
    monkeypatch.setattr(EvaluationCoordinator, "evaluate_network", eval_spy)
    monkeypatch.setattr(DataService, "report_device_context", report_context_spy)
    with deterministic_fixture(tmp_path, "compact") as fx:
        story_context_networks.clear()
        snapshot_load_keys.clear()
        availability_load_keys.clear()
        topology_link_snapshot_ids.clear()
        _builder(fx).devices()
        assert story_context_networks == ["home"]
        assert len(snapshot_load_keys) == len(set(snapshot_load_keys))
        assert len(snapshot_load_keys) <= fx.repo.count_devices()
        assert len(availability_load_keys) == len(set(availability_load_keys))
        assert len(availability_load_keys) <= fx.repo.count_devices()
        assert len(topology_link_snapshot_ids) == len(set(topology_link_snapshot_ids))

        before = calls.get("evaluate_network", 0)
        _builder(fx).dashboard()
        assert calls.get("evaluate_network", 0) == before

        monkeypatch.setattr(PayloadBuilder, "devices", devices_fail)
        _builder(fx).incident(fx.active_incident_id)
        _data(fx).report_preview(
            request=ReportRequest(scope=ReportScope.incident, incident_id=fx.active_incident_id)
        )
        assert report_batch_scopes[-1] == (None, 3)
        before_batches = len(report_batch_scopes)
        _data(fx).report_preview(
            request=ReportRequest(
                scope=ReportScope.device, network_id="home", device=fx.target_device[1]
            )
        )
        assert len(report_batch_scopes) == before_batches + 1
        assert report_batch_scopes[-1] == ("home", 1)
        monkeypatch.setattr(PayloadBuilder, "devices", original_devices)

        for attr in (
            "aggregate_historical_evidence",
            "aggregate_last_known_links",
            "aggregate_passive_hints",
            "observed_model_patterns_for_network",
            "observed_router_areas_for_network",
        ):
            original = getattr(eg, attr)

            def wrapper(*args, _original=original, _attr=attr, **kwargs):
                count(_attr)
                return _original(*args, **kwargs)

            monkeypatch.setattr(eg, attr, wrapper)
        EvidenceGraphService(fx.repo).build("home")
        assert calls["aggregate_historical_evidence"] == 1
        assert calls["aggregate_last_known_links"] == 1
        assert calls["aggregate_passive_hints"] == 1
        assert calls["observed_model_patterns_for_network"] == 1
        assert calls["observed_router_areas_for_network"] == 1


def test_markdown_baseline_table_matches_structured_snapshot():
    doc = (
        Path(__file__).resolve().parents[4] / "docs" / "performance-baseline.md"
    ).read_text(encoding="utf-8")
    labels = {
        "availability_ingestion": "Availability change ingestion",
        "availability_ingestion_beast": "Availability change ingestion",
        "dashboard": "Dashboard composition",
        "dashboard_beast": "Dashboard composition",
        "device_detail": "Device detail",
        "devices": "Devices inventory composition",
        "devices_beast": "Devices inventory composition",
        "evidence_graph": "EvidenceGraphService.build",
        "incident_detail": "Incident detail",
        "incident_list": "Incident list",
        "incident_list_history": "Incident list history",
        "inventory_ingestion_beast": "Device inventory refresh",
        "inventory_ingestion_compact": "Device inventory refresh",
        "payload_ingestion": "Ordinary MQTT payload ingestion",
        "payload_ingestion_beast": "Ordinary MQTT payload ingestion",
        "report_device": "Device report preview",
        "report_full": "Full report preview",
        "report_incident": "Incident report preview",
        "report_network": "Network report preview",
    }
    for key, baseline in EXPECTED_BASELINES.items():
        other = baseline["category_counts"].get("other", 0)
        row_fragment = (
            f"| {labels[key]} | {baseline['fixture']} | {baseline['state']} | "
            f"{baseline['execute_count']} | {baseline['executemany_count']} | "
            f"{baseline['commit_count']} | {baseline['rollback_count']} | {other} |"
        )
        assert row_fragment in doc
        section = doc.split(f"### {key}", 1)[1].split("\n### ", 1)[0]
        for item in baseline["top_repeated_statements"]:
            assert f"- {item['count']}× `{item['statement']}`" in section

    comparison_labels = {
        "payload_ingestion": "Payload",
        "availability_ingestion": "Availability",
        "inventory_ingestion_compact": "Compact inventory",
        "inventory_ingestion_beast": "Beast inventory",
    }
    for key, label in comparison_labels.items():
        track_3a = TRACK_3A_COMMIT_TOTALS[key]
        track_3b_total = TRACK_3B_PHASE_BASELINES[key]["total_commit_count"]
        ingestion = TRACK_3B_PHASE_BASELINES[key]["ingestion_commit_count"]
        delta = track_3b_total - track_3a
        row = f"| {label} | {track_3a} | {track_3b_total} | {ingestion} | {delta} |"
        assert row in doc

    track_3c_phase_labels = {
        "payload_ingestion": "Compact payload",
        "payload_ingestion_beast": "Beast payload",
        "availability_ingestion": "Compact availability",
        "availability_ingestion_beast": "Beast availability",
        "inventory_ingestion_compact": "Compact inventory",
        "inventory_ingestion_beast": "Beast inventory",
    }
    for key, label in track_3c_phase_labels.items():
        phase = EXPECTED_PHASE_BASELINES[key]
        phase_row = (
            f"| {label} | {phase['ingestion_execute_count']} | {phase['ingestion_commit_count']} | "
            f"{phase['post_commit_execute_count']} | {phase['post_commit_commit_count']} | "
            f"{phase['total_execute_count']} | {phase['total_commit_count']} |"
        )
        assert phase_row in doc

    for key, label in (
        ("payload_ingestion", "Compact payload"),
        ("availability_ingestion", "Compact availability"),
        ("inventory_ingestion_compact", "Compact inventory"),
        ("inventory_ingestion_beast", "Beast inventory"),
    ):
        t3b = TRACK_3B_PHASE_BASELINES[key]
        t3c = EXPECTED_PHASE_BASELINES[key]
        delta = t3c["total_execute_count"] - t3b["total_execute_count"]
        row = (
            f"| {label} | {t3b['total_execute_count']} | {t3c['total_execute_count']} | "
            f"{t3b['post_commit_execute_count']} | {t3c['post_commit_execute_count']} | {delta} |"
        )
        assert row in doc

    track_3d_labels = {
        "dashboard": "Dashboard Compact",
        "dashboard_beast": "Dashboard Beast",
        "devices": "Devices Compact",
        "devices_beast": "Devices Beast",
        "incident_list": "Incident list",
        "incident_detail": "Incident detail",
        "device_detail": "Device detail",
        "report_full": "Full report preview",
        "report_network": "Network report preview",
        "report_incident": "Incident report preview",
        "report_device": "Device report preview",
        "evidence_graph": "EvidenceGraphService.build",
    }
    for key, label in track_3d_labels.items():
        t3c = TRACK_3C_READ_EXECUTE_TOTALS[key]
        t3d = EXPECTED_BASELINES[key]["execute_count"]
        assert f"| {label} | {t3c} | {t3d} | {t3d - t3c} |" in doc


@pytest.mark.parametrize("operation_name", sorted(EXPECTED_PHASE_BASELINES))
def test_ingestion_phase_baselines(tmp_path: Path, operation_name: str):
    fixture_name, op, _readonly = _operations()[operation_name]
    with deterministic_fixture(tmp_path, fixture_name) as fx:
        fx.assert_integrity()
        fx.counter.reset()
        fx.phases = PhaseAccumulator(fx.counter)
        with _frozen_time():
            op(fx)
        measured = fx.phases.finish(operation_name)
        assert measured.as_dict() == EXPECTED_PHASE_BASELINES[operation_name]
        assert measured.ingestion_commit_count == EXPECTED_PHASE_BASELINES[operation_name][
            "ingestion_commit_count"
        ]
        assert measured.total_commit_count == EXPECTED_BASELINES[operation_name]["commit_count"]
        assert measured.total_execute_count == EXPECTED_BASELINES[operation_name]["execute_count"]


def test_track_3a_and_track_3b_history_preserved():
    assert TRACK_3A_COMMIT_TOTALS == {
        "payload_ingestion": 8,
        "availability_ingestion": 11,
        "inventory_ingestion_compact": 50,
        "inventory_ingestion_beast": 357,
    }
    assert TRACK_3B_OPERATION_TOTALS == {
        "payload_ingestion": {"execute_count": 90, "commit_count": 3},
        "availability_ingestion": {"execute_count": 100, "commit_count": 8},
        "inventory_ingestion_compact": {"execute_count": 136, "commit_count": 9},
        "inventory_ingestion_beast": {"execute_count": 963, "commit_count": 27},
    }
    for key, track_3a in TRACK_3A_COMMIT_TOTALS.items():
        track_3b = TRACK_3B_PHASE_BASELINES[key]["total_commit_count"]
        ingestion = TRACK_3B_PHASE_BASELINES[key]["ingestion_commit_count"]
        assert track_3b < track_3a
        assert ingestion >= 1
        assert TRACK_3B_OPERATION_TOTALS[key]["commit_count"] == track_3b
        # Track 3C keeps Track 3B physical commit totals for these MQTT paths.
        assert EXPECTED_BASELINES[key]["commit_count"] == track_3b
        assert EXPECTED_PHASE_BASELINES[key]["ingestion_commit_count"] == ingestion


def test_incremental_target_event_query_shape_invariants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    list_devices_calls: list[str | None] = []
    availability_keys: list[tuple[str, str]] = []
    health_snapshot_keys: list[tuple[str, str | None]] = []
    context_keys: list[tuple[str, str]] = []

    original_list = Repository.list_devices
    original_avail = Repository.count_availability_changes_in_window
    original_latest = Repository.get_latest_health_snapshot
    original_build = HealthDiagnosticService._build_context

    def list_spy(repo, network_id=None):
        list_devices_calls.append(network_id)
        return original_list(repo, network_id)

    def avail_spy(repo, network_id, ieee_address, window_hours):
        availability_keys.append((network_id, ieee_address))
        return original_avail(repo, network_id, ieee_address, window_hours)

    def latest_spy(repo, scope, network_id, ieee_address=None):
        health_snapshot_keys.append((network_id, ieee_address))
        return original_latest(repo, scope, network_id, ieee_address)

    def build_spy(service, row, bridge_state, network_updated_at=None):
        context_keys.append((row.network_id, row.ieee_address))
        return original_build(service, row, bridge_state, network_updated_at=network_updated_at)

    monkeypatch.setattr(Repository, "list_devices", list_spy)
    monkeypatch.setattr(Repository, "count_availability_changes_in_window", avail_spy)
    monkeypatch.setattr(Repository, "get_latest_health_snapshot", latest_spy)
    monkeypatch.setattr(HealthDiagnosticService, "_build_context", build_spy)

    def run(name: str):
        fixture_name, op, _readonly = _operations()[name]
        with deterministic_fixture(tmp_path / name, fixture_name) as fx:
            fx.assert_integrity()
            list_devices_calls.clear()
            availability_keys.clear()
            health_snapshot_keys.clear()
            context_keys.clear()
            with _frozen_time():
                measured = measure_operation(
                    name, fixture_name, "warm", fx.counter.stats, lambda: op(fx)
                )
            return (
                measured,
                list(list_devices_calls),
                list(availability_keys),
                list(health_snapshot_keys),
                list(context_keys),
            )

    compact, compact_lists, compact_avail, compact_health, compact_ctx = run("payload_ingestion")
    beast, beast_lists, beast_avail, beast_health, beast_ctx = run("payload_ingestion_beast")

    assert compact_lists == []
    assert beast_lists == []
    assert len(set(compact_avail)) == 1
    assert len(set(beast_avail)) == 1
    assert compact_avail[0][0] == "home"
    assert beast_avail[0][0] == "home"
    assert len(set(compact_ctx)) == 1
    assert len(set(beast_ctx)) == 1
    assert compact_ctx[0] == compact_avail[0]
    assert beast_ctx[0] == beast_avail[0]
    target_ieee = compact_avail[0][1]
    assert set(ieee for _, ieee in compact_health) <= {target_ieee, None}
    assert ("home", target_ieee) in compact_health
    assert ("home", None) in compact_health
    assert compact.category_counts["read.availability_changes"] == EXPECTED_BASELINES[
        "payload_ingestion"
    ]["category_counts"]["read.availability_changes"]
    assert beast.category_counts["read.availability_changes"] == EXPECTED_BASELINES[
        "payload_ingestion_beast"
    ]["category_counts"]["read.availability_changes"]
    assert compact.category_counts["read.health_snapshots"] == 3
    assert beast.category_counts["read.health_snapshots"] == 3
    # Beast must not pay ~144 extra per-device health classification reads.
    assert beast.execute_count - compact.execute_count < 40
    assert (
        beast.category_counts["read.availability_changes"]
        - compact.category_counts["read.availability_changes"]
        < 5
    )
    assert (
        beast.category_counts["read.health_snapshots"]
        == compact.category_counts["read.health_snapshots"]
    )