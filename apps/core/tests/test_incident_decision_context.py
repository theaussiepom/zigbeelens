"""Incident affected-device Device Story decision context (Phase 5C-1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.device_story import device_story_for_device
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.mock.device_stories import (
    apply_incident_device_story_badges,
    build_device_stories_for_scenario,
)
from zigbeelens.mock.fixtures import BUILDERS, NOW, get_scenario
from zigbeelens.schemas import DeviceDecisionBadge
from zigbeelens.services.device_decision_badge import (
    device_decision_badge_from_story,
    device_decision_badges_for_devices,
)
from zigbeelens.services.mock_provider import MockProvider
from zigbeelens.services.payload_builder import PayloadBuilder
from zigbeelens.storage.incident_collection import build_incident_collection_query
from zigbeelens.storage.repository import Repository

REF_NOW = datetime(2026, 7, 13, 2, 0, 0, tzinfo=timezone.utc)


def _repo(
    tmp_path: Path, *, networks: list[NetworkConfig] | None = None
) -> tuple[Repository, AppConfig]:
    db_path = tmp_path / "incident-decision.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    network_cfgs = networks or [
        NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")
    ]
    config = AppConfig(
        mode=ModeConfig(mock=False),
        networks=network_cfgs,
        storage=StorageConfig(path=str(db_path)),
    )
    repo.sync_networks(config.networks)
    return repo, config


def _add_device(
    repo: Repository,
    ieee: str,
    *,
    network_id: str = "home",
    availability: str = "online",
    last_seen: datetime | None = None,
    battery: int | None = None,
    friendly_name: str | None = None,
) -> None:
    repo.upsert_device(
        network_id=network_id,
        ieee_address=ieee,
        friendly_name=friendly_name or f"Device {ieee}",
        device_type="EndDevice",
        power_source="Battery" if battery is not None else "Mains",
    )
    repo.ensure_device_current_state(network_id, ieee)
    repo.update_device_current_state(
        network_id=network_id,
        ieee_address=ieee,
        availability=availability,
        last_seen=(last_seen or REF_NOW).isoformat(),
        battery=battery,
    )


def _link_device(repo: Repository, incident_id: str, ieee: str, *, network_id: str = "home") -> None:
    repo.db.conn.execute(
        """
        INSERT INTO incident_devices (incident_id, network_id, ieee_address, role)
        VALUES (?, ?, ?, 'affected')
        """,
        (incident_id, network_id, ieee),
    )
    repo.db.conn.commit()


def _insert_incident(
    repo: Repository,
    incident_id: str,
    *,
    title: str = "Incident",
    summary: str = "Recorded summary",
    explanation: str = "Recorded explanation",
    lifecycle_state: str = "open",
    opened_at: datetime | None = None,
) -> None:
    when = (opened_at or REF_NOW).isoformat()
    repo.insert_incident(
        incident_id=incident_id,
        dedup_key=f"dedup-{incident_id}",
        incident_type="single_device_unavailable",
        lifecycle_state=lifecycle_state,
        severity="incident",
        scope="device",
        confidence="medium",
        title=title,
        summary=summary,
        explanation=explanation,
        evidence=["stored evidence"],
        counter_evidence=["stored counter"],
        limitations=["stored limitation"],
        opened_at=when,
        updated_at=when,
    )


def test_incidents_batch_compose_unique_device_rows_once(tmp_path: Path):
    repo, config = _repo(tmp_path)
    for ieee in ("0xa1", "0xa2", "0xa3", "0xa4"):
        _add_device(repo, ieee, availability="offline" if ieee in {"0xa1", "0xa2"} else "online")

    _insert_incident(repo, "inc-1")
    _link_device(repo, "inc-1", "0xa1")
    _link_device(repo, "inc-1", "0xa2")

    _insert_incident(repo, "inc-2")
    _link_device(repo, "inc-2", "0xa1")  # overlap
    _link_device(repo, "inc-2", "0xa3")

    _insert_incident(repo, "inc-3")
    _link_device(repo, "inc-3", "0xa4")

    health = HealthDiagnosticService(config, repo)
    health.clock = MagicMock(now=lambda: REF_NOW)
    health.recalculate_all()
    spy = MagicMock(wraps=device_decision_badges_for_devices)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "zigbeelens.services.payload_builder.device_decision_badges_for_devices",
            spy,
        )
        incidents = PayloadBuilder(config, repo, health).incidents_page(
            build_incident_collection_query()
        )["items"]

    assert spy.call_count == 1
    rows = spy.call_args.args[1]
    keys = {(row.network_id, row.ieee_address) for row in rows}
    assert keys == {("home", "0xa1"), ("home", "0xa2"), ("home", "0xa3"), ("home", "0xa4")}
    assert len(rows) == 4

    by_id = {inc.id: inc for inc in incidents}
    assert by_id["inc-1"].affected_devices[0].decision is not None
    badge_a1_inc1 = next(
        d.decision for d in by_id["inc-1"].affected_devices if d.ieee_address == "0xa1"
    )
    badge_a1_inc2 = next(
        d.decision for d in by_id["inc-2"].affected_devices if d.ieee_address == "0xa1"
    )
    assert badge_a1_inc1 == badge_a1_inc2


def test_incidents_multi_network_batches_once_with_story_parity(tmp_path: Path):
    repo, config = _repo(
        tmp_path,
        networks=[
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
            NetworkConfig(id="office", name="Office", base_topic="zigbee2mqtt-office"),
        ],
    )
    _add_device(repo, "0xoff", network_id="home", availability="offline")
    _add_device(
        repo,
        "0xstale",
        network_id="office",
        availability="online",
        last_seen=REF_NOW - timedelta(hours=50),
    )
    _add_device(repo, "0xok", network_id="office", availability="online")

    _insert_incident(repo, "inc-home")
    _link_device(repo, "inc-home", "0xoff", network_id="home")
    _insert_incident(repo, "inc-office")
    _link_device(repo, "inc-office", "0xstale", network_id="office")
    _link_device(repo, "inc-office", "0xok", network_id="office")

    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    builder = PayloadBuilder(config, repo, health)
    rows = repo.incidents.list_incidents()
    device_rows = builder._unique_device_rows_for_incidents(rows)
    badges = device_decision_badges_for_devices(repo, device_rows, now=REF_NOW)
    assert len(badges) == 3

    spy = MagicMock(wraps=device_decision_badges_for_devices)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "zigbeelens.services.payload_builder.device_decision_badges_for_devices",
            spy,
        )
        PayloadBuilder(config, repo, health).incidents_page(build_incident_collection_query())["items"]
    assert spy.call_count == 1

    incidents = [
        builder._incident_from_row(row, decision_badges=badges)
        for row in rows
        if row
    ]
    for inc in incidents:
        assert inc is not None
        for ref in inc.affected_devices:
            story = device_story_for_device(
                repo, ref.network_id, ref.ieee_address, now=REF_NOW
            )
            assert story is not None
            assert ref.decision == device_decision_badge_from_story(story)

    offline_ref = next(
        ref
        for inc in incidents
        if inc is not None
        for ref in inc.affected_devices
        if ref.ieee_address == "0xoff"
    )
    assert offline_ref.decision is not None
    assert offline_ref.decision.status == "worth_reviewing"


def test_incidents_list_batch_composer_called_once_across_networks(tmp_path: Path):
    repo, config = _repo(
        tmp_path,
        networks=[
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
            NetworkConfig(id="office", name="Office", base_topic="zigbee2mqtt-office"),
        ],
    )
    _add_device(repo, "0xa1", network_id="home", availability="offline")
    _add_device(repo, "0xb1", network_id="office", availability="online")
    _insert_incident(repo, "inc-1")
    _link_device(repo, "inc-1", "0xa1", network_id="home")
    _insert_incident(repo, "inc-2")
    _link_device(repo, "inc-2", "0xb1", network_id="office")

    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    spy = MagicMock(wraps=device_decision_badges_for_devices)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "zigbeelens.services.payload_builder.device_decision_badges_for_devices",
            spy,
        )
        PayloadBuilder(config, repo, health).incidents_page(build_incident_collection_query())["items"]
    assert spy.call_count == 1
    assert len(spy.call_args.args[1]) == 2


def test_missing_historical_device_keeps_identity_with_null_decision(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "0xalive", availability="online")
    _insert_incident(repo, "inc-hist")
    _link_device(repo, "inc-hist", "0xalive")
    _link_device(repo, "inc-hist", "0xmissing")

    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    incident = PayloadBuilder(config, repo, health).incident("inc-hist")
    assert incident is not None
    assert len(incident.affected_devices) == 2
    missing = next(d for d in incident.affected_devices if d.ieee_address == "0xmissing")
    alive = next(d for d in incident.affected_devices if d.ieee_address == "0xalive")
    assert missing.decision is None
    assert missing.network_id == "home"
    assert missing.friendly_name == "0xmissing"
    assert alive.decision is not None


def test_incident_from_row_does_not_compose_decisions(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "0xa1", availability="offline")
    _insert_incident(repo, "inc-1")
    _link_device(repo, "inc-1", "0xa1")
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    badge = DeviceDecisionBadge(
        status="worth_reviewing",
        priority="high",
        headline_code="current_issue_present",
        coverage_label_codes=[],
    )
    builder = PayloadBuilder(config, repo, health)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "zigbeelens.services.payload_builder.device_decision_badge_for_device",
            MagicMock(side_effect=AssertionError("must not call single badge helper")),
        )
        mp.setattr(
            "zigbeelens.decisions.device_story.device_story_for_device",
            MagicMock(side_effect=AssertionError("must not compose Device Story")),
        )
        row = repo.incidents.get_incident("inc-1")
        incident = builder._incident_from_row(
            row, decision_badges={("home", "0xa1"): badge}
        )
    assert incident is not None
    assert incident.affected_devices[0].decision == badge


def test_single_incident_batches_affected_devices_once(tmp_path: Path):
    repo, config = _repo(tmp_path)
    for ieee in ("0xa1", "0xa2", "0xa3"):
        _add_device(repo, ieee, availability="offline")
    _insert_incident(repo, "inc-many")
    for ieee in ("0xa1", "0xa2", "0xa3"):
        _link_device(repo, "inc-many", ieee)

    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    spy = MagicMock(wraps=device_decision_badges_for_devices)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "zigbeelens.services.payload_builder.device_decision_badges_for_devices",
            spy,
        )
        incident = PayloadBuilder(config, repo, health).incident("inc-many")
    assert incident is not None
    assert spy.call_count == 1
    assert len(spy.call_args.args[1]) == 3
    assert all(ref.decision is not None for ref in incident.affected_devices)


def test_resolved_incident_preserves_stored_fields_and_current_decision(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _add_device(
        repo,
        "0xa1",
        availability="online",
        last_seen=REF_NOW + timedelta(days=10),
    )
    _insert_incident(
        repo,
        "inc-resolved",
        title="Old outage",
        summary="Device was offline on Monday",
        explanation="Legacy explanation text",
        lifecycle_state="resolved",
        opened_at=REF_NOW - timedelta(days=2),
    )
    repo.db.conn.execute(
        "UPDATE incidents SET resolved_at = ? WHERE id = ?",
        ((REF_NOW - timedelta(days=1)).isoformat(), "inc-resolved"),
    )
    repo.db.conn.commit()
    _link_device(repo, "inc-resolved", "0xa1")

    health = HealthDiagnosticService(config, repo)
    health.clock = MagicMock(now=lambda: REF_NOW)
    health.recalculate_all()
    incident = PayloadBuilder(config, repo, health).incident("inc-resolved")
    assert incident is not None
    assert incident.status.value == "resolved"
    assert incident.summary == "Device was offline on Monday"
    assert incident.interpretation == "Legacy explanation text"
    assert [e.summary for e in incident.evidence] == ["stored evidence"]
    assert [e.summary for e in incident.counter_evidence] == ["stored counter"]
    assert [lim.summary for lim in incident.limitations] == ["stored limitation"]
    story = device_story_for_device(repo, "home", "0xa1", now=REF_NOW)
    assert story is not None
    assert incident.affected_devices[0].decision == device_decision_badge_from_story(
        story
    )


def test_scenario_incident_affected_decisions_match_stories():
    for scenario_id in BUILDERS:
        data = get_scenario(scenario_id)
        for incident in data.incidents:
            for ref in incident.affected_devices:
                key = (ref.network_id, ref.ieee_address)
                story = data.device_stories.get(key)
                if story is None:
                    assert ref.decision is None
                else:
                    assert ref.decision == device_decision_badge_from_story(story)


def test_apply_incident_device_story_badges_projects_from_stories_only():
    raw = BUILDERS["single_device_unavailable"]()
    stories = build_device_stories_for_scenario(raw, now=NOW)
    projected = apply_incident_device_story_badges(raw.incidents, stories)
    assert projected
    for incident in projected:
        for ref in incident.affected_devices:
            story = stories.get((ref.network_id, ref.ieee_address))
            if story is None:
                assert ref.decision is None
            else:
                assert ref.decision == device_decision_badge_from_story(story)


def test_scenario_incidents_api_does_not_bleed_live_repository(
    live_client: TestClient, tmp_path: Path
):
    scenario_id = "single_device_unavailable"
    provider = MockProvider(scenario_id)
    scenario_incidents = provider.incidents_complete_history()
    assert scenario_incidents
    scenario_ref = next(
        ref
        for inc in scenario_incidents
        for ref in inc.affected_devices
        if ref.decision is not None
    )

    ctx = live_client.app.state.ctx
    # Seed a live device with matching IDs but clearly different availability.
    _add_device(
        ctx.repo,
        scenario_ref.ieee_address,
        network_id=scenario_ref.network_id,
        availability="online",
        last_seen=REF_NOW,
    )
    live_story = device_story_for_device(
        ctx.repo, scenario_ref.network_id, scenario_ref.ieee_address, now=REF_NOW
    )
    assert live_story is not None
    live_badge = device_decision_badge_from_story(live_story)
    assert live_badge != scenario_ref.decision

    res = live_client.get("/api/incidents", params={"scenario": scenario_id})
    assert res.status_code == 200
    body = res.json()
    matched = None
    for item in body["items"]:
        for ref in item["affected_devices"]:
            if (
                ref["network_id"] == scenario_ref.network_id
                and ref["ieee_address"] == scenario_ref.ieee_address
            ):
                matched = ref
                break
    assert matched is not None
    assert matched["decision"] == scenario_ref.decision.model_dump(mode="json")
    assert matched["decision"]["status"] != live_badge.status


def test_incident_api_shape_includes_decision_and_legacy_fields(mock_client: TestClient):
    res = mock_client.get(
        "/api/incidents", params={"scenario": "single_device_unavailable"}
    )
    assert res.status_code == 200
    items = res.json()["items"]
    assert items
    incident = items[0]
    for key in (
        "type",
        "status",
        "severity",
        "scope",
        "confidence",
        "title",
        "summary",
        "interpretation",
        "network_ids",
        "affected_device_count",
        "affected_devices",
        "opened_at",
        "updated_at",
        "evidence",
        "counter_evidence",
        "limitations",
        "timeline",
        "conclusion",
    ):
        assert key in incident
    if incident["affected_devices"]:
        ref = incident["affected_devices"][0]
        for key in (
            "network_id",
            "ieee_address",
            "friendly_name",
            "health_primary",
            "lens_bucket",
            "lens_bucket_label",
            "lens_bucket_reason",
            "decision",
        ):
            assert key in ref
