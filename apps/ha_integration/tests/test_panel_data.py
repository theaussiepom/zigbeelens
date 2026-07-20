"""Tests for the redacted companion-panel summary builder."""

from __future__ import annotations

import json
from pathlib import Path

from zigbeelens.coordinator import ZigbeeLensCoordinatorData
from zigbeelens.panel_data import MAX_COMPANION_INVESTIGATION_PRIORITIES, build_panel_summary

PANEL_JS = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "zigbeelens"
    / "panel"
    / "zigbeelens-panel.js"
)


def _priority(i: int, *, network_id: str = "home", **overrides) -> dict:
    base = {
        "id": f"p{i}",
        "network_id": network_id,
        "card_type": "shared_availability_event",
        "priority": f"Priority {i}",
        "score": 100 - i,
        "action_group": "investigate_shared_event",
        "title": f"Title {i}",
        "summary": f"Summary {i}",
        "device_ieees": ["0xaa"],
        "latest_supporting_evidence_at": "2026-06-14T12:00:00+00:00",
    }
    base.update(overrides)
    return base


def _data(
    sample_health,
    sample_dashboard,
    sample_config_status,
    *,
    shared: bool = False,
    contract: int = 0,
    compatible: bool | None = True,
):
    return ZigbeeLensCoordinatorData(
        health=sample_health,
        dashboard=sample_dashboard,
        config_status=sample_config_status,
        core_version="0.1.0",
        collector_connected=True,
        last_update_success=True,
        shared_decisions_available=shared,
        decision_contract_version=contract,
        core_version_compatible=compatible,
    )


def test_summary_connected_has_expected_fields(
    sample_health, sample_dashboard, sample_config_status
):
    data = _data(sample_health, sample_dashboard, sample_config_status)
    summary = build_panel_summary(data, core_url="http://192.168.100.5:8377", connected=True)

    assert summary["connected"] is True
    assert summary["core_url"] == "http://192.168.100.5:8377"
    assert summary["core_version"] == "0.1.0"
    assert summary["overall_decision_status"] is None  # decision mode off
    assert summary["active_incident_count"] is None
    assert summary["network_count"] is None
    assert summary["device_count"] is None
    assert summary["unavailable_devices"] is None
    assert summary["router_risks"] is None
    assert summary["collector_connected"] is True
    assert summary["shared_decisions_available"] is False
    assert summary["decision_contract_version"] == 0
    assert summary["core_version_compatible"] is True
    assert summary["investigation_priorities"] == []
    assert summary["investigation_priority_count"] is None
    assert summary["networks"] == []


def test_summary_exposes_decision_contract_flags(
    sample_health, sample_dashboard, sample_config_status
):
    data = _data(
        sample_health,
        sample_dashboard,
        sample_config_status,
        shared=True,
        contract=2,
        compatible=True,
    )
    summary = build_panel_summary(data, core_url="http://core:8377", connected=True)
    assert summary["shared_decisions_available"] is True
    assert summary["decision_contract_version"] == 2
    assert summary["core_version_compatible"] is True
    assert summary["active_incident_count"] == 1
    assert summary["device_count"] == 10
    assert summary["networks"][0]["id"] == "home"


