"""Tests for Lens-family MQTT summary presentation."""

from __future__ import annotations

from zigbeelens.presentation.lens_mqtt import build_summary_entities, count_state, issue_count, severity_to_lens_bucket
from zigbeelens.schemas import Severity


def test_severity_maps_to_lens_bucket() -> None:
    assert severity_to_lens_bucket(Severity.healthy) == "healthy"
    assert severity_to_lens_bucket(Severity.watch) == "recently_unstable"
    assert severity_to_lens_bucket(Severity.incident) == "needs_attention"


def test_issue_count_unknown_if_any_bucket_unknown() -> None:
    counts = {"unavailable": "unknown", "needs_attention": 0}
    assert issue_count(counts) == "unknown"
    assert count_state("unknown") == "unknown"
    assert count_state(0) == "0"


def test_build_summary_entities_mock_mode_observable() -> None:
    from zigbeelens.config.models import AppConfig, ModeConfig
    from zigbeelens.db.connection import Database
    from zigbeelens.diagnostics.incidents.service import IncidentDiagnosticService
    from zigbeelens.diagnostics.service import HealthDiagnosticService
    from zigbeelens.services.data_service import DataService
    from zigbeelens.storage.repository import Repository

    config = AppConfig(mode=ModeConfig(mock=True, default_scenario="four_devices_same_room_unavailable"))
    db = Database(":memory:")
    db.migrate()
    repo = Repository(db)
    dashboard = DataService(
        config,
        repo,
        HealthDiagnosticService(config, repo),
        IncidentDiagnosticService(config, repo),
    ).dashboard()
    summaries = build_summary_entities(
        dashboard,
        core_version="1.0.0",
        collector_connected=False,
        mock_mode=True,
    )
    health = next(item for item in summaries if item.key == "health")
    assert health.attributes["product"] == "zigbeelens"
    assert health.attributes["observation_reliable"] is True
