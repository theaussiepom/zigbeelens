"""Map ZigbeeLens domain health to shared Lens family presentation buckets."""

from __future__ import annotations

from enum import Enum

from zigbeelens.schemas import (
    Availability,
    BridgeState,
    DeviceHealth,
    DeviceHealthPrimary,
    DeviceSummary,
    Severity,
)

# Re-export for schema typing
class LensBucket(str, Enum):
    healthy = "healthy"
    recently_unstable = "recently_unstable"
    needs_attention = "needs_attention"
    unavailable = "unavailable"
    diagnostics_limited = "diagnostics_limited"
    informational = "informational"
    unknown = "unknown"


BUCKET_LABELS: dict[LensBucket, str] = {
    LensBucket.healthy: "Healthy",
    LensBucket.recently_unstable: "Recently unstable",
    LensBucket.needs_attention: "Needs attention",
    LensBucket.unavailable: "Unavailable",
    LensBucket.diagnostics_limited: "Diagnostics limited",
    LensBucket.informational: "Informational",
    LensBucket.unknown: "Unknown",
}

PRIMARY_REASON_LABELS: dict[DeviceHealthPrimary, str] = {
    DeviceHealthPrimary.healthy: "Healthy",
    DeviceHealthPrimary.unavailable: "Unavailable",
    DeviceHealthPrimary.recently_unstable: "Recent availability changes",
    DeviceHealthPrimary.router_risk: "Router risk",
    DeviceHealthPrimary.weak_link: "Weak link",
    DeviceHealthPrimary.low_battery: "Low battery",
    DeviceHealthPrimary.stale_reporting: "Stale reporting",
    DeviceHealthPrimary.interview_issue: "Interview issue",
    DeviceHealthPrimary.unknown: "Insufficient data",
}

_PRIMARY_BUCKET: dict[DeviceHealthPrimary, LensBucket] = {
    DeviceHealthPrimary.healthy: LensBucket.healthy,
    DeviceHealthPrimary.unavailable: LensBucket.unavailable,
    DeviceHealthPrimary.recently_unstable: LensBucket.recently_unstable,
    DeviceHealthPrimary.router_risk: LensBucket.needs_attention,
    DeviceHealthPrimary.low_battery: LensBucket.needs_attention,
    DeviceHealthPrimary.interview_issue: LensBucket.needs_attention,
    DeviceHealthPrimary.weak_link: LensBucket.needs_attention,
    DeviceHealthPrimary.stale_reporting: LensBucket.needs_attention,
    DeviceHealthPrimary.unknown: LensBucket.unknown,
}

_BUCKET_RANK: dict[LensBucket, int] = {
    LensBucket.unavailable: 0,
    LensBucket.needs_attention: 1,
    LensBucket.recently_unstable: 2,
    LensBucket.diagnostics_limited: 3,
    LensBucket.unknown: 4,
    LensBucket.informational: 5,
    LensBucket.healthy: 6,
}


def _max_bucket(a: LensBucket, b: LensBucket) -> LensBucket:
    return a if _BUCKET_RANK[a] <= _BUCKET_RANK[b] else b


def _insufficient_data(health: DeviceHealth) -> bool:
    if health.primary == DeviceHealthPrimary.unknown:
        return True
    combined = " ".join(health.limitations).lower()
    markers = (
        "not observed",
        "not enough",
        "insufficient",
        "availability may not be enabled",
        "has not observed enough",
    )
    return any(marker in combined for marker in markers)


def _weak_link_bucket(health: DeviceHealth) -> LensBucket:
    if health.severity in {Severity.incident, Severity.critical}:
        return LensBucket.needs_attention
    flags = health.flags or []
    if DeviceHealthPrimary.recently_unstable in flags:
        return LensBucket.recently_unstable
    return LensBucket.needs_attention


def _collect_reasons(health: DeviceHealth) -> list[str]:
    reasons: list[str] = []
    primary_label = PRIMARY_REASON_LABELS.get(health.primary)
    if primary_label and health.primary != DeviceHealthPrimary.healthy:
        reasons.append(primary_label)
    for flag in health.flags or []:
        if flag == health.primary or flag == DeviceHealthPrimary.healthy:
            continue
        label = PRIMARY_REASON_LABELS.get(flag)
        if label and label not in reasons:
            reasons.append(label)
    return reasons


def lens_presentation_for_health(
    health: DeviceHealth,
    *,
    availability: Availability,
    incident_affected: bool = False,
    bridge_state: BridgeState | None = None,
) -> dict[str, str | list[str]]:
    """Derive Lens bucket fields from existing device health (presentation only)."""
    if availability == Availability.offline:
        bucket = LensBucket.unavailable
    elif health.primary == DeviceHealthPrimary.weak_link:
        bucket = _weak_link_bucket(health)
    else:
        bucket = _PRIMARY_BUCKET.get(health.primary, LensBucket.unknown)

    if _insufficient_data(health):
        bucket = LensBucket.diagnostics_limited

    if bridge_state == BridgeState.offline:
        if health.primary in {
            DeviceHealthPrimary.unknown,
            DeviceHealthPrimary.stale_reporting,
        }:
            bucket = LensBucket.diagnostics_limited

    if incident_affected:
        bucket = _max_bucket(bucket, LensBucket.needs_attention)

    reasons = _collect_reasons(health)
    if bucket == LensBucket.diagnostics_limited and bridge_state == BridgeState.offline:
        if "Bridge offline limits observation" not in reasons:
            reasons.insert(0, "Bridge offline limits observation")

    primary_reason = reasons[0] if reasons else BUCKET_LABELS[bucket]

    return {
        "lens_bucket": bucket.value,
        "lens_bucket_label": BUCKET_LABELS[bucket],
        "lens_bucket_reason": primary_reason,
        "lens_reasons": reasons,
    }


def enrich_device_summary(
    summary: DeviceSummary,
    *,
    bridge_state: BridgeState | None = None,
) -> DeviceSummary:
    presentation = lens_presentation_for_health(
        summary.health,
        availability=summary.availability,
        incident_affected=summary.incident_affected,
        bridge_state=bridge_state,
    )
    return summary.model_copy(update=presentation)