def test_summary_projects_priorities_preserving_order_and_cap(
    sample_health, sample_dashboard, sample_config_status
):
    dashboard = dict(sample_dashboard)
    dashboard["networks"] = [
        {
            "id": "home",
            "name": "Home",
            "bridge_state": "online",
            "device_count": 10,
            "unavailable_count": 1,
            "active_incident_count": 0,
            "active_incident_severity": "watch",
            "decision": {
                "status": "watch",
                "priority": "low",
                "headline_code": "network_watch",
                "coverage_label_codes": [],
            },
            "decision_summary": {
                "subject_count": 1,
                "overall_status": "watch",
                "highest_priority": "low",
                "status_counts": {"watch": 1},
                "priority_counts": {"low": 1},
                "coverage_warning_count": 0,
            },
        },
        {
            "id": "office",
            "name": "Office",
            "bridge_state": "online",
            "device_count": 4,
            "unavailable_count": 0,
            "active_incident_count": 0,
            "decision": {
                "status": "no_notable_change",
                "priority": "none",
                "headline_code": "network_no_notable_change",
                "coverage_label_codes": [],
            },
            "decision_summary": {
                "subject_count": 0,
                "overall_status": "data_unavailable",
                "highest_priority": "none",
                "status_counts": {},
                "priority_counts": {},
                "coverage_warning_count": 0,
            },
        },
    ]
    dashboard["investigation_priorities"] = [
        _priority(1, network_id="home", title="Exact Alpha Title", summary="Exact Alpha Summary", priority="Review first"),
        _priority(2, network_id="office", title="Exact Beta Title", summary="Exact Beta Summary", priority="Worth reviewing"),
        _priority(3, network_id="home", title="Exact Gamma Title", summary="Exact Gamma Summary", priority="Watch"),
        _priority(4, network_id="office", title="Exact Delta Title", summary="Exact Delta Summary", priority="Watch"),
        "not-a-dict",
        {"title": "Missing priority", "summary": "x"},
        _priority(5, network_id="home", title="Exact Epsilon Title", summary="Exact Epsilon Summary", priority="Informational"),
    ]
    dashboard["data_coverage_warnings"] = [
        {"id": "w1", "network_id": "home", "label_code": "availability_tracking_off"},
        {"id": "w2", "network_id": "office", "label_code": "route_hints_unavailable"},
        "skip-me",
    ]
    data = _data(
        sample_health,
        dashboard,
        sample_config_status,
        shared=True,
        contract=2,
        compatible=True,
    )
    summary = build_panel_summary(data, core_url="http://core:8377", connected=True)

    assert summary["investigation_priority_count"] == 5
    assert len(summary["investigation_priorities"]) == MAX_COMPANION_INVESTIGATION_PRIORITIES
    assert summary["more_investigation_priority_count"] == 2
    assert summary["data_coverage_warning_count"] == 2

    projected = summary["investigation_priorities"]
    assert [p["title"] for p in projected] == [
        "Exact Alpha Title",
        "Exact Beta Title",
        "Exact Gamma Title",
    ]
    assert projected[0]["priority"] == "Review first"
    assert projected[0]["summary"] == "Exact Alpha Summary"
    assert projected[0]["network_name"] == "Home"
    assert projected[1]["network_name"] == "Office"
    assert "score" not in projected[0]
    assert "action_group" not in projected[0]
    assert "card_type" not in projected[0]
    assert "device_ieees" not in projected[0]

    by_id = {n["id"]: n for n in summary["networks"]}
    assert by_id["home"]["investigation_priority_count"] == 3
    assert by_id["office"]["investigation_priority_count"] == 2

    blob = json.dumps(summary)
    assert "score" not in blob or '"score"' not in blob
    assert "action_group" not in blob
    assert "device_ieees" not in blob
    assert "availability_tracking_off" not in blob


def test_summary_hides_decisions_when_contract_unavailable(
    sample_health, sample_dashboard, sample_config_status
):
    dashboard = dict(sample_dashboard)
    dashboard["investigation_priorities"] = [_priority(1)]
    dashboard["data_coverage_warnings"] = [{"id": "w1"}]
    data = _data(
        sample_health,
        dashboard,
        sample_config_status,
        shared=False,
        contract=2,
        compatible=True,
    )
    summary = build_panel_summary(data, core_url="http://core:8377", connected=True)
    assert summary["investigation_priorities"] == []
    assert summary["investigation_priority_count"] is None
    assert summary["more_investigation_priority_count"] is None
    assert summary["data_coverage_warning_count"] is None
    assert summary["active_incident_count"] is None
    assert summary["networks"] == []


def test_summary_hides_decisions_when_core_incompatible(
    sample_health, sample_dashboard, sample_config_status
):
    dashboard = dict(sample_dashboard)
    dashboard["investigation_priorities"] = [_priority(1)]
    data = _data(
        sample_health,
        dashboard,
        sample_config_status,
        shared=False,
        contract=2,
        compatible=False,
    )
    summary = build_panel_summary(data, core_url="http://core:8377", connected=True)
    assert summary["investigation_priorities"] == []
    assert summary["core_version_compatible"] is False


def test_summary_excludes_secrets(sample_health, sample_dashboard, sample_config_status):
    config_status = dict(sample_config_status)
    config_status["mqtt_server"] = "mqtt://user:supersecret@broker:1883"
    data = _data(sample_health, sample_dashboard, config_status)

    summary = build_panel_summary(data, core_url="http://core:8377", connected=True)
    serialized = json.dumps(summary).lower()

    assert "mqtt_server" not in summary
    assert "supersecret" not in serialized
    assert "broker" not in serialized
    assert "password" not in serialized


