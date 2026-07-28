"""Per-device evidence coverage evaluation (Phase 4C-1).

Composes dimension-specific coverage statements for one device from stored
evidence. Outputs coded DataCoverage facts only — presenters map labels.
"""

from __future__ import annotations

from datetime import datetime, timezone
from itertools import islice
from typing import TYPE_CHECKING, Any, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field

from zigbeelens.decisions import coverage as coverage_helpers
from zigbeelens.decisions.availability_tracking import availability_tracking_enabled_now
from zigbeelens.decisions.topology_facts import normalize_device_ieee
from zigbeelens.decisions.types import (
    CoverageDimension,
    DataCoverage,
    TopologyHistoryCoverageParams,
)
from zigbeelens.topology.device_compare import MAX_SNAPSHOT_HISTORY

if TYPE_CHECKING:
    from zigbeelens.storage.repository import DeviceRow, Repository

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

    model_config = ConfigDict(extra="forbid")

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
    topology_history: TopologyHistoryCoverageParams = Field(
        default_factory=TopologyHistoryCoverageParams.empty
    )
    ha_area_id: str | None = None
    ha_area_name: str | None = None



def _availability_value(value: Any) -> str | None:
    if value is None:
        return None
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value
    if isinstance(value, str):
        return value
    return None

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


def _topology_layout_contains_device(
    device_ieee: str,
    nodes: Iterable[Mapping[str, Any]],
    links: Iterable[Mapping[str, Any]],
) -> bool:
    """Return whether a stored layout has node or link-endpoint evidence."""
    device = normalize_device_ieee(device_ieee)
    if not device:
        return False
    if any(
        normalize_device_ieee(node.get("ieee_address")) == device for node in nodes
    ):
        return True
    return any(
        device
        in (
            normalize_device_ieee(link.get("source_ieee")),
            normalize_device_ieee(link.get("target_ieee")),
        )
        for link in links
    )


def count_device_topology_history(
    *,
    device_ieee: str,
    usable_snapshots: Iterable[Mapping[str, Any]],
    nodes_by_snapshot_id: Mapping[str, Iterable[Mapping[str, Any]]],
    links_by_snapshot_id: Mapping[str, Iterable[Mapping[str, Any]]],
    layout_available_by_snapshot_id: Mapping[str, bool],
    max_snapshots: int = MAX_SNAPSHOT_HISTORY,
) -> TopologyHistoryCoverageParams:
    """Count exact device evidence over a bounded complete-capture window.

    The explicit layout map owns availability; node/link maps may be filtered
    to the target device and therefore cannot prove that a layout is limited.
    """
    if (
        isinstance(max_snapshots, bool)
        or not isinstance(max_snapshots, int)
        or max_snapshots < 0
    ):
        raise ValueError("max_snapshots must be a non-negative integer")
    device = normalize_device_ieee(device_ieee)
    if not device:
        raise ValueError("device_ieee must be a non-empty IEEE address")

    window = list(
        islice(
            (
                snapshot
                for snapshot in usable_snapshots
                if snapshot.get("status") == "complete"
            ),
            max_snapshots,
        )
    )
    observed = 0
    available = 0
    limited = 0
    seen_snapshot_ids: set[str] = set()
    for snapshot in window:
        snapshot_id = str(snapshot.get("snapshot_id") or "").strip()
        if not snapshot_id:
            raise ValueError("complete topology snapshot is missing snapshot_id")
        if snapshot_id in seen_snapshot_ids:
            raise ValueError(f"duplicate topology snapshot_id {snapshot_id!r}")
        seen_snapshot_ids.add(snapshot_id)

        layout_available = layout_available_by_snapshot_id.get(snapshot_id)
        if not isinstance(layout_available, bool):
            raise ValueError(
                f"topology snapshot {snapshot_id!r} is missing exact layout availability"
            )
        nodes = tuple(nodes_by_snapshot_id.get(snapshot_id, ()))
        links = tuple(links_by_snapshot_id.get(snapshot_id, ()))
        if not layout_available:
            limited += 1
            continue
        available += 1
        if _topology_layout_contains_device(device, nodes, links):
            observed += 1

    complete = len(window)
    return TopologyHistoryCoverageParams(
        observed_snapshot_count=observed,
        complete_snapshot_count=complete,
        available_layout_snapshot_count=available,
        limited_layout_snapshot_count=limited,
        snapshot_window_count=complete,
    )


def _topology_observation_counts_from_context(
    network_evidence_context: Any,
    device_ieee: str,
) -> TopologyHistoryCoverageParams:
    from zigbeelens.services.network_evidence import NetworkEvidenceCapability

    network_evidence_context.require(NetworkEvidenceCapability.snapshot_history)
    network_evidence_context.require(NetworkEvidenceCapability.latest_topology)
    history_context = network_evidence_context.snapshot_history_context
    if history_context is None:
        raise ValueError("NetworkEvidenceContext is missing snapshot_history_context")
    return count_device_topology_history(
        device_ieee=device_ieee,
        usable_snapshots=history_context.usable_snapshots,
        nodes_by_snapshot_id=history_context.nodes_by_snapshot_id,
        links_by_snapshot_id=history_context.links_by_snapshot_id,
        layout_available_by_snapshot_id=(
            history_context.layout_available_by_snapshot_id
        ),
    )


