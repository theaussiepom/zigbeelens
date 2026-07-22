"""Table-driven /api versus /api/v1 parity — identity-sensitive equality."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from zigbeelens.schemas import ReportDetailV3
from zigbeelens.services import report_redaction as report_redaction_mod
from zigbeelens.services import reports as reports_mod

_FIXED_SALT = "zigbeelens-api-prefix-parity-v1"
NOW = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)

MEDIA_TYPES = {
    "json": "application/json",
    "yaml": "application/x-yaml",
    "markdown": "text/markdown",
}


def _normalize_root_report_fields(body: dict[str, Any]) -> dict[str, Any]:
    """Normalize only independently generated root report fields."""
    out = dict(body)
    if "id" in out:
        out["id"] = "<generated-id>"
    if "generated_at" in out:
        out["generated_at"] = "<generated-ts>"
    md = out.get("markdown_summary")
    if isinstance(md, str) and "Generated:" in md:
        lines = []
        for line in md.splitlines():
            if line.startswith("Generated:"):
                lines.append("Generated: <generated-ts>")
            else:
                lines.append(line)
        out["markdown_summary"] = "\n".join(lines)
    return out


def _normalize_creation_summary(body: dict[str, Any]) -> dict[str, Any]:
    out = dict(body)
    if "id" in out:
        out["id"] = "<generated-id>"
    if "generated_at" in out:
        out["generated_at"] = "<generated-ts>"
    return out


def _normalize_markdown_bytes(raw: bytes) -> str:
    text = raw.decode("utf-8")
    lines = []
    for line in text.splitlines():
        if line.startswith("Generated:"):
            lines.append("Generated: <generated-ts>")
        else:
            lines.append(line)
    return "\n".join(lines)


@pytest.fixture
def parity_client(mock_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    original = report_redaction_mod.Redactor

    class _DeterministicRedactor(original):  # type: ignore[misc,valid-type]
        def __init__(self, resolved, salt: str = _FIXED_SALT) -> None:
            super().__init__(resolved, salt=salt)

    monkeypatch.setattr(report_redaction_mod, "Redactor", _DeterministicRedactor)
    monkeypatch.setattr(reports_mod, "Redactor", _DeterministicRedactor)

    ctx = mock_client.app.state.ctx
    ctx.repo.upsert_device(
        network_id="home",
        ieee_address="0x00158d0001a1b2c3",
        friendly_name="living_room_motion",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )
    ctx.repo.update_device_current_state(
        network_id="home",
        ieee_address="0x00158d0001a1b2c3",
        availability="online",
        last_seen=NOW.isoformat(),
        last_payload_at=NOW.isoformat(),
    )
    return mock_client


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
    "/topology",
]


def test_api_and_v1_read_parity_matrix(parity_client: TestClient):
    for suffix in READ_ROUTES:
        legacy = parity_client.get(f"/api{suffix}")
        v1 = parity_client.get(f"/api/v1{suffix}")
        assert legacy.status_code == v1.status_code == 200, suffix
        assert legacy.json() == v1.json(), suffix


def test_api_and_v1_report_preview_full_body_parity(parity_client: TestClient):
    legacy = parity_client.get(
        "/api/reports/preview",
        params={"scope": "full", "hash_ieee_addresses": "false"},
    )
    v1 = parity_client.get(
        "/api/v1/reports/preview",
        params={"scope": "full", "hash_ieee_addresses": "false"},
    )
    assert legacy.status_code == v1.status_code == 200
    left = _normalize_root_report_fields(legacy.json())
    right = _normalize_root_report_fields(v1.json())
    assert left["report_version"] == right["report_version"] == 3
    assert left == right


def test_api_and_v1_detail_parity_requires_success(parity_client: TestClient):
    networks = parity_client.get("/api/networks").json()["items"]
    devices = parity_client.get("/api/devices").json()["items"]
    incidents = parity_client.get("/api/incidents").json()["items"]
    assert networks and devices

    network_id = "home"
    device = next(d for d in devices if d["network_id"] == "home")
    routes = [
        f"/networks/{network_id}",
        f"/devices/{device['network_id']}/{device['ieee_address']}",
        f"/devices/{device['network_id']}/{device['ieee_address']}/story",
        "/devices/home/0x00158d0001a1b2c3/coverage",
        f"/topology/{network_id}",
        f"/topology/{network_id}/evidence-graph",
        f"/topology/{network_id}/devices/{device['ieee_address']}/snapshot-history",
    ]
    assert incidents, "expected mock incidents for success parity"
    routes.append(f"/incidents/{incidents[0]['id']}")

    for suffix in routes:
        legacy = parity_client.get(f"/api{suffix}")
        v1 = parity_client.get(f"/api/v1{suffix}")
        assert legacy.status_code == v1.status_code == 200, suffix
        assert legacy.json() == v1.json(), suffix


def _normalized_download_payload(fmt: str, content: bytes) -> Any:
    if fmt == "json":
        return _normalize_root_report_fields(json.loads(content))
    if fmt == "yaml":
        return _normalize_root_report_fields(yaml.safe_load(content))
    return _normalize_markdown_bytes(content)


@pytest.mark.parametrize("fmt", ["json", "yaml", "markdown"])
def test_api_and_v1_same_request_report_mutation_parity(
    parity_client: TestClient, fmt: str
):
    request = {
        "scope": "full",
        "format": fmt,
        "redaction": {"profile": "standard", "hash_ieee_addresses": False},
    }
    create_legacy = parity_client.post("/api/reports", json=request)
    create_v1 = parity_client.post("/api/v1/reports", json=request)
    assert create_legacy.status_code == create_v1.status_code == 200
    assert _normalize_creation_summary(create_legacy.json()) == _normalize_creation_summary(
        create_v1.json()
    )
    legacy_id = create_legacy.json()["id"]
    v1_id = create_v1.json()["id"]

    # Canonical normalized bodies/downloads for the independently created reports.
    created_bodies: dict[str, dict[str, Any]] = {}
    created_downloads: dict[str, Any] = {}

    for label, report_id in (("api", legacy_id), ("api_v1", v1_id)):
        details: list[dict[str, Any]] = []
        downloads = []
        for prefix in ("/api", "/api/v1"):
            detail = parity_client.get(f"{prefix}/reports/{report_id}")
            assert detail.status_code == 200
            body = detail.json()
            assert type(body["report_version"]) is int
            assert body["report_version"] == 3
            assert body["format"] == fmt
            ReportDetailV3.model_validate(body)
            details.append(_normalize_root_report_fields(body))

            download = parity_client.get(f"{prefix}/reports/{report_id}/download")
            assert download.status_code == 200
            media = download.headers["content-type"].split(";")[0].strip()
            assert media == MEDIA_TYPES[fmt]
            downloads.append(download)

        # Same stored row must read identically through both prefixes.
        assert details[0] == details[1]
        assert _normalized_download_payload(fmt, downloads[0].content) == (
            _normalized_download_payload(fmt, downloads[1].content)
        )
        created_bodies[label] = details[0]
        created_downloads[label] = _normalized_download_payload(fmt, downloads[0].content)

    # Independently created /api and /api/v1 outputs must match after root-only normalization.
    assert created_bodies["api"] == created_bodies["api_v1"]
    assert created_downloads["api"] == created_downloads["api_v1"]

    assert parity_client.delete(f"/api/reports/{legacy_id}").status_code == 200
    assert parity_client.get(f"/api/v1/reports/{legacy_id}").status_code == 404
    assert parity_client.delete(f"/api/v1/reports/{v1_id}").status_code == 200
    assert parity_client.get(f"/api/reports/{v1_id}").status_code == 404


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
def test_api_and_v1_error_parity(parity_client: TestClient, suffix: str, expected: set[int]):
    legacy = parity_client.get(f"/api{suffix}")
    v1 = parity_client.get(f"/api/v1{suffix}")
    assert legacy.status_code == v1.status_code
    assert legacy.status_code in expected
    legacy_json = "application/json" in legacy.headers.get("content-type", "")
    v1_json = "application/json" in v1.headers.get("content-type", "")
    if legacy_json and v1_json:
        assert legacy.json() == v1.json()


def test_api_and_v1_unknown_route_parity(parity_client: TestClient):
    legacy = parity_client.get("/api/this-route-does-not-exist")
    v1 = parity_client.get("/api/v1/this-route-does-not-exist")
    assert legacy.status_code == v1.status_code == 404
    if (
        "application/json" in legacy.headers.get("content-type", "")
        and "application/json" in v1.headers.get("content-type", "")
    ):
        assert legacy.json() == v1.json()
