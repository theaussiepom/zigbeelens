"""Build mesh evidence-graph payloads from stored topology and passive evidence."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from zigbeelens.decisions.topology_facts import (
    TopologyFacts,
    build_topology_facts_from_evidence_graph,
)
from zigbeelens.decisions.availability_event_groups import (
    shared_availability_event_groups_for_network,
)
from zigbeelens.decisions.router_area import observed_router_areas_for_network
from zigbeelens.decisions.model_pattern import observed_model_patterns_for_network
from zigbeelens.topology.investigations import issue_device_ieees_from_state
from zigbeelens.services.topology_facts_composition import compose_network_topology_facts_payload
from zigbeelens.topology.device_stats import aggregate_device_stats
from zigbeelens.topology.history import (
    aggregate_historical_evidence,
    aggregate_last_known_links,
)
from zigbeelens.topology.investigations import aggregate_investigations
from zigbeelens.topology.passive_hints import aggregate_passive_hints

if TYPE_CHECKING:
    from zigbeelens.storage.repository import Repository


class NetworkNotFoundError(LookupError):
    """Raised when evidence graph is requested for an unknown network."""


class EvidenceGraphService:
    """Orchestrate evidence-graph assembly for one network."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    def _compose_investigations(
        self,
        network_id: str,
        *,
        links: list[dict[str, Any]],
        history: dict[str, Any],
        last_known: dict[str, Any],
        passive: dict[str, Any],
    ) -> dict[str, Any]:
        """Compose ranked investigation cards from already-loaded evidence inputs."""
        shared_availability = shared_availability_event_groups_for_network(
            self._repo, network_id
        )
        devices = self._repo.list_devices(network_id)
        issue_device_ieees = issue_device_ieees_from_state(devices)
        observed_router_areas = observed_router_areas_for_network(
            self._repo,
            network_id,
            devices=devices,
            latest_links=links,
            history=history,
            last_known_links=last_known["last_known_links"],
            passive_hints=passive["hints"],
            issue_device_ieees=issue_device_ieees,
        )
        observed_model_patterns = observed_model_patterns_for_network(
            self._repo, network_id
        )
        return aggregate_investigations(
            self._repo,
            network_id,
            history=history,
            passive_hints=passive["hints"],
            shared_availability_events=shared_availability.groups,
            observed_router_areas=observed_router_areas.areas,
            observed_model_patterns=observed_model_patterns.patterns,
            last_known_links=last_known["last_known_links"],
        )

    def investigations_for_network(self, network_id: str) -> dict[str, Any]:
        """Ranked investigation cards for one network (shared by mesh and Overview)."""
        network = self._repo.networks.get_network(network_id)
        if network is None:
            raise NetworkNotFoundError(network_id)

        topology = self._repo.topology
        latest = topology.get_latest_topology_snapshot(network_id)
        links = topology.list_topology_links(latest["snapshot_id"]) if latest else []
        history = aggregate_historical_evidence(self._repo, network_id)
        last_known = aggregate_last_known_links(self._repo, network_id)
        passive = aggregate_passive_hints(self._repo, network_id)
        return self._compose_investigations(
            network_id,
            links=links,
            history=history,
            last_known=last_known,
            passive=passive,
        )

    def build(self, network_id: str, *, now: datetime | None = None) -> dict:
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

        ``now`` is optional and only affects the recent-history window used for
        historical neighbour/route aggregation. When omitted, wall-clock UTC
        is used.

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
        history = aggregate_historical_evidence(self._repo, network_id, now=now)
        last_known = aggregate_last_known_links(self._repo, network_id)
        passive = aggregate_passive_hints(self._repo, network_id)
        device_stats = aggregate_device_stats(self._repo, network_id)
        investigations = self._compose_investigations(
            network_id,
            links=links,
            history=history,
            last_known=last_known,
            passive=passive,
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

    def build_with_network_topology_facts(
        self,
        network_id: str,
        *,
        stale_after_hours: int | None,
        now: datetime | None = None,
    ) -> dict:
        """Evidence graph payload with network topology facts attached."""
        body = self.build(network_id, now=now)
        body["topology_facts"] = compose_network_topology_facts_payload(
            self,
            self._repo,
            body,
            stale_after_hours=stale_after_hours,
            now=now,
        )
        return body

    def build_topology_facts(
        self,
        network_id: str,
        *,
        evidence_graph: dict | None = None,
        now: datetime | None = None,
        stale_after_hours: int | None = None,
        device_ieees: list[str] | None = None,
        device_snapshot_histories: dict[str, dict[str, Any]] | None = None,
    ) -> TopologyFacts:
        """Build topology decision facts from stored evidence for one network.

        ``stale_after_hours`` must be supplied by the caller when
        ``latest_snapshot_stale`` facts are required. When omitted, snapshot
        age is not compared against any implicit product default.
        """
        graph = evidence_graph if evidence_graph is not None else self.build(network_id, now=now)
        return build_topology_facts_from_evidence_graph(
            network_id=network_id,
            evidence_graph=graph,
            device_ieees=device_ieees,
            device_snapshot_histories=device_snapshot_histories,
            now=now,
            stale_after_hours=stale_after_hours,
        )

    def network_topology_facts_payload(
        self,
        evidence_graph: dict,
        *,
        stale_after_hours: int | None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Network topology facts ready for API/report payloads."""
        return compose_network_topology_facts_payload(
            self,
            self._repo,
            evidence_graph,
            stale_after_hours=stale_after_hours,
            now=now,
        )


def _topology_inventory_counts(repo: Repository, network_id: str) -> dict[str, int]:
    devices = repo.devices.list_devices(network_id)
    return {
        "device_count": len(devices),
        "router_count": sum(1 for device in devices if device.device_type == "Router"),
        "end_device_count": sum(1 for device in devices if device.device_type == "EndDevice"),
    }
