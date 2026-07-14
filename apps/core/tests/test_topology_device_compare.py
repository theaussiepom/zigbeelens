"""Device-led snapshot history tests: per-device counts, actionable status
mapping, availability coverage honesty, and wording guardrails."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.compare import MEANINGFUL_LQI_CHANGE
from zigbeelens.topology.device_compare import (
    CHECK_ENABLE_AVAILABILITY,
    CHECK_ROUTE_HINTS_CONTEXT,
    COVERAGE_BUILDING,
    COVERAGE_OFF,
    COVERAGE_TRACKED,
    COVERAGE_UNKNOWN,
    MAX_SNAPSHOT_HISTORY,
    STATUS_CHANGED,
    STATUS_NO_NOTABLE_CHANGE,
    STATUS_WATCH,
    STATUS_WORTH_REVIEWING,
    WATCH_LINK_DIFFERENCE_MIN,
    device_snapshot_history,
)
from zigbeelens.topology.parser import parse_networkmap_payload

NOW = datetime(2026, 7, 10, 6, 0, 0, tzinfo=timezone.utc)

# Section 12 wording guardrails: none of these may appear in generated copy.
FORBIDDEN_PHRASES = [
    "neighbour evidence",
    "topology evidence churn",
    "topology-evidence churn",
    "lost",
    "missing",
    "disappeared",
    "broken",
    "parent router",
    "current route",
    "currently routed",
    "actual path",
]
FORBIDDEN_WORD_PATTERNS = [r"\bfailed\b", r"\bcaused\b", r"\bcause\b"]


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "device-compare.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "device-compare.sqlite")),
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


def _insert_availability_change(
    repo: Repository,
    ieee: str,
    to_state: str,
    changed_at: datetime,
    from_state: str = "unknown",
) -> None:
    repo.db.conn.execute(
        """
        INSERT INTO availability_changes
            (network_id, ieee_address, from_state, to_state, changed_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("home", ieee, from_state, to_state, changed_at.isoformat()),
    )
    repo.db.conn.commit()


def _device(repo: Repository, ieee: str, name: str, device_type: str = "Router") -> None:
    repo.upsert_device(
        network_id="home",
        ieee_address=ieee,
        friendly_name=name,
        device_type=device_type,
        power_source="Mains",
    )



def _open_incident_for(repo: Repository, ieee: str) -> None:
    repo.insert_incident(
        incident_id="inc-device-compare",
        dedup_key="dedup-device-compare",
        incident_type="single_device_unavailable",
        lifecycle_state="open",
        severity="warning",
        scope="device",
        confidence="medium",
        title="Device unavailable",
        summary="Device stopped reporting.",
        explanation="Stored incident.",
        evidence=[],
        counter_evidence=[],
        limitations=[],
        opened_at=NOW.isoformat(),
        updated_at=NOW.isoformat(),
    )
    repo.db.conn.execute(
        """
        INSERT INTO incident_devices (incident_id, network_id, ieee_address, role)
        VALUES ('inc-device-compare', 'home', ?, 'affected')
        """,
        (ieee,),
    )
    repo.db.conn.commit()


def test_active_incident_does_not_make_snapshot_history_worth_reviewing(tmp_path: Path):
    repo = _repo(tmp_path)
    _device(repo, "0x02", "Hall Router")
    repo.update_device_current_state(
        network_id="home", ieee_address="0x02", availability="online"
    )
    _open_incident_for(repo, "0x02")
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
        links=[{"source": "0x02", "target": "0x01", "linkquality": 40}],
    )

    result = device_snapshot_history(repo, "home", "0x02")
    assert result["snapshots"][0]["comparison_to_latest"]["status"] is not STATUS_WORTH_REVIEWING


