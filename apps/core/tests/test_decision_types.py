"""Tests for shared decision-engine types."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from zigbeelens.decisions.types import (
    CoverageDimension,
    CoverageLabelCode,
    CoverageState,
    DataCoverage,
    Decision,
    DecisionBundle,
    DecisionLimitation,
    DecisionPriority,
    DecisionReason,
    DecisionStatus,
    EvidenceFact,
    EvidenceReference,
    SuggestedCheck,
    TopologyHistoryCoverageParams,
    classify_topology_history_params,
)


def test_decision_status_serialisation_is_stable():
    assert DecisionStatus.worth_reviewing.value == "worth_reviewing"
    assert DecisionStatus("watch") is DecisionStatus.watch


def test_decision_priority_serialisation_is_stable():
    assert DecisionPriority.none.value == "none"
    assert DecisionPriority.high.value == "high"


def test_default_lists_are_not_shared_mutable_state():
    first = Decision(subject_type="device", subject_id="0x01", status=DecisionStatus.watch)
    second = Decision(subject_type="device", subject_id="0x02", status=DecisionStatus.changed)
    first.reasons.append(DecisionReason(code="battery_low"))
    assert second.reasons == []


def test_decision_round_trip_includes_all_fields():
    captured_at = datetime(2026, 7, 10, 6, 0, tzinfo=timezone.utc)
    decision = Decision(
        subject_type="device",
        subject_id="0x0abc",
        status=DecisionStatus.worth_reviewing,
        priority=DecisionPriority.medium,
        reasons=[DecisionReason(code="latest_snapshot_no_links", params={"link_count": 0})],
        evidence=[
            EvidenceReference(
                source="topology_snapshot",
                id="snap-1",
                captured_at=captured_at,
                label="Latest snapshot",
            )
        ],
        limitations=[DecisionLimitation(code="route_hints_not_live_routing")],
        suggested_checks=[SuggestedCheck(code="confirm_powered")],
        coverage=[],
    )
    payload = decision.model_dump(mode="json")
    restored = Decision.model_validate(payload)
    assert restored == decision
    assert restored.evidence[0].captured_at == captured_at


def test_evidence_fact_accepts_none_params_not_zero():
    fact = EvidenceFact(code="device_link_count", params={"count": None})
    assert fact.params["count"] is None


def test_decision_bundle_groups_decisions():
    bundle = DecisionBundle(
        subject_type="device",
        subject_id="0x01",
        decisions=[
            Decision(subject_type="device", subject_id="0x01", status=DecisionStatus.watch),
            Decision(
                subject_type="device",
                subject_id="0x01",
                status=DecisionStatus.improve_data_coverage,
            ),
        ],
    )
    assert len(bundle.decisions) == 2


def test_data_coverage_unknown_stays_unknown_not_unavailable():
    coverage = DataCoverage.model_validate(
        {
            "dimension": "availability",
            "state": "unknown",
            "label_code": "availability_status_unknown",
        }
    )
    assert coverage.state.value == "unknown"


def test_topology_history_coverage_params_own_exact_count_arithmetic():
    params = TopologyHistoryCoverageParams(
        observed_snapshot_count=2,
        complete_snapshot_count=4,
        available_layout_snapshot_count=3,
        limited_layout_snapshot_count=1,
        snapshot_window_count=4,
    )

    assert params.model_dump() == {
        "observed_snapshot_count": 2,
        "complete_snapshot_count": 4,
        "available_layout_snapshot_count": 3,
        "limited_layout_snapshot_count": 1,
        "snapshot_window_count": 4,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"observed_snapshot_count": True},
        {"complete_snapshot_count": -1},
        {"available_layout_snapshot_count": 4},
        {"observed_snapshot_count": 4},
        {"snapshot_window_count": 2},
    ],
)
def test_topology_history_coverage_params_reject_malformed_counts(changes):
    payload = {
        "observed_snapshot_count": 2,
        "complete_snapshot_count": 4,
        "available_layout_snapshot_count": 3,
        "limited_layout_snapshot_count": 1,
        "snapshot_window_count": 4,
        **changes,
    }

    with pytest.raises(ValidationError):
        TopologyHistoryCoverageParams.model_validate(payload)


def test_topology_history_coverage_params_require_every_exact_count():
    payload = TopologyHistoryCoverageParams.empty().model_dump()
    payload.pop("limited_layout_snapshot_count")

    with pytest.raises(ValidationError):
        TopologyHistoryCoverageParams.model_validate(payload)


@pytest.mark.parametrize(
    ("counts", "state", "label_code"),
    [
        ((0, 0, 0), CoverageState.not_observed, "topology_history_not_observed"),
        ((0, 0, 2), CoverageState.unknown, "topology_history_unavailable"),
        ((1, 1, 1), CoverageState.sparse, "topology_history_sparse"),
        ((0, 2, 0), CoverageState.not_observed, "topology_history_not_observed"),
        ((1, 2, 0), CoverageState.sparse, "topology_history_sparse"),
        ((2, 2, 0), CoverageState.available, "topology_history_available"),
    ],
)
def test_data_coverage_types_and_validates_topology_history_matrix(
    counts,
    state,
    label_code,
):
    observed, available, limited = counts
    complete = available + limited
    raw_params = {
        "observed_snapshot_count": observed,
        "complete_snapshot_count": complete,
        "available_layout_snapshot_count": available,
        "limited_layout_snapshot_count": limited,
        "snapshot_window_count": complete,
    }

    coverage = DataCoverage.model_validate(
        {
            "dimension": "historical_snapshots",
            "state": state,
            "label_code": label_code,
            "params": raw_params,
        }
    )

    assert isinstance(coverage.params, TopologyHistoryCoverageParams)
    assert coverage.params.model_dump() == raw_params
    assert classify_topology_history_params(coverage.params) == (
        state,
        CoverageLabelCode(label_code),
    )
    assert coverage.model_dump(mode="json")["params"] == raw_params


@pytest.mark.parametrize(
    "changes",
    [
        {"dimension": CoverageDimension.availability},
        {"state": CoverageState.sparse},
        {"label_code": CoverageLabelCode.topology_history_sparse},
        {"label_code": CoverageLabelCode.battery_history_available},
        {"params": {"observed_snapshot_count": 1}},
        {
            "params": {
                "observed_snapshot_count": True,
                "complete_snapshot_count": 1,
                "available_layout_snapshot_count": 1,
                "limited_layout_snapshot_count": 0,
                "snapshot_window_count": 1,
            }
        },
    ],
)
def test_data_coverage_rejects_malformed_topology_history(changes):
    payload = {
        "dimension": CoverageDimension.historical_snapshots,
        "state": CoverageState.available,
        "label_code": CoverageLabelCode.topology_history_available,
        "params": {
            "observed_snapshot_count": 1,
            "complete_snapshot_count": 1,
            "available_layout_snapshot_count": 1,
            "limited_layout_snapshot_count": 0,
            "snapshot_window_count": 1,
        },
        **changes,
    }

    with pytest.raises(ValidationError):
        DataCoverage.model_validate(payload)


def test_data_coverage_rejects_topology_label_on_non_historical_dimension():
    with pytest.raises(ValidationError):
        DataCoverage.model_validate(
            {
                "dimension": CoverageDimension.availability,
                "state": CoverageState.available,
                "label_code": CoverageLabelCode.topology_history_available,
                "params": TopologyHistoryCoverageParams.empty().model_dump(),
            }
        )


def test_non_topology_coverage_params_remain_generic_dicts():
    params = TopologyHistoryCoverageParams.empty().model_dump()
    coverage = DataCoverage(
        dimension=CoverageDimension.battery,
        state=CoverageState.available,
        label_code=CoverageLabelCode.battery_history_available,
        params=params,
    )

    assert type(coverage.params) is dict
    assert coverage.params == params


def test_decisions_package_exports_public_model_pattern_symbols():
    import zigbeelens.decisions as decisions

    for symbol in (
        "ModelPatternSignal",
        "ObservedModelPattern",
        "ObservedModelPatternState",
        "ObservedModelPatterns",
        "build_observed_model_patterns",
        "observed_model_patterns_for_network",
    ):
        assert symbol in decisions.__all__
        assert hasattr(decisions, symbol)


def test_decisions_package_exports_public_router_area_symbols():
    import zigbeelens.decisions as decisions

    for symbol in (
        "HeadlineCode",
        "ObservedRouterArea",
        "ObservedRouterAreaState",
        "ObservedRouterAreas",
        "RouterAreaHAAreaContext",
        "build_observed_router_areas",
        "ha_area_context_for_members",
        "observed_router_areas_for_network",
    ):
        assert symbol in decisions.__all__
        assert hasattr(decisions, symbol)
