"""Device-led snapshot history for the Mesh Evidence Graph.

Whole-network snapshot diffs are rarely actionable on a large Zigbee mesh.
This module answers the useful question instead:

    For this device, does comparing the latest snapshot with earlier
    snapshots reveal anything worth checking?

It returns the recent usable snapshots for one device — per-device link and
route-hint counts, availability tracking coverage for each period, and a
comparison of each earlier snapshot against the latest with an actionable
status, plain-language reasons and practical suggested checks.

Safety rules enforced here:

- Only complete ("usable") snapshots are listed or compared.
- Statuses describe snapshot comparison only, never device health, and use
  existing issue signals only (currently reported unavailable, or linked to
  an active incident). No new issue inference, no causality.
- Absence from the latest snapshot is evidence absence, never failure.
- Route-hint differences never imply live routing changed.
- Availability coverage is stated honestly: "off" when no usable
  availability history exists, "building" when tracking appears enabled but
  started after the snapshot, "unknown" when coverage cannot be confirmed.
  Unknown values stay ``None`` — never zero, never a fake online/offline.
- Ordering is deterministic; nothing is polled, published or mutated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from zigbeelens.decisions.availability_tracking import availability_tracking_enabled_now
from zigbeelens.topology.compare import MEANINGFUL_LQI_CHANGE

if TYPE_CHECKING:
    from zigbeelens.storage.repository import DeviceRow, Repository

# Most recent usable snapshots listed for a device (latest + earlier ones).
MAX_SNAPSHOT_HISTORY = 10

# "Links changed substantially" for the watch status: at least this many
# per-device link differences (latest-only + selected-only + changed).
WATCH_LINK_DIFFERENCE_MIN = 3

# Per-device availability transitions inspected when estimating the state
# near a snapshot capture time.
_AVAILABILITY_LOOKUP_LIMIT = 500

STATUS_NO_NOTABLE_CHANGE = "no_notable_change"
STATUS_CHANGED = "changed"
STATUS_WATCH = "watch"
STATUS_WORTH_REVIEWING = "worth_reviewing"

COVERAGE_OFF = "off"
COVERAGE_BUILDING = "building"
COVERAGE_TRACKED = "tracked"
COVERAGE_UNKNOWN = "unknown"

NO_EARLIER_SNAPSHOTS_COPY = (
    "No earlier usable topology snapshots are available for this device yet."
)

CHECK_POWER = "Confirm the device is powered."
CHECK_REPORTING = "Check whether it is reporting in Zigbee2MQTT."
CHECK_ANOTHER_SNAPSHOT = (
    "Compare with another earlier snapshot to see whether this is a one-off "
    "snapshot difference."
)
CHECK_ROUTE_HINTS_CONTEXT = (
    "Treat route-hint differences as context only; they do not prove live "
    "routing changed."
)
CHECK_ENABLE_AVAILABILITY = (
    "Enable Zigbee2MQTT availability and last-seen reporting if you want "
    "offline history, passive hints and reports to include availability "
    "evidence."
)


def _norm(ieee: Any) -> str:
    return str(ieee or "").strip().lower()


def _pair_key(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((a, b)))  # type: ignore[return-value]


class DeviceSnapshotHistoryNetworkContext(BaseModel):
    """Network-scoped snapshot-history evidence loaded once for batch composition."""

    network_id: str
    usable_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    links_by_snapshot_id: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    earliest_availability_at: str | None = None
    tracking_enabled_now: bool = False


class _DeviceSnapshotEvidence:
    """Per-device link and route-hint evidence from one snapshot."""

    def __init__(self, links: list[dict[str, Any]], device: str) -> None:
        # Undirected neighbour pairs involving the device -> best recorded LQI.
        self.link_lqi: dict[tuple[str, str], int | None] = {}
        # Directed route pairs involving the device -> recorded route count.
        self.route_counts: dict[tuple[str, str], int | None] = {}
        for link in links:
            source = _norm(link["source_ieee"])
            target = _norm(link["target_ieee"])
            if not source or not target or source == target:
                continue
            if device not in (source, target):
                continue
            pair = _pair_key(source, target)
            lqi = link.get("linkquality")
            lqi_int = int(lqi) if lqi is not None else None
            existing = self.link_lqi.get(pair)
            if pair not in self.link_lqi or (
                lqi_int is not None and (existing is None or lqi_int > existing)
            ):
                self.link_lqi[pair] = lqi_int
            route_count = link.get("route_count")
            if route_count is not None and route_count > 0:
                self.route_counts[(source, target)] = int(route_count)


def _pair_counts(
    latest: dict[tuple[str, str], int | None],
    selected: dict[tuple[str, str], int | None],
    *,
    changed: int,
) -> dict[str, int]:
    latest_keys = set(latest)
    selected_keys = set(selected)
    return {
        "latest_count": len(latest_keys),
        "selected_count": len(selected_keys),
        "latest_only_count": len(latest_keys - selected_keys),
        "selected_only_count": len(selected_keys - latest_keys),
        "changed_count": changed,
    }


def _changed_links(
    latest: dict[tuple[str, str], int | None],
    selected: dict[tuple[str, str], int | None],
) -> int:
    """Shared links whose recorded LQI differs meaningfully. Only compared
    when both values were recorded — null is never zero."""
    changed = 0
    for pair in set(latest) & set(selected):
        a, b = latest[pair], selected[pair]
        if a is not None and b is not None and abs(a - b) >= MEANINGFUL_LQI_CHANGE:
            changed += 1
    return changed


def _changed_routes(
    latest: dict[tuple[str, str], int | None],
    selected: dict[tuple[str, str], int | None],
) -> int:
    changed = 0
    for pair in set(latest) & set(selected):
        if latest[pair] != selected[pair]:
            changed += 1
    return changed


def _coverage_for_snapshot(
    captured_at: str | None,
    *,
    is_latest: bool,
    tracking_enabled_now: bool,
    earliest_availability_at: str | None,
) -> str:
    """Availability tracking coverage for one snapshot period.

    Honest by construction: "off" only when no usable availability signal
    exists at all, "building" when tracking appears enabled now but the
    first recorded availability observation is after the snapshot, and
    "unknown" when coverage genuinely cannot be confirmed.
    """
    if not tracking_enabled_now:
        return COVERAGE_OFF
    if is_latest:
        return COVERAGE_TRACKED
    if earliest_availability_at is None or captured_at is None:
        return COVERAGE_UNKNOWN
    if earliest_availability_at > captured_at:
        return COVERAGE_BUILDING
    return COVERAGE_TRACKED


def _state_near_snapshot(
    changes: list[dict[str, Any]],
    captured_at: str | None,
    coverage: str,
    *,
    is_latest: bool,
    current_availability: str | None,
) -> str | None:
    """Recorded availability state around a snapshot capture, or None.

    Uses only recorded transitions at or before the capture time when the
    period was tracked. Never invents a state for untracked periods.
    """
    if coverage != COVERAGE_TRACKED:
        return None
    if is_latest:
        if current_availability in ("online", "offline"):
            return current_availability
        return None
    if captured_at is None:
        return None
    state: str | None = None
    for change in changes:  # oldest first
        if change["changed_at"] <= captured_at:
            state = change["to_state"]
        else:
            break
    if state in ("online", "offline"):
        return state
    return None


def _comparison_to_latest(
    *,
    latest_evidence: _DeviceSnapshotEvidence,
    selected_evidence: _DeviceSnapshotEvidence,
    has_current_issue: bool,
    coverage: str,
) -> dict[str, Any]:
    """Actionable comparison of one earlier snapshot against the latest.

    Statuses are about the snapshot comparison only, never device health:
    no_notable_change / changed / watch / worth_reviewing.
    """
    changed_link_count = _changed_links(latest_evidence.link_lqi, selected_evidence.link_lqi)
    link_counts = _pair_counts(
        latest_evidence.link_lqi, selected_evidence.link_lqi, changed=changed_link_count
    )
    changed_route_count = _changed_routes(
        latest_evidence.route_counts, selected_evidence.route_counts
    )
    route_counts = _pair_counts(
        latest_evidence.route_counts,
        selected_evidence.route_counts,
        changed=changed_route_count,
    )

    link_diff_total = (
        link_counts["latest_only_count"]
        + link_counts["selected_only_count"]
        + link_counts["changed_count"]
    )
    route_diff_total = (
        route_counts["latest_only_count"]
        + route_counts["selected_only_count"]
        + route_counts["changed_count"]
    )
    no_latest_links_after_selected = (
        link_counts["latest_count"] == 0 and link_counts["selected_count"] > 0
    )
    any_difference = link_diff_total > 0 or route_diff_total > 0

    reasons: list[str] = []
    checks: list[str] = []

    if no_latest_links_after_selected:
        reasons.append("Latest snapshot shows no links for this device.")
        reasons.append(
            f"The selected snapshot showed "
            f"{link_counts['selected_count']} "
            f"{'link' if link_counts['selected_count'] == 1 else 'links'}."
        )
    elif link_diff_total > 0:
        if link_counts["latest_only_count"]:
            reasons.append(
                f"{link_counts['latest_only_count']} "
                f"{'link' if link_counts['latest_only_count'] == 1 else 'links'} "
                "only in the latest snapshot."
            )
        if link_counts["selected_only_count"]:
            reasons.append(
                f"{link_counts['selected_only_count']} "
                f"{'link' if link_counts['selected_only_count'] == 1 else 'links'} "
                "only in the selected snapshot."
            )
        if link_counts["changed_count"]:
            reasons.append(
                f"{link_counts['changed_count']} "
                f"{'link' if link_counts['changed_count'] == 1 else 'links'} changed."
            )
    else:
        reasons.append("Similar number of links shown.")

    if route_diff_total > 0:
        reasons.append("Route hints differ between the two snapshots.")
    else:
        reasons.append("No route-hint change that looks relevant.")

    if has_current_issue:
        reasons.append("This device currently needs attention.")
    else:
        reasons.append("There is no current ZigbeeLens issue for this device.")

    if coverage == COVERAGE_OFF:
        reasons.append("Availability tracking was off for this period.")
    elif coverage == COVERAGE_BUILDING:
        reasons.append("Availability history does not cover this period yet.")

    # Deterministic status mapping using existing issue signals only.
    if has_current_issue and any_difference:
        status = STATUS_WORTH_REVIEWING
    elif no_latest_links_after_selected:
        status = STATUS_WATCH
    elif link_diff_total >= WATCH_LINK_DIFFERENCE_MIN:
        status = STATUS_WATCH
    elif route_diff_total > 0 and coverage != COVERAGE_TRACKED:
        status = STATUS_WATCH
    elif any_difference:
        status = STATUS_CHANGED
    else:
        status = STATUS_NO_NOTABLE_CHANGE

    if status in (STATUS_WATCH, STATUS_WORTH_REVIEWING):
        if has_current_issue:
            checks.append(CHECK_POWER)
            checks.append(CHECK_REPORTING)
        if no_latest_links_after_selected:
            checks.append(CHECK_ANOTHER_SNAPSHOT)
        if route_diff_total > 0:
            checks.append(CHECK_ROUTE_HINTS_CONTEXT)
        if coverage == COVERAGE_OFF:
            checks.append(CHECK_ENABLE_AVAILABILITY)

    return {
        "status": status,
        "reasons": reasons,
        "suggested_checks": checks,
        "link_counts": link_counts,
        "route_hint_counts": route_counts,
    }


def load_device_snapshot_history_network_context(
    repo: Repository,
    network_id: str,
    *,
    max_snapshots: int = MAX_SNAPSHOT_HISTORY,
    snapshots: list[dict[str, Any]] | None = None,
    links_by_snapshot_id: dict[str, list[dict[str, Any]]] | None = None,
    earliest_availability_at: str | None | object = None,
    earliest_availability_supplied: bool = False,
    devices: list | None = None,
) -> DeviceSnapshotHistoryNetworkContext:
    """Load network-scoped snapshot-history evidence once for a network."""
    if snapshots is not None:
        usable = [
            snapshot
            for snapshot in snapshots
            if snapshot.get("status") == "complete"
        ][:max_snapshots]
    else:
        usable = list(
            repo.list_complete_topology_snapshots(network_id, limit=max_snapshots)
        )
    resolved_links: dict[str, list[dict[str, Any]]] = {}
    missing_link_ids: list[str] = []
    for snapshot in usable:
        snapshot_id = str(snapshot["snapshot_id"])
        if links_by_snapshot_id is not None and snapshot_id in links_by_snapshot_id:
            resolved_links[snapshot_id] = links_by_snapshot_id[snapshot_id]
        else:
            missing_link_ids.append(snapshot_id)
    if missing_link_ids:
        bulk_links = repo.list_topology_links_for_snapshots(missing_link_ids)
        for snapshot_id in missing_link_ids:
            resolved_links[snapshot_id] = list(bulk_links.get(snapshot_id, []))
    if earliest_availability_supplied:
        resolved_earliest = earliest_availability_at  # may be None
    else:
        resolved_earliest = repo.availability.get_earliest_availability_change_at(
            network_id
        )
    return DeviceSnapshotHistoryNetworkContext(
        network_id=network_id,
        usable_snapshots=usable,
        links_by_snapshot_id=resolved_links,
        earliest_availability_at=resolved_earliest,  # type: ignore[arg-type]
        tracking_enabled_now=availability_tracking_enabled_now(
            repo,
            network_id,
            earliest_availability_at=resolved_earliest,
            devices=devices,
        ),
    )


def build_device_snapshot_history(
    repo: Repository,
    network_context: DeviceSnapshotHistoryNetworkContext,
    device_ieee: str,
    *,
    device_row: DeviceRow | None,
    has_current_issue: bool,
    availability_changes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build snapshot history for one device from a preloaded network context."""
    device = _norm(device_ieee)
    usable = network_context.usable_snapshots
    tracking_enabled_now = network_context.tracking_enabled_now
    earliest_availability_at = network_context.earliest_availability_at
    raw_device_changes = (
        availability_changes
        if availability_changes is not None
        else repo.availability.list_availability_changes(
            network_context.network_id,
            device_ieee,
            limit=_AVAILABILITY_LOOKUP_LIMIT,
        )
    )
    device_changes = list(reversed(raw_device_changes))  # oldest first

    def _evidence_for(snapshot_id: str) -> _DeviceSnapshotEvidence:
        links = network_context.links_by_snapshot_id.get(snapshot_id, [])
        return _DeviceSnapshotEvidence(links, device)

    latest_evidence = (
        _evidence_for(str(usable[0]["snapshot_id"])) if usable else None
    )

    snapshots: list[dict[str, Any]] = []
    for index, snapshot in enumerate(usable):
        is_latest = index == 0
        snapshot_id = str(snapshot["snapshot_id"])
        evidence = latest_evidence if is_latest else _evidence_for(snapshot_id)
        assert evidence is not None
        coverage = _coverage_for_snapshot(
            snapshot.get("captured_at"),
            is_latest=is_latest,
            tracking_enabled_now=tracking_enabled_now,
            earliest_availability_at=earliest_availability_at,
        )
        row: dict[str, Any] = {
            "snapshot_id": snapshot["snapshot_id"],
            "captured_at": snapshot.get("captured_at"),
            "is_latest": is_latest,
            "is_usable": True,
            "links_for_device_count": len(evidence.link_lqi),
            "route_hints_for_device_count": len(evidence.route_counts),
            "availability_coverage_status": coverage,
            "availability_state_near_snapshot": _state_near_snapshot(
                device_changes,
                snapshot.get("captured_at"),
                coverage,
                is_latest=is_latest,
                current_availability=device_row.availability if device_row else None,
            ),
            "comparison_to_latest": None,
        }
        if not is_latest and latest_evidence is not None:
            row["comparison_to_latest"] = _comparison_to_latest(
                latest_evidence=latest_evidence,
                selected_evidence=evidence,
                has_current_issue=has_current_issue,
                coverage=coverage,
            )
        snapshots.append(row)

    return {
        "network_id": network_context.network_id,
        "device_ieee": device_ieee,
        "friendly_name": device_row.friendly_name if device_row else None,
        "has_current_issue": has_current_issue,
        "availability_tracking": {
            "enabled": tracking_enabled_now,
            "earliest_observation_at": earliest_availability_at,
        },
        "latest_snapshot": snapshots[0] if snapshots else None,
        "snapshots": snapshots[1:],
    }


def device_snapshot_history(
    repo: Repository,
    network_id: str,
    device_ieee: str,
    *,
    max_snapshots: int = MAX_SNAPSHOT_HISTORY,
    network_context: DeviceSnapshotHistoryNetworkContext | None = None,
) -> dict[str, Any]:
    """Snapshot history for one device: recent usable snapshots with
    per-device counts, availability coverage, and a comparison of each
    earlier snapshot against the latest.

    Read-only over stored snapshots and availability history. Deterministic
    ordering (newest first). Unknown values stay None, never zero.
    """
    if network_context is None:
        network_context = load_device_snapshot_history_network_context(
            repo, network_id, max_snapshots=max_snapshots
        )
    elif network_context.network_id != network_id:
        raise ValueError(
            "DeviceSnapshotHistoryNetworkContext network_id does not match "
            "requested network_id"
        )

    device_row = repo.get_device(network_id, device_ieee)
    has_current_issue = bool(
        device_row is not None and device_row.availability == "offline"
    )
    return build_device_snapshot_history(
        repo,
        network_context,
        device_ieee,
        device_row=device_row,
        has_current_issue=has_current_issue,
    )
