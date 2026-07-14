"""Device decision badge composition tests (Phase 5B-1)."""

from __future__ import annotations

from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.device_story import device_story_for_device
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.services.device_decision_badge import (
    device_decision_badge_for_device,
    device_decision_badge_from_story,
)
from zigbeelens.services.payload_builder import PayloadBuilder
from zigbeelens.storage.repository import Repository


def _repo(tmp_path: Path) -> tuple[Repository, AppConfig]:
    db_path = tmp_path / "device-decision-badge.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(db_path)),
    )
    repo.sync_networks(config.networks)
    return repo, config


def _add_device(
    repo: Repository,
    ieee: str,
    *,
    availability: str = "online",
) -> None:
    repo.upsert_device(
        network_id="home",
        ieee_address=ieee,
        friendly_name=f"Device {ieee}",
        device_type="EndDevice",
        power_source="Mains",
    )
    repo.ensure_device_current_state("home", ieee)
    repo.update_device_current_state(
        network_id="home",
        ieee_address=ieee,
        availability=availability,
    )


def test_badge_matches_device_story_status_priority_and_headline(tmp_path: Path):
    repo, _ = _repo(tmp_path)
    _add_device(repo, "0xa1", availability="offline")
    story = device_story_for_device(repo, "home", "0xa1")
    assert story is not None
    badge = device_decision_badge_from_story(story)
    assert badge.status == str(story.status)
    assert badge.priority == str(story.priority)
    assert badge.headline_code == str(story.headline_code)


def test_badge_for_device_helper_matches_story(tmp_path: Path):
    repo, _ = _repo(tmp_path)
    _add_device(repo, "0xa1", availability="online")
    story = device_story_for_device(repo, "home", "0xa1")
    badge = device_decision_badge_for_device(repo, "home", "0xa1")
    assert story is not None
    assert badge is not None
    assert badge.status == str(story.status)
    assert badge.headline_code == str(story.headline_code)


def test_device_list_payload_includes_decision_badge(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "0xa1", availability="offline")
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    devices = PayloadBuilder(config, repo, health).devices()
    assert len(devices) == 1
    assert devices[0].decision is not None
    story = device_story_for_device(repo, "home", "0xa1")
    assert story is not None
    assert devices[0].decision.status == str(story.status)
    assert devices[0].decision.headline_code == str(story.headline_code)


def test_unknown_device_returns_no_badge(tmp_path: Path):
    repo, _ = _repo(tmp_path)
    assert device_decision_badge_for_device(repo, "home", "0xmissing") is None
