"""Compose shared availability event facts for the Overview dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from zigbeelens.decisions.availability_event_groups import (
    shared_availability_event_groups_for_network,
)
from zigbeelens.schemas import SharedAvailabilityEventSummary
from zigbeelens.services.network_evidence import (
    NetworkEvidenceCapability,
    require_mapped_network_evidence_context,
)

if TYPE_CHECKING:
    from zigbeelens.storage.repository import NetworkRow, Repository

MAX_OVERVIEW_SHARED_AVAILABILITY_EVENTS = 4


def compose_dashboard_shared_availability_events(
    repo: Repository,
    networks: list[NetworkRow],
    *,
    now: datetime | None = None,
    network_evidence_contexts: dict[str, Any] | None = None,
) -> list[SharedAvailabilityEventSummary]:
    """Flatten Phase 4E-1 groups across networks for Overview presentation."""
    summaries: list[SharedAvailabilityEventSummary] = []
    for network in networks:
        if network_evidence_contexts is not None:
            context = require_mapped_network_evidence_context(
                network_evidence_contexts, network.id
            )
            reference_now = now if now is not None else context.reference_now
            context.require_compatible(
                network_id=network.id, reference_now=reference_now
            )
            context.require(NetworkEvidenceCapability.shared_availability)
            assert context.shared_availability is not None
            groups = context.shared_availability
        else:
            reference_now = now or datetime.now(timezone.utc)
            groups = shared_availability_event_groups_for_network(
                repo, network.id, now=reference_now
            )
        for event in groups.groups:
            summaries.append(
                SharedAvailabilityEventSummary(
                    event_id=event.event_id,
                    network_id=network.id,
                    started_at=event.started_at.isoformat(),
                    ended_at=event.ended_at.isoformat(),
                    device_count=event.device_count,
                    duration_minutes=event.duration_minutes,
                    device_ieees=list(event.device_ieees),
                )
            )
    summaries.sort(key=lambda item: item.ended_at, reverse=True)
    return summaries[:MAX_OVERVIEW_SHARED_AVAILABILITY_EVENTS]
