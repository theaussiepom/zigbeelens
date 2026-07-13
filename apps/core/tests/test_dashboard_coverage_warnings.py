"""Dashboard data coverage warning composition tests (Phase 5A-3 corrections)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from zigbeelens.config.models import (
    AppConfig,
    ModeConfig,
    NetworkConfig,
    StorageConfig,
    TopologyConfig,
)
from zigbeelens.db.connection import Database
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.schemas import InvestigationPrioritySummary
from zigbeelens.services.dashboard_coverage_warnings import (
    MAX_OVERVIEW_COVERAGE_WARNINGS,
    compose_dashboard_coverage_warnings,
)
from zigbeelens.services.empty_state import build_empty_dashboard
from zigbeelens.services.payload_builder import PayloadBuilder
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.parser import parse_networkmap_payload


def _now() -> datetime:
    return datetime.now(timezone.utc)


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


def _add_device(
    repo: Repository,
    network_id: str,
    ieee: str,
    *,
    availability: str | None = None,
) -> None:
    repo.upsert_device(
        network_id=network_id,
        ieee_address=ieee,
        friendly_name=f"Device {ieee}",
        device_type="EndDevice",
        power_source="Mains",
    )
    if availability is not None:
        repo.ensure_device_current_state(network_id, ieee)
        repo.update_device_current_state(
            network_id=network_id,
            ieee_address=ieee,
            availability=availability,
        )


def _store_snapshot(
    repo: Repository,
    *,
    snapshot_id: str = "snap-latest",
    captured_at: datetime | None = None,
    with_routes: bool = False,
) -> None:
    captured_at = captured_at or (_now() - timedelta(hours=1))
    repo.create_topology_snapshot(
        snapshot_id=snapshot_id,
        network_id="home",
        requested_by="test",
        status="pending",
        warning_acknowledged=True,
    )
    link: dict = {"source": "0x02", "target": "0x01", "linkquality": 120}
    if with_routes:
        link["routes"] = [{"destinationAddress": 0, "nextHop": 0}]
    parsed = parse_networkmap_payload(
        {
            "nodes": {
                "0x01": {"type": "Coordinator"},
                "0x02": {"type": "Router"},
            },
            "links": [link],
        }
    )
    repo.store_topology_parsed(snapshot_id, "home", parsed, status="complete")
    repo.db.conn.execute(
        "UPDATE topology_snapshots SET captured_at = ? WHERE snapshot_id = ?",
        (captured_at.isoformat(), snapshot_id),
    )
    repo.db.conn.commit()


def _priority(
    *,
    card_type: str,
    network_id: str = "home",
    card_id: str = "priority-1",
) -> InvestigationPrioritySummary:
    return InvestigationPrioritySummary(
        id=card_id,
        network_id=network_id,
        card_type=card_type,
        priority="Review first",
        score=10,
        action_group="review_observed_router_area",
        title="Priority title",
        summary="Priority summary",
        device_ieees=[],
        latest_supporting_evidence_at=_now().isoformat(),
    )


def test_empty_dashboard_includes_data_coverage_warnings(tmp_path: Path):
    repo, config = _repo(tmp_path)
    dash = build_empty_dashboard(config, repo.list_networks())
    assert dash.data_coverage_warnings == []


def test_compose_surfaces_availability_tracking_off(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "home", "0xa1")
    warnings = compose_dashboard_coverage_warnings(repo, repo.list_networks(), config)
    assert any(item.label_code == "availability_tracking_off" for item in warnings)
    assert all(item.scope_type == "network" for item in warnings)
    assert len(warnings) <= MAX_OVERVIEW_COVERAGE_WARNINGS


def test_explicit_current_availability_without_transitions_is_not_history_building(
    tmp_path: Path,
):
    """Stable online devices with no transitions are tracked, not 'building'."""
    repo, config = _repo(tmp_path)
    _add_device(repo, "home", "0xa1", availability="online")
    warnings = compose_dashboard_coverage_warnings(repo, repo.list_networks(), config)
    codes = {item.label_code for item in warnings}
    assert "availability_tracking_off" not in codes
    assert "availability_history_building" not in codes


def test_dashboard_payload_includes_coverage_warnings(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "home", "0xa1")
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    dash = PayloadBuilder(config, repo, health).dashboard()
    assert any(item.label_code == "availability_tracking_off" for item in dash.data_coverage_warnings)


def test_route_hints_absent_for_shared_event_priority_only(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "home", "0xa1", availability="online")
    _store_snapshot(repo, with_routes=False)
    warnings = compose_dashboard_coverage_warnings(
        repo,
        repo.list_networks(),
        config,
        route_hint_relevant_network_ids=set(),
    )
    assert all(item.label_code != "route_hints_unavailable" for item in warnings)


def test_route_hints_absent_for_model_pattern_priority_only(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "home", "0xa1", availability="online")
    _store_snapshot(repo, with_routes=False)
    # Composer receives only router-area network IDs; model patterns pass empty set.
    warnings = compose_dashboard_coverage_warnings(
        repo,
        repo.list_networks(),
        config,
        route_hint_relevant_network_ids=set(),
    )
    assert all(item.label_code != "route_hints_unavailable" for item in warnings)


def test_route_hints_present_when_router_area_priority_selected(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "home", "0xa1", availability="online")
    _store_snapshot(repo, with_routes=False)
    warnings = compose_dashboard_coverage_warnings(
        repo,
        repo.list_networks(),
        config,
        route_hint_relevant_network_ids={"home"},
    )
    assert any(item.label_code == "route_hints_unavailable" for item in warnings)


def test_route_hints_suppressed_when_routes_present(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "home", "0xa1", availability="online")
    _store_snapshot(repo, with_routes=True)
    warnings = compose_dashboard_coverage_warnings(
        repo,
        repo.list_networks(),
        config,
        route_hint_relevant_network_ids={"home"},
    )
    assert all(item.label_code != "route_hints_unavailable" for item in warnings)


def test_snapshot_stale_when_automatic_capture_policy_applies(tmp_path: Path):
    repo, config = _repo(tmp_path, automatic_capture_enabled=True)
    _add_device(repo, "home", "0xa1", availability="online")
    _store_snapshot(repo, captured_at=_now() - timedelta(hours=48), with_routes=True)
    warnings = compose_dashboard_coverage_warnings(repo, repo.list_networks(), config)
    assert any(item.label_code == "snapshot_stale" for item in warnings)


def test_payload_builder_gates_route_hints_by_router_area_card_type(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "home", "0xa1", availability="online")
    _store_snapshot(repo, with_routes=False)
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    builder = PayloadBuilder(config, repo, health)

    with patch(
        "zigbeelens.services.payload_builder.compose_dashboard_investigation_priorities",
        return_value=[_priority(card_type="shared_availability_event")],
    ):
        shared_only = builder.dashboard()
    assert all(
        item.label_code != "route_hints_unavailable"
        for item in shared_only.data_coverage_warnings
    )

    with patch(
        "zigbeelens.services.payload_builder.compose_dashboard_investigation_priorities",
        return_value=[_priority(card_type="model_pattern_review")],
    ):
        model_only = builder.dashboard()
    assert all(
        item.label_code != "route_hints_unavailable"
        for item in model_only.data_coverage_warnings
    )

    with patch(
        "zigbeelens.services.payload_builder.compose_dashboard_investigation_priorities",
        return_value=[_priority(card_type="router_neighbourhood_review")],
    ):
        router_area = builder.dashboard()
    assert any(
        item.label_code == "route_hints_unavailable"
        for item in router_area.data_coverage_warnings
    )


def test_dashboard_aggregates_history_last_known_passive_once_for_one_network(
    monkeypatch,
    tmp_path: Path,
):
    """Coverage composition must not re-run investigation evidence aggregators."""
    repo, config = _repo(tmp_path)
    _add_device(repo, "home", "0xa1", availability="online")
    _store_snapshot(repo, with_routes=False)
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()

    from zigbeelens.services import evidence_graph as evidence_graph_module
    from zigbeelens.topology.history import (
        aggregate_historical_evidence,
        aggregate_last_known_links,
    )
    from zigbeelens.topology.passive_hints import aggregate_passive_hints

    historical_calls = {"count": 0}
    last_known_calls = {"count": 0}
    passive_calls = {"count": 0}

    def _historical_spy(*args, **kwargs):
        historical_calls["count"] += 1
        return aggregate_historical_evidence(*args, **kwargs)

    def _last_known_spy(*args, **kwargs):
        last_known_calls["count"] += 1
        return aggregate_last_known_links(*args, **kwargs)

    def _passive_spy(*args, **kwargs):
        passive_calls["count"] += 1
        return aggregate_passive_hints(*args, **kwargs)

    monkeypatch.setattr(
        evidence_graph_module, "aggregate_historical_evidence", _historical_spy
    )
    monkeypatch.setattr(
        evidence_graph_module, "aggregate_last_known_links", _last_known_spy
    )
    monkeypatch.setattr(evidence_graph_module, "aggregate_passive_hints", _passive_spy)

    PayloadBuilder(config, repo, health).dashboard()

    assert historical_calls["count"] == 1
    assert last_known_calls["count"] == 1
    assert passive_calls["count"] == 1
