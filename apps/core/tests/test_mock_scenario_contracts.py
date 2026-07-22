"""Oracle seal: every mock scenario satisfies the current public contract."""

from __future__ import annotations

import json

import pytest

from zigbeelens.config.models import AppConfig
from zigbeelens.db.connection import Database
from zigbeelens.mock.fixtures import BUILDERS, NOW
from zigbeelens.schemas import (
    DashboardPayload,
    DeviceDecisionBadge,
    DeviceDetail,
    ReportDetailV3,
    ReportRequest,
)
from zigbeelens.services.data_service import DataService
from zigbeelens.services.mock_provider import MockProvider
from zigbeelens.services.reports import generate_report
from zigbeelens.storage.incident_collection import build_incident_collection_query
from zigbeelens.storage.repository import Repository

SCENARIO_IDS = tuple(BUILDERS.keys())

DECISION_SUMMARY_KEYS = (
    "subject_count",
    "overall_status",
    "highest_priority",
    "status_counts",
    "priority_counts",
    "coverage_warning_count",
)


@pytest.fixture(scope="module")
def mock_data_service(tmp_path_factory) -> DataService:
    db = Database(tmp_path_factory.mktemp("oracle-mock-contracts") / "mock.sqlite")
    db.migrate()
    repo = Repository(db)
    config = AppConfig()
    config.mode.mock = True
    return DataService(config, repo)


def _assert_decision_summary(summary) -> None:
    dumped = summary.model_dump(mode="json")
    for key in DECISION_SUMMARY_KEYS:
        assert key in dumped, f"missing decision_summary.{key}"
    assert dumped["overall_status"]
    assert dumped["highest_priority"] is not None


def _assert_decision_badge(badge) -> None:
    assert badge is not None
    DeviceDecisionBadge.model_validate(badge.model_dump(mode="json"))


def _scenario_provider(scenario_id: str) -> MockProvider:
    return MockProvider(scenario_id)


def _scenario_report(
    data: DataService,
    scenario_id: str,
) -> ReportDetailV3:
    config = data.config
    return generate_report(
        data=data,
        config=config,
        reporting=config.reporting,
        collector={},
        request=ReportRequest(),
        scenario=scenario_id,
        now=NOW,
    )


def _status_value(incident) -> str:
    return str(getattr(incident.status, "value", incident.status))