def test_offline_state_still_makes_snapshot_history_worth_reviewing(tmp_path: Path):
    repo = _repo(tmp_path)
    _device(repo, "0x02", "Hall Router")
    repo.update_device_current_state(
        network_id="home", ieee_address="0x02", availability="offline"
    )
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
        links=[{"source": "0x02", "target": "0x01", "linkquality": 40}],
    )

    result = device_snapshot_history(repo, "home", "0x02")
    assert result["snapshots"][0]["comparison_to_latest"]["status"] == STATUS_WORTH_REVIEWING

def test_history_returns_multiple_previous_usable_snapshots_newest_first(tmp_path: Path):
    repo = _repo(tmp_path)
    links = [{"source": "0x02", "target": "0x01", "linkquality": 100}]
    for i in range(4):
        _store_snapshot(
            repo, f"snap-{i}", captured_at=NOW - timedelta(days=4 - i), links=links
        )
    _store_snapshot(
        repo, "snap-failed", captured_at=NOW - timedelta(hours=2), links=[], status="failed"
    )
    result = device_snapshot_history(repo, "home", "0x02")
    assert result["latest_snapshot"]["snapshot_id"] == "snap-3"
    assert result["latest_snapshot"]["is_latest"] is True
    # Failed snapshots are never listed; earlier usable ones are newest first.
    assert [row["snapshot_id"] for row in result["snapshots"]] == [
        "snap-2",
        "snap-1",
        "snap-0",
    ]
    # The first earlier row is the previous usable snapshot (UI default).
    assert result["snapshots"][0]["snapshot_id"] == "snap-2"
    # Every earlier snapshot can be selected: each carries a comparison.
    assert all(row["comparison_to_latest"] is not None for row in result["snapshots"])


def test_history_is_capped_at_max_snapshots(tmp_path: Path):
    repo = _repo(tmp_path)
    links = [{"source": "0x02", "target": "0x01", "linkquality": 100}]
    for i in range(MAX_SNAPSHOT_HISTORY + 5):
        _store_snapshot(
            repo,
            f"snap-{i:02d}",
            captured_at=NOW - timedelta(days=MAX_SNAPSHOT_HISTORY + 5 - i),
            links=links,
        )
    result = device_snapshot_history(repo, "home", "0x02")
    assert 1 + len(result["snapshots"]) == MAX_SNAPSHOT_HISTORY


def test_counts_are_per_device_not_network_wide(tmp_path: Path):
    repo = _repo(tmp_path)
    links = [
        {"source": "0x02", "target": "0x01", "linkquality": 100},
        {
            "source": "0x02",
            "target": "0x03",
            "linkquality": 90,
            "routes": [{"destinationAddress": 1}],
        },
        # Not involving 0x02: must not count for it.
        {"source": "0x03", "target": "0x01", "linkquality": 80},
        {"source": "0x04", "target": "0x03", "linkquality": 70},
    ]
    _store_snapshot(repo, "snap-prev", captured_at=NOW - timedelta(days=1), links=links)
    _store_snapshot(repo, "snap-latest", captured_at=NOW - timedelta(hours=1), links=links)
    result = device_snapshot_history(repo, "home", "0x02")
    assert result["latest_snapshot"]["links_for_device_count"] == 2
    assert result["latest_snapshot"]["route_hints_for_device_count"] == 1
    row = result["snapshots"][0]
    assert row["links_for_device_count"] == 2
    assert row["route_hints_for_device_count"] == 1


def test_latest_only_selected_only_and_changed_link_counts(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        links=[
            {"source": "0x02", "target": "0x01", "linkquality": 100},
            {"source": "0x02", "target": "0x03", "linkquality": 90},
        ],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[
            # Shared pair with a meaningful LQI change.
            {
                "source": "0x02",
                "target": "0x01",
                "linkquality": 100 - MEANINGFUL_LQI_CHANGE,
            },
            # Latest-only pair for the device.
            {"source": "0x02", "target": "0x04", "linkquality": 60},
        ],
    )
    counts = device_snapshot_history(repo, "home", "0x02")["snapshots"][0][
        "comparison_to_latest"
    ]["link_counts"]
    assert counts == {
        "latest_count": 2,
        "selected_count": 2,
        "latest_only_count": 1,
        "selected_only_count": 1,
        "changed_count": 1,
    }


