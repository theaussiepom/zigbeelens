"""Topology-derived diagnostic enrichment helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from zigbeelens.storage.repository import Repository
from zigbeelens.topology.topics import TOPOLOGY_LIMITATION


@dataclass
class TopologyEnrichment:
    has_snapshot: bool
    snapshot_id: str | None
    captured_at: str | None
    shared_router_ieee: str | None = None
    shared_router_name: str | None = None
    linked_affected_count: int = 0
    unrelated_topology: bool = False
    limitations: list[str] | None = None


def get_latest_topology(repo: Repository, network_id: str) -> dict | None:
    return repo.get_latest_topology_snapshot(network_id)


def enrich_correlated_unavailability(
    repo: Repository,
    network_id: str,
    affected_ieees: Iterable[str],
) -> TopologyEnrichment:
    snapshot = repo.get_latest_topology_snapshot(network_id)
    if not snapshot:
        return TopologyEnrichment(
            has_snapshot=False,
            snapshot_id=None,
            captured_at=None,
            limitations=[TOPOLOGY_LIMITATION, "No topology snapshot is available"],
        )

    ieee_list = list(affected_ieees)
    parents = [_parent_routers(repo, snapshot["snapshot_id"], ieee) for ieee in ieee_list]
    parents = [p for p in parents if p]
    shared = set(parents)
    limitations = [TOPOLOGY_LIMITATION]

    if len(shared) == 1 and parents:
        router_ieee = next(iter(shared))
        router_name = repo.get_topology_node_name(snapshot["snapshot_id"], router_ieee)
        linked = sum(1 for p in parents if p == router_ieee)
        return TopologyEnrichment(
            has_snapshot=True,
            snapshot_id=snapshot["snapshot_id"],
            captured_at=snapshot["captured_at"],
            shared_router_ieee=router_ieee,
            shared_router_name=router_name,
            linked_affected_count=linked,
            limitations=limitations,
        )

    if len(shared) > 1:
        return TopologyEnrichment(
            has_snapshot=True,
            snapshot_id=snapshot["snapshot_id"],
            captured_at=snapshot["captured_at"],
            unrelated_topology=True,
            limitations=limitations,
        )

    return TopologyEnrichment(
        has_snapshot=True,
        snapshot_id=snapshot["snapshot_id"],
        captured_at=snapshot["captured_at"],
        limitations=limitations,
    )


def enrich_router_risk(
    repo: Repository,
    network_id: str,
    router_ieee: str,
    affected_ieees: Iterable[str] | None = None,
) -> TopologyEnrichment:
    snapshot = repo.get_latest_topology_snapshot(network_id)
    if not snapshot:
        return TopologyEnrichment(
            has_snapshot=False,
            snapshot_id=None,
            captured_at=None,
            limitations=[TOPOLOGY_LIMITATION, "No topology snapshot is available"],
        )

    children = repo.list_topology_children(snapshot["snapshot_id"], router_ieee)
    linked_affected = 0
    if affected_ieees is not None:
        affected = set(affected_ieees)
        linked_affected = sum(1 for c in children if c in affected)

    return TopologyEnrichment(
        has_snapshot=True,
        snapshot_id=snapshot["snapshot_id"],
        captured_at=snapshot["captured_at"],
        shared_router_ieee=router_ieee,
        shared_router_name=repo.get_topology_node_name(snapshot["snapshot_id"], router_ieee),
        linked_affected_count=linked_affected or len(children),
        limitations=[TOPOLOGY_LIMITATION],
    )


def _parent_routers(repo: Repository, snapshot_id: str, ieee: str) -> str | None:
    return repo.get_topology_parent_router(snapshot_id, ieee)
