"""Observed reporting rhythm for sleepy battery devices (Phase 4B-1).

Learns typical payload-reporting intervals from stored device snapshots and
classifies current silence against that rhythm. Outputs coded facts only —
presenters map them to cautious copy. Does not claim device failure.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from statistics import median
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from zigbeelens.storage.repository import DeviceRow, Repository

# Bounded history window for rhythm calculation.
MAX_SNAPSHOTS = 50
# Minimum filtered interval samples required before claiming a rhythm.
MIN_INTERVAL_SAMPLES = 4
# Gaps larger than this multiple of the median interval are treated as collector downtime.
COLLECTOR_GAP_MULTIPLIER = 4.0
# Absolute floor for treating a gap as collector downtime (minutes).
COLLECTOR_GAP_FLOOR_MINUTES = 12 * 60
# Silence beyond p75 * this multiplier may be classified as beyond_expected.
SUSPICION_MULTIPLIER = 2.5
# Ignore very short silence when classifying against rhythm.
MIN_SILENCE_MINUTES_FOR_CLASSIFICATION = 30


class ReportingRhythmState(StrEnum):
    """Whether a rhythm could be derived for this device."""

    not_applicable = "not_applicable"
    insufficient_history = "insufficient_history"
    rhythm_available = "rhythm_available"


class SilenceState(StrEnum):
    """How current silence compares to the observed rhythm."""

    within_expected = "within_expected"
    beyond_expected = "beyond_expected"
    unknown = "unknown"


class ReportingRhythm(BaseModel):
    """Coded reporting-rhythm facts for one device."""

    subject_type: str = "device"
    subject_id: str
    state: ReportingRhythmState
    observation_count: int = 0
    interval_sample_count: int = 0
    interval_minutes_p25: int | None = None
    interval_minutes_median: int | None = None
    interval_minutes_p75: int | None = None
    silence_minutes: int | None = None
    silence_state: SilenceState | None = None
    params: dict[str, Any] = Field(default_factory=dict)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def is_sleepy_device_candidate(device: DeviceRow) -> bool:
    """Battery end devices are the only sleepy rhythm subjects in 4B-1."""
    return device.device_type == "EndDevice" and device.power_source == "Battery"


def _percentile(sorted_values: list[int], fraction: float) -> int:
    if not sorted_values:
        raise ValueError("sorted_values must not be empty")
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = (len(sorted_values) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    if lower == upper:
        return sorted_values[lower]
    weight = index - lower
    return round(sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * weight)


def _observation_times(snapshots: list[dict[str, Any]]) -> list[datetime]:
    times: list[datetime] = []
    seen: set[datetime] = set()
    for row in snapshots:
        observed_at = _parse_ts(row.get("last_payload_at")) or _parse_ts(row.get("captured_at"))
        if observed_at is None or observed_at in seen:
            continue
        seen.add(observed_at)
        times.append(observed_at)
    times.sort()
    return times


def _interval_minutes(start: datetime, end: datetime) -> int:
    return max(0, int((end - start).total_seconds() // 60))


def _filter_collector_gaps(intervals: list[int]) -> list[int]:
    if not intervals:
        return []
    preliminary_median = int(median(intervals))
    threshold = max(
        int(preliminary_median * COLLECTOR_GAP_MULTIPLIER),
        COLLECTOR_GAP_FLOOR_MINUTES,
    )
    return [gap for gap in intervals if gap <= threshold]


def _classify_silence(
    silence_minutes: int,
    *,
    interval_minutes_p75: int,
) -> SilenceState:
    if silence_minutes < MIN_SILENCE_MINUTES_FOR_CLASSIFICATION:
        return SilenceState.within_expected
    threshold = max(
        int(interval_minutes_p75 * SUSPICION_MULTIPLIER),
        MIN_SILENCE_MINUTES_FOR_CLASSIFICATION,
    )
    if silence_minutes > threshold:
        return SilenceState.beyond_expected
    return SilenceState.within_expected


def build_reporting_rhythm(
    *,
    device_ieee: str,
    observation_times: list[datetime],
    now: datetime,
    applicable: bool,
) -> ReportingRhythm:
    """Compute rhythm facts from deduplicated observation timestamps."""
    if not applicable:
        return ReportingRhythm(
            subject_id=device_ieee,
            state=ReportingRhythmState.not_applicable,
        )

    observation_count = len(observation_times)
    if observation_count < MIN_INTERVAL_SAMPLES + 1:
        return ReportingRhythm(
            subject_id=device_ieee,
            state=ReportingRhythmState.insufficient_history,
            observation_count=observation_count,
        )

    raw_intervals = [
        _interval_minutes(observation_times[index - 1], observation_times[index])
        for index in range(1, len(observation_times))
    ]
    intervals = [gap for gap in _filter_collector_gaps(raw_intervals) if gap > 0]
    if len(intervals) < MIN_INTERVAL_SAMPLES:
        return ReportingRhythm(
            subject_id=device_ieee,
            state=ReportingRhythmState.insufficient_history,
            observation_count=observation_count,
            interval_sample_count=len(intervals),
        )

    sorted_intervals = sorted(intervals)
    p25 = _percentile(sorted_intervals, 0.25)
    p75 = _percentile(sorted_intervals, 0.75)
    median_minutes = int(median(sorted_intervals))
    silence_minutes = _interval_minutes(observation_times[-1], now)
    silence_state = _classify_silence(silence_minutes, interval_minutes_p75=p75)

    return ReportingRhythm(
        subject_id=device_ieee,
        state=ReportingRhythmState.rhythm_available,
        observation_count=observation_count,
        interval_sample_count=len(intervals),
        interval_minutes_p25=p25,
        interval_minutes_median=median_minutes,
        interval_minutes_p75=p75,
        silence_minutes=silence_minutes,
        silence_state=silence_state,
        params={
            "collector_gap_threshold_minutes": max(
                int(median_minutes * COLLECTOR_GAP_MULTIPLIER),
                COLLECTOR_GAP_FLOOR_MINUTES,
            ),
            "suspicion_threshold_minutes": max(
                int(p75 * SUSPICION_MULTIPLIER),
                MIN_SILENCE_MINUTES_FOR_CLASSIFICATION,
            ),
        },
    )


def reporting_rhythm_for_device(
    repo: Repository,
    network_id: str,
    device_ieee: str,
    *,
    now: datetime | None = None,
) -> ReportingRhythm | None:
    """Load stored snapshots and compute reporting rhythm for one device."""
    device = repo.get_device(network_id, device_ieee)
    if device is None:
        return None

    now = now or datetime.now(timezone.utc)
    snapshots = repo.list_device_snapshots(network_id, device_ieee, limit=MAX_SNAPSHOTS)
    observation_times = _observation_times(list(reversed(snapshots)))
    return build_reporting_rhythm(
        device_ieee=device_ieee,
        observation_times=observation_times,
        now=now,
        applicable=is_sleepy_device_candidate(device),
    )