def test_summary_disconnected_is_calm():
    summary = build_panel_summary(
        None,
        core_url="http://192.168.100.5:8377",
        connected=False,
        last_exception="boom",
    )
    assert summary["connected"] is False
    assert summary["core_url"] == "http://192.168.100.5:8377"
    assert summary["error"] == "boom"
    assert summary["networks"] == []
    assert summary["device_count"] is None
    assert summary["investigation_priorities"] == []
    assert summary["core_version_compatible"] is None
    assert summary["shared_decisions_available"] is False
    assert summary["decision_contract_version"] == 0


def test_summary_preserves_compatibility_tri_state(
    sample_health, sample_dashboard, sample_config_status
):
    true_data = _data(
        sample_health,
        sample_dashboard,
        sample_config_status,
        shared=True,
        contract=2,
        compatible=True,
    )
    assert (
        build_panel_summary(true_data, core_url="http://core:8377", connected=True)[
            "core_version_compatible"
        ]
        is True
    )
    false_data = _data(
        sample_health,
        sample_dashboard,
        sample_config_status,
        shared=False,
        contract=2,
        compatible=False,
    )
    assert (
        build_panel_summary(false_data, core_url="http://core:8377", connected=True)[
            "core_version_compatible"
        ]
        is False
    )
    unknown = _data(
        sample_health,
        sample_dashboard,
        sample_config_status,
        shared=False,
        contract=2,
        compatible=None,
    )
    summary = build_panel_summary(unknown, core_url="http://core:8377", connected=True)
    assert summary["core_version_compatible"] is None
    assert summary["investigation_priorities"] == []


def test_panel_frontend_asset_default_summary_with_optional_embed():
    source = PANEL_JS.read_text(encoding="utf-8")
    assert PANEL_JS.exists()
    assert 'customElements.define("zigbeelens-panel"' in source
    assert "Try Embedded View" in source
    assert "Back to Summary" in source
    assert "_backToSummary" in source
    assert 'canEmbed ? "embedded" : "embed_blocked"' in source
    assert 'this._view = "summary"' in source
    assert "_maybeAutoEmbed" not in source
    assert 'target="_blank"' in source
    assert 'rel="noopener noreferrer"' in source
    assert "zigbeelens/panel_summary" in source
    assert "canEmbedDashboard" in source
    assert "<iframe" in source.lower()
    assert "embed_blocked" in source


def test_panel_frontend_asset_decision_mode():
    source = PANEL_JS.read_text(encoding="utf-8")
    assert "_decisionMode(s)" in source
    assert "shared_decisions_available === true" in source
    assert "What needs attention now" in source
    assert "_decisionPrioritiesCard(s)" in source
    assert "No current investigation priorities from stored evidence." in source
    assert "more in the full ZigbeeLens dashboard" in source
    assert "Decision contract" in source
    assert "Open full ZigbeeLens dashboard" in source
    assert "esc(item.priority)" in source
    assert "esc(item.title)" in source
    assert "esc(item.summary)" in source
    assert "esc(item.network_name" in source
    assert "_contractIncompatibleCard" in source
    assert "decision contract is incompatible" in source
    assert "_findingCard" not in source
    assert "n.health" not in source
    assert "No active findings" not in source
    assert "current_finding" not in source
    assert "Compatible" in source
    assert "Incompatible" in source
    assert "Unknown" in source
    # Decision-mode priority/coverage counts are neutral (no Watch accent).
    assert 'this._stat("Investigation priorities", s.investigation_priority_count)' in source
    assert 'this._stat("Data coverage warnings", s.data_coverage_warning_count)' in source
    assert "formatCount" in source
    assert "priorityAccent" not in source
    assert "coverageAccent" not in source

    for forbidden in (
        "review_first",
        "worth_reviewing",
        "improve_data_coverage",
        "no_notable_change",
        "current_issue_present",
        "availability_tracking_off",
        "investigate_shared_event",
        "review_model_pattern",
    ):
        assert forbidden not in source

    assert "item.score" not in source
    assert "item.action_group" not in source
    assert "item.device_ieees" not in source
    assert "item.card_type" not in source
