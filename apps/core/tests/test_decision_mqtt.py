"""Decision MQTT summary presentation tests."""

from __future__ import annotations

from zigbeelens.presentation.decision_mqtt import build_summary_entities, count_state
from zigbeelens.schemas import (
    DecisionCountSummary,
    DashboardPayload,
)


def _dashboard(*, overall: str = "watch", counts: dict | None = None) -> DashboardPayload:
    return DashboardPayload(
        generated_at="2026-06-14T12:00:00+00:00",
        active_incident_count=1,
        watching_incident_count=0,
        network_count=1,
        device_count=4,
        unavailable_device_count=2,
        networks=[],
        router_risks=[],
        recent_timeline=[],
        decision_summary=DecisionCountSummary(
            subject_count=4,
            overall_status=overall,
            highest_priority="medium",
            status_counts=counts
            or {
                "review_first": 1,
                "worth_reviewing": 1,
                "watch": 2,
            },
            priority_counts={"high": 1, "medium": 1, "low": 2},
            coverage_warning_count=3,
        ),
        data_coverage_warnings=[],
    )


def test_count_state_unknown_vs_zero():
    assert count_state(0, observable=True) == "0"
    assert count_state(0, observable=False) == "unknown"
    assert count_state(None, observable=True) == "unknown"


def test_build_summary_entities_decision_keys():
    entities = build_summary_entities(
        _dashboard(),
        core_version="0.1.0",
        collector_connected=True,
        mock_mode=False,
    )
    keys = [e.key for e in entities]
    assert keys == [
        "decision_status",
        "review_first",
        "worth_reviewing",
        "coverage_warnings",
        "active_incidents",
        "unavailable",
    ]
    by_key = {e.key: e for e in entities}
    assert by_key["decision_status"].state == "watch"
    assert by_key["review_first"].state == "1"
    assert by_key["worth_reviewing"].state == "1"
    assert by_key["coverage_warnings"].state == "3"
    assert by_key["active_incidents"].state == "1"
    assert by_key["unavailable"].state == "2"
    assert "lens_bucket" not in by_key["decision_status"].attributes
    assert by_key["decision_status"].attributes["decision_contract_version"] == 2


def test_unobservable_estate_uses_unknown_counts():
    entities = build_summary_entities(
        _dashboard(overall="review_first"),
        core_version="0.1.0",
        collector_connected=False,
        mock_mode=False,
    )
    by_key = {e.key: e for e in entities}
    assert by_key["decision_status"].state == "data_unavailable"
    assert by_key["review_first"].state == "unknown"
    assert by_key["unavailable"].state == "unknown"
    attrs = by_key["decision_status"].attributes
    assert attrs["observation_reliable"] is False
    # Stale decision/count attributes must be omitted while unobservable.
    for key in (
        "highest_priority",
        "status_counts",
        "priority_counts",
        "coverage_warning_count",
        "active_incident_count",
        "unavailable_device_count",
    ):
        assert key not in attrs
