"""Unified data access: mock fixtures, SQLite-backed, or empty state."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from zigbeelens.config.models import AppConfig
from zigbeelens.decisions.device_story import DeviceStory, device_stories_for_devices
from zigbeelens.schemas import DeviceDetail, DeviceSummary, ReportDetail, ReportRequest
from zigbeelens.diagnostics.incidents.service import IncidentDiagnosticService
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.services.device_decision_badge import device_decision_badge_from_story
from zigbeelens.services.mock_provider import MockProvider
from zigbeelens.services.payload_builder import EvaluationAccess, PayloadBuilder
from zigbeelens.services.reports import generate_report
from zigbeelens.storage.repository import Repository


@dataclass(frozen=True)
class ReportDeviceContext:
    """Summaries, stories and optional details from one composition batch (Phase 5D)."""

    devices: list[DeviceSummary]
    stories: dict[tuple[str, str], DeviceStory]
    device_details: dict[tuple[str, str], DeviceDetail] = field(default_factory=dict)


class DataService:
    def __init__(
        self,
        config: AppConfig,
        repo: Repository,
        health: HealthDiagnosticService | None = None,
        incidents: IncidentDiagnosticService | None = None,
        evaluation: EvaluationAccess | None = None,
    ) -> None:
        self.config = config
        self.repo = repo
        self._builder = PayloadBuilder(config, repo, health, incidents, evaluation)

    @property
    def is_mock_mode(self) -> bool:
        return self.config.mode.mock

    @property
    def payload_builder(self) -> PayloadBuilder:
        return self._builder

    def uses_mock(self, scenario: str | None) -> bool:
        """Scenario query param always selects mock fixtures (UI regression)."""
        if scenario:
            return MockProvider.is_valid_scenario(scenario)
        return self.config.mode.mock

    def _mock(self, scenario: str | None) -> MockProvider:
        scenario_id = scenario or self.config.mode.default_scenario
        return MockProvider(scenario_id)

    def dashboard(self, scenario: str | None = None):
        if self.uses_mock(scenario):
            return self._mock(scenario).dashboard()
        return self._builder.dashboard()

    def networks(self, scenario: str | None = None):
        if self.uses_mock(scenario):
            return self._mock(scenario).networks()
        return self._builder.networks()

    def network(self, network_id: str, scenario: str | None = None):
        if self.uses_mock(scenario):
            return self._mock(scenario).network(network_id)
        return self._builder.network(network_id)

    def devices(self, scenario: str | None = None, network_id: str | None = None):
        if self.uses_mock(scenario):
            devices = self._mock(scenario).devices(network_id)
            from zigbeelens.services.decision_summary import DECISION_STATUS_ORDER

            rank = {s.value: i for i, s in enumerate(DECISION_STATUS_ORDER)}
            return sorted(
                devices,
                key=lambda d: (
                    rank.get(str(d.decision.status), len(rank)),
                    d.network_id,
                    d.ieee_address,
                ),
            )
        return self._builder.devices(network_id)

    def report_device_context(
        self,
        scenario: str | None = None,
        *,
        network_id: str | None = None,
        device_keys: set[tuple[str, str]] | None = None,
        include_device_details: bool = False,
        now: datetime | None = None,
    ) -> ReportDeviceContext:
        """Load DeviceSummaries and full Device Stories from one story batch."""
        if self.uses_mock(scenario):
            return self._scenario_report_device_context(
                scenario,
                network_id=network_id,
                device_keys=device_keys,
                include_device_details=include_device_details,
            )

        rows = self.repo.list_devices(network_id)
        if device_keys is not None:
            rows = [
                row
                for row in rows
                if (row.network_id, row.ieee_address) in device_keys
            ]
        stories = device_stories_for_devices(self.repo, rows, now=now)
        badges = {
            key: device_decision_badge_from_story(story)
            for key, story in stories.items()
        }
        devices = self._builder._devices_from_rows(rows, decision_badges=badges)
        details: dict[tuple[str, str], DeviceDetail] = {}
        if include_device_details:
            for row in rows:
                key = (row.network_id, row.ieee_address)
                details[key] = self._builder._device_detail_from_row(
                    row,
                    decision_badge=badges.get(key),
                )
        return ReportDeviceContext(
            devices=devices,
            stories=stories,
            device_details=details,
        )

    def _scenario_report_device_context(
        self,
        scenario: str | None,
        *,
        network_id: str | None,
        device_keys: set[tuple[str, str]] | None,
        include_device_details: bool,
    ) -> ReportDeviceContext:
        from zigbeelens.mock.fixtures import device_detail_from_summary

        mock = self._mock(scenario)
        devices = mock.devices(network_id)
        if device_keys is not None:
            devices = [
                d for d in devices if (d.network_id, d.ieee_address) in device_keys
            ]
        stories: dict[tuple[str, str], DeviceStory] = {}
        for device in devices:
            key = (device.network_id, device.ieee_address)
            story = mock.data.device_stories.get(key)
            if story is not None:
                stories[key] = story
        details: dict[tuple[str, str], DeviceDetail] = {}
        if include_device_details:
            for device in devices:
                key = (device.network_id, device.ieee_address)
                detail = device_detail_from_summary(device, mock.data)
                story = stories.get(key)
                if story is not None:
                    detail = detail.model_copy(
                        update={
                            "decision": device_decision_badge_from_story(story),
                        }
                    )
                else:
                    detail = detail.model_copy(update={"decision": None})
                details[key] = detail
        return ReportDeviceContext(
            devices=devices,
            stories=stories,
            device_details=details,
        )

    def device(self, network_id: str, ieee_address: str, scenario: str | None = None):
        if self.uses_mock(scenario):
            return self._mock(scenario).device(network_id, ieee_address)
        return self._builder.device_detail(network_id, ieee_address)

    def device_story(
        self,
        network_id: str,
        ieee_address: str,
        scenario: str | None = None,
    ):
        if self.uses_mock(scenario):
            return self._mock(scenario).device_story(network_id, ieee_address)
        from zigbeelens.decisions.device_story import device_story_for_device

        return device_story_for_device(self.repo, network_id, ieee_address)

    def routers(self, scenario: str | None = None):
        if self.uses_mock(scenario):
            return self._mock(scenario).routers()
        return self._builder.routers()

    def incidents(self, scenario: str | None = None, *, query=None):
        """Public paginated incident collection."""
        from zigbeelens.storage.incident_collection import build_incident_collection_query

        collection_query = query or build_incident_collection_query()
        if self.uses_mock(scenario):
            return self._mock(scenario).incidents_page(collection_query)
        return self._builder.incidents_page(collection_query)

    def incident(self, incident_id: str, scenario: str | None = None):
        if self.uses_mock(scenario):
            return self._mock(scenario).incident(incident_id)
        return self._builder.incident(incident_id)

    def timeline(self, scenario: str | None = None, network_id: str | None = None):
        if self.uses_mock(scenario):
            return self._mock(scenario).timeline(network_id)
        return self._builder.timeline(network_id)

    def compose_report_scope(
        self,
        request: ReportRequest,
        scenario: str | None = None,
        *,
        reference_now: datetime,
        include_timeline: bool,
        reporting=None,
    ):
        """One request-local scoped report composition context (Track 3F)."""
        from zigbeelens.services.report_composition import (
            compose_live_report_scope,
            compose_mock_report_scope,
        )

        reporting_config = reporting or self.config.reporting
        if self.uses_mock(scenario):
            return compose_mock_report_scope(
                self._mock(scenario),
                request,
                reference_now=reference_now,
                include_timeline=include_timeline,
                reporting=reporting_config,
            )
        return compose_live_report_scope(
            self._builder,
            request,
            reference_now=reference_now,
            include_timeline=include_timeline,
            reporting=reporting_config,
        )

    def report_preview(
        self,
        scenario: str | None = None,
        request: ReportRequest | None = None,
        collector: dict | None = None,
    ):
        return generate_report(
            data=self,
            config=self.config,
            reporting=self.config.reporting,
            collector=collector or {},
            request=request or ReportRequest(),
            scenario=scenario,
            repo=self.repo,
        )

    def get_stored_report(self, report_id: str, scenario: str | None = None):
        if self.uses_mock(scenario) and report_id in {"report-preview"}:
            return self.report_preview(scenario)
        row = self.repo.reports.get_report(report_id)
        if not row or not row.body_json:
            return None
        from zigbeelens.services.report_storage import load_stored_report_body

        return load_stored_report_body(row)

    @staticmethod
    def list_scenarios() -> list[dict[str, str]]:
        return MockProvider.list_scenarios()