def _expected_incident_counts(provider: MockProvider) -> tuple[int, int]:
    open_count = sum(1 for inc in provider.data.incidents if _status_value(inc) == "open")
    watching_count = sum(
        1 for inc in provider.data.incidents if _status_value(inc) == "watching"
    )
    return open_count, watching_count


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_scenario_dashboard_round_trips(scenario_id: str) -> None:
    provider = _scenario_provider(scenario_id)
    payload = provider.dashboard().model_dump(mode="json")
    round_tripped = DashboardPayload.model_validate(payload)
    assert round_tripped.scenario == scenario_id


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_scenario_dashboard_decision_summary_invariants(scenario_id: str) -> None:
    dashboard = _scenario_provider(scenario_id).dashboard()
    assert dashboard.decision_summary is not None
    _assert_decision_summary(dashboard.decision_summary)


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_scenario_dashboard_incident_counts_match_incidents(scenario_id: str) -> None:
    provider = _scenario_provider(scenario_id)
    expected_open, expected_watching = _expected_incident_counts(provider)
    dashboard = provider.dashboard()
    assert dashboard.active_incident_count == expected_open
    assert dashboard.watching_incident_count == expected_watching


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_scenario_network_summary_invariants(scenario_id: str) -> None:
    provider = _scenario_provider(scenario_id)
    active = [
        inc
        for inc in provider.data.incidents
        if _status_value(inc) in {"open", "watching"}
    ]
    for network in provider.networks():
        _assert_decision_badge(network.decision)
        _assert_decision_summary(network.decision_summary)
        expected = sum(1 for inc in active if network.id in inc.network_ids)
        assert network.active_incident_count == expected
        if network.active_incident_count == 0:
            assert network.active_incident_severity is None
        else:
            assert network.active_incident_severity is not None


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_scenario_device_summary_decisions(scenario_id: str) -> None:
    for device in _scenario_provider(scenario_id).devices():
        _assert_decision_badge(device.decision)


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_scenario_device_detail_decisions(scenario_id: str) -> None:
    provider = _scenario_provider(scenario_id)
    for device in provider.devices():
        detail = provider.device(device.network_id, device.ieee_address)
        assert detail is not None
        assert detail.decision is not None
        DeviceDetail.model_validate(detail.model_dump(mode="json"))


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_scenario_incidents_page_contract(scenario_id: str) -> None:
    provider = _scenario_provider(scenario_id)
    page = provider.incidents_page(build_incident_collection_query(limit=50))
    assert "items" in page
    for incident in page["items"]:
        assert incident.affected_device_count == len(incident.affected_devices)
        for ref in incident.affected_devices:
            _assert_decision_badge(ref.decision)


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_scenario_report_preview_round_trips(scenario_id: str) -> None:
    preview = _scenario_provider(scenario_id).report_preview()
    ReportDetailV3.model_validate(preview.model_dump(mode="json"))


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_scenario_full_report_round_trips(
    scenario_id: str,
    mock_data_service: DataService,
) -> None:
    detail = _scenario_report(mock_data_service, scenario_id)
    ReportDetailV3.model_validate(detail.model_dump(mode="json"))


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_scenario_report_incident_parity(
    scenario_id: str,
    mock_data_service: DataService,
) -> None:
    provider = _scenario_provider(scenario_id)
    detail = _scenario_report(mock_data_service, scenario_id)
    expected_ids = {inc.id for inc in provider.data.incidents}
    report_ids = {inc.id for inc in detail.incidents}
    assert report_ids == expected_ids
    assert detail.raw_counts.get("incidents_included") == len(provider.data.incidents)
    expected_open, expected_watching = _expected_incident_counts(provider)
    assert provider.dashboard().active_incident_count == expected_open
    assert provider.dashboard().watching_incident_count == expected_watching


def test_bridge_offline_affected_devices_empty() -> None:
    provider = _scenario_provider("bridge_offline")
    incident = provider.data.incidents[0]
    assert incident.affected_device_count == 0
    assert incident.affected_devices == []


def test_bridge_offline_network_critical_severity() -> None:
    provider = _scenario_provider("bridge_offline")
    home = provider.network("home")
    assert home is not None
    assert home.active_incident_count >= 1
    assert home.active_incident_severity is not None
    assert home.active_incident_severity.value == "critical"


def test_single_device_unavailable_one_affected_ref() -> None:
    provider = _scenario_provider("single_device_unavailable")
    incident = provider.data.incidents[0]
    assert incident.affected_device_count == 1
    assert len(incident.affected_devices) == 1


def test_bridge_offline_pydantic_dump_no_protocol_errors() -> None:
    provider = _scenario_provider("bridge_offline")
    dashboard = provider.dashboard().model_dump(mode="json")
    json.dumps(dashboard)
    DashboardPayload.model_validate(dashboard)

    page = provider.incidents_page(build_incident_collection_query(limit=50))
    incidents = [inc.model_dump(mode="json") for inc in page["items"]]
    json.dumps(incidents)

    preview = provider.report_preview().model_dump(mode="json")
    json.dumps(preview)
    ReportDetailV3.model_validate(preview)


def test_oracle_fixture_generation_matches_checked_in(tmp_path) -> None:
    """Thin pointer: freshness lives in tests/contracts (Phase 7B)."""
    from support.contracts import (  # type: ignore[import-not-found]
        ORACLE_FIXTURE,
        generate_oracle_fixture_text,
    )

    generated = tmp_path / "oracleMockScenarios.json"
    result = generate_oracle_fixture_text(output=generated)
    assert result.returncode == 0, result.stderr
    assert generated.read_text(encoding="utf-8") == ORACLE_FIXTURE.read_text(
        encoding="utf-8"
    )
