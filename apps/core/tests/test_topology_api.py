"""Topology capture API confirmation tests."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from zigbeelens.topology.parser import parse_networkmap_payload
from zigbeelens.topology.publisher import FakeTopologyRequestPublisher


def test_topology_network_includes_inventory_and_layout_flags(topology_client: TestClient):
    ctx = topology_client.app.state.ctx
    snapshot_id = "snap-inv"
    ctx.repo.create_topology_snapshot(
        snapshot_id=snapshot_id,
        network_id="home",
        requested_by="startup_scan",
        status="complete",
        warning_acknowledged=True,
    )
    parsed = parse_networkmap_payload({"nodes": {}, "links": []})
    ctx.repo.store_topology_parsed(snapshot_id, "home", parsed, status="complete")
    ctx.repo.upsert_device(
        network_id="home",
        ieee_address="0x00124b0024abcd02",
        friendly_name="Hall Router",
        device_type="Router",
        power_source="Mains",
        manufacturer="Test",
        model="Router",
        interview_state="successful",
    )
    ctx.repo.upsert_device(
        network_id="home",
        ieee_address="0x00124b0024abcd03",
        friendly_name="Lamp",
        device_type="EndDevice",
        power_source="Battery",
        manufacturer="Test",
        model="Lamp",
        interview_state="successful",
    )

    res = topology_client.get("/api/topology/home")
    assert res.status_code == 200
    body = res.json()
    assert body["layout_available"] is False
    assert body["inventory"]["device_count"] == 2
    assert body["inventory"]["router_count"] == 1
    assert body["inventory"]["end_device_count"] == 1


def test_snapshot_compare_endpoint_is_read_only_and_calm_without_history(
    topology_client: TestClient,
):
    res = topology_client.get("/api/topology/home/snapshots/compare")
    assert res.status_code == 200
    body = res.json()
    assert body["has_comparison"] is False
    assert body["summary"] == "There is not enough snapshot history to compare yet."
    assert body["changes"] == []

    unknown = topology_client.get("/api/topology/nope/snapshots/compare")
    assert unknown.status_code == 404


def test_snapshot_compare_endpoint_compares_latest_usable_snapshots(
    topology_client: TestClient,
):
    ctx = topology_client.app.state.ctx
    for snapshot_id, captured_at, links in (
        ("snap-prev", "2026-07-08T10:00:00+00:00", []),
        (
            "snap-latest",
            "2026-07-09T10:00:00+00:00",
            [{"source": "0x02", "target": "0x01", "linkquality": 90}],
        ),
    ):
        ctx.repo.create_topology_snapshot(
            snapshot_id=snapshot_id,
            network_id="home",
            requested_by="startup_scan",
            status="pending",
            warning_acknowledged=True,
        )
        parsed = parse_networkmap_payload(
            {
                "nodes": {"0x01": {"type": "Coordinator"}, "0x02": {"type": "Router"}},
                "links": links,
            }
        )
        ctx.repo.store_topology_parsed(snapshot_id, "home", parsed, status="complete")
        ctx.repo.db.conn.execute(
            "UPDATE topology_snapshots SET captured_at = ? WHERE snapshot_id = ?",
            (captured_at, snapshot_id),
        )
        ctx.repo.db.conn.commit()

    res = topology_client.get("/api/topology/home/snapshots/compare")
    assert res.status_code == 200
    body = res.json()
    assert body["has_comparison"] is True
    assert body["compare_snapshot"]["snapshot_id"] == "snap-latest"
    assert body["base_snapshot"]["snapshot_id"] == "snap-prev"
    assert body["counts"]["new_neighbour_links"] == 1
    # Deterministic: the same request yields the same ordered changes.
    again = topology_client.get("/api/topology/home/snapshots/compare").json()
    assert [c["id"] for c in again["changes"]] == [c["id"] for c in body["changes"]]


def test_topology_capture_requires_strict_true(topology_client: TestClient):
    with patch(
        "zigbeelens.topology.service.TopologyRequestPublisher",
        FakeTopologyRequestPublisher,
    ):
        blocked_false = topology_client.post(
            "/api/topology/home/capture",
            json={"confirmed": False},
        )
        assert blocked_false.status_code == 400

        blocked_string = topology_client.post(
            "/api/topology/home/capture",
            json={"confirmed": "false"},
        )
        assert blocked_string.status_code == 422

        blocked_missing = topology_client.post("/api/topology/home/capture", json={})
        assert blocked_missing.status_code == 422

        ok = topology_client.post(
            "/api/topology/home/capture",
            json={"confirmed": True, "reason": "test"},
        )
        assert ok.status_code == 200


def test_topology_capture_disabled_returns_403(mock_client: TestClient):
    res = mock_client.post(
        "/api/topology/home/capture",
        json={"confirmed": True},
    )
    assert res.status_code == 403
