"""Per-device reported LQI trend from stored payload snapshots (Phase 4D-1).

Compares recent and earlier bounded windows of stored linkquality values.
Outputs coded facts only — no RF path or root-cause claims (Phase 4D-2).
"""

from __future__ import annotations

from enum import StrEnum
from statistics import median
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from zigbeelens.decisions.topology_facts import normalize_device_ieee

if TYPE_CHECKING:
    from zigbeelens.storage.repository import Repository

# Bounded lookback for trend calculation.
MAX_SNAPSHOTS = 50
# Samples per comparison window.
WINDOW_SIZE = 3
# Minimum stored LQI observations before comparing windows.
MIN_LQI_SAMPLES = WINDOW_SIZE * 2
# Minimum median shift between windows before calling a trend non-stable.
TREND_DELTA_THRESHOLD = 15


class LqiTrendState(StrEnum):
    """Whether a cautious LQI trend could be derived for this device."""

    insufficient_history = "insufficient_history"
    stable = "stable"
    declining = "declining"
    improving = "improving"


class LqiTrend(BaseModel):
    """Coded reported-LQI trend facts for one device."""

    subject_type: str = "device"
    subject_id: str
    state: LqiTrendState
    sample_count: int = 0
    window_size: int = WINDOW_SIZE
    recent_median: int | None = None
    earlier_median: int | None = None
    delta: int | None = None
    latest_value: int | None = None
    params: dict[str, Any] = Field(default_factory=dict)


def _lqi_samples(snapshots: list[dict[str, Any]]) -> list[int]:
    """Chronological distinct stored linkquality observations, oldest first."""
    samples: list[int] = []
    seen: set[str] = set()
    for row in reversed(snapshots):
        value = row.get("linkquality")
        if value is None:
            continue
        captured_at = row.get("captured_at")
        key = str(captured_at or value)
        if key in seen:
            continue
        seen.add(key)
        samples.append(int(value))
    return samples


def build_lqi_trend(*, device_ieee: str, lqi_samples: list[int]) -> LqiTrend:
    """Compare recent and earlier LQI windows from chronological samples."""
    sample_count = len(lqi_samples)
    latest_value = lqi_samples[-1] if lqi_samples else None

    if sample_count < MIN_LQI_SAMPLES:
        return LqiTrend(
            subject_id=device_ieee,
            state=LqiTrendState.insufficient_history,
            sample_count=sample_count,
            latest_value=latest_value,
        )

    recent = lqi_samples[-WINDOW_SIZE:]
    earlier = lqi_samples[-WINDOW_SIZE * 2 : -WINDOW_SIZE]
    recent_median = int(median(recent))
    earlier_median = int(median(earlier))
    delta = recent_median - earlier_median

    if delta <= -TREND_DELTA_THRESHOLD:
        state = LqiTrendState.declining
    elif delta >= TREND_DELTA_THRESHOLD:
        state = LqiTrendState.improving
    else:
        state = LqiTrendState.stable

    return LqiTrend(
        subject_id=device_ieee,
        state=state,
        sample_count=sample_count,
        recent_median=recent_median,
        earlier_median=earlier_median,
        delta=delta,
        latest_value=latest_value,
        params={
            "recent_median": recent_median,
            "earlier_median": earlier_median,
            "delta": delta,
            "window_size": WINDOW_SIZE,
            "sample_count": sample_count,
        },
    )


def lqi_trend_for_device(
    repo: Repository,
    network_id: str,
    device_ieee: str,
) -> LqiTrend | None:
    """Load stored snapshots and compute reported LQI trend for one device."""
    device = normalize_device_ieee(device_ieee)
    if not device:
        return None

    if repo.devices.get_device(network_id, device) is None:
        return None

    snapshots = repo.devices.list_device_snapshots(network_id, device, limit=MAX_SNAPSHOTS)
    return build_lqi_trend(device_ieee=device, lqi_samples=_lqi_samples(snapshots))
