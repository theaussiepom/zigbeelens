"""Table-driven /api versus /api/v1 parity — identity-sensitive equality."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


def _strip_generated_only(value: Any, *, allow_ids: set[str] | None = None) -> Any:
    """Normalise only newly generated IDs/timestamps — never deterministic identity."""
    allow_ids = allow_ids or set()
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"generated_at", "created_at", "updated_at", "downloaded_at"}:
                out[key] = "<generated-ts>"
            elif key == "id" and isinstance(item, str) and item in allow_ids:
                out[key] = "<generated-id>"
            else:
                out[key] = _strip_generated_only(item, allow_ids=allow_ids)
        return out
    if isinstance(value, list):
        return [_strip_generated_only(item, allow_ids=allow_ids) for item in value]
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
    "/reports/preview",
    "/storage/status",
    "/scenarios",
    "/config/status",
    "/enrichment/status",
    "/topology",
]


def test_api_and_v1_read_parity_matrix(mock_client: TestClient):
    for suffix in READ_ROUTES:
        legacy = mock_client.get(f"/api{suffix}")
        v1 = mock_client.get(f"/api/v1{suffix}")
        assert legacy.status_code == v1.status_code, suffix
        assert legacy.status_code == 200, suffix
        # Report preview redaction salt differs per call — compare semantic keys only.
        if suffix.startswith("/reports/preview"):
            left, right = legacy.json(), v1.json()
            assert left["report_version"] == right["report_version"] == 3
            assert left["scope"] == right["scope"]
            assert left["decision_summary"] == right["decision_summary"]
            assert len(left["device_stories"]) == len(right["device_stories"])
            continue
        assert legacy.json() == v1.json(), suffix


def test_api_and_v1_detail_parity(mock_client: TestClient):
    networks = mock_client.get("/api/networks").json()["items"]
    devices = mock_client.get("/api/devices").json()["items"]
    incidents = mock_client.get("/api/incidents").json()["items"]
    assert networks and devices

    network_id = networks[0]["id"]
    device = devices[0]
    routes = [
        f"/networks/{network_id}",
        f"/devices/{device['network_id']}/{device['ieee_address']}",
        f"/devices/{device['network_id']}/{device['ieee_address']}/story",
        f"/devices/{device['network_id']}/{device['ieee_address']}/coverage",
        f"/topology/{network_id}",
        f"/topology/{network_id}/evidence-graph",
        f"/topology/{network_id}/devices/{device['ieee_address']}/snapshot-history",
    ]
    if incidents:
        routes.append(f"/incidents/{incidents[0]['id']}")

    for suffix in routes:
        legacy = mock_client.get(f"/api{suffix}")
        v1 = mock_client.get(f"/api/v1{suffix}")
        assert legacy.status_code == v1.status_code, suffix
        if legacy.status_code == 200:
            assert legacy.json() == v1.json(), suffix


def test_api_and_v1_report_mutation_parity(mock_client: TestClient):
    create_legacy = mock_client.post("/api/reports", json={"scope": "full"})
    create_v1 = mock_client.post("/api/v1/reports", json={"scope": "full"})
    assert create_legacy.status_code == create_v1.status_code == 200
    legacy_id = create_legacy.json()["id"]
    v1_id = create_v1.json()["id"]

    for report_id in (legacy_id, v1_id):
        for prefix in ("/api", "/api/v1"):
            detail = mock_client.get(f"{prefix}/reports/{report_id}")
            assert detail.status_code == 200
            assert detail.json()["report_version"] == 3
            download = mock_client.get(f"{prefix}/reports/{report_id}/download")
            assert download.status_code == 200

    listed_legacy = mock_client.get("/api/reports").json()
    listed_v1 = mock_client.get("/api/v1/reports").json()
    assert {row["id"] for row in listed_legacy} == {row["id"] for row in listed_v1}

    assert mock_client.delete(f"/api/reports/{legacy_id}").status_code == 200
    assert mock_client.delete(f"/api/v1/reports/{v1_id}").status_code == 200


@pytest.mark.parametrize(
    "suffix,expected",
    [
        ("/incidents?cursor=not-a-cursor", {400, 422}),
        ("/incidents?order=recent&cursor=v1.bad", {400, 422}),
        ("/incidents?order=not-an-order", {400, 422}),
        ("/networks/does-not-exist", {404}),
        ("/devices/home/0xdeadbeef", {404}),
        ("/devices/home/0xdeadbeef/story", {404}),
        ("/incidents/does-not-exist", {404}),
        ("/reports/does-not-exist", {404}),
        ("/reports/preview?scope=not-a-scope", {400, 422}),
        ("/topology/does-not-exist", {404}),
    ],
)
def test_api_and_v1_error_parity(mock_client: TestClient, suffix: str, expected: set[int]):
    legacy = mock_client.get(f"/api{suffix}")
    v1 = mock_client.get(f"/api/v1{suffix}")
    assert legacy.status_code == v1.status_code
    assert legacy.status_code in expected


def test_api_and_v1_unknown_route_parity(mock_client: TestClient):
    legacy = mock_client.get("/api/this-route-does-not-exist")
    v1 = mock_client.get("/api/v1/this-route-does-not-exist")
    assert legacy.status_code == v1.status_code == 404