def test_no_notable_change_when_snapshots_match(tmp_path: Path):
    repo = _repo(tmp_path)
    links = [{"source": "0x02", "target": "0x01", "linkquality": 100}]
    _store_snapshot(repo, "snap-prev", captured_at=NOW - timedelta(days=1), links=links)
    _store_snapshot(repo, "snap-latest", captured_at=NOW - timedelta(hours=1), links=links)
    comparison = device_snapshot_history(repo, "home", "0x02")["snapshots"][0][
        "comparison_to_latest"
    ]
    assert comparison["status"] == STATUS_NO_NOTABLE_CHANGE
    assert "Similar number of links shown." in comparison["reasons"]
    # Calm statuses carry no suggested checks.
    assert comparison["suggested_checks"] == []


def test_small_difference_without_issue_is_changed(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        links=[
            {"source": "0x02", "target": "0x01", "linkquality": 100},
            {"source": "0x02", "target": "0x03", "linkquality": 90},
        ],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[
            {"source": "0x02", "target": "0x01", "linkquality": 100},
            {"source": "0x02", "target": "0x04", "linkquality": 60},
        ],
    )
    comparison = device_snapshot_history(repo, "home", "0x02")["snapshots"][0][
        "comparison_to_latest"
    ]
    # 2 link differences: below the watch threshold, no issue -> changed.
    assert (
        comparison["link_counts"]["latest_only_count"]
        + comparison["link_counts"]["selected_only_count"]
        + comparison["link_counts"]["changed_count"]
        < WATCH_LINK_DIFFERENCE_MIN
    )
    assert comparison["status"] == STATUS_CHANGED


def test_substantial_link_change_without_issue_is_watch(tmp_path: Path):
    repo = _repo(tmp_path)
    prev_links = [
        {"source": "0x02", "target": f"0xn{i}", "linkquality": 100}
        for i in range(WATCH_LINK_DIFFERENCE_MIN)
    ] + [{"source": "0x02", "target": "0x01", "linkquality": 100}]
    nodes = {
        "0x01": {"type": "Coordinator"},
        "0x02": {"type": "Router"},
        **{f"0xn{i}": {"type": "EndDevice"} for i in range(WATCH_LINK_DIFFERENCE_MIN)},
    }
    _store_snapshot(
        repo, "snap-prev", captured_at=NOW - timedelta(days=1), nodes=nodes, links=prev_links
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        nodes=nodes,
        links=[{"source": "0x02", "target": "0x01", "linkquality": 100}],
    )
    comparison = device_snapshot_history(repo, "home", "0x02")["snapshots"][0][
        "comparison_to_latest"
    ]
    assert comparison["status"] == STATUS_WATCH


def test_current_issue_plus_changed_links_is_worth_reviewing(tmp_path: Path):
    repo = _repo(tmp_path)
    _device(repo, "0x02", "Hall Router")
    repo.update_device_current_state(
        network_id="home", ieee_address="0x02", availability="offline"
    )
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        links=[
            {"source": "0x02", "target": "0x01", "linkquality": 100},
            {"source": "0x02", "target": "0x03", "linkquality": 90},
        ],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 100}],
    )
    result = device_snapshot_history(repo, "home", "0x02")
    assert result["has_current_issue"] is True
    comparison = result["snapshots"][0]["comparison_to_latest"]
    assert comparison["status"] == STATUS_WORTH_REVIEWING
    assert "This device currently needs attention." in comparison["reasons"]
    assert "Confirm the device is powered." in comparison["suggested_checks"]
    assert "Check whether it is reporting in Zigbee2MQTT." in comparison["suggested_checks"]


