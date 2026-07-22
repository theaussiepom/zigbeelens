"""Phase 7A scaling, EXPLAIN, and bound proofs (cardinality, not wall-clock)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.services.evidence_graph import EvidenceGraphService
from zigbeelens.services.network_evidence import EVIDENCE_GRAPH_FACTS_REQUIREMENTS
from zigbeelens.services.network_evidence_composition import (
    compose_network_evidence_context,
)
from zigbeelens.services.topology_facts_composition import (
    build_device_snapshot_history_response,
    compose_device_topology_facts_payload,
)
from zigbeelens.storage.incident_collection import build_incident_collection_query
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.device_compare import MAX_SNAPSHOT_HISTORY, device_snapshot_history
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
    status: str = "complete",
) -> None:
    repo.create_topology_snapshot(
        snapshot_id=snapshot_id,
        network_id=network_id,
        requested_by="phase7a",
        status="pending",
    )
    if status != "complete":
        repo.update_topology_snapshot(snapshot_id, status=status, error="err" if status == "error" else None)
        repo.db.conn.execute(
            "UPDATE topology_snapshots SET captured_at = ? WHERE snapshot_id = ?",
            (captured_at.isoformat(), snapshot_id),
        )
        repo.db.conn.commit()
        return
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

    assert measure(2) == measure(40)


def test_latest_snapshot_1_vs_1000_retained_same_statement_count(tmp_path: Path):
    def measure(retained: int) -> tuple[int, str | None]:
        repo, _ = _repo(tmp_path / f"ret{retained}", networks=["home"])
        for index in range(retained):
            _seed_complete_snapshot(
                repo,
                network_id="home",
                snapshot_id=f"snap-{index:04d}",
                captured_at=REFERENCE_TIME - timedelta(minutes=index),
            )
        counter = install_counter(repo)

        def run():
            return repo.get_latest_topology_snapshots_for_networks(["home"])

        measured = measure_operation(
            f"latest_{retained}",
            "phase7a",
            "warm",
            counter.stats,
            run,
        )
        result = run()["home"]
        assert result is not None
        assert result["snapshot_id"] == "snap-0000"
        return measured.execute_count, result["snapshot_id"]

    c1, id1 = measure(1)
    c1000, id1000 = measure(1000)
    assert c1 == c1000
    assert id1 == id1000 == "snap-0000"


def test_latest_snapshot_bulk_parity_and_tie_break(tmp_path: Path):
    repo, _ = _repo(tmp_path, networks=["home", "office", "empty"])
    tie = REFERENCE_TIME
    _seed_complete_snapshot(repo, network_id="home", snapshot_id="home-a", captured_at=tie)
    _seed_complete_snapshot(repo, network_id="home", snapshot_id="home-b", captured_at=tie)
    _seed_complete_snapshot(
        repo,
        network_id="office",
        snapshot_id="office-1",
        captured_at=REFERENCE_TIME - timedelta(hours=1),
    )
    # Newer pending/error must not win over older complete.
    _seed_complete_snapshot(
        repo,
        network_id="office",
        snapshot_id="office-pending",
        captured_at=REFERENCE_TIME,
        status="pending",
    )
    bulk = repo.get_latest_topology_snapshots_for_networks(["home", "office", "empty"])
    assert bulk["empty"] is None
    assert bulk["home"]["snapshot_id"] == "home-b"
    assert bulk["office"]["snapshot_id"] == "office-1"
    for network_id in ("home", "office", "empty"):
        assert bulk[network_id] == repo.get_latest_topology_snapshot(network_id)


def test_latest_topology_production_explain_uses_index(tmp_path: Path):
    repo, _ = _repo(tmp_path, networks=[f"n{i:02d}" for i in range(5)])
    for network in repo.list_networks():
        _seed_complete_snapshot(
            repo,
            network_id=network.id,
            snapshot_id=f"s-{network.id}",
            captured_at=REFERENCE_TIME,
        )
    ids = [n.id for n in repo.list_networks()]
    sql, params = repo._latest_topology_snapshots_for_networks_sql(ids)
    assert "ROW_NUMBER" not in sql
    plan = " | ".join(
        str(row[-1]) for row in repo.db.conn.execute(f"EXPLAIN QUERY PLAN {sql}", params)
    )
    assert "idx_topology_snapshots_latest_complete" in plan
    assert "USE TEMP B-TREE FOR ORDER BY" not in plan
    assert "SCAN topology_snapshots" not in plan


def test_device_snapshot_history_bounds_10_30_300(tmp_path: Path):
    def measure(retained: int, *, unrelated_links: int = 20) -> tuple[int, int, set[str], dict]:
        repo, cfg = _repo(tmp_path / f"hist{retained}_{unrelated_links}", networks=["home"])
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
                link_count=unrelated_links,
            )
        service = EvidenceGraphService(repo)
        counter = install_counter(repo)
        link_statements: list[str] = []

        original = repo.list_topology_links_for_device_in_snapshots

        def spy(snapshot_ids, ieee_address):
            result = original(snapshot_ids, ieee_address)
            link_statements.append(
                f"ids={len(list(snapshot_ids))} rows={sum(len(v) for v in result.values())}"
            )
            return result

        repo.list_topology_links_for_device_in_snapshots = spy  # type: ignore[method-assign]

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
        history_len = (1 if payload["latest_snapshot"] else 0) + len(payload["snapshots"])
        snap_ids = set()
        if payload["latest_snapshot"]:
            snap_ids.add(payload["latest_snapshot"]["snapshot_id"])
        snap_ids.update(row["snapshot_id"] for row in payload["snapshots"])
        # Must not call all-history bulk snapshot loader for this endpoint.
        statements = " | ".join(counter.stats.statement_counts)
        assert "list_topology_snapshots_for_networks" not in statements
        assert "FROM topology_snapshots WHERE network_id IN" not in (
            " ".join(counter.stats.statements)
        ) or "status = ?" in " ".join(counter.stats.statements)
        all_history = any(
            "FROM topology_snapshots WHERE network_id IN" in s
            and "status" not in s.lower()
            for s in counter.stats.statements
        )
        assert not all_history
        return measured.execute_count, history_len, snap_ids, payload

    c10, len10, ids10, p10 = measure(10)
    c30, len30, ids30, p30 = measure(30)
    c300, len300, ids300, p300 = measure(300)
    assert len10 == len30 == len300 == MAX_SNAPSHOT_HISTORY
    assert ids10 == ids30 == ids300
    assert c10 == c30 == c300
    # Dense unrelated links must not change coded history length.
    _, len_dense, _, p_dense = measure(30, unrelated_links=200)
    assert len_dense == MAX_SNAPSHOT_HISTORY
    assert p_dense["topology_facts"]["device_facts"]
    assert set(p10["topology_facts"].keys()) == set(p_dense["topology_facts"].keys())


def test_device_snapshot_history_response_parity_fixture(tmp_path: Path):
    """Bounded endpoint matches prior response shape on a small compatibility estate."""
    repo, _ = _repo(tmp_path, networks=["home"])
    target = "0xtarget"
    repo.upsert_device(
        network_id="home",
        ieee_address=target,
        friendly_name="Target",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )
    for index in range(5):
        _seed_complete_snapshot(
            repo,
            network_id="home",
            snapshot_id=f"snap-{index:02d}",
            captured_at=REFERENCE_TIME - timedelta(hours=index),
            target_ieee=target if index != 1 else None,
            link_count=4,
        )
    service = EvidenceGraphService(repo)
    payload = build_device_snapshot_history_response(
        repo,
        service,
        network_id="home",
        device_ieee=target,
        stale_after_hours=24,
        now=REFERENCE_TIME,
    )
    assert payload["latest_snapshot"] is not None
    assert payload["latest_snapshot"]["snapshot_id"] == "snap-00"
    assert "topology_facts" in payload
    assert "device_facts" in payload["topology_facts"]
    assert "comparison_facts_by_snapshot_id" in payload["topology_facts"]
    assert set(payload["topology_facts"]["comparison_facts_by_snapshot_id"]) == {
        row["snapshot_id"] for row in payload["snapshots"]
    }


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
        assert len(run().rows) == 50
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
            repo.db.conn.execute(
                """
                INSERT INTO metric_samples (network_id, ieee_address, metric_name, metric_value, sampled_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "home",
                    ieee,
                    name,
                    float(index),
                    tie
                    if index < 10
                    else (REFERENCE_TIME - timedelta(seconds=index)).isoformat(),
                ),
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


