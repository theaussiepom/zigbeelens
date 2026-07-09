"""Snapshot comparison for the Mesh Evidence Graph.

Compares two usable (complete) topology snapshots and explains what changed
in calm, human language. This is an evidence comparison, never a live
routing diagnosis.

Safety rules enforced here:

- Only *complete* snapshots are compared by default; failed or incomplete
  captures never contribute.
- Route-hint changes come only from stored route-table evidence
  (``route_count > 0``); routes are never derived from neighbour links,
  LQI, inventory or passive data.
- Absence from the latest snapshot is never presented as failure: wording
  stays "not present in the latest snapshot" / "no topology evidence in the
  latest snapshot". Offline is only mentioned when the stored availability
  state actually says so.
- Unknown values stay ``None`` — LQI changes are only compared when both
  values were recorded, and nulls are never collapsed to zero.
- Ordering is deterministic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zigbeelens.storage.repository import Repository

# LQI is noisy snapshot-to-snapshot; only differences at least this large
# count as changed neighbour evidence.
MEANINGFUL_LQI_CHANGE = 20

NOT_ENOUGH_HISTORY_COPY = "There is not enough snapshot history to compare yet."
NO_CHANGES_COPY = "No meaningful topology evidence changes between these snapshots."

MISSING_NEIGHBOUR_PRACTICAL_NOTE = (
    "A neighbour link not present in the latest snapshot does not prove a "
    "failure. It can happen when devices are sleepy, temporarily unavailable, "
    "moved, or simply absent from the latest map."
)
NEW_NEIGHBOUR_PRACTICAL_NOTE = (
    "A newly observed neighbour link shows radio audibility at capture time. "
    "It does not prove current live routing."
)
CHANGED_NEIGHBOUR_PRACTICAL_NOTE = (
    "Link quality readings vary between captures. A change this large may be "
    "worth noting, but a single reading does not prove a trend."
)
ROUTE_HINT_PRACTICAL_NOTE = (
    "A changed route hint suggests different route-table evidence at capture "
    "time. It does not prove current live routing."
)
NEW_DEVICE_PRACTICAL_NOTE = (
    "A newly observed device appeared in the latest topology capture. This is "
    "point-in-time evidence, not a statement about when the device joined."
)
DEVICE_NO_EVIDENCE_PRACTICAL_NOTE = (
    "No topology evidence in the latest snapshot is not, by itself, a "
    "statement about device availability. Sleepy devices routinely age out "
    "of neighbour tables between captures."
)

# Deterministic category ordering (after the unavailable-first rule):
# route-hint changes, device topology changes, neighbour links not present
# in latest, newly observed neighbour links, changed evidence.
_CATEGORY_ORDER = {
    "new_route_hint": 1,
    "missing_route_hint": 1,
    "changed_route_hint": 1,
    "newly_observed_device": 2,
    "device_no_topology_evidence": 2,
    "missing_neighbour_link": 3,
    "new_neighbour_link": 4,
    "changed_neighbour_link": 5,
}


def _norm(ieee: Any) -> str:
    return str(ieee or "").strip().lower()


def _pair_key(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((a, b)))  # type: ignore[return-value]


def _snapshot_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "snapshot_id": snapshot["snapshot_id"],
        "captured_at": snapshot.get("captured_at"),
        "requested_by": snapshot.get("requested_by"),
        "status": snapshot.get("status"),
    }


class _SnapshotEvidence:
    """Parsed evidence from one snapshot: nodes, neighbour pairs, routes."""

    def __init__(self, repo: Repository, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot
        self.node_ieees: set[str] = set()
        self.node_names: dict[str, str] = {}
        for node in repo.list_topology_nodes(snapshot["snapshot_id"]):
            ieee = _norm(node["ieee_address"])
            if not ieee:
                continue
            self.node_ieees.add(ieee)
            if node.get("friendly_name"):
                self.node_names[ieee] = str(node["friendly_name"])

        # Undirected neighbour pairs -> best recorded LQI and relationship.
        self.neighbour_lqi: dict[tuple[str, str], int | None] = {}
        self.neighbour_relationship: dict[tuple[str, str], str | None] = {}
        # Directed route pairs -> recorded route count.
        self.route_counts: dict[tuple[str, str], int | None] = {}
        for link in repo.list_topology_links(snapshot["snapshot_id"]):
            source = _norm(link["source_ieee"])
            target = _norm(link["target_ieee"])
            if not source or not target or source == target:
                continue
            pair = _pair_key(source, target)
            lqi = link.get("linkquality")
            lqi_int = int(lqi) if lqi is not None else None
            existing = self.neighbour_lqi.get(pair)
            if pair not in self.neighbour_lqi or (
                lqi_int is not None and (existing is None or lqi_int > existing)
            ):
                self.neighbour_lqi[pair] = lqi_int
            if link.get("relationship") is not None and pair not in self.neighbour_relationship:
                self.neighbour_relationship[pair] = str(link["relationship"])
            route_count = link.get("route_count")
            if route_count is not None and route_count > 0:
                self.route_counts[(source, target)] = int(route_count)


def _usable_snapshots(repo: Repository, network_id: str) -> list[dict[str, Any]]:
    """Complete snapshots, newest first."""
    return [
        snapshot
        for snapshot in repo.list_topology_snapshots(network_id)
        if snapshot.get("status") == "complete"
    ]


def compare_snapshots(
    repo: Repository,
    network_id: str,
    *,
    base_snapshot_id: str | None = None,
    compare_snapshot_id: str | None = None,
) -> dict[str, Any]:
    """Compare two usable snapshots and describe what changed.

    ``compare_snapshot`` is the newer snapshot (default: latest usable) and
    ``base_snapshot`` the older one (default: previous usable). Only complete
    snapshots are eligible. Returns a calm, deterministic change summary; if
    there is not enough history the response says so without alarm.
    """
    usable = _usable_snapshots(repo, network_id)
    by_id = {snapshot["snapshot_id"]: snapshot for snapshot in usable}

    def _resolve(snapshot_id: str | None, default_index: int) -> dict[str, Any] | None:
        if snapshot_id is not None:
            return by_id.get(snapshot_id)
        return usable[default_index] if len(usable) > default_index else None

    compare_snapshot = _resolve(compare_snapshot_id, 0)
    base_snapshot = _resolve(base_snapshot_id, 1)

    if (
        compare_snapshot is None
        or base_snapshot is None
        or compare_snapshot["snapshot_id"] == base_snapshot["snapshot_id"]
    ):
        return {
            "network_id": network_id,
            "base_snapshot": _snapshot_summary(base_snapshot) if base_snapshot else None,
            "compare_snapshot": (
                _snapshot_summary(compare_snapshot) if compare_snapshot else None
            ),
            "comparison_window": {"usable_snapshots": len(usable)},
            "has_comparison": False,
            "summary": NOT_ENOUGH_HISTORY_COPY,
            "summary_items": [],
            "changes": [],
            "counts": _counts([]),
            "limitations": [NOT_ENOUGH_HISTORY_COPY],
        }

    base = _SnapshotEvidence(repo, base_snapshot)
    latest = _SnapshotEvidence(repo, compare_snapshot)

    devices = {
        _norm(row.ieee_address): row for row in repo.list_devices(network_id)
    }

    def name_for(ieee: str) -> str:
        row = devices.get(ieee)
        if row is not None and row.friendly_name:
            return row.friendly_name
        return latest.node_names.get(ieee) or base.node_names.get(ieee) or ieee

    def unavailable(ieee: str) -> bool:
        row = devices.get(ieee)
        return row is not None and row.availability == "offline"

    def availability_context(ieees: list[str]) -> list[str]:
        # Supporting context only: offline is stated only when the stored
        # availability state actually says offline.
        return [
            f"{name_for(ieee)} is currently reported unavailable by ZigbeeLens."
            for ieee in ieees
            if unavailable(ieee)
        ]

    changes: list[dict[str, Any]] = []

    def add_change(
        *,
        change_type: str,
        title: str,
        summary: str,
        device_ieees: list[str],
        edge_key: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        supporting_evidence: list[str] | None = None,
        practical_note: str,
        focus_edge_ids: list[str] | None = None,
    ) -> None:
        changes.append(
            {
                "id": f"{change_type}-{edge_key or '-'.join(device_ieees)}",
                "type": change_type,
                "title": title,
                "summary": summary,
                "device_ieees": device_ieees,
                "edge_key": edge_key,
                "before": before or {},
                "after": after or {},
                "supporting_evidence": [
                    *(supporting_evidence or []),
                    *availability_context(device_ieees),
                ],
                "practical_note": practical_note,
                "focus_device_ieees": device_ieees,
                "focus_edge_ids": focus_edge_ids or [],
            }
        )

    # ---- devices ---------------------------------------------------------
    for ieee in sorted(latest.node_ieees - base.node_ieees):
        add_change(
            change_type="newly_observed_device",
            title=f"{name_for(ieee)} is newly observed in topology evidence",
            summary=(
                f"{name_for(ieee)} appears in the latest snapshot but was not "
                "observed in the previous compared snapshot."
            ),
            device_ieees=[ieee],
            before={"observed_in_topology": False},
            after={"observed_in_topology": True},
            practical_note=NEW_DEVICE_PRACTICAL_NOTE,
        )
    for ieee in sorted(base.node_ieees - latest.node_ieees):
        add_change(
            change_type="device_no_topology_evidence",
            title=f"{name_for(ieee)} has no topology evidence in the latest snapshot",
            summary=(
                f"{name_for(ieee)} was observed in the previous compared snapshot "
                "but has no topology evidence in the latest snapshot."
            ),
            device_ieees=[ieee],
            before={"observed_in_topology": True},
            after={"observed_in_topology": False},
            practical_note=DEVICE_NO_EVIDENCE_PRACTICAL_NOTE,
        )

    # ---- neighbour links -------------------------------------------------
    base_pairs = set(base.neighbour_lqi)
    latest_pairs = set(latest.neighbour_lqi)
    for pair in sorted(latest_pairs - base_pairs):
        a, b = pair
        lqi = latest.neighbour_lqi[pair]
        add_change(
            change_type="new_neighbour_link",
            title=f"New neighbour link: {name_for(a)} — {name_for(b)}",
            summary=(
                "This neighbour link was observed in the latest snapshot but "
                "not in the previous compared snapshot."
            ),
            device_ieees=[a, b],
            edge_key=f"{a}|{b}",
            before={"observed": False, "lqi": None},
            after={"observed": True, "lqi": lqi},
            supporting_evidence=(
                [f"Recorded link quality (LQI) {lqi} in the latest snapshot."]
                if lqi is not None
                else []
            ),
            practical_note=NEW_NEIGHBOUR_PRACTICAL_NOTE,
            focus_edge_ids=[f"live-neighbor-{a}|{b}"],
        )
    for pair in sorted(base_pairs - latest_pairs):
        a, b = pair
        lqi = base.neighbour_lqi[pair]
        add_change(
            change_type="missing_neighbour_link",
            title=f"Neighbour link not present in the latest snapshot: "
            f"{name_for(a)} — {name_for(b)}",
            summary=(
                "This neighbour link was observed in the previous compared "
                "snapshot but is not present in the latest snapshot."
            ),
            device_ieees=[a, b],
            edge_key=f"{a}|{b}",
            before={"observed": True, "lqi": lqi},
            after={"observed": False, "lqi": None},
            supporting_evidence=(
                [f"Recorded link quality (LQI) {lqi} in the previous compared snapshot."]
                if lqi is not None
                else []
            ),
            practical_note=MISSING_NEIGHBOUR_PRACTICAL_NOTE,
            # If the recent-missing aggregation also produced this edge, the
            # UI can draw it; otherwise focus falls back to the devices.
            focus_edge_ids=[f"hist-neighbor-{a}|{b}"],
        )
    for pair in sorted(base_pairs & latest_pairs):
        before_lqi = base.neighbour_lqi[pair]
        after_lqi = latest.neighbour_lqi[pair]
        # Only compare where both values were recorded — null is never zero.
        lqi_changed = (
            before_lqi is not None
            and after_lqi is not None
            and abs(after_lqi - before_lqi) >= MEANINGFUL_LQI_CHANGE
        )
        if not lqi_changed:
            continue
        a, b = pair
        add_change(
            change_type="changed_neighbour_link",
            title=f"Changed neighbour evidence: {name_for(a)} — {name_for(b)}",
            summary=(
                f"Recorded link quality (LQI) changed from {before_lqi} to "
                f"{after_lqi} between the compared snapshots."
            ),
            device_ieees=[a, b],
            edge_key=f"{a}|{b}",
            before={"observed": True, "lqi": before_lqi},
            after={"observed": True, "lqi": after_lqi},
            practical_note=CHANGED_NEIGHBOUR_PRACTICAL_NOTE,
            focus_edge_ids=[f"live-neighbor-{a}|{b}"],
        )

    # ---- route hints (directional; route-table evidence only) -------------
    base_routes = set(base.route_counts)
    latest_routes = set(latest.route_counts)
    for source, target in sorted(latest_routes - base_routes):
        count = latest.route_counts[(source, target)]
        add_change(
            change_type="new_route_hint",
            title=f"New route hint: {name_for(source)} → {name_for(target)}",
            summary=(
                "Route-table evidence for this pair was observed in the latest "
                "snapshot but not in the previous compared snapshot."
            ),
            device_ieees=[source, target],
            edge_key=f"{source}->{target}",
            before={"route_evidence": False, "route_count": None},
            after={"route_evidence": True, "route_count": count},
            practical_note=ROUTE_HINT_PRACTICAL_NOTE,
            focus_edge_ids=[f"live-route-{source}-{target}"],
        )
    for source, target in sorted(base_routes - latest_routes):
        count = base.route_counts[(source, target)]
        add_change(
            change_type="missing_route_hint",
            title=f"Route hint not present in the latest snapshot: "
            f"{name_for(source)} → {name_for(target)}",
            summary=(
                "Route-table evidence for this pair was observed in the "
                "previous compared snapshot but is not present in the latest "
                "snapshot."
            ),
            device_ieees=[source, target],
            edge_key=f"{source}->{target}",
            before={"route_evidence": True, "route_count": count},
            after={"route_evidence": False, "route_count": None},
            practical_note=ROUTE_HINT_PRACTICAL_NOTE,
            focus_edge_ids=[f"hist-route-{source}-{target}"],
        )
    for source, target in sorted(base_routes & latest_routes):
        before_count = base.route_counts[(source, target)]
        after_count = latest.route_counts[(source, target)]
        if before_count == after_count:
            continue
        add_change(
            change_type="changed_route_hint",
            title=f"Changed route-hint evidence: {name_for(source)} → {name_for(target)}",
            summary=(
                f"Recorded route-table entries changed from {before_count} to "
                f"{after_count} between the compared snapshots."
            ),
            device_ieees=[source, target],
            edge_key=f"{source}->{target}",
            before={"route_evidence": True, "route_count": before_count},
            after={"route_evidence": True, "route_count": after_count},
            practical_note=ROUTE_HINT_PRACTICAL_NOTE,
            focus_edge_ids=[f"live-route-{source}-{target}"],
        )

    # ---- deterministic ordering -------------------------------------------
    def sort_key(change: dict[str, Any]) -> tuple[Any, ...]:
        involves_unavailable = any(unavailable(ieee) for ieee in change["device_ieees"])
        first_name = name_for(change["device_ieees"][0]) if change["device_ieees"] else ""
        first_ieee = change["device_ieees"][0] if change["device_ieees"] else ""
        return (
            0 if involves_unavailable else 1,
            _CATEGORY_ORDER.get(change["type"], 99),
            first_name,
            first_ieee,
            change["id"],
        )

    changes.sort(key=sort_key)

    counts = _counts(changes)
    summary_items = _summary_items(counts)
    summary = (
        "Compared with the previous usable snapshot, ZigbeeLens observed:"
        if summary_items
        else NO_CHANGES_COPY
    )

    return {
        "network_id": network_id,
        "base_snapshot": _snapshot_summary(base_snapshot),
        "compare_snapshot": _snapshot_summary(compare_snapshot),
        "comparison_window": {"usable_snapshots": len(usable)},
        "has_comparison": True,
        "summary": summary,
        "summary_items": summary_items,
        "changes": changes,
        "counts": counts,
        "limitations": [],
    }


def _counts(changes: list[dict[str, Any]]) -> dict[str, int]:
    def count(change_type: str) -> int:
        return sum(1 for change in changes if change["type"] == change_type)

    return {
        "newly_observed_devices": count("newly_observed_device"),
        "devices_no_topology_evidence": count("device_no_topology_evidence"),
        "new_neighbour_links": count("new_neighbour_link"),
        "neighbour_links_not_present_latest": count("missing_neighbour_link"),
        "changed_neighbour_links": count("changed_neighbour_link"),
        "new_route_hints": count("new_route_hint"),
        "route_hints_not_present_latest": count("missing_route_hint"),
        "changed_route_hints": count("changed_route_hint"),
        "total_changes": len(changes),
    }


def _summary_items(counts: dict[str, int]) -> list[str]:
    """Human bullets, one per non-zero category. Zero categories stay silent."""

    def plural(count: int, singular: str, plural_form: str) -> str:
        return singular if count == 1 else plural_form

    items: list[str] = []
    n = counts["newly_observed_devices"]
    if n:
        items.append(f"{n} newly observed {plural(n, 'device', 'devices')}")
    n = counts["devices_no_topology_evidence"]
    if n:
        items.append(
            f"{n} {plural(n, 'device', 'devices')} with no topology evidence "
            "in the latest snapshot"
        )
    n = counts["new_neighbour_links"]
    if n:
        items.append(f"{n} newly observed neighbour {plural(n, 'link', 'links')}")
    n = counts["neighbour_links_not_present_latest"]
    if n:
        items.append(
            f"{n} neighbour {plural(n, 'link', 'links')} not present in the latest snapshot"
        )
    n = counts["changed_neighbour_links"]
    if n:
        items.append(
            f"{n} neighbour {plural(n, 'link', 'links')} with changed evidence"
        )
    n = counts["new_route_hints"]
    if n:
        items.append(f"{n} new route {plural(n, 'hint', 'hints')}")
    n = counts["route_hints_not_present_latest"]
    if n:
        items.append(
            f"{n} route {plural(n, 'hint', 'hints')} not present in the latest snapshot"
        )
    n = counts["changed_route_hints"]
    if n:
        items.append(f"{n} changed route {plural(n, 'hint', 'hints')}")
    return items