def test_no_latest_links_after_selected_links_depends_on_issue_context(tmp_path: Path):
    repo = _repo(tmp_path)
    _device(repo, "0x04", "Bathroom Sensor", device_type="EndDevice")
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        links=[
            {"source": "0x04", "target": "0x02", "linkquality": 60},
            {"source": "0x02", "target": "0x01", "linkquality": 100},
        ],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(hours=1),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 100}],
    )
    # No current issue: evidence absence alone is watch, not worth reviewing.
    comparison = device_snapshot_history(repo, "home", "0x04")["snapshots"][0][
        "comparison_to_latest"
    ]
    assert comparison["status"] == STATUS_WATCH
    assert "Latest snapshot shows no links for this device." in comparison["reasons"]
    assert any("one-off snapshot difference" in c for c in comparison["suggested_checks"])

    # With a current issue the same comparison becomes worth reviewing.
    repo.update_device_current_state(
        network_id="home", ieee_address="0x04", availability="offline"
    )
    comparison = device_snapshot_history(repo, "home", "0x04")["snapshots"][0][
        "comparison_to_latest"
    ]
    assert comparison["status"] == STATUS_WORTH_REVIEWING


def test_route_hint_changes_never_imply_live_route_change(tmp_path: Path):
    repo = _repo(tmp_path)
    _device(repo, "0x02", "Hall Router")
    repo.update_device_current_state(
        network_id="home", ieee_address="0x02", availability="offline"
    )
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
        links=[{"source": "0x02", "target": "0x01", "linkquality": 100, "routes": []}],
    )
    comparison = device_snapshot_history(repo, "home", "0x02")["snapshots"][0][
        "comparison_to_latest"
    ]
    assert comparison["route_hint_counts"]["selected_only_count"] == 1
    assert "Route hints differ between the two snapshots." in comparison["reasons"]
    assert CHECK_ROUTE_HINTS_CONTEXT in comparison["suggested_checks"]
    assert "do not prove live routing changed" in CHECK_ROUTE_HINTS_CONTEXT


def test_availability_tracking_off_is_reported_as_off(tmp_path: Path):
    repo = _repo(tmp_path)
    _device(repo, "0x02", "Hall Router")
    links = [{"source": "0x02", "target": "0x01", "linkquality": 100}]
    _store_snapshot(repo, "snap-prev", captured_at=NOW - timedelta(days=1), links=links)
    _store_snapshot(repo, "snap-latest", captured_at=NOW - timedelta(hours=1), links=links)
    result = device_snapshot_history(repo, "home", "0x02")
    assert result["availability_tracking"]["enabled"] is False
    assert result["latest_snapshot"]["availability_coverage_status"] == COVERAGE_OFF
    assert result["snapshots"][0]["availability_coverage_status"] == COVERAGE_OFF
    # No fake online/offline for untracked periods.
    assert result["latest_snapshot"]["availability_state_near_snapshot"] is None
    assert result["snapshots"][0]["availability_state_near_snapshot"] is None


def test_availability_history_building_when_tracking_started_recently(tmp_path: Path):
    repo = _repo(tmp_path)
    _device(repo, "0x02", "Hall Router")
    repo.update_device_current_state(
        network_id="home", ieee_address="0x02", availability="online"
    )
    links = [{"source": "0x02", "target": "0x01", "linkquality": 100}]
    _store_snapshot(repo, "snap-old", captured_at=NOW - timedelta(days=5), links=links)
    _store_snapshot(repo, "snap-prev", captured_at=NOW - timedelta(days=1), links=links)
    _store_snapshot(repo, "snap-latest", captured_at=NOW - timedelta(hours=1), links=links)
    # Tracking started two days ago: after snap-old, before snap-prev.
    _insert_availability_change(repo, "0x02", "online", NOW - timedelta(days=2))
    result = device_snapshot_history(repo, "home", "0x02")
    assert result["availability_tracking"]["enabled"] is True
    assert result["latest_snapshot"]["availability_coverage_status"] == COVERAGE_TRACKED
    rows = {row["snapshot_id"]: row for row in result["snapshots"]}
    assert rows["snap-prev"]["availability_coverage_status"] == COVERAGE_TRACKED
    assert rows["snap-prev"]["availability_state_near_snapshot"] == "online"
    assert rows["snap-old"]["availability_coverage_status"] == COVERAGE_BUILDING
    assert rows["snap-old"]["availability_state_near_snapshot"] is None
    # Off coverage produces the enable suggestion only when coverage is off,
    # never for building periods.
    assert CHECK_ENABLE_AVAILABILITY not in (
        rows["snap-old"]["comparison_to_latest"]["suggested_checks"]
    )


