"""Observed router-area evidence facts (Phase 4F-1).

Aggregates bounded topology, history, passive, issue, and optional HA context
around Router/Coordinator devices. Facts only — no routing, parentage, or
cause claims. Investigation cards consume these facts in later 4F slices.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from zigbeelens.storage.repository import DeviceRow, Repository

_INFRA_TYPES = {"Router", "Coordinator"}


class ObservedRouterAreaState(StrEnum):
    """Whether observed router-area facts were found for this network."""

    no_observed_areas = "no_observed_areas"
    observed_areas_available = "observed_areas_available"


class RouterAreaHAAreaContext(BaseModel):
    """Optional HA area context for already-selected router-area members."""

    matched_device_count: int
    area_count: int
    areas: dict[str, list[str]] = Field(default_factory=dict)


class ObservedRouterArea(BaseModel):
    """Bounded evidence around one Router or Coordinator."""

    area_id: str
    router_ieee: str
    latest_neighbour_ieees: list[str] = Field(default_factory=list)
    recent_missing_ieees: list[str] = Field(default_factory=list)
    last_known_ieees: list[str] = Field(default_factory=list)
    route_hint_ieees: list[str] = Field(default_factory=list)
    passive_hint_ieees: list[str] = Field(default_factory=list)
    issue_device_ieees: list[str] = Field(default_factory=list)
    member_ieees: list[str] = Field(default_factory=list)
    evidence_classes: list[str] = Field(default_factory=list)
    latest_supporting_evidence_at: str | None = None
    ha_area_context: RouterAreaHAAreaContext | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class ObservedRouterAreas(BaseModel):
    """Coded observed-router-area facts for one network."""

    subject_type: str = "network"
    subject_id: str
    state: ObservedRouterAreaState
    areas: list[ObservedRouterArea] = Field(default_factory=list)


def _norm(ieee: Any) -> str:
    return str(ieee or "").strip().lower()


def _sorted_unique(ieees: set[str]) -> list[str]:
    return sorted(ieee for ieee in ieees if ieee)


def _area_id(network_id: str, router_ieee: str) -> str:
    return f"{network_id}:{router_ieee}"


def _is_infra(ieee: str, devices_by_ieee: dict[str, DeviceRow], link_type: Any = None) -> bool:
    device = devices_by_ieee.get(ieee)
    if device is not None:
        return device.device_type in _INFRA_TYPES
    return str(link_type or "") in _INFRA_TYPES


def _other_endpoint(router: str, source: str, target: str) -> str | None:
    if source == target:
        return None
    if source == router:
        return target
    if target == router:
        return source
    return None


def _max_timestamp(current: str | None, candidate: str | None) -> str | None:
    if not candidate:
        return current
    if not current:
        return candidate
    return max(current, candidate)


@dataclass
class _AreaAccumulator:
    latest_neighbours: set[str] = field(default_factory=set)
    recent_missing: set[str] = field(default_factory=set)
    last_known: set[str] = field(default_factory=set)
    route_hints: set[str] = field(default_factory=set)
    passive_hints: set[str] = field(default_factory=set)
    evidence_classes: set[str] = field(default_factory=set)
    latest_supporting_evidence_at: str | None = None
    recent_missing_neighbor_count: int = 0
    recent_missing_route_count: int = 0
    route_hint_refs: list[dict[str, str]] = field(default_factory=list)

    def has_observed_evidence(self) -> bool:
        return bool(
            self.latest_neighbours
            or self.recent_missing
            or self.last_known
            or self.route_hints
            or self.passive_hints
        )

    def note_evidence_class(self, evidence_class: str) -> None:
        if evidence_class:
            self.evidence_classes.add(evidence_class)

    def note_timestamp(self, timestamp: str | None) -> None:
        self.latest_supporting_evidence_at = _max_timestamp(
            self.latest_supporting_evidence_at, timestamp
        )


def build_observed_router_areas(
    *,
    network_id: str,
    devices: list[DeviceRow],
    latest_links: list[dict[str, Any]],
    historical_neighbors: list[dict[str, Any]] | None = None,
    historical_routes: list[dict[str, Any]] | None = None,
    last_known_links: list[dict[str, Any]] | None = None,
    passive_hints: list[dict[str, Any]] | None = None,
    issue_device_ieees: set[str] | None = None,
    ha_area_context_by_router: dict[str, RouterAreaHAAreaContext | None] | None = None,
) -> ObservedRouterAreas:
    """Build observed router-area facts from pre-computed evidence inputs."""
    devices_by_ieee = {_norm(device.ieee_address): device for device in devices}
    issue_ids = {_norm(ieee) for ieee in (issue_device_ieees or set()) if _norm(ieee)}
    accumulators: dict[str, _AreaAccumulator] = {}

    def area_for(router: str) -> _AreaAccumulator:
        return accumulators.setdefault(router, _AreaAccumulator())

    for link in latest_links:
        source = _norm(link.get("source_ieee"))
        target = _norm(link.get("target_ieee"))
        if not source or not target or source == target:
            continue

        route_count = link.get("route_count")
        has_route_hint = route_count is not None and int(route_count) > 0

        infra_pairs: list[tuple[str, str]] = []
        if _is_infra(source, devices_by_ieee, link.get("source_type")):
            infra_pairs.append((source, target))
        if _is_infra(target, devices_by_ieee, link.get("target_type")):
            infra_pairs.append((target, source))

        for router, other in infra_pairs:
            if not other or other == router:
                continue
            acc = area_for(router)
            acc.latest_neighbours.add(other)
            acc.note_evidence_class("latest_snapshot_neighbor")
            if has_route_hint:
                acc.route_hints.add(other)
                acc.note_evidence_class("latest_snapshot_route")
                acc.route_hint_refs.append(
                    {
                        "router_ieee": router,
                        "other_ieee": other,
                        "source_ieee": source,
                        "target_ieee": target,
                    }
                )

    for edge in historical_neighbors or []:
        source = _norm(edge.get("source_ieee"))
        target = _norm(edge.get("target_ieee"))
        if not source or not target or source == target:
            continue
        timestamp = edge.get("last_seen_at") or edge.get("last_captured_at")
        for router in (source, target):
            if not _is_infra(router, devices_by_ieee):
                continue
            other = _other_endpoint(router, source, target)
            if other is None:
                continue
            acc = area_for(router)
            acc.recent_missing.add(other)
            acc.recent_missing_neighbor_count += 1
            acc.note_evidence_class("historical_neighbor")
            acc.note_timestamp(str(timestamp) if timestamp else None)

    for edge in historical_routes or []:
        source = _norm(edge.get("source_ieee"))
        target = _norm(edge.get("target_ieee"))
        if not source or not target or source == target:
            continue
        timestamp = edge.get("last_seen_at") or edge.get("last_captured_at")
        for router in (source, target):
            if not _is_infra(router, devices_by_ieee):
                continue
            other = _other_endpoint(router, source, target)
            if other is None:
                continue
            acc = area_for(router)
            acc.recent_missing.add(other)
            acc.recent_missing_route_count += 1
            acc.note_evidence_class("historical_route")
            acc.note_timestamp(str(timestamp) if timestamp else None)

    for edge in last_known_links or []:
        source = _norm(edge.get("source_ieee"))
        target = _norm(edge.get("target_ieee"))
        if not source or not target or source == target:
            continue
        timestamp = edge.get("last_reported_at")
        for router in (source, target):
            if not _is_infra(router, devices_by_ieee):
                continue
            other = _other_endpoint(router, source, target)
            if other is None:
                continue
            acc = area_for(router)
            acc.last_known.add(other)
            acc.note_evidence_class("last_known_link")
            acc.note_timestamp(str(timestamp) if timestamp else None)

    for hint in passive_hints or []:
        if hint.get("evidence_class") != "passive_derived_association":
            continue
        source = _norm(hint.get("source_ieee"))
        target = _norm(hint.get("target_ieee"))
        if not source or not target or source == target:
            continue
        timestamp = hint.get("last_seen_at")
        for router in (source, target):
            if not _is_infra(router, devices_by_ieee):
                continue
            other = _other_endpoint(router, source, target)
            if other is None:
                continue
            acc = area_for(router)
            acc.passive_hints.add(other)
            acc.note_evidence_class("passive_derived_association")
            acc.note_timestamp(str(timestamp) if timestamp else None)

    areas: list[ObservedRouterArea] = []
    ha_context = ha_area_context_by_router or {}
    for router in sorted(accumulators):
        acc = accumulators[router]
        if not acc.has_observed_evidence():
            continue

        member_union = (
            acc.latest_neighbours
            | acc.recent_missing
            | acc.last_known
            | acc.route_hints
            | acc.passive_hints
        )
        issue_members = sorted(member_union & issue_ids)
        if router in issue_ids and router not in issue_members:
            issue_members = sorted([*issue_members, router])

        areas.append(
            ObservedRouterArea(
                area_id=_area_id(network_id, router),
                router_ieee=router,
                latest_neighbour_ieees=_sorted_unique(acc.latest_neighbours),
                recent_missing_ieees=_sorted_unique(acc.recent_missing),
                last_known_ieees=_sorted_unique(acc.last_known),
                route_hint_ieees=_sorted_unique(acc.route_hints),
                passive_hint_ieees=_sorted_unique(acc.passive_hints),
                issue_device_ieees=issue_members,
                member_ieees=_sorted_unique(member_union),
                evidence_classes=sorted(acc.evidence_classes),
                latest_supporting_evidence_at=acc.latest_supporting_evidence_at,
                ha_area_context=ha_context.get(router),
                params={
                    "latest_neighbour_count": len(acc.latest_neighbours),
                    "recent_missing_count": len(acc.recent_missing),
                    "recent_missing_neighbor_count": acc.recent_missing_neighbor_count,
                    "recent_missing_route_count": acc.recent_missing_route_count,
                    "last_known_count": len(acc.last_known),
                    "route_hint_count": len(acc.route_hints),
                    "passive_hint_count": len(acc.passive_hints),
                    "issue_device_count": len(issue_members),
                    "member_count": len(member_union),
                    "route_hint_refs": sorted(
                        acc.route_hint_refs,
                        key=lambda item: (
                            item["router_ieee"],
                            item["source_ieee"],
                            item["target_ieee"],
                        ),
                    ),
                },
            )
        )

    return ObservedRouterAreas(
        subject_id=network_id,
        state=(
            ObservedRouterAreaState.observed_areas_available
            if areas
            else ObservedRouterAreaState.no_observed_areas
        ),
        areas=areas,
    )


def ha_area_context_for_members(
    repo: Repository,
    network_id: str,
    member_ieees: list[str],
) -> RouterAreaHAAreaContext | None:
    """Optional HA area context for selected router-area members."""
    from zigbeelens.enrichment.ha import area_cluster_for_devices

    if not member_ieees:
        return None
    cluster = area_cluster_for_devices(repo, network_id, member_ieees)
    matched = int(cluster.get("matched") or 0)
    if matched <= 0:
        return None
    areas = {
        str(area_name): sorted({_norm(ieee) for ieee in ieees if _norm(ieee)})
        for area_name, ieees in (cluster.get("areas") or {}).items()
    }
    return RouterAreaHAAreaContext(
        matched_device_count=matched,
        area_count=int(cluster.get("area_count") or len(areas)),
        areas=areas,
    )


def observed_router_areas_for_network(
    repo: Repository,
    network_id: str,
    *,
    devices: list[DeviceRow],
    latest_links: list[dict[str, Any]],
    history: dict[str, Any],
    last_known_links: list[dict[str, Any]],
    passive_hints: list[dict[str, Any]],
    issue_device_ieees: set[str],
) -> ObservedRouterAreas:
    """Compose observed router areas with optional HA enrichment."""
    preliminary = build_observed_router_areas(
        network_id=network_id,
        devices=devices,
        latest_links=latest_links,
        historical_neighbors=list(history.get("historical_neighbors") or []),
        historical_routes=list(history.get("historical_routes") or []),
        last_known_links=last_known_links,
        passive_hints=passive_hints,
        issue_device_ieees=issue_device_ieees,
    )
    ha_context_by_router: dict[str, RouterAreaHAAreaContext | None] = {}
    for area in preliminary.areas:
        ha_context_by_router[area.router_ieee] = ha_area_context_for_members(
            repo, network_id, area.member_ieees
        )
    return build_observed_router_areas(
        network_id=network_id,
        devices=devices,
        latest_links=latest_links,
        historical_neighbors=list(history.get("historical_neighbors") or []),
        historical_routes=list(history.get("historical_routes") or []),
        last_known_links=last_known_links,
        passive_hints=passive_hints,
        issue_device_ieees=issue_device_ieees,
        ha_area_context_by_router=ha_context_by_router,
    )
