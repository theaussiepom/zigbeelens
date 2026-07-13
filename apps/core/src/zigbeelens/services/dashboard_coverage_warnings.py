"""Compose Overview data-coverage warnings (Phase 5A-3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zigbeelens.decisions.availability_tracking import availability_tracking_enabled_now
from zigbeelens.decisions.coverage import availability_history_building
from zigbeelens.decisions.topology_coverage import build_network_topology_coverage
from zigbeelens.decisions.types import CoverageLabelCode, CoverageState, DataCoverage
from zigbeelens.schemas import DataCoverageWarningSummary
from zigbeelens.services.evidence_graph import EvidenceGraphService
from zigbeelens.services.topology_facts_composition import topology_stale_threshold_hours

if TYPE_CHECKING:
    from zigbeelens.config.models import AppConfig
    from zigbeelens.storage.repository import NetworkRow, Repository

MAX_OVERVIEW_COVERAGE_WARNINGS = 4

_OVERVIEW_ALLOWED_LABELS = frozenset(
    {
        CoverageLabelCode.availability_tracking_off,
        CoverageLabelCode.availability_history_building,
        CoverageLabelCode.availability_status_unknown,
        CoverageLabelCode.snapshot_stale,
        CoverageLabelCode.route_hints_unavailable,
    }
)

_STATE_PRIORITY: dict[str, int] = {
    CoverageState.off.value: 0,
    CoverageState.unknown.value: 1,
    CoverageState.stale.value: 2,
    CoverageState.building.value: 3,
    CoverageState.sparse.value: 4,
    CoverageState.not_configured.value: 5,
    CoverageState.not_observed.value: 6,
    CoverageState.available.value: 7,
}


def _warning_id(network_id: str, label_code: str) -> str:
    return f"coverage-{network_id}-{label_code}"


def _coverage_to_summary(
    network_id: str,
    item: DataCoverage,
) -> DataCoverageWarningSummary:
    label_code = str(item.label_code)
    return DataCoverageWarningSummary(
        id=_warning_id(network_id, label_code),
        network_id=network_id,
        dimension=str(item.dimension),
        state=str(item.state),
        label_code=label_code,
        scope_type="network",
        params=dict(item.params or {}),
    )


def compose_dashboard_coverage_warnings(
    repo: Repository,
    networks: list[NetworkRow],
    config: AppConfig,
    *,
    investigation_network_ids: set[str] | None = None,
) -> list[DataCoverageWarningSummary]:
    """Compose Overview-relevant coverage warnings from existing evaluators."""
    investigation_network_ids = investigation_network_ids or set()
    service = EvidenceGraphService(repo)
    stale_after_hours = topology_stale_threshold_hours(config)
    summaries: list[DataCoverageWarningSummary] = []

    for network in networks:
        tracking_enabled = availability_tracking_enabled_now(repo, network.id)
        graph = service.build(network.id)
        facts = service.build_topology_facts(
            network.id,
            evidence_graph=graph,
            stale_after_hours=stale_after_hours,
        )
        coverage_items = list(
            build_network_topology_coverage(
                facts.network_facts,
                tracking_enabled_now=tracking_enabled,
                has_known_devices=bool(repo.list_devices(network.id)),
                has_usable_ha_area_assignments=repo.network_has_usable_ha_area_assignments(
                    network.id
                ),
            )
        )

        earliest = repo.availability.get_earliest_availability_change_at(network.id)
        if tracking_enabled and earliest is None:
            coverage_items.append(availability_history_building())

        for item in coverage_items:
            try:
                code = CoverageLabelCode(str(item.label_code))
            except ValueError:
                continue
            if code not in _OVERVIEW_ALLOWED_LABELS:
                continue
            if (
                code == CoverageLabelCode.route_hints_unavailable
                and network.id not in investigation_network_ids
            ):
                continue
            summaries.append(_coverage_to_summary(network.id, item))

    summaries.sort(
        key=lambda warning: (
            _STATE_PRIORITY.get(warning.state, 99),
            warning.label_code,
            warning.network_id,
            warning.id,
        )
    )
    return summaries[:MAX_OVERVIEW_COVERAGE_WARNINGS]
