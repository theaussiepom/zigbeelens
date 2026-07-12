"""Topology decision-fact composition at configuration/service boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from zigbeelens.decisions.topology_facts import (
    build_topology_facts_from_evidence_graph,
    normalize_device_ieee,
    topology_device_facts_payload,
    topology_network_facts_payload,
)
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
    evidence_graph: dict[str, Any],
    *,
    stale_after_hours: int | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    facts = service.build_topology_facts(
        evidence_graph["network_id"],
        evidence_graph=evidence_graph,
        now=now,
        stale_after_hours=stale_after_hours,
    )
    return topology_network_facts_payload(
        facts,
        stale_threshold_hours=stale_after_hours,
    )


def compose_device_topology_facts_payload(
    service: EvidenceGraphService,
    *,
    network_id: str,
    device_ieee: str,
    device_snapshot_history_payload: dict[str, Any],
    stale_after_hours: int | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    evidence_graph = service.build(network_id)
    device_key = normalize_device_ieee(device_ieee)
    facts = build_topology_facts_from_evidence_graph(
        network_id=network_id,
        evidence_graph=evidence_graph,
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
) -> dict[str, Any]:
    history = device_snapshot_history(repo, network_id, device_ieee)
    return {
        **history,
        "topology_facts": compose_device_topology_facts_payload(
            service,
            network_id=network_id,
            device_ieee=device_ieee,
            device_snapshot_history_payload=history,
            stale_after_hours=stale_after_hours,
        ),
    }
