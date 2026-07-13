"""EvidenceGraphService unit tests — behaviour parity without the HTTP layer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.router_area import observed_router_areas_for_network
from zigbeelens.services.evidence_graph import EvidenceGraphService, NetworkNotFoundError
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.history import RECENT_HISTORY_WINDOW_DAYS
from zigbeelens.topology.parser import parse_networkmap_payload

NOW = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "evidence-graph.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "evidence-graph.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    return repo


def _store_snapshot(
    repo: Repository,
    snapshot_id: str,
    *,
    captured_at: datetime,
    links: list[dict],
) -> None:
    repo.create_topology_snapshot(
        snapshot_id=snapshot_id,
        network_id="home",
        requested_by="test",
        status="pending",
        warning_acknowledged=True,
    )
    parsed = parse_networkmap_payload(
        {
            "nodes": {
                "0x01": {"type": "Coordinator"},
                "0x02": {"type": "Router"},
                "0x03": {"type": "Router"},
                "0x04": {"type": "EndDevice"},
            },
            "links": links,
        }
    )
    repo.store_topology_parsed(snapshot_id, "home", parsed, status="complete")
    repo.db.conn.execute(
        "UPDATE topology_snapshots SET captured_at = ? WHERE snapshot_id = ?",
        (captured_at.isoformat(), snapshot_id),
    )
    repo.db.conn.commit()


def test_build_unknown_network_raises(tmp_path: Path):
    service = EvidenceGraphService(_repo(tmp_path))
    with pytest.raises(NetworkNotFoundError):
        service.build("nope")


def test_build_returns_expected_counts_and_windows(tmp_path: Path):
    repo = _repo(tmp_path)
    service = EvidenceGraphService(repo)
    now = datetime.now(timezone.utc)
    _store_snapshot(
        repo,
        "snap-old",
        captured_at=now - timedelta(days=1),
        links=[
            {"source": "0x02", "target": "0x04", "linkquality": 70},
            {
                "source": "0x03",
                "target": "0x01",
                "linkquality": 90,
                "routes": [{"destinationAddress": 0, "nextHop": 0}],
            },
        ],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=now - timedelta(hours=1),
        links=[
            {
                "source": "0x02",
                "target": "0x01",
                "linkquality": 120,
                "routes": [{"destinationAddress": 0, "nextHop": 0}],
            }
        ],
    )

    body = service.build("home")
    assert body["network_id"] == "home"
    assert body["network_name"] == "Home"
    assert body["data_source"] == "latest_snapshot_plus_history"
    assert body["latest_snapshot"]["snapshot_id"] == "snap-latest"
    assert body["history_window"]["days"] == RECENT_HISTORY_WINDOW_DAYS
    assert body["history_window"]["snapshots_considered"] == 1
    assert body["counts"]["latest_snapshot_neighbor_edges"] == 1
    assert body["counts"]["latest_snapshot_route_edges"] == 1
    assert body["counts"]["historical_neighbor_edges"] == 2
    assert body["counts"]["historical_route_edges"] == 1
    assert body["counts"]["recent_missing_link_count_total"] == 3
    assert body["counts"]["last_known_link_count"] == len(body["last_known_links"])
    assert body["counts"]["hidden_for_readability"] is None
    assert body["counts"]["passive_hint_count_drawn"] is None
    assert isinstance(body["investigations"], list)
    assert isinstance(body["device_stats"], dict)


def test_build_empty_snapshot_state(tmp_path: Path):
    body = EvidenceGraphService(_repo(tmp_path)).build("home")
    assert body["latest_snapshot"] is None
    assert body["latest_layout_limited"] is True
    assert body["layout_available"] is False
    assert body["counts"]["latest_snapshot_neighbor_edges"] == 0
    assert body["counts"]["latest_snapshot_route_edges"] == 0


def test_build_composes_observed_model_patterns_once(monkeypatch, tmp_path: Path):
    repo = _repo(tmp_path)
    service = EvidenceGraphService(repo)
    calls = {"count": 0}
    from zigbeelens.decisions.model_pattern import observed_model_patterns_for_network

    original = observed_model_patterns_for_network

    def _spy(*args, **kwargs):
        calls["count"] += 1
        return original(*args, **kwargs)

    from zigbeelens.services import evidence_graph as evidence_graph_module

    monkeypatch.setattr(
        evidence_graph_module, "observed_model_patterns_for_network", _spy
    )
    service.build("home")
    assert calls["count"] == 1


def test_build_composes_observed_router_areas_once(monkeypatch, tmp_path: Path):
    repo = _repo(tmp_path)
    service = EvidenceGraphService(repo)
    calls = {"count": 0}
    original = observed_router_areas_for_network

    def _spy(*args, **kwargs):
        calls["count"] += 1
        return original(*args, **kwargs)

    from zigbeelens.services import evidence_graph as evidence_graph_module

    monkeypatch.setattr(evidence_graph_module, "observed_router_areas_for_network", _spy)
    service.build("home")
    assert calls["count"] == 1
