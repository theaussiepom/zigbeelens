"""Temporary Lens MQTT bridge until Track 5 Commit 5 decision MQTT lands.

Maps DecisionCountSummary onto the existing Lens entity keys so discovery
keeps compiling. Commit 5 replaces this module with decision_mqtt.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from zigbeelens.presentation.lens_buckets import BUCKET_LABELS, LensBucket
from zigbeelens.schemas import DashboardPayload
from zigbeelens.storage.repository import utc_now_iso

PRODUCT = "zigbeelens"
REDACTION_PROFILE = "public_safe"

_STATUS_TO_BUCKET = {
    "review_first": LensBucket.needs_attention.value,
    "worth_reviewing": LensBucket.needs_attention.value,
    "improve_data_coverage": LensBucket.diagnostics_limited.value,
    "watch": LensBucket.recently_unstable.value,
    "changed": LensBucket.informational.value,
    "informational": LensBucket.informational.value,
    "no_notable_change": LensBucket.healthy.value,
    "data_unavailable": LensBucket.unknown.value,
}


def severity_to_lens_bucket(severity: Any) -> str:
    """Compatibility shim — prefer decision status mapping."""
    del severity
    return LensBucket.unknown.value


def _status_counts(dashboard: DashboardPayload) -> dict[str, int]:
    return {
        str(k): int(v)
        for k, v in (dashboard.decision_summary.status_counts or {}).items()
    }


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
    status_counts = _status_counts(dashboard)
    for status, count in status_counts.items():
        bucket = _STATUS_TO_BUCKET.get(status, LensBucket.unknown.value)
        counts[bucket] = counts.get(bucket, 0) + count
    counts[LensBucket.unavailable.value] = dashboard.unavailable_device_count
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
    overall_status = str(dashboard.decision_summary.overall_status)
    overall_bucket = (
        _STATUS_TO_BUCKET.get(overall_status, LensBucket.unknown.value)
        if observable
        else LensBucket.unknown.value
    )
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
        "decision_contract_version": 2,
        "overall_decision_status": overall_status,
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
