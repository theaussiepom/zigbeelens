"""Phase 5D-1: Decision Engine report payload, batching, and scope filtering."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from zigbeelens.config.models import AppConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.device_story import (
    device_stories_for_devices,
    device_story_for_device,
    device_story_report_payload,
)
from zigbeelens.schemas import RedactionOptions, RedactionProfile, ReportRequest, ReportScope
from zigbeelens.services.data_service import DataService, ReportDeviceContext
from zigbeelens.services.device_decision_badge import (
    device_decision_badge_from_story,
    device_decision_badges_for_devices,
)
from zigbeelens.services.report_device_story import (
    coded_payload_excludes_identity,
    report_device_story_from_story,
)
from zigbeelens.services.reports import (
    generate_report,
    render_markdown,
    report_body_as_json,
    report_body_as_yaml,
)
from zigbeelens.storage.repository import Repository

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
SCENARIO = "four_devices_same_room_unavailable"


def _repo(tmp_path) -> tuple[Repository, AppConfig]:
    from zigbeelens.config.models import ModeConfig, NetworkConfig, StorageConfig

    db_path = tmp_path / "r.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = AppConfig(
        mode=ModeConfig(mock=False),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(db_path)),
    )
    repo.sync_networks(config.networks)
    return repo, config


def _add_device(repo: Repository, ieee: str, *, network_id: str = "home", **kwargs):
    repo.upsert_device(
        network_id=network_id,
        ieee_address=ieee,
        friendly_name=kwargs.get("friendly_name", ieee),
        device_type=kwargs.get("device_type", "EndDevice"),
        power_source=kwargs.get("power_source", "Mains"),
    )
    repo.ensure_device_current_state(network_id, ieee)
    repo.update_device_current_state(
        network_id=network_id,
        ieee_address=ieee,
        availability=kwargs.get("availability", "online"),
        last_seen=NOW.isoformat(),
    )


def _enable_tracking(repo: Repository, ieee: str, *, network_id: str = "home"):
    repo.availability.insert_availability_change(
        network_id, ieee, "unknown", "online"
    )
    repo.db.conn.execute(
        "UPDATE availability_changes SET changed_at = ? WHERE rowid = last_insert_rowid()",
        ((NOW - timedelta(days=3)).isoformat(),),
    )
    repo.db.conn.commit()


def test_device_stories_for_devices_one_network_context(monkeypatch, tmp_path):
    from zigbeelens.services.network_evidence_composition import (
        compose_network_evidence_context,
    )

    repo, _ = _repo(tmp_path)
    for ieee in ("0xa", "0xb"):
        _add_device(repo, ieee, friendly_name=ieee)
        _enable_tracking(repo, ieee)

    calls: list[str] = []
    original = compose_network_evidence_context

    def _wrap(r, network_id, **kwargs):
        calls.append(network_id)
        return original(r, network_id, **kwargs)

    monkeypatch.setattr(
        "zigbeelens.services.network_evidence_composition.compose_network_evidence_context",
        _wrap,
    )
    rows = [repo.get_device("home", "0xa"), repo.get_device("home", "0xb")]
    stories = device_stories_for_devices(repo, rows, now=NOW)
    assert len(stories) == 2
    assert calls == ["home"]


def test_device_stories_for_devices_two_networks(monkeypatch, tmp_path):
    from zigbeelens.config.models import ModeConfig, NetworkConfig, StorageConfig
    from zigbeelens.services.network_evidence_composition import (
        compose_network_evidence_context,
    )

    db_path = tmp_path / "r2.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = AppConfig(
        mode=ModeConfig(mock=False),
        networks=[
            NetworkConfig(id="n1", name="N1", base_topic="z2m/n1"),
            NetworkConfig(id="n2", name="N2", base_topic="z2m/n2"),
        ],
        storage=StorageConfig(path=str(db_path)),
    )
    repo.sync_networks(config.networks)
    _add_device(repo, "0xa", network_id="n1")
    _add_device(repo, "0xb", network_id="n2")
    _enable_tracking(repo, "0xa", network_id="n1")
    _enable_tracking(repo, "0xb", network_id="n2")

    calls: list[str] = []
    original = compose_network_evidence_context

    def _wrap(r, network_id, **kwargs):
        calls.append(network_id)
        return original(r, network_id, **kwargs)

    monkeypatch.setattr(
        "zigbeelens.services.network_evidence_composition.compose_network_evidence_context",
        _wrap,
    )
    rows = [repo.get_device("n1", "0xa"), repo.get_device("n2", "0xb")]
    stories = device_stories_for_devices(repo, rows, now=NOW)
    assert len(stories) == 2
    assert sorted(calls) == ["n1", "n2"]


@pytest.mark.parametrize(
    "ieee,availability,friendly",
    [
        ("0xoff", "offline", "Offline"),
        ("0xtrk", "online", "Tracking"),
        ("0xnrm", "online", "Normal"),
    ],
)
def test_batch_story_equals_single(tmp_path, ieee, availability, friendly):
    repo, _ = _repo(tmp_path)
    _add_device(repo, ieee, availability=availability, friendly_name=friendly)
    if ieee != "0xtrk":
        _enable_tracking(repo, ieee)
    rows = [repo.get_device("home", ieee)]
    batch = device_stories_for_devices(repo, rows, now=NOW)
    single = device_story_for_device(repo, "home", ieee, now=NOW)
    assert single is not None
    assert batch[("home", ieee)] == single


def test_badge_batch_projects_from_full_stories(tmp_path):
    repo, _ = _repo(tmp_path)
    _add_device(repo, "0xa", availability="offline", friendly_name="Off")
    _enable_tracking(repo, "0xa")
    rows = [repo.get_device("home", "0xa")]
    stories = device_stories_for_devices(repo, rows, now=NOW)
    badges = device_decision_badges_for_devices(repo, rows, now=NOW)
    assert badges[("home", "0xa")] == device_decision_badge_from_story(
        stories[("home", "0xa")]
    )


def test_report_device_story_coded_parity(tmp_path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "0xa", availability="offline", friendly_name="Off")
    _enable_tracking(repo, "0xa")
    story = device_story_for_device(repo, "home", "0xa", now=NOW)
    assert story is not None
    from zigbeelens.services.payload_builder import PayloadBuilder

    device = PayloadBuilder(config, repo)._device_summary(repo.get_device("home", "0xa"))
    report_story = report_device_story_from_story(device=device, story=story)
    assert coded_payload_excludes_identity(report_story) == device_story_report_payload(
        story
    )


def test_report_device_context_builds_stories_once(monkeypatch, tmp_path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "0xa", availability="offline")
    _enable_tracking(repo, "0xa")
    data = DataService(config, repo)

    spy = MagicMock(wraps=device_stories_for_devices)
    monkeypatch.setattr(
        "zigbeelens.services.data_service.device_stories_for_devices",
        spy,
    )
    devices_spy = MagicMock(wraps=data.payload_builder.devices)
    monkeypatch.setattr(data.payload_builder, "devices", devices_spy)

    ctx = data.report_device_context(network_id="home", now=NOW)
    assert isinstance(ctx, ReportDeviceContext)
    assert spy.call_count == 1
    assert devices_spy.call_count == 0
    assert ("home", "0xa") in ctx.stories
    assert any(d.ieee_address == "0xa" for d in ctx.devices)
    assert ctx.devices[0].decision is not None


def test_full_report_decision_sections_present(mock_client: TestClient):
    detail = mock_client.get("/api/reports/preview", params={"scope": "full"}).json()
    assert detail["report_version"] == 3
    assert detail["decision_summary"] is not None
    assert detail["decision_summary"]["subject_count"] == len(detail["device_stories"])
    assert detail["device_stories"]
    status_total = sum(detail["decision_summary"]["status_counts"].values())
    assert status_total == detail["decision_summary"]["subject_count"]
    assert isinstance(detail["investigation_priorities"], list)
    assert isinstance(detail["data_coverage_warnings"], list)
    assert detail["domain_details"]["devices"]


def test_device_scoped_report_only_target_story(mock_client: TestClient):
    devices = mock_client.get("/api/devices").json()["items"]
    target = next(d for d in devices if d.get("decision"))
    detail = mock_client.get(
        "/api/reports/preview",
        params={
            "scope": "device",
            "network_id": target["network_id"],
            "device": target["ieee_address"],
            "hash_ieee_addresses": "false",
            "preserve_friendly_names": "true",
        },
    ).json()
    assert detail["report_version"] == 3
    domain_devices = detail["domain_details"]["devices"]
    assert len(domain_devices) == 1
    assert len(detail["device_stories"]) == 1
    story = detail["device_stories"][0]
    device = domain_devices[0]
    assert story["ieee_address"] == device["ieee_address"]
    assert story["network_id"] == device["network_id"]
    assert story["friendly_name"] == device["friendly_name"]



def test_related_incidents_are_report_context_not_evidence(tmp_path):
    db = Database(tmp_path / "related-report.sqlite")
    db.migrate()
    repo = Repository(db)
    config = AppConfig()
    config.mode.mock = True
    data = DataService(config, repo)

    from zigbeelens.services.mock_provider import MockProvider

    mock = MockProvider("single_device_unavailable")
    affected = mock.data.incidents[0].affected_devices[0]
    key = (affected.network_id, affected.ieee_address)
    scenario_story = mock.data.device_stories[key]
    assert scenario_story.related_unresolved_incident_ids == ["inc-single-1"]
    assert scenario_story.evidence == []

    detail = generate_report(
        data=data,
        config=config,
        reporting=config.reporting,
        collector={},
        request=ReportRequest(
            scope=ReportScope.device,
            network_id=key[0],
            device=key[1],
            redaction=RedactionOptions(
                profile=RedactionProfile.standard,
                preserve_friendly_names=True,
                hash_ieee_addresses=False,
                redact_network_names=False,
            ),
        ),
        scenario="single_device_unavailable",
        repo=repo,
    )
    assert len(detail.device_stories) == 1
    report_story = detail.device_stories[0]
    assert report_story.related_unresolved_incident_ids == ["inc-single-1"]

    coded = report_story.model_dump(
        mode="json", exclude={"network_id", "ieee_address", "friendly_name"}
    )
    assert coded == device_story_report_payload(scenario_story)

    body = report_body_as_json(detail)
    assert body["device_stories"][0]["related_unresolved_incident_ids"] == [
        "inc-single-1"
    ]
    parsed_yaml = __import__("yaml").safe_load(report_body_as_yaml(detail))
    assert parsed_yaml["device_stories"][0]["related_unresolved_incident_ids"] == [
        "inc-single-1"
    ]

    markdown = render_markdown(detail)
    assert "## Related incident records" in markdown
    assert "Related unresolved incident record (inc-single-1)" in markdown
    evidence_section = markdown.split("## Evidence", 1)
    if len(evidence_section) == 2:
        before_related = evidence_section[1].split("## Related incident records", 1)[0]
        assert "inc-single-1" not in before_related

def test_scenario_report_story_isolation(tmp_path):
    """Scenario report stories stay on fixture stories, not live repo.

    Seed the live repo with a contradictory story, then preview with ?scenario=.
    """
    db = Database(tmp_path / "iso.sqlite")
    db.migrate()
    repo = Repository(db)
    config = AppConfig()
    config.mode.mock = False
    data = DataService(config, repo)

    from zigbeelens.services.mock_provider import MockProvider

    mock = MockProvider(SCENARIO)
    affected = mock.data.incidents[0].affected_devices[0]
    key = (affected.network_id, affected.ieee_address)
    scenario_story = mock.data.device_stories[key]

    # Seed live row that would produce a different story if consulted.
    _add_device(
        repo,
        affected.ieee_address,
        network_id=affected.network_id,
        availability="online",
        friendly_name="Live override",
    )
    _enable_tracking(
        repo, affected.ieee_address, network_id=affected.network_id
    )

    detail = generate_report(
        data=data,
        config=config,
        reporting=config.reporting,
        collector={},
        request=ReportRequest(
            scope=ReportScope.full,
            redaction=RedactionOptions(
                profile=RedactionProfile.standard,
                preserve_friendly_names=True,
                hash_ieee_addresses=False,
                redact_network_names=False,
            ),
        ),
        scenario=SCENARIO,
        repo=repo,
    )
    report_story = next(
        s
        for s in detail.device_stories
        if s.network_id == key[0] and s.ieee_address == key[1]
    )
    expected = device_story_report_payload(scenario_story)
    coded = report_story.model_dump(
        mode="json",
        exclude={"network_id", "ieee_address", "friendly_name"},
    )
    assert coded == expected

    device_detail = generate_report(
        data=data,
        config=config,
        reporting=config.reporting,
        collector={},
        request=ReportRequest(
            scope=ReportScope.device,
            network_id=key[0],
            device=key[1],
            redaction=RedactionOptions(
                profile=RedactionProfile.standard,
                preserve_friendly_names=True,
                hash_ieee_addresses=False,
                redact_network_names=False,
            ),
        ),
        scenario=SCENARIO,
        repo=repo,
    )
    assert len(device_detail.device_stories) == 1
    assert device_detail.device_stories[0].status == str(scenario_story.status)
    assert device_detail.device_stories[0].headline_code == str(
        scenario_story.headline_code
    )


def test_redaction_identity_consistent_across_decision_sections(tmp_path):
    db = Database(tmp_path / "red.sqlite")
    db.migrate()
    repo = Repository(db)
    config = AppConfig()
    config.mode.mock = True
    config.mode.default_scenario = SCENARIO
    data = DataService(config, repo)

    detail = generate_report(
        data=data,
        config=config,
        reporting=config.reporting,
        collector={},
        request=ReportRequest(
            scope=ReportScope.full,
            redaction=RedactionOptions(profile=RedactionProfile.strict),
        ),
        scenario=SCENARIO,
        repo=repo,
    )
    assert detail.device_stories
    domain_devices = detail.domain_details.devices
    assert domain_devices
    device = domain_devices[0]
    story = next(
        s
        for s in detail.device_stories
        if s.network_id == device.network_id and s.friendly_name == device.friendly_name
    )
    assert story.ieee_address == device.ieee_address
    assert story.ieee_address.startswith("ieee_")
    for priority in detail.investigation_priorities:
        for ieee in priority.device_ieees:
            assert ieee.startswith("ieee_")
    for d in domain_devices:
        assert d.ieee_address.startswith("ieee_")
    for s in detail.device_stories:
        assert s.ieee_address.startswith("ieee_")
    assert not story.status.startswith("ieee_")
    assert story.headline_code
    assert not story.headline_code.startswith("ieee_")
