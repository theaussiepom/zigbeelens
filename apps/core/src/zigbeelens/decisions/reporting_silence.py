"""Current silence assessment for sleepy battery devices (Phase 4B-2).

Combines observed reporting rhythm (4B-1) with current time to classify whether
the device has been silent longer than its observed cadence suggests. Outputs
coded facts only — presenters map them to cautious copy.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from zigbeelens.decisions.reporting_rhythm import ReportingRhythm, ReportingRhythmState

# Silence beyond p75 * this multiplier may be classified as beyond_expected.
SUSPICION_MULTIPLIER = 2.5
# Ignore very short silence when classifying against rhythm.
MIN_SILENCE_MINUTES_FOR_CLASSIFICATION = 30


class SilenceState(StrEnum):
    """How current silence compares to the observed rhythm."""

    within_expected = "within_expected"
    beyond_expected = "beyond_expected"
    unknown = "unknown"


class ReportingSilence(BaseModel):
    """Coded current-silence facts for one device."""

    subject_type: str = "device"
    subject_id: str
    silence_minutes: int
    silence_state: SilenceState
    suspicion_threshold_minutes: int
    interval_minutes_p25: int | None = None
    interval_minutes_median: int | None = None
    interval_minutes_p75: int | None = None
    latest_observed_at: datetime | None = None


def _interval_minutes(start: datetime, end: datetime) -> int:
    return max(0, int((end - start).total_seconds() // 60))


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


def build_reporting_silence(
    rhythm: ReportingRhythm,
    *,
    now: datetime,
) -> ReportingSilence | None:
    """Classify current silence against an available reporting rhythm."""
    if rhythm.state is not ReportingRhythmState.rhythm_available:
        return None
    if rhythm.latest_observed_at is None or rhythm.interval_minutes_p75 is None:
        return None

    silence_minutes = _interval_minutes(rhythm.latest_observed_at, now)
    suspicion_threshold_minutes = max(
        int(rhythm.interval_minutes_p75 * SUSPICION_MULTIPLIER),
        MIN_SILENCE_MINUTES_FOR_CLASSIFICATION,
    )
    silence_state = _classify_silence(
        silence_minutes,
        interval_minutes_p75=rhythm.interval_minutes_p75,
    )

    return ReportingSilence(
        subject_id=rhythm.subject_id,
        silence_minutes=silence_minutes,
        silence_state=silence_state,
        suspicion_threshold_minutes=suspicion_threshold_minutes,
        interval_minutes_p25=rhythm.interval_minutes_p25,
        interval_minutes_median=rhythm.interval_minutes_median,
        interval_minutes_p75=rhythm.interval_minutes_p75,
        latest_observed_at=rhythm.latest_observed_at,
    )
