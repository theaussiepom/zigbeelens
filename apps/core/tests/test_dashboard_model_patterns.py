"""Dashboard model pattern composition tests (Phase 4G-3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.model_pattern import (
    MODEL_PATTERN_MIN_AFFECTED_COUNT,
    MODEL_PATTERN_MIN_GROUP_SIZE,
)
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.services.dashboard_model_patterns import (
    MAX_OVERVIEW_MODEL_PATTERNS,
    compose_dashboard_model_patterns,
)
from zigbeelens.services.empty_state import build_empty_dashboard
from zigbeelens.services.payload_builder import PayloadBuilder
from zigbeelens.storage.repository import Repository


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _config(db_path: Path, *, networks: list[NetworkConfig] | None = None) -> AppConfig:
    return AppConfig(
        mode=ModeConfig(mock=True),
        networks=networks
        or [NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(db_path)),
    )


def _repo(tmp_path: Path, *, networks: list[NetworkConfig] | None = None) -> tuple[Repository, AppConfig]:
    db_path = tmp_path / "dashboard-model-pattern.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = _config(db_path, networks=networks)
    repo.sync_networks(config.networks)
    return repo, config


def _add_device(
    repo: Repository,
    network_id: str,
    ieee: str,
    *,
    manufacturer: str | None = "IKEA",
    model: str = "TS011F",
) -> None:
    repo.upsert_device(
        network_id=network_id,
        ieee_address=ieee,
        friendly_name=f"Device {ieee}",
        device_type="EndDevice",
        power_source="Mains",
        manufacturer=manufacturer,
        model=model,
    )


def _offline_event(repo: Repository, network_id: str, ieee: str, at: datetime) -> None:
    repo.db.conn.execute(
        """
        INSERT INTO availability_changes (network_id, ieee_address, from_state, to_state, changed_at)
        VALUES (?, ?, 'online', 'offline', ?)
        """,
        (network_id, ieee, at.isoformat()),
    )
    repo.db.conn.commit()


def _seed_qualifying_pattern(
    repo: Repository,
    network_id: str,
    *,
    base: datetime,
    device_prefix: str = "0xm",
    model: str = "TS011F",
) -> list[str]:
    devices = [f"{device_prefix}{i:02d}" for i in range(MODEL_PATTERN_MIN_GROUP_SIZE)]
    for ieee in devices:
        _add_device(repo, network_id, ieee, model=model)
    for ieee in devices[:MODEL_PATTERN_MIN_AFFECTED_COUNT]:
        _offline_event(repo, network_id, ieee, base)
    return devices


def test_empty_dashboard_includes_model_patterns(tmp_path: Path):
    repo, config = _repo(tmp_path)
    dash = build_empty_dashboard(config, repo.list_networks())
    assert dash.model_patterns == []


def test_compose_returns_empty_without_qualifying_patterns(tmp_path: Path):
    repo, _ = _repo(tmp_path)
    _add_device(repo, "home", "0xa1")
    _offline_event(repo, "home", "0xa1", _now() - timedelta(days=1))
    summaries = compose_dashboard_model_patterns(repo, repo.list_networks(), now=_now())
    assert summaries == []


def test_dashboard_payload_includes_qualifying_model_pattern(tmp_path: Path):
    repo, config = _repo(tmp_path)
    devices = _seed_qualifying_pattern(repo, "home", base=_now() - timedelta(days=1))
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    dash = PayloadBuilder(config, repo, health).dashboard()
    assert len(dash.model_patterns) == 1
    pattern = dash.model_patterns[0]
    assert pattern.pattern_id.startswith("model-pattern-")
    assert pattern.network_id == "home"
    assert pattern.model == "TS011F"
    assert pattern.manufacturer == "IKEA"
    assert pattern.group_size == MODEL_PATTERN_MIN_GROUP_SIZE
    assert pattern.affected_count == MODEL_PATTERN_MIN_AFFECTED_COUNT
    assert pattern.lookback_days == 7
    assert set(pattern.affected_device_ieees) == set(devices[:MODEL_PATTERN_MIN_AFFECTED_COUNT])
    assert pattern.latest_supporting_evidence_at is not None


def test_dashboard_uses_phase_4g_grouping_not_separate_threshold(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _seed_qualifying_pattern(repo, "home", base=_now() - timedelta(days=1))
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    composed = compose_dashboard_model_patterns(repo, repo.list_networks(), now=_now())
    dash = PayloadBuilder(config, repo, health).dashboard()
    assert dash.model_patterns == composed


def test_compose_respects_overview_presentation_cap(tmp_path: Path):
    repo, _ = _repo(tmp_path)
    for index in range(MAX_OVERVIEW_MODEL_PATTERNS + 1):
        _seed_qualifying_pattern(
            repo,
            "home",
            base=_now() - timedelta(days=index + 1),
            device_prefix=f"0x{index}m",
            model=f"TS0{index:02d}F",
        )
    summaries = compose_dashboard_model_patterns(repo, repo.list_networks(), now=_now())
    assert len(summaries) == MAX_OVERVIEW_MODEL_PATTERNS


def test_model_patterns_do_not_change_dashboard_severity_or_incident_counts(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _seed_qualifying_pattern(repo, "home", base=_now() - timedelta(days=1))
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    builder = PayloadBuilder(config, repo, health)

    with patch(
        "zigbeelens.services.payload_builder.compose_dashboard_model_patterns",
        return_value=[],
    ):
        baseline = builder.dashboard()

    with_patterns = builder.dashboard()

    assert baseline.model_patterns == []
    assert with_patterns.model_patterns
    assert with_patterns.overall_severity == baseline.overall_severity
    assert with_patterns.current_finding == baseline.current_finding
    assert with_patterns.active_incident_count == baseline.active_incident_count
    assert with_patterns.watching_incident_count == baseline.watching_incident_count
