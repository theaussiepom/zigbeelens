"""Problem-first investigation card tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from zigbeelens.decisions.availability_event_groups import (
    SHARED_EVENT_MIN_DEVICES,
    SharedAvailabilityEvent,
)
from zigbeelens.decisions.model_pattern import (
    MODEL_PATTERN_MIN_AFFECTED_COUNT,
    MODEL_PATTERN_MIN_GROUP_SIZE,
    ObservedModelPattern,
)
from zigbeelens.storage.repository import DeviceRow
from zigbeelens.topology.investigations import (
    DIAGNOSTICS_LIMITED_MIN_DEVICES,
    GENERIC_INVESTIGATION_LIMITATION,
    ISSUE_CLUSTER_MIN_DEVICES,
    ISSUE_DEVICE_WEIGHT,
    LOW_BATTERY_PERCENT,
    MAX_DEVICES_PER_CARD,
    MAX_INVESTIGATION_CARDS,
    MAX_SUGGESTED_NEXT_STEPS,
    PRIORITY_CONTEXT_ONLY,
    RECENT_MISSING_CLUSTER_MIN_EDGES,
    RECENT_MISSING_EDGE_WEIGHT,
    REPEATED_OFFLINE_MIN_COUNT,
    ROUTER_REVIEW_MIN_ISSUE_NEIGHBOURS,
    ROUTER_REVIEW_MIN_LINKS,
    ROUTER_AREA_LIMITATION,
    MODEL_PATTERN_LIMITATION,
    SHARED_AVAILABILITY_EVENT_BASE_WEIGHT,
    SHARED_AVAILABILITY_EVENT_LIMITATION,
    STALE_LAST_SEEN_HOURS,
    TOPOLOGY_CORROBORATION_WEIGHT,
    UNAVAILABLE_DEVICE_WEIGHT,
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
    "within 5 minutes",
    "common cause",
    "network failure",
    "coordinator failure",
    "mqtt outage",
    "broker outage",
    "host restart caused",
    "power outage",
    "interference event",
    "shared route",
    "shared path",
]

ROUTER_AREA_FORBIDDEN_PHRASES = [
    *FORBIDDEN_PHRASES,
    "route through router",
    "common parent",
    "coverage area",
    "served by router",
    "router failure",
    "router caused",
]

MODEL_PATTERN_FORBIDDEN_PHRASES = [
    *FORBIDDEN_PHRASES,
    "bad manufacturer",
    "faulty manufacturer",
    "manufacturer is to blame",
    "defective model",
    "model is bad",
    "model failed",
]


def _router_area_claim_text(card: dict) -> str:
    return json.dumps(
        {
            "title": card["title"],
            "summary": card["summary"],
            "why_it_matters": card["why_it_matters"],
            "supporting_evidence": card["supporting_evidence"],
            "suggested_next_steps": card["suggested_next_steps"],
        }
    ).lower()


def _router_review_card(result: dict) -> dict | None:
    cards = [c for c in result["investigations"] if c["type"] == "router_neighbourhood_review"]
    return cards[0] if cards else None


def _device(
    ieee: str,
    *,
    device_type: str = "EndDevice",
    availability: str = "online",
    power_source: str = "Mains",
    name: str | None = None,
    battery: int | None = None,
    last_seen: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
) -> DeviceRow:
    return DeviceRow(
        network_id="home",
        ieee_address=ieee,
        friendly_name=name or f"Device {ieee}",
        device_type=device_type,
        power_source=power_source,
        manufacturer=manufacturer,
        model=model,
        interview_state="successful",
        availability=availability,
        battery=battery,
        last_seen=last_seen,
    )


def _link(source: str, target: str, *, lqi: int = 100, route_count: int | None = None) -> dict:
    return {
        "source_ieee": source,
        "target_ieee": target,
        "linkquality": lqi,
        "source_type": None,
        "target_type": None,
        "route_count": route_count,
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


def _shared_availability_event(
    *,
    device_count: int = SHARED_EVENT_MIN_DEVICES,
    duration_minutes: int = 4,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    event_id: str = "shared-availability-test",
) -> SharedAvailabilityEvent:
    started = started_at or NOW - timedelta(hours=2)
    ended = (
        ended_at
        if ended_at is not None
        else started + timedelta(minutes=duration_minutes)
    )
    devices = [f"0xd{i:02d}" for i in range(device_count)]
    return SharedAvailabilityEvent(
        event_id=event_id,
        started_at=started,
        ended_at=ended,
        device_count=device_count,
        device_ieees=devices,
        duration_minutes=duration_minutes,
    )


def _model_pattern(
    *,
    group_size: int = MODEL_PATTERN_MIN_GROUP_SIZE,
    affected_count: int = MODEL_PATTERN_MIN_AFFECTED_COUNT,
    manufacturer: str | None = "IKEA",
    model: str = "TS011F",
    pattern_id: str = "model-pattern-test",
) -> ObservedModelPattern:
    members = [f"0xm{i:02d}" for i in range(group_size)]
    affected = members[:affected_count]
    return ObservedModelPattern(
        pattern_id=pattern_id,
        manufacturer=manufacturer,
        model=model,
        group_size=group_size,
        affected_count=affected_count,
        member_ieees=members,
        affected_ieees=affected,
        params={
            "group_size": group_size,
            "affected_count": affected_count,
            "lookback_days": 7,
            "min_group_size": MODEL_PATTERN_MIN_GROUP_SIZE,
            "min_affected_count": MODEL_PATTERN_MIN_AFFECTED_COUNT,
            "signal": "offline_in_lookback",
        },
    )


def _build(**overrides) -> dict:
    defaults = dict(
        devices=[],
        latest_nodes=[],
        latest_links=[],
        latest_captured_at=(NOW - timedelta(hours=1)).isoformat(),
        history=_empty_history(),
        passive_hints=[],
        shared_availability_events=[],
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


def test_router_review_uses_observed_router_area_wording():
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
    assert card["title"] == "Review observed router area: Kitchen router"
    assert "2 devices needing attention" in card["summary"]
    assert "observed router area" in card["summary"]
    assert "latest topology snapshot" in json.dumps(card["supporting_evidence"]).lower()
    text = _router_area_claim_text(card)
    for phrase in ROUTER_AREA_FORBIDDEN_PHRASES:
        assert phrase not in text, phrase
    assert ROUTER_AREA_LIMITATION in card["limitations"]
    assert card["action_group"] == "review_observed_router_area"


def test_router_only_issue_path_uses_router_oriented_copy():
    neighbours = [f"0xn{i}" for i in range(ROUTER_REVIEW_MIN_LINKS)]
    devices = [
        _device(
            "0xr1",
            device_type="Router",
            name="Kitchen router",
            availability="offline",
        )
    ]
    devices += [_device(ieee) for ieee in neighbours]
    devices.append(_device("0xextra"))
    links = [_link("0xr1", ieee) for ieee in neighbours]
    history = {
        "historical_neighbors": [
            {
                "source_ieee": "0xr1",
                "target_ieee": "0xextra",
                "evidence_class": "historical_neighbor",
                "last_seen_at": NOW.isoformat(),
            }
        ],
        "historical_routes": [],
    }
    result = _build(
        devices=devices,
        latest_nodes=[{"ieee_address": d.ieee_address} for d in devices],
        latest_links=links,
        history=history,
    )
    card = _router_review_card(result)
    assert card is not None
    assert card["primary_device_ieee"] == "0xr1"
    assert card["primary_neighbourhood_ieee"] == "0xr1"
    assert "0 devices" not in card["summary"].lower()
    assert "currently needs attention" in card["summary"]
    assert "Kitchen router currently needs attention" in card["summary"]
    assert "several devices needing attention" not in card["why_it_matters"].lower()
    assert "The router itself currently needs attention." in card["supporting_evidence"]
    assert not any(
        "currently need attention" in line and "router itself" not in line
        for line in card["supporting_evidence"]
        if "device" in line and "in this observed area" in line
    )
    expected_score = (
        TOPOLOGY_CORROBORATION_WEIGHT + UNAVAILABLE_DEVICE_WEIGHT + 1
    )
    assert card["score"] == expected_score
    assert ROUTER_AREA_LIMITATION in card["limitations"]
    assert card["action_group"] == "review_observed_router_area"
    text = _router_area_claim_text(card)
    for phrase in ROUTER_AREA_FORBIDDEN_PHRASES:
        assert phrase not in text, phrase


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
    assert card["action_group"] == "improve_data_coverage"
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


def test_investigation_cards_include_action_groups():
    devices = [
        _device("0xr1", device_type="Router", name="Hall router"),
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
    result = _build(
        devices=devices,
        latest_nodes=[{"ieee_address": d.ieee_address} for d in devices],
        latest_links=links,
        history=history,
    )
    by_type = {card["type"]: card for card in result["investigations"]}
    assert by_type["issue_cluster"]["action_group"] == "investigate_shared_event"
    assert by_type["recent_missing_cluster"]["action_group"] == "check_power_reporting"


def test_low_priority_passive_group_maps_to_watch_only():
    result = _build(
        devices=[_device("0xa1"), _device("0xa2"), _device("0xa3")],
        passive_hints=[
            _passive_hint("0xa1", "0xa2", confidence="low"),
            _passive_hint("0xa2", "0xa3", confidence="low"),
        ],
    )
    cards = [c for c in result["investigations"] if c["type"] == "passive_instability_group"]
    assert len(cards) == 1
    assert cards[0]["priority"] == PRIORITY_CONTEXT_ONLY
    assert cards[0]["action_group"] == "watch_only"


def test_high_confidence_passive_group_investigates_shared_event():
    result = _build(
        devices=[_device("0xa1"), _device("0xa2"), _device("0xa3")],
        passive_hints=[
            _passive_hint("0xa1", "0xa2", confidence="high"),
            _passive_hint("0xa2", "0xa3", confidence="high"),
        ],
    )
    cards = [c for c in result["investigations"] if c["type"] == "passive_instability_group"]
    assert len(cards) == 1
    assert cards[0]["action_group"] == "investigate_shared_event"
    assert cards[0]["priority"] != PRIORITY_CONTEXT_ONLY


def test_shared_availability_event_produces_one_card():
    event = _shared_availability_event()
    result = _build(shared_availability_events=[event])
    cards = [c for c in result["investigations"] if c["type"] == "shared_availability_event"]
    assert len(cards) == 1
    card = cards[0]
    assert card["id"] == event.event_id
    assert card["action_group"] == "investigate_shared_event"
    assert card["edge_ids"] == []
    assert card["primary_device_ieee"] is None
    assert card["primary_neighbourhood_ieee"] is None
    assert card["title"] == "Several devices went offline around the same time"
    assert str(SHARED_EVENT_MIN_DEVICES) in card["summary"]
    assert SHARED_AVAILABILITY_EVENT_LIMITATION in card["limitations"]


def test_shared_availability_event_does_not_create_pairwise_cards():
    event = _shared_availability_event(device_count=SHARED_EVENT_MIN_DEVICES)
    result = _build(shared_availability_events=[event])
    assert len([c for c in result["investigations"] if c["type"] == "shared_availability_event"]) == 1
    assert not [c for c in result["investigations"] if c["type"] == "passive_instability_group"]
    card = next(c for c in result["investigations"] if c["type"] == "shared_availability_event")
    assert card["edge_ids"] == []
    assert len(card["device_ieees"]) == SHARED_EVENT_MIN_DEVICES


def test_shared_availability_event_respects_device_presentation_cap():
    device_count = MAX_DEVICES_PER_CARD + 3
    event = _shared_availability_event(device_count=device_count, duration_minutes=12)
    result = _build(shared_availability_events=[event])
    card = next(c for c in result["investigations"] if c["type"] == "shared_availability_event")
    assert len(card["device_ieees"]) == MAX_DEVICES_PER_CARD
    assert str(device_count) in card["summary"]
    assert "12 minutes" in card["summary"]


def test_shared_availability_event_uses_actual_duration_not_cluster_gap():
    started = NOW - timedelta(hours=3)
    ended = started + timedelta(minutes=22)
    event = _shared_availability_event(
        device_count=SHARED_EVENT_MIN_DEVICES,
        duration_minutes=22,
        started_at=started,
        ended_at=ended,
    )
    result = _build(shared_availability_events=[event])
    card = next(c for c in result["investigations"] if c["type"] == "shared_availability_event")
    assert "22 minutes" in card["summary"]
    assert "within 5 minutes" not in card["summary"].lower()
    assert "within 5 minutes" not in json.dumps(card).lower()


def test_shared_availability_event_sub_minute_duration_uses_natural_wording():
    started = NOW - timedelta(hours=1)
    event = _shared_availability_event(
        device_count=SHARED_EVENT_MIN_DEVICES,
        duration_minutes=0,
        started_at=started,
        ended_at=started,
    )
    result = _build(shared_availability_events=[event])
    card = next(c for c in result["investigations"] if c["type"] == "shared_availability_event")
    assert card["summary"] == (
        f"{SHARED_EVENT_MIN_DEVICES} devices went offline around the same time."
    )
    assert "0 minutes" not in card["summary"]


def test_shared_availability_event_conservative_scoring():
    event = _shared_availability_event()
    result = _build(shared_availability_events=[event])
    card = next(c for c in result["investigations"] if c["type"] == "shared_availability_event")
    assert card["score"] == SHARED_AVAILABILITY_EVENT_BASE_WEIGHT + 1
    assert card["priority"] == "Worth checking"


def test_shared_availability_event_has_no_forbidden_claims():
    event = _shared_availability_event(device_count=SHARED_EVENT_MIN_DEVICES, duration_minutes=18)
    result = _build(shared_availability_events=[event])
    card = next(c for c in result["investigations"] if c["type"] == "shared_availability_event")
    claim_text = json.dumps(
        {
            "title": card["title"],
            "summary": card["summary"],
            "why_it_matters": card["why_it_matters"],
            "supporting_evidence": card["supporting_evidence"],
            "suggested_next_steps": card["suggested_next_steps"],
        }
    ).lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in claim_text, phrase


def test_shared_availability_event_skips_tailored_device_evidence():
    devices = [
        _device(f"0xd{i:02d}", battery=LOW_BATTERY_PERCENT - 1)
        for i in range(SHARED_EVENT_MIN_DEVICES)
    ]
    event = _shared_availability_event(device_count=SHARED_EVENT_MIN_DEVICES)
    result = _build(
        devices=devices,
        shared_availability_events=[event],
        offline_events={devices[0].ieee_address: [NOW.isoformat()]},
    )
    card = next(c for c in result["investigations"] if c["type"] == "shared_availability_event")
    text = json.dumps(card).lower()
    assert "battery" not in text


def test_passive_pairwise_hints_unchanged_when_shared_events_present():
    passive_result = _build(
        devices=[_device("0xa1"), _device("0xa2"), _device("0xa3")],
        passive_hints=[
            _passive_hint("0xa1", "0xa2", confidence="high"),
            _passive_hint("0xa2", "0xa3", confidence="high"),
        ],
    )
    combined_result = _build(
        devices=[_device("0xa1"), _device("0xa2"), _device("0xa3")],
        passive_hints=[
            _passive_hint("0xa1", "0xa2", confidence="high"),
            _passive_hint("0xa2", "0xa3", confidence="high"),
        ],
        shared_availability_events=[_shared_availability_event()],
    )
    passive_cards = [
        c for c in passive_result["investigations"] if c["type"] == "passive_instability_group"
    ]
    combined_passive = [
        c for c in combined_result["investigations"] if c["type"] == "passive_instability_group"
    ]
    assert passive_cards == combined_passive


def test_model_pattern_produces_one_review_card():
    pattern = _model_pattern()
    result = _build(observed_model_patterns=[pattern])
    cards = [c for c in result["investigations"] if c["type"] == "model_pattern_review"]
    assert len(cards) == 1
    card = cards[0]
    assert card["title"] == "Review model pattern: IKEA TS011F"
    assert (
        card["summary"]
        == "3 of 5 devices with this model have gone offline in the last 7 days."
    )
    assert card["action_group"] == "review_model_pattern"
    assert MODEL_PATTERN_LIMITATION in card["limitations"]


def test_model_pattern_has_no_manufacturer_blame_phrases():
    pattern = _model_pattern()
    result = _build(observed_model_patterns=[pattern])
    card = next(c for c in result["investigations"] if c["type"] == "model_pattern_review")
    text = json.dumps(card).lower()
    for phrase in MODEL_PATTERN_FORBIDDEN_PHRASES:
        assert phrase not in text


def test_model_pattern_skips_tailored_device_evidence():
    pattern = _model_pattern()
    devices = [
        _device(ieee, manufacturer="IKEA", model="TS011F", battery=LOW_BATTERY_PERCENT - 1)
        for ieee in pattern.affected_ieees
    ]
    result = _build(
        devices=devices,
        observed_model_patterns=[pattern],
        offline_events={devices[0].ieee_address: [NOW.isoformat()]},
    )
    card = next(c for c in result["investigations"] if c["type"] == "model_pattern_review")
    supporting = json.dumps(card["supporting_evidence"]).lower()
    assert "battery" not in supporting


def test_router_review_below_latest_threshold_does_not_qualify_without_multi_source():
    neighbours = [f"0xn{i}" for i in range(ROUTER_REVIEW_MIN_LINKS - 1)]
    devices = [_device("0xr1", device_type="Router")]
    devices += [
        _device(ieee, availability="offline" if i < 2 else "online")
        for i, ieee in enumerate(neighbours)
    ]
    links = [_link("0xr1", ieee) for ieee in neighbours]
    result = _build(
        devices=devices,
        latest_nodes=[{"ieee_address": d.ieee_address} for d in devices],
        latest_links=links,
    )
    assert _router_review_card(result) is None


def test_router_review_multi_source_qualifies_with_fewer_latest_links():
    devices = [
        _device("0xr1", device_type="Router", name="Hall router"),
        _device("0xa1", availability="offline"),
        _device("0xa2", availability="offline"),
        _device("0xa3"),
        _device("0xa4"),
    ]
    links = [_link("0xr1", ieee) for ieee in ("0xa1", "0xa2", "0xa3")]
    history = {
        "historical_neighbors": [
            {
                "source_ieee": "0xr1",
                "target_ieee": "0xa4",
                "evidence_class": "historical_neighbor",
                "last_seen_at": NOW.isoformat(),
            }
        ],
        "historical_routes": [],
    }
    result = _build(
        devices=devices,
        latest_nodes=[{"ieee_address": d.ieee_address} for d in devices],
        latest_links=links,
        history=history,
    )
    card = _router_review_card(result)
    assert card is not None
    assert "recent missing topology evidence" in json.dumps(card["supporting_evidence"]).lower()


def test_passive_hints_alone_do_not_qualify_router_review():
    devices = [
        _device("0xr1", device_type="Router"),
        _device("0xa1", availability="offline"),
        _device("0xa2", availability="offline"),
    ]
    result = _build(
        devices=devices,
        passive_hints=[
            _passive_hint("0xr1", "0xa1"),
            _passive_hint("0xr1", "0xa2"),
        ],
    )
    assert _router_review_card(result) is None


def test_topology_evidence_alone_does_not_create_current_issues():
    neighbours = [f"0xn{i}" for i in range(ROUTER_REVIEW_MIN_LINKS)]
    devices = [_device("0xr1", device_type="Router")]
    devices += [_device(ieee) for ieee in neighbours]
    links = [_link("0xr1", ieee) for ieee in neighbours]
    result = _build(
        devices=devices,
        latest_nodes=[{"ieee_address": d.ieee_address} for d in devices],
        latest_links=links,
    )
    assert _router_review_card(result) is None


def test_router_review_produces_one_card_per_observed_router_area():
    neighbours = [f"0xn{i}" for i in range(ROUTER_REVIEW_MIN_LINKS)]
    devices = [_device("0xr1", device_type="Router")]
    devices += [
        _device(ieee, availability="offline" if i < 2 else "online")
        for i, ieee in enumerate(neighbours)
    ]
    links = [_link("0xr1", ieee) for ieee in neighbours]
    result = _build(
        devices=devices,
        latest_nodes=[{"ieee_address": d.ieee_address} for d in devices],
        latest_links=links,
    )
    cards = [c for c in result["investigations"] if c["type"] == "router_neighbourhood_review"]
    assert len(cards) == 1


def test_router_review_route_hints_use_route_hint_wording():
    neighbours = [f"0xn{i}" for i in range(ROUTER_REVIEW_MIN_LINKS)]
    devices = [_device("0xr1", device_type="Router")]
    devices += [
        _device(ieee, availability="offline" if i < 2 else "online")
        for i, ieee in enumerate(neighbours)
    ]
    links = [
        _link("0xr1", ieee, route_count=2 if ieee == neighbours[0] else None)
        for ieee in neighbours
    ]
    result = _build(
        devices=devices,
        latest_nodes=[{"ieee_address": d.ieee_address} for d in devices],
        latest_links=links,
    )
    card = _router_review_card(result)
    assert card is not None
    evidence = json.dumps(card["supporting_evidence"]).lower()
    assert "route hints" in evidence
    assert "currently routed" not in evidence
    assert "current route" not in evidence


def test_router_review_device_ieees_prioritise_router_and_issue_devices():
    neighbours = [f"0xn{i}" for i in range(ROUTER_REVIEW_MIN_LINKS)]
    devices = [_device("0xr1", device_type="Router")]
    devices += [
        _device(ieee, availability="offline" if i < 2 else "online")
        for i, ieee in enumerate(neighbours)
    ]
    links = [_link("0xr1", ieee) for ieee in neighbours]
    passive_only = [f"0xp{i}" for i in range(MAX_DEVICES_PER_CARD)]
    devices += [_device(ieee) for ieee in passive_only]
    hints = [_passive_hint("0xr1", ieee) for ieee in passive_only]
    result = _build(
        devices=devices,
        latest_nodes=[{"ieee_address": d.ieee_address} for d in devices],
        latest_links=links,
        passive_hints=hints,
    )
    card = _router_review_card(result)
    assert card is not None
    assert card["device_ieees"][0] == "0xr1"
    assert card["device_ieees"][1] in {"0xn0", "0xn1"}
    assert not any(ieee.startswith("0xp") for ieee in card["device_ieees"][:3])


def test_router_review_skips_generic_tailored_member_evidence():
    neighbours = [f"0xn{i}" for i in range(ROUTER_REVIEW_MIN_LINKS)]
    devices = [_device("0xr1", device_type="Router")]
    devices += [
        _device(
            ieee,
            availability="offline" if i < 2 else "online",
            battery=LOW_BATTERY_PERCENT - 1 if i == 2 else None,
        )
        for i, ieee in enumerate(neighbours)
    ]
    links = [_link("0xr1", ieee) for ieee in neighbours]
    result = _build(
        devices=devices,
        latest_nodes=[{"ieee_address": d.ieee_address} for d in devices],
        latest_links=links,
    )
    card = _router_review_card(result)
    assert card is not None
    assert "battery" not in json.dumps(card).lower()


def test_router_review_edge_ids_reference_real_graph_schemes():
    neighbours = [f"0xn{i}" for i in range(ROUTER_REVIEW_MIN_LINKS)]
    devices = [_device("0xr1", device_type="Router")]
    devices += [
        _device(ieee, availability="offline" if i < 2 else "online")
        for i, ieee in enumerate(neighbours)
    ]
    links = [_link("0xr1", ieee) for ieee in neighbours]
    history = {
        "historical_neighbors": [
            {
                "source_ieee": "0xr1",
                "target_ieee": "0xn0",
                "evidence_class": "historical_neighbor",
                "last_seen_at": NOW.isoformat(),
            }
        ],
        "historical_routes": [],
    }
    result = _build(
        devices=devices,
        latest_nodes=[{"ieee_address": d.ieee_address} for d in devices],
        latest_links=links,
        history=history,
        passive_hints=[_passive_hint("0xr1", "0xn2")],
    )
    card = _router_review_card(result)
    assert card is not None
    assert any(edge.startswith("live-neighbor-") for edge in card["edge_ids"])
    assert all(not edge.startswith("ha-") for edge in card["edge_ids"])
