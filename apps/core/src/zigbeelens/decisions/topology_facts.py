"""Topology-specific evidence facts for the decision engine.

Facts are neutral, serialisable statements derived from stored topology
evidence. They carry stable codes plus params — never final UI prose.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from zigbeelens.decisions.types import EvidenceFact
from zigbeelens.topology.device_compare import (
    COVERAGE_BUILDING,
    COVERAGE_OFF,
    COVERAGE_UNKNOWN,
    STATUS_CHANGED,
    STATUS_NO_NOTABLE_CHANGE,
    STATUS_WATCH,
    STATUS_WORTH_REVIEWING,
)

# Default age after which the latest usable snapshot is treated as stale for
# decision coverage. Matches topology.automatic_capture_interval_hours default.
DEFAULT_SNAPSHOT_STALE_AFTER_HOURS = 24


class TopologyFactCode(StrEnum):
    latest_snapshot_complete = "latest_snapshot_complete"
    latest_snapshot_missing = "latest_snapshot_missing"
    latest_snapshot_stale = "latest_snapshot_stale"
    latest_layout_limited = "latest_layout_limited"
    route_hints_available = "route_hints_available"
    route_hints_unavailable = "route_hints_unavailable"
    device_seen_in_latest_snapshot = "device_seen_in_latest_snapshot"
    device_absent_from_latest_snapshot = "device_absent_from_latest_snapshot"
    device_has_latest_links = "device_has_latest_links"
    device_no_latest_links = "device_no_latest_links"
    device_has_selected_snapshot_links = "device_has_selected_snapshot_links"
    device_latest_vs_selected_changed = "device_latest_vs_selected_changed"
    last_known_links_available = "last_known_links_available"
    recent_missing_links_available = "recent_missing_links_available"
    passive_hints_available = "passive_hints_available"
    availability_coverage_affects_snapshot_comparison = (
        "availability_coverage_affects_snapshot_comparison"
    )


TOPOLOGY_FACT_CODES: frozenset[str] = frozenset(member.value for member in TopologyFactCode)

_COMPARISON_CHANGED_STATUSES = frozenset(
    {
        STATUS_CHANGED,
        STATUS_WATCH,
        STATUS_WORTH_REVIEWING,
    }
)

_COVERAGE_AFFECTS_COMPARISON = frozenset(
    {
        COVERAGE_OFF,
        COVERAGE_BUILDING,
        COVERAGE_UNKNOWN,
    }
)


class TopologyFacts(BaseModel):
    """Grouped topology facts for one network."""

    network_id: str
    network_facts: list[EvidenceFact] = Field(default_factory=list)
    device_facts: dict[str, list[EvidenceFact]] = Field(default_factory=dict)


def _fact(code: TopologyFactCode | str, **params: Any) -> EvidenceFact:
    return EvidenceFact(code=str(code), params=params)


def _norm(ieee: Any) -> str:
    return str(ieee or "").strip().lower()


def _parse_captured_at(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _snapshot_age_hours(captured_at: Any, *, now: datetime) -> float | None:
    parsed = _parse_captured_at(captured_at)
    if parsed is None:
        return None
    return max(0.0, (now - parsed).total_seconds() / 3600.0)


def _device_link_count(device: str, links: list[dict[str, Any]]) -> int:
    count = 0
    for link in links:
        source = _norm(link.get("source_ieee"))
        target = _norm(link.get("target_ieee"))
        if not source or not target or source == target:
            continue
        if device in (source, target):
            count += 1
    return count


def _device_in_nodes(device: str, nodes: list[dict[str, Any]]) -> bool:
    return any(_norm(node.get("ieee_address")) == device for node in nodes)


def build_network_topology_facts(
    *,
    latest_snapshot: dict[str, Any] | None,
    nodes: list[dict[str, Any]],
    links: list[dict[str, Any]],
    counts: dict[str, Any] | None = None,
    now: datetime | None = None,
    stale_after_hours: int = DEFAULT_SNAPSHOT_STALE_AFTER_HOURS,
) -> list[EvidenceFact]:
    """Derive network-level topology facts from assembled graph evidence."""
    counts = counts or {}
    facts: list[EvidenceFact] = []
    reference_now = now or datetime.now(timezone.utc)

    if latest_snapshot is None:
        facts.append(_fact(TopologyFactCode.latest_snapshot_missing))
        return facts

    status = str(latest_snapshot.get("status") or "").strip().lower()
    layout_available = bool(nodes or links)

    if status == "complete" and layout_available:
        facts.append(
            _fact(
                TopologyFactCode.latest_snapshot_complete,
                snapshot_id=latest_snapshot.get("snapshot_id"),
            )
        )
    elif status == "complete" and not layout_available:
        facts.append(
            _fact(
                TopologyFactCode.latest_layout_limited,
                snapshot_id=latest_snapshot.get("snapshot_id"),
            )
        )

    age_hours = _snapshot_age_hours(latest_snapshot.get("captured_at"), now=reference_now)
    if age_hours is not None and age_hours > stale_after_hours:
        facts.append(
            _fact(
                TopologyFactCode.latest_snapshot_stale,
                age_hours=round(age_hours, 2),
                stale_after_hours=stale_after_hours,
                snapshot_id=latest_snapshot.get("snapshot_id"),
            )
        )

    route_edge_count = int(counts.get("latest_snapshot_route_edges") or 0)
    if route_edge_count > 0:
        facts.append(
            _fact(
                TopologyFactCode.route_hints_available,
                route_hint_count=route_edge_count,
            )
        )
    else:
        facts.append(_fact(TopologyFactCode.route_hints_unavailable))

    recent_missing_count = int(counts.get("recent_missing_link_count_total") or 0)
    if recent_missing_count <= 0:
        recent_missing_count = int(counts.get("historical_neighbor_edges") or 0) + int(
            counts.get("historical_route_edges") or 0
        )
    if recent_missing_count > 0:
        facts.append(
            _fact(
                TopologyFactCode.recent_missing_links_available,
                link_count=recent_missing_count,
            )
        )

    last_known_count = int(counts.get("last_known_link_count") or 0)
    if last_known_count > 0:
        facts.append(
            _fact(
                TopologyFactCode.last_known_links_available,
                link_count=last_known_count,
            )
        )

    passive_hint_count = counts.get("passive_hint_count_available")
    if passive_hint_count is None:
        passive_hint_count = counts.get("passive_hint_count_total")
    if int(passive_hint_count or 0) > 0:
        facts.append(
            _fact(
                TopologyFactCode.passive_hints_available,
                hint_count=int(passive_hint_count),
            )
        )

    return facts


def build_device_topology_facts(
    *,
    device_ieee: str,
    latest_snapshot: dict[str, Any] | None,
    nodes: list[dict[str, Any]],
    links: list[dict[str, Any]],
    selected_snapshot_row: dict[str, Any] | None = None,
) -> list[EvidenceFact]:
    """Derive device-level topology facts from latest snapshot and optional
    selected snapshot history row."""
    device = _norm(device_ieee)
    if not device:
        return []

    facts: list[EvidenceFact] = []

    if latest_snapshot is None:
        return facts

    if _device_in_nodes(device, nodes):
        facts.append(
            _fact(
                TopologyFactCode.device_seen_in_latest_snapshot,
                device_ieee=device,
                snapshot_id=latest_snapshot.get("snapshot_id"),
            )
        )
    else:
        facts.append(
            _fact(
                TopologyFactCode.device_absent_from_latest_snapshot,
                device_ieee=device,
                snapshot_id=latest_snapshot.get("snapshot_id"),
            )
        )

    latest_link_count = _device_link_count(device, links)
    if latest_link_count > 0:
        facts.append(
            _fact(
                TopologyFactCode.device_has_latest_links,
                device_ieee=device,
                link_count=latest_link_count,
            )
        )
    else:
        facts.append(
            _fact(
                TopologyFactCode.device_no_latest_links,
                device_ieee=device,
            )
        )

    if selected_snapshot_row is None:
        return facts

    selected_link_count = int(selected_snapshot_row.get("links_for_device_count") or 0)
    if selected_link_count > 0:
        facts.append(
            _fact(
                TopologyFactCode.device_has_selected_snapshot_links,
                device_ieee=device,
                snapshot_id=selected_snapshot_row.get("snapshot_id"),
                link_count=selected_link_count,
            )
        )

    comparison = selected_snapshot_row.get("comparison_to_latest")
    if isinstance(comparison, dict):
        comparison_status = comparison.get("status")
        if comparison_status in _COMPARISON_CHANGED_STATUSES:
            facts.append(
                _fact(
                    TopologyFactCode.device_latest_vs_selected_changed,
                    device_ieee=device,
                    comparison_status=comparison_status,
                    snapshot_id=selected_snapshot_row.get("snapshot_id"),
                )
            )
        elif comparison_status == STATUS_NO_NOTABLE_CHANGE:
            pass

        coverage = selected_snapshot_row.get("availability_coverage_status")
        if coverage in _COVERAGE_AFFECTS_COMPARISON:
            facts.append(
                _fact(
                    TopologyFactCode.availability_coverage_affects_snapshot_comparison,
                    device_ieee=device,
                    availability_coverage_status=coverage,
                    snapshot_id=selected_snapshot_row.get("snapshot_id"),
                )
            )

    return facts


def build_topology_facts_from_evidence_graph(
    *,
    network_id: str,
    evidence_graph: dict[str, Any],
    device_ieees: list[str] | None = None,
    device_snapshot_history: dict[str, Any] | None = None,
    now: datetime | None = None,
    stale_after_hours: int = DEFAULT_SNAPSHOT_STALE_AFTER_HOURS,
) -> TopologyFacts:
    """Build grouped topology facts from an evidence-graph payload."""
    latest_snapshot = evidence_graph.get("latest_snapshot")
    nodes = evidence_graph.get("nodes") or []
    links = evidence_graph.get("links") or []
    counts = evidence_graph.get("counts") or {}

    network_facts = build_network_topology_facts(
        latest_snapshot=latest_snapshot,
        nodes=nodes,
        links=links,
        counts=counts,
        now=now,
        stale_after_hours=stale_after_hours,
    )

    device_facts: dict[str, list[EvidenceFact]] = {}
    if not device_ieees:
        return TopologyFacts(
            network_id=network_id,
            network_facts=network_facts,
            device_facts=device_facts,
        )

    selected_row = None
    if device_snapshot_history:
        snapshots = device_snapshot_history.get("snapshots") or []
        selected_row = snapshots[0] if snapshots else None

    for ieee in device_ieees:
        device = _norm(ieee)
        if not device:
            continue
        device_facts[device] = build_device_topology_facts(
            device_ieee=device,
            latest_snapshot=latest_snapshot,
            nodes=nodes,
            links=links,
            selected_snapshot_row=selected_row,
        )

    return TopologyFacts(
        network_id=network_id,
        network_facts=network_facts,
        device_facts=device_facts,
    )
