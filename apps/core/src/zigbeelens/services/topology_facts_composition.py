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
    from datetime import datetime, timezone

    from zigbeelens.services.network_evidence import EVIDENCE_GRAPH_FACTS_REQUIREMENTS
    from zigbeelens.services.network_evidence_composition import (
        compose_network_evidence_context,
    )

    reference_now = now or datetime.now(timezone.utc)
    if reference_now.tzinfo is None:
        reference_now = reference_now.replace(tzinfo=timezone.utc)
    context = compose_network_evidence_context(
        repo,
        network_id,
        reference_now=reference_now,
        requirements=EVIDENCE_GRAPH_FACTS_REQUIREMENTS,
        stale_after_hours=stale_after_hours,
    )
    history = device_snapshot_history(
        repo,
        network_id,
        device_ieee,
        network_context=context.snapshot_history_context,
    )
    graph = service.build(network_id, now=reference_now, context=context)
    return {
        **history,
        "topology_facts": compose_device_topology_facts_payload(
            service,
            network_id=network_id,
            device_ieee=device_ieee,
            device_snapshot_history_payload=history,
            stale_after_hours=stale_after_hours,
            now=reference_now,
            evidence_graph=graph,
            network_evidence_context=context,
        ),
    }
