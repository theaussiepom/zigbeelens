"""Per-device diagnostic stats aggregation tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.device_stats import (
    DEVICE_STATS_MAX_SNAPSHOTS,
    DEVICE_STATS_WINDOW_DAYS,
    aggregate_device_stats,
)
from zigbeelens.topology.parser import parse_networkmap_payload

NOW = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "stats.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "stats.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    return repo


def _store_snapshot(
    repo: Repository,
    snapshot_id: str,
    *,
    captured_at: datetime,
    links: list[dict],
    status: str = "complete",
) -> None:
    repo.create_topology_snapshot(
        snapshot_id=snapshot_id,
        network_id="home",
        requested_by="test",
        status="pending",
        warning_acknowledged=True,
    )
    nodes = {
        "0x01": {"type": "Coordinator"},
        "0x02": {"type": "Router"},
        "0x03": {"type": "Router"},
        "0x04": {"type": "EndDevice"},
        "0x05": {"type": "EndDevice"},
    }
    parsed = parse_networkmap_payload({"nodes": nodes, "links": links})
    repo.store_topology_parsed(snapshot_id, "home", parsed, status=status)
    repo.db.conn.execute(
        "UPDATE topology_snapshots SET captured_at = ? WHERE snapshot_id = ?",
        (captured_at.isoformat(), snapshot_id),
    )
    repo.db.conn.commit()


def _record_offline(repo: Repository, ieee: str, changed_at: datetime) -> None:
    repo.db.conn.execute(
        """
        INSERT INTO availability_changes
            (network_id, ieee_address, from_state, to_state, changed_at)
        VALUES ('home', ?, 'online', 'offline', ?)
        """,
        (ieee, changed_at.isoformat()),
    )
    repo.db.conn.commit()


def test_snapshot_link_presence_and_last_router_link(tmp_path: Path):
    repo = _repo(tmp_path)
    # Older snapshot: end device 0x04 linked to router 0x02.
    _store_snapshot(
        repo,
        "s1",
        captured_at=NOW - timedelta(hours=10),
        links=[{"source": {"ieeeAddr": "0x02"}, "target": {"ieeeAddr": "0x04"}, "lqi": 90}],
    )
    # Newest snapshot: 0x04 has no links; router pair 0x02-0x03 remains.
    _store_snapshot(
        repo,
        "s2",
        captured_at=NOW - timedelta(hours=1),
        links=[{"source": {"ieeeAddr": "0x02"}, "target": {"ieeeAddr": "0x03"}, "lqi": 120}],
    )
    result = aggregate_device_stats(repo, "home", now=NOW)
    assert result["device_stats_window"]["snapshots_considered"] == 2

    stats = result["device_stats"]["0x04"]
    assert stats["snapshots_with_links"] == 1
    assert stats["last_router_link_partner"] == "0x02"
    assert stats["last_router_link_at"] == (NOW - timedelta(hours=10)).isoformat()

    router = result["device_stats"]["0x02"]
    assert router["snapshots_with_links"] == 2
    # Last router link tracks the newest snapshot that had one.
    assert router["last_router_link_at"] == (NOW - timedelta(hours=1)).isoformat()
    assert router["last_router_link_partner"] == "0x03"


def test_devices_with_no_recorded_links_have_no_entry(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "s1",
        captured_at=NOW - timedelta(hours=1),
        links=[{"source": {"ieeeAddr": "0x02"}, "target": {"ieeeAddr": "0x04"}, "lqi": 90}],
    )
    result = aggregate_device_stats(repo, "home", now=NOW)
    # 0x05 never appeared in any link and had no availability events:
    # no entry at all — unknown, not a fabricated zero record.
    assert "0x05" not in result["device_stats"]


def test_offline_transitions_counted_in_24h_and_7d_buckets(tmp_path: Path):
    repo = _repo(tmp_path)
    _record_offline(repo, "0x04", NOW - timedelta(days=3))
    _record_offline(repo, "0x04", NOW - timedelta(hours=5))
    _record_offline(repo, "0x04", NOW - timedelta(days=DEVICE_STATS_WINDOW_DAYS + 1))
    result = aggregate_device_stats(repo, "home", now=NOW)
    stats = result["device_stats"]["0x04"]
    assert stats["offline_events_7d"] == 2
    assert stats["offline_events_24h"] == 1
    assert stats["last_offline_at"] == (NOW - timedelta(hours=5)).isoformat()


def test_incomplete_and_out_of_window_snapshots_are_ignored(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "old",
        captured_at=NOW - timedelta(days=DEVICE_STATS_WINDOW_DAYS + 2),
        links=[{"source": {"ieeeAddr": "0x02"}, "target": {"ieeeAddr": "0x04"}, "lqi": 90}],
    )
    _store_snapshot(
        repo,
        "failed",
        captured_at=NOW - timedelta(hours=1),
        links=[{"source": {"ieeeAddr": "0x02"}, "target": {"ieeeAddr": "0x04"}, "lqi": 90}],
        status="failed",
    )
    result = aggregate_device_stats(repo, "home", now=NOW)
    assert result["device_stats_window"]["snapshots_considered"] == 0
    assert "0x04" not in result["device_stats"]


def test_snapshot_cap_is_enforced(tmp_path: Path):
    repo = _repo(tmp_path)
    for i in range(DEVICE_STATS_MAX_SNAPSHOTS + 3):
        _store_snapshot(
            repo,
            f"s{i}",
            captured_at=NOW - timedelta(hours=i + 1),
            links=[{"source": {"ieeeAddr": "0x02"}, "target": {"ieeeAddr": "0x04"}, "lqi": 90}],
        )
    result = aggregate_device_stats(repo, "home", now=NOW)
    assert result["device_stats_window"]["snapshots_considered"] == DEVICE_STATS_MAX_SNAPSHOTS
    assert result["device_stats"]["0x04"]["snapshots_with_links"] == DEVICE_STATS_MAX_SNAPSHOTS


def test_evidence_graph_api_includes_device_stats(topology_client: TestClient):
    body = topology_client.get("/api/topology/home/evidence-graph").json()
    assert "device_stats" in body
    assert isinstance(body["device_stats"], dict)
    window = body["device_stats_window"]
    assert window["days"] == DEVICE_STATS_WINDOW_DAYS
    assert window["max_snapshots"] == DEVICE_STATS_MAX_SNAPSHOTS
    assert "snapshots_considered" in window
