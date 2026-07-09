"""Problem-first investigation card tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from zigbeelens.storage.repository import DeviceRow
from zigbeelens.topology.investigations import (
    DIAGNOSTICS_LIMITED_MIN_DEVICES,
    GENERIC_INVESTIGATION_LIMITATION,
    ISSUE_CLUSTER_MIN_DEVICES,
    ISSUE_DEVICE_WEIGHT,
    LOW_BATTERY_PERCENT,
    MAX_INVESTIGATION_CARDS,
    MAX_SUGGESTED_NEXT_STEPS,
    PRIORITY_CONTEXT_ONLY,
    RECENT_MISSING_CLUSTER_MIN_EDGES,
    RECENT_MISSING_EDGE_WEIGHT,
    REPEATED_OFFLINE_MIN_COUNT,
    ROUTER_REVIEW_MIN_ISSUE_NEIGHBOURS,
    ROUTER_REVIEW_MIN_LINKS,
    STALE_LAST_SEEN_HOURS,
    TOPOLOGY_CORROBORATION_WEIGHT,
    WEAK_LINK_LQI,
    build_investigations,
)

NOW = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)

FORBIDDEN_PHRASES = [
    "root cause",
    "caused by",
    "parent router",
    "child device",
    "current route",
    "currently routed",
    "actual path",
    "failed because",
    "broken link",
    "lost link",
    "same parent",
    "heal network",
]


def _device(
    ieee: str,
    *,
    device_type: str = "EndDevice",
    availability: str = "online",
    power_source: str = "Mains",
    name: str | None = None,
    battery: int | None = None,
    last_seen: str | None = None,
) -> DeviceRow:
    return DeviceRow(
        network_id="home",
        ieee_address=ieee,
        friendly_name=name or f"Device {ieee}",
        device_type=device_type,
        power_source=power_source,
        manufacturer=None,
        model=None,
        interview_state="successful",
        availability=availability,
        battery=battery,
        last_seen=last_seen,
    )


def _link(source: str, target: str, *, lqi: int = 100) -> dict:
    return {
        "source_ieee": source,
        "target_ieee": target,
        "linkquality": lqi,
        "source_type": None,
        "target_type": None,
        "route_count": None,
        "relationship": None,
    }


def _empty_history() -> dict:
    return {"historical_neighbors": [], "historical_routes": []}


def _missing_edge(source: str, target: str, *, last_seen: datetime) -> dict:
    return {
        "source_ieee": source,
        "target_ieee": target,
        "evidence_class": "historical_neighbor",
        "last_seen_at": last_seen.isoformat(),
    }


def _passive_hint(
    source: str,
    target: str,
    *,
    confidence: str = "low",
    rules: list[str] | None = None,
    last_seen: datetime | None = None,
) -> dict:
    return {
        "source_ieee": source,
        "target_ieee": target,
        "evidence_class": "passive_derived_association",
        "confidence": confidence,
        "rules_matched": rules or ["shared_instability_window"],
        "last_seen_at": (last_seen or NOW - timedelta(hours=2)).isoformat(),
    }


def _build(**overrides) -> dict:
    defaults = dict(
        devices=[],
        incident_device_ieees=set(),
        latest_nodes=[],
        latest_links=[],
        latest_captured_at=(NOW - timedelta(hours=1)).isoformat(),
        history=_empty_history(),
        passive_hints=[],
        now=NOW,
    )
    defaults.update(overrides)
    return build_investigations(**defaults)


def test_issue_cluster_from_shared_observed_neighbourhood():
    # Router 0xr1 has two offline devices in its observed neighbourhood.
    devices = [
        _device("0xr1", device_type="Router", name="Hall router"),
        _device("0xa1", availability="offline"),
        _device("0xa2", availability="offline"),
        _device("0xb1"),
    ]
    links = [_link("0xr1", "0xa1"), _link("0xr1", "0xa2"), _link("0xr1", "0xb1")]
    result = _build(
        devices=devices,
        latest_nodes=[{"ieee_address": d.ieee_address} for d in devices],
        latest_links=links,
    )
    cards = [c for c in result["investigations"] if c["type"] == "issue_cluster"]
    assert len(cards) == 1
    card = cards[0]
    assert card["primary_neighbourhood_ieee"] == "0xr1"
    assert set(card["device_ieees"]) == {"0xr1", "0xa1", "0xa2"}
    assert card["score"] >= ISSUE_DEVICE_WEIGHT * ISSUE_CLUSTER_MIN_DEVICES
    assert "observed" in card["summary"]
    assert GENERIC_INVESTIGATION_LIMITATION in card["limitations"]
    # Focusable edges reference the UI's live-neighbour id scheme.
    assert "live-neighbor-0xa1|0xr1" in card["edge_ids"]


def test_single_issue_device_does_not_create_issue_cluster():
    devices = [
        _device("0xr1", device_type="Router"),
        _device("0xa1", availability="offline"),
        _device("0xb1"),
    ]
    links = [_link("0xr1", "0xa1"), _link("0xr1", "0xb1")]
    result = _build(
        devices=devices,
        latest_nodes=[{"ieee_address": d.ieee_address} for d in devices],
        latest_links=links,
    )
    assert not [c for c in result["investigations"] if c["type"] == "issue_cluster"]


def test_recent_missing_cluster_from_missing_edges():
    devices = [_device("0xa1", name="Bedroom sensor"), _device("0xr1", device_type="Router")]
    history = {
        "historical_neighbors": [
            _missing_edge("0xa1", "0xr1", last_seen=NOW - timedelta(hours=3)),
            _missing_edge("0xa1", "0xr2", last_seen=NOW - timedelta(hours=4)),
            _missing_edge("0xa1", "0xr3", last_seen=NOW - timedelta(hours=5)),
        ],
        "historical_routes": [],
    }
    result = _build(
        devices=devices,
        latest_nodes=[{"ieee_address": "0xa1"}, {"ieee_address": "0xr1"}],
        latest_links=[_link("0xr1", "0xa1")],
        history=history,
    )
    cards = [c for c in result["investigations"] if c["type"] == "recent_missing_cluster"]
    assert len(cards) == 1
    card = cards[0]
    assert card["primary_device_ieee"] == "0xa1"
    assert card["score"] >= RECENT_MISSING_EDGE_WEIGHT * RECENT_MISSING_CLUSTER_MIN_EDGES
    assert "not present in the latest usable snapshot" in card["summary"]
    assert any("does not prove a failure" in text for text in [card["why_it_matters"]])
    assert "hist-neighbor-0xa1|0xr1" in card["edge_ids"]
    assert card["created_from_evidence_classes"] == ["historical_neighbor"]


def test_fewer_missing_edges_than_threshold_creates_no_cluster():
    history = {
        "historical_neighbors": [
            _missing_edge("0xa1", "0xr1", last_seen=NOW - timedelta(hours=3)),
            _missing_edge("0xa1", "0xr2", last_seen=NOW - timedelta(hours=4)),
        ],
        "historical_routes": [],
    }
    result = _build(
        devices=[_device("0xa1")],
        latest_nodes=[{"ieee_address": "0xa1"}],
        latest_links=[],
        history=history,
    )
    assert not [
        c for c in result["investigations"] if c["type"] == "recent_missing_cluster"
    ]


def test_passive_group_from_passive_hints():
    hints = [
        _passive_hint("0xa1", "0xa2"),
        _passive_hint("0xa2", "0xa3"),
    ]
    result = _build(devices=[_device("0xa1"), _device("0xa2"), _device("0xa3")],
                    passive_hints=hints)
    cards = [c for c in result["investigations"] if c["type"] == "passive_instability_group"]
    assert len(cards) == 1
    card = cards[0]
    assert set(card["device_ieees"]) == {"0xa1", "0xa2", "0xa3"}
    assert card["edge_ids"] == sorted(
        ["passive-hint-0xa1|0xa2", "passive-hint-0xa2|0xa3"]
    )
    assert "This is not topology evidence" in card["why_it_matters"]
    assert any("not topology evidence" in item for item in card["limitations"])


def test_single_low_confidence_hint_does_not_create_group():
    result = _build(
        devices=[_device("0xa1"), _device("0xa2")],
        passive_hints=[_passive_hint("0xa1", "0xa2", confidence="low")],
    )
    assert not [
        c for c in result["investigations"] if c["type"] == "passive_instability_group"
    ]


def test_single_medium_confidence_hint_creates_group():
    result = _build(
        devices=[_device("0xa1"), _device("0xa2")],
        passive_hints=[_passive_hint("0xa1", "0xa2", confidence="medium")],
    )
    cards = [c for c in result["investigations"] if c["type"] == "passive_instability_group"]
    assert len(cards) == 1


def test_topology_corroboration_raises_score_but_cannot_create_cards():
    # Topology-only input (no issues, no missing edges, no hints) produces no
    # issue/missing/passive cards — corroboration can only raise scores.
    devices = [_device("0xr1", device_type="Router"), _device("0xa1"), _device("0xb1")]
    result = _build(
        devices=devices,
        latest_nodes=[{"ieee_address": d.ieee_address} for d in devices],
        latest_links=[_link("0xr1", "0xa1"), _link("0xr1", "0xb1")],
    )
    types = {card["type"] for card in result["investigations"]}
    assert "issue_cluster" not in types
    assert "passive_instability_group" not in types
    assert "recent_missing_cluster" not in types

    # The corroboration rule raises the score of a passive group.
    base = _build(
        devices=[_device("0xa1"), _device("0xa2")],
        passive_hints=[_passive_hint("0xa1", "0xa2", confidence="medium")],
    )
    corroborated = _build(
        devices=[_device("0xa1"), _device("0xa2")],
        passive_hints=[
            _passive_hint(
                "0xa1",
                "0xa2",
                confidence="medium",
                rules=["shared_instability_window", "topology_neighbourhood_corroboration"],
            )
        ],
    )
    base_card = base["investigations"][0]
    corroborated_card = corroborated["investigations"][0]
    assert corroborated_card["score"] == base_card["score"] + TOPOLOGY_CORROBORATION_WEIGHT


def test_router_review_uses_observed_neighbourhood_wording():
    neighbours = [f"0xn{i}" for i in range(ROUTER_REVIEW_MIN_LINKS)]
    devices = [_device("0xr1", device_type="Router", name="Kitchen router")]
    devices += [
        _device(
            ieee,
            availability="offline" if i < ROUTER_REVIEW_MIN_ISSUE_NEIGHBOURS else "online",
        )
        for i, ieee in enumerate(neighbours)
    ]
    links = [_link("0xr1", ieee) for ieee in neighbours]
    result = _build(
        devices=devices,
        latest_nodes=[{"ieee_address": d.ieee_address} for d in devices],
        latest_links=links,
    )
    cards = [
        c for c in result["investigations"] if c["type"] == "router_neighbourhood_review"
    ]
    assert len(cards) == 1
    card = cards[0]
    assert card["primary_device_ieee"] == "0xr1"
    assert "observed neighbour" in card["summary"]
    text = json.dumps(card).lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in text, phrase
    assert "not a claim that this router is responsible" in card["why_it_matters"]


def test_diagnostics_limited_group_handles_limited_evidence_safely():
    missing = [
        _device(f"0xm{i}", power_source="Battery")
        for i in range(DIAGNOSTICS_LIMITED_MIN_DEVICES)
    ]
    devices = [_device("0xr1", device_type="Router"), *missing]
    result = _build(
        devices=devices,
        latest_nodes=[{"ieee_address": "0xr1"}],
        latest_links=[],
    )
    cards = [
        c for c in result["investigations"] if c["type"] == "diagnostics_limited_group"
    ]
    assert len(cards) == 1
    card = cards[0]
    assert card["priority"] == PRIORITY_CONTEXT_ONLY
    assert "does not prove a fault" in card["why_it_matters"]
    assert card["edge_ids"] == []

    # A limited latest layout means absence is not meaningful: no card at all.
    limited = _build(devices=devices, latest_nodes=[], latest_links=[])
    assert not [
        c for c in limited["investigations"] if c["type"] == "diagnostics_limited_group"
    ]


def test_ranking_and_ties_are_deterministic():
    devices = [
        _device("0xr1", device_type="Router"),
        _device("0xa1", availability="offline"),
        _device("0xa2", availability="offline"),
    ]
    links = [_link("0xr1", "0xa1"), _link("0xr1", "0xa2")]
    history = {
        "historical_neighbors": [
            _missing_edge("0xa1", "0xr2", last_seen=NOW - timedelta(hours=3)),
            _missing_edge("0xa1", "0xr3", last_seen=NOW - timedelta(hours=4)),
            _missing_edge("0xa1", "0xr4", last_seen=NOW - timedelta(hours=5)),
        ],
        "historical_routes": [],
    }
    kwargs = dict(
        devices=devices,
        latest_nodes=[{"ieee_address": d.ieee_address} for d in devices],
        latest_links=links,
        history=history,
        passive_hints=[_passive_hint("0xa1", "0xa2", confidence="medium")],
    )
    first = _build(**kwargs)
    second = _build(**kwargs)
    assert [c["id"] for c in first["investigations"]] == [
        c["id"] for c in second["investigations"]
    ]
    scores = [c["score"] for c in first["investigations"]]
    assert scores == sorted(scores, reverse=True)

    # Two identical-score missing clusters tie-break on card id.
    tie_history = {
        "historical_neighbors": [
            _missing_edge("0xz9", "0xp1", last_seen=NOW - timedelta(hours=3)),
            _missing_edge("0xz9", "0xp2", last_seen=NOW - timedelta(hours=3)),
            _missing_edge("0xz9", "0xp3", last_seen=NOW - timedelta(hours=3)),
            _missing_edge("0xa0", "0xp1", last_seen=NOW - timedelta(hours=3)),
            _missing_edge("0xa0", "0xp2", last_seen=NOW - timedelta(hours=3)),
            _missing_edge("0xa0", "0xp3", last_seen=NOW - timedelta(hours=3)),
        ],
        "historical_routes": [],
    }
    tie = _build(
        devices=[_device("0xz9"), _device("0xa0")],
        latest_nodes=[{"ieee_address": "0xz9"}, {"ieee_address": "0xa0"}],
        latest_links=[],
        history=tie_history,
    )
    missing_cards = [
        c for c in tie["investigations"] if c["type"] == "recent_missing_cluster"
    ]
    same_score = [c for c in missing_cards if c["primary_device_ieee"] in {"0xz9", "0xa0"}]
    assert [c["id"] for c in same_score] == sorted(c["id"] for c in same_score)


def test_every_card_includes_limitations_and_supporting_evidence():
    devices = [
        _device("0xr1", device_type="Router"),
        _device("0xa1", availability="offline"),
        _device("0xa2", availability="offline"),
        *[_device(f"0xm{i}") for i in range(DIAGNOSTICS_LIMITED_MIN_DEVICES)],
    ]
    history = {
        "historical_neighbors": [
            _missing_edge("0xa1", "0xr2", last_seen=NOW - timedelta(hours=3)),
            _missing_edge("0xa1", "0xr3", last_seen=NOW - timedelta(hours=4)),
            _missing_edge("0xa1", "0xr4", last_seen=NOW - timedelta(hours=5)),
        ],
        "historical_routes": [],
    }
    result = _build(
        devices=devices,
        latest_nodes=[
            {"ieee_address": "0xr1"},
            {"ieee_address": "0xa1"},
            {"ieee_address": "0xa2"},
        ],
        latest_links=[_link("0xr1", "0xa1"), _link("0xr1", "0xa2")],
        history=history,
        passive_hints=[_passive_hint("0xa1", "0xa2", confidence="medium")],
    )
    assert result["investigations"]
    for card in result["investigations"]:
        assert GENERIC_INVESTIGATION_LIMITATION in card["limitations"]
        assert card["supporting_evidence"]
        assert card["priority"] in {"Review first", "Worth checking", "Lower priority"}


def test_cards_never_contain_forbidden_wording():
    devices = [
        _device("0xr1", device_type="Router"),
        _device("0xa1", availability="offline"),
        _device("0xa2", availability="offline"),
        *[_device(f"0xm{i}", power_source="Battery") for i in range(4)],
    ]
    history = {
        "historical_neighbors": [
            _missing_edge("0xa1", "0xr2", last_seen=NOW - timedelta(hours=3)),
            _missing_edge("0xa1", "0xr3", last_seen=NOW - timedelta(hours=4)),
            _missing_edge("0xa1", "0xr4", last_seen=NOW - timedelta(hours=5)),
        ],
        "historical_routes": [],
    }
    result = _build(
        devices=devices,
        latest_nodes=[
            {"ieee_address": "0xr1"},
            {"ieee_address": "0xa1"},
            {"ieee_address": "0xa2"},
        ],
        latest_links=[_link("0xr1", "0xa1"), _link("0xr1", "0xa2")],
        history=history,
        passive_hints=[_passive_hint("0xa1", "0xa2", confidence="high")],
    )
    text = json.dumps(result).lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in text, phrase


def test_cards_are_capped_at_max():
    # Many independent missing-link clusters, each qualifying for a card.
    edges = []
    for i in range(MAX_INVESTIGATION_CARDS + 4):
        device = f"0xd{i:02d}"
        edges.extend(
            _missing_edge(device, f"0xp{i:02d}{j}", last_seen=NOW - timedelta(hours=3))
            for j in range(RECENT_MISSING_CLUSTER_MIN_EDGES)
        )
    result = _build(
        devices=[],
        latest_nodes=[{"ieee_address": "0xr1"}],
        latest_links=[],
        history={"historical_neighbors": edges, "historical_routes": []},
    )
    assert result["available_count"] > MAX_INVESTIGATION_CARDS
    assert len(result["investigations"]) == MAX_INVESTIGATION_CARDS


def test_empty_state_when_no_patterns_exist():
    result = _build(
        devices=[_device("0xa1"), _device("0xr1", device_type="Router")],
        latest_nodes=[{"ieee_address": "0xa1"}, {"ieee_address": "0xr1"}],
        latest_links=[_link("0xr1", "0xa1")],
    )
    assert result["available_count"] == 0
    assert result["investigations"] == []


def _missing_cluster_for(result: dict, device: str) -> dict:
    cards = [
        c
        for c in result["investigations"]
        if c["type"] == "recent_missing_cluster" and c["primary_device_ieee"] == device
    ]
    assert len(cards) == 1
    return cards[0]


def _cluster_history(device: str = "0xa1") -> dict:
    return {
        "historical_neighbors": [
            _missing_edge(device, "0xr2", last_seen=NOW - timedelta(hours=3)),
            _missing_edge(device, "0xr3", last_seen=NOW - timedelta(hours=4)),
            _missing_edge(device, "0xr4", last_seen=NOW - timedelta(hours=5)),
        ],
        "historical_routes": [],
    }


def test_low_battery_becomes_a_fact_and_the_first_suggestion():
    result = _build(
        devices=[_device("0xa1", name="Bedroom sensor", battery=LOW_BATTERY_PERCENT - 5)],
        latest_nodes=[{"ieee_address": "0xa1"}],
        latest_links=[],
        history=_cluster_history(),
    )
    card = _missing_cluster_for(result, "0xa1")
    assert any("battery level is 15%" in fact for fact in card["supporting_evidence"])
    assert card["suggested_next_steps"][0] == (
        "Check or replace the battery in Bedroom sensor first — it last reported 15%."
    )


def test_healthy_battery_is_not_mentioned():
    result = _build(
        devices=[_device("0xa1", battery=90)],
        latest_nodes=[{"ieee_address": "0xa1"}],
        latest_links=[],
        history=_cluster_history(),
    )
    card = _missing_cluster_for(result, "0xa1")
    text = json.dumps(card)
    assert "battery" not in text.lower() or "Check battery level if available" in text


def test_unknown_values_never_become_claims():
    # No battery, no last_seen, unknown availability, no LQI: no tailored
    # facts appear — unknown is never presented as a recorded value.
    result = _build(
        devices=[_device("0xa1", availability="unknown")],
        latest_nodes=[{"ieee_address": "0xa1"}],
        latest_links=[],
        history=_cluster_history(),
    )
    card = _missing_cluster_for(result, "0xa1")
    text = json.dumps(card).lower()
    assert "battery level is" not in text
    assert "currently reported offline" not in text
    assert "nothing has been heard from" not in text
    assert "weak (lqi" not in text


def test_repeated_offline_events_become_a_fact():
    events = [
        (NOW - timedelta(days=2)).isoformat(),
        (NOW - timedelta(hours=6)).isoformat(),
    ]
    assert len(events) >= REPEATED_OFFLINE_MIN_COUNT
    result = _build(
        devices=[_device("0xa1", name="Hall plug")],
        latest_nodes=[{"ieee_address": "0xa1"}],
        latest_links=[],
        history=_cluster_history(),
        offline_events={"0xa1": events},
    )
    card = _missing_cluster_for(result, "0xa1")
    assert any(
        "Hall plug went offline 2 times in the last 7 days" in fact
        for fact in card["supporting_evidence"]
    )
    assert any("availability history" in step for step in card["suggested_next_steps"])


def test_stale_last_seen_becomes_a_fact_with_timestamp():
    stale = (NOW - timedelta(hours=STALE_LAST_SEEN_HOURS + 10)).isoformat()
    result = _build(
        devices=[_device("0xa1", name="Porch sensor", last_seen=stale)],
        latest_nodes=[{"ieee_address": "0xa1"}],
        latest_links=[],
        history=_cluster_history(),
    )
    card = _missing_cluster_for(result, "0xa1")
    assert any(
        fact.startswith("Nothing has been heard from Porch sensor since")
        for fact in card["supporting_evidence"]
    )
    # A recently seen device gets no such fact.
    fresh = _build(
        devices=[_device("0xa1", last_seen=(NOW - timedelta(hours=1)).isoformat())],
        latest_nodes=[{"ieee_address": "0xa1"}],
        latest_links=[],
        history=_cluster_history(),
    )
    fresh_card = _missing_cluster_for(fresh, "0xa1")
    assert not any(
        "Nothing has been heard from" in fact for fact in fresh_card["supporting_evidence"]
    )


def test_weak_link_lqi_becomes_a_fact():
    result = _build(
        devices=[_device("0xa1", name="Garage sensor"), _device("0xr1", device_type="Router")],
        latest_nodes=[{"ieee_address": "0xa1"}, {"ieee_address": "0xr1"}],
        latest_links=[_link("0xr1", "0xa1", lqi=WEAK_LINK_LQI - 20)],
        history=_cluster_history(),
    )
    card = _missing_cluster_for(result, "0xa1")
    assert any(
        "strongest observed link in the latest snapshot is weak (LQI 30)" in fact
        for fact in card["supporting_evidence"]
    )
    assert any("placement or sources of interference" in s for s in card["suggested_next_steps"])


def test_offline_device_gets_power_check_suggestion_on_issue_cluster():
    devices = [
        _device("0xr1", device_type="Router", name="Hall router"),
        _device("0xa1", name="Left blind", availability="offline"),
        _device("0xa2", name="Right blind", availability="offline"),
    ]
    links = [_link("0xr1", "0xa1"), _link("0xr1", "0xa2")]
    result = _build(
        devices=devices,
        latest_nodes=[{"ieee_address": d.ieee_address} for d in devices],
        latest_links=links,
    )
    cards = [c for c in result["investigations"] if c["type"] == "issue_cluster"]
    assert len(cards) == 1
    card = cards[0]
    assert any("Left blind is currently reported offline." in f for f in card["supporting_evidence"])
    assert any("Check power to Left blind" in s for s in card["suggested_next_steps"])
    assert any("Check power to Right blind" in s for s in card["suggested_next_steps"])
    assert len(card["suggested_next_steps"]) <= MAX_SUGGESTED_NEXT_STEPS


def test_tailored_wording_stays_within_guardrails():
    stale = (NOW - timedelta(hours=STALE_LAST_SEEN_HOURS + 5)).isoformat()
    result = _build(
        devices=[
            _device(
                "0xa1",
                name="Bedroom sensor",
                battery=5,
                availability="offline",
                last_seen=stale,
            ),
            _device("0xr1", device_type="Router"),
        ],
        latest_nodes=[{"ieee_address": "0xa1"}, {"ieee_address": "0xr1"}],
        latest_links=[_link("0xr1", "0xa1", lqi=10)],
        history=_cluster_history(),
        offline_events={"0xa1": [(NOW - timedelta(hours=i)).isoformat() for i in (30, 6)]},
    )
    text = json.dumps(result).lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in text, phrase


def test_evidence_graph_api_includes_investigations(topology_client: TestClient):
    from zigbeelens.app.context import get_context
    from zigbeelens.topology.parser import parse_networkmap_payload

    ctx = get_context()
    now = datetime.now(timezone.utc)
    ctx.repo.create_topology_snapshot(
        snapshot_id="snap-latest",
        network_id="home",
        requested_by="test",
        status="pending",
        warning_acknowledged=True,
    )
    parsed = parse_networkmap_payload(
        {
            "nodes": {"0x01": {"type": "Coordinator"}, "0x02": {"type": "Router"}},
            "links": [{"source": "0x02", "target": "0x01", "linkquality": 120}],
        }
    )
    ctx.repo.store_topology_parsed("snap-latest", "home", parsed, status="complete")
    ctx.repo.db.conn.execute(
        "UPDATE topology_snapshots SET captured_at = ? WHERE snapshot_id = ?",
        ((now - timedelta(hours=1)).isoformat(), "snap-latest"),
    )
    ctx.repo.db.conn.commit()

    res = topology_client.get("/api/topology/home/evidence-graph")
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body["investigations"], list)
    assert body["investigation_counts"]["returned"] == len(body["investigations"])
    assert body["investigation_counts"]["available"] >= body["investigation_counts"][
        "returned"
    ]
    text = json.dumps(body["investigations"]).lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in text, phrase
