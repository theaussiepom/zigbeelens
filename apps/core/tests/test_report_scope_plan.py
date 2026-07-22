"""Track 3F Commit 1: ReportScopePlan and incident_networks identity."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from zigbeelens.config.models import NetworkConfig
from zigbeelens.db.connection import Database
from zigbeelens.diagnostics.incidents.models import (
    AffectedDevice,
    IncidentCandidate,
    IncidentType,
)
from zigbeelens.diagnostics.incidents.network_identity import network_ids_from_dedup_key
from zigbeelens.schemas import Confidence, IncidentScope, ReportRequest, ReportScope, Severity
from zigbeelens.services.report_scope import (
    ReportScopeAmbiguityError,
    resolve_report_scope_plan,
)
from zigbeelens.storage.repository import Repository


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "scope.sqlite")
    db.migrate()
    repo = Repository(db)
    repo.sync_networks(
        [
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
            NetworkConfig(id="home2", name="Home 2", base_topic="zigbee2mqtt-home2"),
            NetworkConfig(id="office", name="Office", base_topic="zigbee2mqtt-office"),
        ]
    )
    return repo


def _insert_incident(
    repo: Repository,
    *,
    incident_id: str,
    incident_type: str,
    dedup_key: str,
    network_ids: list[str] | None = None,
    devices: list[tuple[str, str]] | None = None,
) -> None:
    repo.incidents.insert_incident(
        incident_id=incident_id,
        dedup_key=dedup_key,
        incident_type=incident_type,
        lifecycle_state="open",
        severity="incident",
        scope="network" if not devices else "device",
        confidence="high",
        title=f"Title {incident_id}",
        summary=f"Summary {incident_id}",
        explanation="explanation",
        evidence=[],
        counter_evidence=[],
        limitations=[],
        opened_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    if devices:
        repo.replace_incident_devices(
            incident_id,
            [
                AffectedDevice(network_id=nid, ieee_address=ieee)
                for nid, ieee in devices
            ],
        )
    if network_ids is not None:
        repo.replace_incident_networks(incident_id, network_ids)


def test_migration_creates_incident_networks(tmp_path: Path):
    db = Database(tmp_path / "mig.sqlite")
    assert db.migrate() == 14
    tables = {
        row[0]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "incident_networks" in tables
    db.close()


def test_backfill_network_level_no_device_refs(tmp_path: Path):
    """Exact dedup_key join backfills no-ref network incidents without prefix false matches."""
    repo = _repo(tmp_path)
    repo.incidents.insert_incident(
        incident_id="inc-bridge",
        dedup_key="bridge_offline:home",
        incident_type="bridge_offline",
        lifecycle_state="open",
        severity="incident",
        scope="network",
        confidence="high",
        title="Bridge offline",
        summary="Bridge offline",
        explanation="explanation",
        evidence=[],
        counter_evidence=[],
        limitations=[],
        opened_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    # Historical row with no lifecycle write — apply the same exact-join backfill as 011.
    repo.db.conn.execute(
        """
        INSERT OR IGNORE INTO incident_networks (incident_id, network_id)
        SELECT i.id, n.id
        FROM incidents i
        JOIN networks n ON i.dedup_key = i.incident_type || ':' || n.id
        WHERE i.incident_type = 'bridge_offline'
        """
    )
    repo.db.conn.commit()
    assert repo.list_incident_networks("inc-bridge") == ["home"]
    assert "home2" not in repo.list_incident_networks("inc-bridge")


def test_prefix_network_ids_do_not_cross_match():
    known = ("home", "home2", "office")
    assert network_ids_from_dedup_key("bridge_offline:home", known_network_ids=known) == (
        "home",
    )
    assert network_ids_from_dedup_key(
        "bridge_offline:home2", known_network_ids=known
    ) == ("home2",)
    assert network_ids_from_dedup_key(
        "single_device_unavailable:home:0xabc", known_network_ids=known
    ) == ("home",)
    assert network_ids_from_dedup_key(
        "single_device_unavailable:home2:0xabc", known_network_ids=known
    ) == ("home2",)
    assert network_ids_from_dedup_key(
        "multi_network_instability:home,office", known_network_ids=known
    ) == ("home", "office")
    # Unproven segment → empty (do not invent).
    assert (
        network_ids_from_dedup_key(
            "multi_network_instability:home,ghost", known_network_ids=known
        )
        == ()
    )


def test_list_incident_rows_for_network_includes_no_ref(tmp_path: Path):
    repo = _repo(tmp_path)
    _insert_incident(
        repo,
        incident_id="inc-bridge-home",
        incident_type="bridge_offline",
        dedup_key="bridge_offline:home",
        network_ids=["home"],
    )
    _insert_incident(
        repo,
        incident_id="inc-multi",
        incident_type="multi_network_instability",
        dedup_key="multi_network_instability:home,office",
        network_ids=["home", "office"],
    )
    _insert_incident(
        repo,
        incident_id="inc-office-device",
        incident_type="single_device_unavailable",
        dedup_key="single_device_unavailable:office:0xoffice",
        network_ids=["office"],
        devices=[("office", "0xoffice")],
    )
    home_rows = repo.list_incident_rows_for_network_history("home")
    home_ids = {row["id"] for row in home_rows}
    assert home_ids == {"inc-bridge-home", "inc-multi"}
    assert "inc-office-device" not in home_ids


def test_list_incident_rows_for_device_history_composite(tmp_path: Path):
    repo = _repo(tmp_path)
    ieee = "0xsame"
    repo.upsert_device(
        network_id="home",
        ieee_address=ieee,
        friendly_name="Home Device",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )
    repo.upsert_device(
        network_id="office",
        ieee_address=ieee,
        friendly_name="Office Device",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )
    _insert_incident(
        repo,
        incident_id="inc-home",
        incident_type="single_device_unavailable",
        dedup_key=f"single_device_unavailable:home:{ieee}",
        network_ids=["home"],
        devices=[("home", ieee)],
    )
    _insert_incident(
        repo,
        incident_id="inc-office",
        incident_type="single_device_unavailable",
        dedup_key=f"single_device_unavailable:office:{ieee}",
        network_ids=["office"],
        devices=[("office", ieee)],
    )
    rows = repo.list_incident_rows_for_device_history("home", ieee)
    assert [row["id"] for row in rows] == ["inc-home"]


def test_count_topology_snapshots_for_networks_scoped(tmp_path: Path):
    repo = _repo(tmp_path)
    assert repo.count_topology_snapshots_for_networks([]) == 0
    assert repo.count_topology_snapshots_for_networks(["home"]) == 0


def test_empty_bulk_helpers_execute_zero_sql(tmp_path: Path):
    repo = _repo(tmp_path)
    assert repo.get_networks_by_ids([]) == []
    assert repo.list_incident_networks_for_incidents([]) == {}
    assert repo.count_topology_snapshots_for_networks([]) == 0


def test_lifecycle_persists_incident_networks(tmp_path: Path):
    from zigbeelens.config.models import AppConfig, StorageConfig
    from zigbeelens.diagnostics.incidents.lifecycle import IncidentLifecycleManager

    repo = _repo(tmp_path)
    mgr = IncidentLifecycleManager(
        AppConfig(storage=StorageConfig(path=str(tmp_path / "scope.sqlite"))),
        repo,
    )
    candidate = IncidentCandidate(
        dedup_key="",
        incident_type=IncidentType.bridge_offline,
        scope=IncidentScope.network,
        severity=Severity.incident,
        confidence=Confidence.high,
        title="Bridge offline",
        summary="Bridge offline",
        explanation="explanation",
        network_ids=["home"],
        affected_devices=[],
    )
    events = mgr.sync([candidate], now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert "incident_opened" in events
    row = repo.get_incident_by_dedup_key(candidate.dedup_key)
    assert row is not None
    assert repo.list_incident_networks(row["id"]) == ["home"]


def test_resolve_full_and_network_scope(tmp_path: Path):
    repo = _repo(tmp_path)
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    full = resolve_report_scope_plan(
        ReportRequest(scope=ReportScope.full),
        repo=repo,
        reference_now=now,
        include_timeline=True,
    )
    assert full.require_full_estate_history is True
    assert set(full.network_ids) == {"home", "home2", "office"}

    network = resolve_report_scope_plan(
        ReportRequest(scope=ReportScope.network, network_id="home"),
        repo=repo,
        reference_now=now,
        include_timeline=False,
    )
    assert network.network_ids == ("home",)
    assert network.include_timeline is False
    assert network.require_full_estate_history is False


def test_resolve_device_scope_narrow_lookup_and_ambiguity(tmp_path: Path):
    repo = _repo(tmp_path)
    ieee = "0xshared"
    for network_id in ("home", "office"):
        repo.upsert_device(
            network_id=network_id,
            ieee_address=ieee,
            friendly_name=f"Dev {network_id}",
            device_type="EndDevice",
            power_source="Battery",
            interview_state="successful",
        )
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    with pytest.raises(ReportScopeAmbiguityError) as exc:
        resolve_report_scope_plan(
            ReportRequest(scope=ReportScope.device, device=ieee),
            repo=repo,
            reference_now=now,
            include_timeline=True,
        )
    assert set(exc.value.network_ids) == {"home", "office"}

    plan = resolve_report_scope_plan(
        ReportRequest(scope=ReportScope.device, device=ieee, network_id="home"),
        repo=repo,
        reference_now=now,
        include_timeline=True,
    )
    assert plan.device_keys == (("home", ieee),)
    assert plan.network_ids == ("home",)


def test_resolve_incident_scope_uses_incident_networks(tmp_path: Path):
    repo = _repo(tmp_path)
    _insert_incident(
        repo,
        incident_id="inc-multi",
        incident_type="multi_network_instability",
        dedup_key="multi_network_instability:home,office",
        network_ids=["home", "office"],
    )
    plan = resolve_report_scope_plan(
        ReportRequest(scope=ReportScope.incident, incident_id="inc-multi"),
        repo=repo,
        reference_now=datetime(2026, 6, 1, tzinfo=timezone.utc),
        include_timeline=True,
    )
    assert plan.incident_ids == ("inc-multi",)
    assert set(plan.network_ids) == {"home", "office"}
    assert plan.require_device_details is True
