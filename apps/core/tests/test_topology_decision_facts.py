"""Topology decision fact builder tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.topology_facts import (
    TOPOLOGY_FACT_CODES,
    TopologyFactCode,
    build_device_latest_topology_facts,
    build_device_snapshot_comparison_facts,
    build_network_topology_facts,
    build_topology_facts_from_evidence_graph,
    topology_device_facts_payload,
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


def _latest_snapshot_body(*, captured_at: datetime | None = None) -> dict:
    return {
        "snapshot_id": "snap-latest",
        "status": "complete",
        "captured_at": (captured_at or NOW).isoformat(),
    }


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


def test_network_facts_stale_snapshot_requires_explicit_threshold(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-stale",
        captured_at=NOW - timedelta(hours=30),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 90}],
    )
    latest = repo.get_latest_topology_snapshot("home")
    nodes = repo.list_topology_nodes(latest["snapshot_id"])
    links = repo.list_topology_links(latest["snapshot_id"])

    facts_without_threshold = build_network_topology_facts(
        latest_snapshot=latest,
        nodes=nodes,
        links=links,
        now=NOW,
    )
    assert TopologyFactCode.latest_snapshot_stale not in _codes(facts_without_threshold)

    facts = build_network_topology_facts(
        latest_snapshot=latest,
        nodes=nodes,
        links=links,
        now=NOW,
        stale_after_hours=24,
    )
    assert TopologyFactCode.latest_snapshot_complete in _codes(facts)
    assert TopologyFactCode.latest_snapshot_stale in _codes(facts)
    stale = next(f for f in facts if f.code == TopologyFactCode.latest_snapshot_stale)
    assert stale.params["stale_after_hours"] == 24
    assert stale.params["age_hours"] > 24


def test_network_facts_stale_threshold_72h_snapshot_age_30h_not_stale():
    facts = build_network_topology_facts(
        latest_snapshot=_latest_snapshot_body(captured_at=NOW - timedelta(hours=30)),
        nodes=[{"ieee_address": "0x02"}],
        links=[{"source_ieee": "0x02", "target_ieee": "0x01", "linkquality": 90}],
        now=NOW,
        stale_after_hours=72,
    )
    assert TopologyFactCode.latest_snapshot_complete in _codes(facts)
    assert TopologyFactCode.latest_snapshot_stale not in _codes(facts)


def test_network_facts_stale_threshold_6h_snapshot_age_12h_is_stale():
    facts = build_network_topology_facts(
        latest_snapshot=_latest_snapshot_body(captured_at=NOW - timedelta(hours=12)),
        nodes=[{"ieee_address": "0x02"}],
        links=[{"source_ieee": "0x02", "target_ieee": "0x01", "linkquality": 90}],
        now=NOW,
        stale_after_hours=6,
    )
    assert TopologyFactCode.latest_snapshot_stale in _codes(facts)
    stale = next(f for f in facts if f.code == TopologyFactCode.latest_snapshot_stale)
    assert stale.params["stale_after_hours"] == 6
    assert stale.params["age_hours"] == 12.0


def test_network_facts_no_route_hints(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-neighbours-only",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x01", "linkquality": 90}],
    )
    body = EvidenceGraphService(repo).build("home", now=NOW)

    facts = build_network_topology_facts(
        latest_snapshot=body["latest_snapshot"],
        nodes=body["nodes"],
        links=body["links"],
        counts=body["counts"],
        now=NOW,
    )
    assert TopologyFactCode.route_hints_unavailable in _codes(facts)
    assert TopologyFactCode.route_hints_available not in _codes(facts)


def test_network_facts_last_known_links_available(tmp_path: Path):
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
    body = EvidenceGraphService(repo).build("home", now=NOW)

    facts = build_network_topology_facts(
        latest_snapshot=body["latest_snapshot"],
        nodes=body["nodes"],
        links=body["links"],
        counts=body["counts"],
        now=NOW,
    )
    assert TopologyFactCode.recent_missing_links_available in _codes(facts)
    assert body["counts"]["last_known_link_count"] > 0
    assert TopologyFactCode.last_known_links_available in _codes(facts)


def test_network_facts_passive_hints_available():
    facts = build_network_topology_facts(
        latest_snapshot=_latest_snapshot_body(),
        nodes=[{"ieee_address": "0x02"}],
        links=[{"source_ieee": "0x02", "target_ieee": "0x01", "linkquality": 90}],
        counts={"passive_hint_count_available": 3},
        now=NOW,
    )
    assert TopologyFactCode.passive_hints_available in _codes(facts)
    passive = next(f for f in facts if f.code == TopologyFactCode.passive_hints_available)
    assert passive.params["hint_count"] == 3


def test_device_latest_facts_no_links():
    facts = build_device_latest_topology_facts(
        device_ieee="0x04",
        latest_snapshot={"snapshot_id": "snap-latest", "status": "complete"},
        nodes=[{"ieee_address": "0x04"}],
        links=[],
    )
    assert TopologyFactCode.device_no_latest_links in _codes(facts)
    assert TopologyFactCode.device_has_selected_snapshot_links not in _codes(facts)


def test_device_comparison_facts_selected_had_links():
    row = {
        "snapshot_id": "snap-old-1",
        "links_for_device_count": 2,
        "availability_coverage_status": COVERAGE_OFF,
        "comparison_to_latest": {"status": STATUS_WATCH},
    }
    facts = build_device_snapshot_comparison_facts(
        device_ieee="0x04",
        comparison_snapshot_row=row,
    )
    assert TopologyFactCode.device_has_selected_snapshot_links in _codes(facts)
    selected = next(
        f for f in facts if f.code == TopologyFactCode.device_has_selected_snapshot_links
    )
    assert selected.params["snapshot_id"] == "snap-old-1"
    assert selected.params["link_count"] == 2


def test_device_comparison_facts_changed_and_coverage_affects_comparison():
    facts = build_device_snapshot_comparison_facts(
        device_ieee="0x04",
        comparison_snapshot_row={
            "snapshot_id": "snap-old",
            "links_for_device_count": 2,
            "availability_coverage_status": COVERAGE_OFF,
            "comparison_to_latest": {"status": STATUS_WATCH},
        },
    )
    assert TopologyFactCode.device_has_selected_snapshot_links in _codes(facts)
    assert TopologyFactCode.device_latest_vs_selected_changed in _codes(facts)
    assert TopologyFactCode.availability_coverage_affects_snapshot_comparison in _codes(facts)


def test_device_comparison_facts_no_change_when_comparison_is_similar():
    facts = build_device_snapshot_comparison_facts(
        device_ieee="0x02",
        comparison_snapshot_row={
            "snapshot_id": "snap-old",
            "links_for_device_count": 1,
            "availability_coverage_status": "tracked",
            "comparison_to_latest": {"status": STATUS_NO_NOTABLE_CHANGE},
        },
    )
    assert TopologyFactCode.device_latest_vs_selected_changed not in _codes(facts)
    assert TopologyFactCode.availability_coverage_affects_snapshot_comparison not in _codes(facts)


def test_comparison_facts_scoped_per_snapshot_id():
    history_for_0x04 = {
        "snapshots": [
            {
                "snapshot_id": "snap-old-1",
                "links_for_device_count": 2,
                "availability_coverage_status": COVERAGE_OFF,
                "comparison_to_latest": {"status": STATUS_WATCH},
            },
            {
                "snapshot_id": "snap-old-2",
                "links_for_device_count": 0,
                "availability_coverage_status": "tracked",
                "comparison_to_latest": {"status": STATUS_NO_NOTABLE_CHANGE},
            },
        ]
    }
    evidence_graph = {
        "latest_snapshot": {"snapshot_id": "snap-latest", "status": "complete"},
        "nodes": [{"ieee_address": "0x04"}],
        "links": [],
        "counts": {},
    }

    grouped = build_topology_facts_from_evidence_graph(
        network_id="home",
        evidence_graph=evidence_graph,
        device_ieees=["0x04"],
        device_snapshot_histories={"0x04": history_for_0x04},
        now=NOW,
    )

    latest_facts = grouped.device_facts["0x04"]
    assert TopologyFactCode.device_no_latest_links in _codes(latest_facts)
    assert TopologyFactCode.device_has_selected_snapshot_links not in _codes(latest_facts)
    assert TopologyFactCode.device_latest_vs_selected_changed not in _codes(latest_facts)

    comp_old_1 = grouped.device_comparison_facts["0x04"]["snap-old-1"]
    comp_old_2 = grouped.device_comparison_facts["0x04"]["snap-old-2"]
    assert TopologyFactCode.device_has_selected_snapshot_links in _codes(comp_old_1)
    assert TopologyFactCode.device_latest_vs_selected_changed in _codes(comp_old_1)
    assert comp_old_2 == []

    for fact in comp_old_1:
        assert fact.params.get("snapshot_id") == "snap-old-1"

    payload = topology_device_facts_payload(grouped, "0x04", stale_threshold_hours=None)
    assert set(payload["comparison_facts_by_snapshot_id"].keys()) == {"snap-old-1", "snap-old-2"}
    assert "snap-unknown" not in payload["comparison_facts_by_snapshot_id"]


def test_device_snapshot_histories_are_isolated_per_device():
    history_for_0x04 = {
        "snapshots": [
            {
                "snapshot_id": "snap-old",
                "links_for_device_count": 2,
                "availability_coverage_status": COVERAGE_OFF,
                "comparison_to_latest": {"status": STATUS_WATCH},
            }
        ]
    }
    evidence_graph = {
        "latest_snapshot": {"snapshot_id": "snap-latest", "status": "complete"},
        "nodes": [{"ieee_address": "0x04"}, {"ieee_address": "0x99"}],
        "links": [],
        "counts": {},
    }

    grouped = build_topology_facts_from_evidence_graph(
        network_id="home",
        evidence_graph=evidence_graph,
        device_ieees=["0x04", "0x99"],
        device_snapshot_histories={"0x04": history_for_0x04},
        now=NOW,
    )

    facts_a = grouped.device_facts["0x04"]
    facts_b = grouped.device_facts["0x99"]
    comp_a = grouped.device_comparison_facts["0x04"]["snap-old"]

    assert TopologyFactCode.device_has_selected_snapshot_links in _codes(comp_a)
    assert TopologyFactCode.device_latest_vs_selected_changed in _codes(comp_a)
    assert TopologyFactCode.availability_coverage_affects_snapshot_comparison in _codes(comp_a)

    assert TopologyFactCode.device_has_selected_snapshot_links not in _codes(facts_a)
    assert TopologyFactCode.device_latest_vs_selected_changed not in _codes(facts_a)
    assert TopologyFactCode.availability_coverage_affects_snapshot_comparison not in _codes(facts_a)

    assert "snap-old" not in grouped.device_comparison_facts.get("0x99", {})
    assert TopologyFactCode.device_has_selected_snapshot_links not in _codes(facts_b)
    assert TopologyFactCode.device_latest_vs_selected_changed not in _codes(facts_b)
    assert TopologyFactCode.availability_coverage_affects_snapshot_comparison not in _codes(facts_b)
    assert TopologyFactCode.device_seen_in_latest_snapshot in _codes(facts_b)
    assert TopologyFactCode.device_no_latest_links in _codes(facts_b)


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
    body = EvidenceGraphService(repo).build("home", now=NOW)
    history = device_snapshot_history(repo, "home", "0x02")

    grouped = build_topology_facts_from_evidence_graph(
        network_id="home",
        evidence_graph=body,
        device_ieees=["0x02"],
        device_snapshot_histories={"0x02": history},
        now=NOW,
    )
    assert grouped.network_id == "home"
    assert TopologyFactCode.latest_snapshot_complete in _codes(grouped.network_facts)
    assert TopologyFactCode.route_hints_available in _codes(grouped.network_facts)
    assert "0x02" in grouped.device_facts
    assert TopologyFactCode.device_has_latest_links in _codes(grouped.device_facts["0x02"])


def test_evidence_graph_service_build_topology_facts_without_implicit_stale_threshold(
    tmp_path: Path,
):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=30),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 90}],
    )
    service = EvidenceGraphService(repo)

    facts_without_threshold = service.build_topology_facts("home", now=NOW)
    assert TopologyFactCode.latest_snapshot_stale not in _codes(
        facts_without_threshold.network_facts
    )

    facts_with_threshold = service.build_topology_facts("home", now=NOW, stale_after_hours=24)
    assert TopologyFactCode.latest_snapshot_stale in _codes(facts_with_threshold.network_facts)
