"""Compact device decision badges for inventory surfaces (Phase 5B-1)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from zigbeelens.decisions.device_story import (
    DeviceStory,
    build_device_story,
    device_story_for_device,
    load_device_story_evidence,
    load_device_story_network_context,
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
    coverage_label_codes: list[str] = []
    for item in story.coverage:
        if item.state in _LIMITING_COVERAGE_STATES:
            code = str(item.label_code)
            if code not in coverage_label_codes:
                coverage_label_codes.append(code)
        if len(coverage_label_codes) >= MAX_BADGE_COVERAGE_LABELS:
            break

    return DeviceDecisionBadge(
        status=str(story.status),
        priority=str(story.priority),
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
) -> dict[tuple[str, str], DeviceDecisionBadge]:
    """Compose decision badges for many devices with one network context each."""
    reference_now = now or datetime.now(timezone.utc)
    by_network: dict[str, list[DeviceRow]] = defaultdict(list)
    for row in rows:
        by_network[row.network_id].append(row)

    badges: dict[tuple[str, str], DeviceDecisionBadge] = {}
    for network_id, network_rows in by_network.items():
        context = load_device_story_network_context(
            repo, network_id, now=reference_now
        )
        for row in network_rows:
            evidence = load_device_story_evidence(
                repo,
                network_id,
                row.ieee_address,
                now=reference_now,
                network_context=context,
            )
            if evidence is None:
                continue
            story = build_device_story(evidence, now=reference_now)
            badges[(network_id, row.ieee_address)] = device_decision_badge_from_story(
                story
            )
    return badges
