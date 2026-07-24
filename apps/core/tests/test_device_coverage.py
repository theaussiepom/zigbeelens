"""Tests for per-device evidence coverage evaluation (Phase 4C-1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.device_coverage import (
    DeviceCoverageEvidence,
    build_device_coverage,
    device_coverage_for_device,
    load_device_coverage_evidence,
)
from zigbeelens.decisions.types import CoverageDimension, CoverageLabelCode, CoverageState
from zigbeelens.enrichment.ha import MatchResult
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.device_compare import MAX_SNAPSHOT_HISTORY
from zigbeelens.topology.parser import parse_networkmap_payload

NOW = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)

_UNSET = object()

EXPECTED_BATTERY_DEVICE_DIMENSIONS = (
    CoverageDimension.availability,
    CoverageDimension.last_seen,
    CoverageDimension.last_payload,
    CoverageDimension.battery,
    CoverageDimension.linkquality,
    CoverageDimension.historical_snapshots,
    CoverageDimension.ha_enrichment,
)

EXPECTED_MAINS_DEVICE_DIMENSIONS = (
    CoverageDimension.availability,
    CoverageDimension.last_seen,
    CoverageDimension.last_payload,
    CoverageDimension.linkquality,
    CoverageDimension.historical_snapshots,
    CoverageDimension.ha_enrichment,
)


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
    last_seen: datetime | str | None = _UNSET,
    last_payload_at: datetime | str | None = _UNSET,
    device_type: str = "EndDevice",
    power_source: str = "Battery",
    battery: int | None = None,
) -> None:
    repo.upsert_device(
        network_id="home",
        ieee_address=ieee,
        friendly_name=f"Device {ieee}",
        device_type=device_type,
        power_source=power_source,
        interview_state="successful",
    )
    if last_seen is _UNSET:
        last_seen_value = NOW.isoformat()
    elif last_seen is None:
        last_seen_value = None
    elif isinstance(last_seen, str):
        last_seen_value = last_seen
    else:
        last_seen_value = last_seen.isoformat()
    if last_payload_at is _UNSET:
        last_payload_value = NOW.isoformat()
    elif last_payload_at is None:
        last_payload_value = None
    elif isinstance(last_payload_at, str):
        last_payload_value = last_payload_at
    else:
        last_payload_value = last_payload_at.isoformat()
    repo.update_device_current_state(
        network_id="home",
        ieee_address=ieee,
        availability=availability,
        last_seen=last_seen_value,
        last_payload_at=last_payload_value,
        battery=battery,
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


def _store_topology_snapshot(
    repo: Repository,
    snapshot_id: str,
    *,
    captured_at: datetime,
    node_ieees: list[str],
    status: str = "complete",
) -> None:
    repo.create_topology_snapshot(
        snapshot_id=snapshot_id,
        network_id="home",
        requested_by="test",
        status="pending" if status != "complete" else "pending",
        warning_acknowledged=True,
    )
    if status == "complete":
        parsed = parse_networkmap_payload(
            {
                "nodes": {ieee: {"type": "EndDevice"} for ieee in node_ieees},
                "links": [],
            }
        )
        repo.store_topology_parsed(snapshot_id, "home", parsed, status="complete")
    repo.db.conn.execute(
        "UPDATE topology_snapshots SET captured_at = ? WHERE snapshot_id = ?",
        (captured_at.isoformat(), snapshot_id),
    )
    repo.db.conn.commit()


def _store_snapshot(repo: Repository, snapshot_id: str, *, captured_at: datetime) -> None:
    _store_topology_snapshot(
        repo,
        snapshot_id,
        captured_at=captured_at,
        node_ieees=["0x01", "0x02", "0x03"],
    )


def _enable_availability_tracking(repo: Repository, ieee: str) -> None:
    repo.availability.insert_availability_change("home", ieee, "unknown", "online")
    repo.db.conn.execute(
        "UPDATE availability_changes SET changed_at = ? WHERE rowid = last_insert_rowid()",
        ((NOW - timedelta(days=3)).isoformat(),),
    )
    repo.db.conn.commit()


def _enable_network_availability_tracking(repo: Repository) -> None:
    _upsert_device(repo, "0x99", availability="online")
    _enable_availability_tracking(repo, "0x99")


def _availability_item(coverage: list) -> object:
    items = [item for item in coverage if item.dimension is CoverageDimension.availability]
    assert len(items) == 1
    return items[0]


def _topology_item(coverage: list) -> object:
    items = [
        item for item in coverage if item.dimension is CoverageDimension.historical_snapshots
    ]
    assert len(items) == 1
    return items[0]


def _ha_item(coverage: list) -> object:
    items = [item for item in coverage if item.dimension is CoverageDimension.ha_enrichment]
    assert len(items) == 1
    return items[0]


def _apply_ha_device_enrichment(
    repo: Repository,
    ieee: str,
    *,
    area_id: str | None = None,
    area_name: str | None = None,
) -> None:
    repo.replace_ha_device_enrichment(
        [
            MatchResult(
                network_id="home",
                ieee_address=ieee,
                ha_device_id=f"ha-{ieee}",
                ha_device_name=f"Device {ieee}",
                area_id=area_id,
                area_name=area_name,
                entity_id=f"light.{ieee.replace('0x', '')}",
                match_confidence="high",
            )
        ]
    )
    repo.update_ha_enrichment_status(
        enabled=True,
        matched_devices=1,
        source="test",
    )


def _insert_ha_enrichment_row(
    repo: Repository,
    ieee: str,
    *,
    area_id: str | None,
    area_name: str | None,
) -> None:
    repo.db.conn.execute(
        """
        INSERT INTO ha_device_enrichment (
            network_id, ieee_address, ha_device_id, ha_device_name,
            area_id, area_name, entity_id, match_confidence, updated_at
        ) VALUES ('home', ?, 'ha-1', 'Device', ?, ?, 'light.test', 'high', ?)
        """,
        (ieee, area_id, area_name, NOW.isoformat()),
    )
    repo.db.conn.commit()


def _device_coverage_with_ha_setup(
    repo: Repository,
    ieee: str = "0x03",
) -> list:
    _upsert_device(repo, ieee)
    _enable_network_availability_tracking(repo)
    _store_snapshot(repo, "snap-latest", captured_at=NOW)
    coverage = device_coverage_for_device(repo, "home", ieee)
    assert coverage is not None
    return coverage


def _assert_unique_dimensions(coverage: list) -> None:
    dimensions = [item.dimension for item in coverage]
    assert len(set(dimensions)) == len(coverage)


def _assert_dimension_order(coverage: list, expected: tuple[CoverageDimension, ...]) -> None:
    assert [item.dimension for item in coverage] == list(expected)


def test_unknown_device_returns_none(tmp_path: Path):
    repo = _repo(tmp_path)
    assert device_coverage_for_device(repo, "home", "0xmissing") is None


def test_empty_ieee_returns_none(tmp_path: Path):
    repo = _repo(tmp_path)
    assert device_coverage_for_device(repo, "home", "   ") is None


def test_ieee_normalisation_is_canonical(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _enable_network_availability_tracking(repo)
    _store_snapshot(repo, "snap-latest", captured_at=NOW)

    evidence = load_device_coverage_evidence(repo, "home", "0X03")
    assert evidence is not None
    assert evidence.device_ieee == "0x03"


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
    availability = _availability_item(coverage)
    assert availability.label_code is CoverageLabelCode.availability_tracking_off


def test_explicit_online_without_transition_history_is_available(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", availability="online")
    _enable_network_availability_tracking(repo)
    _store_snapshot(repo, "snap-latest", captured_at=NOW)

    coverage = device_coverage_for_device(repo, "home", "0x03")
    assert coverage is not None
    availability = _availability_item(coverage)
    assert availability.label_code is CoverageLabelCode.availability_available


def test_explicit_offline_is_available(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", availability="offline")
    _enable_network_availability_tracking(repo)
    _store_snapshot(repo, "snap-latest", captured_at=NOW)

    coverage = device_coverage_for_device(repo, "home", "0x03")
    assert coverage is not None
    availability = _availability_item(coverage)
    assert availability.label_code is CoverageLabelCode.availability_available


def test_unknown_availability_without_device_history_is_building(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(
        repo,
        "0x03",
        availability="unknown",
        last_seen=None,
        last_payload_at=None,
    )
    _enable_network_availability_tracking(repo)
    _store_snapshot(repo, "snap-latest", captured_at=NOW)

    coverage = device_coverage_for_device(repo, "home", "0x03")
    assert coverage is not None
    availability = _availability_item(coverage)
    assert availability.label_code is CoverageLabelCode.availability_history_building


def test_unknown_availability_with_device_history_is_unknown(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", availability="unknown")
    _enable_network_availability_tracking(repo)
    _enable_availability_tracking(repo, "0x03")
    _store_snapshot(repo, "snap-latest", captured_at=NOW)

    coverage = device_coverage_for_device(repo, "home", "0x03")
    assert coverage is not None
    availability = _availability_item(coverage)
    assert availability.label_code is CoverageLabelCode.availability_status_unknown


def test_last_seen_and_payload_available(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _enable_network_availability_tracking(repo)
    _store_snapshot(repo, "snap-latest", captured_at=NOW)

    coverage = device_coverage_for_device(repo, "home", "0x03")
    assert coverage is not None
    labels = {item.label_code for item in coverage}
    assert CoverageLabelCode.last_seen_available in labels
    assert CoverageLabelCode.last_payload_available in labels


def test_missing_last_seen_and_payload_are_unknown(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(
        repo,
        "0x03",
        availability="online",
        last_seen=None,
        last_payload_at=None,
    )
    _enable_network_availability_tracking(repo)

    coverage = device_coverage_for_device(repo, "home", "0x03")
    assert coverage is not None
    labels = {item.label_code for item in coverage}
    assert CoverageLabelCode.last_seen_unknown in labels
    assert CoverageLabelCode.last_payload_unknown in labels


def test_malformed_timestamps_are_unknown(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    repo.update_device_current_state(
        network_id="home",
        ieee_address="0x03",
        availability="online",
        last_seen="not-a-timestamp",
        last_payload_at="also-invalid",
    )
    _enable_network_availability_tracking(repo)

    coverage = device_coverage_for_device(repo, "home", "0x03")
    assert coverage is not None
    labels = {item.label_code for item in coverage}
    assert CoverageLabelCode.last_seen_unknown in labels
    assert CoverageLabelCode.last_payload_unknown in labels


def test_sparse_battery_and_lqi_history(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _enable_network_availability_tracking(repo)
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
    _enable_network_availability_tracking(repo)
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


def test_mains_device_without_battery_evidence_omits_battery_coverage(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(
        repo,
        "0x03",
        device_type="Router",
        power_source="Mains",
    )
    _enable_network_availability_tracking(repo)
    _store_snapshot(repo, "snap-latest", captured_at=NOW)

    coverage = device_coverage_for_device(repo, "home", "0x03")
    assert coverage is not None
    battery_items = [item for item in coverage if item.dimension is CoverageDimension.battery]
    assert battery_items == []


def test_mains_device_with_current_battery_value_is_applicable(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(
        repo,
        "0x03",
        device_type="Router",
        power_source="Mains",
        battery=75,
    )
    _enable_network_availability_tracking(repo)
    _store_snapshot(repo, "snap-latest", captured_at=NOW)

    coverage = device_coverage_for_device(repo, "home", "0x03")
    assert coverage is not None
    battery_items = [item for item in coverage if item.dimension is CoverageDimension.battery]
    assert len(battery_items) == 1
    assert battery_items[0].label_code is CoverageLabelCode.battery_history_sparse


def test_mains_device_with_historical_battery_samples_is_applicable(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(
        repo,
        "0x03",
        device_type="Router",
        power_source="Mains",
    )
    _enable_network_availability_tracking(repo)
    _insert_payload_snapshot(repo, "0x03", captured_at=NOW - timedelta(hours=1))
    _store_snapshot(repo, "snap-latest", captured_at=NOW)

    coverage = device_coverage_for_device(repo, "home", "0x03")
    assert coverage is not None
    battery_items = [item for item in coverage if item.dimension is CoverageDimension.battery]
    assert len(battery_items) == 1


def test_lqi_zero_counts_as_recorded_sample(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _enable_network_availability_tracking(repo)
    _insert_payload_snapshot(
        repo,
        "0x03",
        captured_at=NOW - timedelta(hours=1),
        linkquality=0,
    )
    _store_snapshot(repo, "snap-latest", captured_at=NOW)

    evidence = load_device_coverage_evidence(repo, "home", "0x03")
    assert evidence is not None
    assert evidence.lqi_sample_count == 1


@pytest.mark.parametrize(
    ("observed", "window", "label", "state"),
    [
        (0, 0, CoverageLabelCode.topology_history_not_observed, CoverageState.not_observed),
        (0, 10, CoverageLabelCode.topology_history_not_observed, CoverageState.not_observed),
        (2, 10, CoverageLabelCode.topology_history_sparse, CoverageState.sparse),
        (2, 2, CoverageLabelCode.topology_history_available, CoverageState.available),
        (10, 10, CoverageLabelCode.topology_history_available, CoverageState.available),
    ],
)
def test_topology_history_builder_states(observed, window, label, state):
    evidence = DeviceCoverageEvidence(
        network_id="home",
        device_ieee="0x03",
        topology_observed_snapshot_count=observed,
        topology_snapshot_window_count=window,
    )
    topology = _topology_item(build_device_coverage(evidence))
    assert topology.label_code is label
    assert topology.state is state
    assert topology.params == {
        "observed_snapshot_count": observed,
        "snapshot_window_count": window,
    }


def test_topology_history_device_present_in_all_snapshots(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _enable_network_availability_tracking(repo)
    _store_topology_snapshot(
        repo,
        "snap-new",
        captured_at=NOW,
        node_ieees=["0x01", "0x03"],
    )
    _store_topology_snapshot(
        repo,
        "snap-old",
        captured_at=NOW - timedelta(days=1),
        node_ieees=["0x01", "0x03"],
    )

    topology = _topology_item(device_coverage_for_device(repo, "home", "0x03"))
    assert topology.label_code is CoverageLabelCode.topology_history_available
    assert topology.params == {
        "observed_snapshot_count": 2,
        "snapshot_window_count": 2,
    }


def test_topology_history_device_absent_from_snapshots(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _enable_network_availability_tracking(repo)
    _store_topology_snapshot(
        repo,
        "snap-new",
        captured_at=NOW,
        node_ieees=["0x01", "0x02"],
    )
    _store_topology_snapshot(
        repo,
        "snap-old",
        captured_at=NOW - timedelta(days=1),
        node_ieees=["0x01", "0x02"],
    )

    topology = _topology_item(device_coverage_for_device(repo, "home", "0x03"))
    assert topology.label_code is CoverageLabelCode.topology_history_not_observed
    assert topology.params == {
        "observed_snapshot_count": 0,
        "snapshot_window_count": 2,
    }


def test_topology_history_partial_device_presence(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _enable_network_availability_tracking(repo)
    for index in range(10):
        _store_topology_snapshot(
            repo,
            f"snap-{index}",
            captured_at=NOW - timedelta(hours=index),
            node_ieees=["0x01", "0x03"] if index < 2 else ["0x01", "0x02"],
        )

    topology = _topology_item(device_coverage_for_device(repo, "home", "0x03"))
    assert topology.label_code is CoverageLabelCode.topology_history_sparse
    assert topology.params == {
        "observed_snapshot_count": 2,
        "snapshot_window_count": 10,
    }


def test_topology_window_is_bounded_to_latest_complete_snapshots(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _enable_network_availability_tracking(repo)
    for index in range(MAX_SNAPSHOT_HISTORY + 1):
        _store_topology_snapshot(
            repo,
            f"snap-{index}",
            captured_at=NOW - timedelta(hours=index),
            node_ieees=["0x01", "0x03"],
        )

    evidence = load_device_coverage_evidence(repo, "home", "0x03")
    assert evidence is not None
    assert evidence.topology_observed_snapshot_count == MAX_SNAPSHOT_HISTORY
    assert evidence.topology_snapshot_window_count == MAX_SNAPSHOT_HISTORY


def test_pending_topology_snapshots_do_not_enter_window(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _enable_network_availability_tracking(repo)
    _store_topology_snapshot(
        repo,
        "snap-complete",
        captured_at=NOW,
        node_ieees=["0x01", "0x03"],
    )
    _store_topology_snapshot(
        repo,
        "snap-pending",
        captured_at=NOW - timedelta(hours=1),
        node_ieees=["0x01", "0x03"],
        status="pending",
    )

    evidence = load_device_coverage_evidence(repo, "home", "0x03")
    assert evidence is not None
    assert evidence.topology_snapshot_window_count == 1
    assert evidence.topology_observed_snapshot_count == 1


def test_topology_node_ieee_comparison_is_case_insensitive(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _enable_network_availability_tracking(repo)
    _store_topology_snapshot(
        repo,
        "snap-case",
        captured_at=NOW,
        node_ieees=["0X03"],
    )

    evidence = load_device_coverage_evidence(repo, "home", "0x03")
    assert evidence is not None
    assert evidence.topology_observed_snapshot_count == 1


def test_ha_area_linked_area_name_only(tmp_path: Path):
    repo = _repo(tmp_path)
    _device_coverage_with_ha_setup(repo)
    _apply_ha_device_enrichment(repo, "0x03", area_name="Hall")

    ha = _ha_item(device_coverage_for_device(repo, "home", "0x03"))
    assert ha.label_code is CoverageLabelCode.ha_area_linked
    assert ha.state is CoverageState.available
    assert ha.params == {"area_name": "Hall"}


def test_ha_area_linked_area_id_only(tmp_path: Path):
    repo = _repo(tmp_path)
    _device_coverage_with_ha_setup(repo)
    _apply_ha_device_enrichment(repo, "0x03", area_id="hall")

    ha = _ha_item(device_coverage_for_device(repo, "home", "0x03"))
    assert ha.label_code is CoverageLabelCode.ha_area_linked
    assert ha.state is CoverageState.available
    assert ha.params == {"area_id": "hall"}
    assert "area_name" not in ha.params


def test_ha_area_linked_trimmed_area_id(tmp_path: Path):
    repo = _repo(tmp_path)
    _device_coverage_with_ha_setup(repo)
    _insert_ha_enrichment_row(repo, "0x03", area_id="  hall  ", area_name=" ")

    ha = _ha_item(device_coverage_for_device(repo, "home", "0x03"))
    assert ha.label_code is CoverageLabelCode.ha_area_linked
    assert ha.params == {"area_id": "hall"}


def test_ha_area_linked_both_area_id_and_area_name(tmp_path: Path):
    repo = _repo(tmp_path)
    _device_coverage_with_ha_setup(repo)
    _apply_ha_device_enrichment(repo, "0x03", area_id="hall", area_name="Hall")

    ha = _ha_item(device_coverage_for_device(repo, "home", "0x03"))
    assert ha.label_code is CoverageLabelCode.ha_area_linked
    assert ha.params == {"area_id": "hall", "area_name": "Hall"}


def test_ha_area_blank_values_are_not_linked(tmp_path: Path):
    repo = _repo(tmp_path)
    _device_coverage_with_ha_setup(repo)
    _insert_ha_enrichment_row(repo, "0x03", area_id="   ", area_name="")

    ha = _ha_item(device_coverage_for_device(repo, "home", "0x03"))
    assert ha.label_code is CoverageLabelCode.ha_areas_not_linked
    assert ha.state is CoverageState.not_configured
    assert ha.params == {}


def test_ha_area_not_linked_when_device_missing_area(tmp_path: Path):
    repo = _repo(tmp_path)
    _device_coverage_with_ha_setup(repo, ieee="0x03")
    _apply_ha_device_enrichment(repo, "0x04", area_name="Kitchen")

    ha = _ha_item(device_coverage_for_device(repo, "home", "0x03"))
    assert ha.label_code is CoverageLabelCode.ha_areas_not_linked


def test_ha_area_not_linked_on_unenriched_network(tmp_path: Path):
    repo = _repo(tmp_path)
    _device_coverage_with_ha_setup(repo)

    ha = _ha_item(device_coverage_for_device(repo, "home", "0x03"))
    assert ha.label_code is CoverageLabelCode.ha_areas_not_linked


def test_device_coverage_order_is_deterministic():
    evidence = DeviceCoverageEvidence(
        network_id="home",
        device_ieee="0x03",
        availability_tracking_enabled=True,
        current_availability="online",
        battery_history_applicable=True,
        battery_sample_count=1,
        lqi_sample_count=1,
        topology_observed_snapshot_count=2,
        topology_snapshot_window_count=2,
        last_seen=NOW,
        last_payload_at=NOW,
    )
    first = build_device_coverage(evidence)
    second = build_device_coverage(evidence)
    assert first == second


def test_battery_device_dimension_order_and_no_duplicates():
    evidence = DeviceCoverageEvidence(
        network_id="home",
        device_ieee="0x03",
        availability_tracking_enabled=True,
        current_availability="online",
        battery_history_applicable=True,
        battery_sample_count=1,
        lqi_sample_count=1,
        topology_observed_snapshot_count=2,
        topology_snapshot_window_count=2,
        last_seen=NOW,
        last_payload_at=NOW,
    )
    coverage = build_device_coverage(evidence)
    _assert_unique_dimensions(coverage)
    _assert_dimension_order(coverage, EXPECTED_BATTERY_DEVICE_DIMENSIONS)
    assert len(coverage) == 7


def test_mains_device_dimension_order_and_no_duplicates(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(
        repo,
        "0x03",
        device_type="Router",
        power_source="Mains",
    )
    _enable_network_availability_tracking(repo)
    _store_snapshot(repo, "snap-latest", captured_at=NOW)

    coverage = device_coverage_for_device(repo, "home", "0x03")
    assert coverage is not None
    _assert_unique_dimensions(coverage)
    _assert_dimension_order(coverage, EXPECTED_MAINS_DEVICE_DIMENSIONS)
    assert len(coverage) == 6


def test_build_device_coverage_from_loaded_evidence(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _enable_network_availability_tracking(repo)
    _store_snapshot(repo, "snap-latest", captured_at=NOW)

    evidence = load_device_coverage_evidence(repo, "home", "0x03")
    assert evidence is not None
    loaded = build_device_coverage(evidence)
    direct = device_coverage_for_device(repo, "home", "0x03")
    assert loaded == direct
