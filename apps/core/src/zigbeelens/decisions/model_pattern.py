"""Observed model/manufacturer pattern facts (Phase 4G-1).

Groups devices with the same stored model identity and surfaces cautious
offline-in-lookback patterns when sample sizes meet conservative thresholds.
Facts only — no manufacturer blame or causal claims (Phase 4G-2/4G-3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from zigbeelens.topology.passive_hints import (
    PASSIVE_HINT_LOOKBACK_DAYS,
    _instability_events,
)

if TYPE_CHECKING:
    from zigbeelens.storage.repository import DeviceRow, Repository

MODEL_PATTERN_LOOKBACK_DAYS = PASSIVE_HINT_LOOKBACK_DAYS
MODEL_PATTERN_MIN_GROUP_SIZE = 5
MODEL_PATTERN_MIN_AFFECTED_COUNT = 3
MAX_MODEL_PATTERNS = 20


class ModelPatternSignal(StrEnum):
    """Bounded signals that can form a model pattern."""

    offline_in_lookback = "offline_in_lookback"


class ObservedModelPatternState(StrEnum):
    """Whether observed model patterns were found for this network."""

    no_patterns = "no_patterns"
    patterns_available = "patterns_available"


class ObservedModelPattern(BaseModel):
    """One cautious model/manufacturer offline pattern."""

    pattern_id: str
    manufacturer: str | None = None
    model: str
    signal: ModelPatternSignal = ModelPatternSignal.offline_in_lookback
    group_size: int
    affected_count: int
    member_ieees: list[str] = Field(default_factory=list)
    affected_ieees: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)


class ObservedModelPatterns(BaseModel):
    """Coded model-pattern facts for one network."""

    subject_type: str = "network"
    subject_id: str
    state: ObservedModelPatternState
    lookback_days: int = MODEL_PATTERN_LOOKBACK_DAYS
    min_group_size: int = MODEL_PATTERN_MIN_GROUP_SIZE
    min_affected_count: int = MODEL_PATTERN_MIN_AFFECTED_COUNT
    patterns: list[ObservedModelPattern] = Field(default_factory=list)


@dataclass(frozen=True)
class _ModelGroup:
    manufacturer: str | None
    model: str
    members: frozenset[str]


def _norm(ieee: Any) -> str:
    return str(ieee or "").strip().lower()


def _group_key(manufacturer: str | None, model: str) -> str:
    manufacturer_key = (manufacturer or "").strip().lower()
    model_key = model.strip().lower()
    return f"{manufacturer_key}|{model_key}"


def _pattern_id(
    network_id: str,
    manufacturer: str | None,
    model: str,
    signal: ModelPatternSignal,
) -> str:
    identity_key = _group_key(manufacturer, model)
    digest = sha256(
        f"{network_id}|{identity_key}|{signal.value}".encode()
    ).hexdigest()
    return f"model-pattern-{digest[:16]}"


def _group_devices_by_model(devices: list[DeviceRow]) -> dict[str, _ModelGroup]:
    groups: dict[str, _ModelGroup] = {}
    for device in devices:
        model = str(device.model or "").strip()
        if not model:
            continue
        manufacturer_raw = str(device.manufacturer or "").strip()
        manufacturer = manufacturer_raw or None
        ieee = _norm(device.ieee_address)
        if not ieee:
            continue
        key = _group_key(manufacturer, model)
        existing = groups.get(key)
        if existing is None:
            groups[key] = _ModelGroup(
                manufacturer=manufacturer,
                model=model,
                members=frozenset({ieee}),
            )
            continue
        groups[key] = _ModelGroup(
            manufacturer=existing.manufacturer,
            model=existing.model,
            members=existing.members | {ieee},
        )
    return groups


def build_observed_model_patterns(
    *,
    network_id: str,
    groups: dict[str, _ModelGroup],
    affected_ieees: set[str],
    signal: ModelPatternSignal = ModelPatternSignal.offline_in_lookback,
) -> ObservedModelPatterns:
    """Build model-pattern facts from grouped inventory and affected devices."""
    patterns: list[ObservedModelPattern] = []
    for group in groups.values():
        group_size = len(group.members)
        if group_size < MODEL_PATTERN_MIN_GROUP_SIZE:
            continue
        affected = sorted(ieee for ieee in group.members if ieee in affected_ieees)
        affected_count = len(affected)
        if affected_count < MODEL_PATTERN_MIN_AFFECTED_COUNT:
            continue
        patterns.append(
            ObservedModelPattern(
                pattern_id=_pattern_id(network_id, group.manufacturer, group.model, signal),
                manufacturer=group.manufacturer,
                model=group.model,
                signal=signal,
                group_size=group_size,
                affected_count=affected_count,
                member_ieees=sorted(group.members),
                affected_ieees=affected,
                params={
                    "group_size": group_size,
                    "affected_count": affected_count,
                    "lookback_days": MODEL_PATTERN_LOOKBACK_DAYS,
                    "min_group_size": MODEL_PATTERN_MIN_GROUP_SIZE,
                    "min_affected_count": MODEL_PATTERN_MIN_AFFECTED_COUNT,
                    "signal": signal.value,
                },
            )
        )

    patterns.sort(
        key=lambda pattern: (
            -pattern.affected_count,
            -pattern.group_size,
            pattern.model.lower(),
            (pattern.manufacturer or "").lower(),
        )
    )
    patterns = patterns[:MAX_MODEL_PATTERNS]

    return ObservedModelPatterns(
        subject_id=network_id,
        state=(
            ObservedModelPatternState.patterns_available
            if patterns
            else ObservedModelPatternState.no_patterns
        ),
        patterns=patterns,
    )


def observed_model_patterns_for_network(
    repo: Repository,
    network_id: str,
    *,
    now: datetime | None = None,
) -> ObservedModelPatterns:
    """Load stored inventory and availability transitions for model patterns."""
    devices = repo.list_devices(network_id)
    if not devices:
        return ObservedModelPatterns(
            subject_id=network_id,
            state=ObservedModelPatternState.no_patterns,
        )

    now = now or datetime.now(timezone.utc)
    known = {_norm(device.ieee_address) for device in devices}
    cutoff = now - timedelta(days=MODEL_PATTERN_LOOKBACK_DAYS)
    events = _instability_events(repo, network_id, known, cutoff.isoformat())
    affected_ieees = {ieee for _, ieee in events}
    groups = _group_devices_by_model(devices)
    return build_observed_model_patterns(
        network_id=network_id,
        groups=groups,
        affected_ieees=affected_ieees,
    )


def stored_model_identity_key(
    manufacturer: str | None, model: str | None
) -> str | None:
    """Stable stored model identity key used for exact grouping."""
    model_value = str(model or "").strip()
    if not model_value:
        return None
    manufacturer_value = str(manufacturer or "").strip() or None
    return _group_key(manufacturer_value, model_value)


def qualifying_pattern_for_device(
    patterns: list[ObservedModelPattern],
    *,
    manufacturer: str | None,
    model: str | None,
    device_ieee: str,
) -> tuple[ObservedModelPattern, bool] | None:
    """Return a qualifying pattern and whether the device was offline in lookback."""
    identity_key = stored_model_identity_key(manufacturer, model)
    device = _norm(device_ieee)
    if identity_key is None or not device:
        return None
    for pattern in patterns:
        if stored_model_identity_key(pattern.manufacturer, pattern.model) != identity_key:
            continue
        if device not in pattern.member_ieees:
            continue
        return pattern, device in pattern.affected_ieees
    return None


def latest_offline_transition_at(
    repo: Repository,
    network_id: str,
    affected_ieees: set[str],
    *,
    now: datetime | None = None,
) -> str | None:
    """Most recent offline transition among affected devices in the lookback window."""
    if not affected_ieees:
        return None
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=MODEL_PATTERN_LOOKBACK_DAYS)).isoformat()
    latest: str | None = None
    for row in repo.availability.list_availability_changes_since(network_id, cutoff):
        if row.get("to_state") != "offline":
            continue
        ieee = _norm(row.get("ieee_address"))
        if ieee not in affected_ieees:
            continue
        changed_at = row.get("changed_at")
        if not changed_at:
            continue
        if latest is None or changed_at > latest:
            latest = str(changed_at)
    return latest
