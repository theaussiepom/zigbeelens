from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType

from zigbeelens.config.models import AppConfig, DiagnosticsConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.diagnostics.coordinator import EvaluationCoordinator, PeriodicEvaluationScheduler
from zigbeelens.diagnostics.incidents.lifecycle import IncidentLifecycleManager
from zigbeelens.diagnostics.incidents.models import (
    AffectedDevice,
    IncidentCandidate,
    IncidentLifecycle,
    IncidentType,
)
from zigbeelens.diagnostics.incidents.service import IncidentDiagnosticService
from zigbeelens.diagnostics.service import HealthCacheState, HealthDiagnosticService
from zigbeelens.schemas import Confidence, IncidentScope, Severity
from zigbeelens.services.payload_builder import PayloadBuilder
from zigbeelens.storage.repository import Repository


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
        ),
    )


def _repo(tmp_path: Path) -> tuple[AppConfig, Repository]:
    cfg = _config(tmp_path / "test.sqlite")
    db = Database(cfg.storage.path)
    db.migrate()
    repo = Repository(db)
    repo.sync_networks(cfg.networks)
    return cfg, repo


def _seed_device(repo: Repository, network: str, ieee: str, *, availability: str = "online", **extra) -> None:
    repo.upsert_device(
        network_id=network,
        ieee_address=ieee,
        friendly_name=extra.get("name", ieee),
        device_type=extra.get("device_type", "EndDevice"),
        power_source=extra.get("power_source", "Battery"),
        interview_state=extra.get("interview_state", "successful"),
    )
    repo.ensure_device_current_state(network, ieee)
    repo.update_device_current_state(network_id=network, ieee_address=ieee, availability=availability)


def _offline_change(repo: Repository, network: str, ieee: str, at: datetime) -> None:
    repo.db.conn.execute(
        """
        INSERT INTO availability_changes (network_id, ieee_address, from_state, to_state, changed_at)
        VALUES (?, ?, 'online', 'offline', ?)
        """,
        (network, ieee, at.isoformat()),
    )
    repo.db.conn.commit()


def _coordinator(cfg: AppConfig, repo: Repository, clock: FakeClock, events: list[str] | None = None):
    health = HealthDiagnosticService(cfg, repo)
    incidents = IncidentDiagnosticService(cfg, repo)
    dashboard_requests: list[str] = []
    coord = EvaluationCoordinator(
        health,
        incidents,
        clock=clock,
        on_event=(events.append if events is not None else None),
        on_dashboard_required=lambda: dashboard_requests.append("dashboard"),
    )
    return coord, health, incidents, dashboard_requests


def _active(repo: Repository):
    return repo.incidents.list_active_incidents()


def _candidate(
    incident_type: IncidentType,
    *,
    network_ids: list[str] | None = None,
    devices: list[AffectedDevice] | None = None,
    scope: IncidentScope = IncidentScope.network,
    title: str = "Incident",
) -> IncidentCandidate:
    return IncidentCandidate(
        dedup_key="legacy-will-be-overwritten",
        incident_type=incident_type,
        scope=scope,
        severity=Severity.watch,
        confidence=Confidence.medium,
        title=title,
        summary=title,
        explanation="explanation",
        affected_devices=devices or [],
        network_ids=network_ids or ["home"],
    )


