"""Topology capture API confirmation tests."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from zigbeelens.topology.publisher import FakeTopologyRequestPublisher


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
