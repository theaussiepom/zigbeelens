"""Track 3D bulk composition reads and scoped event query tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from performance.query_instrumentation import install_counter
from performance.test_performance_baselines import (
    REFERENCE_TIME,
    _builder,
    _data,
    _frozen_time,
    deterministic_fixture,
)
from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.device_story import (
    device_stories_for_devices,
    device_story_for_device,
    load_device_story_evidence,
)
from zigbeelens.diagnostics.incidents.models import AffectedDevice
from zigbeelens.diagnostics.incidents.service import (
    IncidentDiagnosticService,
    build_active_incident_read_context,
)
from zigbeelens.schemas import ReportRequest, ReportScope
from zigbeelens.services import payload_builder as payload_builder_module
from zigbeelens.services.payload_builder import PayloadBuilder
from zigbeelens.storage import repository as repository_module
from zigbeelens.storage.repository import Repository

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "bulk.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
            NetworkConfig(id="office", name="Office", base_topic="z2m-office"),
        ],
        storage=StorageConfig(path=str(tmp_path / "bulk.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    return repo


def _seed_device(repo: Repository, network_id: str, ieee: str, *, friendly: str | None = None) -> None:
    repo.upsert_device(
        network_id=network_id,
        ieee_address=ieee,
        friendly_name=friendly or f"Device {ieee}",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )
    repo.update_device_current_state(
        network_id=network_id,
        ieee_address=ieee,
        availability="online",
        last_seen=NOW.isoformat(),
        linkquality=120,
        battery=80,
    )


def _seed_incident(
    repo: Repository,
    incident_id: str,
    *,
    refs: list[tuple[str, str]],
    lifecycle: str = "open",
    updated_at: str | None = None,
    dedup_key: str | None = None,
) -> None:
    ts = updated_at or NOW.isoformat()
    repo.insert_incident(
        incident_id=incident_id,
        dedup_key=dedup_key or f"dedup:{incident_id}",
        incident_type="device_offline",
        lifecycle_state=lifecycle,
        severity="incident",
        scope="device",
        confidence="likely",
        title=f"Incident {incident_id}",
        summary=f"Summary {incident_id}",
        explanation="Explanation",
        evidence=["evidence"],
        counter_evidence=[],
        limitations=[],
        opened_at=ts,
        updated_at=ts,
    )
    repo.replace_incident_devices(
        incident_id,
        [AffectedDevice(network_id, ieee, role="primary") for network_id, ieee in refs],
    )


def test_empty_bulk_inputs_execute_zero_sql(tmp_path: Path):
    repo = _repo(tmp_path)
    counter = install_counter(repo)
    counter.reset()
    assert repo.list_incident_devices_for_incidents([]) == {}
    assert repo.list_incident_ids_for_devices([]) == {}
    assert repo.get_devices_by_keys([]) == {}
    assert repo.list_ha_device_enrichment_for_devices([]) == {}
    assert repo.list_events_for_incidents([]) == {}
    assert counter.stats.execute_count == 0


def test_bulk_api_one_and_multi_item_parity(tmp_path: Path):
    repo = _repo(tmp_path)
    _seed_device(repo, "home", "0xA1")
    _seed_device(repo, "home", "0xA2")
    _seed_device(repo, "office", "0xB1")
    repo.db.conn.execute(
        """
        INSERT INTO ha_device_enrichment (
            network_id, ieee_address, ha_device_id, ha_device_name,
            area_id, area_name, entity_id, match_confidence, updated_at
        ) VALUES
            ('home', '0xA1', 'ha-a1', 'HA A1', 'area-1', 'Kitchen', 'sensor.a1', 0.9, ?),
            ('office', '0xB1', 'ha-b1', 'HA B1', 'area-2', 'Desk', 'sensor.b1', 0.8, ?)
        """,
        (NOW.isoformat(), NOW.isoformat()),
    )
    repo.db.conn.commit()
    _seed_incident(
        repo,
        "inc-1",
        refs=[("home", "0xA1")],
        updated_at=(NOW - timedelta(hours=1)).isoformat(),
    )
    _seed_incident(repo, "inc-2", refs=[("home", "0xA1"), ("home", "0xA2")], updated_at=NOW.isoformat())
    _seed_incident(repo, "inc-empty", refs=[], lifecycle="watching")
    _seed_incident(
        repo,
        "inc-resolved",
        refs=[("home", "0xA2")],
        lifecycle="resolved",
        updated_at=(NOW - timedelta(days=1)).isoformat(),
    )

    keys = [("home", "0xA1"), ("home", "0xA2"), ("office", "0xB1"), ("home", "0xMISSING")]
    incident_ids = ["inc-1", "inc-2", "inc-empty", "inc-missing"]

    bulk_refs = repo.list_incident_devices_for_incidents(incident_ids)
    assert set(bulk_refs) == set(incident_ids)
    for incident_id in incident_ids:
        if incident_id == "inc-missing":
            assert bulk_refs[incident_id] == []
        else:
            assert bulk_refs[incident_id] == repo.list_incident_devices(incident_id)

    bulk_devices = repo.get_devices_by_keys(keys)
    assert ("home", "0xMISSING") not in bulk_devices
    for key in [("home", "0xA1"), ("home", "0xA2"), ("office", "0xB1")]:
        single = repo.get_device(*key)
        assert single is not None
        assert bulk_devices[key] == single

    bulk_ha = repo.list_ha_device_enrichment_for_devices(keys)
    assert ("home", "0xA2") not in bulk_ha
    assert ("home", "0xMISSING") not in bulk_ha
    for key in [("home", "0xA1"), ("office", "0xB1")]:
        assert bulk_ha[key] == repo.get_ha_device_enrichment(*key)

    bulk_ids = repo.list_incident_ids_for_devices(keys)
    assert set(bulk_ids) == set(keys)
    for key in keys:
        assert bulk_ids[key] == repo.list_incidents_for_device(*key)
    assert "inc-resolved" not in bulk_ids[("home", "0xA2")]


def test_parameter_chunking_covers_all_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = _repo(tmp_path)
    monkeypatch.setattr(repository_module, "_SAFE_ID_CHUNK", 3)
    monkeypatch.setattr(repository_module, "_SAFE_PAIR_CHUNK", 2)
    keys = []
    for i in range(5):
        ieee = f"0xC{i:02X}"
        _seed_device(repo, "home", ieee)
        keys.append(("home", ieee))
        _seed_incident(repo, f"chunk-inc-{i}", refs=[("home", ieee)])
    counter = install_counter(repo)
    counter.reset()
    refs = repo.list_incident_devices_for_incidents([f"chunk-inc-{i}" for i in range(5)])
    assert len(refs) == 5
    assert all(refs[f"chunk-inc-{i}"] for i in range(5))
    id_queries = [
        sql
        for sql in counter.stats.statements
        if "FROM incident_devices" in sql and "IN (" in sql
    ]
    assert len(id_queries) == 2  # ceil(5/3)

    counter.reset()
    devices = repo.get_devices_by_keys(keys)
    assert set(devices) == set(keys)
    pair_queries = [
        sql for sql in counter.stats.statements if "WITH requested(network_id, ieee_address)" in sql
    ]
    assert len(pair_queries) == 3  # ceil(5/2)
    for sql in counter.stats.statements:
        assert "0xC" not in sql


def test_active_incident_read_context_and_network_counts(tmp_path: Path):
    repo = _repo(tmp_path)
    _seed_device(repo, "home", "0xA1")
    _seed_device(repo, "office", "0xB1")
    _seed_incident(repo, "inc-home", refs=[("home", "0xA1")])
    _seed_incident(repo, "inc-multi", refs=[("home", "0xA1"), ("office", "0xB1")])
    _seed_incident(
        repo,
        "inc-dedup-only",
        refs=[],
        dedup_key="bridge_offline:home",
        lifecycle="watching",
    )
    _seed_incident(repo, "inc-resolved", refs=[("home", "0xA1")], lifecycle="resolved")

    ctx = build_active_incident_read_context(repo)
    assert {row["id"] for row in ctx.incidents} == {"inc-home", "inc-multi", "inc-dedup-only"}
    assert ("home", "0xA1") in ctx.affected_keys
    assert ("office", "0xB1") in ctx.affected_keys
    assert ctx.active_count_by_network_id["home"] == 3
    assert ctx.active_count_by_network_id["office"] == 1
    svc = IncidentDiagnosticService(
        AppConfig(
            mode=ModeConfig(mock=True),
            networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
            storage=StorageConfig(path=str(tmp_path / "bulk.sqlite")),
        ),
        repo,
    )
    assert svc.network_active_count("home", context=ctx) == 3
    assert svc.incident_affected_keys(context=ctx) == set(ctx.affected_keys)


def test_device_story_batch_parity_and_authority(tmp_path: Path):
    with deterministic_fixture(tmp_path, "compact") as fx:
        rows = fx.repo.list_devices("home")[:5]
        with _frozen_time():
            singles = {
                (row.network_id, row.ieee_address): device_story_for_device(
                    fx.repo, row.network_id, row.ieee_address, now=REFERENCE_TIME
                )
                for row in rows
            }
            batch = device_stories_for_devices(fx.repo, rows, now=REFERENCE_TIME)
        assert set(batch) == {key for key, story in singles.items() if story is not None}
        for key, story in batch.items():
            single = singles[key]
            assert single is not None
            assert story.model_dump() == single.model_dump()
            assert story.status == single.status
            assert story.priority == single.priority
            assert story.headline_code == single.headline_code
            assert story.reasons == single.reasons


def test_device_story_preloaded_wrong_key_raises(tmp_path: Path):
    with deterministic_fixture(tmp_path, "compact") as fx:
        row = fx.repo.list_devices("home")[0]
        other = fx.repo.list_devices("home")[1]
        with pytest.raises(ValueError):
            load_device_story_evidence(
                fx.repo,
                row.network_id,
                row.ieee_address,
                now=REFERENCE_TIME,
                device_row=other,
            )


def test_device_summary_and_dashboard_semantic_parity(tmp_path: Path):
    with deterministic_fixture(tmp_path, "compact") as fx:
        with _frozen_time():
            devices_a = [d.model_dump() for d in _builder(fx).devices()]
            dash_a = _builder(fx).dashboard().model_dump()
            devices_b = [d.model_dump() for d in _builder(fx).devices()]
            dash_b = _builder(fx).dashboard().model_dump()
    assert devices_a == devices_b
    for payload in (dash_a, dash_b):
        payload.pop("generated_at", None)
        snapshot = payload.get("health_snapshot") or {}
        if isinstance(snapshot, dict):
            snapshot.pop("timestamp", None)
    assert dash_a == dash_b


def test_dashboard_and_devices_no_per_device_membership_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    get_network_calls: list[str] = []
    ha_single_calls: list[tuple[str, str]] = []
    incident_ids_single: list[tuple[str, str]] = []
    affected_calls = {"count": 0}

    original_get_network = Repository.get_network
    original_ha = Repository.get_ha_device_enrichment
    original_list_for_device = Repository.list_incidents_for_device
    original_affected = IncidentDiagnosticService.incident_affected_keys
    original_summary = PayloadBuilder._device_summary

    def network_spy(repo, network_id):
        get_network_calls.append(network_id)
        return original_get_network(repo, network_id)

    def ha_spy(repo, network_id, ieee_address):
        ha_single_calls.append((network_id, ieee_address))
        return original_ha(repo, network_id, ieee_address)

    def incidents_spy(repo, network_id, ieee_address):
        incident_ids_single.append((network_id, ieee_address))
        return original_list_for_device(repo, network_id, ieee_address)

    def affected_spy(self, *args, **kwargs):
        affected_calls["count"] += 1
        return original_affected(self, *args, **kwargs)

    def summary_spy(self, row, *, summary_context=None, decision_badge=None):
        before_net = len(get_network_calls)
        before_ha = len(ha_single_calls)
        before_affected = affected_calls["count"]
        result = original_summary(
            self, row, summary_context=summary_context, decision_badge=decision_badge
        )
        if summary_context is not None:
            assert len(get_network_calls) == before_net
            assert len(ha_single_calls) == before_ha
            assert affected_calls["count"] == before_affected
        return result

    monkeypatch.setattr(Repository, "get_network", network_spy)
    monkeypatch.setattr(Repository, "get_ha_device_enrichment", ha_spy)
    monkeypatch.setattr(Repository, "list_incidents_for_device", incidents_spy)
    monkeypatch.setattr(IncidentDiagnosticService, "incident_affected_keys", affected_spy)
    monkeypatch.setattr(PayloadBuilder, "_device_summary", summary_spy)

    with deterministic_fixture(tmp_path / "dash", "beast") as fx:
        with _frozen_time():
            _builder(fx).dashboard()

    with deterministic_fixture(tmp_path / "dev", "beast") as fx:
        get_network_calls.clear()
        ha_single_calls.clear()
        incident_ids_single.clear()
        with _frozen_time():
            _builder(fx).devices()
        assert not incident_ids_single
        assert not ha_single_calls


def test_incident_list_one_bulk_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls = {
        "list_incident_devices": 0,
        "get_device": 0,
        "list_events": 0,
        "bulk_refs": 0,
        "bulk_devices": 0,
        "bulk_events": 0,
        "badge_batch": 0,
    }
    original_list_refs = Repository.list_incident_devices
    original_get_device = Repository.get_device
    original_list_events = Repository.list_events
    original_bulk_refs = Repository.list_incident_devices_for_incidents
    original_bulk_devices = Repository.get_devices_by_keys
    original_bulk_events = Repository.list_events_for_incidents
    original_badges = payload_builder_module.device_decision_badges_for_devices

    def refs_spy(*args, **kwargs):
        calls["list_incident_devices"] += 1
        return original_list_refs(*args, **kwargs)

    def get_device_spy(*args, **kwargs):
        calls["get_device"] += 1
        return original_get_device(*args, **kwargs)

    def list_events_spy(*args, **kwargs):
        calls["list_events"] += 1
        return original_list_events(*args, **kwargs)

    def bulk_refs_spy(*args, **kwargs):
        calls["bulk_refs"] += 1
        return original_bulk_refs(*args, **kwargs)

    def bulk_devices_spy(*args, **kwargs):
        calls["bulk_devices"] += 1
        return original_bulk_devices(*args, **kwargs)

    def bulk_events_spy(*args, **kwargs):
        calls["bulk_events"] += 1
        return original_bulk_events(*args, **kwargs)

    def badges_spy(*args, **kwargs):
        calls["badge_batch"] += 1
        return original_badges(*args, **kwargs)

    with deterministic_fixture(tmp_path, "compact") as fx:
        monkeypatch.setattr(Repository, "list_incident_devices", refs_spy)
        monkeypatch.setattr(Repository, "get_device", get_device_spy)
        monkeypatch.setattr(Repository, "list_events", list_events_spy)
        monkeypatch.setattr(Repository, "list_incident_devices_for_incidents", bulk_refs_spy)
        monkeypatch.setattr(Repository, "get_devices_by_keys", bulk_devices_spy)
        monkeypatch.setattr(Repository, "list_events_for_incidents", bulk_events_spy)
        monkeypatch.setattr(
            payload_builder_module, "device_decision_badges_for_devices", badges_spy
        )
        for key in calls:
            calls[key] = 0
        with _frozen_time():
            incidents = _builder(fx).incidents()
        assert incidents
        assert calls["bulk_refs"] == 1
        assert calls["bulk_devices"] == 1
        assert calls["bulk_events"] == 1
        assert calls["badge_batch"] == 1
        assert calls["list_incident_devices"] == 0
        assert calls["get_device"] == 0
        assert calls["list_events"] == 0


def test_scoped_device_and_incident_detail_events(tmp_path: Path):
    with deterministic_fixture(tmp_path, "beast") as fx:
        network_id, ieee = fx.target_device
        latest_network = fx.repo.list_events(network_id, limit=20)
        latest_global = fx.repo.list_events(limit=100)
        assert all(row["id"] != "older-target-device-event" for row in latest_network)
        assert all(row["id"] != "older-target-incident-event" for row in latest_global)

        scoped_device = fx.repo.list_events_for_device(network_id, ieee, limit=20)
        assert any(row["id"] == "older-target-device-event" for row in scoped_device)
        assert all(row["ieee_address"] == ieee for row in scoped_device)
        assert len(scoped_device) <= 20
        assert scoped_device == sorted(
            scoped_device, key=lambda row: (row["occurred_at"], row["id"]), reverse=True
        )

        scoped_incident = fx.repo.list_events_for_incident(fx.active_incident_id, limit=100)
        assert any(row["id"] == "older-target-incident-event" for row in scoped_incident)
        assert all(row["incident_id"] == fx.active_incident_id for row in scoped_incident)
        assert len(scoped_incident) <= 100

        with _frozen_time():
            detail = _builder(fx).device_detail(network_id, ieee)
            incident = _builder(fx).incident(fx.active_incident_id)
        assert detail is not None
        assert any(event.id == "older-target-device-event" for event in detail.recent_events)
        assert all(event.ieee_address == ieee for event in detail.recent_events)
        assert incident is not None
        assert any(event.id == "older-target-incident-event" for event in incident.timeline)
        assert all(event.incident_id == fx.active_incident_id for event in incident.timeline)


def test_detail_uses_scoped_event_queries_not_global(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls = {"list_events": 0, "device_scoped": 0, "bulk_incident_events": 0}
    original_list = Repository.list_events
    original_device = Repository.list_events_for_device
    original_bulk = Repository.list_events_for_incidents

    def list_spy(*args, **kwargs):
        calls["list_events"] += 1
        return original_list(*args, **kwargs)

    def device_spy(*args, **kwargs):
        calls["device_scoped"] += 1
        return original_device(*args, **kwargs)

    def bulk_spy(*args, **kwargs):
        calls["bulk_incident_events"] += 1
        return original_bulk(*args, **kwargs)

    with deterministic_fixture(tmp_path, "beast") as fx:
        monkeypatch.setattr(Repository, "list_events", list_spy)
        monkeypatch.setattr(Repository, "list_events_for_device", device_spy)
        monkeypatch.setattr(Repository, "list_events_for_incidents", bulk_spy)
        for key in calls:
            calls[key] = 0
        with _frozen_time():
            _builder(fx).device_detail(*fx.target_device)
            assert calls["device_scoped"] == 1
            assert calls["list_events"] == 0
            _builder(fx).incident(fx.active_incident_id)
        assert calls["bulk_incident_events"] == 1
        assert calls["list_events"] == 0


def test_event_tie_ordering(tmp_path: Path):
    repo = _repo(tmp_path)
    _seed_device(repo, "home", "0xT1")
    ts = NOW.isoformat()
    for event_id in ("tie-b", "tie-a", "tie-c"):
        repo.insert_event(
            event_id=event_id,
            network_id="home",
            ieee_address="0xT1",
            event_type="audit",
            severity="healthy",
            title=event_id,
            summary=event_id,
            occurred_at=ts,
        )
    rows = repo.list_events_for_device("home", "0xT1", limit=10)
    assert [row["id"] for row in rows] == ["tie-c", "tie-b", "tie-a"]


def test_report_preview_parity_and_no_devices_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    with deterministic_fixture(tmp_path, "compact") as fx:
        with _frozen_time():
            full = _data(fx).report_preview(request=ReportRequest(scope=ReportScope.full))
            network = _data(fx).report_preview(
                request=ReportRequest(scope=ReportScope.network, network_id="home")
            )
            incident = _data(fx).report_preview(
                request=ReportRequest(scope=ReportScope.incident, incident_id=fx.active_incident_id)
            )
            device = _data(fx).report_preview(
                request=ReportRequest(
                    scope=ReportScope.device, network_id="home", device=fx.target_device[1]
                )
            )
        assert full.scope == ReportScope.full
        assert network.scope == ReportScope.network
        assert incident.scope == ReportScope.incident
        assert device.scope == ReportScope.device
        assert len(full.devices) == len(network.devices) == 20
        assert device.devices and device.devices[0].ieee_address
        assert full.incidents
        assert incident.incidents

        monkeypatch.setattr(
            PayloadBuilder,
            "devices",
            MagicMock(side_effect=AssertionError("reports must not call devices()")),
        )
        with _frozen_time():
            _data(fx).report_preview(request=ReportRequest(scope=ReportScope.full))
            incidents = _builder(fx).incidents()
            detail = _builder(fx).incident(fx.active_incident_id)
        assert incidents
        assert detail is not None


def test_read_only_surfaces_commit_zero(tmp_path: Path):
    with deterministic_fixture(tmp_path, "compact") as fx:
        fx.counter.reset()
        with _frozen_time():
            _builder(fx).dashboard()
            _builder(fx).devices()
            _builder(fx).incidents()
            _builder(fx).incident(fx.active_incident_id)
            _builder(fx).device_detail(*fx.target_device)
        assert fx.counter.stats.commit_count == 0
        assert fx.counter.stats.rollback_count == 0


def test_track_3c_ingestion_baselines_unchanged():
    from performance.expected_baselines import EXPECTED_BASELINES, EXPECTED_PHASE_BASELINES

    assert EXPECTED_BASELINES["payload_ingestion"]["execute_count"] == 36
    assert EXPECTED_BASELINES["payload_ingestion"]["commit_count"] == 3
    assert EXPECTED_BASELINES["payload_ingestion_beast"]["execute_count"] == 62
    assert EXPECTED_BASELINES["availability_ingestion"]["execute_count"] == 46
    assert EXPECTED_BASELINES["availability_ingestion_beast"]["execute_count"] == 75
    assert EXPECTED_BASELINES["inventory_ingestion_compact"]["execute_count"] == 136
    assert EXPECTED_BASELINES["inventory_ingestion_beast"]["execute_count"] == 963
    assert EXPECTED_PHASE_BASELINES["payload_ingestion"]["total_execute_count"] == 36


def test_beast_scaling_reductions():
    from performance.expected_baselines import EXPECTED_BASELINES, TRACK_3C_READ_EXECUTE_TOTALS

    dash = EXPECTED_BASELINES["dashboard_beast"]
    devices = EXPECTED_BASELINES["devices_beast"]
    assert dash["execute_count"] < TRACK_3C_READ_EXECUTE_TOTALS["dashboard_beast"] * 0.55
    assert devices["execute_count"] < TRACK_3C_READ_EXECUTE_TOTALS["devices_beast"] * 0.55
    assert dash["category_counts"].get("read.incident_devices", 0) <= 2
    assert devices["category_counts"].get("read.incident_devices", 0) <= 2
    assert devices["category_counts"].get("read.ha_enrichment", 0) <= 5
    assert devices["category_counts"].get("read.networks", 0) <= 5


def test_devices_cold_cache_evaluates_before_incident_context(tmp_path: Path):
    """Cold health cache must evaluate before Devices builds incident membership."""
    from zigbeelens.config.models import DiagnosticsConfig
    from zigbeelens.diagnostics.coordinator import EvaluationCoordinator
    from zigbeelens.diagnostics.models import HealthFlag
    from zigbeelens.diagnostics.service import HealthDiagnosticService

    db = Database(tmp_path / "cold.sqlite")
    db.migrate()
    repo = Repository(db)
    config = AppConfig(
        mode=ModeConfig(mock=False),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "cold.sqlite")),
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
    repo.sync_networks(config.networks)
    _seed_device(repo, "home", "0xOFF")
    repo.update_device_current_state(
        network_id="home",
        ieee_address="0xOFF",
        availability="offline",
        last_seen=(NOW - timedelta(hours=2)).isoformat(),
        last_payload_at=(NOW - timedelta(hours=2)).isoformat(),
    )
    repo.availability.insert_availability_change("home", "0xOFF", "online", "offline")
    repo.db.conn.execute(
        "UPDATE availability_changes SET changed_at = ? WHERE rowid = last_insert_rowid()",
        ((NOW - timedelta(hours=1)).isoformat(),),
    )
    repo.db.conn.commit()

    health = HealthDiagnosticService(config, repo)
    incidents = IncidentDiagnosticService(config, repo)
    coordinator = EvaluationCoordinator(health, incidents)
    assert not health.has_complete_network_cache(["home"])
    assert incidents.active_incidents() == []

    builder = PayloadBuilder(config, repo, health, incidents, coordinator)
    summaries = builder.devices()
    assert health.has_complete_network_cache(["home"])
    active = incidents.active_incidents()
    assert active
    assert any(
        (ref["network_id"], ref["ieee_address"]) == ("home", "0xOFF")
        for incident in active
        for ref in repo.list_incident_devices(incident["id"])
    )
    match = next(item for item in summaries if item.ieee_address == "0xOFF")
    assert match.incident_affected is True
    cached = health.get_device_health("home", "0xOFF")
    assert cached is not None
    assert HealthFlag.unavailable in cached.flags
    assert match.health.primary.value == cached.primary.value


def test_devices_recovers_when_cache_incomplete_after_failed_eval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from zigbeelens.config.models import DiagnosticsConfig
    from zigbeelens.diagnostics.coordinator import EvaluationCoordinator
    from zigbeelens.diagnostics.service import HealthDiagnosticService

    db = Database(tmp_path / "recover.sqlite")
    db.migrate()
    repo = Repository(db)
    config = AppConfig(
        mode=ModeConfig(mock=False),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "recover.sqlite")),
        diagnostics=DiagnosticsConfig(),
    )
    repo.sync_networks(config.networks)
    _seed_device(repo, "home", "0x1")
    repo.update_device_current_state(
        network_id="home",
        ieee_address="0x1",
        availability="offline",
        last_seen=(NOW - timedelta(hours=2)).isoformat(),
    )
    health = HealthDiagnosticService(config, repo)
    incidents = IncidentDiagnosticService(config, repo)
    coordinator = EvaluationCoordinator(health, incidents)

    calls = {"evaluate_all": 0}
    original = coordinator.evaluate_all

    def flaky(*, now=None):
        calls["evaluate_all"] += 1
        if calls["evaluate_all"] == 1:
            raise RuntimeError("simulated post-commit evaluation failure")
        return original(now=now)

    monkeypatch.setattr(coordinator, "evaluate_all", flaky)
    builder = PayloadBuilder(config, repo, health, incidents, coordinator)
    with pytest.raises(RuntimeError, match="simulated"):
        builder.devices()
    assert not health.has_complete_network_cache(["home"])
    summaries = builder.devices()
    assert health.has_complete_network_cache(["home"])
    assert any(item.ieee_address == "0x1" for item in summaries)


def test_dashboard_reuses_one_active_incident_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    context_calls = {"count": 0}
    original = IncidentDiagnosticService.active_incident_read_context

    def spy(self):
        context_calls["count"] += 1
        return original(self)

    monkeypatch.setattr(IncidentDiagnosticService, "active_incident_read_context", spy)
    with deterministic_fixture(tmp_path, "compact") as fx:
        with _frozen_time():
            _builder(fx).dashboard()
    assert context_calls["count"] == 1
