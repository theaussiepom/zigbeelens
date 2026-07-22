"""Table-driven /api versus /api/v1 parity for current decision/report surfaces."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


def _strip_dynamics(value: Any) -> Any:
    """Normalise deliberate dynamic IDs/timestamps/redacted tokens for comparison."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in {
                "id",
                "generated_at",
                "created_at",
                "updated_at",
                "captured_at",
                "downloaded_at",
                "cursor",
                "next_cursor",
                "prev_cursor",
                "markdown",
                "ieee_address",
                "subject_id",
                "friendly_name",
                "device_ieees",
            }:
                out[key] = "<dynamic>"
            else:
                out[key] = _strip_dynamics(item)
        return out
    if isinstance(value, list):
        return [_strip_dynamics(item) for item in value]
    return value


READ_ROUTES = [
    "/version",
    "/capabilities",
    "/dashboard",
    "/networks",
    "/devices",
    "/incidents",
    "/incidents?order=lifecycle",
    "/incidents?order=recent",
    "/reports",
    "/storage/status",
    "/scenarios",
    "/config/status",
    "/enrichment/status",
]


def test_api_and_v1_read_parity_matrix(mock_client: TestClient):
    for suffix in READ_ROUTES:
        legacy = mock_client.get(f"/api{suffix}")
        v1 = mock_client.get(f"/api/v1{suffix}")
        assert legacy.status_code == v1.status_code, suffix
        assert legacy.status_code == 200, suffix
        assert _strip_dynamics(legacy.json()) == _strip_dynamics(v1.json()), suffix


def test_api_and_v1_report_preview_parity(mock_client: TestClient):
    """Preview bodies differ by redaction salt; compare semantic structure."""
    legacy = mock_client.get("/api/reports/preview")
    v1 = mock_client.get("/api/v1/reports/preview")
    assert legacy.status_code == v1.status_code == 200
    left = _strip_dynamics(legacy.json())
    right = _strip_dynamics(v1.json())
    for key in (
        "report_version",
        "scope",
        "product",
        "decision_summary",
        "redaction",
    ):
        assert left[key] == right[key], key
    assert left["report_version"] == 3
    assert len(left["device_stories"]) == len(right["device_stories"])
    for a, b in zip(left["device_stories"], right["device_stories"], strict=True):
        assert a["status"] == b["status"]
        assert a["priority"] == b["priority"]
        assert a["headline_code"] == b["headline_code"]
        assert a["reasons"] == b["reasons"]
        assert a["limitations"] == b["limitations"]
        assert a["suggested_checks"] == b["suggested_checks"]


def test_api_and_v1_device_story_parity(mock_client: TestClient):
    devices = mock_client.get("/api/devices").json()["items"]
    assert devices
    sample = devices[0]
    path = f"/devices/{sample['network_id']}/{sample['ieee_address']}/story"
    coverage = f"/devices/{sample['network_id']}/{sample['ieee_address']}/coverage"
    for suffix in (path, coverage):
        legacy = mock_client.get(f"/api{suffix}")
        v1 = mock_client.get(f"/api/v1{suffix}")
        assert legacy.status_code == v1.status_code, suffix
        if legacy.status_code == 200:
            assert _strip_dynamics(legacy.json()) == _strip_dynamics(v1.json()), suffix


def test_api_and_v1_topology_parity(mock_client: TestClient):
    networks = mock_client.get("/api/networks").json()["items"]
    assert networks
    network_id = networks[0]["id"]
    routes = [
        "/topology",
        f"/topology/{network_id}",
        f"/topology/{network_id}/evidence-graph",
    ]
    for suffix in routes:
        legacy = mock_client.get(f"/api{suffix}")
        v1 = mock_client.get(f"/api/v1{suffix}")
        assert legacy.status_code == v1.status_code, suffix
        if legacy.status_code == 200:
            assert _strip_dynamics(legacy.json()) == _strip_dynamics(v1.json()), suffix


def test_api_and_v1_report_mutation_parity(mock_client: TestClient):
    create_legacy = mock_client.post("/api/reports", json={})
    create_v1 = mock_client.post("/api/v1/reports", json={})
    assert create_legacy.status_code == create_v1.status_code
    assert create_legacy.status_code in {200, 201}
    legacy_body = create_legacy.json()
    v1_body = create_v1.json()
    assert legacy_body["scope"] == v1_body["scope"]
    assert legacy_body["id"] and v1_body["id"]

    for report_id in (legacy_body["id"], v1_body["id"]):
        for prefix in ("/api", "/api/v1"):
            detail = mock_client.get(f"{prefix}/reports/{report_id}")
            assert detail.status_code == 200
            assert detail.json()["report_version"] == 3
            download = mock_client.get(f"{prefix}/reports/{report_id}/download")
            assert download.status_code == 200

    del_legacy = mock_client.delete(f"/api/reports/{legacy_body['id']}")
    del_v1 = mock_client.delete(f"/api/v1/reports/{v1_body['id']}")
    assert del_legacy.status_code == del_v1.status_code


@pytest.mark.parametrize(
    "suffix,expected",
    [
        ("/incidents?cursor=not-a-cursor", {400, 422}),
        ("/networks/does-not-exist", {404}),
        ("/devices/home/0xdeadbeef/story", {404}),
        ("/reports/does-not-exist", {404}),
    ],
)
def test_api_and_v1_error_parity(
    mock_client: TestClient,
    suffix: str,
    expected: set[int],
):
    legacy = mock_client.get(f"/api{suffix}")
    v1 = mock_client.get(f"/api/v1{suffix}")
    assert legacy.status_code == v1.status_code
    assert legacy.status_code in expected


def test_api_and_v1_unknown_route_parity(mock_client: TestClient):
    legacy = mock_client.get("/api/this-route-does-not-exist")
    v1 = mock_client.get("/api/v1/this-route-does-not-exist")
    assert legacy.status_code == v1.status_code == 404
