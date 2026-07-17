"""Compose Overview data-coverage warnings (Phase 5A-3)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from zigbeelens.decisions.availability_tracking import availability_tracking_enabled_now
from zigbeelens.decisions.topology_coverage import build_network_topology_coverage
from zigbeelens.decisions.topology_facts import build_network_topology_facts
from zigbeelens.decisions.types import CoverageLabelCode, CoverageState, DataCoverage
from zigbeelens.schemas import DataCoverageWarningSummary
from zigbeelens.services.network_evidence import NetworkEvidenceCapability
from zigbeelens.services.topology_facts_composition import topology_stale_threshold_hours

if TYPE_CHECKING:
    from zigbeelens.config.models import AppConfig
    from zigbeelens.storage.repository import NetworkRow, Repository

MAX_OVERVIEW_COVERAGE_WARNINGS = 4

# Network topology coverage may emit these. Building/unknown remain allowed for
# future honest evaluator emission but are not manufactured here.
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


def _latest_route_edge_count(links: list[dict[str, Any]]) -> int:
    return sum(
        1
        for link in links
        if link.get("route_count") is not None and link["route_count"] > 0
    )


def compose_dashboard_coverage_warnings(
    repo: Repository,
    networks: list[NetworkRow],
    config: AppConfig,
    *,
    route_hint_relevant_network_ids: set[str] | None = None,
    now: datetime | None = None,
    network_evidence_contexts: dict | None = None,
) -> list[DataCoverageWarningSummary]:
    """Compose Overview-relevant coverage warnings from latest topology facts.

    Uses snapshot/node/link inputs only — never builds the full Mesh evidence
    graph or re-aggregates historical/last-known/passive investigation evidence.
    """
    route_hint_relevant_network_ids = route_hint_relevant_network_ids or set()
    stale_after_hours = topology_stale_threshold_hours(config)
    summaries: list[DataCoverageWarningSummary] = []

    for network in networks:
        context = (
            network_evidence_contexts.get(network.id)
            if network_evidence_contexts is not None
            else None
        )
        if context is not None:
            reference_now = now if now is not None else context.reference_now
            context.require_compatible(
                network_id=network.id,
                reference_now=reference_now,
                stale_after_hours=stale_after_hours,
            )
            context.require(NetworkEvidenceCapability.coverage)
            assert context.network_topology_coverage is not None
            coverage_items = context.network_topology_coverage
        else:
            topology = repo.topology
            latest = topology.get_latest_topology_snapshot(network.id)
            nodes = topology.list_topology_nodes(latest["snapshot_id"]) if latest else []
            links = topology.list_topology_links(latest["snapshot_id"]) if latest else []
            network_facts = build_network_topology_facts(
                latest_snapshot=latest,
                nodes=nodes,
                links=links,
                counts={
                    "latest_snapshot_route_edges": _latest_route_edge_count(links),
                },
                now=now,
                stale_after_hours=stale_after_hours,
            )
            coverage_items = build_network_topology_coverage(
                network_facts,
                tracking_enabled_now=availability_tracking_enabled_now(repo, network.id),
                has_known_devices=bool(repo.list_devices(network.id)),
                has_usable_ha_area_assignments=repo.network_has_usable_ha_area_assignments(
                    network.id
                ),
            )

        for item in coverage_items:
            try:
                code = CoverageLabelCode(str(item.label_code))
            except ValueError:
                continue
            if code not in _OVERVIEW_ALLOWED_LABELS:
                continue
            if (
                code == CoverageLabelCode.route_hints_unavailable
                and network.id not in route_hint_relevant_network_ids
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
