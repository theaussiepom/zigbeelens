"""Tests for deterministic device story rules (Phase 4A-1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.device_story import (
    CheckCode,
    DEVICE_STORY_HEADLINE_CODES,
    HeadlineCode,
    build_device_story,
    device_story_for_device,
    load_device_story_evidence,
)
from zigbeelens.decisions.model_pattern import (
    MODEL_PATTERN_MIN_AFFECTED_COUNT,
    MODEL_PATTERN_MIN_GROUP_SIZE,
    qualifying_pattern_for_device,
    stored_model_identity_key,
)
from zigbeelens.decisions.reasons import ReasonCode
from zigbeelens.decisions.types import CoverageLabelCode, DecisionPriority, DecisionStatus
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.parser import parse_networkmap_payload

NOW = datetime(2026, 7, 13, 2, 0, 0, tzinfo=timezone.utc)

DEFAULT_NODES = {
    "0x01": {"type": "Coordinator"},
    "0x02": {"type": "Router"},
    "0x03": {"type": "EndDevice"},
}


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "device-story.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "device-story.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    return repo


def _upsert_device(
    repo: Repository,
    ieee: str,
    *,
    availability: str = "online",
    last_seen: datetime | None = None,
    battery: int | None = None,
    linkquality: int | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
) -> None:
    repo.upsert_device(
        network_id="home",
        ieee_address=ieee,
        friendly_name=f"Device {ieee}",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
        manufacturer=manufacturer,
        model=model,
    )
    repo.update_device_current_state(
        network_id="home",
        ieee_address=ieee,
        availability=availability,
        last_seen=(last_seen or NOW).isoformat(),
        linkquality=linkquality,
        battery=battery,
    )


def _enable_availability_tracking(
    repo: Repository,
    ieee: str,
    *,
    changed_at: datetime,
) -> None:
    repo.availability.insert_availability_change("home", ieee, "unknown", "online")
    repo.db.conn.execute(
        "UPDATE availability_changes SET changed_at = ? WHERE rowid = last_insert_rowid()",
        (changed_at.isoformat(),),
    )
    repo.db.conn.commit()


def _link_ha_area(repo: Repository, ieee: str) -> None:
    repo.db.conn.execute(
        """
        INSERT INTO ha_device_enrichment (
            network_id, ieee_address, entity_id, area_id, area_name,
            match_confidence, updated_at
        ) VALUES ('home', ?, 'light.kitchen', 'area-1', 'Kitchen', 'high', ?)
        """,
        (ieee, NOW.isoformat()),
    )
    repo.db.conn.commit()


def _store_snapshot(
    repo: Repository,
    snapshot_id: str,
    *,
    captured_at: datetime,
    links: list[dict],
    nodes: dict[str, dict] | None = None,
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


def _topology_gap_nodes() -> dict[str, dict]:
    return {
        "0x01": {"type": "Coordinator"},
        "0x02": {"type": "Router"},
        "0x03": {"type": "EndDevice"},
    }


def _store_topology_gap_fixtures(repo: Repository) -> None:
    nodes = _topology_gap_nodes()
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[],
        nodes=nodes,
    )
    _store_snapshot(
        repo,
        "snap-old",
        captured_at=NOW - timedelta(days=1),
        links=[{"source": "0x02", "target": "0x03", "linkquality": 90}],
        nodes=nodes,
    )


def test_device_story_headline_codes_are_stable():
    assert "current_issue_present" in DEVICE_STORY_HEADLINE_CODES
    assert "topology_evidence_gap" in DEVICE_STORY_HEADLINE_CODES
    assert "extended_reporting_silence" in DEVICE_STORY_HEADLINE_CODES
    assert "reported_link_quality_changed" in DEVICE_STORY_HEADLINE_CODES
    assert "weak_reported_lqi" not in DEVICE_STORY_HEADLINE_CODES


def test_device_story_for_device_returns_none_for_unknown_device(tmp_path: Path):
    repo = _repo(tmp_path)
    assert device_story_for_device(repo, "home", "0xmissing", now=NOW) is None


def test_current_issue_offline_device(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", availability="offline")
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x03", "linkquality": 120}],
    )

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    assert story.status is DecisionStatus.worth_reviewing
    assert story.priority is DecisionPriority.high
    assert story.headline_code == HeadlineCode.current_issue_present
    assert any(reason.code == ReasonCode.current_issue_present for reason in story.reasons)
    assert any(check.code == CheckCode.confirm_powered for check in story.suggested_checks)


def test_current_issue_active_incident(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", availability="online")
    _open_incident_for(repo, "0x03")
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x03", "linkquality": 120}],
    )

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    assert story.status is DecisionStatus.worth_reviewing
    assert any(reason.code == ReasonCode.current_issue_present for reason in story.reasons)


def test_current_issue_plus_topology_gap_is_review_first(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", availability="offline")
    _store_topology_gap_fixtures(repo)

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    assert story.status is DecisionStatus.review_first
    assert story.priority is DecisionPriority.high
    assert story.headline_code == HeadlineCode.current_issue_present
    assert any(reason.code == ReasonCode.current_issue_present for reason in story.reasons)
    assert any(reason.code == ReasonCode.latest_snapshot_no_links for reason in story.reasons)


def test_topology_gap_without_current_issue_is_watch(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _store_topology_gap_fixtures(repo)

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    assert story.status is DecisionStatus.watch
    assert story.priority is DecisionPriority.low
    assert story.headline_code == HeadlineCode.topology_evidence_gap
    assert any(reason.code == ReasonCode.latest_snapshot_no_links for reason in story.reasons)
    assert any(
        reason.code
        in (ReasonCode.selected_snapshot_had_links, ReasonCode.recent_missing_links_present)
        for reason in story.reasons
    )
    assert any(
        limitation.code == "absence_from_latest_not_failure"
        for limitation in story.limitations
    )


def test_availability_tracking_off_primary_when_no_stronger_signal(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", availability="unknown")
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x03", "linkquality": 120}],
    )

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    assert story.status is DecisionStatus.improve_data_coverage
    assert story.priority is DecisionPriority.medium
    assert story.headline_code == HeadlineCode.availability_tracking_needed
    assert any(
        reason.code == ReasonCode.availability_tracking_off for reason in story.reasons
    )
    assert any(
        check.code == CheckCode.enable_availability_reporting
        for check in story.suggested_checks
    )


def test_stale_last_seen_watch_status(tmp_path: Path):
    repo = _repo(tmp_path)
    stale = NOW - timedelta(hours=72)
    _upsert_device(repo, "0x03", last_seen=stale)
    _enable_availability_tracking(repo, "0x03", changed_at=NOW - timedelta(days=1))
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x03", "linkquality": 120}],
    )

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    assert story.status is DecisionStatus.watch
    assert story.priority is DecisionPriority.low
    assert story.headline_code == HeadlineCode.stale_last_seen
    assert any(reason.code == ReasonCode.last_seen_stale for reason in story.reasons)


def test_low_battery_watch_status(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", battery=12)
    _enable_availability_tracking(repo, "0x03", changed_at=NOW - timedelta(days=1))
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x03", "linkquality": 120}],
    )

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    assert story.status is DecisionStatus.watch
    assert story.priority is DecisionPriority.low
    assert story.headline_code == HeadlineCode.low_battery
    assert any(reason.code == ReasonCode.battery_low for reason in story.reasons)


def test_route_hints_unavailable_is_interpretation_context_not_watch(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", battery=80, linkquality=120)
    _enable_availability_tracking(repo, "0x03", changed_at=NOW - timedelta(days=3))
    _link_ha_area(repo, "0x03")
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x03", "linkquality": 120, "routes": []}],
    )

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    assert story.status is not DecisionStatus.watch
    assert any(reason.code == ReasonCode.route_hints_unavailable for reason in story.reasons)
    assert any(
        limitation.code == "route_hints_not_live_routing"
        for limitation in story.limitations
    )


def test_informational_when_ha_areas_are_not_linked(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", battery=80, linkquality=120)
    _enable_availability_tracking(repo, "0x03", changed_at=NOW - timedelta(days=3))
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[
            {
                "source": "0x02",
                "target": "0x03",
                "linkquality": 120,
                "routes": [{"destination": "0x01"}],
            }
        ],
    )

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    assert story.status is DecisionStatus.informational
    assert story.priority is DecisionPriority.low
    assert story.headline_code == HeadlineCode.data_coverage_gaps
    assert any(reason.code == ReasonCode.ha_areas_not_linked for reason in story.reasons)


def test_old_building_snapshot_coverage_does_not_leak_into_current_story(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _enable_availability_tracking(repo, "0x03", changed_at=NOW - timedelta(days=1))
    nodes = _topology_gap_nodes()
    _store_snapshot(
        repo,
        "snap-old",
        captured_at=NOW - timedelta(days=3),
        links=[{"source": "0x02", "target": "0x03", "linkquality": 90}],
        nodes=nodes,
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x03", "linkquality": 120}],
        nodes=nodes,
    )

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    reason_codes = {reason.code for reason in story.reasons}
    assert ReasonCode.availability_history_building not in reason_codes
    coverage_codes = {item.label_code for item in story.coverage}
    assert CoverageLabelCode.availability_history_building not in coverage_codes


def test_old_unknown_snapshot_coverage_does_not_leak_into_current_story(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", availability="online")
    nodes = _topology_gap_nodes()
    _store_snapshot(
        repo,
        "snap-old",
        captured_at=NOW - timedelta(days=3),
        links=[{"source": "0x02", "target": "0x03", "linkquality": 90}],
        nodes=nodes,
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x03", "linkquality": 120}],
        nodes=nodes,
    )

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    reason_codes = {reason.code for reason in story.reasons}
    assert ReasonCode.availability_status_unknown not in reason_codes
    coverage_codes = {item.label_code for item in story.coverage}
    assert CoverageLabelCode.availability_status_unknown not in coverage_codes


def test_old_topology_snapshot_age_does_not_emit_snapshot_stale(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", battery=80, linkquality=120)
    _enable_availability_tracking(repo, "0x03", changed_at=NOW - timedelta(days=30))
    _link_ha_area(repo, "0x03")
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW - timedelta(days=30),
        links=[
            {
                "source": "0x02",
                "target": "0x03",
                "linkquality": 120,
                "routes": [{"destination": "0x01"}],
            }
        ],
    )

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    coverage_codes = {item.label_code for item in story.coverage}
    assert CoverageLabelCode.snapshot_stale not in coverage_codes


def test_low_current_lqi_alone_does_not_produce_watch_story(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", battery=80, linkquality=30)
    _enable_availability_tracking(repo, "0x03", changed_at=NOW - timedelta(days=3))
    _link_ha_area(repo, "0x03")
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[
            {
                "source": "0x02",
                "target": "0x03",
                "linkquality": 30,
                "routes": [{"destination": "0x01"}],
            }
        ],
    )

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    reason_codes = {reason.code for reason in story.reasons}
    assert ReasonCode.reported_lqi_low not in reason_codes
    assert story.status is DecisionStatus.no_notable_change
    assert story.headline_code == HeadlineCode.no_notable_signals


def test_passive_hints_do_not_feed_device_story_outcomes(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", battery=80, linkquality=120)
    _upsert_device(repo, "0x02")
    _enable_availability_tracking(repo, "0x03", changed_at=NOW - timedelta(days=3))
    _enable_availability_tracking(repo, "0x02", changed_at=NOW - timedelta(days=3))
    _link_ha_area(repo, "0x03")
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[
            {
                "source": "0x02",
                "target": "0x03",
                "linkquality": 120,
                "routes": [{"destination": "0x01"}],
            }
        ],
    )
    for offset in range(3):
        changed_at = NOW - timedelta(days=6 - offset)
        repo.availability.insert_availability_change("home", "0x03", "online", "offline")
        repo.db.conn.execute(
            "UPDATE availability_changes SET changed_at = ? WHERE rowid = last_insert_rowid()",
            (changed_at.isoformat(),),
        )
        repo.availability.insert_availability_change("home", "0x02", "online", "offline")
        repo.db.conn.execute(
            "UPDATE availability_changes SET changed_at = ? WHERE rowid = last_insert_rowid()",
            ((changed_at + timedelta(minutes=5)).isoformat(),),
        )
    repo.db.conn.commit()

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    reason_codes = {reason.code for reason in story.reasons}
    assert ReasonCode.passive_instability_hint_present not in reason_codes
    assert story.headline_code != HeadlineCode.data_coverage_gaps


def test_device_story_timeline_is_empty(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", availability="offline")
    _enable_availability_tracking(repo, "0x03", changed_at=NOW - timedelta(days=1))
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x03", "linkquality": 120}],
    )

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    assert story.timeline == []


def test_no_notable_change_when_evidence_is_healthy_and_ha_linked(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", battery=80, linkquality=120)
    _enable_availability_tracking(repo, "0x03", changed_at=NOW - timedelta(days=3))
    _link_ha_area(repo, "0x03")
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[
            {
                "source": "0x02",
                "target": "0x03",
                "linkquality": 120,
                "routes": [{"destination": "0x01"}],
            }
        ],
    )

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    assert story.status is DecisionStatus.no_notable_change
    assert story.headline_code == HeadlineCode.no_notable_signals


def test_device_story_outputs_codes_not_prose(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", availability="offline", battery=10)
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x03", "linkquality": 120}],
    )

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    payload = story.model_dump(mode="json")
    text = str(payload).lower()
    assert "caused by" not in text
    assert "broken link" not in text
    assert "parent router" not in text
    for reason in story.reasons:
        assert reason.code
        assert " " not in reason.code


def test_device_story_is_deterministic(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", availability="offline")
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x03", "linkquality": 120}],
    )

    first = device_story_for_device(repo, "home", "0x03", now=NOW)
    second = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert first == second


def test_build_device_story_from_loaded_evidence(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", availability="offline")
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x03", "linkquality": 120}],
    )

    evidence = load_device_story_evidence(repo, "home", "0x03", now=NOW)
    assert evidence is not None
    story = build_device_story(evidence, now=NOW)
    assert story.subject_id == "0x03"


RHYTHM_BASE = datetime(2026, 7, 13, 0, 0, 0, tzinfo=timezone.utc)


def _insert_payload_snapshot(
    repo: Repository,
    ieee: str,
    *,
    last_payload_at: datetime,
) -> None:
    payload_at = last_payload_at.isoformat()
    repo.db.conn.execute(
        """
        INSERT INTO device_snapshots (
            network_id, ieee_address, availability, last_seen, last_payload_at,
            linkquality, battery, payload_json, captured_at
        ) VALUES ('home', ?, 'online', ?, ?, 120, 80, '{}', ?)
        """,
        (ieee, payload_at, payload_at, payload_at),
    )
    repo.db.conn.commit()


def _seed_regular_payload_observations(
    repo: Repository,
    ieee: str,
    *,
    start: datetime,
    count: int = 9,
    interval_minutes: int = 60,
) -> list[datetime]:
    observations = [
        start + timedelta(minutes=interval_minutes * index) for index in range(count)
    ]
    for observed_at in observations:
        _insert_payload_snapshot(repo, ieee, last_payload_at=observed_at)
    return observations


def _healthy_sleepy_story_setup(repo: Repository, ieee: str = "0x03") -> None:
    _enable_availability_tracking(repo, ieee, changed_at=NOW - timedelta(days=3))
    _link_ha_area(repo, ieee)
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[
            {
                "source": "0x02",
                "target": ieee,
                "linkquality": 120,
                "routes": [{"destination": "0x01"}],
            }
        ],
    )


def test_sleepy_device_within_expected_rhythm_is_not_flagged(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", battery=80, linkquality=120)
    observations = _seed_regular_payload_observations(
        repo,
        "0x03",
        start=RHYTHM_BASE,
        interval_minutes=60,
    )
    _healthy_sleepy_story_setup(repo)
    now = observations[-1] + timedelta(minutes=90)

    story = device_story_for_device(repo, "home", "0x03", now=now)
    assert story is not None
    assert story.status is DecisionStatus.no_notable_change
    assert story.headline_code == HeadlineCode.no_notable_signals
    reason_codes = {reason.code for reason in story.reasons}
    assert ReasonCode.reporting_silence_beyond_expected not in reason_codes
    assert ReasonCode.observed_reporting_rhythm not in reason_codes


def test_sleepy_device_beyond_expected_rhythm_is_watch(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", battery=80, linkquality=120)
    observations = _seed_regular_payload_observations(
        repo,
        "0x03",
        start=RHYTHM_BASE,
        interval_minutes=60,
    )
    _healthy_sleepy_story_setup(repo)
    now = observations[-1] + timedelta(hours=4)

    story = device_story_for_device(repo, "home", "0x03", now=now)
    assert story is not None
    assert story.status is DecisionStatus.watch
    assert story.priority is DecisionPriority.low
    assert story.headline_code == HeadlineCode.extended_reporting_silence
    assert any(
        reason.code == ReasonCode.observed_reporting_rhythm for reason in story.reasons
    )
    assert any(
        reason.code == ReasonCode.reporting_silence_beyond_expected
        for reason in story.reasons
    )
    assert any(
        limitation.code == "extended_silence_not_failure"
        for limitation in story.limitations
    )
    beyond_reason = next(
        reason
        for reason in story.reasons
        if reason.code == ReasonCode.reporting_silence_beyond_expected
    )
    assert beyond_reason.params["silence_minutes"] == 240
    assert beyond_reason.params["extended_silence_threshold_minutes"] == 150
    assert "suspicion_threshold_minutes" not in beyond_reason.params
    observed_reason = next(
        reason
        for reason in story.reasons
        if reason.code == ReasonCode.observed_reporting_rhythm
    )
    assert observed_reason.params["interval_minutes_p25"] == 60
    assert observed_reason.params["interval_minutes_median"] == 60
    assert observed_reason.params["interval_minutes_p75"] == 60
    assert observed_reason.params["interval_minutes_max"] == 60


def test_beyond_expected_rhythm_with_current_issue_is_worth_reviewing(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", availability="offline", battery=80, linkquality=120)
    observations = _seed_regular_payload_observations(
        repo,
        "0x03",
        start=RHYTHM_BASE,
        interval_minutes=60,
    )
    _healthy_sleepy_story_setup(repo)
    now = observations[-1] + timedelta(hours=4)

    story = device_story_for_device(repo, "home", "0x03", now=now)
    assert story is not None
    assert story.status is DecisionStatus.worth_reviewing
    assert story.headline_code == HeadlineCode.current_issue_present
    assert any(
        reason.code == ReasonCode.reporting_silence_beyond_expected
        for reason in story.reasons
    )


def test_insufficient_rhythm_history_does_not_add_silence_reasons(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", battery=80, linkquality=120)
    _seed_regular_payload_observations(
        repo,
        "0x03",
        start=RHYTHM_BASE,
        count=5,
        interval_minutes=60,
    )
    _healthy_sleepy_story_setup(repo)
    now = RHYTHM_BASE + timedelta(hours=12)

    story = device_story_for_device(repo, "home", "0x03", now=now)
    assert story is not None
    reason_codes = {reason.code for reason in story.reasons}
    assert ReasonCode.reporting_silence_beyond_expected not in reason_codes
    assert ReasonCode.observed_reporting_rhythm not in reason_codes


def _seed_long_interval_payload_observations(
    repo: Repository,
    ieee: str,
) -> list[datetime]:
    observations = [
        RHYTHM_BASE,
        RHYTHM_BASE + timedelta(minutes=40),
        RHYTHM_BASE + timedelta(minutes=80),
        RHYTHM_BASE + timedelta(minutes=120),
        RHYTHM_BASE + timedelta(hours=20),
        RHYTHM_BASE + timedelta(hours=20, minutes=40),
        RHYTHM_BASE + timedelta(hours=21, minutes=20),
        RHYTHM_BASE + timedelta(hours=22),
        RHYTHM_BASE + timedelta(hours=22, minutes=40),
    ]
    for observed_at in observations:
        _insert_payload_snapshot(repo, ieee, last_payload_at=observed_at)
    return observations


def test_long_interval_cadence_four_hour_silence_is_not_watch(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", battery=80, linkquality=120)
    observations = _seed_long_interval_payload_observations(repo, "0x03")
    _healthy_sleepy_story_setup(repo)
    now = observations[-1] + timedelta(hours=4)

    story = device_story_for_device(repo, "home", "0x03", now=now)
    assert story is not None
    assert story.status is DecisionStatus.no_notable_change
    assert story.headline_code == HeadlineCode.no_notable_signals
    reason_codes = {reason.code for reason in story.reasons}
    assert ReasonCode.reporting_silence_beyond_expected not in reason_codes


def test_long_interval_cadence_silence_beyond_threshold_is_watch(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", battery=80, linkquality=120)
    observations = _seed_long_interval_payload_observations(repo, "0x03")
    _healthy_sleepy_story_setup(repo)
    now = observations[-1] + timedelta(hours=19)

    story = device_story_for_device(repo, "home", "0x03", now=now)
    assert story is not None
    assert story.status is DecisionStatus.watch
    assert story.headline_code == HeadlineCode.extended_reporting_silence
    assert any(
        reason.code == ReasonCode.reporting_silence_beyond_expected
        for reason in story.reasons
    )


def test_future_latest_payload_observation_does_not_trigger_rhythm_watch(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", battery=80, linkquality=120)
    observations = _seed_regular_payload_observations(
        repo,
        "0x03",
        start=RHYTHM_BASE,
        interval_minutes=60,
    )
    _healthy_sleepy_story_setup(repo)
    now = observations[-1] - timedelta(hours=1)

    story = device_story_for_device(repo, "home", "0x03", now=now)
    assert story is not None
    assert story.status is DecisionStatus.no_notable_change
    assert story.headline_code == HeadlineCode.no_notable_signals
    reason_codes = {reason.code for reason in story.reasons}
    assert ReasonCode.reporting_silence_beyond_expected not in reason_codes
    assert ReasonCode.observed_reporting_rhythm not in reason_codes


LQI_BASE = datetime(2026, 7, 12, 0, 0, 0, tzinfo=timezone.utc)


def _upsert_router_device(
    repo: Repository,
    ieee: str,
    *,
    availability: str = "online",
    last_seen: datetime | None = None,
    battery: int | None = None,
    linkquality: int | None = None,
) -> None:
    repo.upsert_device(
        network_id="home",
        ieee_address=ieee,
        friendly_name=f"Device {ieee}",
        device_type="Router",
        power_source="Mains",
        interview_state="successful",
    )
    repo.update_device_current_state(
        network_id="home",
        ieee_address=ieee,
        availability=availability,
        last_seen=(last_seen or NOW).isoformat(),
        linkquality=linkquality,
        battery=battery,
    )


def _insert_lqi_snapshot(
    repo: Repository,
    ieee: str,
    *,
    linkquality: int,
    captured_at: datetime,
) -> None:
    captured = captured_at.isoformat()
    repo.db.conn.execute(
        """
        INSERT INTO device_snapshots (
            network_id, ieee_address, availability, last_seen, last_payload_at,
            linkquality, battery, payload_json, captured_at
        ) VALUES ('home', ?, 'online', NULL, NULL, ?, NULL, '{}', ?)
        """,
        (ieee, linkquality, captured),
    )
    repo.db.conn.commit()


def _seed_declining_lqi_observations(
    repo: Repository,
    ieee: str,
    *,
    start: datetime = LQI_BASE,
) -> None:
    values = [200] * 44 + [200, 200, 200, 80, 80, 80]
    for index, value in enumerate(values):
        _insert_lqi_snapshot(
            repo,
            ieee,
            linkquality=value,
            captured_at=start + timedelta(minutes=index),
        )


def _healthy_lqi_story_setup(repo: Repository, ieee: str = "0x03") -> None:
    _enable_availability_tracking(repo, ieee, changed_at=NOW - timedelta(days=3))
    _link_ha_area(repo, ieee)
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[
            {
                "source": "0x02",
                "target": ieee,
                "linkquality": 80,
                "routes": [{"destination": "0x01"}],
            }
        ],
    )


def test_declining_lqi_trend_alone_does_not_escalate(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_router_device(repo, "0x03", linkquality=80)
    _seed_declining_lqi_observations(repo, "0x03")
    _healthy_lqi_story_setup(repo)

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    reason_codes = {reason.code for reason in story.reasons}
    assert ReasonCode.observed_lqi_trend not in reason_codes
    assert ReasonCode.reported_lqi_declining not in reason_codes
    assert story.status is DecisionStatus.no_notable_change
    assert story.headline_code == HeadlineCode.no_notable_signals


def test_declining_lqi_trend_with_stale_last_seen_is_watch(tmp_path: Path):
    repo = _repo(tmp_path)
    stale = NOW - timedelta(hours=72)
    _upsert_router_device(repo, "0x03", linkquality=80, last_seen=stale)
    _seed_declining_lqi_observations(repo, "0x03")
    _healthy_lqi_story_setup(repo)

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    assert story.status is DecisionStatus.watch
    assert story.priority is DecisionPriority.low
    assert story.headline_code == HeadlineCode.reported_link_quality_changed
    assert any(reason.code == ReasonCode.observed_lqi_trend for reason in story.reasons)
    assert any(reason.code == ReasonCode.reported_lqi_declining for reason in story.reasons)
    assert any(reason.code == ReasonCode.last_seen_stale for reason in story.reasons)
    assert any(
        limitation.code == "reported_lqi_not_path_failure"
        for limitation in story.limitations
    )


def test_declining_lqi_trend_with_current_issue_is_worth_reviewing(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_router_device(repo, "0x03", availability="offline", linkquality=80)
    _seed_declining_lqi_observations(repo, "0x03")
    _healthy_lqi_story_setup(repo)

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    assert story.status is DecisionStatus.worth_reviewing
    assert story.headline_code == HeadlineCode.current_issue_present
    assert any(reason.code == ReasonCode.reported_lqi_declining for reason in story.reasons)


def test_declining_lqi_trend_with_topology_gap_uses_topology_headline(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_router_device(repo, "0x03", linkquality=80)
    _seed_declining_lqi_observations(repo, "0x03")
    _store_topology_gap_fixtures(repo)

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    assert story.headline_code == HeadlineCode.topology_evidence_gap
    assert any(reason.code == ReasonCode.reported_lqi_declining for reason in story.reasons)


def test_stable_lqi_trend_does_not_add_reasons(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_router_device(repo, "0x03", linkquality=120)
    values = [120, 118, 116, 115, 114, 113]
    for index, value in enumerate(values):
        _insert_lqi_snapshot(
            repo,
            "0x03",
            linkquality=value,
            captured_at=LQI_BASE + timedelta(minutes=index),
        )
    _healthy_lqi_story_setup(repo)

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    reason_codes = {reason.code for reason in story.reasons}
    assert ReasonCode.observed_lqi_trend not in reason_codes
    assert ReasonCode.reported_lqi_declining not in reason_codes


def _store_recent_missing_link_corroboration_fixtures(
    repo: Repository,
    ieee: str = "0x03",
) -> None:
    nodes = {
        "0x01": {"type": "Coordinator"},
        "0x02": {"type": "Router"},
        ieee: {"type": "Router"},
    }
    _store_snapshot(
        repo,
        "snap-old",
        captured_at=NOW - timedelta(days=1),
        links=[{"source": ieee, "target": "0x01", "linkquality": 100}],
        nodes=nodes,
    )
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[
            {
                "source": "0x02",
                "target": ieee,
                "linkquality": 80,
                "routes": [{"destination": "0x01"}],
            }
        ],
        nodes=nodes,
    )


def test_declining_lqi_trend_escalates_with_recent_missing_links_without_topology_gap(
    tmp_path: Path,
):
    repo = _repo(tmp_path)
    ieee = "0x03"
    _upsert_router_device(repo, ieee, linkquality=80)
    _seed_declining_lqi_observations(repo, ieee)
    _enable_availability_tracking(repo, ieee, changed_at=NOW - timedelta(days=3))
    _link_ha_area(repo, ieee)
    _store_recent_missing_link_corroboration_fixtures(repo, ieee)

    evidence = load_device_story_evidence(repo, "home", ieee, now=NOW)
    assert evidence is not None
    assert evidence.recent_missing_link_count > 0
    from zigbeelens.decisions.topology_facts import TopologyFactCode

    assert TopologyFactCode.device_has_latest_links in {
        fact.code for fact in evidence.topology_facts
    }

    story = device_story_for_device(repo, "home", ieee, now=NOW)
    assert story is not None
    reason_codes = {reason.code for reason in story.reasons}
    assert ReasonCode.latest_snapshot_no_links not in reason_codes
    assert ReasonCode.reporting_silence_beyond_expected not in reason_codes
    assert ReasonCode.observed_lqi_trend in reason_codes
    assert ReasonCode.reported_lqi_declining in reason_codes
    assert story.status is DecisionStatus.watch
    assert story.priority is DecisionPriority.low
    assert story.headline_code == HeadlineCode.reported_link_quality_changed


def _offline_transition(repo: Repository, ieee: str, at: datetime) -> None:
    repo.availability.insert_availability_change("home", ieee, "online", "offline")
    repo.db.conn.execute(
        "UPDATE availability_changes SET changed_at = ? WHERE rowid = last_insert_rowid()",
        (at.isoformat(),),
    )
    repo.db.conn.commit()


def _seed_qualifying_model_pattern(
    repo: Repository,
    *,
    manufacturer: str | None = "IKEA",
    model: str = "TS011F",
    device_prefix: str = "0xm",
) -> list[str]:
    devices = [f"{device_prefix}{i:02d}" for i in range(MODEL_PATTERN_MIN_GROUP_SIZE)]
    for ieee in devices:
        _upsert_device(repo, ieee, manufacturer=manufacturer, model=model)
    base = NOW - timedelta(days=1)
    for ieee in devices[:MODEL_PATTERN_MIN_AFFECTED_COUNT]:
        _offline_transition(repo, ieee, base)
    return devices


def test_model_pattern_attaches_only_to_exact_model_identity(tmp_path: Path):
    repo = _repo(tmp_path)
    devices = _seed_qualifying_model_pattern(repo)
    affected_story = device_story_for_device(repo, "home", devices[0], now=NOW)
    _upsert_device(repo, "0xother", manufacturer="IKEA", model="OTHER")
    other_model_story = device_story_for_device(repo, "home", "0xother", now=NOW)

    assert affected_story is not None
    assert any(reason.code == ReasonCode.model_pattern_observed for reason in affected_story.reasons)
    assert other_model_story is not None
    assert not any(
        reason.code == ReasonCode.model_pattern_observed for reason in other_model_story.reasons
    )


def test_model_pattern_does_not_match_manufacturer_only(tmp_path: Path):
    repo = _repo(tmp_path)
    _seed_qualifying_model_pattern(repo)
    _upsert_device(repo, "0xpartial", manufacturer="IKEA", model="PARTIAL")
    story = device_story_for_device(repo, "home", "0xpartial", now=NOW)
    assert story is not None
    assert not any(reason.code == ReasonCode.model_pattern_observed for reason in story.reasons)


def test_affected_device_uses_affected_device_wording(tmp_path: Path):
    repo = _repo(tmp_path)
    devices = _seed_qualifying_model_pattern(repo)
    story = device_story_for_device(repo, "home", devices[0], now=NOW)
    assert story is not None
    reason = next(
        reason for reason in story.reasons if reason.code == ReasonCode.model_pattern_observed
    )
    assert reason.params["current_device_affected"] is True


def test_unaffected_same_group_device_stays_informational(tmp_path: Path):
    repo = _repo(tmp_path)
    devices = _seed_qualifying_model_pattern(repo)
    unaffected = devices[-1]
    story = device_story_for_device(repo, "home", unaffected, now=NOW)
    assert story is not None
    reason = next(
        reason for reason in story.reasons if reason.code == ReasonCode.model_pattern_observed
    )
    assert reason.params["current_device_affected"] is False
    assert story.status is DecisionStatus.informational
    assert story.status not in {DecisionStatus.worth_reviewing, DecisionStatus.review_first}


def test_unaffected_device_is_not_escalated_solely_by_model_pattern(tmp_path: Path):
    repo = _repo(tmp_path)
    devices = _seed_qualifying_model_pattern(repo)
    story = device_story_for_device(repo, "home", devices[-1], now=NOW)
    assert story is not None
    assert story.status not in {DecisionStatus.worth_reviewing, DecisionStatus.review_first}


def test_model_pattern_includes_no_blame_limitation_and_checks(tmp_path: Path):
    repo = _repo(tmp_path)
    devices = _seed_qualifying_model_pattern(repo)
    story = device_story_for_device(repo, "home", devices[0], now=NOW)
    assert story is not None
    assert any(
        limitation.code == "model_pattern_not_causal" for limitation in story.limitations
    )
    check_codes = {check.code for check in story.suggested_checks}
    assert CheckCode.compare_same_model_device_context in check_codes
    assert CheckCode.review_same_model_availability_history in check_codes


def test_tiny_group_does_not_attach_model_pattern(tmp_path: Path):
    repo = _repo(tmp_path)
    for ieee in ["0xs0", "0xs1", "0xs2"]:
        _upsert_device(repo, ieee, manufacturer="IKEA", model="TS011F")
        _offline_transition(repo, ieee, NOW - timedelta(days=1))
    story = device_story_for_device(repo, "home", "0xs0", now=NOW)
    assert story is not None
    assert not any(
        reason.code == ReasonCode.model_pattern_observed for reason in story.reasons
    )


def test_stored_model_identity_key_requires_exact_model():
    assert stored_model_identity_key("IKEA", "TS011F") == stored_model_identity_key("IKEA", "TS011F")
    assert stored_model_identity_key("IKEA", "TS011F") != stored_model_identity_key("Aqara", "TS011F")
    assert stored_model_identity_key(None, "TS011F") == "|ts011f"
    assert stored_model_identity_key("IKEA", None) is None


def test_qualifying_pattern_for_device_requires_membership():
    from zigbeelens.decisions.model_pattern import ObservedModelPattern

    pattern = ObservedModelPattern(
        pattern_id="model-pattern-test",
        manufacturer="IKEA",
        model="TS011F",
        group_size=5,
        affected_count=3,
        member_ieees=["0xm00", "0xm01", "0xm02", "0xm03", "0xm04"],
        affected_ieees=["0xm00", "0xm01", "0xm02"],
    )
    match = qualifying_pattern_for_device(
        [pattern],
        manufacturer="IKEA",
        model="TS011F",
        device_ieee="0xm04",
    )
    assert match is not None
    assert match[1] is False
    assert qualifying_pattern_for_device(
        [pattern], manufacturer="IKEA", model="OTHER", device_ieee="0xm04"
    ) is None
