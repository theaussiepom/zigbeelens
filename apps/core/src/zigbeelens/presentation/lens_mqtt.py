"""Lens-family MQTT summary presentation (no health-engine changes)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from zigbeelens.presentation.lens_buckets import BUCKET_LABELS, LensBucket
from zigbeelens.schemas import DashboardPayload, Severity
from zigbeelens.storage.repository import utc_now_iso

PRODUCT = "zigbeelens"
REDACTION_PROFILE = "public_safe"


def severity_to_lens_bucket(severity: Severity | str | None) -> str:
    if severity is None:
        return LensBucket.unknown.value
    raw = severity.value if isinstance(severity, Severity) else str(severity)
    if raw in {"healthy", "ok"}:
        return LensBucket.healthy.value
    if raw == "watch":
        return LensBucket.recently_unstable.value
    if raw in {"incident", "critical"}:
        return LensBucket.needs_attention.value
    return LensBucket.unknown.value


def _iter_dashboard_devices(dashboard: DashboardPayload):
    seen: set[tuple[str, str]] = set()
    for collection in (
        dashboard.top_affected_devices,
        dashboard.recently_unstable,
        dashboard.weak_links,
        dashboard.low_batteries,
        dashboard.stale_devices,
    ):
        for device in collection:
            key = (device.network_id, device.ieee_address)
            if key in seen:
                continue
            seen.add(key)
            yield device


def lens_bucket_counts(
    dashboard: DashboardPayload,
    *,
    observable: bool,
) -> dict[str, int | str]:
    keys = (
        LensBucket.healthy.value,
        LensBucket.recently_unstable.value,
        LensBucket.needs_attention.value,
        LensBucket.unavailable.value,
        LensBucket.diagnostics_limited.value,
        LensBucket.informational.value,
        LensBucket.unknown.value,
    )
    if not observable:
        return dict.fromkeys(keys, "unknown")

    counts: dict[str, int] = dict.fromkeys(keys, 0)
    counts[LensBucket.unavailable.value] = dashboard.health_snapshot.unavailable_count
    for device in _iter_dashboard_devices(dashboard):
        bucket = device.lens_bucket if device.lens_bucket in counts else LensBucket.unknown.value
        counts[bucket] += 1
    counts[LensBucket.needs_attention.value] += len(dashboard.router_risks)
    return counts


def issue_count(counts: dict[str, int | str]) -> int | str:
    if any(value == "unknown" for value in counts.values()):
        return "unknown"
    total = 0
    for bucket in (
        LensBucket.unavailable.value,
        LensBucket.recently_unstable.value,
        LensBucket.needs_attention.value,
        LensBucket.diagnostics_limited.value,
        LensBucket.unknown.value,
    ):
        total += int(counts.get(bucket, 0))
    return total


def count_state(value: int | str) -> str:
    if value == "unknown":
        return "unknown"
    return str(int(value))


@dataclass(frozen=True)
class SummaryEntityState:
    key: str
    name: str
    state: str
    attributes: dict[str, Any]


def build_summary_entities(
    dashboard: DashboardPayload,
    *,
    core_version: str,
    collector_connected: bool,
    mock_mode: bool,
) -> list[SummaryEntityState]:
    observable = mock_mode or collector_connected
    counts = lens_bucket_counts(dashboard, observable=observable)
    overall_bucket = severity_to_lens_bucket(dashboard.overall_severity)
    overall_label = BUCKET_LABELS.get(LensBucket(overall_bucket), overall_bucket.title())
    issues = issue_count(counts)
    generated_at = utc_now_iso()

    base_attrs = {
        "product": PRODUCT,
        "version": core_version,
        "lens_bucket": overall_bucket,
        "lens_bucket_label": overall_label,
        "issue_count": issues,
        "unavailable_count": counts[LensBucket.unavailable.value],
        "needs_attention_count": counts[LensBucket.needs_attention.value],
        "recently_unstable_count": counts[LensBucket.recently_unstable.value],
        "diagnostics_limited_count": counts[LensBucket.diagnostics_limited.value],
        "informational_count": counts[LensBucket.informational.value],
        "unknown_count": counts[LensBucket.unknown.value],
        "generated_at": generated_at,
        "redaction_profile": REDACTION_PROFILE,
        "collector_connected": collector_connected,
        "observation_reliable": observable,
    }

    return [
        SummaryEntityState(
            key="health",
            name="ZigbeeLens Health",
            state=overall_bucket,
            attributes=base_attrs,
        ),
        SummaryEntityState(
            key="issues",
            name="ZigbeeLens Issues",
            state=count_state(issues),
            attributes={**base_attrs, "lens_bucket": overall_bucket},
        ),
        SummaryEntityState(
            key="unavailable",
            name="ZigbeeLens Unavailable Devices",
            state=count_state(counts[LensBucket.unavailable.value]),
            attributes=base_attrs,
        ),
        SummaryEntityState(
            key="needs_attention",
            name="ZigbeeLens Needs Attention",
            state=count_state(counts[LensBucket.needs_attention.value]),
            attributes=base_attrs,
        ),
        SummaryEntityState(
            key="recently_unstable",
            name="ZigbeeLens Recently Unstable",
            state=count_state(counts[LensBucket.recently_unstable.value]),
            attributes=base_attrs,
        ),
        SummaryEntityState(
            key="diagnostics_limited",
            name="ZigbeeLens Diagnostics Limited",
            state=count_state(counts[LensBucket.diagnostics_limited.value]),
            attributes=base_attrs,
        ),
    ]
