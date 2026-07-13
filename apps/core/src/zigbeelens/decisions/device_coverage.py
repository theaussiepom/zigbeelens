"""Per-device evidence coverage evaluation (Phase 4C-1).

Composes dimension-specific coverage statements for one device from stored
evidence. Outputs coded DataCoverage facts only — presenters map labels.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from zigbeelens.decisions import coverage as coverage_helpers
from zigbeelens.decisions.availability_tracking import availability_tracking_enabled_now
from zigbeelens.decisions.topology_facts import normalize_device_ieee
from zigbeelens.decisions.types import CoverageDimension, CoverageLabelCode, DataCoverage
from zigbeelens.topology.device_compare import (
    COVERAGE_UNKNOWN,
    MAX_SNAPSHOT_HISTORY,
    device_snapshot_history,
)

if TYPE_CHECKING:
    from zigbeelens.storage.repository import Repository

# Minimum stored payload snapshots with a value before history is "available".
MIN_HISTORY_SAMPLES = 3

_DEVICE_COVERAGE_ORDER: tuple[CoverageDimension, ...] = (
    CoverageDimension.availability,
    CoverageDimension.last_seen,
    CoverageDimension.last_payload,
    CoverageDimension.battery,
    CoverageDimension.linkquality,
    CoverageDimension.historical_snapshots,
    CoverageDimension.ha_enrichment,
)

_ORDER_INDEX = {dimension: index for index, dimension in enumerate(_DEVICE_COVERAGE_ORDER)}


class DeviceCoverageEvidence(BaseModel):
    """Bounded evidence inputs for one device coverage evaluation."""

    network_id: str
    device_ieee: str
    availability_tracking_enabled: bool = False
    has_device_availability_history: bool = False
    availability_coverage_status: str | None = None
    last_seen: datetime | None = None
    last_payload_at: datetime | None = None
    battery_sample_count: int = 0
    lqi_sample_count: int = 0
    topology_snapshot_count: int = 0
    topology_snapshot_max: int = MAX_SNAPSHOT_HISTORY
    ha_area: str | None = None
    network_has_usable_ha_areas: bool = False


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _count_snapshot_field(samples: list[dict[str, Any]], field: str) -> int:
    count = 0
    seen: set[str] = set()
    for row in samples:
        value = row.get(field)
        if value is None:
            continue
        captured_at = row.get("captured_at")
        key = str(captured_at or value)
        if key in seen:
            continue
        seen.add(key)
        count += 1
    return count


def load_device_coverage_evidence(
    repo: Repository,
    network_id: str,
    device_ieee: str,
) -> DeviceCoverageEvidence | None:
    """Load bounded stored evidence for device coverage. Returns None when unknown."""
    device = normalize_device_ieee(device_ieee)
    if not device:
        return None

    row = repo.devices.get_device(network_id, device)
    if row is None:
        return None

    history = device_snapshot_history(repo, network_id, device)
    latest_row = history.get("latest_snapshot")
    availability_coverage_status = None
    if isinstance(latest_row, dict):
        coverage = latest_row.get("availability_coverage_status")
        if isinstance(coverage, str):
            availability_coverage_status = coverage

    snapshots = repo.devices.list_device_snapshots(network_id, device, limit=MAX_SNAPSHOT_HISTORY)
    usable_topology_snapshots = [
        snapshot
        for snapshot in repo.list_topology_snapshots(network_id)
        if snapshot.get("status") == "complete"
    ][:MAX_SNAPSHOT_HISTORY]

    ha_enrichment = repo.get_ha_device_enrichment(network_id, device)
    device_changes = repo.availability.list_availability_changes(network_id, device, limit=1)

    return DeviceCoverageEvidence(
        network_id=network_id,
        device_ieee=device,
        availability_tracking_enabled=availability_tracking_enabled_now(repo, network_id),
        has_device_availability_history=bool(device_changes),
        availability_coverage_status=availability_coverage_status,
        last_seen=_parse_ts(row.last_seen),
        last_payload_at=_parse_ts(row.last_payload_at),
        battery_sample_count=_count_snapshot_field(snapshots, "battery"),
        lqi_sample_count=_count_snapshot_field(snapshots, "linkquality"),
        topology_snapshot_count=len(usable_topology_snapshots),
        topology_snapshot_max=MAX_SNAPSHOT_HISTORY,
        ha_area=ha_enrichment.get("area_name") if ha_enrichment else None,
        network_has_usable_ha_areas=repo.network_has_usable_ha_area_assignments(network_id),
    )


def build_device_coverage(evidence: DeviceCoverageEvidence) -> list[DataCoverage]:
    """Compose per-device coverage items from bounded evidence."""
    items: list[DataCoverage] = []

    if not evidence.availability_tracking_enabled:
        items.append(coverage_helpers.availability_tracking_off())
    elif not evidence.has_device_availability_history:
        items.append(coverage_helpers.availability_history_building())
    elif evidence.availability_coverage_status == COVERAGE_UNKNOWN:
        items.append(coverage_helpers.availability_status_unknown())

    if evidence.last_seen is not None:
        items.append(coverage_helpers.last_seen_available())
    else:
        items.append(coverage_helpers.last_seen_unknown())

    if evidence.last_payload_at is not None:
        items.append(coverage_helpers.last_payload_available())
    else:
        items.append(coverage_helpers.last_payload_unknown())

    if evidence.battery_sample_count >= MIN_HISTORY_SAMPLES:
        items.append(
            coverage_helpers.battery_history_available(
                sample_count=evidence.battery_sample_count
            )
        )
    else:
        items.append(
            coverage_helpers.battery_history_sparse(
                sample_count=evidence.battery_sample_count
            )
        )

    if evidence.lqi_sample_count >= MIN_HISTORY_SAMPLES:
        items.append(
            coverage_helpers.lqi_history_available(sample_count=evidence.lqi_sample_count)
        )
    else:
        items.append(
            coverage_helpers.lqi_history_sparse(sample_count=evidence.lqi_sample_count)
        )

    items.append(
        coverage_helpers.topology_history_available(
            snapshot_count=evidence.topology_snapshot_count,
            max_snapshots=evidence.topology_snapshot_max,
        )
    )

    if evidence.network_has_usable_ha_areas:
        if evidence.ha_area:
            items.append(coverage_helpers.ha_area_linked(area_name=evidence.ha_area))
        else:
            items.append(coverage_helpers.ha_areas_not_linked())
    elif evidence.ha_area:
        items.append(coverage_helpers.ha_area_linked(area_name=evidence.ha_area))

    return sort_device_coverage(items)


def sort_device_coverage(items: list[DataCoverage]) -> list[DataCoverage]:
    """Return device coverage items in product display order."""
    return sorted(
        items,
        key=lambda item: (
            _ORDER_INDEX.get(item.dimension, len(_DEVICE_COVERAGE_ORDER)),
            item.label_code,
        ),
    )


def device_coverage_for_device(
    repo: Repository,
    network_id: str,
    device_ieee: str,
) -> list[DataCoverage] | None:
    """Evaluate per-device evidence coverage. Returns None when device unknown."""
    evidence = load_device_coverage_evidence(repo, network_id, device_ieee)
    if evidence is None:
        return None
    return build_device_coverage(evidence)
