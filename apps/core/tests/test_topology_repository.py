"""TopologyRepository access-layer tests — delegation parity with Repository."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.parser import parse_networkmap_payload

NOW = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "topology-access.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "topology-access.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    return repo


def _store_complete_snapshot(repo: Repository, snapshot_id: str) -> None:
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
            },
            "links": [
                {
                    "source": {"ieeeAddr": "0x02"},
                    "target": {"ieeeAddr": "0x01"},
                    "lqi": 120,
                }
            ],
        }
    )
    repo.store_topology_parsed(snapshot_id, "home", parsed, status="complete")
    repo.db.conn.execute(
        "UPDATE topology_snapshots SET captured_at = ? WHERE snapshot_id = ?",
        (NOW.isoformat(), snapshot_id),
    )
    repo.db.conn.commit()


def test_topology_repository_delegates_latest_snapshot(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _store_complete_snapshot(repo, "snap-1")

    via_repo = repo.get_latest_topology_snapshot("home")
    via_access = repo.topology.get_latest_topology_snapshot("home")

    assert via_access == via_repo
    assert via_access is not None
    assert via_access["snapshot_id"] == "snap-1"


def test_topology_repository_delegates_nodes_and_links(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _store_complete_snapshot(repo, "snap-1")

    topology = repo.topology
    latest = topology.get_latest_topology_snapshot("home")
    assert latest is not None

    assert topology.list_topology_nodes(latest["snapshot_id"]) == repo.list_topology_nodes(
        latest["snapshot_id"]
    )
    assert topology.list_topology_links(latest["snapshot_id"]) == repo.list_topology_links(
        latest["snapshot_id"]
    )


def test_topology_repository_cached_on_repository_instance(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert repo.topology is repo.topology
