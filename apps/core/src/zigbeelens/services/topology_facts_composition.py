"""Topology decision-fact composition at configuration/service boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from zigbeelens.decisions.topology_facts import (
    build_topology_facts_from_evidence_graph,
    normalize_device_ieee,
    topology_device_facts_payload,
    topology_network_facts_payload,
)
from zigbeelens.decisions.availability_tracking import availability_tracking_enabled_now
from zigbeelens.decisions.topology_coverage import build_network_topology_coverage
from zigbeelens.topology.device_compare import device_snapshot_history

if TYPE_CHECKING:
    from datetime import datetime

    from zigbeelens.config.models import AppConfig
    from zigbeelens.storage.repository import Repository

    from zigbeelens.services.evidence_graph import EvidenceGraphService


def topology_stale_threshold_hours(config: AppConfig) -> int | None:
    """Derive snapshot staleness threshold from topology configuration.

  When automatic capture is disabled, the configured interval is scheduler
  cadence only and must not become an evidence-staleness policy.
    """
    topo = config.topology
    if topo.automatic_capture_enabled:
        return topo.automatic_capture_interval_hours
    return None


def compose_network_topology_facts_payload(
    service: EvidenceGraphService,
    repo: Repository,
    evidence_graph: dict[str, Any],
    *,
    stale_after_hours: int | None,
    now: datetime | None = None,
    network_evidence_context: Any | None = None,
) -> dict[str, Any]:
    facts = service.build_topology_facts(
        evidence_graph["network_id"],
        evidence_graph=evidence_graph,
        now=now,
        stale_after_hours=stale_after_hours,
        context=network_evidence_context,
    )
    network_id = evidence_graph["network_id"]
    if network_evidence_context is not None:
        from zigbeelens.services.network_evidence import NetworkEvidenceCapability

        network_evidence_context.require_compatible(
            network_id=str(network_id),
            reference_now=now,
            stale_after_hours=stale_after_hours,
        )
        network_evidence_context.require(NetworkEvidenceCapability.coverage)
        assert network_evidence_context.network_topology_coverage is not None
        coverage = network_evidence_context.network_topology_coverage
    else:
        coverage = build_network_topology_coverage(
            facts.network_facts,
            tracking_enabled_now=availability_tracking_enabled_now(repo, network_id),
            has_known_devices=bool(repo.list_devices(network_id)),
            has_usable_ha_area_assignments=repo.network_has_usable_ha_area_assignments(
                network_id
            ),
        )
    return topology_network_facts_payload(
        facts,
        stale_threshold_hours=stale_after_hours,
        coverage=coverage,
    )


def compose_device_topology_facts_payload(
    service: EvidenceGraphService,
    *,
    network_id: str,
    device_ieee: str,
    device_snapshot_history_payload: dict[str, Any],
    stale_after_hours: int | None,
    now: datetime | None = None,
    evidence_graph: dict[str, Any] | None = None,
    network_evidence_context: Any | None = None,
) -> dict[str, Any]:
    graph = (
        evidence_graph
        if evidence_graph is not None
        else service.build(network_id, now=now, context=network_evidence_context)
    )
    device_key = normalize_device_ieee(device_ieee)
    facts = build_topology_facts_from_evidence_graph(
        network_id=network_id,
        evidence_graph=graph,
        device_ieees=[device_ieee],
        device_snapshot_histories={device_key: device_snapshot_history_payload},
        now=now,
        stale_after_hours=stale_after_hours,
    )
    return topology_device_facts_payload(
        facts,
        device_ieee=device_ieee,
        stale_threshold_hours=stale_after_hours,
    )


def build_device_snapshot_history_response(
    repo: Repository,
    service: EvidenceGraphService,
    *,
    network_id: str,
    device_ieee: str,
    stale_after_hours: int | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Exact device snapshot-history endpoint with row/link bounds.

    Loads at most ``MAX_SNAPSHOT_HISTORY`` complete snapshots and only
    target-device links for those IDs. Preserves coded device topology facts
    without the broad all-history NetworkEvidenceContext path.
    """
    from datetime import datetime, timezone

    from zigbeelens.topology.device_compare import (
        MAX_SNAPSHOT_HISTORY,
        load_device_snapshot_history_network_context,
    )

    reference_now = now or datetime.now(timezone.utc)
    if reference_now.tzinfo is None:
        reference_now = reference_now.replace(tzinfo=timezone.utc)

    usable = list(
        repo.list_complete_topology_snapshots(network_id, limit=MAX_SNAPSHOT_HISTORY)
    )
    snapshot_ids = [str(row["snapshot_id"]) for row in usable]
    links_by_snapshot_id = (
        repo.list_topology_links_for_device_in_snapshots(snapshot_ids, device_ieee)
        if snapshot_ids
        else {}
    )
    earliest_availability_at = repo.availability.get_earliest_availability_change_at(
        network_id
    )
    devices = repo.list_devices(network_id)
    network_context = load_device_snapshot_history_network_context(
        repo,
        network_id,
        max_snapshots=MAX_SNAPSHOT_HISTORY,
        snapshots=usable,
        links_by_snapshot_id=links_by_snapshot_id,
        earliest_availability_at=earliest_availability_at,
        earliest_availability_supplied=True,
        devices=devices,
    )
    history = device_snapshot_history(
        repo,
        network_id,
        device_ieee,
        max_snapshots=MAX_SNAPSHOT_HISTORY,
        network_context=network_context,
    )

    latest = usable[0] if usable else None
    latest_id = str(latest["snapshot_id"]) if latest is not None else None
    latest_nodes: list[dict[str, Any]] = []
    if latest_id is not None:
        node_row = repo.get_topology_node(latest_id, device_ieee)
        if node_row is not None:
            latest_nodes = [node_row]

    evidence_graph = {
        "latest_snapshot": dict(latest) if latest is not None else None,
        "nodes": latest_nodes,
        "links": list(links_by_snapshot_id.get(latest_id, [])) if latest_id else [],
        "counts": {},
    }
    return {
        **history,
        "topology_facts": compose_device_topology_facts_payload(
            service,
            network_id=network_id,
            device_ieee=device_ieee,
            device_snapshot_history_payload=history,
            stale_after_hours=stale_after_hours,
            now=reference_now,
            evidence_graph=evidence_graph,
            network_evidence_context=None,
        ),
    }
