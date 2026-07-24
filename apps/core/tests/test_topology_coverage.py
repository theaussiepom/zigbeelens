"""Tests for network topology coverage composition (Phase 3E)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.availability_tracking import availability_tracking_enabled_now
from zigbeelens.decisions.topology_coverage import build_network_topology_coverage
from zigbeelens.decisions.topology_facts import TopologyFactCode
from zigbeelens.decisions.types import CoverageDimension, CoverageLabelCode, CoverageState, EvidenceFact
from zigbeelens.enrichment.ha import MatchResult
from zigbeelens.storage.repository import Repository

NOW = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "topology-coverage.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "topology-coverage.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    return repo


def _upsert_device(
    repo: Repository,
    ieee: str,
    *,
    availability: str = "unknown",
) -> None:
    repo.upsert_device(
        network_id="home",
        ieee_address=ieee,
        friendly_name=f"Device {ieee}",
        device_type="Router",
        power_source="Mains",
        interview_state="successful",
    )
    repo.update_device_current_state(
        network_id="home",
        ieee_address=ieee,
        availability=availability,
    )


def _store_ha_enrichment(
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
                ha_device_name="Hall lamp",
                area_id=area_id,
                area_name=area_name,
                entity_id="light.hall",
                match_confidence="high",
            )
        ]
    )
    repo.update_ha_enrichment_status(
        enabled=True,
        matched_devices=1,
        source="test",
    )


def _insert_availability_change(
    repo: Repository,
    ieee: str,
    to_state: str,
    changed_at: datetime,
    from_state: str = "unknown",
) -> None:
    repo.availability.insert_availability_change(
        "home",
        ieee,
        from_state,
        to_state,
    )
    repo.db.conn.execute(
        "UPDATE availability_changes SET changed_at = ? WHERE rowid = last_insert_rowid()",
        (changed_at.isoformat(),),
    )
    repo.db.conn.commit()


def _fact(code: TopologyFactCode | str, **params) -> EvidenceFact:
    return EvidenceFact(code=str(code), params=params)


def _build_coverage(**kwargs):
    defaults = dict(
        network_facts=[],
        tracking_enabled_now=True,
        has_known_devices=True,
        has_usable_ha_area_assignments=True,
    )
    defaults.update(kwargs)
    return build_network_topology_coverage(**defaults)


def test_availability_tracking_off_when_no_usable_signals(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0xa1", availability="unknown")
    _upsert_device(repo, "0xa2", availability="unknown")
    assert availability_tracking_enabled_now(repo, "home") is False
    items = _build_coverage(tracking_enabled_now=False)
    assert len(items) == 1
    item = items[0]
    assert item.label_code == CoverageLabelCode.availability_tracking_off
    assert item.dimension == CoverageDimension.availability
    assert item.state == CoverageState.off


def test_availability_tracking_on_with_explicit_online_state(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0xa1", availability="online")
    assert availability_tracking_enabled_now(repo, "home") is True
    assert not _build_coverage(tracking_enabled_now=True)


def test_availability_tracking_on_with_recorded_transition(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0xa1", availability="unknown")
    _insert_availability_change(repo, "0xa1", "offline", NOW - timedelta(hours=1))
    assert availability_tracking_enabled_now(repo, "home") is True


def test_route_hints_unavailable_from_topology_fact():
    facts = [_fact(TopologyFactCode.route_hints_unavailable)]
    items = _build_coverage(network_facts=facts)
    assert len(items) == 1
    item = items[0]
    assert item.label_code == CoverageLabelCode.route_hints_unavailable
    assert item.dimension == CoverageDimension.route_hints
    assert item.state == CoverageState.not_observed


def test_snapshot_stale_only_when_stale_fact_present():
    stale_facts = [
        _fact(
            TopologyFactCode.latest_snapshot_stale,
            age_hours=30.0,
            stale_after_hours=24,
            snapshot_id="snap-old",
        )
    ]
    items = _build_coverage(network_facts=stale_facts)
    assert len(items) == 1
    assert items[0].label_code == CoverageLabelCode.snapshot_stale
    assert items[0].params["age_hours"] == 30.0
    assert not _build_coverage(
        network_facts=[_fact(TopologyFactCode.latest_snapshot_complete, snapshot_id="snap")]
    )


def test_ha_areas_not_linked_without_area_assignments(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0xa1")
    _store_ha_enrichment(repo, "0xa1")
    assert repo.network_has_usable_ha_area_assignments("home") is False
    items = _build_coverage(has_usable_ha_area_assignments=False)
    assert any(
        item.label_code == CoverageLabelCode.ha_areas_not_linked for item in items
    )


def test_ha_areas_not_linked_when_no_enrichment_rows(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0xa1")
    assert repo.network_has_usable_ha_area_assignments("home") is False
    items = _build_coverage(has_usable_ha_area_assignments=False)
    assert any(
        item.label_code == CoverageLabelCode.ha_areas_not_linked for item in items
    )


def test_ha_areas_linked_when_area_name_present(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0xa1")
    _store_ha_enrichment(repo, "0xa1", area_name="Hall")
    assert repo.network_has_usable_ha_area_assignments("home") is True
    assert not any(
        item.label_code == CoverageLabelCode.ha_areas_not_linked
        for item in _build_coverage(has_usable_ha_area_assignments=True)
    )


def test_matched_device_count_alone_does_not_clear_ha_areas_not_linked(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0xa1")
    _store_ha_enrichment(repo, "0xa1", area_id="   ", area_name="")
    assert repo.network_has_usable_ha_area_assignments("home") is False


def test_coverage_order_is_deterministic():
    facts = [
        _fact(TopologyFactCode.route_hints_unavailable),
        _fact(
            TopologyFactCode.latest_snapshot_stale,
            age_hours=30.0,
            stale_after_hours=24,
            snapshot_id="snap-old",
        ),
    ]
    items = _build_coverage(
        network_facts=facts,
        tracking_enabled_now=False,
        has_usable_ha_area_assignments=False,
    )
    labels = [item.label_code for item in items]
    assert labels == [
        CoverageLabelCode.availability_tracking_off,
        CoverageLabelCode.snapshot_stale,
        CoverageLabelCode.route_hints_unavailable,
        CoverageLabelCode.ha_areas_not_linked,
    ]
