"""Problem-first investigation cards for the Mesh Evidence Graph.

Ranks, groups and explains *existing* evidence so users of large networks
know where to look first. No new evidence classes are created here: cards
are built only from evidence the graph already exposes (latest snapshot,
recent missing history, last known links, passive-derived hints) plus
existing device/incident state.

Safety rules enforced here:

- Cards are investigation priorities, never root-cause, routing, or
  parentage claims. Every card carries explicit limitations.
- Grouping by "observed router neighbourhood" uses only latest-snapshot
  adjacency; it never claims devices share a parent, route or path.
- Ranking is deterministic: named integer weights, then explicit
  tie-breaking (score desc, latest supporting evidence desc, stable card
  type order, card id).
- Nothing is polled, published, triggered or mutated; this module only
  reads aggregates the evidence-graph endpoint already computes.
- Unknown values stay ``None``; they are never collapsed to zero.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zigbeelens.storage.repository import DeviceRow, Repository

# --------------------------------------------------------------------------
# Named ranking weights. Tuning constants, not user configuration.
# --------------------------------------------------------------------------
ISSUE_DEVICE_WEIGHT = 5
UNAVAILABLE_DEVICE_WEIGHT = 5
RECENT_MISSING_EDGE_WEIGHT = 2
PASSIVE_HINT_LOW_WEIGHT = 1
PASSIVE_HINT_MEDIUM_WEIGHT = 2
PASSIVE_HINT_HIGH_WEIGHT = 3
TOPOLOGY_CORROBORATION_WEIGHT = 2
RECENCY_BOOST_WEIGHT = 1
DIAGNOSTICS_LIMITED_DEVICE_WEIGHT = 1

# Qualification thresholds — conservative so quiet networks stay quiet.
ISSUE_CLUSTER_MIN_DEVICES = 2
RECENT_MISSING_CLUSTER_MIN_EDGES = 3
PASSIVE_GROUP_MIN_HINTS = 2
DIAGNOSTICS_LIMITED_MIN_DEVICES = 3
ROUTER_REVIEW_MIN_LINKS = 8
ROUTER_REVIEW_MIN_ISSUE_NEIGHBOURS = 2

# Supporting evidence within this window earns the recency boost.
RECENCY_BOOST_HOURS = 24

MAX_INVESTIGATION_CARDS = 8
# device_ieees lists are capped so one card never dumps a whole network.
MAX_DEVICES_PER_CARD = 12

# Tailored per-device evidence: thresholds that turn stored facts (battery,
# last seen, availability history, link LQI) into card-specific supporting
# evidence and suggestions. Facts are only emitted when the underlying value
# is actually recorded — unknown never becomes a claim.
LOW_BATTERY_PERCENT = 20
WEAK_LINK_LQI = 50
STALE_LAST_SEEN_HOURS = 48
REPEATED_OFFLINE_MIN_COUNT = 2
DEVICE_EVIDENCE_LOOKBACK_DAYS = 7
# Per card, tailored evidence covers the primary device plus the most
# issue-relevant members — never every device on a big card.
MAX_TAILORED_DEVICES_PER_CARD = 3
MAX_SUGGESTED_NEXT_STEPS = 6

PRIORITY_REVIEW_FIRST = "Review first"
PRIORITY_WORTH_CHECKING = "Worth checking"
PRIORITY_CONTEXT_ONLY = "Lower priority"
REVIEW_FIRST_MIN_SCORE = 12
WORTH_CHECKING_MIN_SCORE = 6

GENERIC_INVESTIGATION_LIMITATION = (
    "This is a place to look first based on available ZigbeeLens evidence. "
    "It is not a root-cause claim and does not prove live routing or current connectivity."
)
RECENT_MISSING_LIMITATION = (
    "Recent missing links were seen in previous snapshots. That can happen if a "
    "device is sleepy, recently moved, powered off, or simply absent from the "
    "latest map — check the device before treating this as a mesh problem."
)
PASSIVE_GROUP_LIMITATION = (
    "This suggestion comes from passive observations, not topology evidence. "
    "It is useful for deciding which devices to inspect together, but it should "
    "not be treated as a connection between them."
)
DIAGNOSTICS_LIMITED_LIMITATION = (
    "The latest snapshot has limited topology evidence for some devices, so "
    "ZigbeeLens cannot tell whether their mesh relationships changed. Checking "
    "power, placement and recent movement is more useful than reading the graph "
    "as a failure."
)

# Stable card-type order used for deterministic tie-breaking.
CARD_TYPE_ORDER = (
    "issue_cluster",
    "recent_missing_cluster",
    "passive_instability_group",
    "router_neighbourhood_review",
    "diagnostics_limited_group",
)

_PASSIVE_CONFIDENCE_WEIGHT = {
    "low": PASSIVE_HINT_LOW_WEIGHT,
    "medium": PASSIVE_HINT_MEDIUM_WEIGHT,
    "high": PASSIVE_HINT_HIGH_WEIGHT,
}

_INFRA_TYPES = {"Router", "Coordinator"}


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


def _priority(score: int) -> str:
    if score >= REVIEW_FIRST_MIN_SCORE:
        return PRIORITY_REVIEW_FIRST
    if score >= WORTH_CHECKING_MIN_SCORE:
        return PRIORITY_WORTH_CHECKING
    return PRIORITY_CONTEXT_ONLY


def _recency_boost(latest_iso: str | None, now: datetime) -> int:
    ts = _parse_ts(latest_iso)
    if ts is None:
        return 0
    if now - ts <= timedelta(hours=RECENCY_BOOST_HOURS):
        return RECENCY_BOOST_WEIGHT
    return 0


def _latest_iso(values: list[str | None]) -> str | None:
    known = [value for value in values if value]
    return max(known) if known else None


# --------------------------------------------------------------------------
# Edge id scheme — must match the UI mapper (meshEvidenceLive.ts) so cards
# can reference the exact edges the graph draws. Covered by tests both sides.
# --------------------------------------------------------------------------
def _neighbor_edge_id(a: str, b: str) -> str:
    return f"live-neighbor-{'|'.join(sorted((a, b)))}"


def _route_edge_id(source: str, target: str) -> str:
    return f"live-route-{source}-{target}"


def _hist_neighbor_edge_id(a: str, b: str) -> str:
    return f"hist-neighbor-{'|'.join(sorted((a, b)))}"


def _hist_route_edge_id(source: str, target: str) -> str:
    return f"hist-route-{source}-{target}"


def _passive_edge_id(a: str, b: str) -> str:
    return f"passive-hint-{'|'.join(sorted((a, b)))}"


def _last_known_edge_id(a: str, b: str) -> str:
    return f"last-known-{'|'.join(sorted((a, b)))}"


def _name_of(devices_by_ieee: dict[str, DeviceRow], ieee: str) -> str:
    device = devices_by_ieee.get(ieee)
    return device.friendly_name if device else ieee


def _friendly_ts(value: str | None) -> str | None:
    ts = _parse_ts(value)
    if ts is None:
        return None
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _count_phrase(count: int, singular: str, plural: str | None = None) -> str:
    plural = plural or f"{singular}s"
    return f"{count} {singular if count == 1 else plural}"


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        parent = self._parent.setdefault(item, item)
        if parent == item:
            return item
        root = self.find(parent)
        self._parent[item] = root
        return root

    def union(self, a: str, b: str) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            # Deterministic root choice: lexicographically smaller wins.
            small, large = sorted((root_a, root_b))
            self._parent[large] = small


def _issue_device_ids(devices: list[DeviceRow], incident_ieees: set[str]) -> set[str]:
    """Existing issue signals only: currently offline or linked to an active
    incident. No new issue inference is derived here."""
    issues = {ieee for ieee in (_norm(i) for i in incident_ieees) if ieee}
    for device in devices:
        if device.availability == "offline":
            issues.add(_norm(device.ieee_address))
    return issues


def _router_neighbourhoods(
    latest_links: list[dict[str, Any]],
    devices_by_ieee: dict[str, DeviceRow],
) -> dict[str, set[str]]:
    """Observed router/coordinator neighbourhoods from the latest snapshot.

    Adjacency observation only — this never claims shared parentage or
    routing. A device belongs to router R's observed neighbourhood if the
    latest snapshot has any link between them.
    """
    neighbourhoods: dict[str, set[str]] = {}

    def _is_infra(ieee: str, link_type: Any) -> bool:
        device = devices_by_ieee.get(ieee)
        if device is not None:
            return device.device_type in _INFRA_TYPES
        return str(link_type) in _INFRA_TYPES

    for link in latest_links:
        source = _norm(link.get("source_ieee"))
        target = _norm(link.get("target_ieee"))
        if not source or not target or source == target:
            continue
        if _is_infra(source, link.get("source_type")):
            neighbourhoods.setdefault(source, set()).add(target)
        if _is_infra(target, link.get("target_type")):
            neighbourhoods.setdefault(target, set()).add(source)
    return neighbourhoods


def _issue_cluster_cards(
    *,
    issue_ids: set[str],
    neighbourhoods: dict[str, set[str]],
    latest_links: list[dict[str, Any]],
    devices_by_ieee: dict[str, DeviceRow],
    latest_captured_at: str | None,
    now: datetime,
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    claimed: list[frozenset[str]] = []
    # Routers with the most issue-adjacent devices first; deterministic order.
    candidates = sorted(
        neighbourhoods.items(),
        key=lambda item: (-len(item[1] & issue_ids), item[0]),
    )
    for router, neighbours in candidates:
        cluster = set(neighbours & issue_ids)
        if router in issue_ids:
            cluster.add(router)
        if len(cluster) < ISSUE_CLUSTER_MIN_DEVICES:
            continue
        frozen = frozenset(cluster)
        # Skip neighbourhoods whose issue devices are already covered by an
        # earlier (larger) cluster — one card per distinct pattern.
        if any(frozen <= existing for existing in claimed):
            continue
        claimed.append(frozen)

        edge_ids = sorted(
            {
                _neighbor_edge_id(_norm(link["source_ieee"]), _norm(link["target_ieee"]))
                for link in latest_links
                if _norm(link.get("source_ieee")) in ({router} | cluster)
                and _norm(link.get("target_ieee")) in ({router} | cluster)
                and _norm(link.get("source_ieee")) != _norm(link.get("target_ieee"))
            }
        )
        offline = [
            ieee for ieee in cluster if devices_by_ieee.get(ieee)
            and devices_by_ieee[ieee].availability == "offline"
        ]
        score = (
            ISSUE_DEVICE_WEIGHT * len(cluster)
            + TOPOLOGY_CORROBORATION_WEIGHT
            + _recency_boost(latest_captured_at, now)
        )
        router_name = _name_of(devices_by_ieee, router)
        supporting = [
            f"{_count_phrase(len(cluster), 'device')} needing attention have recent "
            f"evidence near the observed neighbourhood of {router_name}.",
        ]
        if offline:
            supporting.append(
                f"{_count_phrase(len(offline), 'device is', 'devices are')} currently offline."
            )
        supporting.append(
            "Latest topology evidence places these devices in a related observed "
            "neighbourhood."
        )
        cards.append(
            {
                "id": f"issue-cluster-{router}",
                "type": "issue_cluster",
                "priority": _priority(score),
                "score": score,
                "title": "Devices needing attention share an observed neighbourhood",
                "summary": (
                    f"{_count_phrase(len(cluster), 'device')} needing attention have "
                    f"recent evidence near the same observed router neighbourhood "
                    f"({router_name})."
                ),
                "why_it_matters": (
                    "This may be worth investigating as a local mesh, power, placement "
                    "or interference pattern rather than several unrelated faults."
                ),
                "supporting_evidence": supporting,
                "limitations": [GENERIC_INVESTIGATION_LIMITATION],
                "suggested_next_steps": [
                    "Check whether nearby router devices are powered.",
                    "Check physical placement and whether anything changed recently.",
                    "Review recent incidents involving these devices.",
                    "Select a device in the graph to inspect its evidence details.",
                ],
                "device_ieees": sorted(cluster | {router})[:MAX_DEVICES_PER_CARD],
                "edge_ids": edge_ids,
                "primary_device_ieee": None,
                "primary_neighbourhood_ieee": router,
                "created_from_evidence_classes": ["latest_snapshot_neighbor"],
                "latest_supporting_evidence_at": latest_captured_at,
            }
        )
    return cards


def _recent_missing_cluster_cards(
    *,
    history: dict[str, Any],
    issue_ids: set[str],
    devices_by_ieee: dict[str, DeviceRow],
    now: datetime,
) -> list[dict[str, Any]]:
    missing_edges = list(history.get("historical_neighbors") or []) + list(
        history.get("historical_routes") or []
    )
    if not missing_edges:
        return []

    per_device: dict[str, list[dict[str, Any]]] = {}
    for edge in missing_edges:
        for endpoint in (_norm(edge["source_ieee"]), _norm(edge["target_ieee"])):
            per_device.setdefault(endpoint, []).append(edge)

    cards: list[dict[str, Any]] = []
    for device, edges in sorted(per_device.items()):
        if len(edges) < RECENT_MISSING_CLUSTER_MIN_EDGES:
            continue
        latest_seen = _latest_iso([edge.get("last_seen_at") for edge in edges])
        score = (
            RECENT_MISSING_EDGE_WEIGHT * len(edges)
            + (ISSUE_DEVICE_WEIGHT if device in issue_ids else 0)
            + _recency_boost(latest_seen, now)
        )
        partners = sorted(
            {
                _norm(edge["target_ieee"]) if _norm(edge["source_ieee"]) == device
                else _norm(edge["source_ieee"])
                for edge in edges
            }
        )
        edge_ids = sorted(
            {
                _hist_route_edge_id(_norm(e["source_ieee"]), _norm(e["target_ieee"]))
                if e.get("evidence_class") == "historical_route"
                else _hist_neighbor_edge_id(_norm(e["source_ieee"]), _norm(e["target_ieee"]))
                for e in edges
            }
        )
        name = _name_of(devices_by_ieee, device)
        supporting = [
            f"{_count_phrase(len(edges), 'recent missing link')} involve {name}.",
        ]
        if latest_seen:
            supporting.append(f"Last seen in topology evidence at {latest_seen}.")
        if device in issue_ids:
            supporting.append(
                "This device is currently offline or linked to an active incident."
            )
        cards.append(
            {
                "id": f"recent-missing-{device}",
                "type": "recent_missing_cluster",
                "priority": _priority(score),
                "score": score,
                "title": f"Several recent missing links involve {name}",
                "summary": (
                    f"{name} has {_count_phrase(len(edges), 'link')} that were seen "
                    "recently but are not present in the latest usable snapshot."
                ),
                "why_it_matters": (
                    "This does not prove a failure, but it may be worth checking if "
                    "the device has moved, lost power, or has weak mesh conditions."
                ),
                "supporting_evidence": supporting,
                "limitations": [
                    GENERIC_INVESTIGATION_LIMITATION,
                    RECENT_MISSING_LIMITATION,
                ],
                "suggested_next_steps": [
                    "Check device power.",
                    "Check whether the device was recently moved.",
                    "Compare with latest topology snapshot evidence.",
                    "Select the device to inspect its evidence details.",
                ],
                "device_ieees": sorted({device, *partners})[:MAX_DEVICES_PER_CARD],
                "edge_ids": edge_ids,
                "primary_device_ieee": device,
                "primary_neighbourhood_ieee": None,
                "created_from_evidence_classes": sorted(
                    {str(edge.get("evidence_class")) for edge in edges}
                ),
                "latest_supporting_evidence_at": latest_seen,
            }
        )
    return cards


def _passive_group_cards(
    *,
    passive_hints: list[dict[str, Any]],
    issue_ids: set[str],
    now: datetime,
) -> list[dict[str, Any]]:
    if not passive_hints:
        return []
    union = _UnionFind()
    for hint in passive_hints:
        union.union(_norm(hint["source_ieee"]), _norm(hint["target_ieee"]))

    groups: dict[str, list[dict[str, Any]]] = {}
    for hint in passive_hints:
        groups.setdefault(union.find(_norm(hint["source_ieee"])), []).append(hint)

    cards: list[dict[str, Any]] = []
    for root, hints in sorted(groups.items()):
        strong = any(hint.get("confidence") in {"medium", "high"} for hint in hints)
        if len(hints) < PASSIVE_GROUP_MIN_HINTS and not strong:
            continue
        members = sorted(
            {_norm(h["source_ieee"]) for h in hints}
            | {_norm(h["target_ieee"]) for h in hints}
        )
        corroborated = any(
            "topology_neighbourhood_corroboration" in (hint.get("rules_matched") or [])
            for hint in hints
        )
        issue_members = [ieee for ieee in members if ieee in issue_ids]
        latest_seen = _latest_iso([hint.get("last_seen_at") for hint in hints])
        score = (
            sum(
                _PASSIVE_CONFIDENCE_WEIGHT.get(str(hint.get("confidence")), 0)
                for hint in hints
            )
            + ISSUE_DEVICE_WEIGHT * len(issue_members)
            + (TOPOLOGY_CORROBORATION_WEIGHT if corroborated else 0)
            + _recency_boost(latest_seen, now)
        )
        supporting = [
            f"{_count_phrase(len(hints), 'passive investigation hint')} connect "
            f"{_count_phrase(len(members), 'device')} in this group.",
        ]
        if corroborated:
            supporting.append(
                "Recent topology evidence also involved a related observed "
                "neighbourhood."
            )
        if issue_members:
            supporting.append(
                f"{_count_phrase(len(issue_members), 'device is', 'devices are')} "
                "currently offline or linked to an active incident."
            )
        if latest_seen:
            supporting.append(f"Last related passive observation at {latest_seen}.")
        cards.append(
            {
                "id": f"passive-group-{root}",
                "type": "passive_instability_group",
                "priority": _priority(score),
                "score": score,
                "title": "Devices repeatedly went offline around the same time",
                "summary": (
                    f"{_count_phrase(len(members), 'device')} showed repeated related "
                    "offline timing in passive observations."
                ),
                "why_it_matters": (
                    "This is not topology evidence, but it may be worth investigating "
                    "these devices together — for example shared power, placement or "
                    "radio environment."
                ),
                "supporting_evidence": supporting,
                "limitations": [
                    GENERIC_INVESTIGATION_LIMITATION,
                    PASSIVE_GROUP_LIMITATION,
                ],
                "suggested_next_steps": [
                    "Review recent incidents around the correlated windows.",
                    "Check whether these devices share placement or power.",
                    "Check battery level if available.",
                    "Select a device to inspect its evidence details.",
                ],
                "device_ieees": members[:MAX_DEVICES_PER_CARD],
                "edge_ids": sorted(
                    _passive_edge_id(_norm(h["source_ieee"]), _norm(h["target_ieee"]))
                    for h in hints
                ),
                "primary_device_ieee": None,
                "primary_neighbourhood_ieee": None,
                "created_from_evidence_classes": ["passive_derived_association"],
                "latest_supporting_evidence_at": latest_seen,
            }
        )
    return cards


def _router_review_cards(
    *,
    issue_ids: set[str],
    neighbourhoods: dict[str, set[str]],
    latest_links: list[dict[str, Any]],
    devices_by_ieee: dict[str, DeviceRow],
    latest_captured_at: str | None,
    now: datetime,
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for router, neighbours in sorted(neighbourhoods.items()):
        device = devices_by_ieee.get(router)
        if device is not None and device.device_type not in _INFRA_TYPES:
            continue
        if len(neighbours) < ROUTER_REVIEW_MIN_LINKS:
            continue
        issue_neighbours = sorted(neighbours & issue_ids)
        if len(issue_neighbours) < ROUTER_REVIEW_MIN_ISSUE_NEIGHBOURS:
            continue
        score = (
            ISSUE_DEVICE_WEIGHT * len(issue_neighbours)
            + TOPOLOGY_CORROBORATION_WEIGHT
            + (UNAVAILABLE_DEVICE_WEIGHT if router in issue_ids else 0)
            + _recency_boost(latest_captured_at, now)
        )
        name = _name_of(devices_by_ieee, router)
        edge_ids = sorted(
            _neighbor_edge_id(router, neighbour) for neighbour in issue_neighbours
        )
        cards.append(
            {
                "id": f"router-review-{router}",
                "type": "router_neighbourhood_review",
                "priority": _priority(score),
                "score": score,
                "title": f"Busy router worth reviewing: {name}",
                "summary": (
                    f"{name} appears in many observed topology relationships "
                    f"({_count_phrase(len(neighbours), 'observed neighbour')}) and has "
                    f"{_count_phrase(len(issue_neighbours), 'issue-adjacent device')} "
                    "nearby in the evidence graph."
                ),
                "why_it_matters": (
                    "It may be worth checking power, placement, firmware and whether "
                    "it is a reliable repeater. This is an observation about evidence "
                    "concentration, not a claim that this router is responsible."
                ),
                "supporting_evidence": [
                    f"{_count_phrase(len(neighbours), 'observed neighbour')} in the "
                    "latest snapshot.",
                    f"{_count_phrase(len(issue_neighbours), 'device')} needing "
                    "attention in its observed neighbourhood.",
                ],
                "limitations": [GENERIC_INVESTIGATION_LIMITATION],
                "suggested_next_steps": [
                    "Check device power and placement.",
                    "Check whether nearby router devices are powered.",
                    "Review recent incidents involving nearby devices.",
                    "Select the router to inspect its evidence details.",
                ],
                "device_ieees": sorted({router, *issue_neighbours})[:MAX_DEVICES_PER_CARD],
                "edge_ids": edge_ids,
                "primary_device_ieee": router,
                "primary_neighbourhood_ieee": router,
                "created_from_evidence_classes": ["latest_snapshot_neighbor"],
                "latest_supporting_evidence_at": latest_captured_at,
            }
        )
    return cards


def _diagnostics_limited_card(
    *,
    devices: list[DeviceRow],
    latest_nodes: list[dict[str, Any]],
    latest_links: list[dict[str, Any]],
    latest_layout_available: bool,
    latest_captured_at: str | None,
) -> list[dict[str, Any]]:
    if not latest_layout_available:
        # Absence from a limited snapshot is not meaningful; say nothing.
        return []
    observed = {_norm(node.get("ieee_address")) for node in latest_nodes}
    for link in latest_links:
        observed.add(_norm(link.get("source_ieee")))
        observed.add(_norm(link.get("target_ieee")))

    missing = sorted(
        _norm(device.ieee_address)
        for device in devices
        if _norm(device.ieee_address) not in observed
    )
    if len(missing) < DIAGNOSTICS_LIMITED_MIN_DEVICES:
        return []
    battery_count = sum(
        1
        for device in devices
        if _norm(device.ieee_address) in missing and device.power_source == "Battery"
    )
    score = DIAGNOSTICS_LIMITED_DEVICE_WEIGHT * len(missing)
    supporting = [
        f"{_count_phrase(len(missing), 'known device')} have no topology evidence "
        "in the latest snapshot.",
    ]
    if battery_count:
        supporting.append(
            f"{_count_phrase(battery_count, 'of them is', 'of them are')} "
            "battery powered, which commonly limits topology evidence."
        )
    return [
        {
            "id": "diagnostics-limited-group",
            "type": "diagnostics_limited_group",
            "priority": PRIORITY_CONTEXT_ONLY,
            "score": score,
            "title": "Known devices with limited topology evidence",
            "summary": (
                f"{_count_phrase(len(missing), 'known device')} have limited topology "
                "evidence in the latest snapshot."
            ),
            "why_it_matters": (
                "This can happen with sleepy devices or limited map data, and does "
                "not prove a fault. It mainly limits mesh context for these devices."
            ),
            "supporting_evidence": supporting,
            "limitations": [
                GENERIC_INVESTIGATION_LIMITATION,
                DIAGNOSTICS_LIMITED_LIMITATION,
            ],
            "suggested_next_steps": [
                "Check battery level if available.",
                "Select a device to inspect its evidence details.",
                "Compare with latest topology snapshot evidence.",
            ],
            "device_ieees": missing[:MAX_DEVICES_PER_CARD],
            "edge_ids": [],
            "primary_device_ieee": None,
            "primary_neighbourhood_ieee": None,
            "created_from_evidence_classes": [],
            "latest_supporting_evidence_at": latest_captured_at,
        }
    ]


def _best_link_lqi(latest_links: list[dict[str, Any]]) -> dict[str, int]:
    """Strongest recorded LQI per device across latest-snapshot links.

    Devices whose links all lack an LQI reading are simply absent — unknown
    stays unknown, it never becomes zero.
    """
    best: dict[str, int] = {}
    for link in latest_links:
        lqi = link.get("linkquality")
        if lqi is None:
            continue
        for endpoint in (_norm(link.get("source_ieee")), _norm(link.get("target_ieee"))):
            if not endpoint:
                continue
            if endpoint not in best or int(lqi) > best[endpoint]:
                best[endpoint] = int(lqi)
    return best


def _tailored_device_evidence(
    ieee: str,
    *,
    devices_by_ieee: dict[str, DeviceRow],
    offline_events: dict[str, list[str]],
    best_lqi: dict[str, int],
    now: datetime,
) -> tuple[list[str], list[str]]:
    """Facts and safe suggestions for one device, from stored evidence only.

    Every fact maps to a recorded value (battery level, availability state,
    availability transitions, last seen, link LQI). Nothing is inferred and
    unknown values produce no output.
    """
    device = devices_by_ieee.get(ieee)
    if device is None:
        return [], []
    name = device.friendly_name
    facts: list[str] = []
    suggestions: list[str] = []

    battery = device.battery
    if battery is not None and battery <= LOW_BATTERY_PERCENT:
        facts.append(f"{name}'s last reported battery level is {battery}%.")
        suggestions.append(
            f"Check or replace the battery in {name} first — it last reported {battery}%."
        )

    if device.availability == "offline":
        facts.append(f"{name} is currently reported offline.")
        suggestions.append(f"Check power to {name} — it is currently reported offline.")

    events = offline_events.get(ieee) or []
    if len(events) >= REPEATED_OFFLINE_MIN_COUNT:
        last_event = _friendly_ts(events[-1]) or events[-1]
        facts.append(
            f"{name} went offline {len(events)} times in the last "
            f"{DEVICE_EVIDENCE_LOOKBACK_DAYS} days (most recently {last_event})."
        )
        suggestions.append(
            f"Review {name}'s availability history — repeated offline periods can "
            "point to unstable power or weak radio conditions."
        )

    last_seen = _parse_ts(device.last_seen)
    if last_seen is not None and now - last_seen >= timedelta(hours=STALE_LAST_SEEN_HOURS):
        seen_text = _friendly_ts(device.last_seen) or str(device.last_seen)
        facts.append(f"Nothing has been heard from {name} since {seen_text}.")
        suggestions.append(
            f"Check whether {name} is still powered and in place — it has been "
            f"quiet since {seen_text}."
        )

    lqi = best_lqi.get(ieee)
    if lqi is not None and lqi < WEAK_LINK_LQI:
        facts.append(
            f"{name}'s strongest observed link in the latest snapshot is weak (LQI {lqi})."
        )
        suggestions.append(
            f"Check placement or sources of interference near {name} — its strongest "
            "observed link is weak."
        )

    return facts, suggestions


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _apply_tailored_evidence(
    cards: list[dict[str, Any]],
    *,
    devices_by_ieee: dict[str, DeviceRow],
    issue_ids: set[str],
    offline_events: dict[str, list[str]],
    best_lqi: dict[str, int],
    now: datetime,
) -> None:
    """Enrich cards in place with device-specific facts and suggestions.

    Tailored suggestions come first (they are actionable and specific);
    generic next steps keep the tail. The tailored device set per card is the
    primary device, then issue devices, then the rest — capped so big cards
    stay readable.
    """
    for card in cards:
        ordered: list[str] = []
        primary = card.get("primary_device_ieee")
        if primary:
            ordered.append(primary)
        members = card.get("device_ieees") or []
        for ieee in sorted(members, key=lambda i: (i not in issue_ids, i)):
            if ieee not in ordered:
                ordered.append(ieee)

        facts: list[str] = []
        suggestions: list[str] = []
        for ieee in ordered[:MAX_TAILORED_DEVICES_PER_CARD]:
            device_facts, device_suggestions = _tailored_device_evidence(
                ieee,
                devices_by_ieee=devices_by_ieee,
                offline_events=offline_events,
                best_lqi=best_lqi,
                now=now,
            )
            facts.extend(device_facts)
            suggestions.extend(device_suggestions)

        if facts:
            card["supporting_evidence"] = _dedupe(card["supporting_evidence"] + facts)
        if suggestions:
            card["suggested_next_steps"] = _dedupe(
                suggestions + card["suggested_next_steps"]
            )[:MAX_SUGGESTED_NEXT_STEPS]


def build_investigations(
    *,
    devices: list[DeviceRow],
    incident_device_ieees: set[str],
    latest_nodes: list[dict[str, Any]],
    latest_links: list[dict[str, Any]],
    latest_captured_at: str | None,
    history: dict[str, Any],
    passive_hints: list[dict[str, Any]],
    offline_events: dict[str, list[str]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build ranked investigation cards from existing evidence aggregates.

    Pure function over already-computed inputs: nothing is fetched, polled or
    mutated. Returns the full deterministic ranking capped at
    MAX_INVESTIGATION_CARDS plus the pre-cap available count.
    """
    now = now or datetime.now(timezone.utc)
    devices_by_ieee = {_norm(device.ieee_address): device for device in devices}
    issue_ids = _issue_device_ids(devices, incident_device_ieees)
    latest_layout_available = bool(latest_nodes or latest_links)
    neighbourhoods = _router_neighbourhoods(latest_links, devices_by_ieee)

    cards: list[dict[str, Any]] = []
    cards.extend(
        _issue_cluster_cards(
            issue_ids=issue_ids,
            neighbourhoods=neighbourhoods,
            latest_links=latest_links,
            devices_by_ieee=devices_by_ieee,
            latest_captured_at=latest_captured_at,
            now=now,
        )
    )
    cards.extend(
        _recent_missing_cluster_cards(
            history=history,
            issue_ids=issue_ids,
            devices_by_ieee=devices_by_ieee,
            now=now,
        )
    )
    cards.extend(
        _passive_group_cards(passive_hints=passive_hints, issue_ids=issue_ids, now=now)
    )
    cards.extend(
        _router_review_cards(
            issue_ids=issue_ids,
            neighbourhoods=neighbourhoods,
            latest_links=latest_links,
            devices_by_ieee=devices_by_ieee,
            latest_captured_at=latest_captured_at,
            now=now,
        )
    )
    cards.extend(
        _diagnostics_limited_card(
            devices=devices,
            latest_nodes=latest_nodes,
            latest_links=latest_links,
            latest_layout_available=latest_layout_available,
            latest_captured_at=latest_captured_at,
        )
    )

    _apply_tailored_evidence(
        cards,
        devices_by_ieee=devices_by_ieee,
        issue_ids=issue_ids,
        offline_events=offline_events or {},
        best_lqi=_best_link_lqi(latest_links),
        now=now,
    )

    type_rank = {card_type: index for index, card_type in enumerate(CARD_TYPE_ORDER)}
    cards.sort(
        key=lambda card: (
            -card["score"],
            # Newest supporting evidence first; unknown timestamps last.
            -(_parse_ts(card["latest_supporting_evidence_at"]) or datetime.min.replace(
                tzinfo=timezone.utc
            )).timestamp(),
            type_rank.get(card["type"], len(CARD_TYPE_ORDER)),
            card["id"],
        )
    )

    return {
        "available_count": len(cards),
        "investigations": cards[:MAX_INVESTIGATION_CARDS],
    }


