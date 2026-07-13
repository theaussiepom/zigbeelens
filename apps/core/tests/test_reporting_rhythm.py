"""Tests for sleepy-device reporting rhythm calculation (Phase 4B-1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.reporting_rhythm import (
    ReportingRhythm,
    ReportingRhythmState,
    build_reporting_rhythm,
    is_sleepy_device_candidate,
    reporting_rhythm_for_device,
)
from zigbeelens.storage.repository import DeviceRow, Repository

BASE = datetime(2026, 7, 13, 0, 0, 0, tzinfo=timezone.utc)
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


def _insert_payload_snapshot(
    repo: Repository,
    ieee: str,
    *,
    last_payload_at: datetime,
    captured_at: datetime | None = None,
) -> None:
    payload_at = last_payload_at.isoformat()
    repo.db.conn.execute(
        """
        INSERT INTO device_snapshots (
            network_id, ieee_address, availability, last_seen, last_payload_at,
            linkquality, battery, payload_json, captured_at
        ) VALUES ('home', ?, 'online', ?, ?, 120, 80, '{}', ?)
        """,
        (ieee, payload_at, payload_at, (captured_at or last_payload_at).isoformat()),
    )
    repo.db.conn.commit()


def _insert_snapshot_without_payload_at(
    repo: Repository,
    ieee: str,
    *,
    captured_at: datetime,
) -> None:
    repo.db.conn.execute(
        """
        INSERT INTO device_snapshots (
            network_id, ieee_address, availability, last_seen, last_payload_at,
            linkquality, battery, payload_json, captured_at
        ) VALUES ('home', ?, 'online', NULL, NULL, 120, 80, '{}', ?)
        """,
        (ieee, captured_at.isoformat()),
    )
    repo.db.conn.commit()


def _payload_observations(
    *,
    start: datetime,
    count: int,
    interval_minutes: int,
) -> list[datetime]:
    return [start + timedelta(minutes=interval_minutes * index) for index in range(count)]


def _seed_payload_observations(
    repo: Repository,
    ieee: str,
    observations: list[datetime],
) -> None:
    for observed_at in observations:
        _insert_payload_snapshot(repo, ieee, last_payload_at=observed_at)


def test_unknown_device_returns_none(tmp_path: Path):
    repo = _repo(tmp_path)
    assert reporting_rhythm_for_device(repo, "home", "0xmissing") is None


def test_invalid_ieee_returns_none(tmp_path: Path):
    repo = _repo(tmp_path)
    assert reporting_rhythm_for_device(repo, "home", "   ") is None


def test_battery_end_device_is_applicable(tmp_path: Path):
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


def test_mains_router_is_not_applicable(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x02", device_type="Router", power_source="Mains")

    rhythm = reporting_rhythm_for_device(repo, "home", "0x02")
    assert rhythm is not None
    assert rhythm.state is ReportingRhythmState.not_applicable


def test_mains_end_device_is_not_applicable(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x04", device_type="EndDevice", power_source="Mains")

    rhythm = reporting_rhythm_for_device(repo, "home", "0x04")
    assert rhythm is not None
    assert rhythm.state is ReportingRhythmState.not_applicable


def test_battery_router_is_not_applicable(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x05", device_type="Router", power_source="Battery")

    rhythm = reporting_rhythm_for_device(repo, "home", "0x05")
    assert rhythm is not None
    assert rhythm.state is ReportingRhythmState.not_applicable


def test_eight_observations_seven_intervals_is_insufficient_history(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    observations = _payload_observations(start=BASE, count=8, interval_minutes=60)
    _seed_payload_observations(repo, "0x03", observations)

    rhythm = reporting_rhythm_for_device(repo, "home", "0x03")
    assert rhythm is not None
    assert rhythm.state is ReportingRhythmState.insufficient_history
    assert rhythm.observation_count == 8
    assert rhythm.interval_sample_count == 7
    assert rhythm.interval_minutes_median is None
    assert rhythm.latest_observed_at == observations[-1]


def test_nine_observations_eight_intervals_is_rhythm_available(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    observations = _payload_observations(start=BASE, count=9, interval_minutes=60)
    _seed_payload_observations(repo, "0x03", observations)

    rhythm = reporting_rhythm_for_device(repo, "home", "0x03")
    assert rhythm is not None
    assert rhythm.state is ReportingRhythmState.rhythm_available
    assert rhythm.observation_count == 9
    assert rhythm.interval_sample_count == 8
    assert rhythm.interval_minutes_p25 == 60
    assert rhythm.interval_minutes_median == 60
    assert rhythm.interval_minutes_p75 == 60
    assert rhythm.interval_minutes_max == 60
    assert rhythm.latest_observed_at == observations[-1]


def test_regular_payload_observations_produce_deterministic_percentiles():
    observations = _payload_observations(start=BASE, count=9, interval_minutes=45)
    rhythm = build_reporting_rhythm(
        device_ieee="0x03",
        observation_times=observations,
        applicable=True,
    )
    assert rhythm.state is ReportingRhythmState.rhythm_available
    assert rhythm.interval_minutes_p25 == 45
    assert rhythm.interval_minutes_median == 45
    assert rhythm.interval_minutes_p75 == 45
    assert rhythm.interval_minutes_max == 45
    assert rhythm.latest_observed_at == observations[-1]


def test_duplicate_payload_timestamps_are_deduplicated(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    observations = _payload_observations(start=BASE, count=9, interval_minutes=60)
    for observed_at in observations:
        _insert_payload_snapshot(repo, "0x03", last_payload_at=observed_at)
    _insert_payload_snapshot(repo, "0x03", last_payload_at=observations[-1])

    rhythm = reporting_rhythm_for_device(repo, "home", "0x03")
    assert rhythm is not None
    assert rhythm.observation_count == 9
    assert rhythm.interval_sample_count == 8


def test_missing_last_payload_at_does_not_fall_back_to_captured_at(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    observations = _payload_observations(start=BASE, count=9, interval_minutes=60)
    _seed_payload_observations(repo, "0x03", observations)
    _insert_snapshot_without_payload_at(repo, "0x03", captured_at=NOW)

    rhythm = reporting_rhythm_for_device(repo, "home", "0x03")
    assert rhythm is not None
    assert rhythm.observation_count == 9


def test_invalid_payload_timestamps_are_ignored(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    observations = _payload_observations(start=BASE, count=9, interval_minutes=60)
    _seed_payload_observations(repo, "0x03", observations)
    repo.db.conn.execute(
        """
        INSERT INTO device_snapshots (
            network_id, ieee_address, availability, last_seen, last_payload_at,
            linkquality, battery, payload_json, captured_at
        ) VALUES ('home', '0x03', 'online', NULL, 'not-a-timestamp', 120, 80, '{}', ?)
        """,
        (NOW.isoformat(),),
    )
    repo.db.conn.commit()

    rhythm = reporting_rhythm_for_device(repo, "home", "0x03")
    assert rhythm is not None
    assert rhythm.observation_count == 9


def test_large_observed_intervals_remain_in_interval_sample_count(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    observations = [
        BASE,
        BASE + timedelta(minutes=40),
        BASE + timedelta(minutes=80),
        BASE + timedelta(minutes=120),
        BASE + timedelta(hours=20),
        BASE + timedelta(hours=20, minutes=40),
        BASE + timedelta(hours=21, minutes=20),
        BASE + timedelta(hours=22),
        BASE + timedelta(hours=22, minutes=40),
    ]
    _seed_payload_observations(repo, "0x03", observations)

    rhythm = reporting_rhythm_for_device(repo, "home", "0x03")
    assert rhythm is not None
    assert rhythm.state is ReportingRhythmState.rhythm_available
    assert rhythm.interval_sample_count == 8
    assert rhythm.interval_minutes_max == 18 * 60


def test_reporting_rhythm_model_has_no_silence_classification_fields():
    fields = set(ReportingRhythm.model_fields)
    assert "silence_minutes" not in fields
    assert "silence_state" not in fields
    assert "interval_minutes_max" in fields

    payload = ReportingRhythm(
        subject_id="0x03",
        state=ReportingRhythmState.rhythm_available,
        observation_count=9,
        interval_sample_count=8,
        interval_minutes_p25=40,
        interval_minutes_median=40,
        interval_minutes_p75=1080,
        interval_minutes_max=1080,
        latest_observed_at=BASE,
    ).model_dump(mode="json")

    assert "silence_minutes" not in payload
    assert "silence_state" not in payload
    assert "suspicion_threshold_minutes" not in payload
    assert "collector_gap_threshold_minutes" not in payload
    assert payload["interval_minutes_max"] == 1080


def test_mixed_case_ieee_resolves_canonical_subject_id(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    observations = _payload_observations(start=BASE, count=9, interval_minutes=60)
    _seed_payload_observations(repo, "0x03", observations)

    rhythm = reporting_rhythm_for_device(repo, "home", "0X03")
    assert rhythm is not None
    assert rhythm.subject_id == "0x03"


def test_build_reporting_rhythm_is_deterministic():
    observations = _payload_observations(start=BASE, count=9, interval_minutes=45)
    first = build_reporting_rhythm(
        device_ieee="0x03",
        observation_times=observations,
        applicable=True,
    )
    second = build_reporting_rhythm(
        device_ieee="0x03",
        observation_times=observations,
        applicable=True,
    )
    assert first == second


def test_sparse_samples_return_insufficient_history(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    observations = _payload_observations(start=BASE, count=3, interval_minutes=45)
    _seed_payload_observations(repo, "0x03", observations)

    rhythm = reporting_rhythm_for_device(repo, "home", "0x03")
    assert rhythm is not None
    assert rhythm.state is ReportingRhythmState.insufficient_history
    assert rhythm.latest_observed_at == observations[-1]
