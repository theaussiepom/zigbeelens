"""API exposure tests for Device Story transport (Phase 4A-2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from zigbeelens.decisions.reasons import ReasonCode
from zigbeelens.decisions.types import CoverageLabelCode
from zigbeelens.topology.parser import parse_networkmap_payload

NOW = datetime(2026, 7, 13, 2, 0, 0, tzinfo=timezone.utc)

STORY_TOP_LEVEL_KEYS = {
    "subject_type",
    "subject_id",
    "status",
    "priority",
    "headline_code",
    "reasons",
    "evidence",
    "limitations",
    "suggested_checks",
    "coverage",
    "timeline",
}

REASON_KEYS = {"code", "params"}
EVIDENCE_KEYS = {"source", "id", "captured_at", "label"}
LIMITATION_KEYS = {"code", "params"}
CHECK_KEYS = {"code", "params"}
COVERAGE_KEYS = {"dimension", "state", "label_code", "params"}
TIMELINE_KEYS = {"code", "params", "occurred_at"}


def _upsert_device(
    repo,
    ieee: str,
    *,
    availability: str = "online",
    last_seen: datetime | None = None,
    battery: int | None = None,
) -> None:
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
        last_seen=(last_seen or NOW).isoformat(),
        battery=battery,
    )


def _store_snapshot(
    repo,
    snapshot_id: str,
    *,
    captured_at: datetime,
    links: list[dict],
    nodes: dict[str, dict] | None = None,
) -> None:
    default_nodes = {
        "0x01": {"type": "Coordinator"},
        "0x02": {"type": "Router"},
        "0x03": {"type": "EndDevice"},
    }
    repo.create_topology_snapshot(
        snapshot_id=snapshot_id,
        network_id="home",
        requested_by="test",
        status="pending",
        warning_acknowledged=True,
    )
    parsed = parse_networkmap_payload(
        {"nodes": default_nodes if nodes is None else nodes, "links": links}
    )
    repo.store_topology_parsed(snapshot_id, "home", parsed, status="complete")
    repo.db.conn.execute(
        "UPDATE topology_snapshots SET captured_at = ? WHERE snapshot_id = ?",
        (captured_at.isoformat(), snapshot_id),
    )
    repo.db.conn.commit()


def _open_incident_for(repo, ieee: str) -> None:
    repo.insert_incident(
        incident_id="inc-1",
        dedup_key="dedup-1",
        incident_type="single_device_unavailable",
        lifecycle_state="open",
        severity="warning",
        scope="device",
        confidence="medium",
        title="Device unavailable",
        summary="Device stopped reporting.",
        explanation="Passive observations show the device is unavailable.",
        evidence=[],
        counter_evidence=[],
        limitations=[],
        opened_at=NOW.isoformat(),
        updated_at=NOW.isoformat(),
    )
    repo.db.conn.execute(
        """
        INSERT INTO incident_devices (incident_id, network_id, ieee_address, role)
        VALUES ('inc-1', 'home', ?, 'affected')
        """,
        (ieee,),
    )
    repo.db.conn.commit()


def _topology_gap_nodes() -> dict[str, dict]:
    return {
        "0x01": {"type": "Coordinator"},
        "0x02": {"type": "Router"},
        "0x03": {"type": "EndDevice"},
    }


def _seed_topology_gap_fixture(repo) -> None:
    nodes = _topology_gap_nodes()
    _store_snapshot(repo, "snap-latest", captured_at=NOW, links=[], nodes=nodes)
    _store_snapshot(
        repo,
        "snap-old",
        captured_at=NOW - timedelta(days=1),
        links=[{"source": "0x02", "target": "0x03", "linkquality": 90}],
        nodes=nodes,
    )


def test_device_story_api_topology_gap_exact_response_shape(topology_client: TestClient):
    ctx = topology_client.app.state.ctx
    _upsert_device(ctx.repo, "0x03")
    _seed_topology_gap_fixture(ctx.repo)

    res = topology_client.get("/api/devices/home/0x03/story")
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == STORY_TOP_LEVEL_KEYS

    assert body["subject_type"] == "device"
    assert body["subject_id"] == "0x03"
    assert body["status"] == "watch"
    assert body["priority"] == "low"
    assert body["headline_code"] == "topology_evidence_gap"

    reason_codes = {reason["code"] for reason in body["reasons"]}
    assert ReasonCode.latest_snapshot_no_links in reason_codes
    assert (
        ReasonCode.selected_snapshot_had_links in reason_codes
        or ReasonCode.recent_missing_links_present in reason_codes
    )

    limitation_codes = {item["code"] for item in body["limitations"]}
    assert "absence_from_latest_not_failure" in limitation_codes

    check_codes = {item["code"] for item in body["suggested_checks"]}
    assert "compare_earlier_snapshot" in check_codes

    assert any(item["source"] == "topology_snapshot" for item in body["evidence"])
    assert body["timeline"] == []

    for reason in body["reasons"]:
        assert set(reason.keys()) == REASON_KEYS
    for item in body["evidence"]:
        assert set(item.keys()) == EVIDENCE_KEYS
    for item in body["limitations"]:
        assert set(item.keys()) == LIMITATION_KEYS
    for item in body["suggested_checks"]:
        assert set(item.keys()) == CHECK_KEYS
    for item in body["coverage"]:
        assert set(item.keys()) == COVERAGE_KEYS
    for item in body["timeline"]:
        assert set(item.keys()) == TIMELINE_KEYS


def test_device_story_api_current_issue_serialisation(topology_client: TestClient):
    ctx = topology_client.app.state.ctx
    _upsert_device(ctx.repo, "0x03", availability="offline")
    _store_snapshot(
        ctx.repo,
        "snap-latest",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x03", "linkquality": 120}],
    )

    res = topology_client.get("/api/devices/home/0x03/story")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "worth_reviewing"
    assert body["priority"] == "high"
    assert body["headline_code"] == "current_issue_present"
    assert ReasonCode.current_issue_present in {reason["code"] for reason in body["reasons"]}


def test_device_story_api_current_issue_plus_topology_gap(topology_client: TestClient):
    ctx = topology_client.app.state.ctx
    _upsert_device(ctx.repo, "0x03", availability="offline")
    _seed_topology_gap_fixture(ctx.repo)

    res = topology_client.get("/api/devices/home/0x03/story")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "review_first"
    assert body["priority"] == "high"
    assert body["headline_code"] == "current_issue_present"


def test_device_story_api_coverage_serialisation(topology_client: TestClient):
    ctx = topology_client.app.state.ctx
    _upsert_device(ctx.repo, "0x03", availability="unknown")
    _store_snapshot(
        ctx.repo,
        "snap-latest",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x03", "linkquality": 120}],
    )

    res = topology_client.get("/api/devices/home/0x03/story")
    assert res.status_code == 200
    body = res.json()
    assert body["coverage"]
    coverage = body["coverage"][0]
    assert set(coverage.keys()) == COVERAGE_KEYS
    tracking_off = next(
        item
        for item in body["coverage"]
        if item["label_code"] == CoverageLabelCode.availability_tracking_off
    )
    assert tracking_off["dimension"] == "availability"
    assert tracking_off["state"] == "off"
    assert tracking_off["label_code"] == "availability_tracking_off"


def test_device_story_api_unknown_network(topology_client: TestClient):
    res = topology_client.get("/api/devices/nope/0x03/story")
    assert res.status_code == 404
    assert res.json() == {"detail": "Network not found"}


def test_device_story_api_unknown_device(topology_client: TestClient):
    res = topology_client.get("/api/devices/home/0xmissing/story")
    assert res.status_code == 404
    assert res.json() == {"detail": "Device not found"}


def test_device_story_api_ieee_normalisation(topology_client: TestClient):
    ctx = topology_client.app.state.ctx
    _upsert_device(ctx.repo, "0x03")
    _store_snapshot(
        ctx.repo,
        "snap-latest",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x03", "linkquality": 120}],
    )

    res = topology_client.get("/api/devices/home/0X03/story")
    assert res.status_code == 200
    assert res.json()["subject_id"] == "0x03"


def test_device_story_api_output_remains_coded(topology_client: TestClient):
    ctx = topology_client.app.state.ctx
    _upsert_device(ctx.repo, "0x03", availability="offline")
    _open_incident_for(ctx.repo, "0x03")
    _seed_topology_gap_fixture(ctx.repo)

    body = topology_client.get("/api/devices/home/0x03/story").json()
    text = str(body).lower()
    assert "caused by" not in text
    assert "broken link" not in text
    assert "parent router" not in text
    assert "current route" not in text
    assert body["headline_code"]
    assert " " not in body["headline_code"]
    for reason in body["reasons"]:
        assert reason["code"]
        assert " " not in reason["code"]