def build_device_coverage_evidence(
    *,
    device_row: DeviceRow,
    tracking_enabled: bool,
    device_snapshots: list[dict[str, Any]],
    availability_changes: list[dict[str, Any]],
    topology_history: TopologyHistoryCoverageParams,
    ha_enrichment: dict[str, Any] | None,
) -> DeviceCoverageEvidence:
    """Compose canonical per-device coverage evidence from loaded facts."""
    device = normalize_device_ieee(device_row.ieee_address)
    battery_sample_count = _count_snapshot_field(device_snapshots, "battery")
    lqi_sample_count = _count_snapshot_field(device_snapshots, "linkquality")
    return DeviceCoverageEvidence(
        network_id=device_row.network_id,
        device_ieee=device,
        availability_tracking_enabled=tracking_enabled,
        has_device_availability_history=bool(availability_changes),
        current_availability=_availability_value(device_row.availability),
        last_seen=_parse_ts(device_row.last_seen),
        last_payload_at=_parse_ts(device_row.last_payload_at),
        battery_history_applicable=(
            device_row.power_source == "Battery"
            or device_row.battery is not None
            or battery_sample_count > 0
        ),
        battery_sample_count=battery_sample_count,
        lqi_sample_count=lqi_sample_count,
        topology_history=topology_history,
        ha_area_id=ha_enrichment.get("area_id") if ha_enrichment else None,
        ha_area_name=ha_enrichment.get("area_name") if ha_enrichment else None,
    )

def load_device_coverage_evidence(
    repo: Repository,
    network_id: str,
    device_ieee: str,
    *,
    network_evidence_context: Any | None = None,
    now: datetime | None = None,
) -> DeviceCoverageEvidence | None:
    """Load bounded stored evidence for device coverage. Returns None when unknown."""
    device = normalize_device_ieee(device_ieee)
    if not device:
        return None

    from zigbeelens.services.network_evidence import (
        DEVICE_COVERAGE_EVIDENCE_REQUIREMENTS,
        NetworkEvidenceCapability,
    )
    from zigbeelens.services.network_evidence_composition import (
        compose_network_evidence_context,
    )

    if network_evidence_context is not None:
        reference_now = (
            now if now is not None else network_evidence_context.reference_now
        )
        if reference_now.tzinfo is None:
            reference_now = reference_now.replace(tzinfo=timezone.utc)
        network_evidence_context.require_compatible(
            network_id=network_id,
            reference_now=reference_now,
        )
        network_evidence_context.require(NetworkEvidenceCapability.devices)
        network_evidence_context.require(NetworkEvidenceCapability.earliest_availability)
        context = network_evidence_context
    else:
        reference_now = now or datetime.now(timezone.utc)
        if reference_now.tzinfo is None:
            reference_now = reference_now.replace(tzinfo=timezone.utc)
        context = compose_network_evidence_context(
            repo,
            network_id,
            reference_now=reference_now,
            requirements=DEVICE_COVERAGE_EVIDENCE_REQUIREMENTS,
        )

    row = context.get_device_row(device)
    if row is None:
        return None

    snapshots = repo.devices.list_device_snapshots(network_id, device, limit=MAX_SNAPSHOT_HISTORY)
    device_changes = repo.availability.list_availability_changes(network_id, device, limit=1)
    ha_enrichment = repo.get_ha_device_enrichment(network_id, device)
    topology_history = _topology_observation_counts_from_context(context, device)
    tracking_enabled = bool(context.availability_tracking_enabled)
    if context.availability_tracking_enabled is None:
        tracking_enabled = availability_tracking_enabled_now(repo, network_id)

    return build_device_coverage_evidence(
        device_row=row,
        tracking_enabled=tracking_enabled,
        device_snapshots=snapshots,
        availability_changes=device_changes,
        topology_history=topology_history,
        ha_enrichment=ha_enrichment,
    )


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

    items.append(
        coverage_helpers.classify_topology_history_coverage(
            evidence.topology_history
        )
    )

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
    *,
    network_evidence_context: Any | None = None,
    now: datetime | None = None,
) -> list[DataCoverage] | None:
    """Evaluate per-device evidence coverage. Returns None when device unknown."""
    evidence = load_device_coverage_evidence(
        repo,
        network_id,
        device_ieee,
        network_evidence_context=network_evidence_context,
        now=now,
    )
    if evidence is None:
        return None
    return build_device_coverage(evidence)
