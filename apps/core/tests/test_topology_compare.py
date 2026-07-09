"""Snapshot compare tests: change detection rules, wording and determinism."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.compare import (
    CHURN_LOW_MAX_RATIO,
    CHURN_MODERATE_MAX_RATIO,
    LARGE_ROUTER_CHANGE_MIN_LINKS,
    LARGE_ROUTER_CHANGE_RATIO,
    LATEST_LIMITED_COPY,
    MEANINGFUL_LQI_CHANGE,
    NO_CHANGES_COPY,
    NOT_ENOUGH_HISTORY_COPY,
    compare_snapshots,
)
from zigbeelens.topology.parser import parse_networkmap_payload

NOW = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)

FORBIDDEN_WORDING = [
    "lost",
    "broken",
    "dropped",
    "disconnected",
    "gone",
    "missing from mesh",
    "offline",
    "failed",
    "root cause",
    "parent router",
    "child device",
    "current route",
    "actual path",
]


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "compare.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "compare.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    return repo


DEFAULT_NODES = {
    "0x01": {"type": "Coordinator"},
    "0x02": {"type": "Router"},
    "0x03": {"type": "Router"},
    "0x04": {"type": "EndDevice"},
}


def _store_snapshot(
    repo: Repository,
    snapshot_id: str,
    *,
    captured_at: datetime,
    links: list[dict],
    nodes: dict[str, dict] | None = None,
    status: str = "complete",
) -> None:
    repo.create_topology_snapshot(
        snapshot_id=snapshot_id,
        network_id="home",
        requested_by="test",
        status="pending",
        warning_acknowledged=True,
    )
    parsed = parse_networkmap_payload(
        {"nodes": DEFAULT_NODES if nodes is None else nodes, "links": links}
    )
    repo.store_topology_parsed(snapshot_id, "home", parsed, status=status)
    repo.db.conn.execute(
        "UPDATE topology_snapshots SET captured_at = ? WHERE snapshot_id = ?",
        (captured_at.isoformat(), snapshot_id),
    )
    repo.db.conn.commit()


def _changes_of(result: dict, change_type: str) -> list[dict]:
    return [c for c in result["changes"] if c["type"] == change_type]


def test_not_enough_history_returns_calm_compare_specific_response(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-only",
        captured_at=NOW - timedelta(hours=1),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 100}],
    )
    result = compare_snapshots(repo, "home")
    assert result["has_comparison"] is False
    assert result["summary"] == NOT_ENOUGH_HISTORY_COPY
    assert result["changes"] == []
    assert result["counts"]["total_changes"] == 0


def test_default_compare_uses_latest_and_previous_usable_snapshots(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-old",
        captured_at=NOW - timedelta(days=2),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 100}],
    )
    _store_snapshot(
        repo,
        "snap-failed",
        captured_at=NOW - timedelta(days=1),
        links=[],
        status="failed",
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 100}],
    )
    result = compare_snapshots(repo, "home")
    assert result["has_comparison"] is True
    # Failed snapshots are never chosen for comparison.
    assert result["compare_snapshot"]["snapshot_id"] == "snap-latest"
    assert result["base_snapshot"]["snapshot_id"] == "snap-old"


def test_newly_observed_and_no_longer_observed_devices(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        nodes={"0x01": {"type": "Coordinator"}, "0x02": {"type": "Router"}},
        links=[{"source": "0x02", "target": "0x01", "linkquality": 100}],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        nodes={"0x01": {"type": "Coordinator"}, "0x03": {"type": "Router"}},
        links=[{"source": "0x03", "target": "0x01", "linkquality": 90}],
    )
    result = compare_snapshots(repo, "home")
    new_devices = _changes_of(result, "newly_observed_device")
    assert [c["device_ieees"] for c in new_devices] == [["0x03"]]
    no_evidence = _changes_of(result, "device_no_topology_evidence")
    assert [c["device_ieees"] for c in no_evidence] == [["0x02"]]
    # Absence is worded as evidence absence, never as failure/offline.
    assert "no topology evidence in the latest snapshot" in no_evidence[0]["title"]
    assert result["counts"]["newly_observed_devices"] == 1
    assert result["counts"]["devices_no_topology_evidence"] == 1


def test_new_and_missing_neighbour_links(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        links=[
            {"source": "0x02", "target": "0x01", "linkquality": 100},
            {"source": "0x03", "target": "0x02", "linkquality": 70},
        ],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[
            {"source": "0x02", "target": "0x01", "linkquality": 100},
            {"source": "0x04", "target": "0x02", "linkquality": 60},
        ],
    )
    result = compare_snapshots(repo, "home")
    new_links = _changes_of(result, "new_neighbour_link")
    assert len(new_links) == 1
    assert set(new_links[0]["device_ieees"]) == {"0x02", "0x04"}
    assert new_links[0]["focus_edge_ids"] == ["live-neighbor-0x02|0x04"]
    missing = _changes_of(result, "missing_neighbour_link")
    assert len(missing) == 1
    assert set(missing[0]["device_ieees"]) == {"0x02", "0x03"}
    # Neutral compare wording: previous-only, never lost/removed/missing.
    assert "seen in previous snapshot only" in missing[0]["title"]
    new_titles = [c["title"] for c in new_links]
    assert all("seen in latest snapshot only" in t for t in new_titles)
    assert result["counts"]["new_neighbour_links"] == 1
    assert result["counts"]["neighbour_links_not_present_latest"] == 1


def test_reverse_direction_is_the_same_neighbour_link(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 100}],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[{"source": "0x01", "target": "0x02", "linkquality": 100}],
    )
    result = compare_snapshots(repo, "home")
    assert result["counts"]["new_neighbour_links"] == 0
    assert result["counts"]["neighbour_links_not_present_latest"] == 0


def test_changed_neighbour_lqi_uses_threshold_and_ignores_nulls(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        links=[
            {"source": "0x02", "target": "0x01", "linkquality": 100},
            {"source": "0x03", "target": "0x01", "linkquality": 100},
            # No LQI recorded for this pair in the previous snapshot.
            {"source": "0x03", "target": "0x02"},
        ],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[
            # Below threshold: not a change.
            {
                "source": "0x02",
                "target": "0x01",
                "linkquality": 100 + MEANINGFUL_LQI_CHANGE - 1,
            },
            # At threshold: a change.
            {
                "source": "0x03",
                "target": "0x01",
                "linkquality": 100 - MEANINGFUL_LQI_CHANGE,
            },
            # Null on one side is never compared (null is not zero).
            {"source": "0x03", "target": "0x02", "linkquality": 200},
        ],
    )
    result = compare_snapshots(repo, "home")
    changed = _changes_of(result, "changed_neighbour_link")
    assert len(changed) == 1
    assert set(changed[0]["device_ieees"]) == {"0x03", "0x01"}
    assert changed[0]["before"]["lqi"] == 100
    assert changed[0]["after"]["lqi"] == 100 - MEANINGFUL_LQI_CHANGE
    assert result["counts"]["changed_neighbour_links"] == 1


def test_route_hint_changes_come_only_from_route_evidence(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        links=[
            # Route evidence present previously.
            {
                "source": "0x02",
                "target": "0x01",
                "linkquality": 100,
                "routes": [{"destinationAddress": 1}],
            },
            # Strong neighbour link with no route evidence: never a route hint.
            {"source": "0x03", "target": "0x01", "linkquality": 250},
        ],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[
            # Route evidence gone in the latest snapshot (routes list empty).
            {"source": "0x02", "target": "0x01", "linkquality": 100, "routes": []},
            {"source": "0x03", "target": "0x01", "linkquality": 250},
            # New route evidence.
            {
                "source": "0x03",
                "target": "0x02",
                "linkquality": 80,
                "routes": [{"destinationAddress": 2}, {"destinationAddress": 3}],
            },
        ],
    )
    result = compare_snapshots(repo, "home")
    new_hints = _changes_of(result, "new_route_hint")
    assert len(new_hints) == 1
    assert new_hints[0]["device_ieees"] == ["0x03", "0x02"]
    assert new_hints[0]["after"]["route_count"] == 2
    missing_hints = _changes_of(result, "missing_route_hint")
    assert len(missing_hints) == 1
    assert missing_hints[0]["device_ieees"] == ["0x02", "0x01"]
    # The strong neighbour link never became route evidence.
    assert all(
        "0x03" not in c["device_ieees"] or "0x01" not in c["device_ieees"]
        for c in new_hints + missing_hints
    )
    assert result["counts"]["new_route_hints"] == 1
    assert result["counts"]["route_hints_not_present_latest"] == 1


def test_changed_route_hint_from_route_count_change(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        links=[
            {
                "source": "0x02",
                "target": "0x01",
                "linkquality": 100,
                "routes": [{"destinationAddress": 1}],
            }
        ],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[
            {
                "source": "0x02",
                "target": "0x01",
                "linkquality": 100,
                "routes": [{"destinationAddress": 1}, {"destinationAddress": 2}],
            }
        ],
    )
    result = compare_snapshots(repo, "home")
    changed = _changes_of(result, "changed_route_hint")
    assert len(changed) == 1
    assert changed[0]["before"]["route_count"] == 1
    assert changed[0]["after"]["route_count"] == 2
    assert "not proof of current live routing" in changed[0]["practical_note"]


def test_no_meaningful_changes_yields_calm_summary(tmp_path: Path):
    repo = _repo(tmp_path)
    links = [{"source": "0x02", "target": "0x01", "linkquality": 100}]
    _store_snapshot(repo, "snap-prev", captured_at=NOW - timedelta(days=1), links=links)
    _store_snapshot(repo, "snap-latest", captured_at=NOW - timedelta(hours=1), links=links)
    result = compare_snapshots(repo, "home")
    assert result["has_comparison"] is True
    assert result["summary"] == NO_CHANGES_COPY
    assert result["summary_items"] == []
    assert result["counts"]["total_changes"] == 0


def test_summary_items_include_only_non_zero_categories(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 100}],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[
            {"source": "0x02", "target": "0x01", "linkquality": 100},
            {"source": "0x03", "target": "0x02", "linkquality": 70},
        ],
    )
    result = compare_snapshots(repo, "home")
    assert result["summary_items"] == ["1 neighbour link seen in latest snapshot only"]


def test_ordering_is_deterministic_and_unavailable_devices_come_first(tmp_path: Path):
    repo = _repo(tmp_path)
    for ieee, name in (("0x02", "Hall Router"), ("0x03", "Study Router")):
        repo.upsert_device(
            network_id="home",
            ieee_address=ieee,
            friendly_name=name,
            device_type="Router",
            power_source="Mains",
        )
    # Study Router (0x03) is currently reported unavailable.
    repo.update_device_current_state(
        network_id="home", ieee_address="0x03", availability="offline"
    )
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        links=[
            {"source": "0x02", "target": "0x01", "linkquality": 100},
            {"source": "0x03", "target": "0x01", "linkquality": 100},
        ],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[],
        nodes={"0x01": {"type": "Coordinator"}},
    )
    first = compare_snapshots(repo, "home")
    second = compare_snapshots(repo, "home")
    assert [c["id"] for c in first["changes"]] == [c["id"] for c in second["changes"]]
    missing = [c for c in first["changes"] if c["type"] == "missing_neighbour_link"]
    # The change involving the unavailable device sorts first.
    assert "0x03" in missing[0]["device_ieees"]
    # Availability context is supporting evidence, not an inference from
    # topology absence.
    assert any("unavailable" in item for item in missing[0]["supporting_evidence"])
    other = [c for c in missing if "0x02" in c["device_ieees"]][0]
    assert not any("unavailable" in item for item in other["supporting_evidence"])


def test_comparison_never_uses_forbidden_wording(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        links=[
            {"source": "0x02", "target": "0x01", "linkquality": 100},
            {
                "source": "0x03",
                "target": "0x01",
                "linkquality": 90,
                "routes": [{"destinationAddress": 4}],
            },
        ],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        nodes={"0x01": {"type": "Coordinator"}, "0x04": {"type": "EndDevice"}},
        links=[{"source": "0x04", "target": "0x01", "linkquality": 50}],
    )
    result = compare_snapshots(repo, "home")
    assert result["counts"]["total_changes"] > 0
    text = " ".join(
        [result["summary"], *result["summary_items"]]
        + [
            " ".join(
                [
                    change["title"],
                    change["summary"],
                    change["practical_note"],
                    *change["supporting_evidence"],
                ]
            )
            for change in result["changes"]
        ]
    ).lower()
    for phrase in FORBIDDEN_WORDING:
        assert phrase not in text, phrase


def _many_links(count: int, *, lqi: int = 100) -> list[dict]:
    """Distinct neighbour links 0x01 — 0xn10, 0xn11, ... for churn fixtures."""
    return [
        {"source": f"0xn{i + 10}", "target": "0x01", "linkquality": lqi}
        for i in range(count)
    ]


def _nodes_for(links: list[dict]) -> dict[str, dict]:
    nodes: dict[str, dict] = {"0x01": {"type": "Coordinator"}}
    for link in links:
        nodes[link["source"]] = {"type": "Router"}
    return nodes


def test_churn_level_is_low_when_few_links_differ(tmp_path: Path):
    repo = _repo(tmp_path)
    stable = _many_links(30)
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        nodes=_nodes_for(stable),
        links=stable,
    )
    latest = [*stable, {"source": "0x02", "target": "0x01", "linkquality": 90}]
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        nodes=_nodes_for(latest),
        links=latest,
    )
    result = compare_snapshots(repo, "home")
    churn = result["churn"]
    # 1 changed link over 61 available links: below the low threshold.
    assert churn["changed_evidence_total"] == 1
    assert churn["available_compare_evidence"] == 61
    assert churn["changed_evidence_total"] / churn["available_compare_evidence"] < (
        CHURN_LOW_MAX_RATIO
    )
    assert churn["level"] == "low"
    assert "low topology-evidence churn" in result["summary"]


def test_churn_level_is_moderate_between_thresholds(tmp_path: Path):
    repo = _repo(tmp_path)
    stable = _many_links(20)
    extra_prev = [
        {"source": f"0xp{i}", "target": "0x01", "linkquality": 80} for i in range(4)
    ]
    prev = [*stable, *extra_prev]
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        nodes=_nodes_for(prev),
        links=prev,
    )
    extra_latest = [
        {"source": f"0xl{i}", "target": "0x01", "linkquality": 80} for i in range(4)
    ]
    latest = [*stable, *extra_latest]
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        nodes=_nodes_for(latest),
        links=latest,
    )
    result = compare_snapshots(repo, "home")
    churn = result["churn"]
    # 8 differing links over 48 available links: between the thresholds.
    ratio = churn["changed_evidence_total"] / churn["available_compare_evidence"]
    assert CHURN_LOW_MAX_RATIO <= ratio <= CHURN_MODERATE_MAX_RATIO
    assert churn["level"] == "moderate"
    assert "moderate topology-evidence churn" in result["summary"]


def test_churn_level_is_high_when_most_links_differ(tmp_path: Path):
    repo = _repo(tmp_path)
    prev = _many_links(10)
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        nodes=_nodes_for(prev),
        links=prev,
    )
    latest = [
        {"source": f"0xz{i}", "target": "0x01", "linkquality": 90} for i in range(10)
    ]
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        nodes=_nodes_for(latest),
        links=latest,
    )
    result = compare_snapshots(repo, "home")
    churn = result["churn"]
    ratio = churn["changed_evidence_total"] / churn["available_compare_evidence"]
    assert ratio > CHURN_MODERATE_MAX_RATIO
    assert churn["level"] == "high"
    assert "high topology-evidence churn" in result["summary"]
    # High churn is still described calmly with the dominant-category note.
    assert "does not prove live routing changed" in result["summary"]
    # The raw counts remain available for the churn section.
    assert result["counts"]["new_neighbour_links"] == 10
    assert result["counts"]["neighbour_links_not_present_latest"] == 10


def test_churn_is_deterministic(tmp_path: Path):
    repo = _repo(tmp_path)
    prev = _many_links(10)
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        nodes=_nodes_for(prev),
        links=prev,
    )
    latest = _many_links(6)
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        nodes=_nodes_for(latest),
        links=latest,
    )
    first = compare_snapshots(repo, "home")
    second = compare_snapshots(repo, "home")
    assert first["churn"] == second["churn"]
    assert first["summary"] == second["summary"]
    assert [i["id"] for i in first["worth_reviewing"]] == [
        i["id"] for i in second["worth_reviewing"]
    ]


def test_no_history_reports_unknown_churn_not_zero(tmp_path: Path):
    repo = _repo(tmp_path)
    result = compare_snapshots(repo, "home")
    assert result["has_comparison"] is False
    # Unknown stays null, never zero.
    assert result["churn"]["level"] is None
    assert result["churn"]["changed_evidence_total"] is None
    assert result["churn"]["available_compare_evidence"] is None
    assert result["worth_reviewing"] == []


def test_issue_linked_insight_uses_existing_issue_flags_only(tmp_path: Path):
    repo = _repo(tmp_path)
    for ieee, name in (("0x02", "Hall Router"), ("0x03", "Study Router")):
        repo.upsert_device(
            network_id="home",
            ieee_address=ieee,
            friendly_name=name,
            device_type="Router",
            power_source="Mains",
        )
    # Hall Router is currently reported unavailable; Study Router is healthy.
    repo.update_device_current_state(
        network_id="home", ieee_address="0x02", availability="offline"
    )
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        links=[
            {"source": "0x02", "target": "0x01", "linkquality": 100},
            {"source": "0x03", "target": "0x01", "linkquality": 100},
        ],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[
            {"source": "0x02", "target": "0x01", "linkquality": 40},
            {"source": "0x03", "target": "0x01", "linkquality": 100},
        ],
    )
    result = compare_snapshots(repo, "home")
    issue_linked = [
        i for i in result["worth_reviewing"] if i["type"] == "issue_linked_topology_change"
    ]
    # Only the unavailable device produces an issue-linked insight; the
    # healthy device with unchanged evidence never does.
    assert [i["device_ieees"] for i in issue_linked] == [["0x02"]]
    assert "Hall Router" in issue_linked[0]["title"]
    assert "unavailable" in issue_linked[0]["summary"]
    # The insight is a place to look, never a causal claim.
    assert "does not prove" in issue_linked[0]["practical_note"]


def test_no_latest_neighbour_evidence_insight_is_worded_neutrally(tmp_path: Path):
    repo = _repo(tmp_path)
    repo.upsert_device(
        network_id="home",
        ieee_address="0x04",
        friendly_name="Bedroom Sensor",
        device_type="EndDevice",
        power_source="Battery",
    )
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        links=[
            {"source": "0x02", "target": "0x01", "linkquality": 100},
            {"source": "0x04", "target": "0x02", "linkquality": 60},
        ],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 100}],
    )
    result = compare_snapshots(repo, "home")
    insights = [
        i
        for i in result["worth_reviewing"]
        if i["type"] == "no_latest_neighbour_evidence_after_previous"
    ]
    assert [i["device_ieees"] for i in insights] == [["0x04"]]
    assert insights[0]["title"] == (
        "Bedroom Sensor has no neighbour evidence in the latest snapshot"
    )
    # Evidence absence, never failure.
    assert "but none in the latest usable snapshot" in insights[0]["summary"]
    assert "evidence absence" in insights[0]["practical_note"]


def test_large_router_evidence_change_uses_named_thresholds(tmp_path: Path):
    repo = _repo(tmp_path)
    repo.upsert_device(
        network_id="home",
        ieee_address="0x02",
        friendly_name="Hall Router",
        device_type="Router",
        power_source="Mains",
    )
    # Previous snapshot: the router has LARGE_ROUTER_CHANGE_MIN_LINKS + 2
    # neighbours; the latest keeps only 2, so both thresholds are met.
    neighbour_count = LARGE_ROUTER_CHANGE_MIN_LINKS + 2
    prev = [
        {"source": "0x02", "target": f"0xn{i + 10}", "linkquality": 100}
        for i in range(neighbour_count)
    ]
    nodes = {
        "0x01": {"type": "Coordinator"},
        "0x02": {"type": "Router"},
        **{f"0xn{i + 10}": {"type": "EndDevice"} for i in range(neighbour_count)},
    }
    _store_snapshot(
        repo, "snap-prev", captured_at=NOW - timedelta(days=1), nodes=nodes, links=prev
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        nodes=nodes,
        links=prev[:2],
    )
    result = compare_snapshots(repo, "home")
    router_insights = [
        i for i in result["worth_reviewing"] if i["type"] == "large_router_evidence_change"
    ]
    assert [i["device_ieees"] for i in router_insights] == [["0x02"]]
    changed = LARGE_ROUTER_CHANGE_MIN_LINKS
    assert changed / neighbour_count >= LARGE_ROUTER_CHANGE_RATIO
    assert "large change in observed neighbour evidence" in router_insights[0]["title"]


def test_small_router_change_does_not_trigger_large_change_insight(tmp_path: Path):
    repo = _repo(tmp_path)
    repo.upsert_device(
        network_id="home",
        ieee_address="0x02",
        friendly_name="Hall Router",
        device_type="Router",
        power_source="Mains",
    )
    # Below the absolute threshold: only a handful of links differ.
    prev = [
        {"source": "0x02", "target": f"0xn{i + 10}", "linkquality": 100}
        for i in range(LARGE_ROUTER_CHANGE_MIN_LINKS - 1)
    ]
    nodes = {
        "0x01": {"type": "Coordinator"},
        "0x02": {"type": "Router"},
        **{
            f"0xn{i + 10}": {"type": "EndDevice"}
            for i in range(LARGE_ROUTER_CHANGE_MIN_LINKS - 1)
        },
    }
    _store_snapshot(
        repo, "snap-prev", captured_at=NOW - timedelta(days=1), nodes=nodes, links=prev
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        nodes=nodes,
        links=[],
    )
    result = compare_snapshots(repo, "home")
    assert not [
        i for i in result["worth_reviewing"] if i["type"] == "large_router_evidence_change"
    ]


def test_worth_reviewing_is_empty_without_issue_signals(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 100}],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[
            {"source": "0x02", "target": "0x01", "linkquality": 100},
            {"source": "0x03", "target": "0x02", "linkquality": 70},
        ],
    )
    result = compare_snapshots(repo, "home")
    # A single new link with no issue flags produces no insights.
    assert result["worth_reviewing"] == []


def test_limited_latest_snapshot_adds_qualified_limitation(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 100}],
    )
    # Complete status but nothing parsed: the compare must say it is limited.
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        nodes={},
        links=[],
    )
    result = compare_snapshots(repo, "home")
    assert LATEST_LIMITED_COPY in result["limitations"]


def test_worth_reviewing_wording_never_uses_forbidden_terms(tmp_path: Path):
    repo = _repo(tmp_path)
    repo.upsert_device(
        network_id="home",
        ieee_address="0x02",
        friendly_name="Hall Router",
        device_type="Router",
        power_source="Mains",
    )
    repo.update_device_current_state(
        network_id="home", ieee_address="0x02", availability="offline"
    )
    prev = [
        {"source": "0x02", "target": f"0xn{i + 10}", "linkquality": 100}
        for i in range(LARGE_ROUTER_CHANGE_MIN_LINKS + 2)
    ]
    nodes = {
        "0x01": {"type": "Coordinator"},
        "0x02": {"type": "Router"},
        **{
            f"0xn{i + 10}": {"type": "EndDevice"}
            for i in range(LARGE_ROUTER_CHANGE_MIN_LINKS + 2)
        },
    }
    _store_snapshot(
        repo, "snap-prev", captured_at=NOW - timedelta(days=1), nodes=nodes, links=prev
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        nodes={"0x01": {"type": "Coordinator"}, "0x02": {"type": "Router"}},
        links=[],
    )
    result = compare_snapshots(repo, "home")
    assert result["worth_reviewing"]
    text = " ".join(
        " ".join(
            [
                insight["title"],
                insight["summary"],
                insight["practical_note"],
                *insight["supporting_evidence"],
            ]
        )
        for insight in result["worth_reviewing"]
    ).lower()
    for phrase in FORBIDDEN_WORDING:
        if phrase == "offline":
            # "unavailable" is the approved availability wording; the word
            # offline never appears in insight copy either.
            assert "offline" not in text
            continue
        assert phrase not in text, phrase


def test_explicit_snapshot_ids_can_be_compared(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-a",
        captured_at=NOW - timedelta(days=3),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 100}],
    )
    _store_snapshot(
        repo,
        "snap-b",
        captured_at=NOW - timedelta(days=2),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 100}],
    )
    _store_snapshot(
        repo,
        "snap-c",
        captured_at=NOW - timedelta(hours=1),
        links=[
            {"source": "0x02", "target": "0x01", "linkquality": 100},
            {"source": "0x03", "target": "0x02", "linkquality": 70},
        ],
    )
    result = compare_snapshots(
        repo, "home", base_snapshot_id="snap-a", compare_snapshot_id="snap-c"
    )
    assert result["base_snapshot"]["snapshot_id"] == "snap-a"
    assert result["compare_snapshot"]["snapshot_id"] == "snap-c"
    assert result["counts"]["new_neighbour_links"] == 1
