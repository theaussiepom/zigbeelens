"""Tests for per-device reported LQI trend calculation (Phase 4D-1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.lqi_trend import (
    LqiTrend,
    LqiTrendState,
    MIN_LQI_SAMPLES,
    TREND_DELTA_THRESHOLD,
    WINDOW_SIZE,
    build_lqi_trend,
    lqi_trend_for_device,
)
from zigbeelens.storage.repository import Repository

BASE = datetime(2026, 7, 13, 0, 0, 0, tzinfo=timezone.utc)


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "lqi-trend.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "lqi-trend.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    return repo


def _upsert_device(repo: Repository, ieee: str) -> None:
    repo.upsert_device(
        network_id="home",
        ieee_address=ieee,
        friendly_name=f"Device {ieee}",
        device_type="Router",
        power_source="Mains",
        interview_state="successful",
    )


def _insert_lqi_snapshot(
    repo: Repository,
    ieee: str,
    *,
    linkquality: int | None,
    captured_at: datetime,
) -> None:
    repo.db.conn.execute(
        """
        INSERT INTO device_snapshots (
            network_id, ieee_address, availability, last_seen, last_payload_at,
            linkquality, battery, payload_json, captured_at
        ) VALUES ('home', ?, 'online', ?, ?, ?, NULL, '{}', ?)
        """,
        (
            ieee,
            captured_at.isoformat(),
            captured_at.isoformat(),
            linkquality,
            captured_at.isoformat(),
        ),
    )
    repo.db.conn.commit()


def _seed_lqi_series(
    repo: Repository,
    ieee: str,
    values: list[int | None],
    *,
    start: datetime = BASE,
    interval_minutes: int = 5,
) -> None:
    for index, value in enumerate(values):
        captured_at = start + timedelta(minutes=interval_minutes * index)
        _insert_lqi_snapshot(repo, ieee, linkquality=value, captured_at=captured_at)


def test_unknown_device_returns_none(tmp_path: Path):
    repo = _repo(tmp_path)
    assert lqi_trend_for_device(repo, "home", "0xmissing") is None


def test_invalid_ieee_returns_none(tmp_path: Path):
    repo = _repo(tmp_path)
    assert lqi_trend_for_device(repo, "home", "   ") is None


def test_build_lqi_trend_insufficient_history():
    trend = build_lqi_trend(device_ieee="0xabc", lqi_samples=[120, 118, 116, 114, 112])
    assert trend == LqiTrend(
        subject_id="0xabc",
        state=LqiTrendState.insufficient_history,
        sample_count=5,
        latest_value=112,
    )


def test_build_lqi_trend_stable_when_delta_within_threshold():
    trend = build_lqi_trend(
        device_ieee="0xabc",
        lqi_samples=[120, 118, 116, 115, 114, 113],
    )
    assert trend.state == LqiTrendState.stable
    assert trend.recent_median == 114
    assert trend.earlier_median == 118
    assert trend.delta == -4
    assert trend.latest_value == 113


def test_build_lqi_trend_declining_when_recent_window_drops():
    drop = TREND_DELTA_THRESHOLD + 5
    earlier = 180
    recent = earlier - drop
    trend = build_lqi_trend(
        device_ieee="0xabc",
        lqi_samples=[
            earlier,
            earlier,
            earlier,
            recent,
            recent,
            recent,
        ],
    )
    assert trend.state == LqiTrendState.declining
    assert trend.recent_median == recent
    assert trend.earlier_median == earlier
    assert trend.delta == -drop


def test_build_lqi_trend_improving_when_recent_window_rises():
    rise = TREND_DELTA_THRESHOLD + 5
    earlier = 80
    recent = earlier + rise
    trend = build_lqi_trend(
        device_ieee="0xabc",
        lqi_samples=[
            earlier,
            earlier,
            earlier,
            recent,
            recent,
            recent,
        ],
    )
    assert trend.state == LqiTrendState.improving
    assert trend.delta == rise


def test_build_lqi_trend_uses_median_not_single_outlier():
    trend = build_lqi_trend(
        device_ieee="0xabc",
        lqi_samples=[200, 200, 200, 50, 200, 200],
    )
    assert trend.state == LqiTrendState.stable
    assert trend.recent_median == 200
    assert trend.earlier_median == 200


def test_lqi_trend_for_device_skips_null_linkquality(tmp_path: Path):
    repo = _repo(tmp_path)
    ieee = "0x00124b0022aabbcc"
    _upsert_device(repo, ieee)
    _seed_lqi_series(
        repo,
        ieee,
        [180, None, 180, None, 180, 180, 180, 180],
    )

    trend = lqi_trend_for_device(repo, "home", ieee)
    assert trend is not None
    assert trend.sample_count == 6
    assert trend.state == LqiTrendState.stable


def test_lqi_trend_for_device_deduplicates_same_captured_at(tmp_path: Path):
    repo = _repo(tmp_path)
    ieee = "0x00124b0022aabbcc"
    _upsert_device(repo, ieee)
    captured_at = BASE
    for _ in range(3):
        _insert_lqi_snapshot(repo, ieee, linkquality=180, captured_at=captured_at)
    for index in range(1, MIN_LQI_SAMPLES):
        _insert_lqi_snapshot(
            repo,
            ieee,
            linkquality=180 - index,
            captured_at=BASE + timedelta(minutes=index),
        )

    trend = lqi_trend_for_device(repo, "home", ieee)
    assert trend is not None
    assert trend.sample_count == MIN_LQI_SAMPLES


def test_lqi_trend_for_device_respects_bounded_lookback(tmp_path: Path):
    repo = _repo(tmp_path)
    ieee = "0x00124b0022aabbcc"
    _upsert_device(repo, ieee)

    values = [200] * 44 + [200, 200, 200, 80, 80, 80]
    _seed_lqi_series(repo, ieee, values, interval_minutes=1)

    trend = lqi_trend_for_device(repo, "home", ieee)
    assert trend is not None
    assert trend.sample_count == 50
    assert trend.state == LqiTrendState.declining
    assert trend.recent_median == 80
    assert trend.earlier_median == 200


def test_lqi_trend_params_include_window_metadata():
    trend = build_lqi_trend(
        device_ieee="0xabc",
        lqi_samples=[120, 120, 120, 90, 90, 90],
    )
    assert trend.params == {
        "recent_median": 90,
        "earlier_median": 120,
        "delta": -30,
        "window_size": WINDOW_SIZE,
        "sample_count": 6,
    }
