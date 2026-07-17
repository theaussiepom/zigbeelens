"""Compose mesh investigation priorities for the Overview dashboard (Phase 5A-1)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from zigbeelens.schemas import InvestigationPrioritySummary
from zigbeelens.services.evidence_graph import EvidenceGraphService

if TYPE_CHECKING:
    from zigbeelens.storage.repository import NetworkRow, Repository

MAX_OVERVIEW_INVESTIGATION_PRIORITIES = 6


def _card_to_summary(network_id: str, card: dict[str, Any]) -> InvestigationPrioritySummary:
    return InvestigationPrioritySummary(
        id=str(card["id"]),
        network_id=network_id,
        card_type=str(card["type"]),
        priority=str(card["priority"]),
        score=int(card["score"]),
        action_group=str(card.get("action_group") or ""),
        title=str(card["title"]),
        summary=str(card["summary"]),
        device_ieees=list(card.get("device_ieees") or []),
        latest_supporting_evidence_at=card.get("latest_supporting_evidence_at"),
    )


def compose_dashboard_investigation_priorities(
    repo: Repository,
    networks: list[NetworkRow],
    *,
    now: datetime | None = None,
    network_evidence_contexts: dict[str, Any] | None = None,
) -> list[InvestigationPrioritySummary]:
    """Flatten ranked mesh investigation cards across networks for Overview."""
    from zigbeelens.services.network_evidence import (
        NetworkEvidenceCapability,
        require_mapped_network_evidence_context,
    )

    service = EvidenceGraphService(repo)
    summaries: list[InvestigationPrioritySummary] = []
    for network in networks:
        if network_evidence_contexts is not None:
            context = require_mapped_network_evidence_context(
                network_evidence_contexts, network.id
            )
            reference_now = now if now is not None else context.reference_now
            context.require_compatible(
                network_id=network.id, reference_now=reference_now
            )
            context.require(NetworkEvidenceCapability.investigations)
            investigations = service.investigations_for_network(
                network.id, now=reference_now, context=context
            )
        else:
            investigations = service.investigations_for_network(
                network.id, now=now, context=None
            )
        for card in investigations["investigations"]:
            summaries.append(_card_to_summary(network.id, card))

    summaries.sort(
        key=lambda item: (
            item.score,
            item.latest_supporting_evidence_at or "",
            item.network_id,
            item.id,
        ),
        reverse=True,
    )
    return summaries[:MAX_OVERVIEW_INVESTIGATION_PRIORITIES]
