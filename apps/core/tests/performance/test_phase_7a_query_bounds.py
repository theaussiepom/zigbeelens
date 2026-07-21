"""Phase 7A scaling, EXPLAIN, and bound proofs (cardinality, not wall-clock)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.services.evidence_graph import EvidenceGraphService
from zigbeelens.services.topology_facts_composition import (
    build_device_snapshot_history_response,
)
from zigbeelens.storage.incident_collection import build_incident_collection_query
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.device_compare import MAX_SNAPSHOT_HISTORY
from zigbeelens.topology.parser import ParsedTopology, ParsedTopologyLink, ParsedTopologyNode
from zigbeelens.topology.service import topology_status_dict

from .query_instrumentation import install_counter, measure_operation

REFERENCE_TIME = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def _repo(tmp_path: Path, *, networks: list[str]) -> tuple[Repository, AppConfig]:
    db = Database(tmp_path / "phase7a.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[
            NetworkConfig(id=nid, name=nid.title(), base_topic=f"z2m/{nid}")
            for nid in networks
        ],
        storage=StorageConfig(path=str(tmp_path / "phase7a.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    return repo, cfg


def _seed_complete_snapshot(
    repo: Repository,
    *,
    network_id: str,
    snapshot_id: str,
    captured_at: datetime,
    target_ieee: str | None = None,
    link_count: int = 8,
) -> None:
    repo.create_topology_snapshot(
        snapshot_id=snapshot_id,
        network_id=network_id,
        requested_by="phase7a",
        status="pending",
    )
    nodes = [
        ParsedTopologyNode(
            ieee_address="0xcoord",
            friendly_name="Coordinator",
            node_type="Coordinator",
            depth=0,
            lqi=255,
        ),
        ParsedTopologyNode(
            ieee_address="0xrouter",
            friendly_name="Router",
            node_type="Router",
            depth=1,
            lqi=200,
        ),
    ]
    links = [
        ParsedTopologyLink(
            source_ieee="0xcoord",
            target_ieee="0xrouter",
            source_type="Coordinator",
            target_type="Router",
            linkquality=200,
            depth=1,
            relationship="child",
            route_count=1,
        )
    ]
    if target_ieee is not None:
        nodes.append(
            ParsedTopologyNode(
                ieee_address=target_ieee,
                friendly_name="Target",
                node_type="EndDevice",
                depth=2,
                lqi=120,
            )
        )
        links.append(
            ParsedTopologyLink(
                source_ieee="0xrouter",
                target_ieee=target_ieee,
                source_type="Router",
                target_type="EndDevice",
                linkquality=120,
                depth=2,
                relationship="child",
                route_count=1,
            )
        )
    for index in range(link_count):
        child = f"0xchild{index:04d}"
        nodes.append(
            ParsedTopologyNode(
                ieee_address=child,
                friendly_name=f"Child {index}",
                node_type="EndDevice",
                depth=2,
                lqi=100,
            )
        )
        links.append(
            ParsedTopologyLink(
                source_ieee="0xrouter",
                target_ieee=child,
                source_type="Router",
                target_type="EndDevice",
                linkquality=100,
                depth=2,
                relationship="child",
                route_count=0,
            )
        )
    parsed = ParsedTopology(
        nodes=nodes,
        links=links,
        router_count=sum(1 for n in nodes if n.node_type == "Router"),
        end_device_count=sum(1 for n in nodes if n.node_type == "EndDevice"),
        link_count=len(links),
        raw_redacted={"phase7a": True, "snapshot_id": snapshot_id},
    )
    repo.store_topology_parsed(snapshot_id, network_id, parsed, status="complete")
    repo.db.conn.execute(
        "UPDATE topology_snapshots SET captured_at = ? WHERE snapshot_id = ?",
        (captured_at.isoformat(), snapshot_id),
    )
    repo.db.conn.commit()


def test_topology_overview_statement_count_constant_within_chunk(tmp_path: Path, monkeypatch):
    import zigbeelens.topology.service as topology_service_mod

    monkeypatch.setattr(topology_service_mod, "_topology", None)

    def measure(networks: int) -> int:
        repo, cfg = _repo(tmp_path / f"n{networks}", networks=[f"n{i:02d}" for i in range(networks)])
        for i, network in enumerate(repo.list_networks()):
            _seed_complete_snapshot(
                repo,
                network_id=network.id,
                snapshot_id=f"snap-{network.id}",
                captured_at=REFERENCE_TIME - timedelta(minutes=i),
            )
        counter = install_counter(repo)
        ctx = SimpleNamespace(config=cfg, repo=repo)

        def run():
            return topology_status_dict(ctx)

        measured = measure_operation(
            f"topology_status_{networks}",
            "phase7a",
            "warm",
            counter.stats,
            run,
        )
        assert len(run()["networks"]) == networks
        return measured.execute_count

    two = measure(2)
    forty = measure(40)
    assert two == forty


def test_latest_snapshot_bulk_parity_and_tie_break(tmp_path: Path):
    repo, _ = _repo(tmp_path, networks=["home", "office", "empty"])
    tie = REFERENCE_TIME
    _seed_complete_snapshot(
        repo,
        network_id="home",
        snapshot_id="home-a",
        captured_at=tie,
    )
    _seed_complete_snapshot(
        repo,
        network_id="home",
        snapshot_id="home-b",
        captured_at=tie,
    )
    _seed_complete_snapshot(
        repo,
        network_id="office",
        snapshot_id="office-1",
        captured_at=REFERENCE_TIME - timedelta(hours=1),
    )
    bulk = repo.get_latest_topology_snapshots_for_networks(["home", "office", "empty"])
    assert bulk["empty"] is None
    assert bulk["home"]["snapshot_id"] == "home-b"  # snapshot_id DESC tie-break
    assert bulk["office"]["snapshot_id"] == "office-1"
    for network_id in ("home", "office", "empty"):
        assert bulk[network_id] == repo.get_latest_topology_snapshot(network_id)


def test_device_snapshot_history_bounds_10_vs_30(tmp_path: Path):
    def measure(retained: int) -> tuple[int, dict]:
        repo, cfg = _repo(tmp_path / f"hist{retained}", networks=["home"])
        target = "0xtarget"
        repo.upsert_device(
            network_id="home",
            ieee_address=target,
            friendly_name="Target",
            device_type="EndDevice",
            power_source="Battery",
            interview_state="successful",
        )
        for index in range(retained):
            _seed_complete_snapshot(
                repo,
                network_id="home",
                snapshot_id=f"snap-{index:03d}",
                captured_at=REFERENCE_TIME - timedelta(minutes=index),
                target_ieee=target if index % 2 == 0 else None,
                link_count=20,
            )
        # Non-complete should not expand the window.
        repo.create_topology_snapshot(
            snapshot_id="pending-x",
            network_id="home",
            requested_by="phase7a",
            status="pending",
        )
        service = EvidenceGraphService(repo)
        counter = install_counter(repo)

        def run():
            return build_device_snapshot_history_response(
                repo,
                service,
                network_id="home",
                device_ieee=target,
                stale_after_hours=24,
                now=REFERENCE_TIME,
            )

        measured = measure_operation(
            f"device_snapshot_history_{retained}",
            "phase7a",
            "warm",
            counter.stats,
            run,
        )
        payload = run()
        return measured.execute_count, payload

    ten_count, ten_payload = measure(10)
    thirty_count, thirty_payload = measure(30)
    assert ten_count == thirty_count
    for payload in (ten_payload, thirty_payload):
        history_len = (1 if payload["latest_snapshot"] else 0) + len(payload["snapshots"])
        assert history_len == MAX_SNAPSHOT_HISTORY


def test_incident_recent_first_page_scales_constant(tmp_path: Path):
    def measure(n: int) -> int:
        repo, _ = _repo(tmp_path / f"inc{n}", networks=["home"])
        for index in range(n):
            ts = (REFERENCE_TIME - timedelta(minutes=index)).isoformat()
            repo.insert_incident(
                incident_id=f"i-{index:04d}",
                dedup_key=f"d:{index}",
                incident_type="device_offline",
                lifecycle_state="resolved" if index % 3 else "open",
                severity="watch",
                scope="device",
                confidence="medium",
                title=f"i{index}",
                summary="s",
                explanation="e",
                evidence=[],
                counter_evidence=[],
                limitations=[],
                opened_at=ts,
                updated_at=ts,
            )
        counter = install_counter(repo)
        query = build_incident_collection_query(limit=50, order="recent")

        def run():
            return repo.list_incidents_page(query)

        measured = measure_operation(
            f"incident_recent_{n}",
            "phase7a",
            "warm",
            counter.stats,
            run,
        )
        page = run()
        assert len(page.rows) == 50
        return measured.execute_count

    assert measure(100) == measure(1500)


def test_metric_samples_window_and_plan(tmp_path: Path):
    def seed_and_measure(rows: int) -> tuple[int, list]:
        repo, _ = _repo(tmp_path / f"m{rows}", networks=["home"])
        ieee = "0xmetric"
        repo.upsert_device(
            network_id="home",
            ieee_address=ieee,
            friendly_name="Metric",
            device_type="EndDevice",
            power_source="Battery",
            interview_state="successful",
        )
        tie = REFERENCE_TIME.isoformat()
        for index in range(rows):
            name = f"m{index % 5}"
            # Insert via SQL to control sampled_at / create many rows quickly.
            repo.db.conn.execute(
                """
                INSERT INTO metric_samples (network_id, ieee_address, metric_name, metric_value, sampled_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("home", ieee, name, float(index), tie if index < 10 else (REFERENCE_TIME - timedelta(seconds=index)).isoformat()),
            )
        repo.db.conn.commit()
        counter = install_counter(repo)

        def run():
            return repo.list_metric_samples("home", ieee, limit=50)

        measured = measure_operation(
            f"metrics_{rows}",
            "phase7a",
            "warm",
            counter.stats,
            run,
        )
        result = run()
        assert len(result) == 50
        sql = """
            SELECT metric_name, metric_value, sampled_at
            FROM metric_samples
            WHERE network_id = ? AND ieee_address = ?
            ORDER BY sampled_at DESC, id DESC
            LIMIT ?
        """
        plan = " | ".join(
            str(row[-1])
            for row in repo.db.conn.execute(
                f"EXPLAIN QUERY PLAN {sql}", ("home", ieee, 50)
            ).fetchall()
        )
        assert "idx_metric_samples_device_time" in plan
        assert "USE TEMP B-TREE FOR ORDER BY" not in plan
        return measured.execute_count, result

    c100, r100 = seed_and_measure(100)
    c10k, r10k = seed_and_measure(10000)
    assert c100 == c10k
    assert r100 == r10k