def test_topology_link_single_snapshot_source_still_uses_primary_key(tmp_path: Path):
    """Single-snapshot source lookup remains on PK; no speculative source index."""
    repo, _ = _repo(tmp_path, networks=["home"])
    _seed_complete_snapshot(
        repo,
        network_id="home",
        snapshot_id="snap-1",
        captured_at=REFERENCE_TIME,
        target_ieee="0xtarget",
        link_count=200,
    )
    children_sql = """
        SELECT target_ieee FROM topology_links
        WHERE snapshot_id = ? AND source_ieee = ?
    """
    children_plan = " | ".join(
        str(row[-1])
        for row in repo.db.conn.execute(
            f"EXPLAIN QUERY PLAN {children_sql}", ("snap-1", "0xrouter")
        ).fetchall()
    )
    assert "sqlite_autoindex_topology_links_1" in children_plan
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


def test_recent_incident_production_explain(tmp_path: Path):
    repo, _ = _repo(tmp_path, networks=["home"])
    for index in range(200):
        ts = (REFERENCE_TIME - timedelta(minutes=index)).isoformat()
        repo.insert_incident(
            incident_id=f"i-{index:04d}",
            dedup_key=f"d:{index}",
            incident_type="device_offline",
            lifecycle_state="open",
            severity="watch",
            scope="device",
            confidence="medium",
            title="t",
            summary="s",
            explanation="e",
            evidence=[],
            counter_evidence=[],
            limitations=[],
            opened_at=ts,
            updated_at=ts,
        )
    first = repo.list_incidents_page(
        build_incident_collection_query(limit=50, order="recent")
    )
    assert first.next_cursor
    plans = {
        "first": repo._incident_collection_page_sql(
            build_incident_collection_query(limit=50, order="recent"),
            include_cursor=False,
        ),
        "cursor": repo._incident_collection_page_sql(
            build_incident_collection_query(
                limit=50, order="recent", cursor=first.next_cursor
            ),
            include_cursor=True,
        ),
        "updated_after": repo._incident_collection_page_sql(
            build_incident_collection_query(
                updated_after=(REFERENCE_TIME - timedelta(hours=2)).isoformat(),
                limit=50,
                order="recent",
            ),
            include_cursor=False,
        ),
    }
    for name, (sql, params) in plans.items():
        plan = " | ".join(
            str(row[-1])
            for row in repo.db.conn.execute(f"EXPLAIN QUERY PLAN {sql}", params)
        )
        assert "idx_incidents_recent_order" in plan, (name, plan)
        assert "USE TEMP B-TREE FOR ORDER BY" not in plan, (name, plan)


