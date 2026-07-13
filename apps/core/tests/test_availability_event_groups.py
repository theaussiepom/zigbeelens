"""Tests for shared availability event grouping (Phase 4E-1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.availability_event_groups import (
    SHARED_EVENT_MIN_DEVICES,
    SharedAvailabilityEventState,
    build_shared_availability_event_groups,
    shared_availability_event_groups_for_network,
)
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.passive_hints import PASSIVE_HINT_MAX_DEVICES_PER_WINDOW

NOW = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "availability-events.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "availability-events.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    return repo


def _add_device(repo: Repository, ieee: str) -> None:
    repo.upsert_device(
        network_id="home",
        ieee_address=ieee,
        friendly_name=f"Device {ieee}",
        device_type="EndDevice",
        power_source="Mains",
    )


def _offline_event(repo: Repository, ieee: str, at: datetime) -> None:
    repo.db.conn.execute(
        """
        INSERT INTO availability_changes (network_id, ieee_address, from_state, to_state, changed_at)
        VALUES ('home', ?, 'online', 'offline', ?)
        """,
        (ieee, at.isoformat()),
    )
    repo.db.conn.commit()


def _network_wide_offline_window(
    repo: Repository,
    devices: list[str],
    *,
    base: datetime,
) -> None:
    for index, ieee in enumerate(devices):
        _offline_event(repo, ieee, base + timedelta(seconds=10 * index))


def test_empty_network_returns_no_events(tmp_path: Path):
    repo = _repo(tmp_path)
    result = shared_availability_event_groups_for_network(repo, "home", now=NOW)
    assert result.state is SharedAvailabilityEventState.no_events
    assert result.groups == []


def test_pairwise_window_does_not_create_shared_event(tmp_path: Path):
    repo = _repo(tmp_path)
    _add_device(repo, "0xa1")
    _add_device(repo, "0xa2")
    base = NOW - timedelta(days=1)
    _offline_event(repo, "0xa1", base)
    _offline_event(repo, "0xa2", base + timedelta(minutes=2))

    result = shared_availability_event_groups_for_network(repo, "home", now=NOW)
    assert result.state is SharedAvailabilityEventState.no_events


def test_network_wide_window_creates_shared_event(tmp_path: Path):
    repo = _repo(tmp_path)
    devices = [f"0xd{i:02d}" for i in range(SHARED_EVENT_MIN_DEVICES)]
    for ieee in devices:
        _add_device(repo, ieee)
    _network_wide_offline_window(repo, devices, base=NOW - timedelta(days=1))

    result = shared_availability_event_groups_for_network(repo, "home", now=NOW)
    assert result.state is SharedAvailabilityEventState.events_available
    assert len(result.groups) == 1
    group = result.groups[0]
    assert group.device_count == SHARED_EVENT_MIN_DEVICES
    assert set(group.device_ieees) == set(devices)
    assert group.params["device_count"] == SHARED_EVENT_MIN_DEVICES
    assert group.params["min_devices"] == SHARED_EVENT_MIN_DEVICES


def test_passive_hint_excluded_window_matches_shared_event_threshold(tmp_path: Path):
    assert SHARED_EVENT_MIN_DEVICES == PASSIVE_HINT_MAX_DEVICES_PER_WINDOW + 1


def test_unknown_devices_are_ignored(tmp_path: Path):
    repo = _repo(tmp_path)
    devices = [f"0xd{i:02d}" for i in range(SHARED_EVENT_MIN_DEVICES - 1)]
    for ieee in devices:
        _add_device(repo, ieee)
    unknown = "0xunknown"
    base = NOW - timedelta(days=1)
    for ieee in devices:
        _offline_event(repo, ieee, base)
    _offline_event(repo, unknown, base + timedelta(seconds=30))

    result = shared_availability_event_groups_for_network(repo, "home", now=NOW)
    assert result.state is SharedAvailabilityEventState.no_events


def test_build_shared_availability_event_groups_is_deterministic():
    started = NOW - timedelta(hours=2)
    ended = NOW - timedelta(hours=1, minutes=56)
    devices = {f"0xd{i:02d}" for i in range(SHARED_EVENT_MIN_DEVICES)}
    windows = [(started, ended, devices)]

    first = build_shared_availability_event_groups(network_id="home", windows=windows)
    second = build_shared_availability_event_groups(network_id="home", windows=windows)
    assert first == second
    assert first.groups[0].event_id == second.groups[0].event_id


def test_multiple_network_wide_windows_are_sorted_newest_first(tmp_path: Path):
    repo = _repo(tmp_path)
    devices = [f"0xd{i:02d}" for i in range(SHARED_EVENT_MIN_DEVICES)]
    for ieee in devices:
        _add_device(repo, ieee)
    _network_wide_offline_window(repo, devices, base=NOW - timedelta(days=2))
    _network_wide_offline_window(repo, devices, base=NOW - timedelta(days=1))

    result = shared_availability_event_groups_for_network(repo, "home", now=NOW)
    assert len(result.groups) == 2
    assert result.groups[0].started_at > result.groups[1].started_at
