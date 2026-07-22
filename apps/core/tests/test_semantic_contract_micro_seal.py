"""Track 5 semantic-contract micro-seal regressions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from zigbeelens.decisions.types import DecisionPriority, DecisionStatus
from zigbeelens.schemas import DecisionCountSummary, DeviceDecisionBadge, DeviceDetail
from zigbeelens.services.decision_summary import data_unavailable_device_badge
from zigbeelens.services.network_decision import compose_network_decision
from zigbeelens.services.report_storage import (
    load_stored_report_envelope,
)
from zigbeelens.db.connection import Database
from zigbeelens.storage.repository import Repository


def _badge(
    status: DecisionStatus = DecisionStatus.watch,
    priority: DecisionPriority = DecisionPriority.low,
) -> DeviceDecisionBadge:
    return DeviceDecisionBadge(
        status=status,
        priority=priority,
        headline_code=f"device_{status.value}",
        coverage_label_codes=[],
    )


def test_decision_count_summary_rejects_string_float_bool_counts():
    base = {
        "subject_count": 1,
        "overall_status": "watch",
        "highest_priority": "low",
        "status_counts": {"watch": 1},
        "priority_counts": {"low": 1},
        "coverage_warning_count": 0,
    }
    with pytest.raises(ValidationError):
        DecisionCountSummary.model_validate({**base, "subject_count": "1"})
    with pytest.raises(ValidationError):
        DecisionCountSummary.model_validate({**base, "subject_count": 1.0})
    with pytest.raises(ValidationError):
        DecisionCountSummary.model_validate({**base, "subject_count": True})
    with pytest.raises(ValidationError):
        DecisionCountSummary.model_validate(
            {**base, "status_counts": {"watch": "1"}, "priority_counts": {"low": 1}}
        )
    with pytest.raises(ValidationError):
        DecisionCountSummary.model_validate(
            {**base, "status_counts": {"watch": 1.0}, "priority_counts": {"low": 1}}
        )
    with pytest.raises(ValidationError):
        DecisionCountSummary.model_validate(
            {**base, "status_counts": {"watch": True}, "priority_counts": {"low": 1}}
        )


def test_decision_count_summary_rejects_balanced_negative_maps():
    with pytest.raises(ValidationError):
        DecisionCountSummary.model_validate(
            {
                "subject_count": 1,
                "overall_status": "watch",
                "highest_priority": "low",
                "status_counts": {"watch": 2, "informational": -1},
                "priority_counts": {"low": 1},
                "coverage_warning_count": 0,
            }
        )


def test_decision_count_summary_rejects_inconsistent_overall_and_priority():
    with pytest.raises(ValidationError):
        DecisionCountSummary.model_validate(
            {
                "subject_count": 2,
                "overall_status": "watch",
                "highest_priority": "high",
                "status_counts": {"watch": 1, "review_first": 1},
                "priority_counts": {"high": 1, "low": 1},
                "coverage_warning_count": 0,
            }
        )
    with pytest.raises(ValidationError):
        DecisionCountSummary.model_validate(
            {
                "subject_count": 2,
                "overall_status": "review_first",
                "highest_priority": "low",
                "status_counts": {"watch": 1, "review_first": 1},
                "priority_counts": {"high": 1, "low": 1},
                "coverage_warning_count": 0,
            }
        )


def test_decision_count_summary_empty_requires_data_unavailable_and_none():
    DecisionCountSummary.model_validate(
        {
            "subject_count": 0,
            "overall_status": "data_unavailable",
            "highest_priority": "none",
            "status_counts": {},
            "priority_counts": {},
            "coverage_warning_count": 0,
        }
    )
    with pytest.raises(ValidationError):
        DecisionCountSummary.model_validate(
            {
                "subject_count": 0,
                "overall_status": "no_notable_change",
                "highest_priority": "none",
                "status_counts": {},
                "priority_counts": {},
                "coverage_warning_count": 0,
            }
        )
    with pytest.raises(ValidationError):
        DecisionCountSummary.model_validate(
            {
                "subject_count": 0,
                "overall_status": "data_unavailable",
                "highest_priority": "low",
                "status_counts": {},
                "priority_counts": {},
                "coverage_warning_count": 0,
            }
        )


def test_compose_network_decision_promotes_badge_not_summary():
    badge, summary = compose_network_decision(
        device_badges=[],
        has_active_incident=True,
    )
    assert summary.subject_count == 0
    assert summary.overall_status == DecisionStatus.data_unavailable
    assert summary.highest_priority == DecisionPriority.none
    assert summary.status_counts == {}
    assert summary.priority_counts == {}
    assert badge.status == DecisionStatus.worth_reviewing
    assert badge.priority == DecisionPriority.medium
    assert badge.headline_code == "network_worth_reviewing"


def test_compose_network_decision_coverage_only_empty_network():
    badge, summary = compose_network_decision(
        device_badges=[],
        coverage_warning_count=2,
    )
    assert summary.subject_count == 0
    assert summary.overall_status == DecisionStatus.data_unavailable
    assert summary.coverage_warning_count == 2
    assert badge.status == DecisionStatus.improve_data_coverage
    assert badge.priority == DecisionPriority.low


def test_compose_network_decision_review_first_promotes_badge():
    badge, summary = compose_network_decision(
        device_badges=[_badge(DecisionStatus.watch, DecisionPriority.low)],
        has_review_first_priority=True,
    )
    assert summary.overall_status == DecisionStatus.watch
    assert summary.highest_priority == DecisionPriority.low
    assert badge.status == DecisionStatus.review_first
    assert badge.priority == DecisionPriority.high


def test_compose_network_decision_empty_unobserved():
    badge, summary = compose_network_decision(device_badges=[])
    assert summary.overall_status == DecisionStatus.data_unavailable
    assert badge.status == DecisionStatus.data_unavailable
    assert badge.priority == DecisionPriority.none


def test_non_exact_v3_stored_reports_fail_closed(tmp_path: Path):
    db = Database(tmp_path / "proto.sqlite")
    db.migrate()
    repo = Repository(db)
    for idx, raw in enumerate(
        [None, 1, 2, "1", "2", "3", True, 3.0, -1, 4, 1.5, [], {}]
    ):
        body = {
            "id": f"bad-{idx}",
            "markdown_summary": "should not load",
        }
        if raw is not None or raw is None:
            if raw is None:
                pass  # missing report_version
            else:
                body["report_version"] = raw
        row = repo.reports.save_report(
            report_id=f"proto-row-{idx}",
            format="json",
            scope="full",
            redaction_profile="standard",
            summary="bad",
            body=body,
            markdown=body["markdown_summary"],
            redaction={},
            metadata={},
        )
        assert load_stored_report_envelope(row) is None
        stored = repo.reports.get_report(row.id)
        assert stored is not None
        assert stored.body_json  # bytes remain untouched


def test_mock_missing_story_receives_data_unavailable_badge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from zigbeelens.config.models import AppConfig
    from zigbeelens.services.data_service import DataService
    from zigbeelens.services.mock_provider import MockProvider

    db = Database(tmp_path / "mock-missing-story.sqlite")
    db.migrate()
    repo = Repository(db)
    config = AppConfig()
    config.mode.mock = True
    data = DataService(config, repo)
    scenario = "all_ok_single_network"
    mock = MockProvider(scenario)
    first = mock.devices()[0]
    orphan_key = (first.network_id, first.ieee_address)
    mock.data.device_stories.pop(orphan_key, None)
    monkeypatch.setattr(data, "_mock", lambda _scenario: mock)
    rebuilt = data._scenario_report_device_context(
        scenario,
        network_id=orphan_key[0],
        device_keys={orphan_key},
        include_device_details=True,
    )
    detail = rebuilt.device_details[orphan_key]
    assert detail.decision is not None
    assert detail.decision.status == DecisionStatus.data_unavailable
    assert detail.decision.priority == DecisionPriority.none
    assert detail.decision.headline_code == "device_data_unavailable"
    DeviceDetail.model_validate(detail.model_dump(mode="json"))
    # Canonical empty badge remains independently valid.
    DeviceDetail.model_validate(
        DeviceDetail(
            network_id="home",
            ieee_address="0xmissing",
            friendly_name="orphan",
            device_type="EndDevice",
            power_source="Battery",
            availability="online",
            interview_state="successful",
            decision=data_unavailable_device_badge(),
        ).model_dump(mode="json")
    )
