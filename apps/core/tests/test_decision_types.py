"""Tests for shared decision-engine types."""

from __future__ import annotations

from datetime import datetime, timezone

from zigbeelens.decisions.types import (
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
