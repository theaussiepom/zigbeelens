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


def _regular_rhythm(
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


def _long_interval_observations() -> list[datetime]:
    return [
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


def _long_interval_rhythm() -> ReportingRhythm:
    return build_reporting_rhythm(
        device_ieee="0x03",
        observation_times=_long_interval_observations(),
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


def test_regular_cadence_ninety_minute_silence_is_within_expected():
    latest = BASE + timedelta(hours=8)
    rhythm = _regular_rhythm(latest_observed_at=latest, interval_minutes=60)
    now = latest + timedelta(minutes=90)

    silence = build_reporting_silence(rhythm, now=now)
    assert silence is not None
    assert silence.silence_state is SilenceState.within_expected
    assert silence.silence_minutes == 90
    assert silence.extended_silence_threshold_minutes == 150


def test_regular_cadence_four_hour_silence_is_beyond_expected():
    latest = BASE + timedelta(hours=8)
    rhythm = _regular_rhythm(latest_observed_at=latest, interval_minutes=60)
    now = latest + timedelta(hours=4)

    silence = build_reporting_silence(rhythm, now=now)
    assert silence is not None
    assert silence.silence_state is SilenceState.beyond_expected
    assert silence.silence_minutes == 240
    assert silence.extended_silence_threshold_minutes == 150


def test_long_interval_cadence_four_hour_silence_is_within_expected():
    rhythm = _long_interval_rhythm()
    latest = rhythm.latest_observed_at
    assert latest is not None

    silence = build_reporting_silence(rhythm, now=latest + timedelta(hours=4))
    assert silence is not None
    assert silence.silence_state is SilenceState.within_expected
    assert silence.silence_minutes == 240
    assert silence.extended_silence_threshold_minutes == 1120


def test_long_interval_cadence_silence_beyond_corrected_threshold():
    rhythm = _long_interval_rhythm()
    latest = rhythm.latest_observed_at
    assert latest is not None

    silence = build_reporting_silence(rhythm, now=latest + timedelta(hours=19))
    assert silence is not None
    assert silence.silence_state is SilenceState.beyond_expected
    assert silence.silence_minutes == 19 * 60
    assert silence.extended_silence_threshold_minutes == 1120


def test_now_before_latest_observed_at_is_unknown():
    latest = BASE + timedelta(hours=8)
    rhythm = _regular_rhythm(latest_observed_at=latest, interval_minutes=60)
    now = latest - timedelta(minutes=5)

    silence = build_reporting_silence(rhythm, now=now)
    assert silence is not None
    assert silence.silence_state is SilenceState.unknown
    assert silence.silence_minutes is None
    assert silence.extended_silence_threshold_minutes == 150


def test_malformed_rhythm_available_missing_cadence_field_is_unknown():
    rhythm = ReportingRhythm(
        subject_id="0x03",
        state=ReportingRhythmState.rhythm_available,
        observation_count=9,
        interval_sample_count=8,
        interval_minutes_p25=40,
        interval_minutes_median=40,
        interval_minutes_p75=40,
        interval_minutes_max=None,
        latest_observed_at=BASE,
    )

    silence = build_reporting_silence(rhythm, now=BASE + timedelta(hours=2))
    assert silence is not None
    assert silence.silence_state is SilenceState.unknown
    assert silence.silence_minutes is None
    assert silence.extended_silence_threshold_minutes is None


def test_build_reporting_silence_is_deterministic():
    latest = BASE + timedelta(hours=8)
    rhythm = _regular_rhythm(latest_observed_at=latest, interval_minutes=60)
    now = latest + timedelta(hours=2)

    first = build_reporting_silence(rhythm, now=now)
    second = build_reporting_silence(rhythm, now=now)
    assert first == second