def test_unknown_availability_coverage_stays_unknown_not_zero(tmp_path: Path):
    repo = _repo(tmp_path)
    _device(repo, "0x02", "Hall Router")
    # Tracking appears enabled now (state known) but no transitions were
    # ever recorded, so coverage of earlier periods cannot be confirmed.
    repo.update_device_current_state(
        network_id="home", ieee_address="0x02", availability="online"
    )
    links = [{"source": "0x02", "target": "0x01", "linkquality": 100}]
    _store_snapshot(repo, "snap-prev", captured_at=NOW - timedelta(days=1), links=links)
    _store_snapshot(repo, "snap-latest", captured_at=NOW - timedelta(hours=1), links=links)
    result = device_snapshot_history(repo, "home", "0x02")
    assert result["availability_tracking"]["enabled"] is True
    assert result["availability_tracking"]["earliest_observation_at"] is None
    row = result["snapshots"][0]
    assert row["availability_coverage_status"] == COVERAGE_UNKNOWN
    assert row["availability_state_near_snapshot"] is None


def test_availability_off_check_suggests_enabling_reporting(tmp_path: Path):
    repo = _repo(tmp_path)
    _device(repo, "0x04", "Bathroom Sensor", device_type="EndDevice")
    _store_snapshot(
        repo,
        "snap-prev",
        captured_at=NOW - timedelta(days=1),
        links=[{"source": "0x04", "target": "0x02", "linkquality": 60}],
    )
    _store_snapshot(repo, "snap-latest", captured_at=NOW - timedelta(hours=1), links=[])
    comparison = device_snapshot_history(repo, "home", "0x04")["snapshots"][0][
        "comparison_to_latest"
    ]
    # Watch status with tracking off surfaces the enable suggestion.
    assert comparison["status"] == STATUS_WATCH
    assert CHECK_ENABLE_AVAILABILITY in comparison["suggested_checks"]
    assert "availability and last-seen reporting" in CHECK_ENABLE_AVAILABILITY


def test_no_earlier_snapshots_yields_empty_history(tmp_path: Path):
    repo = _repo(tmp_path)
    _store_snapshot(
        repo,
        "snap-only",
        captured_at=NOW - timedelta(hours=1),
        links=[{"source": "0x02", "target": "0x01", "linkquality": 100}],
    )
    result = device_snapshot_history(repo, "home", "0x02")
    assert result["latest_snapshot"] is not None
    assert result["snapshots"] == []


def test_generated_copy_never_uses_forbidden_wording(tmp_path: Path):
    repo = _repo(tmp_path)
    _device(repo, "0x02", "Hall Router")
    repo.update_device_current_state(
        network_id="home", ieee_address="0x02", availability="offline"
    )
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
            },
            {"source": "0x02", "target": "0x03", "linkquality": 90},
        ],
    )
    _store_snapshot(repo, "snap-latest", captured_at=NOW - timedelta(hours=1), links=[])
    result = device_snapshot_history(repo, "home", "0x02")
    comparison = result["snapshots"][0]["comparison_to_latest"]
    text = " ".join(
        [*comparison["reasons"], *comparison["suggested_checks"]]
    ).lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in text, phrase
    for pattern in FORBIDDEN_WORD_PATTERNS:
        assert not re.search(pattern, text), pattern


