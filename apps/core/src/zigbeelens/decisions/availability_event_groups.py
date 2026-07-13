"""Shared availability event groups from stored offline transitions (Phase 4E-1).

Surfaces network-wide co-offline windows that passive pairwise hints exclude.
Outputs coded facts only — no cause inference (Phase 4E-2/4E-3).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from zigbeelens.topology.passive_hints import (
    PASSIVE_HINT_EVENT_WINDOW_MINUTES,
    PASSIVE_HINT_LOOKBACK_DAYS,
    PASSIVE_HINT_MAX_DEVICES_PER_WINDOW,
    _cluster_windows,
    _instability_events,
)

if TYPE_CHECKING:
    from zigbeelens.storage.repository import Repository

# Windows with more devices than the passive-hint pairwise cap are network-wide.
SHARED_EVENT_MIN_DEVICES = PASSIVE_HINT_MAX_DEVICES_PER_WINDOW + 1
MAX_SHARED_EVENTS = 20


class SharedAvailabilityEventState(StrEnum):
    """Whether shared availability events were found for this network."""

    no_events = "no_events"
    events_available = "events_available"


class SharedAvailabilityEvent(BaseModel):
    """One bounded shared offline co-occurrence window."""

    event_id: str
    started_at: datetime
    ended_at: datetime
    device_count: int
    device_ieees: list[str] = Field(default_factory=list)
    duration_minutes: int = 0
    params: dict[str, Any] = Field(default_factory=dict)


class SharedAvailabilityEventGroups(BaseModel):
    """Coded shared-availability event facts for one network."""

    subject_type: str = "network"
    subject_id: str
    state: SharedAvailabilityEventState
    lookback_days: int = PASSIVE_HINT_LOOKBACK_DAYS
    event_window_minutes: int = PASSIVE_HINT_EVENT_WINDOW_MINUTES
    min_devices: int = SHARED_EVENT_MIN_DEVICES
    groups: list[SharedAvailabilityEvent] = Field(default_factory=list)


def _norm(ieee: Any) -> str:
    return str(ieee or "").strip().lower()


def _event_id(network_id: str, started_at: datetime, ended_at: datetime) -> str:
    digest = sha256(
        f"{network_id}|{started_at.isoformat()}|{ended_at.isoformat()}".encode()
    ).hexdigest()
    return f"shared-availability-{digest[:16]}"


def _duration_minutes(started_at: datetime, ended_at: datetime) -> int:
    return max(0, int((ended_at - started_at).total_seconds() // 60))


def build_shared_availability_event_groups(
    *,
    network_id: str,
    windows: list[tuple[datetime, datetime, set[str]]],
) -> SharedAvailabilityEventGroups:
    """Build shared-event facts from pre-clustered instability windows."""
    groups: list[SharedAvailabilityEvent] = []
    for started_at, ended_at, devices in windows:
        if len(devices) < SHARED_EVENT_MIN_DEVICES:
            continue
        ordered_devices = sorted(devices)
        duration_minutes = _duration_minutes(started_at, ended_at)
        groups.append(
            SharedAvailabilityEvent(
                event_id=_event_id(network_id, started_at, ended_at),
                started_at=started_at,
                ended_at=ended_at,
                device_count=len(ordered_devices),
                device_ieees=ordered_devices,
                duration_minutes=duration_minutes,
                params={
                    "device_count": len(ordered_devices),
                    "duration_minutes": duration_minutes,
                    "event_window_minutes": PASSIVE_HINT_EVENT_WINDOW_MINUTES,
                    "min_devices": SHARED_EVENT_MIN_DEVICES,
                },
            )
        )

    groups.sort(key=lambda group: (group.started_at, group.ended_at), reverse=True)
    groups = groups[:MAX_SHARED_EVENTS]

    return SharedAvailabilityEventGroups(
        subject_id=network_id,
        state=(
            SharedAvailabilityEventState.events_available
            if groups
            else SharedAvailabilityEventState.no_events
        ),
        groups=groups,
    )


def shared_availability_event_groups_for_network(
    repo: Repository,
    network_id: str,
    *,
    now: datetime | None = None,
) -> SharedAvailabilityEventGroups:
    """Load stored availability transitions and group network-wide offline windows."""
    now = now or datetime.now(timezone.utc)
    known = {_norm(device.ieee_address) for device in repo.list_devices(network_id)}
    if not known:
        return SharedAvailabilityEventGroups(
            subject_id=network_id,
            state=SharedAvailabilityEventState.no_events,
        )

    cutoff = now - timedelta(days=PASSIVE_HINT_LOOKBACK_DAYS)
    events = _instability_events(repo, network_id, known, cutoff.isoformat())
    windows = _cluster_windows(events)
    return build_shared_availability_event_groups(network_id=network_id, windows=windows)
