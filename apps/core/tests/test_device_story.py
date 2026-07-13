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
from zigbeelens.decisions.reasons import ReasonCode
from zigbeelens.decisions.types import DecisionStatus
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
        linkquality=linkquality,
        battery=battery,
    )


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


def test_device_story_headline_codes_are_stable():
    assert "current_issue_present" in DEVICE_STORY_HEADLINE_CODES
    assert "topology_evidence_gap" in DEVICE_STORY_HEADLINE_CODES


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


def test_topology_gap_without_latest_links_but_earlier_snapshot_links(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    nodes = {
        "0x01": {"type": "Coordinator"},
        "0x02": {"type": "Router"},
        "0x03": {"type": "EndDevice"},
    }
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

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    assert story.status is DecisionStatus.worth_reviewing
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
    repo.availability.insert_availability_change(
        "home", "0x03", "unknown", "online"
    )
    repo.db.conn.execute(
        "UPDATE availability_changes SET changed_at = ? WHERE rowid = last_insert_rowid()",
        ((NOW - timedelta(days=1)).isoformat(),),
    )
    repo.db.conn.commit()
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x03", "linkquality": 120}],
    )

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    assert story.status is DecisionStatus.watch
    assert story.headline_code == HeadlineCode.stale_last_seen
    assert any(reason.code == ReasonCode.last_seen_stale for reason in story.reasons)


def test_low_battery_watch_status(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", battery=12)
    repo.availability.insert_availability_change(
        "home", "0x03", "unknown", "online"
    )
    repo.db.conn.execute(
        "UPDATE availability_changes SET changed_at = ? WHERE rowid = last_insert_rowid()",
        ((NOW - timedelta(days=1)).isoformat(),),
    )
    repo.db.conn.commit()
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x03", "linkquality": 120}],
    )

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    assert story.status is DecisionStatus.watch
    assert story.headline_code == HeadlineCode.low_battery
    assert any(reason.code == ReasonCode.battery_low for reason in story.reasons)


def test_route_hints_unavailable_adds_limitation_not_alarm(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    repo.availability.insert_availability_change(
        "home", "0x03", "unknown", "online"
    )
    repo.db.conn.execute(
        "UPDATE availability_changes SET changed_at = ? WHERE rowid = last_insert_rowid()",
        ((NOW - timedelta(days=1)).isoformat(),),
    )
    repo.db.conn.commit()
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0x03", "linkquality": 120, "routes": []}],
    )

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    assert any(reason.code == ReasonCode.route_hints_unavailable for reason in story.reasons)
    assert any(
        limitation.code == "route_hints_not_live_routing"
        for limitation in story.limitations
    )


def test_informational_when_ha_areas_are_not_linked(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", battery=80, linkquality=120)
    repo.availability.insert_availability_change(
        "home", "0x03", "unknown", "online"
    )
    repo.db.conn.execute(
        "UPDATE availability_changes SET changed_at = ? WHERE rowid = last_insert_rowid()",
        ((NOW - timedelta(days=1)).isoformat(),),
    )
    repo.db.conn.commit()
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
    assert story.headline_code == HeadlineCode.data_coverage_gaps
    assert any(reason.code == ReasonCode.ha_areas_not_linked for reason in story.reasons)


def test_no_notable_change_when_evidence_is_healthy_and_ha_linked(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", battery=80, linkquality=120)
    repo.availability.insert_availability_change(
        "home", "0x03", "unknown", "online"
    )
    repo.db.conn.execute(
        "UPDATE availability_changes SET changed_at = ? WHERE rowid = last_insert_rowid()",
        ((NOW - timedelta(days=3)).isoformat(),),
    )
    repo.db.conn.commit()
    repo.db.conn.execute(
        """
        INSERT INTO ha_device_enrichment (
            network_id, ieee_address, entity_id, area_id, area_name,
            match_confidence, updated_at
        ) VALUES ('home', '0x03', 'light.kitchen', 'area-1', 'Kitchen', 'high', ?)
        """,
        (NOW.isoformat(),),
    )
    repo.db.conn.commit()
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
