"""Recent-missing topology evidence aggregation tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.history import (
    HISTORICAL_NEIGHBOR_LIMITATION,
    HISTORICAL_NEIGHBOR_LIMITED_LIMITATION,
    HISTORICAL_ROUTE_LIMITATION,
    LAST_KNOWN_LINK_LIMITATION,
    LAST_KNOWN_LINKS_PER_DEVICE,
    LATEST_LAYOUT_LIMITED_LIMITATION,
    NOT_IN_LATEST_LIMITATION,
    RECENT_HISTORY_MAX_SNAPSHOTS,
    RECENT_HISTORY_WINDOW_DAYS,
    aggregate_historical_evidence,
    aggregate_last_known_links,
)
from zigbeelens.topology.parser import parse_networkmap_payload

NOW = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "history.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "history.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    return repo


def _store_snapshot(
    repo: Repository,
    snapshot_id: str,
    *,
    captured_at: datetime,
    links: list[dict],
    nodes: dict[str, dict] | None = None,
    status: str = "complete",
) -> None:
    repo.create_topology_snapshot(
        snapshot_id=snapshot_id,
        network_id="home",
        requested_by="test",
        status="pending",
        warning_acknowledged=True,
    )
    default_nodes = {
        "0x01": {"type": "Coordinator"},
        "0x02": {"type": "Router"},
        "0x03": {"type": "Router"},
        "0x04": {"type": "EndDevice"},
    }
    parsed = parse_networkmap_payload(
        {"nodes": default_nodes if nodes is None else nodes, "links": links}
    )
    repo.store_topology_parsed(snapshot_id, "home", parsed, status=status)
    repo.db.conn.execute(
        "UPDATE topology_snapshots SET captured_at = ? WHERE snapshot_id = ?",
        (captured_at.isoformat(), snapshot_id),
    )
    repo.db.conn.commit()


def test_historical_neighbor_aggregation_first_last_counts_and_lqi(tmp_path: Path):
    repo = _repo(tmp_path)
    # Three previous snapshots observe 0x02↔0x04 with varying LQI; the latest
    # snapshot does not contain that pair.
    _store_snapshot(
        repo,
        "snap-1",
        captured_at=NOW - timedelta(days=3),
        links=[{"source": "0x02", "target": "0x04", "linkquality": 60}],
    )
    _store_snapshot(
        repo,
        "snap-2",
        captured_at=NOW - timedelta(days=2),
        links=[
            {"source": "0x02", "target": "0x04", "linkquality": 100},
            # Reverse direction in the same snapshot: same unordered pair.
            {"source": "0x04", "target": "0x02", "linkquality": 90, "relationship": 1},
        ],
    )
    _store_snapshot(
        repo,
        "snap-3",
        captured_at=NOW - timedelta(days=1),
        links=[{"source": "0x02", "target": "0x04", "linkquality": 80}],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 120}],
    )

    result = aggregate_historical_evidence(repo, "home", now=NOW)
    assert result["latest_layout_available"] is True
    edges = result["historical_neighbors"]
    assert len(edges) == 1
    edge = edges[0]
    assert {edge["source_ieee"], edge["target_ieee"]} == {"0x02", "0x04"}
    assert edge["evidence_class"] == "historical_neighbor"
    assert edge["first_seen_at"] == (NOW - timedelta(days=3)).isoformat()
    assert edge["last_seen_at"] == (NOW - timedelta(days=1)).isoformat()
    assert edge["observed_count"] == 4
    assert edge["snapshot_count"] == 3
    assert edge["lqi_min"] == 60
    assert edge["lqi_median"] == 85
    assert edge["lqi_max"] == 100
    assert edge["lqi_latest"] == 80
    assert edge["not_seen_in_latest_snapshot"] is True
    assert edge["confidence"] == "medium"
    assert HISTORICAL_NEIGHBOR_LIMITATION in edge["limitations"]
    assert NOT_IN_LATEST_LIMITATION in edge["limitations"]


def test_historical_route_aggregation_only_from_route_table_evidence(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-1",
        captured_at=NOW - timedelta(days=2),
        links=[
            {
                "source": "0x02",
                "target": "0x01",
                "linkquality": 100,
                "routes": [{"destinationAddress": 0, "nextHop": 0}],
            },
            # Neighbour-only link: must never become route evidence.
            {"source": "0x03", "target": "0x01", "linkquality": 200},
        ],
    )
    _store_snapshot(
        repo,
        "snap-2",
        captured_at=NOW - timedelta(days=1),
        links=[
            {
                "source": "0x02",
                "target": "0x01",
                "linkquality": 100,
                "routes": [
                    {"destinationAddress": 0, "nextHop": 0},
                    {"destinationAddress": 4002, "nextHop": 0},
                ],
            }
        ],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[{"source": "0x03", "target": "0x04", "linkquality": 50}],
    )

    result = aggregate_historical_evidence(repo, "home", now=NOW)
    routes = result["historical_routes"]
    assert len(routes) == 1
    route = routes[0]
    assert route["source_ieee"] == "0x02"
    assert route["target_ieee"] == "0x01"
    assert route["directional"] is True
    assert route["route_observed_count"] == 2
    assert route["last_route_count"] == 2
    assert route["confidence"] == "medium"
    assert HISTORICAL_ROUTE_LIMITATION in route["limitations"]
    # The neighbour-only 0x03→0x01 link appears as a historical neighbour,
    # never as route evidence.
    neighbor_pairs = {
        frozenset((e["source_ieee"], e["target_ieee"])) for e in result["historical_neighbors"]
    }
    assert frozenset(("0x03", "0x01")) in neighbor_pairs


def test_latest_snapshot_edges_are_excluded_from_historical_output(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-old",
        captured_at=NOW - timedelta(days=1),
        links=[
            {
                "source": "0x02",
                "target": "0x01",
                "linkquality": 100,
                "routes": [{"destinationAddress": 0, "nextHop": 0}],
            },
            {"source": "0x03", "target": "0x01", "linkquality": 80},
        ],
    )
    # Latest still observes both relationships (including the route).
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[
            {
                "source": "0x02",
                "target": "0x01",
                "linkquality": 110,
                "routes": [{"destinationAddress": 0, "nextHop": 0}],
            },
            # Reverse direction still matches the same unordered neighbour pair.
            {"source": "0x01", "target": "0x03", "linkquality": 90},
        ],
    )

    result = aggregate_historical_evidence(repo, "home", now=NOW)
    assert result["historical_neighbors"] == []
    assert result["historical_routes"] == []


def test_null_route_count_is_unknown_not_zero(tmp_path: Path):
    repo = _repo(tmp_path)
    # Old snapshot link without a routes key: route evidence unknown (NULL).
    _store_snapshot(
        repo,
        "snap-old",
        captured_at=NOW - timedelta(days=1),
        links=[{"source": "0x02", "target": "0x04", "linkquality": 70}],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 100}],
    )
    stored = repo.list_topology_links("snap-old")
    assert stored[0]["route_count"] is None

    result = aggregate_historical_evidence(repo, "home", now=NOW)
    assert result["historical_routes"] == []
    edge = result["historical_neighbors"][0]
    # Unknown route evidence stays None on the aggregate, never zero.
    assert edge["route_observed_count"] is None
    assert edge["last_route_count"] is None


def test_limited_latest_snapshot_does_not_overclaim_missing_evidence(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-old",
        captured_at=NOW - timedelta(days=1),
        links=[{"source": "0x02", "target": "0x04", "linkquality": 70}],
    )
    # Latest complete snapshot parsed to nothing (limited layout).
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[],
        nodes={},
    )

    result = aggregate_historical_evidence(repo, "home", now=NOW)
    assert result["latest_layout_available"] is False
    assert LATEST_LAYOUT_LIMITED_LIMITATION in result["limitations"]
    edge = result["historical_neighbors"][0]
    assert edge["latest_layout_limited"] is True
    # Limited layout gets the qualified copy, never a "missing from latest" claim.
    assert HISTORICAL_NEIGHBOR_LIMITED_LIMITATION in edge["limitations"]
    assert HISTORICAL_NEIGHBOR_LIMITATION not in edge["limitations"]
    assert NOT_IN_LATEST_LIMITATION not in edge["limitations"]


def test_incomplete_and_out_of_window_snapshots_are_ignored(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-failed",
        captured_at=NOW - timedelta(days=1),
        links=[{"source": "0x02", "target": "0x04", "linkquality": 70}],
        status="failed",
    )
    # Outside the recent window: contributes nothing (no forever history).
    _store_snapshot(
        repo,
        "snap-too-old",
        captured_at=NOW - timedelta(days=RECENT_HISTORY_WINDOW_DAYS + 2),
        links=[{"source": "0x03", "target": "0x04", "linkquality": 70}],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 100}],
    )

    result = aggregate_historical_evidence(repo, "home", now=NOW)
    assert result["historical_neighbors"] == []
    assert result["historical_routes"] == []
    assert result["history_window"]["snapshots_considered"] == 0
    assert any("No previous complete topology snapshots" in item for item in result["limitations"])


def test_history_window_caps_snapshot_count(tmp_path: Path):
    repo = _repo(tmp_path)
    for i in range(RECENT_HISTORY_MAX_SNAPSHOTS + 3):
        _store_snapshot(
            repo,
            f"snap-{i}",
            captured_at=NOW - timedelta(days=1, minutes=i),
            links=[{"source": "0x02", "target": "0x04", "linkquality": 70}],
        )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 100}],
    )

    result = aggregate_historical_evidence(repo, "home", now=NOW)
    assert result["history_window"]["snapshots_considered"] == RECENT_HISTORY_MAX_SNAPSHOTS
    edge = result["historical_neighbors"][0]
    assert edge["snapshot_count"] == RECENT_HISTORY_MAX_SNAPSHOTS


def test_recent_window_is_recent_not_forever_history(tmp_path: Path):
    """Snapshots older than the recent window never contribute, even when
    still stored: the feature explains recent gaps, not forever history."""
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-ancient",
        captured_at=NOW - timedelta(days=RECENT_HISTORY_WINDOW_DAYS + 10),
        links=[{"source": "0x03", "target": "0x04", "linkquality": 90}],
    )
    _store_snapshot(
        repo,
        "snap-recent",
        captured_at=NOW - timedelta(days=2),
        links=[{"source": "0x02", "target": "0x04", "linkquality": 70}],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 100}],
    )

    result = aggregate_historical_evidence(repo, "home", now=NOW)
    pairs = {
        frozenset((e["source_ieee"], e["target_ieee"])) for e in result["historical_neighbors"]
    }
    assert frozenset(("0x02", "0x04")) in pairs
    assert frozenset(("0x03", "0x04")) not in pairs
    assert result["history_window"]["days"] == RECENT_HISTORY_WINDOW_DAYS
    assert result["history_window"]["snapshots_considered"] == 1


def test_last_known_links_for_devices_absent_from_latest_snapshot(tmp_path: Path):
    """A device with no links in the latest snapshot gets its most recent
    stored link evidence, clearly marked as last known and not currently
    reported. This is the sleepy-end-device case: the device is healthy but
    its entries aged out of router neighbour tables."""
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-older",
        captured_at=NOW - timedelta(days=5),
        links=[{"source": "0x03", "target": "0x04", "linkquality": 40}],
    )
    _store_snapshot(
        repo,
        "snap-newer",
        captured_at=NOW - timedelta(days=2),
        links=[
            {"source": "0x02", "target": "0x04", "linkquality": 90},
            {"source": "0x03", "target": "0x04", "linkquality": 60},
            {"source": "0x01", "target": "0x04", "linkquality": 30},
        ],
    )
    # 0x04 has no links at all in the latest snapshot.
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 120}],
    )

    result = aggregate_last_known_links(repo, "home")
    edges = result["last_known_links"]
    pairs = {frozenset((e["source_ieee"], e["target_ieee"])) for e in edges}
    # Strongest links from the most recent snapshot that mentioned 0x04,
    # capped per device — the weakest of the three is left out.
    assert len(edges) == LAST_KNOWN_LINKS_PER_DEVICE
    assert frozenset(("0x02", "0x04")) in pairs
    assert frozenset(("0x03", "0x04")) in pairs
    for edge in edges:
        assert edge["evidence_class"] == "last_known_link"
        assert edge["directional"] is False
        assert edge["confidence"] == "low"
        assert edge["not_seen_in_latest_snapshot"] is True
        assert edge["last_reported_at"] == (NOW - timedelta(days=2)).isoformat()
        assert LAST_KNOWN_LINK_LIMITATION in edge["limitations"]
    # Devices linked in the latest snapshot contribute nothing.
    assert frozenset(("0x02", "0x01")) not in pairs


def test_last_known_links_come_from_newest_mentioning_snapshot_only(tmp_path: Path):
    """Older snapshots never override the newest one that mentioned the
    device — "last known" is the most recent stored evidence, not a merge of
    everything ever observed."""
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-older",
        captured_at=NOW - timedelta(days=6),
        links=[{"source": "0x02", "target": "0x04", "linkquality": 200}],
    )
    _store_snapshot(
        repo,
        "snap-newer",
        captured_at=NOW - timedelta(days=2),
        links=[{"source": "0x03", "target": "0x04", "linkquality": 50}],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 120}],
    )

    result = aggregate_last_known_links(repo, "home")
    pairs = {frozenset((e["source_ieee"], e["target_ieee"])) for e in result["last_known_links"]}
    assert frozenset(("0x03", "0x04")) in pairs
    # The stronger-but-older link is not "last known".
    assert frozenset(("0x02", "0x04")) not in pairs


def test_last_known_links_skip_incomplete_snapshots(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-failed",
        captured_at=NOW - timedelta(days=1),
        links=[{"source": "0x02", "target": "0x04", "linkquality": 70}],
        status="failed",
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 120}],
    )
    result = aggregate_last_known_links(repo, "home")
    assert result["last_known_links"] == []


def test_last_known_links_empty_when_latest_layout_limited(tmp_path: Path):
    """When the latest layout is limited, "linkless in the latest snapshot"
    is meaningless, so no last known links are claimed."""
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-old",
        captured_at=NOW - timedelta(days=2),
        links=[{"source": "0x02", "target": "0x04", "linkquality": 70}],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[],
        nodes={},
    )
    result = aggregate_last_known_links(repo, "home")
    assert result["last_known_links"] == []
    assert any("limited" in item for item in result["limitations"])


def test_last_known_link_wording_never_claims_current_connectivity(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-old",
        captured_at=NOW - timedelta(days=2),
        links=[{"source": "0x02", "target": "0x04", "linkquality": 70}],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 120}],
    )
    result = aggregate_last_known_links(repo, "home")
    text = str(result).lower()
    for forbidden in ["parent router", "current route", "currently routed", "actual path"]:
        assert forbidden not in text


def test_evidence_graph_api_includes_historical_counts(topology_client: TestClient):
    from zigbeelens.app.context import get_context

    ctx = get_context()
    repo = ctx.repo
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

    res = topology_client.get("/api/topology/home/evidence-graph")
    assert res.status_code == 200
    body = res.json()
    assert body["network_id"] == "home"
    assert body["data_source"] == "latest_snapshot_plus_history"
    assert body["latest_snapshot"]["snapshot_id"] == "snap-latest"
    assert body["history_window"]["days"] == RECENT_HISTORY_WINDOW_DAYS
    assert body["history_window"]["snapshots_considered"] == 1
    assert body["latest_layout_limited"] is False
    assert body["counts"]["latest_snapshot_neighbor_edges"] == 1
    assert body["counts"]["latest_snapshot_route_edges"] == 1
    assert body["counts"]["historical_neighbor_edges"] == 2
    assert body["counts"]["historical_route_edges"] == 1
    assert body["counts"]["recent_missing_link_count_total"] == 3
    # 0x03 and 0x04 have no links in the latest snapshot: each contributes
    # its most recent stored evidence as last known links.
    assert isinstance(body["last_known_links"], list)
    assert body["counts"]["last_known_link_count"] == len(body["last_known_links"])
    assert body["counts"]["last_known_link_count"] > 0
    for edge in body["last_known_links"]:
        assert edge["evidence_class"] == "last_known_link"
    # Rendering subsets are a client decision: unknown, never zero.
    assert body["counts"]["hidden_for_readability"] is None
    assert body["counts"]["observed_topology_nodes"] == len(body["nodes"])
    assert isinstance(body["historical_neighbors"], list)
    assert isinstance(body["historical_routes"], list)
    # v1 alias serves the same endpoint.
    v1 = topology_client.get("/api/v1/topology/home/evidence-graph")
    assert v1.status_code == 200
    assert v1.json()["counts"] == body["counts"]


def test_evidence_graph_api_unknown_network_is_404(topology_client: TestClient):
    res = topology_client.get("/api/topology/nope/evidence-graph")
    assert res.status_code == 404
