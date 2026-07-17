"""Per-device diagnostic stats for the mesh evidence device details panel.

Repeatable, recorded numbers only: how often a device appeared with link
evidence in recent snapshots, when it last had a link to a router, and how
many recorded offline transitions it had recently. Values come straight from
stored snapshots and availability transitions — nothing is inferred, and a
device with no recorded data simply has no entry (unknown never becomes
zero; zero only appears for counts over data that was actually evaluated).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zigbeelens.storage.repository import Repository

# Recent complete snapshots contribute if captured within this many days,
# capped at this many snapshots (newest first). Matches the spirit of the
# recent-history window: recent context, not forever history.
DEVICE_STATS_WINDOW_DAYS = 7
DEVICE_STATS_MAX_SNAPSHOTS = 10

ROUTER_TYPES = {"Router", "Coordinator"}


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


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


def aggregate_device_stats(
    repo: Repository,
    network_id: str,
    *,
    now: datetime | None = None,
    snapshots: list[dict[str, Any]] | None = None,
    links_by_snapshot_id: dict[str, list[dict[str, Any]]] | None = None,
    availability_rows: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
) -> dict[str, Any]:
    """Diagnostic stats per device from recent snapshots and availability data.

    Returns window metadata plus a per-IEEE map with:

    - ``snapshots_with_links`` — recent complete snapshots (including the
      latest) in which the device had at least one link entry.
    - ``last_router_link_at`` / ``last_router_link_partner`` — the newest
      snapshot in the window where the device had a link whose other endpoint
      was a Router or Coordinator, and that partner's IEEE.
    - ``offline_events_24h`` / ``offline_events_7d`` / ``last_offline_at`` —
      recorded transitions to offline within the window.

    When ``snapshots``, ``links_by_snapshot_id``, and ``availability_rows`` are
    supplied (request-local evidence context), no repository reread is performed.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=DEVICE_STATS_WINDOW_DAYS)

    snapshot_rows = (
        snapshots if snapshots is not None else repo.list_topology_snapshots(network_id)
    )
    window_snapshots: list[dict[str, Any]] = []
    for snapshot in snapshot_rows:  # newest first
        if snapshot.get("status") != "complete":
            continue
        captured = _parse_ts(snapshot.get("captured_at"))
        if captured is None or captured < cutoff:
            continue
        window_snapshots.append(snapshot)
        if len(window_snapshots) >= DEVICE_STATS_MAX_SNAPSHOTS:
            break
    # Oldest first so "last router link" fields track the newest observation.
    window_snapshots.reverse()

    def _links_for(snapshot_id: str) -> list[dict[str, Any]]:
        if links_by_snapshot_id is not None and snapshot_id in links_by_snapshot_id:
            return links_by_snapshot_id[snapshot_id]
        return repo.list_topology_links(snapshot_id)

    stats: dict[str, dict[str, Any]] = {}

    def entry(ieee: str) -> dict[str, Any]:
        return stats.setdefault(
            ieee,
            {
                "snapshots_with_links": 0,
                "last_router_link_at": None,
                "last_router_link_partner": None,
                "offline_events_24h": 0,
                "offline_events_7d": 0,
                "last_offline_at": None,
            },
        )

    for snapshot in window_snapshots:
        captured_at = snapshot.get("captured_at")
        linked: set[str] = set()
        router_partner: dict[str, str] = {}
        for link in _links_for(str(snapshot["snapshot_id"])):
            source = _norm(link.get("source_ieee"))
            target = _norm(link.get("target_ieee"))
            if not source or not target or source == target:
                continue
            linked.add(source)
            linked.add(target)
            if link.get("target_type") in ROUTER_TYPES:
                router_partner[source] = target
            if link.get("source_type") in ROUTER_TYPES:
                router_partner[target] = source
        for ieee in linked:
            entry(ieee)["snapshots_with_links"] += 1
        for ieee, partner in router_partner.items():
            record = entry(ieee)
            record["last_router_link_at"] = captured_at
            record["last_router_link_partner"] = partner

    day_ago = now - timedelta(hours=24)
    change_rows = (
        list(availability_rows)
        if availability_rows is not None
        else repo.availability.list_availability_changes_since(
            network_id, cutoff.isoformat()
        )
    )
    for row in change_rows:
        if row.get("to_state") != "offline":
            continue
        changed = _parse_ts(str(row.get("changed_at")))
        if changed is not None and changed < cutoff:
            continue
        ieee = _norm(row.get("ieee_address"))
        if not ieee:
            continue
        changed_at = str(row.get("changed_at"))
        record = entry(ieee)
        record["offline_events_7d"] += 1
        if changed is not None and changed >= day_ago:
            record["offline_events_24h"] += 1
        # Transitions arrive oldest first, so each one is the newest so far.
        record["last_offline_at"] = changed_at

    return {
        "device_stats_window": {
            "days": DEVICE_STATS_WINDOW_DAYS,
            "max_snapshots": DEVICE_STATS_MAX_SNAPSHOTS,
            "snapshots_considered": len(window_snapshots),
        },
        "device_stats": stats,
    }
