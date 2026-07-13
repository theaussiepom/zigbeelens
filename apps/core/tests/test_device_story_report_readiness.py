"""Report-readiness tests for Device Story transport (Phase 4A-4)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.device_story import (
    DEVICE_STORY_HEADLINE_CODES,
    device_story_for_device,
    device_story_report_payload,
)
from zigbeelens.decisions.reasons import ReasonCode
from zigbeelens.storage.repository import Repository
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


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "device-story-report.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "device-story-report.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    return repo


def _upsert_device(repo: Repository, ieee: str, *, availability: str = "online") -> None:
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
    )


def _store_snapshot(repo: Repository, snapshot_id: str, *, links: list[dict]) -> None:
    repo.create_topology_snapshot(
        snapshot_id=snapshot_id,
        network_id="home",
        requested_by="test",
        status="pending",
        warning_acknowledged=True,
    )
    parsed = parse_networkmap_payload(
        {
            "nodes": {
                "0x01": {"type": "Coordinator"},
                "0x02": {"type": "Router"},
                "0x03": {"type": "EndDevice"},
            },
            "links": links,
        }
    )
    repo.store_topology_parsed(snapshot_id, "home", parsed, status="complete")
    repo.db.conn.execute(
        "UPDATE topology_snapshots SET captured_at = ? WHERE snapshot_id = ?",
        (NOW.isoformat(), snapshot_id),
    )
    repo.db.conn.commit()


def test_device_story_report_payload_matches_api_contract(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03")
    _store_snapshot(
        repo,
        "snap-latest",
        links=[{"source": "0x02", "target": "0x03", "linkquality": 120}],
    )

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    payload = device_story_report_payload(story)

    assert set(payload.keys()) == STORY_TOP_LEVEL_KEYS
    assert payload == story.model_dump(mode="json")
    assert payload["subject_type"] == "device"
    assert payload["headline_code"] in DEVICE_STORY_HEADLINE_CODES


def test_device_story_report_payload_remains_coded_not_prose(tmp_path: Path):
    repo = _repo(tmp_path)
    _upsert_device(repo, "0x03", availability="offline")
    _store_snapshot(repo, "snap-latest", links=[])

    story = device_story_for_device(repo, "home", "0x03", now=NOW)
    assert story is not None
    payload = device_story_report_payload(story)
    text = str(payload).lower()

    assert "caused by" not in text
    assert "broken link" not in text
    assert "parent router" not in text
    assert ReasonCode.current_issue_present in {reason["code"] for reason in payload["reasons"]}
