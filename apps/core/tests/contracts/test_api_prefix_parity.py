"""Table-driven /api versus /api/v1 parity — identity-sensitive equality."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from zigbeelens.enrichment import ha as ha_module
from zigbeelens.schemas import ReportDetailV3
from zigbeelens.services import report_redaction as report_redaction_mod
from zigbeelens.services import reports as reports_mod

_FIXED_SALT = "zigbeelens-api-prefix-parity-v1"
_FIXED_ENRICHMENT_TIME = "2026-07-13T12:00:00+00:00"
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
    monkeypatch.setattr(ha_module, "utc_now_iso", lambda: _FIXED_ENRICHMENT_TIME)

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


def test_api_and_v1_enrichment_mutation_parity(parity_client: TestClient):
    request = {
        "home_assistant_enrichment_contract_version": 1,
        "devices": [
            {
                "network_id": "home",
                "ieee_address": "0X00158D0001A1B2C3",
                "ha_device_id": "ha-motion",
                "ha_device_name": "Living room motion",
                "area_id": "living-room",
                "area_name": "Living room",
                "entity_id": "binary_sensor.living_room_motion",
            }
        ],
    }
    legacy = parity_client.post("/api/enrichment/homeassistant", json=request)
    v1 = parity_client.post("/api/v1/enrichment/homeassistant", json=request)
    assert legacy.status_code == v1.status_code == 200
    assert legacy.json() == v1.json() == {
        "home_assistant_enrichment_contract_version": 1,
        "submitted": 1,
        "matched": 1,
        "unmatched": 0,
        "ambiguous": 0,
        "stored": 1,
        "last_push_at": _FIXED_ENRICHMENT_TIME,
    }

    legacy_clear = parity_client.delete("/api/enrichment/homeassistant")
    v1_clear = parity_client.delete("/api/v1/enrichment/homeassistant")
    assert legacy_clear.status_code == v1_clear.status_code == 200
    assert legacy_clear.json() == v1_clear.json() == {"cleared": True}


def test_api_and_v1_malformed_enrichment_error_parity(parity_client: TestClient):
    malformed = {
        "home_assistant_enrichment_contract_version": True,
        "devices": [],
    }
    legacy = parity_client.post("/api/enrichment/homeassistant", json=malformed)
    v1 = parity_client.post("/api/v1/enrichment/homeassistant", json=malformed)
    assert legacy.status_code == v1.status_code == 422
    _assert_json_error_parity(legacy, v1)


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
def test_api_and_v1_same_request_report_mutation_parity(parity_client: TestClient, fmt: str):
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

    # Canonical bodies/downloads for the independently created reports.
    created_raw_bodies: dict[str, dict[str, Any]] = {}
    created_bodies: dict[str, dict[str, Any]] = {}
    created_downloads: dict[str, Any] = {}

    for label, report_id in (("api", legacy_id), ("api_v1", v1_id)):
        raw_details: list[dict[str, Any]] = []
        downloads = []
        for prefix in ("/api", "/api/v1"):
            detail = parity_client.get(f"{prefix}/reports/{report_id}")
            context = f"format={fmt} report_id={report_id} prefix={prefix} detail"
            assert detail.status_code == 200, f"{context}: status mismatch"
            body = detail.json()
            assert type(body["report_version"]) is int, (
                f"{context}: report_version is not an exact integer"
            )
            assert body["report_version"] == 3, f"{context}: report_version mismatch"
            assert body["format"] == fmt, f"{context}: format mismatch"
            ReportDetailV3.model_validate(body)
            raw_details.append(body)

            download = parity_client.get(f"{prefix}/reports/{report_id}/download")
            assert download.status_code == 200, (
                f"format={fmt} report_id={report_id} prefix={prefix} download: status mismatch"
            )
            media = download.headers["content-type"].split(";")[0].strip()
            assert media == MEDIA_TYPES[fmt], (
                f"format={fmt} report_id={report_id} prefix={prefix} download: "
                "unexpected media type"
            )
            downloads.append(download)

        # Same stored row must read identically through both prefixes.
        same_row_context = f"format={fmt} report_id={report_id} prefix_pair=/api,/api/v1"
        legacy_detail, v1_detail = raw_details
        assert legacy_detail == v1_detail, f"{same_row_context}: raw detail body mismatch"
        for field in ("id", "generated_at", "report_version", "format"):
            assert legacy_detail[field] == v1_detail[field], (
                f"{same_row_context}: detail identity field {field!r} mismatch"
            )
        semantic_fields = sorted(
            (set(legacy_detail) | set(v1_detail))
            - {"id", "generated_at", "report_version", "format"}
        )
        for field in semantic_fields:
            assert legacy_detail.get(field) == v1_detail.get(field), (
                f"{same_row_context}: nested semantic detail field {field!r} mismatch"
            )

        legacy_download, v1_download = downloads
        assert legacy_download.content == v1_download.content, (
            f"{same_row_context}: download byte mismatch"
        )
        assert legacy_download.headers["content-type"] == v1_download.headers["content-type"], (
            f"{same_row_context}: download media-type header mismatch"
        )
        assert legacy_download.headers.get("content-disposition") == v1_download.headers.get(
            "content-disposition"
        ), f"{same_row_context}: download Content-Disposition/filename mismatch"
        assert legacy_download.headers.get("content-disposition"), (
            f"{same_row_context}: download Content-Disposition missing"
        )

        # Use the /api same-row body only after exact identity/semantic checks pass.
        created_raw_bodies[label] = legacy_detail
        created_bodies[label] = _normalize_root_report_fields(legacy_detail)
        created_downloads[label] = _normalized_download_payload(fmt, downloads[0].content)

    # Independently created /api and /api/v1 outputs must match after root-only normalization.
    assert created_bodies["api"] == created_bodies["api_v1"], (
        f"format={fmt} independently-created detail mismatch after root-only normalization"
    )
    assert created_downloads["api"] == created_downloads["api_v1"], (
        f"format={fmt} independently-created download mismatch after root-only normalization"
    )

    list_legacy = parity_client.get("/api/reports")
    list_v1 = parity_client.get("/api/v1/reports")
    assert list_legacy.status_code == list_v1.status_code == 200
    # Exact list-body equality between prefixes (ordering preserved).
    assert list_legacy.json() == list_v1.json()
    listed = list_legacy.json()
    listed_ids = [row["id"] for row in listed]
    assert legacy_id in listed_ids
    assert v1_id in listed_ids

    api_list_row = next(row for row in listed if row["id"] == legacy_id)
    v1_list_row = next(row for row in listed if row["id"] == v1_id)
    assert _normalize_creation_summary(api_list_row) == _normalize_creation_summary(v1_list_row)

    for report_id, create_body, detail_body in (
        (legacy_id, create_legacy.json(), created_raw_bodies["api"]),
        (v1_id, create_v1.json(), created_raw_bodies["api_v1"]),
    ):
        list_row = next(row for row in listed if row["id"] == report_id)
        assert list_row["id"] == create_body["id"] == report_id
        assert list_row["format"] == create_body["format"] == fmt
        assert list_row["format"] == detail_body["format"]
        assert list_row["scope"] == create_body["scope"] == detail_body["scope"]
        assert list_row["redaction_profile"] == create_body["redaction_profile"]
        assert list_row["redaction_profile"] == detail_body["redaction"]["profile"]
        assert list_row["redaction_applied"] == create_body["redaction_applied"]
        assert list_row["redaction_applied"] == detail_body["redaction"]["applied"]
        assert list_row["incident_count"] == create_body["incident_count"]
        assert list_row["incident_count"] == len(detail_body["incidents"])
        assert list_row["device_count"] == create_body["device_count"]
        assert list_row["network_count"] == create_body["network_count"]
        assert list_row["summary"] == create_body["summary"]
        assert (
            list_row["generated_at"] == create_body["generated_at"] == detail_body["generated_at"]
        )

    assert parity_client.delete(f"/api/reports/{legacy_id}").status_code == 200
    assert parity_client.get(f"/api/v1/reports/{legacy_id}").status_code == 404
    assert parity_client.delete(f"/api/v1/reports/{v1_id}").status_code == 200
    assert parity_client.get(f"/api/reports/{v1_id}").status_code == 404


def _assert_json_error_parity(legacy, v1) -> None:
    assert legacy.status_code == v1.status_code
    legacy_ct = legacy.headers.get("content-type", "")
    v1_ct = v1.headers.get("content-type", "")
    assert "application/json" in legacy_ct, legacy_ct
    assert "application/json" in v1_ct, v1_ct
    assert legacy.json() == v1.json()


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
    assert legacy.status_code in expected
    _assert_json_error_parity(legacy, v1)


def test_api_and_v1_unknown_route_parity(parity_client: TestClient):
    legacy = parity_client.get("/api/this-route-does-not-exist")
    v1 = parity_client.get("/api/v1/this-route-does-not-exist")
    assert legacy.status_code == v1.status_code == 404
    _assert_json_error_parity(legacy, v1)
