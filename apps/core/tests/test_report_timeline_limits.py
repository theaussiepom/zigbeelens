"""Exhaustive ownership for reporting.max_recent_events."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient

from zigbeelens.config.models import (
    AppConfig,
    ModeConfig,
    NetworkConfig,
    ReportingConfig,
    StorageConfig,
)
from zigbeelens.db.connection import Database
from zigbeelens.decisions.device_story import DeviceStoryTimelineItem
from zigbeelens.diagnostics.incidents.models import AffectedDevice
from zigbeelens.main import create_app
from zigbeelens.mock.fixtures import DEFAULT_SCENARIO, ScenarioData, get_scenario
from zigbeelens.schemas import RedactionOptions, ReportRequest, ReportScope
from zigbeelens.services import report_composition as report_composition_module
from zigbeelens.services.data_service import DataService
from zigbeelens.services.mock_provider import MockProvider
from zigbeelens.services.report_composition import compose_mock_report_scope
from zigbeelens.services.reports import generate_report
from zigbeelens.storage.repository import Repository

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
TARGET = ("home", "0xabc")
KEEP_TITLE = "C7D2_TIMELINE_KEEP"
DROP_TITLES = ("C7D2_TIMELINE_DROP_1", "C7D2_TIMELINE_DROP_2")
DROP_STORY_CODES = ("c7d2_story_drop_1", "c7d2_story_drop_2")


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return NOW.replace(tzinfo=None)
        return NOW.astimezone(tz)


def _assert_detail_bounded(detail, limit: int) -> None:
    assert len(detail.events_or_timeline) <= limit
    assert all(len(incident.timeline) <= limit for incident in detail.incidents)
    assert all(
        len(device.recent_events) <= limit for device in detail.domain_details.device_details
    )
    assert all(len(story.timeline) <= limit for story in detail.device_stories)
    assert detail.raw_counts["events_included"] == len(detail.events_or_timeline)


def _assert_body_bounded(body: dict[str, Any], limit: int) -> None:
    assert len(body["events_or_timeline"]) <= limit
    assert all(len(incident["timeline"]) <= limit for incident in body["incidents"])
    assert all(
        len(device["recent_events"]) <= limit for device in body["domain_details"]["device_details"]
    )
    assert all(len(story["timeline"]) <= limit for story in body["device_stories"])
    assert body["raw_counts"]["events_included"] == len(body["events_or_timeline"])


def _decision_projection(detail) -> list[tuple[Any, ...]]:
    return [
        (
            str(story.status),
            str(story.priority),
            story.headline_code,
            story.reasons,
            story.limitations,
            story.suggested_checks,
            story.coverage,
            story.related_unresolved_incident_ids,
        )
        for story in detail.device_stories
    ]


def _identity_projection(detail) -> dict[str, Any]:
    return {
        "incidents": [incident.id for incident in detail.incidents],
        "device_details": [
            (device.network_id, device.ieee_address)
            for device in detail.domain_details.device_details
        ],
        "device_stories": [
            (story.network_id, story.ieee_address) for story in detail.device_stories
        ],
        "decisions": _decision_projection(detail),
    }


def _adversarial_scenario() -> tuple[ScenarioData, tuple[str, str], str]:
    data = deepcopy(get_scenario(DEFAULT_SCENARIO))
    incident = data.incidents[0]
    target = incident.affected_devices[0]
    target_key = (target.network_id, target.ieee_address)
    base = incident.timeline[0]
    events = [
        base.model_copy(
            update={
                "id": "c7d2-keep",
                "timestamp": NOW.isoformat(),
                "title": KEEP_TITLE,
                "summary": KEEP_TITLE,
                "network_id": target.network_id,
                "ieee_address": target.ieee_address,
                "incident_id": incident.id,
            }
        ),
        base.model_copy(
            update={
                "id": "c7d2-drop-1",
                "timestamp": (NOW - timedelta(minutes=1)).isoformat(),
                "title": DROP_TITLES[0],
                "summary": DROP_TITLES[0],
                "network_id": target.network_id,
                "ieee_address": target.ieee_address,
                "incident_id": incident.id,
            }
        ),
        base.model_copy(
            update={
                "id": "c7d2-drop-2",
                "timestamp": (NOW - timedelta(minutes=2)).isoformat(),
                "title": DROP_TITLES[1],
                "summary": DROP_TITLES[1],
                "network_id": target.network_id,
                "ieee_address": target.ieee_address,
                "incident_id": incident.id,
            }
        ),
    ]
    data.timeline = events
    data.incidents = [incident.model_copy(update={"timeline": events})]
    story = data.device_stories[target_key]
    data.device_stories[target_key] = story.model_copy(
        update={
            "timeline": [
                DeviceStoryTimelineItem(code="c7d2_story_keep", occurred_at=NOW),
                DeviceStoryTimelineItem(
                    code=DROP_STORY_CODES[0],
                    occurred_at=NOW - timedelta(minutes=1),
                ),
                DeviceStoryTimelineItem(
                    code=DROP_STORY_CODES[1],
                    occurred_at=NOW - timedelta(minutes=2),
                ),
            ]
        }
    )
    return data, target_key, incident.id


class _ScenarioSource:
    def __init__(self, data: ScenarioData) -> None:
        self.provider = MockProvider(data.id)
        self.provider._data = data

    def compose_report_scope(
        self,
        request,
        scenario=None,
        *,
        reference_now,
        include_timeline,
        reporting,
    ):
        return compose_mock_report_scope(
            self.provider,
            request,
            reference_now=reference_now,
            include_timeline=include_timeline,
            reporting=reporting,
        )


class _MismatchedLimitScenarioSource(_ScenarioSource):
    """Adversarial producer that ignores the authoritative reporting limit."""

    def compose_report_scope(
        self,
        request,
        scenario=None,
        *,
        reference_now,
        include_timeline,
        reporting,
    ):
        return super().compose_report_scope(
            request,
            scenario,
            reference_now=reference_now,
            include_timeline=include_timeline,
            reporting=ReportingConfig(max_recent_events=1000),
        )


def _scope_requests(
    *,
    network_id: str,
    ieee_address: str,
    incident_id: str,
    include_timeline: bool,
) -> list[ReportRequest]:
    redaction = RedactionOptions(
        include_timeline=include_timeline,
        hash_ieee_addresses=False,
    )
    return [
        ReportRequest(scope=ReportScope.full, redaction=redaction),
        ReportRequest(
            scope=ReportScope.network,
            network_id=network_id,
            redaction=redaction,
        ),
        ReportRequest(
            scope=ReportScope.incident,
            incident_id=incident_id,
            redaction=redaction,
        ),
        ReportRequest(
            scope=ReportScope.device,
            network_id=network_id,
            device=ieee_address,
            redaction=redaction,
        ),
    ]


def _live_service(tmp_path: Path) -> tuple[DataService, AppConfig, Repository]:
    db_path = tmp_path / "live-report-limits.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = AppConfig(
        mode=ModeConfig(mock=False),
        networks=[NetworkConfig(id=TARGET[0], name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(db_path)),
        reporting=ReportingConfig(max_recent_events=1),
    )
    repo.sync_networks(config.networks)
    repo.upsert_device(
        network_id=TARGET[0],
        ieee_address=TARGET[1],
        friendly_name="C7D2 target",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )
    repo.ensure_device_current_state(*TARGET)
    repo.update_device_current_state(
        network_id=TARGET[0],
        ieee_address=TARGET[1],
        availability="online",
        last_seen=NOW.isoformat(),
    )
    repo.incidents.insert_incident(
        incident_id="inc-c7d2",
        dedup_key="c7d2:home:0xabc",
        incident_type="single_device_unavailable",
        lifecycle_state="open",
        severity="watch",
        scope="device",
        confidence="high",
        title="C7D2 incident",
        summary="C7D2 incident",
        explanation="C7D2 incident",
        evidence=[],
        counter_evidence=[],
        limitations=[],
        opened_at=(NOW - timedelta(hours=1)).isoformat(),
        updated_at=NOW.isoformat(),
    )
    repo.replace_incident_devices(
        "inc-c7d2",
        [AffectedDevice(TARGET[0], TARGET[1])],
    )
    repo.replace_incident_networks("inc-c7d2", [TARGET[0]])
    for index, title in enumerate((KEEP_TITLE, *DROP_TITLES)):
        repo.insert_event(
            event_id=f"c7d2-live-{index}",
            network_id=TARGET[0],
            ieee_address=TARGET[1],
            event_type="audit",
            severity="watch",
            title=title,
            summary=title,
            incident_id="inc-c7d2",
            occurred_at=(NOW - timedelta(minutes=index)).isoformat(),
        )
    return DataService(config, repo), config, repo


def test_live_limit_bounds_every_owner_and_exact_sql_reads(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, config, repo = _live_service(tmp_path)
    real_stories = report_composition_module.device_stories_for_devices

    def stories_with_adversarial_timeline(*args, **kwargs):
        stories = real_stories(*args, **kwargs)
        return {
            key: story.model_copy(
                update={
                    "timeline": [
                        DeviceStoryTimelineItem(
                            code=f"c7d2_live_story_{index}",
                            occurred_at=NOW - timedelta(minutes=index),
                        )
                        for index in range(3)
                    ]
                }
            )
            for key, story in stories.items()
        }

    monkeypatch.setattr(
        report_composition_module,
        "device_stories_for_devices",
        stories_with_adversarial_timeline,
    )
    incident_limits: list[int] = []
    device_limits: list[int] = []
    real_incident_events = repo.list_events_for_incidents
    real_device_events = repo.list_events_for_device

    def incident_events_spy(incident_ids, *, limit_per_incident=100):
        incident_limits.append(limit_per_incident)
        return real_incident_events(
            incident_ids,
            limit_per_incident=limit_per_incident,
        )

    def device_events_spy(network_id, ieee_address, *, limit=20):
        device_limits.append(limit)
        return real_device_events(network_id, ieee_address, limit=limit)

    monkeypatch.setattr(repo, "list_events_for_incidents", incident_events_spy)
    monkeypatch.setattr(repo, "list_events_for_device", device_events_spy)

    limited_details = []
    for request in _scope_requests(
        network_id=TARGET[0],
        ieee_address=TARGET[1],
        incident_id="inc-c7d2",
        include_timeline=True,
    ):
        detail = generate_report(
            data=service,
            config=config,
            reporting=ReportingConfig(max_recent_events=1),
            collector={},
            request=request,
            repo=repo,
            now=NOW,
        )
        _assert_detail_bounded(detail, 1)
        assert len(detail.events_or_timeline) == 1
        assert [incident.id for incident in detail.incidents] == ["inc-c7d2"]
        assert all(len(incident.timeline) == 1 for incident in detail.incidents)
        assert all(len(story.timeline) == 1 for story in detail.device_stories)
        if request.scope in {ReportScope.incident, ReportScope.device}:
            target_detail = next(
                device
                for device in detail.domain_details.device_details
                if (device.network_id, device.ieee_address) == TARGET
            )
            assert len(target_detail.recent_events) == 1
        limited_details.append(detail)

    assert incident_limits and set(incident_limits) == {1}
    assert device_limits and set(device_limits) == {1}

    incident_limits.clear()
    device_limits.clear()
    disabled_requests = _scope_requests(
        network_id=TARGET[0],
        ieee_address=TARGET[1],
        incident_id="inc-c7d2",
        include_timeline=False,
    )
    for enabled, request in zip(limited_details, disabled_requests, strict=True):
        no_timeline = generate_report(
            data=service,
            config=config,
            reporting=ReportingConfig(max_recent_events=1),
            collector={},
            request=request,
            repo=repo,
            now=NOW,
        )
        _assert_detail_bounded(no_timeline, 0)
        assert _identity_projection(no_timeline) == _identity_projection(enabled)
        assert no_timeline.decision_summary == enabled.decision_summary
    assert incident_limits == []
    assert device_limits == []

    wide_requests = _scope_requests(
        network_id=TARGET[0],
        ieee_address=TARGET[1],
        incident_id="inc-c7d2",
        include_timeline=True,
    )
    for limited, request in zip(limited_details, wide_requests, strict=True):
        wide = generate_report(
            data=service,
            config=config,
            reporting=ReportingConfig(max_recent_events=1000),
            collector={},
            request=request,
            repo=repo,
            now=NOW,
        )
        _assert_detail_bounded(wide, 1000)
        assert len(wide.events_or_timeline) == 3
        assert len(wide.incidents[0].timeline) == 3
        target_story = next(
            story
            for story in wide.device_stories
            if (story.network_id, story.ieee_address) == TARGET
        )
        assert len(target_story.timeline) == 3
        if request.scope in {ReportScope.incident, ReportScope.device}:
            target_detail = next(
                device
                for device in wide.domain_details.device_details
                if (device.network_id, device.ieee_address) == TARGET
            )
            assert len(target_detail.recent_events) == 3
        assert limited.decision_summary == wide.decision_summary
        assert _decision_projection(limited) == _decision_projection(wide)
        assert [incident.id for incident in limited.incidents] == [
            incident.id for incident in wide.incidents
        ]
    assert 1000 in incident_limits
    assert 1000 in device_limits


def test_mock_limit_and_disabled_timeline_cover_every_scope(tmp_path: Path) -> None:
    scenario, target, incident_id = _adversarial_scenario()
    db_path = tmp_path / "mock-report-limits.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = AppConfig(
        mode=ModeConfig(mock=True),
        storage=StorageConfig(path=str(db_path)),
        reporting=ReportingConfig(max_recent_events=1),
    )
    source = _ScenarioSource(scenario)

    limited_details = []
    for request in _scope_requests(
        network_id=target[0],
        ieee_address=target[1],
        incident_id=incident_id,
        include_timeline=True,
    ):
        detail = generate_report(
            data=source,
            config=config,
            reporting=config.reporting,
            collector={},
            request=request,
            scenario=scenario.id,
            repo=repo,
            now=NOW,
        )
        _assert_detail_bounded(detail, 1)
        assert len(detail.events_or_timeline) == 1
        assert all(len(incident.timeline) == 1 for incident in detail.incidents)
        target_story = next(
            story
            for story in detail.device_stories
            if (story.network_id, story.ieee_address) == target
        )
        assert len(target_story.timeline) == 1
        if request.scope in {ReportScope.incident, ReportScope.device}:
            target_detail = next(
                device
                for device in detail.domain_details.device_details
                if (device.network_id, device.ieee_address) == target
            )
            assert len(target_detail.recent_events) == 1
        limited_details.append(detail)

    disabled_requests = _scope_requests(
        network_id=target[0],
        ieee_address=target[1],
        incident_id=incident_id,
        include_timeline=False,
    )
    for enabled, request in zip(limited_details, disabled_requests, strict=True):
        detail = generate_report(
            data=source,
            config=config,
            reporting=config.reporting,
            collector={},
            request=request,
            scenario=scenario.id,
            repo=repo,
            now=NOW,
        )
        _assert_detail_bounded(detail, 0)
        assert _identity_projection(detail) == _identity_projection(enabled)
        assert detail.decision_summary == enabled.decision_summary

    wide_requests = _scope_requests(
        network_id=target[0],
        ieee_address=target[1],
        incident_id=incident_id,
        include_timeline=True,
    )
    for limited, request in zip(limited_details, wide_requests, strict=True):
        wide = generate_report(
            data=source,
            config=config,
            reporting=ReportingConfig(max_recent_events=1000),
            collector={},
            request=request,
            scenario=scenario.id,
            repo=repo,
            now=NOW,
        )
        _assert_detail_bounded(wide, 1000)
        assert len(wide.events_or_timeline) == 3
        assert len(wide.incidents[0].timeline) == 3
        target_story = next(
            story
            for story in wide.device_stories
            if (story.network_id, story.ieee_address) == target
        )
        assert len(target_story.timeline) == 3
        if request.scope in {ReportScope.incident, ReportScope.device}:
            target_detail = next(
                device
                for device in wide.domain_details.device_details
                if (device.network_id, device.ieee_address) == target
            )
            assert len(target_detail.recent_events) == 3
        assert limited.decision_summary == wide.decision_summary
        assert _decision_projection(limited) == _decision_projection(wide)
        assert [incident.id for incident in limited.incidents] == [
            incident.id for incident in wide.incidents
        ]


def test_authoritative_final_seal_rejects_a_producer_limit_mismatch(
    tmp_path: Path,
) -> None:
    scenario, target, incident_id = _adversarial_scenario()
    db_path = tmp_path / "mismatched-producer-limit.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = AppConfig(
        mode=ModeConfig(mock=True),
        storage=StorageConfig(path=str(db_path)),
        reporting=ReportingConfig(max_recent_events=1),
    )

    detail = generate_report(
        data=_MismatchedLimitScenarioSource(scenario),
        config=config,
        reporting=config.reporting,
        collector={},
        request=ReportRequest(
            scope=ReportScope.device,
            network_id=target[0],
            device=target[1],
            redaction=RedactionOptions(
                include_timeline=True,
                hash_ieee_addresses=False,
            ),
        ),
        scenario=scenario.id,
        repo=repo,
        now=NOW,
    )

    assert len(detail.events_or_timeline) == 1
    assert len(detail.incidents[0].timeline) == 1
    target_detail = next(
        device
        for device in detail.domain_details.device_details
        if (device.network_id, device.ieee_address) == target
    )
    assert len(target_detail.recent_events) == 1
    target_story = next(
        story
        for story in detail.device_stories
        if (story.network_id, story.ieee_address) == target
    )
    assert len(target_story.timeline) == 1
    assert detail.raw_counts["events_included"] == 1


def test_api_storage_download_restart_prefix_and_redaction_seal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from zigbeelens.services import mock_provider as mock_provider_module
    from zigbeelens.services import reports as reports_module

    scenario, target, incident_id = _adversarial_scenario()
    monkeypatch.setattr(
        mock_provider_module,
        "get_scenario",
        lambda _scenario_id=None: deepcopy(scenario),
    )

    original_redactor = reports_module.Redactor

    class _DeterministicRedactor(original_redactor):
        def __init__(self, resolved, salt: str = "c7d2-prefix-parity") -> None:
            super().__init__(resolved, salt=salt)

    monkeypatch.setattr(reports_module, "Redactor", _DeterministicRedactor)
    monkeypatch.setattr(reports_module, "datetime", _FrozenDateTime)
    db_path = tmp_path / "api-report-limits.sqlite"
    config = AppConfig(
        mode=ModeConfig(mock=True, default_scenario=scenario.id),
        storage=StorageConfig(path=str(db_path)),
        reporting=ReportingConfig(
            max_recent_events=1,
            default_profile="public_safe",
        ),
    )
    created: list[tuple[str, str]] = []
    request = {
        "scope": "incident",
        "incident_id": incident_id,
        "redaction": {
            "profile": "public_safe",
            "include_timeline": True,
        },
    }

    with TestClient(create_app(resolved_config=config)) as client:
        preview_bodies: list[dict[str, Any]] = []
        disabled_bodies: list[dict[str, Any]] = []
        for prefix in ("/api", "/api/v1"):
            preview = client.get(
                f"{prefix}/reports/preview",
                params={
                    "scope": "incident",
                    "incident_id": incident_id,
                    "profile": "public_safe",
                    "include_timeline": "true",
                },
            )
            assert preview.status_code == 200
            preview_body = preview.json()
            preview_bodies.append(preview_body)
            _assert_body_bounded(preview_body, 1)
            assert preview_body["redaction"]["profile"] == "public_safe"
            assert preview_body["redaction"]["ieee_addresses_hashed"] is True
            assert preview_body["redaction"]["friendly_names"] == "labeled"
            assert preview_body["redaction"]["network_names"] == "labeled"
            preview_blob = json.dumps(preview_body)
            assert target[1] not in preview_blob
            assert all(
                device["ieee_address"].startswith("ieee_")
                for device in preview_body["domain_details"]["devices"]
            )
            assert all(
                device["friendly_name"].startswith("device_")
                for device in preview_body["domain_details"]["devices"]
            )

            disabled = client.get(
                f"{prefix}/reports/preview",
                params={
                    "scope": "incident",
                    "incident_id": incident_id,
                    "include_timeline": "false",
                },
            )
            assert disabled.status_code == 200
            disabled_body = disabled.json()
            disabled_bodies.append(disabled_body)
            _assert_body_bounded(disabled_body, 0)
        assert preview_bodies[0] == preview_bodies[1]
        assert disabled_bodies[0] == disabled_bodies[1]

        for prefix in ("/api", "/api/v1"):
            for report_format in ("json", "yaml", "markdown"):
                response = client.post(
                    f"{prefix}/reports",
                    json={**request, "format": report_format},
                )
                assert response.status_code == 200
                report_id = response.json()["id"]
                created.append((report_format, report_id))

                stored_bodies: list[dict[str, Any]] = []
                download_bodies: list[str] = []
                for read_prefix in ("/api", "/api/v1"):
                    stored = client.get(f"{read_prefix}/reports/{report_id}")
                    assert stored.status_code == 200
                    body = stored.json()
                    stored_bodies.append(body)
                    _assert_body_bounded(body, 1)
                    assert body["redaction"]["profile"] == "public_safe"
                    blob = json.dumps(body)
                    assert target[1] not in blob
                    assert all(
                        device["ieee_address"].startswith("ieee_")
                        for device in body["domain_details"]["devices"]
                    )
                    assert all(
                        device["friendly_name"].startswith("device_")
                        for device in body["domain_details"]["devices"]
                    )
                    assert all(title not in blob for title in DROP_TITLES)
                    assert all(code not in blob for code in DROP_STORY_CODES)

                    download = client.get(f"{read_prefix}/reports/{report_id}/download")
                    assert download.status_code == 200
                    download_bodies.append(download.text)
                    if report_format == "json":
                        _assert_body_bounded(download.json(), 1)
                    elif report_format == "yaml":
                        _assert_body_bounded(yaml.safe_load(download.text), 1)
                    else:
                        assert KEEP_TITLE in download.text
                        assert all(title not in download.text for title in DROP_TITLES)
                assert stored_bodies[0] == stored_bodies[1]
                assert download_bodies[0] == download_bodies[1]

                row = client.app.state.ctx.repo.reports.get_report(report_id)
                assert row is not None and row.body_json is not None
                raw_body = json.loads(row.body_json)
                _assert_body_bounded(raw_body, 1)
                assert all(title not in row.body_json for title in DROP_TITLES)
                assert all(code not in row.body_json for code in DROP_STORY_CODES)

    with TestClient(create_app(resolved_config=config)) as client:
        for report_format, report_id in created:
            stored_bodies = []
            download_bodies = []
            for prefix in ("/api", "/api/v1"):
                stored = client.get(f"{prefix}/reports/{report_id}")
                assert stored.status_code == 200
                stored_body = stored.json()
                stored_bodies.append(stored_body)
                _assert_body_bounded(stored_body, 1)
                download = client.get(f"{prefix}/reports/{report_id}/download")
                assert download.status_code == 200
                download_bodies.append(download.text)
                if report_format == "json":
                    _assert_body_bounded(download.json(), 1)
                elif report_format == "yaml":
                    _assert_body_bounded(yaml.safe_load(download.text), 1)
                else:
                    assert KEEP_TITLE in download.text
            assert stored_bodies[0] == stored_bodies[1]
            assert download_bodies[0] == download_bodies[1]
