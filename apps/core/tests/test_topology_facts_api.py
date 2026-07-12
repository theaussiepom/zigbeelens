"""API exposure tests for topology decision facts (Phase 3A-3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from zigbeelens.app.context import get_context
from zigbeelens.config.models import TopologyConfig
from zigbeelens.decisions.topology_facts import TopologyFactCode
from zigbeelens.services.topology_facts_composition import topology_stale_threshold_hours
from zigbeelens.topology.parser import parse_networkmap_payload


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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


def _enable_automatic_capture(ctx, *, enabled: bool, interval_hours: int) -> None:
    ctx.config.topology.automatic_capture_enabled = enabled
    ctx.config.topology.automatic_capture_interval_hours = interval_hours


def test_topology_stale_threshold_hours_respects_automatic_capture_enabled():
    enabled_topo = TopologyConfig(
        enabled=True,
        automatic_capture_enabled=True,
        automatic_capture_interval_hours=24,
    )
    disabled_topo = TopologyConfig(
        enabled=True,
        automatic_capture_enabled=False,
        automatic_capture_interval_hours=24,
    )

    class _Cfg:
        def __init__(self, topology: TopologyConfig) -> None:
            self.topology = topology

    assert topology_stale_threshold_hours(_Cfg(enabled_topo)) == 24
    assert topology_stale_threshold_hours(_Cfg(disabled_topo)) is None


def test_evidence_graph_api_stale_when_capture_enabled_threshold_24h(
    topology_client: TestClient,
):
    ctx = get_context()
    previous_enabled = ctx.config.topology.automatic_capture_enabled
    previous_interval = ctx.config.topology.automatic_capture_interval_hours
    try:
        _enable_automatic_capture(ctx, enabled=True, interval_hours=24)
        now = _utc_now()
        _store_snapshot(
            ctx.repo,
            "snap-stale",
            captured_at=now - timedelta(hours=30),
            links=[{"source": "0x02", "target": "0x01", "linkquality": 90}],
        )

        topology_facts = topology_client.get("/api/topology/home/evidence-graph").json()[
            "topology_facts"
        ]
        assert topology_facts["stale_threshold_hours"] == 24
        codes = {fact["code"] for fact in topology_facts["network_facts"]}
        assert TopologyFactCode.latest_snapshot_stale in codes
    finally:
        ctx.config.topology.automatic_capture_enabled = previous_enabled
        ctx.config.topology.automatic_capture_interval_hours = previous_interval


def test_evidence_graph_api_not_stale_when_capture_enabled_threshold_72h(
    topology_client: TestClient,
):
    ctx = get_context()
    previous_enabled = ctx.config.topology.automatic_capture_enabled
    previous_interval = ctx.config.topology.automatic_capture_interval_hours
    try:
        _enable_automatic_capture(ctx, enabled=True, interval_hours=72)
        now = _utc_now()
        _store_snapshot(
            ctx.repo,
            "snap-fresh",
            captured_at=now - timedelta(hours=30),
            links=[{"source": "0x02", "target": "0x01", "linkquality": 90}],
        )

        topology_facts = topology_client.get("/api/topology/home/evidence-graph").json()[
            "topology_facts"
        ]
        assert topology_facts["stale_threshold_hours"] == 72
        codes = {fact["code"] for fact in topology_facts["network_facts"]}
        assert TopologyFactCode.latest_snapshot_stale not in codes
    finally:
        ctx.config.topology.automatic_capture_enabled = previous_enabled
        ctx.config.topology.automatic_capture_interval_hours = previous_interval


def test_evidence_graph_api_capture_disabled_null_threshold_no_stale_fact(
    topology_client: TestClient,
):
    ctx = get_context()
    previous_enabled = ctx.config.topology.automatic_capture_enabled
    try:
        ctx.config.topology.automatic_capture_enabled = False
        now = _utc_now()
        _store_snapshot(
            ctx.repo,
            "snap-old",
            captured_at=now - timedelta(hours=30),
            links=[{"source": "0x02", "target": "0x01", "linkquality": 90}],
        )

        topology_facts = topology_client.get("/api/topology/home/evidence-graph").json()[
            "topology_facts"
        ]
        assert topology_facts["stale_threshold_hours"] is None
        codes = {fact["code"] for fact in topology_facts["network_facts"]}
        assert TopologyFactCode.latest_snapshot_stale not in codes
    finally:
        ctx.config.topology.automatic_capture_enabled = previous_enabled


def test_evidence_graph_api_topology_facts_shape(topology_client: TestClient):
    body = topology_client.get("/api/topology/home/evidence-graph").json()
    topology_facts = body["topology_facts"]
    assert set(topology_facts.keys()) == {"stale_threshold_hours", "network_facts"}
    assert topology_facts["stale_threshold_hours"] is None
    assert isinstance(topology_facts["network_facts"], list)


def test_device_snapshot_history_api_topology_facts_shape_and_scoped_comparisons(
    topology_client: TestClient,
):
    ctx = get_context()
    now = _utc_now()
    for snapshot_id, captured_at, links in (
        (
            "snap-old-1",
            now - timedelta(days=2),
            [{"source": "0x04", "target": "0x02", "linkquality": 80}],
        ),
        (
            "snap-old-2",
            now - timedelta(days=1),
            [{"source": "0x02", "target": "0x01", "linkquality": 85}],
        ),
        ("snap-latest", now, []),
    ):
        _store_snapshot(ctx.repo, snapshot_id, captured_at=captured_at, links=links)

    body = topology_client.get("/api/topology/home/devices/0x04/snapshot-history").json()
    topology_facts = body["topology_facts"]
    assert set(topology_facts.keys()) == {
        "stale_threshold_hours",
        "device_facts",
        "comparison_facts_by_snapshot_id",
    }
    assert topology_facts["stale_threshold_hours"] is None

    device_codes = {fact["code"] for fact in topology_facts["device_facts"]}
    assert TopologyFactCode.device_no_latest_links in device_codes
    assert TopologyFactCode.device_has_selected_snapshot_links not in device_codes
    assert TopologyFactCode.device_latest_vs_selected_changed not in device_codes

    comparison_by_id = topology_facts["comparison_facts_by_snapshot_id"]
    assert set(comparison_by_id.keys()) == {"snap-old-1", "snap-old-2"}
    assert "snap-unknown" not in comparison_by_id

    snap_old_1_codes = {fact["code"] for fact in comparison_by_id["snap-old-1"]}
    snap_old_2_codes = {fact["code"] for fact in comparison_by_id["snap-old-2"]}
    assert TopologyFactCode.device_has_selected_snapshot_links in snap_old_1_codes
    assert TopologyFactCode.device_latest_vs_selected_changed in snap_old_1_codes
    assert TopologyFactCode.device_has_selected_snapshot_links not in snap_old_2_codes
    assert TopologyFactCode.device_latest_vs_selected_changed not in snap_old_2_codes

    for fact in comparison_by_id["snap-old-1"]:
        assert fact["params"].get("snapshot_id") == "snap-old-1"
