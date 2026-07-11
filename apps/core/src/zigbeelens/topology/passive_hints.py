"""Passive-derived investigation hints.

Builds cautious, explainable ``passive_derived_association`` hints for the
Mesh Evidence Graph from passive observations ZigbeeLens already stores.
A hint means only: "these devices may be worth investigating together".

Hints are never topology facts. They are not routes, not adjacency, not
proof of current connectivity, and they never identify which device is
responsible for anything.

Safety rules enforced here:

- Only passive data already stored is read (``availability_changes``,
  current device state, active incidents, existing topology snapshots).
  Nothing is polled, published or triggered.
- One weak signal never creates a hint: a pair must show repeated
  co-instability windows (Rule 1) before any hint exists.
- Topology evidence can only *corroborate* an existing passive hint
  (Rule 2); it can never create one on its own.
- Existing issue signals can only raise relevance of an existing passive
  hint (Rule 4); they never create hints and no new issue flags are derived.
- Hints are undirected and never produce route evidence.
- Network-wide instability windows (many devices at once) are excluded:
  they say something about the network, not about any device pair.
- Output is capped per node and in total so hints never become a hairball.
- Unknown values stay ``None``; they are never collapsed to zero.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from zigbeelens.topology.history import (
    RECENT_HISTORY_MAX_SNAPSHOTS,
    RECENT_HISTORY_WINDOW_DAYS,
)

if TYPE_CHECKING:
    from zigbeelens.storage.repository import Repository

# Tuning constants — deliberately conservative, not user configuration.
PASSIVE_HINT_LOOKBACK_DAYS = 7
PASSIVE_HINT_EVENT_WINDOW_MINUTES = 5
PASSIVE_HINT_MIN_REPEATED_WINDOWS = 2
# Instability windows touching more devices than this are treated as
# network-wide events and excluded: correlation across a storm carries no
# pairwise signal.
PASSIVE_HINT_MAX_DEVICES_PER_WINDOW = 10
# Defensive per-device event cap inside the lookback window so one very
# flappy device cannot dominate the analysis.
PASSIVE_HINT_MAX_EVENTS_PER_DEVICE = 200
MAX_PASSIVE_HINTS_TOTAL = 100
MAX_PASSIVE_HINTS_PER_NODE = 3

RULE_SHARED_INSTABILITY = "shared_instability_window"
RULE_TOPOLOGY_CORROBORATION = "topology_neighbourhood_corroboration"
RULE_ISSUE_RELEVANCE = "current_issue_relevance"

REASON_SHARED_INSTABILITY = "These devices repeatedly showed instability around the same time."
REASON_TOPOLOGY_CORROBORATION = (
    "Recent topology evidence also places these devices in a related router neighbourhood."
)
REASON_ISSUE_RELEVANCE = (
    "One or more of these devices currently needs attention, and recent passive "
    "observations show related instability timing."
)

# Every hint carries these limitations verbatim. No causal, route, or
# connectivity claim is ever made.
PASSIVE_HINT_LIMITATIONS = [
    "This suggestion comes from passive observations, not topology evidence. "
    "It is useful for deciding which devices to inspect together, but it should "
    "not be treated as a connection between them.",
    "This does not prove current live routing.",
]

PASSIVE_HINT_SUGGESTED_INVESTIGATION = [
    "Review both devices' recent availability history around the correlated windows.",
    "Check whether both devices share placement, power, or radio environment.",
    "If instability continues, capture a new topology snapshot for fresh mesh evidence.",
]

_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


def _norm(ieee: Any) -> str:
    return str(ieee or "").strip().lower()


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(value)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def _instability_events(
    repo: Repository, network_id: str, known: set[str], cutoff_iso: str
) -> list[tuple[datetime, str]]:
    """Offline transitions inside the lookback window for known devices.

    Only availability transitions already recorded by passive MQTT ingestion
    are read. Events per device are capped defensively at the most recent
    PASSIVE_HINT_MAX_EVENTS_PER_DEVICE.
    """
    events: list[tuple[datetime, str]] = []
    per_device: dict[str, int] = {}
    rows = repo.availability.list_availability_changes_since(network_id, cutoff_iso)
    # Rows are oldest-first; walk newest-first so the per-device cap keeps
    # the most recent events.
    for row in reversed(rows):
        if row.get("to_state") != "offline":
            continue
        ieee = _norm(row.get("ieee_address"))
        if ieee not in known:
            continue
        ts = _parse_ts(row.get("changed_at"))
        if ts is None:
            continue
        count = per_device.get(ieee, 0)
        if count >= PASSIVE_HINT_MAX_EVENTS_PER_DEVICE:
            continue
        per_device[ieee] = count + 1
        events.append((ts, ieee))
    events.sort(key=lambda item: (item[0], item[1]))
    return events


def _cluster_windows(
    events: list[tuple[datetime, str]],
) -> list[tuple[datetime, datetime, set[str]]]:
    """Group instability events into co-occurrence windows.

    Consecutive events closer than PASSIVE_HINT_EVENT_WINDOW_MINUTES chain
    into one window. Each window yields (start, end, device set).
    """
    if not events:
        return []
    gap = timedelta(minutes=PASSIVE_HINT_EVENT_WINDOW_MINUTES)
    windows: list[tuple[datetime, datetime, set[str]]] = []
    start, end = events[0][0], events[0][0]
    devices = {events[0][1]}
    for ts, ieee in events[1:]:
        if ts - end <= gap:
            end = ts
            devices.add(ieee)
        else:
            windows.append((start, end, devices))
            start, end, devices = ts, ts, {ieee}
    windows.append((start, end, devices))
    return windows


class _PairAccumulator:
    def __init__(self) -> None:
        self.window_count = 0
        self.first_seen_at: datetime | None = None
        self.last_seen_at: datetime | None = None

    def add(self, start: datetime, end: datetime) -> None:
        self.window_count += 1
        if self.first_seen_at is None or start < self.first_seen_at:
            self.first_seen_at = start
        if self.last_seen_at is None or end > self.last_seen_at:
            self.last_seen_at = end


def _topology_neighbourhoods(
    repo: Repository, network_id: str, *, now: datetime
) -> tuple[dict[str, set[str]], set[tuple[str, str]]]:
    """Router/coordinator neighbourhoods from latest + recent snapshots.

    Used strictly as corroboration for hints that already exist from passive
    rules — never to create hints. Returns per-device sets of observed
    router/coordinator neighbours plus the set of observed adjacency pairs.
    """
    cutoff = now - timedelta(days=RECENT_HISTORY_WINDOW_DAYS)
    latest = repo.get_latest_topology_snapshot(network_id)
    snapshot_ids: list[str] = []
    if latest:
        snapshot_ids.append(latest["snapshot_id"])
    previous = 0
    for snapshot in repo.list_topology_snapshots(network_id):
        if latest and snapshot["snapshot_id"] == latest["snapshot_id"]:
            continue
        if snapshot.get("status") != "complete":
            continue
        captured = _parse_ts(snapshot.get("captured_at"))
        if captured is None or captured < cutoff:
            continue
        snapshot_ids.append(snapshot["snapshot_id"])
        previous += 1
        if previous >= RECENT_HISTORY_MAX_SNAPSHOTS:
            break

    router_neighbours: dict[str, set[str]] = {}
    adjacency: set[tuple[str, str]] = set()
    infra_types = {"Router", "Coordinator"}
    for snapshot_id in snapshot_ids:
        for link in repo.list_topology_links(snapshot_id):
            source = _norm(link.get("source_ieee"))
            target = _norm(link.get("target_ieee"))
            if not source or not target or source == target:
                continue
            pair: tuple[str, str] = tuple(sorted((source, target)))  # type: ignore[assignment]
            adjacency.add(pair)
            if str(link.get("target_type")) in infra_types:
                router_neighbours.setdefault(source, set()).add(target)
            if str(link.get("source_type")) in infra_types:
                router_neighbours.setdefault(target, set()).add(source)
    return router_neighbours, adjacency


def _issue_device_ids(repo: Repository, network_id: str) -> set[str]:
    """Devices with existing issue signals: currently offline or linked to an
    active incident. Reads existing fields only — no new issue inference."""
    issues: set[str] = set()
    for device in repo.list_devices(network_id):
        if getattr(device, "availability", None) == "offline":
            issues.add(_norm(device.ieee_address))
    for ieee in repo.list_active_incident_device_addresses(network_id):
        issues.add(_norm(ieee))
    return issues


def _confidence(*, repeated: bool, corroborated: bool, issue_relevant: bool) -> str:
    # Conservative mapping: "high" needs multiple independent signals.
    if repeated and corroborated and issue_relevant:
        return "high"
    if repeated or corroborated:
        return "medium"
    return "low"


def aggregate_passive_hints(
    repo: Repository,
    network_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Aggregate passive-derived investigation hints for a network.

    Returns the hint window metadata, the number of qualifying hints, and a
    capped, deterministically ordered list of hint objects ready for the
    evidence graph API.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=PASSIVE_HINT_LOOKBACK_DAYS)

    window_meta = {
        "days": PASSIVE_HINT_LOOKBACK_DAYS,
        "event_window_minutes": PASSIVE_HINT_EVENT_WINDOW_MINUTES,
        "min_repeated_windows": PASSIVE_HINT_MIN_REPEATED_WINDOWS,
    }

    known = {_norm(device.ieee_address) for device in repo.list_devices(network_id)}
    if not known:
        return {"window": window_meta, "available_count": 0, "hints": []}

    events = _instability_events(repo, network_id, known, cutoff.isoformat())
    if not events:
        return {"window": window_meta, "available_count": 0, "hints": []}

    pairs: dict[tuple[str, str], _PairAccumulator] = {}
    for start, end, devices in _cluster_windows(events):
        if len(devices) < 2:
            continue
        if len(devices) > PASSIVE_HINT_MAX_DEVICES_PER_WINDOW:
            # Network-wide window: no pairwise signal.
            continue
        ordered = sorted(devices)
        for i, first in enumerate(ordered):
            for second in ordered[i + 1 :]:
                pairs.setdefault((first, second), _PairAccumulator()).add(start, end)

    qualifying = {
        pair: acc
        for pair, acc in pairs.items()
        if acc.window_count >= PASSIVE_HINT_MIN_REPEATED_WINDOWS
    }
    if not qualifying:
        return {"window": window_meta, "available_count": 0, "hints": []}

    # Corroboration and relevance are looked up only for pairs that already
    # earned a passive hint — they can raise confidence, never create hints.
    router_neighbours, adjacency = _topology_neighbourhoods(repo, network_id, now=now)
    issue_devices = _issue_device_ids(repo, network_id)

    hints: list[dict[str, Any]] = []
    for (first, second), acc in sorted(qualifying.items()):
        repeated = acc.window_count > PASSIVE_HINT_MIN_REPEATED_WINDOWS
        corroborated = (first, second) in adjacency or bool(
            router_neighbours.get(first, set()) & router_neighbours.get(second, set())
        )
        issue_relevant = first in issue_devices or second in issue_devices

        rules = [RULE_SHARED_INSTABILITY]
        observations = [
            f"{acc.window_count} related instability windows in the last "
            f"{PASSIVE_HINT_LOOKBACK_DAYS} days."
        ]
        if corroborated:
            rules.append(RULE_TOPOLOGY_CORROBORATION)
            observations.append(
                "Recent topology evidence also involved a related router neighbourhood."
            )
        if issue_relevant:
            rules.append(RULE_ISSUE_RELEVANCE)
            observations.append(
                "At least one of these devices is currently offline or linked to an "
                "active incident."
            )

        hints.append(
            {
                "source_ieee": first,
                "target_ieee": second,
                "evidence_class": "passive_derived_association",
                "directional": False,
                "confidence": _confidence(
                    repeated=repeated,
                    corroborated=corroborated,
                    issue_relevant=issue_relevant,
                ),
                "first_seen_at": acc.first_seen_at.isoformat() if acc.first_seen_at else None,
                "last_seen_at": acc.last_seen_at.isoformat() if acc.last_seen_at else None,
                "observed_count": acc.window_count,
                "issue_related": issue_relevant,
                "rules_matched": rules,
                "supporting_observations": observations,
                "limitations": list(PASSIVE_HINT_LIMITATIONS),
                "suggested_investigation": list(PASSIVE_HINT_SUGGESTED_INVESTIGATION),
            }
        )

    available_count = len(hints)

    capped: list[dict[str, Any]] = []
    per_node: dict[str, int] = {}
    for hint in _recency_ordered(hints):
        if len(capped) >= MAX_PASSIVE_HINTS_TOTAL:
            break
        source, target = hint["source_ieee"], hint["target_ieee"]
        if (
            per_node.get(source, 0) >= MAX_PASSIVE_HINTS_PER_NODE
            or per_node.get(target, 0) >= MAX_PASSIVE_HINTS_PER_NODE
        ):
            continue
        capped.append(hint)
        per_node[source] = per_node.get(source, 0) + 1
        per_node[target] = per_node.get(target, 0) + 1

    return {"window": window_meta, "available_count": available_count, "hints": capped}


def _recency_ordered(hints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order by confidence desc, issue relevance desc, recency desc, pair asc."""
    return sorted(
        hints,
        key=lambda hint: (
            -_CONFIDENCE_RANK[hint["confidence"]],
            -int(hint["issue_related"]),
            _inverse_ts(hint["last_seen_at"]),
            hint["source_ieee"],
            hint["target_ieee"],
        ),
    )


def _inverse_ts(value: str | None) -> float:
    ts = _parse_ts(value)
    return -ts.timestamp() if ts else 0.0