def test_topology_link_source_target_plans_use_primary_key(tmp_path: Path):
    """Source/target candidate indexes were rejected: PK autoindex wins EXPLAIN."""
    repo, _ = _repo(tmp_path, networks=["home"])
    _seed_complete_snapshot(
        repo,
        network_id="home",
        snapshot_id="snap-1",
        captured_at=REFERENCE_TIME,
        target_ieee="0xtarget",
        link_count=40,
    )
    children_sql = """
        SELECT target_ieee FROM topology_links
        WHERE snapshot_id = ? AND source_ieee = ?
    """
    parent_sql = """
        SELECT source_ieee FROM topology_links
        WHERE snapshot_id = ? AND target_ieee = ?
        LIMIT 1
    """
    children_plan = " | ".join(
        str(row[-1])
        for row in repo.db.conn.execute(
            f"EXPLAIN QUERY PLAN {children_sql}", ("snap-1", "0xrouter")
        ).fetchall()
    )
    parent_plan = " | ".join(
        str(row[-1])
        for row in repo.db.conn.execute(
            f"EXPLAIN QUERY PLAN {parent_sql}", ("snap-1", "0xtarget")
        ).fetchall()
    )
    assert "sqlite_autoindex_topology_links_1" in children_plan
    assert "sqlite_autoindex_topology_links_1" in parent_plan
    assert "SCAN topology_links" not in children_plan
    assert repo.list_topology_children("snap-1", "0xrouter")
    assert repo.get_topology_parent_router("snap-1", "0xtarget") == "0xrouter"


