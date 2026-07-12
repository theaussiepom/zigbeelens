"""API exposure tests for topology decision facts (Phase 3A-3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from zigbeelens.app.context import get_context
from zigbeelens.decisions.topology_facts import TopologyFactCode
from zigbeelens.topology.parser import parse_networkmap_payload

NOW = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)


def _store_snapshot(
    repo,
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


def test_evidence_graph_api_includes_network_topology_facts(topology_client: TestClient):
    ctx = get_context()
    repo = ctx.repo
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=30),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 90}],
    )

    body = topology_client.get("/api/topology/home/evidence-graph").json()
    topology_facts = body["topology_facts"]
    assert topology_facts["stale_threshold_hours"] == ctx.config.topology.automatic_capture_interval_hours
    assert isinstance(topology_facts["network_facts"], list)
    codes = {fact["code"] for fact in topology_facts["network_facts"]}
    assert TopologyFactCode.latest_snapshot_complete in codes
    assert TopologyFactCode.latest_snapshot_stale in codes


def test_evidence_graph_api_topology_facts_respect_configured_stale_threshold(
    topology_client: TestClient,
):
    ctx = get_context()
    repo = ctx.repo
    previous_threshold = ctx.config.topology.automatic_capture_interval_hours
    ctx.config.topology.automatic_capture_interval_hours = 72
    try:
        _store_snapshot(
            repo,
            "snap-fresh",
            captured_at=NOW - timedelta(hours=1),
            links=[{"source": "0x02", "target": "0x01", "linkquality": 90}],
        )

        body = topology_client.get("/api/topology/home/evidence-graph").json()
        topology_facts = body["topology_facts"]
        assert topology_facts["stale_threshold_hours"] == 72
        codes = {fact["code"] for fact in topology_facts["network_facts"]}
        assert TopologyFactCode.latest_snapshot_stale not in codes
    finally:
        ctx.config.topology.automatic_capture_interval_hours = previous_threshold


def test_device_snapshot_history_api_includes_device_topology_facts(
    topology_client: TestClient,
):
    ctx = get_context()
    repo = ctx.repo
    for snapshot_id, captured_at, links in (
        ("snap-1", NOW - timedelta(days=2), [{"source": "0x04", "target": "0x02", "linkquality": 80}]),
        ("snap-2", NOW - timedelta(days=1), [{"source": "0x04", "target": "0x02", "linkquality": 85}]),
        ("snap-3", NOW, []),
    ):
        _store_snapshot(repo, snapshot_id, captured_at=captured_at, links=links)

    body = topology_client.get("/api/topology/home/devices/0x04/snapshot-history").json()
    topology_facts = body["topology_facts"]
    assert topology_facts["stale_threshold_hours"] == ctx.config.topology.automatic_capture_interval_hours
    codes = {fact["code"] for fact in topology_facts["device_facts"]}
    assert TopologyFactCode.device_no_latest_links in codes
    assert TopologyFactCode.device_has_selected_snapshot_links in codes
