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

# Extended silence beyond p75 * this multiplier may exceed observed cadence.
EXTENDED_SILENCE_MULTIPLIER = 2.5
# Minimum cadence comparison floor for extended-silence classification.
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
    silence_minutes: int | None = None
    silence_state: SilenceState
    extended_silence_threshold_minutes: int | None = None
    interval_minutes_p25: int | None = None
    interval_minutes_median: int | None = None
    interval_minutes_p75: int | None = None
    interval_minutes_max: int | None = None
    latest_observed_at: datetime | None = None


def _extended_silence_threshold_minutes(rhythm: ReportingRhythm) -> int | None:
    if (
        rhythm.interval_minutes_p75 is None
        or rhythm.interval_minutes_median is None
        or rhythm.interval_minutes_max is None
    ):
        return None

    return max(
        int(rhythm.interval_minutes_p75 * EXTENDED_SILENCE_MULTIPLIER),
        rhythm.interval_minutes_max + rhythm.interval_minutes_median,
        MIN_SILENCE_MINUTES_FOR_CLASSIFICATION,
    )


def _silence_minutes_since(latest_observed_at: datetime, now: datetime) -> int:
    return int((now - latest_observed_at).total_seconds() // 60)


def _classify_silence(
    silence_minutes: int,
    *,
    extended_silence_threshold_minutes: int,
) -> SilenceState:
    if silence_minutes > extended_silence_threshold_minutes:
        return SilenceState.beyond_expected
    return SilenceState.within_expected


def _cadence_fields_complete(rhythm: ReportingRhythm) -> bool:
    return (
        rhythm.latest_observed_at is not None
        and rhythm.interval_minutes_p75 is not None
        and rhythm.interval_minutes_median is not None
        and rhythm.interval_minutes_max is not None
    )


def build_reporting_silence(
    rhythm: ReportingRhythm,
    *,
    now: datetime,
) -> ReportingSilence | None:
    """Classify current silence against an available reporting rhythm."""
    if rhythm.state is not ReportingRhythmState.rhythm_available:
        return None

    base_fields = {
        "subject_id": rhythm.subject_id,
        "interval_minutes_p25": rhythm.interval_minutes_p25,
        "interval_minutes_median": rhythm.interval_minutes_median,
        "interval_minutes_p75": rhythm.interval_minutes_p75,
        "interval_minutes_max": rhythm.interval_minutes_max,
        "latest_observed_at": rhythm.latest_observed_at,
    }

    if not _cadence_fields_complete(rhythm):
        return ReportingSilence(
            **base_fields,
            silence_minutes=None,
            silence_state=SilenceState.unknown,
            extended_silence_threshold_minutes=None,
        )

    threshold = _extended_silence_threshold_minutes(rhythm)
    assert threshold is not None

    if now < rhythm.latest_observed_at:  # type: ignore[operator]
        return ReportingSilence(
            **base_fields,
            silence_minutes=None,
            silence_state=SilenceState.unknown,
            extended_silence_threshold_minutes=threshold,
        )

    silence_minutes = _silence_minutes_since(rhythm.latest_observed_at, now)  # type: ignore[arg-type]
    silence_state = _classify_silence(
        silence_minutes,
        extended_silence_threshold_minutes=threshold,
    )

    return ReportingSilence(
        **base_fields,
        silence_minutes=silence_minutes,
        silence_state=silence_state,
        extended_silence_threshold_minutes=threshold,
    )
