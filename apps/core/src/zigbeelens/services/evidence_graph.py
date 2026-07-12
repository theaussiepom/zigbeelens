"""Build mesh evidence-graph payloads from stored topology and passive evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zigbeelens.decisions.topology_facts import (
    TopologyFacts,
    build_topology_facts_from_evidence_graph,
)
from zigbeelens.topology.device_stats import aggregate_device_stats
from zigbeelens.topology.history import (
    aggregate_historical_evidence,
    aggregate_last_known_links,
)
from zigbeelens.topology.investigations import aggregate_investigations
from zigbeelens.topology.passive_hints import aggregate_passive_hints

if TYPE_CHECKING:
    from datetime import datetime

    from zigbeelens.storage.repository import Repository


class NetworkNotFoundError(LookupError):
    """Raised when evidence graph is requested for an unknown network."""


class EvidenceGraphService:
    """Orchestrate evidence-graph assembly for one network."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    def build(self, network_id: str) -> dict:
        """Graph-ready topology evidence: latest snapshot plus aggregated
        recent-missing (historical) neighbour/route evidence.

        Historical edges are aggregated backend-side from recent previous
        complete snapshots only and never duplicate relationships present in the
        latest snapshot — this is gap-filling context, not forever history.
        Last known links cover only devices with no link entries at all in the
        latest usable snapshot (typically sleepy battery devices whose entries
        aged out of router neighbour tables): each gets its most recently stored
        link evidence, clearly marked as last known rather than currently
        reported. Passive-derived investigation hints come only from passive
        observations already stored (availability transitions, existing
        incidents); topology evidence corroborates them but never creates them,
        and they are never routes. ``hidden_for_readability`` and
        ``passive_hint_count_drawn`` are client rendering decisions and
        therefore reported as null here, never zero. Investigations are ranked
        problem-first cards built only from the evidence above — investigation
        priorities, never root-cause, routing or parentage claims.

        This service backs the public evidence-graph endpoint. Its returned
        dict is an API contract; keep response-shape changes intentional and
        covered by API parity tests.
        """
        network = self._repo.networks.get_network(network_id)
        if network is None:
            raise NetworkNotFoundError(network_id)

        topology = self._repo.topology
        latest = topology.get_latest_topology_snapshot(network_id)
        nodes = topology.list_topology_nodes(latest["snapshot_id"]) if latest else []
        links = topology.list_topology_links(latest["snapshot_id"]) if latest else []
        history = aggregate_historical_evidence(self._repo, network_id)
        last_known = aggregate_last_known_links(self._repo, network_id)
        passive = aggregate_passive_hints(self._repo, network_id)
        device_stats = aggregate_device_stats(self._repo, network_id)
        investigations = aggregate_investigations(
            self._repo, network_id, history=history, passive_hints=passive["hints"]
        )

        latest_neighbor_pairs = {
            tuple(sorted((link["source_ieee"].lower(), link["target_ieee"].lower())))
            for link in links
            if link["source_ieee"].lower() != link["target_ieee"].lower()
        }
        latest_route_edges = sum(
            1
            for link in links
            if link.get("route_count") is not None and link["route_count"] > 0
        )
        inventory = _topology_inventory_counts(self._repo, network_id)

        return {
            "network_id": network_id,
            "network_name": network.name,
            "data_source": "latest_snapshot_plus_history",
            "latest_snapshot": latest,
            "nodes": nodes,
            "links": links,
            "layout_available": bool(nodes or links),
            "latest_layout_limited": not bool(nodes or links),
            "inventory": inventory,
            "history_window": history["history_window"],
            "historical_neighbors": history["historical_neighbors"],
            "historical_routes": history["historical_routes"],
            "last_known_links": last_known["last_known_links"],
            "last_known_window": last_known["last_known_window"],
            "passive_hints": passive["hints"],
            "passive_hint_window": passive["window"],
            "investigations": investigations["investigations"],
            "investigation_counts": {
                "available": investigations["available_count"],
                "returned": len(investigations["investigations"]),
            },
            "device_stats": device_stats["device_stats"],
            "device_stats_window": device_stats["device_stats_window"],
            "limitations": history["limitations"],
            "counts": {
                "latest_snapshot_neighbor_edges": len(latest_neighbor_pairs),
                "latest_snapshot_route_edges": latest_route_edges,
                "historical_neighbor_edges": len(history["historical_neighbors"]),
                "historical_route_edges": len(history["historical_routes"]),
                "recent_missing_link_count_total": len(history["historical_neighbors"])
                + len(history["historical_routes"]),
                "last_known_link_count": len(last_known["last_known_links"]),
                "passive_hint_count_available": passive["available_count"],
                "passive_hint_count_total": len(passive["hints"]),
                # Rendering subsets are chosen client-side; unknown here, not zero.
                "passive_hint_count_drawn": None,
                "hidden_for_readability": None,
                "known_inventory_devices": inventory["device_count"],
                "observed_topology_nodes": len(nodes),
            },
        }

    def build_topology_facts(
        self,
        network_id: str,
        *,
        now: datetime | None = None,
    ) -> TopologyFacts:
        """Build topology decision facts from stored evidence for one network.

        Internal decision-engine entry point — not part of the public API
        contract until explicitly exposed.
        """
        evidence_graph = self.build(network_id)
        return build_topology_facts_from_evidence_graph(
            network_id=network_id,
            evidence_graph=evidence_graph,
            now=now,
        )


def _topology_inventory_counts(repo: Repository, network_id: str) -> dict[str, int]:
    devices = repo.devices.list_devices(network_id)
    return {
        "device_count": len(devices),
        "router_count": sum(1 for device in devices if device.device_type == "Router"),
        "end_device_count": sum(1 for device in devices if device.device_type == "EndDevice"),
    }
