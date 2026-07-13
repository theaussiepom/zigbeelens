"""Tests for per-device evidence coverage evaluation (Phase 4C-1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.device_coverage import (
    DeviceCoverageEvidence,
    build_device_coverage,
    device_coverage_for_device,
    load_device_coverage_evidence,
)
from zigbeelens.decisions.types import CoverageDimension, CoverageLabelCode, CoverageState
from zigbeelens.enrichment.ha import apply_ha_enrichment
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.parser import parse_networkmap_payload

NOW = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "device-coverage.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "device-coverage.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    return repo


def _upsert_device(
    repo: Repository,
    ieee: str,
    *,
    availability: str = "online",
    last_seen: datetime | None = None,
    last_payload_at: datetime | None = None,
) -> None:
    repo.upsert_device(
        network_id="home",
        ieee_address=ieee,
        friendly_name=f"Device {ieee}",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )
    repo.update_device_current_state(
        network_id="home",
        ieee_address=ieee,
        availability=availability,
        last_seen=(last_seen or NOW).isoformat(),
        last_payload_at=(last_payload_at or NOW).isoformat(),
    )


def _insert_payload_snapshot(
    repo: Repository,
    ieee: str,
    *,
    captured_at: datetime,
    battery: int | None = 80,
    linkquality: int | None = 120,
) -> None:
    repo.db.conn.execute(
        """
        INSERT INTO device_snapshots (
            network_id, ieee_address, availability, last_seen, last_payload_at,
            linkquality, battery, payload_json, captured_at
        ) VALUES ('home', ?, 'online', ?, ?, ?, ?, '{}', ?)
        """,
        (
            ieee,
            captured_at.isoformat(),
            captured_at.isoformat(),
            linkquality,
            battery,
            captured_at.isoformat(),
        ),
    )
    repo.db.conn.commit()


def _store_snapshot(repo: Repository, snapshot_id: str, *, captured_at: datetime) -> None:
    repo.create_topology_snapshot(
        snapshot_id=snapshot_id,
        network_id="home",
        requested_by="test",
        status="pending",
        warning_acknowledged=True,
    )
    parsed = parse_networkmap_payload(
        {
            "nodes": {
                "0x01": {"type": "Coordinator"},
                "0x02": {"type": "Router"},
                "0x03": {"type": "EndDevice"},
            },
            "links": [{"source": "0x02", "target": "0x03", "linkquality": 120}],
        }
    )
    repo.store_topology_parsed(snapshot_id, "home", parsed, status="complete")
    repo.db.conn.execute(
        "UPDATE topology_snapshots SET captured_at = ? WHERE snapshot_id = ?",
        (captured_at.isoformat(), snapshot_id),
    )
    repo.db.conn.commit()


def _enable_availability_tracking(repo: Repository, ieee: str) -> None:
    repo.availability.insert_availability_change("home", ieee, "unknown", "online")
    repo.db.conn.execute(
        "UPDATE availability_changes SET changed_at = ? WHERE rowid = last_insert_rowid()",
        ((NOW - timedelta(days=3)).isoformat(),),
    )
    repo.db.conn.commit()


def test_unknown_device_returns_none(tmp_path: Path):
    repo = _repo(tmp_path)
    assert device_coverage_for_device(repo, "home", "0xmissing") is None


def test_availability_tracking_off_coverage(tmp_path: Path):
    repo = _repo(tmp_path)
    repo.upsert_device(
        network_id="home",
        ieee_address="0x03",
        friendly_name="Device 0x03",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )
    repo.update_device_current_state(
        network_id="home",
        ieee_address="0x03",
        availability="unknown",
        last_seen=None,
        last_payload_at=None,
    )

    coverage = device_coverage_for_device(repo, "home", "0x03")
    assert coverage is not None
    assert any(
        item.label_code == CoverageLabelCode.availability_tracking_off for item in coverage
    )


def test_availability_history_building_coverage(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _upsert_device(repo, "0x04")
    _enable_availability_tracking(repo, "0x03")
    _store_snapshot(repo, "snap-latest", captured_at=NOW)

    coverage = device_coverage_for_device(repo, "home", "0x04")
    assert coverage is not None
    assert any(
        item.label_code == CoverageLabelCode.availability_history_building for item in coverage
    )


def test_last_seen_and_payload_available(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _enable_availability_tracking(repo, "0x03")
    _store_snapshot(repo, "snap-latest", captured_at=NOW)

    coverage = device_coverage_for_device(repo, "home", "0x03")
    assert coverage is not None
    labels = {item.label_code for item in coverage}
    assert CoverageLabelCode.last_seen_available in labels
    assert CoverageLabelCode.last_payload_available in labels


def test_sparse_battery_and_lqi_history(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _enable_availability_tracking(repo, "0x03")
    _insert_payload_snapshot(repo, "0x03", captured_at=NOW - timedelta(hours=2))
    _store_snapshot(repo, "snap-latest", captured_at=NOW)

    coverage = device_coverage_for_device(repo, "home", "0x03")
    assert coverage is not None
    labels = {item.label_code for item in coverage}
    assert CoverageLabelCode.battery_history_sparse in labels
    assert CoverageLabelCode.lqi_history_sparse in labels


def test_available_battery_and_lqi_history(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _enable_availability_tracking(repo, "0x03")
    for offset in range(3):
        _insert_payload_snapshot(
            repo,
            "0x03",
            captured_at=NOW - timedelta(hours=offset + 1),
        )
    _store_snapshot(repo, "snap-latest", captured_at=NOW)

    coverage = device_coverage_for_device(repo, "home", "0x03")
    assert coverage is not None
    labels = {item.label_code for item in coverage}
    assert CoverageLabelCode.battery_history_available in labels
    assert CoverageLabelCode.lqi_history_available in labels


def test_topology_history_reports_snapshot_count(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _enable_availability_tracking(repo, "0x03")
    _store_snapshot(repo, "snap-latest", captured_at=NOW)
    _store_snapshot(repo, "snap-old", captured_at=NOW - timedelta(days=1))

    coverage = device_coverage_for_device(repo, "home", "0x03")
    assert coverage is not None
    topology = next(
        item for item in coverage if item.label_code == CoverageLabelCode.topology_history_available
    )
    assert topology.params["snapshot_count"] == 2
    assert topology.params["max_snapshots"] == 10


def test_ha_area_linked_and_not_linked(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _enable_availability_tracking(repo, "0x03")
    _store_snapshot(repo, "snap-latest", captured_at=NOW)
    apply_ha_enrichment(
        repo,
        {
            "devices": [
                {
                    "network_id": "home",
                    "ieee_address": "0x03",
                    "ha_device_name": "Hall lamp",
                    "area_name": "Hall",
                    "entity_id": "light.hall",
                }
            ]
        },
    )

    linked = device_coverage_for_device(repo, "home", "0x03")
    assert linked is not None
    assert any(item.label_code == CoverageLabelCode.ha_area_linked for item in linked)

    _upsert_device(repo, "0x04")
    _enable_availability_tracking(repo, "0x04")
    not_linked = device_coverage_for_device(repo, "home", "0x04")
    assert not_linked is not None
    assert any(item.label_code == CoverageLabelCode.ha_areas_not_linked for item in not_linked)


def test_device_coverage_order_is_deterministic():
    evidence = DeviceCoverageEvidence(
        network_id="home",
        device_ieee="0x03",
        availability_tracking_enabled=False,
        battery_sample_count=1,
        lqi_sample_count=1,
        topology_snapshot_count=2,
        network_has_usable_ha_areas=True,
    )
    first = build_device_coverage(evidence)
    second = build_device_coverage(evidence)
    assert first == second


def test_build_device_coverage_from_loaded_evidence(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _enable_availability_tracking(repo, "0x03")
    _store_snapshot(repo, "snap-latest", captured_at=NOW)

    evidence = load_device_coverage_evidence(repo, "home", "0x03")
    assert evidence is not None
    coverage = build_device_coverage(evidence)
    assert len(coverage) >= 5
