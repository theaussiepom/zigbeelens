"""Compact device decision badges for inventory surfaces (Phase 5B-1)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Mapping

from zigbeelens.decisions.device_story import (
    DeviceStory,
    device_stories_for_devices,
    device_story_for_device,
)
from zigbeelens.decisions.types import CoverageState
from zigbeelens.schemas import DeviceDecisionBadge

if TYPE_CHECKING:
    from zigbeelens.storage.repository import DeviceRow, Repository

_LIMITING_COVERAGE_STATES = frozenset(
    {
        CoverageState.off,
        CoverageState.building,
        CoverageState.unknown,
        CoverageState.stale,
        CoverageState.not_configured,
        CoverageState.not_observed,
        CoverageState.sparse,
    }
)

MAX_BADGE_COVERAGE_LABELS = 3


def device_decision_badge_from_story(story: DeviceStory) -> DeviceDecisionBadge:
    """Project a Device Story onto the inventory badge DTO."""
    coverage_label_codes = []
    for item in story.coverage:
        if item.state in _LIMITING_COVERAGE_STATES:
            code = item.label_code
            if code not in coverage_label_codes:
                coverage_label_codes.append(code)
        if len(coverage_label_codes) >= MAX_BADGE_COVERAGE_LABELS:
            break

    return DeviceDecisionBadge(
        status=story.status,
        priority=story.priority,
        headline_code=str(story.headline_code),
        coverage_label_codes=coverage_label_codes,
    )


def device_decision_badge_for_device(
    repo: Repository,
    network_id: str,
    device_ieee: str,
    *,
    now: datetime | None = None,
) -> DeviceDecisionBadge | None:
    """Build a compact decision badge from the Device Story rules for one device."""
    story = device_story_for_device(repo, network_id, device_ieee, now=now)
    if story is None:
        return None
    return device_decision_badge_from_story(story)


def device_decision_badges_for_devices(
    repo: Repository,
    rows: list[DeviceRow],
    *,
    now: datetime | None = None,
    ha_enrichment_by_key=None,
    related_incident_ids_by_key=None,
    network_evidence_contexts: Mapping[str, Any] | None = None,
) -> dict[tuple[str, str], DeviceDecisionBadge]:
    """Compose decision badges for many devices via shared full-story batching."""
    stories = device_stories_for_devices(
        repo,
        rows,
        now=now,
        ha_enrichment_by_key=ha_enrichment_by_key,
        related_incident_ids_by_key=related_incident_ids_by_key,
        network_evidence_contexts=network_evidence_contexts,
    )
    return {
        key: device_decision_badge_from_story(story)
        for key, story in stories.items()
    }
