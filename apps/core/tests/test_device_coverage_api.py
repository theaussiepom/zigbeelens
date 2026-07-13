"""API exposure tests for per-device evidence coverage (Phase 4C-2)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from zigbeelens.decisions.types import CoverageDimension, CoverageLabelCode, CoverageState

NOW = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)

COVERAGE_KEYS = {"dimension", "state", "label_code", "params"}


def _upsert_device(repo, ieee: str, *, availability: str = "online") -> None:
    repo.upsert_device(
        network_id="home",
        ieee_address=ieee,
        friendly_name=f"Device {ieee}",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )
    repo.update_device_current_state(
        network_id="home",
        ieee_address=ieee,
        availability=availability,
        last_seen=NOW.isoformat(),
        last_payload_at=NOW.isoformat(),
    )


def test_device_coverage_api_unknown_network(topology_client: TestClient):
    res = topology_client.get("/api/devices/nope/0x03/coverage")
    assert res.status_code == 404
    assert res.json() == {"detail": "Network not found"}


def test_device_coverage_api_unknown_device(topology_client: TestClient):
    res = topology_client.get("/api/devices/home/0xmissing/coverage")
    assert res.status_code == 404
    assert res.json() == {"detail": "Device not found"}


def test_device_coverage_api_returns_coded_facts(topology_client: TestClient):
    ctx = topology_client.app.state.ctx
    _upsert_device(ctx.repo, "0x03")

    res = topology_client.get("/api/devices/home/0x03/coverage")
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    assert len(body) >= 5
    for item in body:
        assert set(item.keys()) == COVERAGE_KEYS

    labels = {item["label_code"] for item in body}
    assert CoverageLabelCode.availability_available in labels
    assert CoverageLabelCode.last_seen_available in labels
    assert CoverageLabelCode.last_payload_available in labels
    assert CoverageLabelCode.ha_areas_not_linked in labels


def test_device_coverage_api_ieee_normalisation(topology_client: TestClient):
    ctx = topology_client.app.state.ctx
    _upsert_device(ctx.repo, "0x03")

    res = topology_client.get("/api/devices/home/0X03/coverage")
    assert res.status_code == 200
    assert len(res.json()) >= 1


def test_device_coverage_api_dimension_order_is_stable(topology_client: TestClient):
    ctx = topology_client.app.state.ctx
    _upsert_device(ctx.repo, "0x03")

    first = topology_client.get("/api/devices/home/0x03/coverage").json()
    second = topology_client.get("/api/devices/home/0x03/coverage").json()
    assert first == second
    dimensions = [item["dimension"] for item in first]
    assert dimensions.index(CoverageDimension.availability) < dimensions.index(
        CoverageDimension.ha_enrichment
    )


def test_device_coverage_api_topology_params(topology_client: TestClient):
    ctx = topology_client.app.state.ctx
    _upsert_device(ctx.repo, "0x03")

    res = topology_client.get("/api/devices/home/0x03/coverage")
    topology = next(
        item for item in res.json() if item["dimension"] == CoverageDimension.historical_snapshots
    )
    assert topology["state"] == CoverageState.not_observed
    assert topology["label_code"] == CoverageLabelCode.topology_history_not_observed
    assert topology["params"]["observed_snapshot_count"] == 0
    assert topology["params"]["snapshot_window_count"] == 0
