"""Pure projections from canonical Device Stories onto report DTOs (Phase 5D)."""

from __future__ import annotations

from collections import Counter

from zigbeelens.decisions.device_story import DeviceStory, device_story_report_payload
from zigbeelens.schemas import (
    DeviceSummary,
    ReportDecisionSummary,
    ReportDeviceStory,
    ReportStoryTimelineItem,
)


def report_device_story_from_story(
    *,
    device: DeviceSummary,
    story: DeviceStory,
) -> ReportDeviceStory:
    """Project a canonical Device Story into the report DTO exactly."""
    payload = device_story_report_payload(story)
    timeline = [
        ReportStoryTimelineItem.model_validate(item)
        for item in payload.get("timeline", [])
    ]
    return ReportDeviceStory(
        network_id=device.network_id,
        ieee_address=device.ieee_address,
        friendly_name=device.friendly_name,
        subject_type=str(payload.get("subject_type") or "device"),
        subject_id=str(payload["subject_id"]),
        status=str(payload["status"]),
        priority=str(payload["priority"]),
        headline_code=str(payload["headline_code"]),
        reasons=list(payload.get("reasons") or []),
        evidence=list(payload.get("evidence") or []),
        limitations=list(payload.get("limitations") or []),
        suggested_checks=list(payload.get("suggested_checks") or []),
        coverage=list(payload.get("coverage") or []),
        related_unresolved_incident_ids=list(
            payload.get("related_unresolved_incident_ids") or []
        ),
        timeline=timeline,
    )


def report_decision_summary_from_stories(
    stories: list[DeviceStory] | list[ReportDeviceStory],
) -> ReportDecisionSummary:
    """Count factual Device Story status/priority values for the report scope."""
    status_counts: Counter[str] = Counter()
    priority_counts: Counter[str] = Counter()
    for story in stories:
        status_counts[str(story.status)] += 1
        priority_counts[str(story.priority)] += 1
    return ReportDecisionSummary(
        device_story_count=len(stories),
        status_counts=dict(status_counts),
        priority_counts=dict(priority_counts),
    )


def coded_payload_excludes_identity(report_story: ReportDeviceStory) -> dict:
    """Coded story fields used for exact parity with device_story_report_payload."""
    return report_story.model_dump(
        mode="json",
        exclude={"network_id", "ieee_address", "friendly_name"},
    )