def aggregate_investigations(
    repo: Repository,
    network_id: str,
    *,
    history: dict[str, Any],
    passive_hints: list[dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Gather repository inputs and build investigation cards for a network.

    The history and passive aggregates are passed in (the evidence-graph
    endpoint already computes them) so nothing is aggregated twice.
    """
    now = now or datetime.now(timezone.utc)
    latest = repo.get_latest_topology_snapshot(network_id)
    latest_snapshot_id = latest["snapshot_id"] if latest else None

    # Recorded offline transitions inside the lookback window, per device —
    # read-only passive data, used only to make card evidence concrete.
    cutoff = now - timedelta(days=DEVICE_EVIDENCE_LOOKBACK_DAYS)
    offline_events: dict[str, list[str]] = {}
    for row in repo.availability.list_availability_changes_since(network_id, cutoff.isoformat()):
        if row.get("to_state") != "offline":
            continue
        ieee = _norm(row.get("ieee_address"))
        if ieee:
            offline_events.setdefault(ieee, []).append(str(row.get("changed_at")))

    return build_investigations(
        devices=repo.list_devices(network_id),
        incident_device_ieees=set(repo.incidents.list_active_incident_device_addresses(network_id)),
        latest_nodes=repo.list_topology_nodes(latest_snapshot_id) if latest_snapshot_id else [],
        latest_links=repo.list_topology_links(latest_snapshot_id) if latest_snapshot_id else [],
        latest_captured_at=latest["captured_at"] if latest else None,
        history=history,
        passive_hints=passive_hints,
        offline_events=offline_events,
        now=now,
    )
