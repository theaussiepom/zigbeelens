"""Dashboard data coverage warning composition tests (Phase 5A-3)."""

from __future__ import annotations

from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig, TopologyConfig
from zigbeelens.db.connection import Database
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.services.dashboard_coverage_warnings import (
    MAX_OVERVIEW_COVERAGE_WARNINGS,
    compose_dashboard_coverage_warnings,
)
from zigbeelens.services.empty_state import build_empty_dashboard
from zigbeelens.services.payload_builder import PayloadBuilder
from zigbeelens.storage.repository import Repository


def _config(
    db_path: Path,
    *,
    networks: list[NetworkConfig] | None = None,
    automatic_capture_enabled: bool = False,
) -> AppConfig:
    return AppConfig(
        mode=ModeConfig(mock=True),
        networks=networks
        or [NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(db_path)),
        topology=TopologyConfig(
            automatic_capture_enabled=automatic_capture_enabled,
            automatic_capture_interval_hours=24,
        ),
    )


def _repo(tmp_path: Path, *, automatic_capture_enabled: bool = False) -> tuple[Repository, AppConfig]:
    db_path = tmp_path / "dashboard-coverage.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = _config(db_path, automatic_capture_enabled=automatic_capture_enabled)
    repo.sync_networks(config.networks)
    return repo, config


def test_empty_dashboard_includes_data_coverage_warnings(tmp_path: Path):
    repo, config = _repo(tmp_path)
    dash = build_empty_dashboard(config, repo.list_networks())
    assert dash.data_coverage_warnings == []


def test_compose_surfaces_availability_tracking_off(tmp_path: Path):
    repo, config = _repo(tmp_path)
    repo.upsert_device(
        network_id="home",
        ieee_address="0xa1",
        friendly_name="Device a1",
        device_type="EndDevice",
        power_source="Mains",
    )
    warnings = compose_dashboard_coverage_warnings(repo, repo.list_networks(), config)
    assert any(item.label_code == "availability_tracking_off" for item in warnings)
    assert all(item.scope_type == "network" for item in warnings)
    assert len(warnings) <= MAX_OVERVIEW_COVERAGE_WARNINGS


def test_dashboard_payload_includes_coverage_warnings(tmp_path: Path):
    repo, config = _repo(tmp_path)
    repo.upsert_device(
        network_id="home",
        ieee_address="0xa1",
        friendly_name="Device a1",
        device_type="EndDevice",
        power_source="Mains",
    )
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    dash = PayloadBuilder(config, repo, health).dashboard()
    assert any(item.label_code == "availability_tracking_off" for item in dash.data_coverage_warnings)


def test_route_hints_require_investigation_priority_network(tmp_path: Path):
    repo, config = _repo(tmp_path)
    without = compose_dashboard_coverage_warnings(
        repo,
        repo.list_networks(),
        config,
        investigation_network_ids=set(),
    )
    assert all(item.label_code != "route_hints_unavailable" for item in without)
