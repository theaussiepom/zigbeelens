"""Tests for sleepy-device reporting rhythm calculation (Phase 4B-1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.reporting_rhythm import (
    ReportingRhythmState,
    SilenceState,
    build_reporting_rhythm,
    is_sleepy_device_candidate,
    reporting_rhythm_for_device,
)
from zigbeelens.storage.repository import DeviceRow, Repository

NOW = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "reporting-rhythm.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "reporting-rhythm.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    return repo


def _upsert_device(
    repo: Repository,
    ieee: str,
    *,
    device_type: str = "EndDevice",
    power_source: str = "Battery",
) -> None:
    repo.upsert_device(
        network_id="home",
        ieee_address=ieee,
        friendly_name=f"Device {ieee}",
        device_type=device_type,
        power_source=power_source,
        interview_state="successful",
    )


def _insert_snapshot(
    repo: Repository,
    ieee: str,
    *,
    captured_at: datetime,
    last_payload_at: datetime | None = None,
) -> None:
    payload_at = (last_payload_at or captured_at).isoformat()
    repo.db.conn.execute(
        """
        INSERT INTO device_snapshots (
            network_id, ieee_address, availability, last_seen, last_payload_at,
            linkquality, battery, payload_json, captured_at
        ) VALUES ('home', ?, 'online', ?, ?, 120, 80, '{}', ?)
        """,
        (ieee, payload_at, payload_at, captured_at.isoformat()),
    )
    repo.db.conn.commit()


def _battery_observations(
    *,
    start: datetime,
    count: int,
    interval_minutes: int,
) -> list[datetime]:
    return [start + timedelta(minutes=interval_minutes * index) for index in range(count)]


def test_mains_device_is_not_applicable(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x02", device_type="Router", power_source="Mains")

    rhythm = reporting_rhythm_for_device(repo, "home", "0x02", now=NOW)
    assert rhythm is not None
    assert rhythm.state is ReportingRhythmState.not_applicable
    assert rhythm.silence_state is None


def test_sparse_samples_return_insufficient_history(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    for captured_at in _battery_observations(start=NOW - timedelta(hours=2), count=3, interval_minutes=45):
        _insert_snapshot(repo, "0x03", captured_at=captured_at)

    rhythm = reporting_rhythm_for_device(repo, "home", "0x03", now=NOW)
    assert rhythm is not None
    assert rhythm.state is ReportingRhythmState.insufficient_history
    assert rhythm.interval_minutes_median is None


def test_normal_sleepy_device_silence_within_expected_rhythm(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    observations = _battery_observations(
        start=NOW - timedelta(hours=8),
        count=8,
        interval_minutes=60,
    )
    for captured_at in observations:
        _insert_snapshot(repo, "0x03", captured_at=captured_at)

    rhythm = reporting_rhythm_for_device(repo, "home", "0x03", now=NOW)
    assert rhythm is not None
    assert rhythm.state is ReportingRhythmState.rhythm_available
    assert rhythm.interval_minutes_median == 60
    assert rhythm.silence_minutes == 60
    assert rhythm.silence_state is SilenceState.within_expected


def test_suspicious_silence_beyond_observed_rhythm(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    observations = _battery_observations(
        start=NOW - timedelta(days=2),
        count=10,
        interval_minutes=50,
    )
    for captured_at in observations:
        _insert_snapshot(repo, "0x03", captured_at=captured_at)

    rhythm = reporting_rhythm_for_device(repo, "home", "0x03", now=NOW)
    assert rhythm is not None
    assert rhythm.state is ReportingRhythmState.rhythm_available
    assert rhythm.silence_minutes is not None
    assert rhythm.silence_minutes > 12 * 60
    assert rhythm.silence_state is SilenceState.beyond_expected


def test_collector_gap_does_not_distort_rhythm(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    early = _battery_observations(start=NOW - timedelta(days=3), count=5, interval_minutes=40)
    late = _battery_observations(start=NOW - timedelta(hours=4), count=5, interval_minutes=40)
    for captured_at in [*early, NOW - timedelta(days=2), *late]:
        _insert_snapshot(repo, "0x03", captured_at=captured_at)

    rhythm = reporting_rhythm_for_device(repo, "home", "0x03", now=NOW)
    assert rhythm is not None
    assert rhythm.state is ReportingRhythmState.rhythm_available
    assert rhythm.interval_minutes_median == 40
    assert rhythm.silence_state is SilenceState.within_expected


def test_is_sleepy_device_candidate_only_battery_end_devices():
    assert is_sleepy_device_candidate(
        DeviceRow(
            network_id="home",
            ieee_address="0x03",
            friendly_name="Sensor",
            device_type="EndDevice",
            power_source="Battery",
            manufacturer=None,
            model=None,
            interview_state="successful",
        )
    )
    assert not is_sleepy_device_candidate(
        DeviceRow(
            network_id="home",
            ieee_address="0x02",
            friendly_name="Router",
            device_type="Router",
            power_source="Mains",
            manufacturer=None,
            model=None,
            interview_state="successful",
        )
    )


def test_build_reporting_rhythm_is_deterministic():
    observations = _battery_observations(start=NOW - timedelta(hours=6), count=7, interval_minutes=45)
    first = build_reporting_rhythm(
        device_ieee="0x03",
        observation_times=observations,
        now=NOW,
        applicable=True,
    )
    second = build_reporting_rhythm(
        device_ieee="0x03",
        observation_times=observations,
        now=NOW,
        applicable=True,
    )
    assert first == second
