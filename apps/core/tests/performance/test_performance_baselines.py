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
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.parser import ParsedTopology, ParsedTopologyLink, ParsedTopologyNode

from .expected_baselines import EXPECTED_BASELINES
from .query_instrumentation import OperationMeasurement, install_counter, measure_operation

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
            _seed_topology(repo, counts, devices)
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
            target_device=("home", devices["home"][5]),
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


def _seed_topology(repo: Repository, counts: dict[str, int], devices: dict[str, list[str]]) -> None:
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
            node_ieees = [coordinator, *routers, *end_devices]
            if snap == 9 and end_devices:
                node_ieees = node_ieees[:-1]  # target absent from latest but present historically
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
                if snap == 9 and idx == len(end_devices) - 1:
                    continue
                parent = routers[idx % len(routers)] if routers else coordinator
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
    service = MqttIngestionService(
        fx.config,
        fx.repo,
        on_health_recalc=lambda nid, _ieee: fx.coordinator.evaluate_network(
            nid, now=fx.clock.now()
        ),
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


def _operations() -> dict[str, tuple[str, Operation, bool]]:
    return {
        "payload_ingestion": (
            "compact",
            lambda fx: _ingest(
                fx,
                "z2m/home/home-Device-001",
                json.dumps({"last_seen": REFERENCE_ISO, "linkquality": 99, "battery": 55}),
            ),
            False,
        ),
        "availability_ingestion": (
            "compact",
            lambda fx: _ingest(
                fx, "z2m/home/home-Device-002/availability", json.dumps({"state": "offline"})
            ),
            False,
        ),
        "inventory_ingestion_compact": ("compact", _compact_inventory_refresh, False),
        "dashboard": ("compact", lambda fx: _builder(fx).dashboard(), True),
        "devices": ("compact", lambda fx: _builder(fx).devices(), True),
        "evidence_graph": ("compact", lambda fx: EvidenceGraphService(fx.repo).build("home"), True),
        "incident_list": ("compact", lambda fx: _builder(fx).incidents(), True),
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
    doc = Path("docs/performance-baseline.md").read_text(encoding="utf-8")
    labels = {
        "availability_ingestion": "Availability change ingestion",
        "dashboard": "Dashboard composition",
        "dashboard_beast": "Dashboard composition",
        "device_detail": "Device detail",
        "devices": "Devices inventory composition",
        "devices_beast": "Devices inventory composition",
        "evidence_graph": "EvidenceGraphService.build",
        "incident_detail": "Incident detail",
        "incident_list": "Incident list",
        "inventory_ingestion_beast": "Device inventory refresh",
        "inventory_ingestion_compact": "Device inventory refresh",
        "payload_ingestion": "Ordinary MQTT payload ingestion",
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
