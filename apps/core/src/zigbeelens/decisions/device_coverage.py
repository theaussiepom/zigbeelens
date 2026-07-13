"""Per-device evidence coverage evaluation (Phase 4C-1).

Composes dimension-specific coverage statements for one device from stored
evidence. Outputs coded DataCoverage facts only — presenters map labels.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from zigbeelens.decisions import coverage as coverage_helpers
from zigbeelens.decisions.availability_tracking import availability_tracking_enabled_now
from zigbeelens.decisions.topology_facts import normalize_device_ieee
from zigbeelens.decisions.types import CoverageDimension, DataCoverage
from zigbeelens.topology.device_compare import MAX_SNAPSHOT_HISTORY

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
    current_availability: str | None = None
    last_seen: datetime | None = None
    last_payload_at: datetime | None = None
    battery_history_applicable: bool = False
    battery_sample_count: int = 0
    lqi_sample_count: int = 0
    topology_observed_snapshot_count: int = 0
    topology_snapshot_window_count: int = 0
    ha_area_id: str | None = None
    ha_area_name: str | None = None


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


def _usable_ha_area_value(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def _topology_observation_counts(
    repo: Repository,
    network_id: str,
    device_ieee: str,
) -> tuple[int, int]:
    window = [
        snapshot
        for snapshot in repo.topology.list_topology_snapshots(network_id)
        if snapshot.get("status") == "complete"
    ][:MAX_SNAPSHOT_HISTORY]
    observed = 0
    for snapshot in window:
        nodes = repo.topology.list_topology_nodes(snapshot["snapshot_id"])
        if any(
            normalize_device_ieee(node.get("ieee_address")) == device_ieee for node in nodes
        ):
            observed += 1
    return observed, len(window)


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

    snapshots = repo.devices.list_device_snapshots(network_id, device, limit=MAX_SNAPSHOT_HISTORY)
    battery_sample_count = _count_snapshot_field(snapshots, "battery")
    lqi_sample_count = _count_snapshot_field(snapshots, "linkquality")
    device_changes = repo.availability.list_availability_changes(network_id, device, limit=1)
    ha_enrichment = repo.get_ha_device_enrichment(network_id, device)
    topology_observed, topology_window = _topology_observation_counts(repo, network_id, device)

    return DeviceCoverageEvidence(
        network_id=network_id,
        device_ieee=device,
        availability_tracking_enabled=availability_tracking_enabled_now(repo, network_id),
        has_device_availability_history=bool(device_changes),
        current_availability=row.availability,
        last_seen=_parse_ts(row.last_seen),
        last_payload_at=_parse_ts(row.last_payload_at),
        battery_history_applicable=(
            row.power_source == "Battery"
            or row.battery is not None
            or battery_sample_count > 0
        ),
        battery_sample_count=battery_sample_count,
        lqi_sample_count=lqi_sample_count,
        topology_observed_snapshot_count=topology_observed,
        topology_snapshot_window_count=topology_window,
        ha_area_id=ha_enrichment.get("area_id") if ha_enrichment else None,
        ha_area_name=ha_enrichment.get("area_name") if ha_enrichment else None,
    )


def _topology_history_params(evidence: DeviceCoverageEvidence) -> dict[str, int]:
    return {
        "observed_snapshot_count": evidence.topology_observed_snapshot_count,
        "snapshot_window_count": evidence.topology_snapshot_window_count,
    }


def build_device_coverage(evidence: DeviceCoverageEvidence) -> list[DataCoverage]:
    """Compose per-device coverage items from bounded evidence."""
    items: list[DataCoverage] = []

    if not evidence.availability_tracking_enabled:
        items.append(coverage_helpers.availability_tracking_off())
    elif evidence.current_availability in ("online", "offline"):
        items.append(coverage_helpers.availability_available())
    elif not evidence.has_device_availability_history:
        items.append(coverage_helpers.availability_history_building())
    else:
        items.append(coverage_helpers.availability_status_unknown())

    if evidence.last_seen is not None:
        items.append(coverage_helpers.last_seen_available())
    else:
        items.append(coverage_helpers.last_seen_unknown())

    if evidence.last_payload_at is not None:
        items.append(coverage_helpers.last_payload_available())
    else:
        items.append(coverage_helpers.last_payload_unknown())

    if evidence.battery_history_applicable:
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

    topology_params = _topology_history_params(evidence)
    if (
        evidence.topology_snapshot_window_count == 0
        or evidence.topology_observed_snapshot_count == 0
    ):
        items.append(coverage_helpers.topology_history_not_observed(**topology_params))
    elif (
        evidence.topology_observed_snapshot_count
        < evidence.topology_snapshot_window_count
    ):
        items.append(coverage_helpers.topology_history_sparse(**topology_params))
    else:
        items.append(coverage_helpers.topology_history_available(**topology_params))

    # Usable assignment matches Phase 3E network HA coverage: trimmed area_id OR area_name.
    usable_area_id = _usable_ha_area_value(evidence.ha_area_id)
    usable_area_name = _usable_ha_area_value(evidence.ha_area_name)
    if usable_area_id or usable_area_name:
        area_params: dict[str, str] = {}
        if usable_area_id:
            area_params["area_id"] = usable_area_id
        if usable_area_name:
            area_params["area_name"] = usable_area_name
        items.append(coverage_helpers.ha_area_linked(**area_params))
    else:
        items.append(coverage_helpers.ha_areas_not_linked())

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
