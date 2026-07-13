"""Deterministic topology coverage composition for network evidence surfaces."""

from __future__ import annotations

from typing import Any

from zigbeelens.decisions import coverage as coverage_helpers
from zigbeelens.decisions.topology_facts import TopologyFactCode
from zigbeelens.decisions.types import CoverageLabelCode, DataCoverage, EvidenceFact

_COVERAGE_ORDER: tuple[CoverageLabelCode, ...] = (
    CoverageLabelCode.availability_tracking_off,
    CoverageLabelCode.availability_history_building,
    CoverageLabelCode.availability_status_unknown,
    CoverageLabelCode.snapshot_stale,
    CoverageLabelCode.route_hints_unavailable,
    CoverageLabelCode.ha_areas_not_linked,
    CoverageLabelCode.battery_history_sparse,
    CoverageLabelCode.lqi_history_sparse,
)

_ORDER_INDEX = {code: index for index, code in enumerate(_COVERAGE_ORDER)}


def _network_fact_codes(network_facts: list[EvidenceFact]) -> set[str]:
    return {str(fact.code) for fact in network_facts}


def _stale_fact_params(network_facts: list[EvidenceFact]) -> dict[str, Any]:
    for fact in network_facts:
        if str(fact.code) == TopologyFactCode.latest_snapshot_stale:
            return dict(fact.params)
    return {}


def build_network_topology_coverage(
    network_facts: list[EvidenceFact],
    *,
    tracking_enabled_now: bool,
    has_known_devices: bool,
    has_usable_ha_area_assignments: bool,
) -> list[DataCoverage]:
    """Compose network-level coverage items from established topology facts.

    Snapshot staleness and route-hint availability follow topology fact
    composition only. Availability history building and status unknown are
    snapshot-period states and are not emitted at network scope here.
    """
    items: list[DataCoverage] = []
    fact_codes = _network_fact_codes(network_facts)

    if not tracking_enabled_now:
        items.append(coverage_helpers.availability_tracking_off())

    if TopologyFactCode.latest_snapshot_stale in fact_codes:
        items.append(coverage_helpers.snapshot_stale(**_stale_fact_params(network_facts)))

    if TopologyFactCode.route_hints_unavailable in fact_codes:
        items.append(coverage_helpers.route_hints_unavailable())

    if has_known_devices and not has_usable_ha_area_assignments:
        items.append(coverage_helpers.ha_areas_not_linked())

    return sort_topology_coverage(items)


def sort_topology_coverage(items: list[DataCoverage]) -> list[DataCoverage]:
    """Return coverage items in the product display order."""
    return sorted(
        items,
        key=lambda item: (
            _ORDER_INDEX.get(item.label_code, len(_COVERAGE_ORDER)),
            item.label_code,
        ),
    )
