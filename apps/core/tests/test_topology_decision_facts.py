"""Topology decision fact builder tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.topology_facts import (
    DEFAULT_SNAPSHOT_STALE_AFTER_HOURS,
    TOPOLOGY_FACT_CODES,
    TopologyFactCode,
    build_device_topology_facts,
    build_network_topology_facts,
    build_topology_facts_from_evidence_graph,
)
from zigbeelens.services.evidence_graph import EvidenceGraphService
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.device_compare import (
    COVERAGE_OFF,
    STATUS_NO_NOTABLE_CHANGE,
    STATUS_WATCH,
    device_snapshot_history,
)
from zigbeelens.topology.parser import parse_networkmap_payload

NOW = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "topology-facts.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "topology-facts.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    return repo


DEFAULT_NODES = {
    "0x01": {"type": "Coordinator"},
    "0x02": {"type": "Router"},
    "0x03": {"type": "Router"},
    "0x04": {"type": "EndDevice"},
}


def _store_snapshot(
    repo: Repository,
    snapshot_id: str,
    *,
    captured_at: datetime,
    links: list[dict],
    nodes: dict[str, dict] | None = None,
) -> None:
    repo.create_topology_snapshot(
        snapshot_id=snapshot_id,
        network_id="home",
        requested_by="test",
        status="pending",
        warning_acknowledged=True,
    )
    parsed = parse_networkmap_payload(
        {"nodes": DEFAULT_NODES if nodes is None else nodes, "links": links}
    )
    repo.store_topology_parsed(snapshot_id, "home", parsed, status="complete")
    repo.db.conn.execute(
        "UPDATE topology_snapshots SET captured_at = ? WHERE snapshot_id = ?",
        (captured_at.isoformat(), snapshot_id),
    )
    repo.db.conn.commit()


def _codes(facts: list) -> set[str]:
    return {fact.code for fact in facts}


def test_topology_fact_codes_are_stable_and_unique():
    assert len(TOPOLOGY_FACT_CODES) == len(TopologyFactCode)
    assert "latest_snapshot_complete" in TOPOLOGY_FACT_CODES
    assert "passive_hints_available" in TOPOLOGY_FACT_CODES


def test_network_facts_missing_snapshot():
    facts = build_network_topology_facts(
        latest_snapshot=None,
        nodes=[],
        links=[],
    )
    assert _codes(facts) == {TopologyFactCode.latest_snapshot_missing}
    assert facts[0].params == {}


def test_network_facts_stale_snapshot(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-stale",
        captured_at=NOW - timedelta(hours=DEFAULT_SNAPSHOT_STALE_AFTER_HOURS + 6),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 90}],
    )
    latest = repo.get_latest_topology_snapshot("home")
    nodes = repo.list_topology_nodes(latest["snapshot_id"])
    links = repo.list_topology_links(latest["snapshot_id"])

    facts = build_network_topology_facts(
        latest_snapshot=latest,
        nodes=nodes,
        links=links,
        now=NOW,
    )
    assert TopologyFactCode.latest_snapshot_complete in _codes(facts)
    assert TopologyFactCode.latest_snapshot_stale in _codes(facts)
    stale = next(f for f in facts if f.code == TopologyFactCode.latest_snapshot_stale)
    assert stale.params["stale_after_hours"] == DEFAULT_SNAPSHOT_STALE_AFTER_HOURS
    assert stale.params["age_hours"] > DEFAULT_SNAPSHOT_STALE_AFTER_HOURS


def test_network_facts_no_route_hints(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-neighbours-only",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x01", "linkquality": 90}],
    )
    body = EvidenceGraphService(repo).build("home")

    facts = build_network_topology_facts(
        latest_snapshot=body["latest_snapshot"],
        nodes=body["nodes"],
        links=body["links"],
        counts=body["counts"],
        now=NOW,
    )
    assert TopologyFactCode.route_hints_unavailable in _codes(facts)
    assert TopologyFactCode.route_hints_available not in _codes(facts)


def test_network_facts_last_known_and_passive_hints(tmp_path: Path):
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
    body = EvidenceGraphService(repo).build("home")

    facts = build_network_topology_facts(
        latest_snapshot=body["latest_snapshot"],
        nodes=body["nodes"],
        links=body["links"],
        counts=body["counts"],
        now=NOW,
    )
    assert TopologyFactCode.recent_missing_links_available in _codes(facts)
    if body["counts"]["last_known_link_count"] > 0:
        assert TopologyFactCode.last_known_links_available in _codes(facts)


def test_device_facts_no_latest_links_but_selected_had_links(tmp_path: Path):
    repo = _repo(tmp_path)
    for snapshot_id, captured_at, links in (
        ("snap-1", NOW - timedelta(days=2), [{"source": "0x04", "target": "0x02", "linkquality": 80}]),
        ("snap-2", NOW - timedelta(days=1), [{"source": "0x04", "target": "0x02", "linkquality": 85}]),
        ("snap-3", NOW, []),
    ):
        _store_snapshot(repo, snapshot_id, captured_at=captured_at, links=links)

    history = device_snapshot_history(repo, "home", "0x04")
    body = EvidenceGraphService(repo).build("home")
    selected_row = history["snapshots"][0]

    facts = build_device_topology_facts(
        device_ieee="0x04",
        latest_snapshot=body["latest_snapshot"],
        nodes=body["nodes"],
        links=body["links"],
        selected_snapshot_row=selected_row,
    )
    assert TopologyFactCode.device_no_latest_links in _codes(facts)
    assert TopologyFactCode.device_has_selected_snapshot_links in _codes(facts)
    selected = next(
        f for f in facts if f.code == TopologyFactCode.device_has_selected_snapshot_links
    )
    assert selected.params["link_count"] == selected_row["links_for_device_count"]


def test_device_facts_comparison_changed_and_coverage_affects_comparison():
    facts = build_device_topology_facts(
        device_ieee="0x04",
        latest_snapshot={"snapshot_id": "snap-latest", "status": "complete"},
        nodes=[{"ieee_address": "0x04"}],
        links=[],
        selected_snapshot_row={
            "snapshot_id": "snap-old",
            "links_for_device_count": 2,
            "availability_coverage_status": COVERAGE_OFF,
            "comparison_to_latest": {"status": STATUS_WATCH},
        },
    )
    assert TopologyFactCode.device_no_latest_links in _codes(facts)
    assert TopologyFactCode.device_has_selected_snapshot_links in _codes(facts)
    assert TopologyFactCode.device_latest_vs_selected_changed in _codes(facts)
    assert TopologyFactCode.availability_coverage_affects_snapshot_comparison in _codes(facts)


def test_device_facts_no_change_when_comparison_is_similar():
    facts = build_device_topology_facts(
        device_ieee="0x02",
        latest_snapshot={"snapshot_id": "snap-latest", "status": "complete"},
        nodes=[{"ieee_address": "0x02"}],
        links=[{"source_ieee": "0x02", "target_ieee": "0x01", "linkquality": 90}],
        selected_snapshot_row={
            "snapshot_id": "snap-old",
            "links_for_device_count": 1,
            "availability_coverage_status": "tracked",
            "comparison_to_latest": {"status": STATUS_NO_NOTABLE_CHANGE},
        },
    )
    assert TopologyFactCode.device_has_latest_links in _codes(facts)
    assert TopologyFactCode.device_latest_vs_selected_changed not in _codes(facts)
    assert TopologyFactCode.availability_coverage_affects_snapshot_comparison not in _codes(facts)


def test_build_topology_facts_from_evidence_graph(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[
            {
                "source": "0x02",
                "target": "0x01",
                "linkquality": 120,
                "routes": [{"destinationAddress": 0, "nextHop": 0}],
            }
        ],
    )
    body = EvidenceGraphService(repo).build("home")
    history = device_snapshot_history(repo, "home", "0x02")

    grouped = build_topology_facts_from_evidence_graph(
        network_id="home",
        evidence_graph=body,
        device_ieees=["0x02"],
        device_snapshot_history=history,
        now=NOW,
    )
    assert grouped.network_id == "home"
    assert TopologyFactCode.latest_snapshot_complete in _codes(grouped.network_facts)
    assert TopologyFactCode.route_hints_available in _codes(grouped.network_facts)
    assert "0x02" in grouped.device_facts
    assert TopologyFactCode.device_has_latest_links in _codes(grouped.device_facts["0x02"])


def test_evidence_graph_service_build_topology_facts(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x01", "linkquality": 90}],
    )
    service = EvidenceGraphService(repo)
    facts = service.build_topology_facts("home", now=NOW)
    assert facts.network_id == "home"
    assert TopologyFactCode.latest_snapshot_complete in _codes(facts.network_facts)