def test_history_is_deterministic(tmp_path: Path):
    repo = _repo(tmp_path)
    _device(repo, "0x02", "Hall Router")
    for i in range(3):
        _store_snapshot(
            repo,
            f"snap-{i}",
            captured_at=NOW - timedelta(days=3 - i),
            links=[{"source": "0x02", "target": "0x01", "linkquality": 100 - i * 30}],
        )
    first = device_snapshot_history(repo, "home", "0x02")
    second = device_snapshot_history(repo, "home", "0x02")
    assert first == second


def test_device_snapshot_evidence_has_no_repository_access():
    import inspect

    from zigbeelens.topology.device_compare import _DeviceSnapshotEvidence

    source = inspect.getsource(_DeviceSnapshotEvidence.__init__)
    assert "repo" not in source
    assert "list_topology_links" not in source
    evidence = _DeviceSnapshotEvidence(
        [
            {
                "source_ieee": "0x02",
                "target_ieee": "0x01",
                "linkquality": 120,
                "route_count": 2,
            }
        ],
        "0x02",
    )
    assert evidence.link_lqi[("0x01", "0x02")] == 120
    assert evidence.route_counts[("0x02", "0x01")] == 2


def test_snapshot_history_parity_batch_vs_ordinary(tmp_path: Path):
    from zigbeelens.topology.device_compare import (
        build_device_snapshot_history,
        load_device_snapshot_history_network_context,
    )

    repo = _repo(tmp_path)
    _device(repo, "0x01", "Coordinator", "Coordinator")
    _device(repo, "0x02", "Hall Router")
    _device(repo, "0x03", "Living Router")
    _device(repo, "0x04", "Sensor", "EndDevice")
    repo.ensure_device_current_state("home", "0x04")
    repo.update_device_current_state(
        network_id="home",
        ieee_address="0x04",
        availability="offline",
    )
    _insert_availability_change(repo, "0x02", "online", NOW - timedelta(days=2))
    _store_snapshot(
        repo,
        "snap-old",
        captured_at=NOW - timedelta(days=2),
        links=[
            {"source": "0x02", "target": "0x01", "linkquality": 100},
            {
                "source": "0x02",
                "target": "0x04",
                "linkquality": 80,
                "routes": [{"destinationAddress": 4}],
            },
            {"source": "0x03", "target": "0x01", "linkquality": 90},
        ],
    )
    _store_snapshot(
        repo,
        "snap-mid",
        captured_at=NOW - timedelta(days=1),
        links=[
            {"source": "0x02", "target": "0x01", "linkquality": 110},
            {"source": "0x03", "target": "0x01", "linkquality": 95},
        ],
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[
            {"source": "0x02", "target": "0x01", "linkquality": 120},
            {"source": "0x03", "target": "0x01", "linkquality": 100},
        ],
    )

    context = load_device_snapshot_history_network_context(repo, "home")
    for ieee in ("0x02", "0x03", "0x04"):
        ordinary = device_snapshot_history(repo, "home", ieee)
        row = repo.get_device("home", ieee)
        batch = build_device_snapshot_history(
            repo,
            context,
            ieee,
            device_row=row,
            has_current_issue=ordinary["has_current_issue"],
        )
        assert batch == ordinary


def test_wrong_snapshot_history_network_context_raises(tmp_path: Path):
    from zigbeelens.topology.device_compare import load_device_snapshot_history_network_context

    repo = _repo(tmp_path)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt/home"),
            NetworkConfig(id="office", name="Office", base_topic="zigbee2mqtt/office"),
        ],
        storage=StorageConfig(path=str(tmp_path / "device-compare.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    context = load_device_snapshot_history_network_context(repo, "office")
    import pytest

    with pytest.raises(ValueError, match="network_id"):
        device_snapshot_history(repo, "home", "0x02", network_context=context)