def _reference_device_snapshot_history_response(
    repo: Repository,
    service: EvidenceGraphService,
    *,
    network_id: str,
    device_ieee: str,
    stale_after_hours: int | None,
    now: datetime,
) -> dict[str, Any]:
    """Test-only pre-bounded production path (broad NetworkEvidenceContext)."""
    context = compose_network_evidence_context(
        repo,
        network_id,
        reference_now=now,
        requirements=EVIDENCE_GRAPH_FACTS_REQUIREMENTS,
        stale_after_hours=stale_after_hours,
    )
    history = device_snapshot_history(
        repo,
        network_id,
        device_ieee,
        network_context=context.snapshot_history_context,
    )
    graph = service.build(network_id, now=now, context=context)
    return {
        **history,
        "topology_facts": compose_device_topology_facts_payload(
            service,
            network_id=network_id,
            device_ieee=device_ieee,
            device_snapshot_history_payload=history,
            stale_after_hours=stale_after_hours,
            now=now,
            evidence_graph=graph,
            network_evidence_context=context,
        ),
    }


def _json_canon(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def _seed_extra_unrelated_links(
    repo: Repository, snapshot_id: str, *, count: int, prefix: str
) -> None:
    for index in range(count):
        repo.db.conn.execute(
            """
            INSERT INTO topology_links (
                snapshot_id, network_id, source_ieee, target_ieee,
                source_type, target_type, linkquality, depth, relationship, route_count
            ) VALUES (?, 'home', ?, ?, 'Router', 'EndDevice', 40, 2, 'child', 0)
            """,
            (snapshot_id, f"0x{prefix}s{index:05d}", f"0x{prefix}t{index:05d}"),
        )
    repo.db.conn.commit()


def test_device_snapshot_history_no_complete_inventory_1_vs_1000(tmp_path: Path):
    """Exact endpoint must not list the network device inventory."""

    def run_case(unrelated: int) -> tuple[dict[str, Any], dict[str, int]]:
        repo, _ = _repo(tmp_path / f"inv{unrelated}", networks=["home"])
        target = "0xtarget"
        repo.upsert_device(
            network_id="home",
            ieee_address=target,
            friendly_name="Target",
            device_type="EndDevice",
            power_source="Battery",
            interview_state="successful",
        )
        # Shared tracking signal so 0-vs-1000 unrelated estates compare equal.
        repo.db.conn.execute(
            """
            INSERT INTO availability_changes
              (network_id, ieee_address, from_state, to_state, changed_at)
            VALUES ('home', ?, 'online', 'offline', ?)
            """,
            (target, (REFERENCE_TIME - timedelta(days=1)).isoformat()),
        )
        repo.db.conn.commit()
        repo.update_device_current_state(
            network_id="home", ieee_address=target, availability="unknown"
        )
        for index in range(unrelated):
            ieee = f"0xu{index:04d}"
            repo.upsert_device(
                network_id="home",
                ieee_address=ieee,
                friendly_name=f"U{index}",
                device_type="EndDevice",
                power_source="Battery",
                interview_state="successful",
            )
            repo.update_device_current_state(
                network_id="home", ieee_address=ieee, availability="online"
            )
        for index in range(MAX_SNAPSHOT_HISTORY + 5):
            _seed_complete_snapshot(
                repo,
                network_id="home",
                snapshot_id=f"snap-{index:02d}",
                captured_at=REFERENCE_TIME - timedelta(minutes=index),
                target_ieee=target if index % 2 == 0 else None,
                link_count=8,
            )
        service = EvidenceGraphService(repo)
        cards: dict[str, int] = {
            "snapshot_rows": 0,
            "selected_ids": 0,
            "target_link_rows": 0,
            "target_node_rows": 0,
            "target_device_rows": 0,
            "availability_existence_rows": 0,
        }

        original_list_devices = Repository.list_devices
        original_list_for_networks = Repository.list_devices_for_networks
        original_get_device = Repository.get_device
        original_complete = Repository.list_complete_topology_snapshots
        original_links = Repository.list_topology_links_for_device_in_snapshots
        original_node = Repository.get_topology_node
        original_exists = Repository.network_has_explicit_availability_state

        def fail_list_devices(self, network_id=None):
            raise AssertionError("list_devices must not be called")

        def fail_list_for_networks(self, network_ids):
            raise AssertionError("list_devices_for_networks must not be called")

        def spy_get_device(self, network_id, ieee_address):
            row = original_get_device(self, network_id, ieee_address)
            cards["target_device_rows"] += 1 if row is not None else 0
            return row

        def spy_complete(self, network_id, *, limit=None, **kwargs):
            rows = original_complete(self, network_id, limit=limit, **kwargs)
            cards["snapshot_rows"] = len(rows)
            cards["selected_ids"] = len(rows)
            return rows

        def spy_links(self, snapshot_ids, ieee_address):
            result = original_links(self, snapshot_ids, ieee_address)
            cards["target_link_rows"] = sum(len(v) for v in result.values())
            return result

        def spy_node(self, snapshot_id, ieee_address):
            row = original_node(self, snapshot_id, ieee_address)
            cards["target_node_rows"] += 1 if row is not None else 0
            return row

        def spy_exists(self, network_id):
            hit = original_exists(self, network_id)
            cards["availability_existence_rows"] = 1 if hit else 0
            return hit

        Repository.list_devices = fail_list_devices  # type: ignore[method-assign]
        Repository.list_devices_for_networks = fail_list_for_networks  # type: ignore[method-assign]
        Repository.get_device = spy_get_device  # type: ignore[method-assign]
        Repository.list_complete_topology_snapshots = spy_complete  # type: ignore[method-assign]
        Repository.list_topology_links_for_device_in_snapshots = spy_links  # type: ignore[method-assign]
        Repository.get_topology_node = spy_node  # type: ignore[method-assign]
        Repository.network_has_explicit_availability_state = spy_exists  # type: ignore[method-assign]
        try:
            payload = build_device_snapshot_history_response(
                repo,
                service,
                network_id="home",
                device_ieee=target,
                stale_after_hours=24,
                now=REFERENCE_TIME,
            )
        finally:
            Repository.list_devices = original_list_devices  # type: ignore[method-assign]
            Repository.list_devices_for_networks = original_list_for_networks  # type: ignore[method-assign]
            Repository.get_device = original_get_device  # type: ignore[method-assign]
            Repository.list_complete_topology_snapshots = original_complete  # type: ignore[method-assign]
            Repository.list_topology_links_for_device_in_snapshots = original_links  # type: ignore[method-assign]
            Repository.get_topology_node = original_node  # type: ignore[method-assign]
            Repository.network_has_explicit_availability_state = original_exists  # type: ignore[method-assign]
        return payload, cards

    p0, c0 = run_case(0)
    p1000, c1000 = run_case(1000)
    assert _json_canon(p0) == _json_canon(p1000)
    assert c0["snapshot_rows"] == c1000["snapshot_rows"] == MAX_SNAPSHOT_HISTORY
    assert c0["selected_ids"] == c1000["selected_ids"] == MAX_SNAPSHOT_HISTORY
    assert c0["target_link_rows"] == c1000["target_link_rows"]
    assert c0["target_node_rows"] == c1000["target_node_rows"] <= 1
    assert c0["target_device_rows"] == c1000["target_device_rows"] == 1
    # Transition present → existence probe skipped (0 rows).
    assert c0["availability_existence_rows"] == c1000["availability_existence_rows"] == 0
    assert p0["availability_tracking"]["enabled"] is True


@pytest.mark.parametrize(
    ("has_transition", "target_state", "unrelated_state", "expect_tracking", "expect_issue"),
    [
        (True, "unknown", None, True, False),
        (False, "unknown", "online", True, False),
        (False, "unknown", "unknown", False, False),
        (False, "offline", None, True, True),
    ],
)
def test_device_snapshot_history_availability_tracking_matrix(
    tmp_path: Path,
    has_transition: bool,
    target_state: str,
    unrelated_state: str | None,
    expect_tracking: bool,
    expect_issue: bool,
):
    repo, _ = _repo(tmp_path, networks=["home"])
    target = "0xtarget"
    repo.upsert_device(
        network_id="home",
        ieee_address=target,
        friendly_name="Target",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )
    repo.update_device_current_state(
        network_id="home", ieee_address=target, availability=target_state
    )
    if unrelated_state is not None:
        repo.upsert_device(
            network_id="home",
            ieee_address="0xother",
            friendly_name="Other",
            device_type="EndDevice",
            power_source="Battery",
            interview_state="successful",
        )
        repo.update_device_current_state(
            network_id="home", ieee_address="0xother", availability=unrelated_state
        )
    if has_transition:
        repo.insert_availability_change("home", target, "online", "offline")
    _seed_complete_snapshot(
        repo,
        network_id="home",
        snapshot_id="snap-0",
        captured_at=REFERENCE_TIME,
        target_ieee=target,
        link_count=2,
    )
    payload = build_device_snapshot_history_response(
        repo,
        EvidenceGraphService(repo),
        network_id="home",
        device_ieee=target,
        stale_after_hours=24,
        now=REFERENCE_TIME,
    )
    assert payload["availability_tracking"]["enabled"] is expect_tracking
    assert payload["has_current_issue"] is expect_issue


def test_device_snapshot_history_missing_target_semantics(tmp_path: Path):
    repo, _ = _repo(tmp_path, networks=["home"])
    _seed_complete_snapshot(
        repo,
        network_id="home",
        snapshot_id="snap-0",
        captured_at=REFERENCE_TIME,
        link_count=2,
    )
    payload = build_device_snapshot_history_response(
        repo,
        EvidenceGraphService(repo),
        network_id="home",
        device_ieee="0xmissing",
        stale_after_hours=24,
        now=REFERENCE_TIME,
    )
    assert payload["friendly_name"] is None
    assert payload["has_current_issue"] is False
    assert payload["latest_snapshot"] is not None


def test_target_device_link_query_sparse_vs_dense_and_explain(tmp_path: Path):
    repo, _ = _repo(tmp_path, networks=["home"])
    target = "0xtarget"
    repo.upsert_device(
        network_id="home",
        ieee_address=target,
        friendly_name="Target",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )
    selected: list[str] = []
    for index in range(MAX_SNAPSHOT_HISTORY):
        sid = f"snap-{index:02d}"
        selected.append(sid)
        # Alternate source / target / absent.
        role = index % 3
        target_ieee = target if role != 2 else None
        _seed_complete_snapshot(
            repo,
            network_id="home",
            snapshot_id=sid,
            captured_at=REFERENCE_TIME - timedelta(minutes=index),
            target_ieee=target_ieee,
            link_count=20,
        )
        if role == 0 and target_ieee:
            # Make target a source in this snapshot.
            repo.db.conn.execute(
                """
                INSERT INTO topology_links (
                    snapshot_id, network_id, source_ieee, target_ieee,
                    source_type, target_type, linkquality, depth, relationship, route_count
                ) VALUES (?, 'home', ?, '0xpeer', 'EndDevice', 'Router', 90, 2, 'child', 1)
                """,
                (sid, target),
            )
            repo.db.conn.commit()
    sparse = repo.list_topology_links_for_device_in_snapshots(selected, target)
    for sid in selected:
        _seed_extra_unrelated_links(repo, sid, count=2000, prefix=f"d{sid[-2:]}")
    dense = repo.list_topology_links_for_device_in_snapshots(selected, target)
    assert set(sparse) == set(dense) == set(selected)
    assert {k: len(v) for k, v in sparse.items()} == {k: len(v) for k, v in dense.items()}
    assert sum(len(v) for v in dense.values()) == sum(len(v) for v in sparse.values())
    for sid, rows in dense.items():
        for link in rows:
            assert target in {link["source_ieee"], link["target_ieee"]}
    assert len(selected) == MAX_SNAPSHOT_HISTORY

    sql, params = repo._topology_links_for_device_in_snapshots_sql(selected, target)
    plan = " | ".join(
        str(row[-1]) for row in repo.db.conn.execute(f"EXPLAIN QUERY PLAN {sql}", params)
    )
    assert "UNION" in sql
    assert "SCAN topology_links" not in plan
    assert "USE TEMP B-TREE FOR ORDER BY" not in plan
    assert "idx_topology_links_snapshot_target" in plan
    assert "sqlite_autoindex_topology_links_1" in plan


@pytest.mark.parametrize(
    "case",
    [
        "empty",
        "latest_only",
        "multiple",
        "absent_latest",
        "source_and_target",
        "tracking_unrelated",
        "tracking_off",
        "target_offline",
        "dense_devices",
        "dense_links",
        "stale_null",
    ],
)
def test_device_snapshot_history_deep_parity_matrix(tmp_path: Path, case: str):
    repo, _ = _repo(tmp_path / case, networks=["home"])
    target = "0xtarget"
    if case != "empty":
        repo.upsert_device(
            network_id="home",
            ieee_address=target,
            friendly_name="Target",
            device_type="EndDevice",
            power_source="Battery",
            interview_state="successful",
        )
    stale = None if case == "stale_null" else 24
    if case == "tracking_off":
        repo.update_device_current_state(
            network_id="home", ieee_address=target, availability="unknown"
        )
    elif case == "target_offline":
        repo.update_device_current_state(
            network_id="home", ieee_address=target, availability="offline"
        )
    elif case == "tracking_unrelated":
        repo.update_device_current_state(
            network_id="home", ieee_address=target, availability="unknown"
        )
        repo.upsert_device(
            network_id="home",
            ieee_address="0xother",
            friendly_name="Other",
            device_type="EndDevice",
            power_source="Battery",
            interview_state="successful",
        )
        repo.update_device_current_state(
            network_id="home", ieee_address="0xother", availability="online"
        )
    elif case != "empty":
        repo.insert_availability_change("home", target, "online", "offline")
        repo.update_device_current_state(
            network_id="home", ieee_address=target, availability="online"
        )

    if case == "dense_devices":
        for index in range(100):
            ieee = f"0xd{index:04d}"
            repo.upsert_device(
                network_id="home",
                ieee_address=ieee,
                friendly_name=f"D{index}",
                device_type="EndDevice",
                power_source="Battery",
                interview_state="successful",
            )
            repo.update_device_current_state(
                network_id="home", ieee_address=ieee, availability="online"
            )

    snapshot_count = {
        "empty": 0,
        "latest_only": 1,
        "absent_latest": 3,
        "multiple": 4,
        "source_and_target": 4,
        "tracking_unrelated": 2,
        "tracking_off": 2,
        "target_offline": 2,
        "dense_devices": 3,
        "dense_links": 3,
        "stale_null": 2,
    }[case]
    for index in range(snapshot_count):
        present = True
        if case == "absent_latest" and index == 0:
            present = False
        _seed_complete_snapshot(
            repo,
            network_id="home",
            snapshot_id=f"snap-{index:02d}",
            captured_at=REFERENCE_TIME - timedelta(hours=index),
            target_ieee=target if present and case != "empty" else None,
            link_count=4,
        )
        if case == "source_and_target" and present:
            repo.db.conn.execute(
                """
                INSERT INTO topology_links (
                    snapshot_id, network_id, source_ieee, target_ieee,
                    source_type, target_type, linkquality, depth, relationship, route_count
                ) VALUES (?, 'home', ?, '0xpeer', 'EndDevice', 'Router', 88, 2, 'child', 2)
                """,
                (f"snap-{index:02d}", target),
            )
            repo.db.conn.commit()
        if case == "dense_links":
            _seed_extra_unrelated_links(
                repo, f"snap-{index:02d}", count=500, prefix=f"p{index}"
            )

    service = EvidenceGraphService(repo)
    bounded = build_device_snapshot_history_response(
        repo,
        service,
        network_id="home",
        device_ieee=target,
        stale_after_hours=stale,
        now=REFERENCE_TIME,
    )
    reference = _reference_device_snapshot_history_response(
        repo,
        service,
        network_id="home",
        device_ieee=target,
        stale_after_hours=stale,
        now=REFERENCE_TIME,
    )
    assert _json_canon(bounded) == _json_canon(reference)
    assert set(bounded) == set(reference)
    assert bounded["topology_facts"] == reference["topology_facts"]
