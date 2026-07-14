"""Observed reporting rhythm for sleepy battery devices (Phase 4B-1).

Describes historical payload-reporting cadence from stored device snapshots.
Outputs coded facts only — no current-silence judgement (Phase 4B-2).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from statistics import median
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from zigbeelens.decisions.topology_facts import normalize_device_ieee

if TYPE_CHECKING:
    from zigbeelens.storage.repository import DeviceRow, Repository

# Bounded history window for rhythm calculation.
MAX_SNAPSHOTS = 50
# Minimum positive interval samples before claiming a rhythm. Requires nine
# distinct payload observations because sleepy devices may emit short bursts of
# closely spaced payloads that are not yet a stable cadence.
MIN_INTERVAL_SAMPLES = 8


class ReportingRhythmState(StrEnum):
    """Whether a rhythm could be derived for this device."""

    not_applicable = "not_applicable"
    insufficient_history = "insufficient_history"
    rhythm_available = "rhythm_available"


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
    interval_minutes_max: int | None = None
    latest_observed_at: datetime | None = None
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
        observed_at = _parse_ts(row.get("last_payload_at"))
        if observed_at is None or observed_at in seen:
            continue
        seen.add(observed_at)
        times.append(observed_at)
    times.sort()
    return times


def _interval_minutes(start: datetime, end: datetime) -> int:
    return max(0, int((end - start).total_seconds() // 60))


def build_reporting_rhythm(
    *,
    device_ieee: str,
    observation_times: list[datetime],
    applicable: bool,
) -> ReportingRhythm:
    """Compute rhythm facts from deduplicated payload observation timestamps."""
    latest_observed_at = observation_times[-1] if observation_times else None

    if not applicable:
        return ReportingRhythm(
            subject_id=device_ieee,
            state=ReportingRhythmState.not_applicable,
        )

    observation_count = len(observation_times)
    raw_intervals = [
        _interval_minutes(observation_times[index - 1], observation_times[index])
        for index in range(1, len(observation_times))
    ]
    intervals = [interval for interval in raw_intervals if interval > 0]

    if len(intervals) < MIN_INTERVAL_SAMPLES:
        return ReportingRhythm(
            subject_id=device_ieee,
            state=ReportingRhythmState.insufficient_history,
            observation_count=observation_count,
            interval_sample_count=len(intervals),
            latest_observed_at=latest_observed_at,
        )

    sorted_intervals = sorted(intervals)
    return ReportingRhythm(
        subject_id=device_ieee,
        state=ReportingRhythmState.rhythm_available,
        observation_count=observation_count,
        interval_sample_count=len(intervals),
        interval_minutes_p25=_percentile(sorted_intervals, 0.25),
        interval_minutes_median=int(median(sorted_intervals)),
        interval_minutes_p75=_percentile(sorted_intervals, 0.75),
        interval_minutes_max=sorted_intervals[-1],
        latest_observed_at=latest_observed_at,
    )


def reporting_rhythm_for_device(
    repo: Repository,
    network_id: str,
    device_ieee: str,
    *,
    device_row: DeviceRow | None = None,
    snapshots: list[dict[str, Any]] | None = None,
) -> ReportingRhythm | None:
    """Load stored snapshots and compute reporting rhythm for one device."""
    device = normalize_device_ieee(device_ieee)
    if not device:
        return None

    resolved_device_row = device_row or repo.devices.get_device(network_id, device)
    if resolved_device_row is None:
        return None

    resolved_snapshots = (
        snapshots
        if snapshots is not None
        else repo.devices.list_device_snapshots(network_id, device, limit=MAX_SNAPSHOTS)
    )
    observation_times = _observation_times(list(reversed(resolved_snapshots)))
    return build_reporting_rhythm(
        device_ieee=device,
        observation_times=observation_times,
        applicable=is_sleepy_device_candidate(resolved_device_row),
    )
