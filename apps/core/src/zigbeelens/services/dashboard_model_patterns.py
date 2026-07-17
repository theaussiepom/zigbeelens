"""Compose model-pattern facts for the Overview dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from zigbeelens.decisions.model_pattern import (
    latest_offline_transition_at,
    observed_model_patterns_for_network,
)
from zigbeelens.schemas import ModelPatternSummary

if TYPE_CHECKING:
    from zigbeelens.storage.repository import NetworkRow, Repository

MAX_OVERVIEW_MODEL_PATTERNS = 4


def compose_dashboard_model_patterns(
    repo: Repository,
    networks: list[NetworkRow],
    *,
    now: datetime | None = None,
    network_evidence_contexts: dict | None = None,
) -> list[ModelPatternSummary]:
    """Flatten qualifying Phase 4G patterns across networks for Overview."""
    now = now or datetime.now(timezone.utc)
    summaries: list[ModelPatternSummary] = []
    for network in networks:
        context = (
            network_evidence_contexts.get(network.id)
            if network_evidence_contexts is not None
            else None
        )
        if context is not None and context.model_patterns is not None:
            patterns = context.model_patterns
        else:
            patterns = observed_model_patterns_for_network(repo, network.id, now=now)
        for pattern in patterns.patterns:
            affected_ieees = set(pattern.affected_ieees)
            summaries.append(
                ModelPatternSummary(
                    pattern_id=pattern.pattern_id,
                    network_id=network.id,
                    manufacturer=pattern.manufacturer,
                    model=pattern.model,
                    group_size=pattern.group_size,
                    affected_count=pattern.affected_count,
                    lookback_days=int(
                        pattern.params.get("lookback_days", patterns.lookback_days)
                    ),
                    affected_device_ieees=list(pattern.affected_ieees),
                    latest_supporting_evidence_at=latest_offline_transition_at(
                        repo,
                        network.id,
                        affected_ieees,
                        now=now,
                    ),
                )
            )
    summaries.sort(
        key=lambda item: item.latest_supporting_evidence_at or "",
        reverse=True,
    )
    return summaries[:MAX_OVERVIEW_MODEL_PATTERNS]
