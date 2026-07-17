"""Build mesh evidence-graph payloads from stored topology and passive evidence."""

from __future__ import annotations

from datetime import datetime, timezone
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
from zigbeelens.services.network_evidence import (
    EVIDENCE_GRAPH_FACTS_REQUIREMENTS,
    EVIDENCE_GRAPH_REQUIREMENTS,
    NetworkEvidenceCapability,
    NetworkEvidenceContext,
)
from zigbeelens.services.network_evidence_composition import compose_network_evidence_context
from zigbeelens.services.topology_facts_composition import compose_network_topology_facts_payload
from zigbeelens.topology.investigations import aggregate_investigations

if TYPE_CHECKING:
    from zigbeelens.storage.repository import Repository


class NetworkNotFoundError(LookupError):
    """Raised when evidence graph is requested for an unknown network."""


class EvidenceGraphService:
    """Orchestrate evidence-graph assembly for one network."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    def _ensure_context(
        self,
        network_id: str,
        *,
        now: datetime | None,
        context: NetworkEvidenceContext | None,
        requirements=EVIDENCE_GRAPH_REQUIREMENTS,
        stale_after_hours: int | None | object = ...,
    ) -> NetworkEvidenceContext:
        if context is not None:
            reference_now = now if now is not None else context.reference_now
            if reference_now.tzinfo is None:
                reference_now = reference_now.replace(tzinfo=timezone.utc)
            compat_kwargs: dict[str, Any] = {
                "network_id": network_id,
                "reference_now": reference_now,
            }
            if stale_after_hours is not ...:
                compat_kwargs["stale_after_hours"] = stale_after_hours
            context.require_compatible(**compat_kwargs)
            return context
        reference_now = now or datetime.now(timezone.utc)
        if reference_now.tzinfo is None:
            reference_now = reference_now.replace(tzinfo=timezone.utc)
        network = self._repo.networks.get_network(network_id)
        if network is None:
            raise NetworkNotFoundError(network_id)
        return compose_network_evidence_context(
            self._repo,
            network_id,
            reference_now=reference_now,
            requirements=requirements,
            network_row=network,
            stale_after_hours=(
                None if stale_after_hours is ... else stale_after_hours  # type: ignore[arg-type]
            ),
        )

    def _compose_investigations_from_context(
        self,
        context: NetworkEvidenceContext,
    ) -> dict[str, Any]:
        context.require(NetworkEvidenceCapability.investigations)
        assert context.investigations is not None
        return dict(context.investigations)

    def _compose_investigations(
        self,
        network_id: str,
        *,
        links: list[dict[str, Any]],
        history: dict[str, Any],
        last_known: dict[str, Any],
        passive: dict[str, Any],
        now: datetime | None = None,
        devices: list | None = None,
        availability_rows: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Compose ranked investigation cards from already-loaded evidence inputs."""
        shared_availability = shared_availability_event_groups_for_network(
            self._repo,
            network_id,
            now=now,
            devices=devices,
            availability_rows=availability_rows,
        )
        device_rows = list(devices) if devices is not None else self._repo.list_devices(network_id)
        issue_device_ieees = issue_device_ieees_from_state(device_rows)
        observed_router_areas = observed_router_areas_for_network(
            self._repo,
            network_id,
            devices=device_rows,
            latest_links=links,
            history=history,
            last_known_links=last_known["last_known_links"],
            passive_hints=passive["hints"],
            issue_device_ieees=issue_device_ieees,
        )
        observed_model_patterns = observed_model_patterns_for_network(
            self._repo,
            network_id,
            now=now,
            devices=device_rows,
            availability_rows=availability_rows,
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

    def investigations_for_network(
        self,
        network_id: str,
        *,
        now: datetime | None = None,
        context: NetworkEvidenceContext | None = None,
    ) -> dict[str, Any]:
        """Ranked investigation cards for one network (shared by mesh and Overview)."""
        evidence = self._ensure_context(network_id, now=now, context=context)
        return self._compose_investigations_from_context(evidence)

    def build(
        self,
        network_id: str,
        *,
        now: datetime | None = None,
        context: NetworkEvidenceContext | None = None,
    ) -> dict:
        """Graph-ready topology evidence: latest snapshot plus aggregated
        recent-missing (historical) neighbour/route evidence.

        Historical edges are aggregated backend-side from recent previous
        complete snapshots only and never duplicate relationships present in the
        latest snapshot — this is gap-filling context, not forever history.
        Last known links cover only devices with no link entries at all in the
        latest usable snapshot (typically sleepy battery devices whose entries
        aged out of router neighbour tables): each gets its most recently stored
        link evidence, clearly marked as last known rather than currently
        reported. Passive service backs the public evidence-graph endpoint.
        """
        evidence = self._ensure_context(network_id, now=now, context=context)
        evidence.require(NetworkEvidenceCapability.latest_topology)
        evidence.require(NetworkEvidenceCapability.historical_links)
        evidence.require(NetworkEvidenceCapability.last_known_links)
        evidence.require(NetworkEvidenceCapability.passive_hints)
        evidence.require(NetworkEvidenceCapability.device_stats)
        evidence.require(NetworkEvidenceCapability.investigations)
        evidence.require(NetworkEvidenceCapability.devices)

        latest = (
            dict(evidence.latest_usable_snapshot)
            if evidence.latest_usable_snapshot is not None
            else None
        )
        nodes = [dict(row) for row in (evidence.latest_nodes or ())]
        links = [dict(row) for row in (evidence.latest_links or ())]
        history = dict(evidence.historical_evidence or {})
        last_known = dict(evidence.last_known_links or {})
        passive = dict(evidence.passive_hints or {})
        device_stats = dict(evidence.device_stats or {})
        investigations = dict(evidence.investigations or {})
        inventory = _topology_inventory_counts_from_devices(
            list(evidence.device_rows or ())
        )
        network_name = (
            evidence.network_row.name
            if evidence.network_row is not None
            else network_id
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

        return {
            "network_id": network_id,
            "network_name": network_name,
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
        context: NetworkEvidenceContext | None = None,
    ) -> dict:
        """Evidence graph payload with network topology facts attached."""
        evidence = self._ensure_context(
            network_id,
            now=now,
            context=context,
            requirements=EVIDENCE_GRAPH_FACTS_REQUIREMENTS,
            stale_after_hours=stale_after_hours,
        )
        evidence.require(NetworkEvidenceCapability.topology_facts)
        evidence.require(NetworkEvidenceCapability.coverage)
        body = self.build(network_id, now=evidence.reference_now, context=evidence)
        body["topology_facts"] = compose_network_topology_facts_payload(
            self,
            self._repo,
            body,
            stale_after_hours=stale_after_hours,
            now=evidence.reference_now,
            network_evidence_context=evidence,
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
        context: NetworkEvidenceContext | None = None,
    ) -> TopologyFacts:
        """Build topology decision facts from stored evidence for one network.

        ``stale_after_hours`` must be supplied by the caller when
        ``latest_snapshot_stale`` facts are required. When omitted, snapshot
        age is not compared against any implicit product default.
        """
        if evidence_graph is not None:
            graph = evidence_graph
        else:
            evidence = self._ensure_context(network_id, now=now, context=context)
            graph = self.build(network_id, now=evidence.reference_now, context=evidence)
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


def _topology_inventory_counts_from_devices(devices: list) -> dict[str, int]:
    return {
        "device_count": len(devices),
        "router_count": sum(1 for device in devices if device.device_type == "Router"),
        "end_device_count": sum(1 for device in devices if device.device_type == "EndDevice"),
    }


def _topology_inventory_counts(repo: Repository, network_id: str) -> dict[str, int]:
    return _topology_inventory_counts_from_devices(repo.devices.list_devices(network_id))