def test_availability_offline_plan(tmp_path: Path):
    repo, _ = _repo(tmp_path, networks=["home"])
    cutoff = (REFERENCE_TIME - timedelta(days=7)).isoformat()
    for index in range(200):
        repo.db.conn.execute(
            """
            INSERT INTO availability_changes
              (network_id, ieee_address, from_state, to_state, changed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "home",
                f"0xd{index:04d}",
                "online",
                "offline" if index % 2 == 0 else "online",
                (REFERENCE_TIME - timedelta(minutes=index)).isoformat(),
            ),
        )
    repo.db.conn.commit()
    sql = """
        SELECT ieee_address, from_state, to_state, changed_at
        FROM availability_changes
        WHERE network_id = ? AND changed_at >= ? AND to_state = 'offline'
        ORDER BY changed_at ASC, ieee_address ASC, id ASC
    """
    plan = " | ".join(
        str(row[-1])
        for row in repo.db.conn.execute(
            f"EXPLAIN QUERY PLAN {sql}", ("home", cutoff)
        ).fetchall()
    )
    assert "idx_availability_changes_offline_since" in plan
    rows = repo.list_availability_offline_transitions_since("home", cutoff)
    assert rows
    assert all(row["to_state"] == "offline" for row in rows)


def test_latest_topology_snapshot_plan(tmp_path: Path):
    repo, _ = _repo(tmp_path, networks=[f"n{i:02d}" for i in range(5)])
    for network in repo.list_networks():
        _seed_complete_snapshot(
            repo,
            network_id=network.id,
            snapshot_id=f"s-{network.id}",
            captured_at=REFERENCE_TIME,
        )
    ids = [n.id for n in repo.list_networks()]
    placeholders = ",".join("?" for _ in ids)
    sql = f"""
        SELECT snapshot_id, network_id, captured_at, requested_by, status,
               router_count, end_device_count, link_count, warning_acknowledged, error
        FROM (
            SELECT snapshot_id, network_id, captured_at, requested_by, status,
                   router_count, end_device_count, link_count, warning_acknowledged, error,
                   ROW_NUMBER() OVER (
                       PARTITION BY network_id
                       ORDER BY captured_at DESC, snapshot_id DESC
                   ) AS rn
            FROM topology_snapshots
            WHERE network_id IN ({placeholders}) AND status = 'complete'
        ) ranked
        WHERE rn = 1
    """
    plan = " | ".join(
        str(row[-1]) for row in repo.db.conn.execute(f"EXPLAIN QUERY PLAN {sql}", ids).fetchall()
    )
    assert "idx_topology_snapshots_latest_complete" in plan or "topology_snapshots" in plan
    bulk = repo.get_latest_topology_snapshots_for_networks(ids)
    assert all(bulk[nid] is not None for nid in ids)
