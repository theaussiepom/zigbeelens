"""Unified data access: mock fixtures, SQLite-backed, or empty state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from zigbeelens.config.models import AppConfig
from zigbeelens.decisions.device_story import DeviceStory, device_stories_for_devices
from zigbeelens.schemas import DeviceSummary, ReportDetail, ReportRequest
from zigbeelens.diagnostics.incidents.service import IncidentDiagnosticService
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.services.device_decision_badge import device_decision_badge_from_story
from zigbeelens.services.mock_provider import MockProvider
from zigbeelens.services.payload_builder import PayloadBuilder
from zigbeelens.services.reports import generate_report
from zigbeelens.storage.repository import Repository


@dataclass(frozen=True)
class ReportDeviceContext:
    """Summaries and full Device Stories from one composition batch (Phase 5D)."""

    devices: list[DeviceSummary]
    stories: dict[tuple[str, str], DeviceStory]


class DataService:
    def __init__(
        self,
        config: AppConfig,
        repo: Repository,
        health: HealthDiagnosticService | None = None,
        incidents: IncidentDiagnosticService | None = None,
    ) -> None:
        self.config = config
        self.repo = repo
        self._builder = PayloadBuilder(config, repo, health, incidents)

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
            return sorted(devices, key=lambda d: d.sort_priority)
        return self._builder.devices(network_id)

    def report_device_context(
        self,
        scenario: str | None = None,
        *,
        network_id: str | None = None,
        device_keys: set[tuple[str, str]] | None = None,
        now: datetime | None = None,
    ) -> ReportDeviceContext:
        """Load DeviceSummaries and full Device Stories from one story batch."""
        if self.uses_mock(scenario):
            mock = self._mock(scenario)
            devices = mock.devices(network_id)
            if device_keys is not None:
                devices = [
                    d
                    for d in devices
                    if (d.network_id, d.ieee_address) in device_keys
                ]
            stories: dict[tuple[str, str], DeviceStory] = {}
            for device in devices:
                key = (device.network_id, device.ieee_address)
                story = mock.data.device_stories.get(key)
                if story is not None:
                    stories[key] = story
            return ReportDeviceContext(devices=devices, stories=stories)

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
        return ReportDeviceContext(devices=devices, stories=stories)

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

    def incidents(self, scenario: str | None = None):
        if self.uses_mock(scenario):
            return self._mock(scenario).incidents()
        return self._builder.incidents()

    def incident(self, incident_id: str, scenario: str | None = None):
        if self.uses_mock(scenario):
            return self._mock(scenario).incident(incident_id)
        return self._builder.incident(incident_id)

    def timeline(self, scenario: str | None = None, network_id: str | None = None):
        if self.uses_mock(scenario):
            return self._mock(scenario).timeline(network_id)
        return self._builder.timeline(network_id)

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
        detail = ReportDetail.model_validate(json.loads(row.body_json))
        detail.id = row.id
        return detail

    @staticmethod
    def list_scenarios() -> list[dict[str, str]]:
        return MockProvider.list_scenarios()
