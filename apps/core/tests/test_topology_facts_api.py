"""API exposure tests for topology decision facts (Phase 3A-3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest
from fastapi.testclient import TestClient

from zigbeelens.app.context import get_context
from zigbeelens.config.models import TopologyConfig
from zigbeelens.decisions.topology_facts import TopologyFactCode
from zigbeelens.services.topology_facts_composition import topology_stale_threshold_hours
from zigbeelens.topology.device_compare import MAX_SNAPSHOT_HISTORY
from zigbeelens.topology.parser import parse_networkmap_payload


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _store_snapshot(
    repo,
    snapshot_id: str,
    *,
    captured_at: datetime,
    links: list[dict],
    nodes: list[dict] | dict[str, dict] | None = None,
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
            "nodes": nodes
            if nodes is not None
            else {
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
    assert set(topology_facts.keys()) == {"stale_threshold_hours", "network_facts", "coverage"}
    assert topology_facts["stale_threshold_hours"] is None
    assert isinstance(topology_facts["network_facts"], list)
    assert isinstance(topology_facts["coverage"], list)
    if topology_facts["coverage"]:
        item = topology_facts["coverage"][0]
        assert set(item.keys()) == {"dimension", "state", "label_code", "params"}


def test_snapshot_detail_never_exposes_stored_raw_topology_surfaces(
    topology_client: TestClient,
):
    ctx = get_context()
    _store_snapshot(
        ctx.repo,
        "snap-private-raw",
        captured_at=_utc_now(),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 90}],
    )
    ctx.repo.db.conn.execute(
        """
        UPDATE topology_snapshots
        SET raw_redacted_json = ?, parsed_json = ?
        WHERE snapshot_id = ?
        """,
        (
            '{"password":"legacy-snapshot-secret"}',
            '{"token":"legacy-parsed-secret"}',
            "snap-private-raw",
        ),
    )
    ctx.repo.db.conn.execute(
        """
        UPDATE topology_nodes
        SET raw_json = '{"network_key":"legacy-node-secret"}'
        WHERE snapshot_id = ?
        """,
        ("snap-private-raw",),
    )
    ctx.repo.db.conn.execute(
        """
        UPDATE topology_links
        SET raw_json = '{"api_key":"legacy-link-secret"}'
        WHERE snapshot_id = ?
        """,
        ("snap-private-raw",),
    )
    ctx.repo.db.conn.commit()

    for prefix in ("/api", "/api/v1"):
        response = topology_client.get(
            f"{prefix}/topology/home/snapshots/snap-private-raw"
        )
        assert response.status_code == 200
        blob = json.dumps(response.json(), sort_keys=True)
        for private_field in ("raw_redacted_json", "parsed_json", "raw_json"):
            assert f'"{private_field}"' not in blob
        for secret in (
            "legacy-snapshot-secret",
            "legacy-parsed-secret",
            "legacy-node-secret",
            "legacy-link-secret",
        ):
            assert secret not in blob


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

    bodies = []
    for prefix in ("/api", "/api/v1"):
        lower_response = topology_client.get(
            f"{prefix}/topology/home/devices/0x04/snapshot-history"
        )
        mixed_response = topology_client.get(
            f"{prefix}/topology/home/devices/0X04/snapshot-history"
        )
        assert lower_response.status_code == mixed_response.status_code == 200
        body = lower_response.json()
        mixed_case_body = mixed_response.json()
        assert mixed_case_body["device_ieee"] == body["device_ieee"] == "0x04"
        assert mixed_case_body["latest_snapshot"] == body["latest_snapshot"]
        assert mixed_case_body["snapshots"] == body["snapshots"]
        assert mixed_case_body["topology_facts"] == body["topology_facts"]
        bodies.append(body)
    assert bodies[0] == bodies[1]
    body = bodies[0]

    unknown_responses = [
        topology_client.get(
            f"{prefix}/topology/home/devices/%20%200XMISSING%20%20/snapshot-history"
        )
        for prefix in ("/api", "/api/v1")
    ]
    assert {response.status_code for response in unknown_responses} == {404}
    assert unknown_responses[0].json() == unknown_responses[1].json() == {
        "detail": "Device '0xmissing' was not found in network 'home'"
    }

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


def _history_bodies(
    client: TestClient,
    ieee: str,
) -> list[dict]:
    bodies: list[dict] = []
    for prefix in ("/api", "/api/v1"):
        for spelling in (ieee.lower(), ieee.upper()):
            response = client.get(f"{prefix}/topology/home/devices/{spelling}/snapshot-history")
            assert response.status_code == 200
            bodies.append(response.json())
    assert all(body == bodies[0] for body in bodies[1:])
    return bodies


@pytest.mark.parametrize(
    ("latest_present", "selected_present", "expected_reason"),
    (
        (
            False,
            True,
            "The device was observed in the selected snapshot but not the latest "
            "snapshot.",
        ),
        (
            True,
            False,
            "The device was observed in the latest snapshot but not the selected "
            "snapshot.",
        ),
    ),
)
def test_snapshot_history_api_compares_node_only_presence_with_exact_facts(
    topology_client: TestClient,
    latest_present: bool,
    selected_present: bool,
    expected_reason: str,
) -> None:
    ctx = get_context()
    target = "0x0a"

    def nodes(present: bool) -> dict[str, dict[str, str]]:
        result = {"0x01": {"type": "Coordinator"}}
        if present:
            result[target] = {"type": "EndDevice"}
        return result

    _store_snapshot(
        ctx.repo,
        "snap-selected-presence",
        captured_at=_utc_now() - timedelta(days=1),
        nodes=nodes(selected_present),
        links=[],
    )
    _store_snapshot(
        ctx.repo,
        "snap-latest-presence",
        captured_at=_utc_now(),
        nodes=nodes(latest_present),
        links=[],
    )

    body = _history_bodies(topology_client, target)[0]
    latest = body["latest_snapshot"]
    selected = body["snapshots"][0]
    comparison = selected["comparison_to_latest"]

    assert latest["device_present_in_snapshot"] is latest_present
    assert selected["device_present_in_snapshot"] is selected_present
    assert comparison["device_presence"] == {
        "latest": latest_present,
        "selected": selected_present,
        "changed": True,
    }
    assert comparison["status"] == "changed"
    assert comparison["reasons"][0] == expected_reason
    assert comparison["link_counts"]["latest_count"] == 0
    assert comparison["link_counts"]["selected_count"] == 0
    assert comparison["route_hint_counts"]["latest_count"] == 0
    assert comparison["route_hint_counts"]["selected_count"] == 0

    facts = body["topology_facts"]["comparison_facts_by_snapshot_id"][
        "snap-selected-presence"
    ]
    changed_fact = next(
        fact
        for fact in facts
        if fact["code"] == TopologyFactCode.device_latest_vs_selected_changed
    )
    assert changed_fact["params"] == {
        "device_ieee": target,
        "comparison_status": "changed",
        "snapshot_id": "snap-selected-presence",
        "latest_device_present_in_snapshot": latest_present,
        "selected_device_present_in_snapshot": selected_present,
        "device_presence_changed": True,
    }


def test_snapshot_history_current_device_without_topology_history_is_available(
    topology_client: TestClient,
) -> None:
    ctx = get_context()
    target = "0xcurrentonly"
    ctx.repo.upsert_device(
        network_id="home",
        ieee_address=target,
        friendly_name="Current only",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )

    body = _history_bodies(topology_client, target)[0]

    assert body["device_ieee"] == target
    assert body["friendly_name"] == "Current only"
    assert body["latest_snapshot"] is None
    assert body["snapshots"] == []


def test_snapshot_history_topology_only_latest_node_is_available(
    topology_client: TestClient,
) -> None:
    ctx = get_context()
    target = "0xlatestonly"
    _store_snapshot(
        ctx.repo,
        "snap-latest-only",
        captured_at=_utc_now(),
        nodes=[
            {"ieeeAddr": "0xpeer", "type": "Router"},
            {
                "ieeeAddr": target,
                "friendlyName": "Topology only",
                "type": "EndDevice",
            },
        ],
        links=[],
    )
    assert ctx.repo.get_device("home", target) is None

    body = _history_bodies(topology_client, target)[0]

    assert body["device_ieee"] == target
    assert body["latest_snapshot"]["snapshot_id"] == "snap-latest-only"
    assert body["latest_snapshot"]["is_usable"] is True
    assert body["latest_snapshot"]["layout_state"] == "available"
    assert body["latest_snapshot"]["device_present_in_snapshot"] is True
    assert body["latest_snapshot"]["links_for_device_count"] == 0
    assert body["latest_snapshot"]["route_hints_for_device_count"] == 0
    codes = {fact["code"] for fact in body["topology_facts"]["device_facts"]}
    assert TopologyFactCode.device_seen_in_latest_snapshot in codes
    assert TopologyFactCode.device_no_latest_links in codes


def test_snapshot_history_available_latest_can_truthfully_report_device_absence(
    topology_client: TestClient,
) -> None:
    ctx = get_context()
    target = "0xcurrentabsent"
    ctx.repo.upsert_device(
        network_id="home",
        ieee_address=target,
        friendly_name="Current absent",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )
    _store_snapshot(
        ctx.repo,
        "snap-available-absent",
        captured_at=_utc_now(),
        nodes=[{"ieeeAddr": "0xpeer", "type": "Router"}],
        links=[],
    )

    body = _history_bodies(topology_client, target)[0]

    latest = body["latest_snapshot"]
    assert latest["layout_state"] == "available"
    assert latest["is_usable"] is True
    assert latest["device_present_in_snapshot"] is False
    assert latest["links_for_device_count"] == 0
    assert latest["route_hints_for_device_count"] == 0
    codes = {fact["code"] for fact in body["topology_facts"]["device_facts"]}
    assert TopologyFactCode.device_absent_from_latest_snapshot in codes
    assert TopologyFactCode.device_no_latest_links in codes
    assert TopologyFactCode.device_seen_in_latest_snapshot not in codes


def test_snapshot_history_latest_link_only_identity_is_positively_represented(
    topology_client: TestClient,
) -> None:
    ctx = get_context()
    target = "0xlatestlinkonly"
    _store_snapshot(
        ctx.repo,
        "snap-latest-link-only",
        captured_at=_utc_now(),
        nodes=[{"ieeeAddr": "0xpeer", "type": "Router"}],
        links=[{"source": "0xpeer", "target": target, "linkquality": 82}],
    )
    assert ctx.repo.get_device("home", target) is None

    body = _history_bodies(topology_client, target)[0]

    latest = body["latest_snapshot"]
    assert latest["layout_state"] == "available"
    assert latest["device_present_in_snapshot"] is True
    assert latest["links_for_device_count"] == 1
    assert latest["route_hints_for_device_count"] == 0
    codes = {fact["code"] for fact in body["topology_facts"]["device_facts"]}
    assert TopologyFactCode.device_seen_in_latest_snapshot in codes
    assert TopologyFactCode.device_has_latest_links in codes
    assert TopologyFactCode.device_absent_from_latest_snapshot not in codes


@pytest.mark.parametrize(
    ("evidence_kind", "expected_link_count"),
    [
        ("node", 0),
        ("source_link", 1),
        ("target_link", 1),
    ],
)
def test_snapshot_history_accepts_identity_only_in_older_retained_snapshot(
    topology_client: TestClient,
    evidence_kind: str,
    expected_link_count: int,
) -> None:
    ctx = get_context()
    target = f"0xhistorical{evidence_kind}"
    older_nodes = [{"ieeeAddr": "0xpeer", "type": "Router"}]
    older_links: list[dict] = []
    if evidence_kind == "node":
        older_nodes.append(
            {
                "ieeeAddr": target,
                "friendlyName": "Historical only",
                "type": "EndDevice",
            }
        )
    elif evidence_kind == "source_link":
        older_links.append({"source": target, "target": "0xpeer", "linkquality": 80})
    else:
        older_links.append({"source": "0xpeer", "target": target, "linkquality": 81})
    now = _utc_now()
    _store_snapshot(
        ctx.repo,
        "snap-historical",
        captured_at=now - timedelta(days=1),
        nodes=older_nodes,
        links=older_links,
    )
    # The selected latest snapshot is layout-limited and omits the identity.
    _store_snapshot(
        ctx.repo,
        "snap-layout-limited",
        captured_at=now,
        nodes=[],
        links=[],
    )
    assert ctx.repo.get_device("home", target) is None

    body = _history_bodies(topology_client, target)[0]

    assert body["device_ieee"] == target
    latest = body["latest_snapshot"]
    assert latest["snapshot_id"] == "snap-layout-limited"
    assert latest["is_usable"] is False
    assert latest["layout_state"] == "limited"
    assert latest["device_present_in_snapshot"] is None
    assert latest["links_for_device_count"] is None
    assert latest["route_hints_for_device_count"] is None
    assert latest["comparison_to_latest"] is None
    historical = body["snapshots"][0]
    assert historical["snapshot_id"] == "snap-historical"
    assert historical["is_usable"] is True
    assert historical["layout_state"] == "available"
    assert historical["device_present_in_snapshot"] is True
    assert historical["links_for_device_count"] == expected_link_count
    assert historical["route_hints_for_device_count"] == 0
    assert historical["comparison_to_latest"] is None
    codes = {fact["code"] for fact in body["topology_facts"]["device_facts"]}
    assert TopologyFactCode.device_absent_from_latest_snapshot not in codes
    assert TopologyFactCode.device_no_latest_links not in codes
    assert TopologyFactCode.device_seen_in_latest_snapshot not in codes
    comparison_codes = {
        fact["code"]
        for fact in body["topology_facts"][
            "comparison_facts_by_snapshot_id"
        ]["snap-historical"]
    }
    assert TopologyFactCode.device_latest_vs_selected_changed not in comparison_codes


def test_snapshot_history_identity_outside_retained_window_is_unknown_unless_current(
    topology_client: TestClient,
) -> None:
    ctx = get_context()
    target = "0xoutsidewindow"
    never_seen = "0xneverseen"
    now = _utc_now()
    _store_snapshot(
        ctx.repo,
        "snap-outside-window",
        captured_at=now - timedelta(days=30),
        nodes=[
            {"ieeeAddr": "0xpeer", "type": "Router"},
            {"ieeeAddr": target, "type": "EndDevice"},
        ],
        links=[],
    )
    for index in range(MAX_SNAPSHOT_HISTORY):
        _store_snapshot(
            ctx.repo,
            f"snap-retained-{index:02d}",
            captured_at=now - timedelta(minutes=MAX_SNAPSHOT_HISTORY - index),
            nodes=[{"ieeeAddr": "0xpeer", "type": "Router"}],
            links=[],
        )

    for ieee in (target, never_seen):
        responses = [
            topology_client.get(f"{prefix}/topology/home/devices/{ieee}/snapshot-history")
            for prefix in ("/api", "/api/v1")
        ]
        assert [response.status_code for response in responses] == [404, 404]
        assert responses[0].json() == responses[1].json()

    ctx.repo.upsert_device(
        network_id="home",
        ieee_address=target,
        friendly_name="Current retained override",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )
    body = _history_bodies(topology_client, target)[0]
    assert body["friendly_name"] == "Current retained override"
    assert 1 + len(body["snapshots"]) == MAX_SNAPSHOT_HISTORY
