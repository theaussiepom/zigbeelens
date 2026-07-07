"""Passive-derived investigation hint tests.

Hints must come only from passive observations already stored, require
repeated co-instability, use topology strictly as corroboration, stay
conservative in confidence, respect caps and never produce route evidence
or parent/router wording.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.parser import parse_networkmap_payload
from zigbeelens.topology.passive_hints import (
    MAX_PASSIVE_HINTS_PER_NODE,
    MAX_PASSIVE_HINTS_TOTAL,
    PASSIVE_HINT_LIMITATIONS,
    PASSIVE_HINT_LOOKBACK_DAYS,
    PASSIVE_HINT_MIN_REPEATED_WINDOWS,
    aggregate_passive_hints,
)

NOW = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)

FORBIDDEN_WORDING = (
    "parent router",
    "child device",
    "current route",
    "currently routed",
    "actual path",
    "connected through",
    "caused by",
    "failed because",
    "broken link",
    "lost link",
    "same parent",
)


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "passive.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "passive.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    return repo


def _add_device(repo: Repository, ieee: str, *, device_type: str = "EndDevice") -> None:
    repo.upsert_device(
        network_id="home",
        ieee_address=ieee,
        friendly_name=f"Device {ieee}",
        device_type=device_type,
        power_source="Mains",
    )


def _offline_event(repo: Repository, ieee: str, at: datetime) -> None:
    repo.db.conn.execute(
        """
        INSERT INTO availability_changes (network_id, ieee_address, from_state, to_state, changed_at)
        VALUES ('home', ?, 'online', 'offline', ?)
        """,
        (ieee, at.isoformat()),
    )
    repo.db.conn.commit()


def _co_instability(repo: Repository, first: str, second: str, *, windows: int) -> None:
    """Record `windows` co-instability windows for a pair, one day apart."""
    for i in range(windows):
        base = NOW - timedelta(days=i + 1)
        _offline_event(repo, first, base)
        _offline_event(repo, second, base + timedelta(minutes=2))


def _store_snapshot(
    repo: Repository,
    snapshot_id: str,
    *,
    captured_at: datetime,
    links: list[dict],
    nodes: dict[str, dict],
) -> None:
    repo.create_topology_snapshot(
        snapshot_id=snapshot_id,
        network_id="home",
        requested_by="test",
        status="pending",
        warning_acknowledged=True,
    )
    parsed = parse_networkmap_payload({"nodes": nodes, "links": links})
    repo.store_topology_parsed(snapshot_id, "home", parsed, status="complete")
    repo.db.conn.execute(
        "UPDATE topology_snapshots SET captured_at = ? WHERE snapshot_id = ?",
        (captured_at.isoformat(), snapshot_id),
    )
    repo.db.conn.commit()


def _open_incident_for(repo: Repository, ieee: str) -> None:
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


def test_empty_state_when_no_passive_data(tmp_path: Path):
    repo = _repo(tmp_path)
    _add_device(repo, "0xa1")
    result = aggregate_passive_hints(repo, "home", now=NOW)
    assert result["available_count"] == 0
    assert result["hints"] == []
    assert result["window"]["days"] == PASSIVE_HINT_LOOKBACK_DAYS


def test_single_weak_observation_does_not_create_hint(tmp_path: Path):
    repo = _repo(tmp_path)
    _add_device(repo, "0xa1")
    _add_device(repo, "0xa2")
    # One co-instability window only: below the repeated-window threshold.
    _co_instability(repo, "0xa1", "0xa2", windows=PASSIVE_HINT_MIN_REPEATED_WINDOWS - 1)
    result = aggregate_passive_hints(repo, "home", now=NOW)
    assert result["hints"] == []


def test_repeated_co_instability_creates_low_hint(tmp_path: Path):
    repo = _repo(tmp_path)
    _add_device(repo, "0xa1")
    _add_device(repo, "0xa2")
    _co_instability(repo, "0xa1", "0xa2", windows=PASSIVE_HINT_MIN_REPEATED_WINDOWS)
    result = aggregate_passive_hints(repo, "home", now=NOW)
    assert result["available_count"] == 1
    hint = result["hints"][0]
    assert {hint["source_ieee"], hint["target_ieee"]} == {"0xa1", "0xa2"}
    assert hint["evidence_class"] == "passive_derived_association"
    assert hint["directional"] is False
    # Minimum threshold with no corroboration stays conservative: low.
    assert hint["confidence"] == "low"
    assert hint["observed_count"] == PASSIVE_HINT_MIN_REPEATED_WINDOWS
    assert "shared_instability_window" in hint["rules_matched"]
    assert hint["limitations"] == PASSIVE_HINT_LIMITATIONS


def test_topology_corroboration_raises_confidence_but_cannot_create_hint(tmp_path: Path):
    repo = _repo(tmp_path)
    for ieee in ("0xa1", "0xa2", "0xb1", "0xb2"):
        _add_device(repo, ieee)
    _add_device(repo, "0xr1", device_type="Router")
    # Both pairs share a router neighbourhood in a recent snapshot, but only
    # the a-pair has passive co-instability evidence.
    _store_snapshot(
        repo,
        "snap-1",
        captured_at=NOW - timedelta(days=1),
        nodes={
            "0xr1": {"type": "Router"},
            "0xa1": {"type": "EndDevice"},
            "0xa2": {"type": "EndDevice"},
            "0xb1": {"type": "EndDevice"},
            "0xb2": {"type": "EndDevice"},
        },
        links=[
            {"source": "0xa1", "target": "0xr1", "linkquality": 80},
            {"source": "0xa2", "target": "0xr1", "linkquality": 90},
            {"source": "0xb1", "target": "0xr1", "linkquality": 70},
            {"source": "0xb2", "target": "0xr1", "linkquality": 60},
        ],
    )
    _co_instability(repo, "0xa1", "0xa2", windows=PASSIVE_HINT_MIN_REPEATED_WINDOWS)

    result = aggregate_passive_hints(repo, "home", now=NOW)
    pairs = {frozenset((h["source_ieee"], h["target_ieee"])) for h in result["hints"]}
    # Topology alone never creates a hint: the b-pair has no passive signal.
    assert frozenset(("0xb1", "0xb2")) not in pairs
    hint = next(
        h for h in result["hints"] if {h["source_ieee"], h["target_ieee"]} == {"0xa1", "0xa2"}
    )
    assert hint["confidence"] == "medium"
    assert "topology_neighbourhood_corroboration" in hint["rules_matched"]


def test_high_confidence_needs_repeats_issue_and_corroboration(tmp_path: Path):
    repo = _repo(tmp_path)
    _add_device(repo, "0xa1")
    _add_device(repo, "0xa2")
    _add_device(repo, "0xr1", device_type="Router")
    _store_snapshot(
        repo,
        "snap-1",
        captured_at=NOW - timedelta(days=1),
        nodes={
            "0xr1": {"type": "Router"},
            "0xa1": {"type": "EndDevice"},
            "0xa2": {"type": "EndDevice"},
        },
        links=[
            {"source": "0xa1", "target": "0xr1", "linkquality": 80},
            {"source": "0xa2", "target": "0xr1", "linkquality": 90},
        ],
    )
    _open_incident_for(repo, "0xa1")
    # More than the minimum repeated windows.
    _co_instability(repo, "0xa1", "0xa2", windows=PASSIVE_HINT_MIN_REPEATED_WINDOWS + 2)

    result = aggregate_passive_hints(repo, "home", now=NOW)
    hint = result["hints"][0]
    assert hint["confidence"] == "high"
    assert hint["issue_related"] is True
    assert set(hint["rules_matched"]) == {
        "shared_instability_window",
        "topology_neighbourhood_corroboration",
        "current_issue_relevance",
    }


def test_issue_relevance_alone_does_not_reach_high(tmp_path: Path):
    repo = _repo(tmp_path)
    _add_device(repo, "0xa1")
    _add_device(repo, "0xa2")
    _open_incident_for(repo, "0xa1")
    _co_instability(repo, "0xa1", "0xa2", windows=PASSIVE_HINT_MIN_REPEATED_WINDOWS)
    result = aggregate_passive_hints(repo, "home", now=NOW)
    hint = result["hints"][0]
    # One passive rule at minimum threshold plus issue relevance, without
    # repetition or corroboration, must not be high confidence.
    assert hint["confidence"] == "low"
    assert hint["issue_related"] is True


def test_lookback_window_excludes_old_passive_events(tmp_path: Path):
    repo = _repo(tmp_path)
    _add_device(repo, "0xa1")
    _add_device(repo, "0xa2")
    old = NOW - timedelta(days=PASSIVE_HINT_LOOKBACK_DAYS + 5)
    for i in range(3):
        base = old - timedelta(days=i)
        _offline_event(repo, "0xa1", base)
        _offline_event(repo, "0xa2", base + timedelta(minutes=1))
    result = aggregate_passive_hints(repo, "home", now=NOW)
    assert result["hints"] == []


def test_events_outside_window_minutes_do_not_pair(tmp_path: Path):
    repo = _repo(tmp_path)
    _add_device(repo, "0xa1")
    _add_device(repo, "0xa2")
    for i in range(3):
        base = NOW - timedelta(days=i + 1)
        _offline_event(repo, "0xa1", base)
        # Far outside the co-occurrence window.
        _offline_event(repo, "0xa2", base + timedelta(hours=3))
    result = aggregate_passive_hints(repo, "home", now=NOW)
    assert result["hints"] == []


def test_unknown_devices_never_get_hints(tmp_path: Path):
    repo = _repo(tmp_path)
    _add_device(repo, "0xa1")
    # 0xzz is not a known inventory device.
    _co_instability(repo, "0xa1", "0xzz", windows=PASSIVE_HINT_MIN_REPEATED_WINDOWS)
    result = aggregate_passive_hints(repo, "home", now=NOW)
    assert result["hints"] == []


def test_no_route_evidence_or_direction_from_passive_data(tmp_path: Path):
    repo = _repo(tmp_path)
    _add_device(repo, "0xa1")
    _add_device(repo, "0xa2")
    _co_instability(repo, "0xa1", "0xa2", windows=PASSIVE_HINT_MIN_REPEATED_WINDOWS + 1)
    result = aggregate_passive_hints(repo, "home", now=NOW)
    for hint in result["hints"]:
        assert hint["evidence_class"] == "passive_derived_association"
        assert hint["directional"] is False
        assert "route" not in json.dumps(hint["rules_matched"]).lower()


def test_hint_wording_has_no_forbidden_phrases(tmp_path: Path):
    repo = _repo(tmp_path)
    _add_device(repo, "0xa1")
    _add_device(repo, "0xa2")
    _open_incident_for(repo, "0xa1")
    _co_instability(repo, "0xa1", "0xa2", windows=PASSIVE_HINT_MIN_REPEATED_WINDOWS + 1)
    result = aggregate_passive_hints(repo, "home", now=NOW)
    blob = json.dumps(result).lower()
    for phrase in FORBIDDEN_WORDING:
        assert phrase not in blob, f"Forbidden wording in passive hints: {phrase}"


def test_caps_respected_backend_side(tmp_path: Path):
    repo = _repo(tmp_path)
    # One hub device co-flapping with many others: per-node cap applies.
    hub = "0xhub"
    _add_device(repo, hub)
    others = [f"0xd{i:02d}" for i in range(8)]
    for other in others:
        _add_device(repo, other)
    for windows_index in range(PASSIVE_HINT_MIN_REPEATED_WINDOWS):
        for i, other in enumerate(others):
            # Separate windows per pair so no window is network-wide.
            base = NOW - timedelta(days=windows_index + 1, hours=i)
            _offline_event(repo, hub, base)
            _offline_event(repo, other, base + timedelta(minutes=1))
    result = aggregate_passive_hints(repo, "home", now=NOW)
    assert result["available_count"] == len(others)
    hub_hints = [
        h for h in result["hints"] if hub in (h["source_ieee"], h["target_ieee"])
    ]
    assert len(hub_hints) <= MAX_PASSIVE_HINTS_PER_NODE
    assert len(result["hints"]) <= MAX_PASSIVE_HINTS_TOTAL


def test_network_wide_windows_are_excluded(tmp_path: Path):
    repo = _repo(tmp_path)
    devices = [f"0xd{i:02d}" for i in range(15)]
    for ieee in devices:
        _add_device(repo, ieee)
    # Every device goes offline in the same windows: a network-wide event,
    # which carries no pairwise signal.
    for windows_index in range(PASSIVE_HINT_MIN_REPEATED_WINDOWS + 1):
        base = NOW - timedelta(days=windows_index + 1)
        for i, ieee in enumerate(devices):
            _offline_event(repo, ieee, base + timedelta(seconds=10 * i))
    result = aggregate_passive_hints(repo, "home", now=NOW)
    assert result["hints"] == []


def test_deterministic_output(tmp_path: Path):
    repo = _repo(tmp_path)
    for ieee in ("0xa1", "0xa2", "0xa3"):
        _add_device(repo, ieee)
    _co_instability(repo, "0xa1", "0xa2", windows=PASSIVE_HINT_MIN_REPEATED_WINDOWS)
    _co_instability(repo, "0xa2", "0xa3", windows=PASSIVE_HINT_MIN_REPEATED_WINDOWS)
    first = aggregate_passive_hints(repo, "home", now=NOW)
    second = aggregate_passive_hints(repo, "home", now=NOW)
    assert first == second


def test_evidence_graph_api_includes_passive_hints(topology_client: TestClient):
    from zigbeelens.app.context import get_context

    ctx = get_context()
    repo = ctx.repo
    now = datetime.now(timezone.utc)
    _add_device(repo, "0xa1")
    _add_device(repo, "0xa2")
    for i in range(PASSIVE_HINT_MIN_REPEATED_WINDOWS):
        base = now - timedelta(days=i + 1)
        _offline_event(repo, "0xa1", base)
        _offline_event(repo, "0xa2", base + timedelta(minutes=2))

    res = topology_client.get("/api/topology/home/evidence-graph")
    assert res.status_code == 200
    body = res.json()
    assert body["counts"]["passive_hint_count_available"] == 1
    assert body["counts"]["passive_hint_count_total"] == 1
    # Drawn subsets are a client decision: unknown here, never zero.
    assert body["counts"]["passive_hint_count_drawn"] is None
    assert body["passive_hint_window"]["days"] == PASSIVE_HINT_LOOKBACK_DAYS
    hint = body["passive_hints"][0]
    assert hint["evidence_class"] == "passive_derived_association"
    assert {hint["source_ieee"], hint["target_ieee"]} == {"0xa1", "0xa2"}
    assert hint["limitations"] == PASSIVE_HINT_LIMITATIONS
    assert hint["supporting_observations"]
    assert hint["suggested_investigation"]


def test_evidence_graph_api_empty_passive_state(topology_client: TestClient):
    res = topology_client.get("/api/topology/home/evidence-graph")
    assert res.status_code == 200
    body = res.json()
    assert body["passive_hints"] == []
    assert body["counts"]["passive_hint_count_available"] == 0
    assert body["counts"]["passive_hint_count_total"] == 0
