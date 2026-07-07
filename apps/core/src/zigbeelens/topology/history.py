"""Recent missing topology evidence aggregation.

Builds "recent missing" neighbour and route evidence — links observed in
recent previous complete topology snapshots but absent from the latest one —
for the Mesh Evidence Graph.

The intent is gap-filling context ("what was seen recently before, but is not
shown in the latest snapshot?"), never a forever-history dump of everything
ever observed.

Safety rules enforced here:

- Only *complete* snapshots contribute historical evidence; failed or
  incomplete captures are ignored.
- Historical route evidence comes only from stored route-table entries
  (``route_count > 0``); it is never derived from neighbour links, LQI,
  inventory or passive observations.
- Any relationship present in the latest complete snapshot's equivalent
  evidence set is excluded — it is latest evidence, not historical.
- Unknown values stay ``None``; they are never collapsed to zero.
- If the latest snapshot layout is limited (no nodes/links), absence from the
  latest snapshot is not meaningful; every historical edge then carries an
  explicit limitation saying so.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zigbeelens.storage.repository import Repository

# Recent history window: previous complete snapshots contribute only if
# captured within this many days, capped at this many snapshots. Kept
# deliberately narrow so historical edges explain recent gaps rather than
# reconstructing forever history.
RECENT_HISTORY_WINDOW_DAYS = 7
RECENT_HISTORY_MAX_SNAPSHOTS = 3

HISTORICAL_NEIGHBOR_LIMITATION = (
    "This neighbour link was observed in a recent previous topology snapshot "
    "but is not shown in the latest usable snapshot. "
    "This does not prove current live routing."
)
HISTORICAL_NEIGHBOR_LIMITED_LIMITATION = (
    "This neighbour link was observed in a recent previous topology snapshot. "
    "The latest snapshot layout is limited, so absence from the latest graph "
    "is not meaningful by itself."
)
HISTORICAL_ROUTE_LIMITATION = (
    "Route-table evidence was observed in a recent previous topology snapshot. "
    "This does not prove current live routing."
)
NOT_IN_LATEST_LIMITATION = (
    "Not observed in the latest snapshot. This alone does not prove the link "
    "is gone or that a device has failed."
)
LATEST_LAYOUT_LIMITED_LIMITATION = (
    "The latest snapshot layout is limited, so absence from the latest graph "
    "is not meaningful by itself."
)


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


class _NeighborAccumulator:
    """Aggregate observations of one unordered neighbour pair."""

    def __init__(self) -> None:
        self.observed_count = 0
        self.snapshot_ids: set[str] = set()
        self.first_seen_at: str | None = None
        self.last_seen_at: str | None = None
        self.lqi_values: list[int] = []
        self.lqi_latest: int | None = None
        self.last_relationship: str | None = None
        self.last_snapshot_id: str | None = None
        self.last_source: str = ""
        self.last_target: str = ""

    def add(self, link: dict[str, Any], snapshot: dict[str, Any]) -> None:
        captured_at = snapshot["captured_at"]
        self.observed_count += 1
        self.snapshot_ids.add(snapshot["snapshot_id"])
        if self.first_seen_at is None:
            self.first_seen_at = captured_at
        # Snapshots are processed oldest-first, so each add is the newest so far.
        self.last_seen_at = captured_at
        self.last_snapshot_id = snapshot["snapshot_id"]
        self.last_source = _norm(link["source_ieee"])
        self.last_target = _norm(link["target_ieee"])
        if link.get("linkquality") is not None:
            self.lqi_values.append(int(link["linkquality"]))
            self.lqi_latest = int(link["linkquality"])
        if link.get("relationship") is not None:
            self.last_relationship = str(link["relationship"])


class _RouteAccumulator:
    """Aggregate route-table observations of one directed pair."""

    def __init__(self) -> None:
        self.snapshot_ids: set[str] = set()
        self.first_seen_at: str | None = None
        self.last_seen_at: str | None = None
        self.last_route_count: int | None = None
        self.last_relationship: str | None = None
        self.last_snapshot_id: str | None = None

    def add(self, link: dict[str, Any], snapshot: dict[str, Any]) -> None:
        captured_at = snapshot["captured_at"]
        self.snapshot_ids.add(snapshot["snapshot_id"])
        if self.first_seen_at is None:
            self.first_seen_at = captured_at
        self.last_seen_at = captured_at
        self.last_snapshot_id = snapshot["snapshot_id"]
        self.last_route_count = int(link["route_count"])
        if link.get("relationship") is not None:
            self.last_relationship = str(link["relationship"])


def _confidence(snapshot_count: int) -> str:
    # Historical evidence is never "high": it is absent from the latest
    # snapshot by definition. Repeated observation earns "medium".
    return "medium" if snapshot_count >= 2 else "low"


def aggregate_historical_evidence(
    repo: Repository,
    network_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Aggregate recent-missing neighbour/route evidence for a network.

    Returns history window metadata, graph-ready historical edge aggregates
    (latest-snapshot relationships excluded) and top-level limitations. The
    window is deliberately recent (RECENT_HISTORY_WINDOW_DAYS /
    RECENT_HISTORY_MAX_SNAPSHOTS) so output explains recent gaps rather than
    accumulating forever history.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RECENT_HISTORY_WINDOW_DAYS)

    latest = repo.get_latest_topology_snapshot(network_id)
    latest_snapshot_id = latest["snapshot_id"] if latest else None
    latest_links = repo.list_topology_links(latest_snapshot_id) if latest_snapshot_id else []
    latest_nodes = repo.list_topology_nodes(latest_snapshot_id) if latest_snapshot_id else []
    latest_layout_available = bool(latest_nodes or latest_links)

    latest_neighbor_pairs: set[tuple[str, str]] = set()
    latest_route_pairs: set[tuple[str, str]] = set()
    for link in latest_links:
        source = _norm(link["source_ieee"])
        target = _norm(link["target_ieee"])
        if not source or not target or source == target:
            continue
        latest_neighbor_pairs.add(tuple(sorted((source, target))))  # type: ignore[arg-type]
        route_count = link.get("route_count")
        if route_count is not None and route_count > 0:
            latest_route_pairs.add((source, target))

    # Previous complete snapshots, newest first, capped by window and count.
    candidates: list[dict[str, Any]] = []
    for snapshot in repo.list_topology_snapshots(network_id):
        if snapshot["snapshot_id"] == latest_snapshot_id:
            continue
        if snapshot.get("status") != "complete":
            continue
        captured = _parse_ts(snapshot.get("captured_at"))
        if captured is None or captured < cutoff:
            continue
        candidates.append(snapshot)
    candidates = candidates[:RECENT_HISTORY_MAX_SNAPSHOTS]
    # Process oldest-first so "last observed" fields track the newest data.
    candidates.reverse()

    neighbors: dict[tuple[str, str], _NeighborAccumulator] = {}
    routes: dict[tuple[str, str], _RouteAccumulator] = {}
    for snapshot in candidates:
        for link in repo.list_topology_links(snapshot["snapshot_id"]):
            source = _norm(link["source_ieee"])
            target = _norm(link["target_ieee"])
            if not source or not target or source == target:
                continue
            pair: tuple[str, str] = tuple(sorted((source, target)))  # type: ignore[assignment]
            neighbors.setdefault(pair, _NeighborAccumulator()).add(link, snapshot)
            route_count = link.get("route_count")
            if route_count is not None and route_count > 0:
                routes.setdefault((source, target), _RouteAccumulator()).add(link, snapshot)

    limited_extra = [LATEST_LAYOUT_LIMITED_LIMITATION] if not latest_layout_available else []
    neighbor_limitations = (
        [HISTORICAL_NEIGHBOR_LIMITATION, NOT_IN_LATEST_LIMITATION]
        if latest_layout_available
        else [HISTORICAL_NEIGHBOR_LIMITED_LIMITATION]
    )
    route_limitations = (
        [HISTORICAL_ROUTE_LIMITATION, NOT_IN_LATEST_LIMITATION]
        if latest_layout_available
        else [HISTORICAL_ROUTE_LIMITATION, LATEST_LAYOUT_LIMITED_LIMITATION]
    )

    historical_neighbors: list[dict[str, Any]] = []
    for pair, acc in sorted(neighbors.items()):
        if pair in latest_neighbor_pairs:
            continue
        snapshot_count = len(acc.snapshot_ids)
        historical_neighbors.append(
            {
                "source_ieee": acc.last_source or pair[0],
                "target_ieee": acc.last_target or pair[1],
                "evidence_class": "historical_neighbor",
                "directional": False,
                "first_seen_at": acc.first_seen_at,
                "last_seen_at": acc.last_seen_at,
                "observed_count": acc.observed_count,
                "snapshot_count": snapshot_count,
                "lqi_latest": acc.lqi_latest,
                "lqi_min": min(acc.lqi_values) if acc.lqi_values else None,
                "lqi_median": statistics.median(acc.lqi_values) if acc.lqi_values else None,
                "lqi_max": max(acc.lqi_values) if acc.lqi_values else None,
                "route_observed_count": None,
                "last_route_count": None,
                "last_relationship": acc.last_relationship,
                "last_snapshot_id": acc.last_snapshot_id,
                "last_captured_at": acc.last_seen_at,
                "not_seen_in_latest_snapshot": True,
                "latest_layout_limited": not latest_layout_available,
                "confidence": _confidence(snapshot_count),
                "limitations": list(neighbor_limitations),
            }
        )

    historical_routes: list[dict[str, Any]] = []
    for (source, target), acc in sorted(routes.items()):
        if (source, target) in latest_route_pairs:
            continue
        snapshot_count = len(acc.snapshot_ids)
        historical_routes.append(
            {
                "source_ieee": source,
                "target_ieee": target,
                "evidence_class": "historical_route",
                "directional": True,
                "first_seen_at": acc.first_seen_at,
                "last_seen_at": acc.last_seen_at,
                "observed_count": snapshot_count,
                "snapshot_count": snapshot_count,
                "lqi_latest": None,
                "lqi_min": None,
                "lqi_median": None,
                "lqi_max": None,
                "route_observed_count": snapshot_count,
                "last_route_count": acc.last_route_count,
                "last_relationship": acc.last_relationship,
                "last_snapshot_id": acc.last_snapshot_id,
                "last_captured_at": acc.last_seen_at,
                "not_seen_in_latest_snapshot": True,
                "latest_layout_limited": not latest_layout_available,
                "confidence": _confidence(snapshot_count),
                "limitations": list(route_limitations),
            }
        )

    limitations: list[str] = []
    if not candidates:
        limitations.append(
            "No previous complete topology snapshots are available in the "
            f"selected history window ({RECENT_HISTORY_WINDOW_DAYS} days, up to "
            f"{RECENT_HISTORY_MAX_SNAPSHOTS} snapshots)."
        )
    limitations.extend(limited_extra)

    return {
        "history_window": {
            "days": RECENT_HISTORY_WINDOW_DAYS,
            "max_snapshots": RECENT_HISTORY_MAX_SNAPSHOTS,
            "snapshots_considered": len(candidates),
            "earliest_captured_at": candidates[0]["captured_at"] if candidates else None,
            "latest_captured_at": candidates[-1]["captured_at"] if candidates else None,
        },
        "latest_layout_available": latest_layout_available,
        "historical_neighbors": historical_neighbors,
        "historical_routes": historical_routes,
        "limitations": limitations,
    }
