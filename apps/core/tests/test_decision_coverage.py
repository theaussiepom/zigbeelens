"""Tests for shared data-coverage helpers."""

from __future__ import annotations

from zigbeelens.decisions.coverage import (
    availability_available,
    availability_history_building,
    availability_status_unknown,
    availability_tracking_off,
    battery_history_sparse,
    ha_areas_not_linked,
    last_seen_available,
    lqi_history_sparse,
    route_hints_unavailable,
    snapshot_stale,
    topology_history_available,
    topology_history_not_observed,
    topology_history_sparse,
)
from zigbeelens.decisions.types import CoverageDimension, CoverageLabelCode, CoverageState


def test_availability_tracking_off():
    coverage = availability_tracking_off()
    assert coverage.dimension is CoverageDimension.availability
    assert coverage.state is CoverageState.off
    assert coverage.label_code is CoverageLabelCode.availability_tracking_off


def test_availability_available():
    coverage = availability_available()
    assert coverage.dimension is CoverageDimension.availability
    assert coverage.state is CoverageState.available
    assert coverage.label_code is CoverageLabelCode.availability_available


def test_availability_history_building():
    coverage = availability_history_building(earliest_at="2026-07-08T00:00:00Z")
    assert coverage.state is CoverageState.building
    assert coverage.label_code is CoverageLabelCode.availability_history_building
    assert coverage.params["earliest_at"] == "2026-07-08T00:00:00Z"


def test_availability_status_unknown():
    coverage = availability_status_unknown()
    assert coverage.state is CoverageState.unknown
    assert coverage.label_code is CoverageLabelCode.availability_status_unknown


def test_route_hints_unavailable():
    coverage = route_hints_unavailable()
    assert coverage.dimension is CoverageDimension.route_hints
    assert coverage.label_code is CoverageLabelCode.route_hints_unavailable


def test_ha_areas_not_linked():
    coverage = ha_areas_not_linked()
    assert coverage.dimension is CoverageDimension.ha_enrichment
    assert coverage.state is CoverageState.not_configured
    assert coverage.label_code is CoverageLabelCode.ha_areas_not_linked


def test_snapshot_stale():
    coverage = snapshot_stale(age_hours=36)
    assert coverage.dimension is CoverageDimension.topology_snapshot
    assert coverage.state is CoverageState.stale
    assert coverage.label_code is CoverageLabelCode.snapshot_stale
    assert coverage.params["age_hours"] == 36


def test_battery_history_sparse():
    coverage = battery_history_sparse(sample_count=2)
    assert coverage.dimension is CoverageDimension.battery
    assert coverage.state is CoverageState.sparse
    assert coverage.label_code is CoverageLabelCode.battery_history_sparse


def test_lqi_history_sparse():
    coverage = lqi_history_sparse(sample_count=1)
    assert coverage.dimension is CoverageDimension.linkquality
    assert coverage.state is CoverageState.sparse
    assert coverage.label_code is CoverageLabelCode.lqi_history_sparse


def test_last_seen_available():
    coverage = last_seen_available()
    assert coverage.dimension is CoverageDimension.last_seen
    assert coverage.state is CoverageState.available
    assert coverage.label_code is CoverageLabelCode.last_seen_available


def test_topology_history_available():
    coverage = topology_history_available(
        observed_snapshot_count=2,
        snapshot_window_count=2,
    )
    assert coverage.dimension is CoverageDimension.historical_snapshots
    assert coverage.state is CoverageState.available
    assert coverage.label_code is CoverageLabelCode.topology_history_available
    assert coverage.params == {
        "observed_snapshot_count": 2,
        "snapshot_window_count": 2,
    }


def test_topology_history_sparse():
    coverage = topology_history_sparse(
        observed_snapshot_count=2,
        snapshot_window_count=10,
    )
    assert coverage.dimension is CoverageDimension.historical_snapshots
    assert coverage.state is CoverageState.sparse
    assert coverage.label_code is CoverageLabelCode.topology_history_sparse
    assert coverage.params == {
        "observed_snapshot_count": 2,
        "snapshot_window_count": 10,
    }


def test_topology_history_not_observed():
    coverage = topology_history_not_observed(
        observed_snapshot_count=0,
        snapshot_window_count=10,
    )
    assert coverage.dimension is CoverageDimension.historical_snapshots
    assert coverage.state is CoverageState.not_observed
    assert coverage.label_code is CoverageLabelCode.topology_history_not_observed
    assert coverage.params == {
        "observed_snapshot_count": 0,
        "snapshot_window_count": 10,
    }


def test_coverage_helpers_are_side_effect_free():
    first = availability_tracking_off()
    second = availability_tracking_off()
    first.params["mutated"] = True
    assert "mutated" not in second.params
