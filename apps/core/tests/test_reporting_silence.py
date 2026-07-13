"""Tests for sleepy-device reporting silence assessment (Phase 4B-2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from zigbeelens.decisions.reporting_rhythm import (
    ReportingRhythm,
    ReportingRhythmState,
    build_reporting_rhythm,
)
from zigbeelens.decisions.reporting_silence import (
    SilenceState,
    build_reporting_silence,
)

BASE = datetime(2026, 7, 13, 0, 0, 0, tzinfo=timezone.utc)


def _rhythm(
    *,
    latest_observed_at: datetime,
    interval_minutes: int = 60,
) -> ReportingRhythm:
    observations = [
        latest_observed_at - timedelta(minutes=interval_minutes * index)
        for index in range(8, -1, -1)
    ]
    return build_reporting_rhythm(
        device_ieee="0x03",
        observation_times=observations,
        applicable=True,
    )


def test_build_reporting_silence_returns_none_without_rhythm_available():
    rhythm = ReportingRhythm(
        subject_id="0x03",
        state=ReportingRhythmState.insufficient_history,
        observation_count=5,
        interval_sample_count=4,
        latest_observed_at=BASE,
    )
    assert build_reporting_silence(rhythm, now=BASE + timedelta(hours=2)) is None


def test_silence_within_expected_when_below_threshold():
    latest = BASE + timedelta(hours=8)
    rhythm = _rhythm(latest_observed_at=latest, interval_minutes=60)
    now = latest + timedelta(minutes=90)

    silence = build_reporting_silence(rhythm, now=now)
    assert silence is not None
    assert silence.silence_state is SilenceState.within_expected
    assert silence.silence_minutes == 90
    assert silence.suspicion_threshold_minutes == 150


def test_silence_beyond_expected_when_above_threshold():
    latest = BASE + timedelta(hours=8)
    rhythm = _rhythm(latest_observed_at=latest, interval_minutes=60)
    now = latest + timedelta(hours=4)

    silence = build_reporting_silence(rhythm, now=now)
    assert silence is not None
    assert silence.silence_state is SilenceState.beyond_expected
    assert silence.silence_minutes == 240
    assert silence.suspicion_threshold_minutes == 150


def test_short_silence_is_within_expected():
    latest = BASE + timedelta(hours=8)
    rhythm = _rhythm(latest_observed_at=latest, interval_minutes=60)
    now = latest + timedelta(minutes=20)

    silence = build_reporting_silence(rhythm, now=now)
    assert silence is not None
    assert silence.silence_state is SilenceState.within_expected


def test_build_reporting_silence_is_deterministic():
    latest = BASE + timedelta(hours=8)
    rhythm = _rhythm(latest_observed_at=latest, interval_minutes=60)
    now = latest + timedelta(hours=2)

    first = build_reporting_silence(rhythm, now=now)
    second = build_reporting_silence(rhythm, now=now)
    assert first == second