def test_new_cache_visible_to_correlation_same_cycle(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed_device(repo, "home", "0x1", availability="online")
    coord, health, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()
    assert health.get_device_health("home", "0x1").primary.value == "healthy"

    repo.update_device_current_state(network_id="home", ieee_address="0x1", availability="offline")
    _offline_change(repo, "home", "0x1", clock.now())
    coord.evaluate_network("home")

    incidents = _active(repo)
    assert len(incidents) == 1
    assert incidents[0]["incident_type"] == IncidentType.single_device_unavailable.value


def test_single_network_evaluation_uses_complete_snapshot_universe(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed_device(repo, "home", "0x1", availability="offline")
    _seed_device(repo, "office", "0x2", availability="online")
    _offline_change(repo, "home", "0x1", clock.now())
    coord, _, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()
    home_incident = _active(repo)[0]

    clock.advance(minutes=1)
    coord.evaluate_network("office")

    after = repo.incidents.get_incident(home_incident["id"])
    assert after["lifecycle_state"] == IncidentLifecycle.open.value
    assert after["updated_at"] == home_incident["updated_at"]


def test_multi_network_incident_survives_single_network_evaluation(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    repo.update_network_bridge_state("home", "offline")
    repo.update_network_bridge_state("office", "offline")
    coord, _, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()
    multi = next(i for i in _active(repo) if i["incident_type"] == IncidentType.multi_network_instability.value)

    clock.advance(minutes=1)
    coord.evaluate_network("office")

    assert repo.incidents.get_incident(multi["id"])["lifecycle_state"] == IncidentLifecycle.open.value


def test_unknown_network_evaluation_does_not_age_incidents(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed_device(repo, "home", "0x1", availability="offline")
    _offline_change(repo, "home", "0x1", clock.now())
    coord, _, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()
    incident = _active(repo)[0]

    clock.advance(minutes=20)
    result = coord.evaluate_network("missing")

    assert result.network_ids == tuple()
    assert repo.incidents.get_incident(incident["id"])["lifecycle_state"] == IncidentLifecycle.open.value


def test_quiet_estate_open_watching_resolved_progression(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed_device(repo, "home", "0x1", availability="offline")
    _offline_change(repo, "home", "0x1", clock.now())
    coord, _, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()
    incident_id = _active(repo)[0]["id"]

    clock.advance(minutes=1)
    repo.update_device_current_state(network_id="home", ieee_address="0x1", availability="online")
    coord.evaluate_all()
    watching = repo.incidents.get_incident(incident_id)
    assert watching["lifecycle_state"] == IncidentLifecycle.watching.value
    assert watching["updated_at"] == clock.now().isoformat()

    clock.advance(minutes=11)
    coord.evaluate_all()
    resolved = repo.incidents.get_incident(incident_id)
    assert resolved["lifecycle_state"] == IncidentLifecycle.resolved.value
    assert resolved["resolved_at"] == clock.now().isoformat()
    assert repo.list_events()[0]["occurred_at"] == clock.now().isoformat()


def test_identity_key_for_every_incident_type():
    assert _candidate(IncidentType.bridge_offline, network_ids=["home"]).dedup_key == "bridge_offline:home"
    assert _candidate(IncidentType.multi_network_instability, network_ids=["office", "home"]).dedup_key == "multi_network_instability:home,office"
    assert _candidate(IncidentType.network_wide_instability, network_ids=["home"], devices=[AffectedDevice("home", "a"), AffectedDevice("home", "b")]).dedup_key == "network_wide_instability:home"
    assert _candidate(IncidentType.correlated_device_unavailability, network_ids=["home"], devices=[AffectedDevice("home", "a"), AffectedDevice("home", "b")]).dedup_key == "correlated_device_unavailability:home"
    assert _candidate(IncidentType.single_device_unavailable, network_ids=["home"], devices=[AffectedDevice("home", "a")], scope=IncidentScope.device).dedup_key == "single_device_unavailable:home:a"
    assert _candidate(IncidentType.router_risk, network_ids=["home"], devices=[AffectedDevice("home", "r", role="router_candidate")]).dedup_key == "router_risk:home:r"
    assert _candidate(IncidentType.stale_reporting_cluster, network_ids=["home"], devices=[AffectedDevice("home", "a"), AffectedDevice("home", "b")]).dedup_key == "stale_reporting_cluster:home"
    assert _candidate(IncidentType.low_battery_cluster, network_ids=["home"], devices=[AffectedDevice("home", "a"), AffectedDevice("home", "b")]).dedup_key == "low_battery_cluster:home"
    assert _candidate(IncidentType.unknown_pattern, network_ids=["home"], devices=[AffectedDevice("home", "a"), AffectedDevice("home", "b")]).dedup_key == "unknown_pattern:home"
    assert _candidate(IncidentType.interview_failure, network_ids=["home"], devices=[AffectedDevice("home", "a")], scope=IncidentScope.device).dedup_key == "interview_failure:home"
    assert _candidate(IncidentType.interview_failure, network_ids=["home"], devices=[AffectedDevice("home", "a"), AffectedDevice("home", "b")], scope=IncidentScope.network).dedup_key == "interview_failure:home"


def test_lifecycle_updates_scope_roles_and_reopen_event(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    lifecycle = IncidentLifecycleManager(cfg, repo)
    t0 = datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=timezone.utc)
    first = _candidate(IncidentType.stale_reporting_cluster, devices=[AffectedDevice("home", "a")], scope=IncidentScope.mesh_segment, title="one")
    lifecycle.sync([first], now=t0)
    incident = _active(repo)[0]

    t1 = t0 + timedelta(minutes=1)
    changed = _candidate(IncidentType.stale_reporting_cluster, devices=[AffectedDevice("home", "a", role="watched"), AffectedDevice("home", "b")], scope=IncidentScope.network, title="two")
    lifecycle.sync([changed], now=t1)
    updated = repo.incidents.get_incident(incident["id"])
    assert updated["scope"] == IncidentScope.network.value
    assert updated["explanation"] == "explanation"
    assert {d["role"] for d in repo.incidents.list_incident_devices(incident["id"])} == {"watched", "affected"}
    assert updated["updated_at"] == t1.isoformat()

    # clear to watching, then return candidate and verify stored reopen event
    t2 = t1 + timedelta(minutes=1)
    lifecycle.sync([], now=t2)
    assert repo.incidents.get_incident(incident["id"])["lifecycle_state"] == IncidentLifecycle.watching.value
    t3 = t2 + timedelta(minutes=1)
    lifecycle.sync([changed], now=t3)
    events = repo.list_events(limit=10)
    assert any(e["title"].startswith("Incident reopened:") and e["occurred_at"] == t3.isoformat() for e in events)


def test_unchanged_candidate_does_not_update_timestamp(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    lifecycle = IncidentLifecycleManager(cfg, repo)
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    candidate = _candidate(IncidentType.low_battery_cluster, devices=[AffectedDevice("home", "a"), AffectedDevice("home", "b")])
    lifecycle.sync([candidate], now=t0)
    incident = _active(repo)[0]
    lifecycle.sync([candidate], now=t0 + timedelta(minutes=5))
    assert repo.incidents.get_incident(incident["id"])["updated_at"] == t0.isoformat()
    assert [e["event_type"] for e in repo.list_events()].count("incident_updated") == 0


def test_all_evaluation_timestamps_equal_fake_clock(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, 0, 654321, tzinfo=timezone.utc))
    _seed_device(repo, "home", "0x1", availability="offline")
    _offline_change(repo, "home", "0x1", clock.now())
    coord, health, _, _ = _coordinator(cfg, repo, clock)
    coord.evaluate_all()
    assert health.get_device_health("home", "0x1").updated_at == clock.now().isoformat()
    health_snapshot = repo.get_latest_health_snapshot("device", "home", "0x1")
    assert health_snapshot["captured_at"] == clock.now().isoformat()
    incident = _active(repo)[0]
    assert incident["opened_at"] == clock.now().isoformat()
    assert repo.list_events()[0]["occurred_at"] == clock.now().isoformat()


def test_scheduler_overlap_exception_recovery_and_stop_waits():
    class CoordinatorStub:
        def __init__(self) -> None:
            self.calls = 0
            self.started = threading.Event()
            self.release = threading.Event()

        def evaluate_all(self, *, now=None):
            self.calls += 1
            if self.calls == 1:
                self.started.set()
                self.release.wait(2)
            if self.calls == 2:
                raise RuntimeError("boom")
            return None

    stub = CoordinatorStub()
    scheduler = PeriodicEvaluationScheduler(stub, interval_seconds=999)
    worker = threading.Thread(target=scheduler.run_once)
    worker.start()
    assert stub.started.wait(1)
    assert scheduler.run_once() is None
    stop_entered = threading.Event()
    stop_finished = threading.Event()

    def stop_scheduler():
        stop_entered.set()
        scheduler.stop()
        stop_finished.set()

    stopped = threading.Thread(target=stop_scheduler)
    stopped.start()
    assert stop_entered.wait(1)
    assert not stop_finished.is_set()
    stub.release.set()
    stopped.join(1)
    worker.join(1)
    assert not stopped.is_alive()
    assert scheduler.run_once() is None  # exception swallowed, future calls still return cleanly
    assert stub.calls == 2
    assert scheduler.run_once() is None
    assert stub.calls == 3


def test_dashboard_requested_once_after_events(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed_device(repo, "home", "0x1", availability="offline")
    _offline_change(repo, "home", "0x1", clock.now())
    events: list[str] = []
    coord, _, _, dashboard = _coordinator(cfg, repo, clock, events)
    coord.evaluate_all()
    assert dashboard == ["dashboard"]
    assert events[-1] == "incidents_updated"


@dataclass
class _TopoCtx:
    config: AppConfig
    repo: Repository
    health: object
    evaluation: object
    discovery: object | None = None


def test_topology_refresh_uses_coordinator_once(tmp_path: Path):
    from zigbeelens.topology.service import TopologyService

    cfg, repo = _repo(tmp_path)

    class HealthStub:
        calls = 0
        def recalculate_all(self):
            self.calls += 1

    class EvalStub:
        calls = 0
        def evaluate_all(self):
            self.calls += 1

    health = HealthStub()
    evaluation = EvalStub()
    service = TopologyService(_TopoCtx(cfg, repo, health, evaluation))
    service._refresh_diagnostics()
    assert evaluation.calls == 1
    assert health.calls == 0



def test_cached_health_changed_does_not_replay_for_unrelated_network(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed_device(repo, "home", "0x1", availability="online")
    _seed_device(repo, "office", "0x2", availability="online")
    events: list[str] = []
    coord, _, _, dashboard = _coordinator(cfg, repo, clock, events)
    coord.evaluate_all()
    events.clear()
    dashboard.clear()

    repo.update_device_current_state(network_id="home", ieee_address="0x1", availability="offline")
    _offline_change(repo, "home", "0x1", clock.now())
    home_result = coord.evaluate_network("home")
    assert home_result.health_changed is True
    events.clear()
    dashboard.clear()

    office_one = coord.evaluate_network("office")
    office_two = coord.evaluate_network("office")

    assert office_one.health_changed is False
    assert office_one.dashboard_update_required is False
    assert office_two.health_changed is False
    assert office_two.dashboard_update_required is False
    assert "health_updated" not in events
    assert dashboard == []


def test_interview_single_to_cluster_retains_incident_id(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    lifecycle = IncidentLifecycleManager(cfg, repo)
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    one = _candidate(
        IncidentType.interview_failure,
        devices=[AffectedDevice("home", "a")],
        scope=IncidentScope.device,
        title="one interview",
    )
    lifecycle.sync([one], now=t0)
    incident = _active(repo)[0]
    opened_events = [e for e in repo.list_events() if e["event_type"] == "incident_opened"]

    two = _candidate(
        IncidentType.interview_failure,
        devices=[AffectedDevice("home", "a"), AffectedDevice("home", "b")],
        scope=IncidentScope.network,
        title="cluster interview",
    )
    lifecycle.sync([two], now=t0 + timedelta(minutes=1))

    active = [i for i in _active(repo) if i["incident_type"] == IncidentType.interview_failure.value]
    assert len(active) == 1
    assert active[0]["id"] == incident["id"]
    assert active[0]["scope"] == IncidentScope.network.value
    assert {d["ieee_address"] for d in repo.incidents.list_incident_devices(incident["id"])} == {"a", "b"}
    assert len([e for e in repo.list_events() if e["event_type"] == "incident_opened"]) == len(opened_events)
    assert any(e["event_type"] == "incident_updated" for e in repo.list_events())

    lifecycle.sync([one], now=t0 + timedelta(minutes=2))
    active = [i for i in _active(repo) if i["incident_type"] == IncidentType.interview_failure.value]
    assert len(active) == 1
    assert active[0]["id"] == incident["id"]
    assert active[0]["scope"] == IncidentScope.device.value
    assert {d["ieee_address"] for d in repo.incidents.list_incident_devices(incident["id"])} == {"a"}


def test_scheduler_tick_cannot_enter_after_stop():
    class CoordinatorStub:
        calls = 0
        def evaluate_all(self, *, now=None):
            self.calls += 1
            return None

    stub = CoordinatorStub()
    scheduler = PeriodicEvaluationScheduler(stub, interval_seconds=999)
    scheduler.start()
    scheduler.stop(wait=True)
    scheduler._tick()
    assert stub.calls == 0


def test_topology_scheduler_stop_joins_thread(tmp_path: Path):
    from zigbeelens.topology.scheduler import TopologyScheduler

    cfg, repo = _repo(tmp_path)
    service = type("Svc", (), {"status": type("Status", (), {"capture_in_progress": False})()})()
    ctx = _TopoCtx(cfg, repo, object(), object())
    scheduler = TopologyScheduler(ctx, service)
    parked = threading.Event()
    scheduler._thread = threading.Thread(target=lambda: (scheduler._stop.wait(60), parked.set()))
    scheduler._thread.start()
    scheduler.stop(wait=True, timeout=1)
    assert not scheduler._thread.is_alive()


def test_dashboard_cancel_waits_for_active_publish():
    from zigbeelens.mqtt.dashboard_scheduler import DashboardPublishScheduler

    started = threading.Event()
    release = threading.Event()
    published: list[str] = []

    class Data:
        def dashboard(self):
            started.set()
            release.wait(2)
            return type("Dashboard", (), {"model_dump_json": lambda self: "{}"})()

    class Broadcaster:
        def publish_dashboard_update(self, payload):
            published.append(payload)

    ctx = type("Ctx", (), {"data": Data(), "discovery": None})()
    scheduler = DashboardPublishScheduler(ctx, Broadcaster())
    worker = threading.Thread(target=scheduler.flush)
    worker.start()
    assert started.wait(1)
    stopper = threading.Thread(target=scheduler.cancel)
    stopper.start()
    stopper.join(0.01)
    assert stopper.is_alive()
    release.set()
    stopper.join(1)
    worker.join(1)
    assert not stopper.is_alive()
    assert published == ["{}"]


def test_context_close_stops_all_repository_producers_before_db_close(tmp_path: Path, monkeypatch):
    from zigbeelens.app import context as context_module
    from zigbeelens.app.context import AppContext
    from zigbeelens.mqtt.events import EventBroadcaster

    calls: list[str] = []

    monkeypatch.setattr(context_module, "stop_topology", lambda: calls.append("topology"))
    monkeypatch.setattr(
        context_module,
        "stop_collector",
        lambda collector, broadcaster: calls.append("collector"),
    )
    monkeypatch.setattr(
        context_module,
        "stop_discovery",
        lambda discovery: (discovery.stop(wait=True), calls.append("discovery")),
    )

    class DB:
        def close(self):
            calls.append("db")

    class Scheduler:
        def stop(self, *, wait=True):
            calls.append(f"eval:{wait}")

    class Dashboard:
        def cancel(self, *, wait=True):
            calls.append(f"dashboard:{wait}")

    class Discovery:
        def stop(self, *, wait=True):
            calls.append(f"discovery_service:{wait}")

    from zigbeelens.security.browser_sessions import BrowserSessionManager

    cfg = _config(tmp_path / "close.sqlite")
    ctx = AppContext(
        config=cfg,
        db=DB(),
        repo=object(),
        data=object(),
        health=object(),
        incidents=object(),
        broadcaster=EventBroadcaster(),
        session_manager=BrowserSessionManager.from_config(cfg),
        evaluation_scheduler=Scheduler(),
        dashboard_scheduler=Dashboard(),
        discovery=Discovery(),
    )
    ctx.close()
    assert calls == [
        "topology",
        "collector",
        "eval:True",
        "dashboard:True",
        "discovery_service:True",
        "discovery",
        "db",
    ]


def test_first_partial_network_evaluation_publishes_estate_atomically(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed_device(repo, "home", "0x1", availability="online")
    _seed_device(repo, "office", "0x2", availability="online")
    observations: list[set[tuple[str, str]]] = []

    class ObservedHealth(HealthDiagnosticService):
        def _build_network_snapshot(self, network_id: str, *, now: datetime):
            snapshot = super()._build_network_snapshot(network_id, now=now)
            observations.append(set(self.all_device_health().keys()))
            return snapshot

    health = ObservedHealth(cfg, repo)
    incidents = IncidentDiagnosticService(cfg, repo)
    coord = EvaluationCoordinator(health, incidents, clock=clock)

    coord.evaluate_network("home")

    assert observations
    assert all(keys == set() for keys in observations)
    assert set(health.all_device_health()) == {("home", "0x1"), ("office", "0x2")}


def test_dashboard_publish_is_serialized_and_cancel_clears_pending():
    from zigbeelens.mqtt.dashboard_scheduler import DashboardPublishScheduler

    entered = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    class Data:
        def dashboard(self):
            calls.append("dashboard")
            entered.set()
            release.wait(2)
            return type("Dashboard", (), {"model_dump_json": lambda self: "{}"})()

    class Broadcaster:
        def publish_dashboard_update(self, payload):
            pass

    scheduler = DashboardPublishScheduler(type("Ctx", (), {"data": Data(), "discovery": None})(), Broadcaster())
    active = threading.Thread(target=scheduler.flush)
    active.start()
    assert entered.wait(1)
    scheduler.schedule()
    scheduler._publish()
    assert calls == ["dashboard"]

    stopper_done = threading.Event()
    stopper = threading.Thread(target=lambda: (scheduler.cancel(wait=True), stopper_done.set()))
    stopper.start()
    assert not stopper_done.is_set()
    release.set()
    stopper.join(1)
    active.join(1)
    assert stopper_done.is_set()
    assert calls == ["dashboard"]


def test_dashboard_scheduler_coalesces_sorted_categorical_causes():
    from zigbeelens.mqtt.dashboard_scheduler import DashboardPublishScheduler

    published: list[tuple[str, tuple[str, ...]]] = []

    class Data:
        def dashboard(self):
            return type(
                "Dashboard",
                (),
                {"model_dump_json": lambda self: "{}"},
            )()

    class Broadcaster:
        def publish_dashboard_update(self, payload, *, causes=()):
            published.append((payload, causes))

    scheduler = DashboardPublishScheduler(
        type("Ctx", (), {"data": Data(), "discovery": None})(),
        Broadcaster(),
    )
    scheduler.schedule(cause="network_health_updated")
    scheduler.schedule(cause="home_assistant_enrichment_updated")
    scheduler.flush()

    assert published == [
        (
            "{}",
            (
                "home_assistant_enrichment_updated",
                "network_health_updated",
            ),
        )
    ]


def test_dashboard_scheduler_preserves_unattributed_coalesced_work():
    from zigbeelens.mqtt.dashboard_scheduler import DashboardPublishScheduler

    published: list[tuple[str, tuple[str, ...]]] = []

    class Data:
        def dashboard(self):
            return type(
                "Dashboard",
                (),
                {"model_dump_json": lambda self: "{}"},
            )()

    class Broadcaster:
        def publish_dashboard_update(self, payload, *, causes=()):
            published.append((payload, causes))

    scheduler = DashboardPublishScheduler(
        type("Ctx", (), {"data": Data(), "discovery": None})(),
        Broadcaster(),
    )
    scheduler.schedule(cause="home_assistant_enrichment_updated")
    scheduler.schedule()
    scheduler.flush()

    assert published == [("{}", ())]


def test_dashboard_scheduler_stale_cancelled_timer_cannot_steal_causes(
    monkeypatch,
):
    from zigbeelens.mqtt import dashboard_scheduler as scheduler_module

    timers = []
    published: list[tuple[str, tuple[str, ...]]] = []

    class ControlledTimer:
        def __init__(self, _delay, callback):
            self.callback = callback
            self.cancelled = False
            self.daemon = False
            timers.append(self)

        def start(self):
            return None

        def cancel(self):
            self.cancelled = True

        def fire_despite_cancel(self):
            self.callback()

    class Data:
        def dashboard(self):
            return type(
                "Dashboard",
                (),
                {"model_dump_json": lambda self: "{}"},
            )()

    class Broadcaster:
        def publish_dashboard_update(self, payload, *, causes=()):
            published.append((payload, causes))

    monkeypatch.setattr(
        scheduler_module.threading,
        "Timer",
        ControlledTimer,
    )
    scheduler = scheduler_module.DashboardPublishScheduler(
        type("Ctx", (), {"data": Data(), "discovery": None})(),
        Broadcaster(),
    )
    scheduler.schedule(cause="home_assistant_enrichment_updated")
    scheduler.schedule(cause="home_assistant_enrichment_updated")
    assert len(timers) == 2
    assert timers[0].cancelled is True

    timers[0].fire_despite_cancel()
    assert published == []
    timers[1].fire_despite_cancel()

    assert published == [
        ("{}", ("home_assistant_enrichment_updated",))
    ]


def test_dashboard_scheduler_failure_log_is_fixed_and_identity_free(caplog):
    import logging

    from zigbeelens.mqtt.dashboard_scheduler import DashboardPublishScheduler

    private_sentinel = "private-device-name-0x00124b0024abcdef"

    class Data:
        def dashboard(self):
            raise RuntimeError(private_sentinel)

    scheduler = DashboardPublishScheduler(
        type("Ctx", (), {"data": Data(), "discovery": None})(),
        object(),
    )
    with caplog.at_level(
        logging.ERROR,
        logger="zigbeelens.mqtt.dashboard_scheduler",
    ):
        scheduler.flush()

    assert caplog.messages == [
        "Dashboard publish failed (category=dashboard_projection)"
    ]
    assert private_sentinel not in caplog.text
    assert "Traceback" not in caplog.text


def test_discovery_stop_waits_for_active_publish_and_clears_pending(tmp_path: Path):
    from zigbeelens.mqtt_discovery.service import MqttDiscoveryService

    cfg, repo = _repo(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    class Publisher:
        connected = True
        def connect(self): pass
        def disconnect(self): calls.append("disconnect")
        def publish(self, *args, **kwargs): pass
        def publish_json(self, *args, **kwargs): pass
        def delete_retained(self, *args, **kwargs): pass

    class Service(MqttDiscoveryService):
        def _publish_all(self, *, force_discovery: bool) -> None:
            calls.append("publish")
            entered.set()
            release.wait(2)

    ctx = _TopoCtx(cfg, repo, object(), object())
    service = Service(ctx, publisher=Publisher())
    service._pending_update = True
    active = threading.Thread(target=service._run_debounced_update)
    active.start()
    assert entered.wait(1)
    service.schedule_update()
    service._run_debounced_update()
    assert calls == ["publish"]

    stopped = threading.Event()
    stopper = threading.Thread(target=lambda: (service.stop(wait=True), stopped.set()))
    stopper.start()
    assert not stopped.is_set()
    release.set()
    stopper.join(1)
    active.join(1)
    assert stopped.is_set()
    assert calls == ["publish", "disconnect"]


class _NoDirectRecalculateHealth(HealthDiagnosticService):
    def recalculate_all(self) -> None:
        raise AssertionError("Payload reads must not call recalculate_all directly")

    def recalculate_device(self, network_id: str, ieee_address: str):
        raise AssertionError("Payload reads must not call recalculate_device directly")


class _CountingEvaluation:
    def __init__(self, *, health: HealthDiagnosticService | None = None, now: datetime | None = None):
        self.health = health
        self.now = now or datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        self.all_calls = 0
        self.network_calls: list[str] = []

    def evaluate_all(self, *, now=None):
        self.all_calls += 1
        if self.health is not None:
            return self.health.evaluate_all(now=now or self.now)
        return None

    def evaluate_network(self, network_id: str, *, now=None):
        self.network_calls.append(network_id)
        if self.health is not None:
            return self.health.evaluate_network(network_id, now=now or self.now)
        return None


def test_payload_dashboard_cache_miss_uses_coordinator_not_direct_recalculate_all(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    _seed_device(repo, "home", "0x1", availability="online")
    health = _NoDirectRecalculateHealth(cfg, repo)
    evaluation = _CountingEvaluation(health=health)

    PayloadBuilder(cfg, repo, health, evaluation=evaluation).dashboard()

    assert evaluation.all_calls == 1
    assert health.has_complete_network_cache(["home", "office"])


def test_payload_missing_device_cache_uses_coordinator_not_direct_recalculate_device(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    _seed_device(repo, "home", "0x1", availability="online")
    health = _NoDirectRecalculateHealth(cfg, repo)
    health.evaluate_all(now=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    # Remove only the Home device entry while keeping network/bridge cache complete.
    state = health._state
    health._state = HealthCacheState(
        devices=MappingProxyType(
            {key: value for key, value in state.devices.items() if key != ("home", "0x1")}
        ),
        networks=state.networks,
        bridges=state.bridges,
    )
    evaluation = _CountingEvaluation(health=health)

    # Device detail is decision/facts only and does not re-enter health evaluation.
    # Inventory remains the surface that ensures network health via the coordinator.
    detail = PayloadBuilder(cfg, repo, health, evaluation=evaluation).device_detail("home", "0x1")
    assert detail is not None
    assert detail.decision is not None
    assert evaluation.network_calls == []

    evaluation.network_calls.clear()
    PayloadBuilder(cfg, repo, health, evaluation=evaluation).devices()
    assert evaluation.network_calls == ["home"]
    assert health.get_device_health("home", "0x1") is not None


def test_payload_cache_miss_runs_incident_lifecycle_in_same_coordinator_cycle(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    _seed_device(repo, "home", "0x1", availability="offline")
    _offline_change(repo, "home", "0x1", clock.now())
    coord, health, incidents, _ = _coordinator(cfg, repo, clock)

    PayloadBuilder(cfg, repo, health, incidents, coord).dashboard()

    active = _active(repo)
    assert len(active) == 1
    assert active[0]["incident_type"] == IncidentType.single_device_unavailable.value
    assert repo.list_events()[0]["event_type"] == "incident_opened"


def test_dashboard_read_during_blocked_first_estate_evaluation_uses_coordinator_lock(
    tmp_path: Path,
):
    cfg, repo = _repo(tmp_path)
    _seed_device(repo, "home", "0x1", availability="online")
    _seed_device(repo, "office", "0x2", availability="online")
    entered = threading.Event()
    release = threading.Event()

    class BlockingHealth(_NoDirectRecalculateHealth):
        def evaluate_all(self, *, now: datetime):
            entered.set()
            release.wait(2)
            return super().evaluate_all(now=now)

    health = BlockingHealth(cfg, repo)
    incidents = IncidentDiagnosticService(cfg, repo)
    coord = EvaluationCoordinator(
        health,
        incidents,
        clock=FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)),
    )
    builder = PayloadBuilder(cfg, repo, health, incidents, coord)
    worker = threading.Thread(target=coord.evaluate_network, args=("home",))
    worker.start()
    assert entered.wait(1)

    dashboard_done = threading.Event()
    dashboard_worker = threading.Thread(target=lambda: (builder.dashboard(), dashboard_done.set()))
    dashboard_worker.start()
    assert not health.all_device_health()
    assert not dashboard_done.is_set()
    release.set()
    worker.join(1)
    dashboard_worker.join(1)

    assert dashboard_done.is_set()
    assert set(health.all_device_health()) == {("home", "0x1"), ("office", "0x2")}


def test_zero_device_estate_complete_cache_does_not_recurse_evaluation(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    health = _NoDirectRecalculateHealth(cfg, repo)
    health.evaluate_all(now=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))

    class FailingEvaluation:
        def evaluate_all(self, *, now=None):
            raise AssertionError("complete zero-device network cache should not evaluate again")

        def evaluate_network(self, network_id: str, *, now=None):
            raise AssertionError("no device cache miss should be evaluated")

    assert health.has_complete_network_cache(["home", "office"])
    PayloadBuilder(cfg, repo, health, evaluation=FailingEvaluation()).dashboard()


def test_builder_without_coordinator_uses_side_effect_free_health_fallback(tmp_path: Path):
    cfg, repo = _repo(tmp_path)
    _seed_device(repo, "home", "0x1", availability="online")
    health = _NoDirectRecalculateHealth(cfg, repo)

    dashboard = PayloadBuilder(cfg, repo, health).dashboard()

    assert dashboard.decision_summary.subject_count >= 0
    assert health.all_device_health() == {}
