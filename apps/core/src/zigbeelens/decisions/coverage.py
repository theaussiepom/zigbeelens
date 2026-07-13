"""Deterministic helpers for shared data-coverage statements."""

from __future__ import annotations

from typing import Any

from zigbeelens.decisions.types import (
    CoverageDimension,
    CoverageLabelCode,
    CoverageState,
    DataCoverage,
)


def _coverage(
    *,
    dimension: CoverageDimension,
    state: CoverageState,
    label_code: CoverageLabelCode,
    params: dict[str, Any] | None = None,
) -> DataCoverage:
    return DataCoverage(
        dimension=dimension,
        state=state,
        label_code=label_code,
        params=params or {},
    )


def availability_tracking_off(**params: Any) -> DataCoverage:
    return _coverage(
        dimension=CoverageDimension.availability,
        state=CoverageState.off,
        label_code=CoverageLabelCode.availability_tracking_off,
        params=params or None,
    )


def availability_history_building(**params: Any) -> DataCoverage:
    return _coverage(
        dimension=CoverageDimension.availability,
        state=CoverageState.building,
        label_code=CoverageLabelCode.availability_history_building,
        params=params or None,
    )


def availability_status_unknown(**params: Any) -> DataCoverage:
    return _coverage(
        dimension=CoverageDimension.availability,
        state=CoverageState.unknown,
        label_code=CoverageLabelCode.availability_status_unknown,
        params=params or None,
    )


def availability_available(**params: Any) -> DataCoverage:
    return _coverage(
        dimension=CoverageDimension.availability,
        state=CoverageState.available,
        label_code=CoverageLabelCode.availability_available,
        params=params or None,
    )


def route_hints_unavailable(**params: Any) -> DataCoverage:
    return _coverage(
        dimension=CoverageDimension.route_hints,
        state=CoverageState.not_observed,
        label_code=CoverageLabelCode.route_hints_unavailable,
        params=params or None,
    )


def ha_areas_not_linked(**params: Any) -> DataCoverage:
    return _coverage(
        dimension=CoverageDimension.ha_enrichment,
        state=CoverageState.not_configured,
        label_code=CoverageLabelCode.ha_areas_not_linked,
        params=params or None,
    )


def snapshot_stale(**params: Any) -> DataCoverage:
    return _coverage(
        dimension=CoverageDimension.topology_snapshot,
        state=CoverageState.stale,
        label_code=CoverageLabelCode.snapshot_stale,
        params=params or None,
    )


def battery_history_sparse(**params: Any) -> DataCoverage:
    return _coverage(
        dimension=CoverageDimension.battery,
        state=CoverageState.sparse,
        label_code=CoverageLabelCode.battery_history_sparse,
        params=params or None,
    )


def lqi_history_sparse(**params: Any) -> DataCoverage:
    return _coverage(
        dimension=CoverageDimension.linkquality,
        state=CoverageState.sparse,
        label_code=CoverageLabelCode.lqi_history_sparse,
        params=params or None,
    )


def last_seen_available(**params: Any) -> DataCoverage:
    return _coverage(
        dimension=CoverageDimension.last_seen,
        state=CoverageState.available,
        label_code=CoverageLabelCode.last_seen_available,
        params=params or None,
    )


def last_seen_unknown(**params: Any) -> DataCoverage:
    return _coverage(
        dimension=CoverageDimension.last_seen,
        state=CoverageState.unknown,
        label_code=CoverageLabelCode.last_seen_unknown,
        params=params or None,
    )


def last_payload_available(**params: Any) -> DataCoverage:
    return _coverage(
        dimension=CoverageDimension.last_payload,
        state=CoverageState.available,
        label_code=CoverageLabelCode.last_payload_available,
        params=params or None,
    )


def last_payload_unknown(**params: Any) -> DataCoverage:
    return _coverage(
        dimension=CoverageDimension.last_payload,
        state=CoverageState.unknown,
        label_code=CoverageLabelCode.last_payload_unknown,
        params=params or None,
    )


def battery_history_available(**params: Any) -> DataCoverage:
    return _coverage(
        dimension=CoverageDimension.battery,
        state=CoverageState.available,
        label_code=CoverageLabelCode.battery_history_available,
        params=params or None,
    )


def lqi_history_available(**params: Any) -> DataCoverage:
    return _coverage(
        dimension=CoverageDimension.linkquality,
        state=CoverageState.available,
        label_code=CoverageLabelCode.lqi_history_available,
        params=params or None,
    )


def topology_history_available(
    *,
    observed_snapshot_count: int,
    snapshot_window_count: int,
    **params: Any,
) -> DataCoverage:
    return _coverage(
        dimension=CoverageDimension.historical_snapshots,
        state=CoverageState.available,
        label_code=CoverageLabelCode.topology_history_available,
        params={
            "observed_snapshot_count": observed_snapshot_count,
            "snapshot_window_count": snapshot_window_count,
            **params,
        },
    )


def topology_history_sparse(
    *,
    observed_snapshot_count: int,
    snapshot_window_count: int,
    **params: Any,
) -> DataCoverage:
    return _coverage(
        dimension=CoverageDimension.historical_snapshots,
        state=CoverageState.sparse,
        label_code=CoverageLabelCode.topology_history_sparse,
        params={
            "observed_snapshot_count": observed_snapshot_count,
            "snapshot_window_count": snapshot_window_count,
            **params,
        },
    )


def topology_history_not_observed(
    *,
    observed_snapshot_count: int,
    snapshot_window_count: int,
    **params: Any,
) -> DataCoverage:
    return _coverage(
        dimension=CoverageDimension.historical_snapshots,
        state=CoverageState.not_observed,
        label_code=CoverageLabelCode.topology_history_not_observed,
        params={
            "observed_snapshot_count": observed_snapshot_count,
            "snapshot_window_count": snapshot_window_count,
            **params,
        },
    )


def ha_area_linked(**params: Any) -> DataCoverage:
    return _coverage(
        dimension=CoverageDimension.ha_enrichment,
        state=CoverageState.available,
        label_code=CoverageLabelCode.ha_area_linked,
        params=params or None,
    )
