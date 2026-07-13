"""Dashboard shared availability event composition tests (Phase 4E-3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from unittest.mock import patch

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.availability_event_groups import SHARED_EVENT_MIN_DEVICES
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.services.dashboard_shared_availability import (
    MAX_OVERVIEW_SHARED_AVAILABILITY_EVENTS,
    compose_dashboard_shared_availability_events,
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
    db_path = tmp_path / "dashboard-shared.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = _config(db_path, networks=networks)
    repo.sync_networks(config.networks)
    return repo, config


def _add_device(repo: Repository, network_id: str, ieee: str) -> None:
    repo.upsert_device(
        network_id=network_id,
        ieee_address=ieee,
        friendly_name=f"Device {ieee}",
        device_type="EndDevice",
        power_source="Mains",
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


def _seed_shared_event(
    repo: Repository,
    network_id: str,
    *,
    base: datetime,
    device_prefix: str = "0xd",
) -> None:
    devices = [f"{device_prefix}{i:02d}" for i in range(SHARED_EVENT_MIN_DEVICES)]
    for ieee in devices:
        _add_device(repo, network_id, ieee)
    for index, ieee in enumerate(devices):
        _offline_event(repo, network_id, ieee, base + timedelta(seconds=10 * index))


def test_empty_dashboard_includes_shared_availability_events(tmp_path: Path):
    repo, config = _repo(tmp_path)
    dash = build_empty_dashboard(config, repo.list_networks())
    assert dash.shared_availability_events == []


def test_compose_returns_empty_without_qualifying_events(tmp_path: Path):
    repo, _ = _repo(tmp_path)
    _add_device(repo, "home", "0xa1")
    _offline_event(repo, "home", "0xa1", _now() - timedelta(days=1))
    summaries = compose_dashboard_shared_availability_events(
        repo, repo.list_networks(), now=_now()
    )
    assert summaries == []


def test_dashboard_payload_includes_qualifying_shared_event(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _seed_shared_event(repo, "home", base=_now() - timedelta(days=1))
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    dash = PayloadBuilder(config, repo, health).dashboard()
    assert len(dash.shared_availability_events) == 1
    event = dash.shared_availability_events[0]
    assert event.event_id.startswith("shared-availability-")
    assert event.network_id == "home"
    assert event.device_count == SHARED_EVENT_MIN_DEVICES
    assert event.duration_minutes >= 0
    assert len(event.device_ieees) == SHARED_EVENT_MIN_DEVICES


def test_dashboard_uses_phase_4e_grouping_not_separate_threshold(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _seed_shared_event(repo, "home", base=_now() - timedelta(days=1))
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    composed = compose_dashboard_shared_availability_events(
        repo, repo.list_networks(), now=_now()
    )
    dash = PayloadBuilder(config, repo, health).dashboard()
    assert dash.shared_availability_events == composed


def test_compose_combines_multiple_networks_and_sorts_newest_first(tmp_path: Path):
    networks = [
        NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
        NetworkConfig(id="office", name="Office", base_topic="zigbee2mqtt/office"),
    ]
    repo, _ = _repo(tmp_path, networks=networks)
    older = _now() - timedelta(days=2)
    newer = _now() - timedelta(hours=6)
    _seed_shared_event(repo, "home", base=older, device_prefix="0xh")
    _seed_shared_event(repo, "office", base=newer, device_prefix="0xo")
    summaries = compose_dashboard_shared_availability_events(
        repo, repo.list_networks(), now=_now()
    )
    assert len(summaries) == 2
    assert summaries[0].network_id == "office"
    assert summaries[1].network_id == "home"


def test_compose_respects_overview_presentation_cap(tmp_path: Path):
    repo, _ = _repo(tmp_path)
    for index in range(MAX_OVERVIEW_SHARED_AVAILABILITY_EVENTS + 1):
        _seed_shared_event(
            repo,
            "home",
            base=_now() - timedelta(days=index + 1),
            device_prefix=f"0x{index}x",
        )
    summaries = compose_dashboard_shared_availability_events(
        repo, repo.list_networks(), now=_now()
    )
    assert len(summaries) == MAX_OVERVIEW_SHARED_AVAILABILITY_EVENTS


def test_shared_events_do_not_change_dashboard_severity_or_incident_counts(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _seed_shared_event(repo, "home", base=_now() - timedelta(days=1))
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    builder = PayloadBuilder(config, repo, health)

    with patch(
        "zigbeelens.services.payload_builder.compose_dashboard_shared_availability_events",
        return_value=[],
    ):
        baseline = builder.dashboard()

    with_events = builder.dashboard()

    assert baseline.shared_availability_events == []
    assert with_events.shared_availability_events
    assert with_events.shared_availability_events[0].device_count >= SHARED_EVENT_MIN_DEVICES
    assert with_events.overall_severity == baseline.overall_severity
    assert with_events.current_finding == baseline.current_finding
    assert with_events.active_incident_count == baseline.active_incident_count
    assert with_events.watching_incident_count == baseline.watching_incident_count
    assert with_events.top_affected_devices == baseline.top_affected_devices
    assert with_events.router_risks == baseline.router_risks
    assert with_events.recently_unstable == baseline.recently_unstable
    assert with_events.weak_links == baseline.weak_links
    assert with_events.low_batteries == baseline.low_batteries
    assert with_events.stale_devices == baseline.stale_devices
