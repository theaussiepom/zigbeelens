"""Dashboard investigation priority composition tests (Phase 5A-1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.availability_event_groups import SHARED_EVENT_MIN_DEVICES
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.services.dashboard_investigation_priorities import (
    MAX_OVERVIEW_INVESTIGATION_PRIORITIES,
    compose_dashboard_investigation_priorities,
)
from zigbeelens.services.empty_state import build_empty_dashboard
from zigbeelens.services.evidence_graph import EvidenceGraphService
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
    db_path = tmp_path / "dashboard-investigation-priorities.sqlite"
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
) -> list[str]:
    devices = [f"{device_prefix}{i:02d}" for i in range(SHARED_EVENT_MIN_DEVICES)]
    for ieee in devices:
        _add_device(repo, network_id, ieee)
    for index, ieee in enumerate(devices):
        _offline_event(repo, network_id, ieee, base + timedelta(seconds=10 * index))
    return devices


def _fake_card(
    card_id: str,
    *,
    score: int,
    evidence_at: str,
    card_type: str = "shared_availability_event",
    priority: str = "Review first",
    action_group: str = "investigate_shared_event",
) -> dict:
    return {
        "id": card_id,
        "type": card_type,
        "priority": priority,
        "score": score,
        "action_group": action_group,
        "title": f"Title {card_id}",
        "summary": f"Summary {card_id}",
        "device_ieees": [],
        "latest_supporting_evidence_at": evidence_at,
    }


def test_empty_dashboard_includes_investigation_priorities(tmp_path: Path):
    repo, config = _repo(tmp_path)
    dash = build_empty_dashboard(config, repo.list_networks())
    assert dash.investigation_priorities == []


def test_compose_returns_empty_without_qualifying_investigations(tmp_path: Path):
    repo, _ = _repo(tmp_path)
    _add_device(repo, "home", "0xa1")
    summaries = compose_dashboard_investigation_priorities(repo, repo.list_networks())
    assert summaries == []


def test_dashboard_payload_includes_shared_event_investigation_priority(tmp_path: Path):
    repo, config = _repo(tmp_path)
    devices = _seed_shared_event(repo, "home", base=_now() - timedelta(days=1))
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    dash = PayloadBuilder(config, repo, health).dashboard()
    assert len(dash.investigation_priorities) >= 1
    priority = next(
        item
        for item in dash.investigation_priorities
        if item.card_type == "shared_availability_event"
    )
    assert priority.network_id == "home"
    assert priority.action_group == "investigate_shared_event"
    assert priority.title
    assert priority.summary
    assert set(priority.device_ieees).issubset(set(devices))
    assert priority.latest_supporting_evidence_at is not None


def test_dashboard_uses_same_investigation_path_as_evidence_graph(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _seed_shared_event(repo, "home", base=_now() - timedelta(days=1))
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    composed = compose_dashboard_investigation_priorities(repo, repo.list_networks())
    dash = PayloadBuilder(config, repo, health).dashboard()
    assert dash.investigation_priorities == composed

    service = EvidenceGraphService(repo)
    mesh_cards = service.investigations_for_network("home")["investigations"]
    composed_ids = {item.id for item in composed}
    assert composed_ids.issubset({card["id"] for card in mesh_cards})


def test_evidence_graph_build_matches_investigations_for_network(tmp_path: Path):
    repo, _ = _repo(tmp_path)
    _seed_shared_event(repo, "home", base=_now() - timedelta(days=1))
    service = EvidenceGraphService(repo)
    built = service.build("home")
    investigations = service.investigations_for_network("home")
    assert built["investigations"] == investigations["investigations"]
    assert built["investigation_counts"]["available"] == investigations["available_count"]


def test_compose_uses_global_ranked_top_six_across_networks(tmp_path: Path):
    """Higher Home priorities must survive even when Office contributes lower scores."""
    networks = [
        NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
        NetworkConfig(id="office", name="Office", base_topic="zigbee2mqtt/office"),
    ]
    repo, _ = _repo(tmp_path, networks=networks)
    evidence = "2026-07-12T12:00:00+00:00"
    home_cards = [
        _fake_card("home-12", score=12, evidence_at=evidence),
        _fake_card("home-11", score=11, evidence_at=evidence),
        _fake_card("home-10", score=10, evidence_at=evidence),
        _fake_card("home-9", score=9, evidence_at=evidence),
    ]
    office_cards = [
        _fake_card("office-8", score=8, evidence_at=evidence),
        _fake_card("office-7", score=7, evidence_at=evidence),
        _fake_card("office-6", score=6, evidence_at=evidence),
    ]

    def _fake_investigations(network_id: str, *, now=None, context=None) -> dict:
        cards = home_cards if network_id == "home" else office_cards
        return {"investigations": cards, "available_count": len(cards)}

    with patch.object(
        EvidenceGraphService,
        "investigations_for_network",
        side_effect=_fake_investigations,
    ):
        summaries = compose_dashboard_investigation_priorities(repo, repo.list_networks())

    scores = [item.score for item in summaries]
    assert scores == [12, 11, 10, 9, 8, 7]
    assert len(summaries) == MAX_OVERVIEW_INVESTIGATION_PRIORITIES
    assert {item.id for item in summaries} == {
        "home-12",
        "home-11",
        "home-10",
        "home-9",
        "office-8",
        "office-7",
    }
    assert "office-6" not in {item.id for item in summaries}
    assert any(item.id == "home-9" for item in summaries)


def test_compose_breaks_equal_score_ties_by_recency(tmp_path: Path):
    networks = [
        NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
    ]
    repo, _ = _repo(tmp_path, networks=networks)
    yesterday = "2026-07-11T12:00:00+00:00"
    today = "2026-07-12T12:00:00+00:00"
    cards = [
        _fake_card("card-a", score=8, evidence_at=yesterday),
        _fake_card("card-b", score=8, evidence_at=today),
    ]

    with patch.object(
        EvidenceGraphService,
        "investigations_for_network",
        return_value={"investigations": cards, "available_count": 2},
    ):
        summaries = compose_dashboard_investigation_priorities(repo, repo.list_networks())

    assert [item.id for item in summaries] == ["card-b", "card-a"]


def test_investigation_priorities_do_not_change_dashboard_severity_or_incident_counts(
    tmp_path: Path,
):
    repo, config = _repo(tmp_path)
    _seed_shared_event(repo, "home", base=_now() - timedelta(days=1))
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    builder = PayloadBuilder(config, repo, health)

    with patch(
        "zigbeelens.services.payload_builder.compose_dashboard_investigation_priorities",
        return_value=[],
    ):
        baseline = builder.dashboard()

    with_priorities = builder.dashboard()

    assert baseline.investigation_priorities == []
    assert with_priorities.investigation_priorities
    assert with_priorities.overall_severity == baseline.overall_severity
    assert with_priorities.current_finding == baseline.current_finding
    assert with_priorities.active_incident_count == baseline.active_incident_count
    assert with_priorities.watching_incident_count == baseline.watching_incident_count
