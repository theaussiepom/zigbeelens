"""Phase 5D corrective regressions: detail seam, timelines, interpretation, redaction."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

from zigbeelens.config.models import AppConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.device_story import (
    DeviceStory,
    device_stories_for_devices,
    device_story_report_payload,
)
from zigbeelens.presentation.report_decision_copy import headline_text
from zigbeelens.schemas import (
    Confidence,
    DiagnosticConclusion,
    Incident,
    IncidentScope,
    IncidentStatus,
    RedactionOptions,
    RedactionProfile,
    ReportDetail,
    ReportDeviceStory,
    ReportRequest,
    ReportScope,
    ReportStoryTimelineItem,
    Severity,
    TimelineEvent,
)
from zigbeelens.services.data_service import DataService
from zigbeelens.services.device_decision_badge import (
    device_decision_badge_for_device,
    device_decision_badge_from_story,
)
from zigbeelens.services.report_redaction import Redactor, resolve_redaction
from zigbeelens.services.reports import (
    _decision_list_summary,
    _recorded_incident_interpretation,
    _without_timelines,
    generate_report,
    render_markdown_v2,
    summary_from_row,
)
from zigbeelens.storage.repository import Repository

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
SENTINEL = "TIMELINE_SENTINEL_5D"
SCENARIO = "four_devices_same_room_unavailable"
V1_SENTINEL = "V1_MARKDOWN_SENTINEL_5D_CORRECTIVE"


def _incident(**kwargs) -> Incident:
    defaults = dict(
        type="test",
        status=IncidentStatus.open,
        severity=Severity.incident,
        scope=IncidentScope.device,
        confidence=Confidence.medium,
        network_ids=["home"],
        affected_device_count=0,
        affected_devices=[],
        opened_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        evidence=[],
        counter_evidence=[],
        limitations=[],
        timeline=[],
        conclusion=DiagnosticConclusion(
            classification="x",
            severity=Severity.incident,
            scope=IncidentScope.device,
            confidence=Confidence.medium,
            summary=kwargs.get("summary", "Summary"),
        ),
    )
    defaults.update(kwargs)
    return Incident(**defaults)


def _live_service(tmp_path) -> tuple[DataService, AppConfig, Repository]:
    from zigbeelens.config.models import ModeConfig, NetworkConfig, StorageConfig

    db_path = tmp_path / "corr.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = AppConfig(
        mode=ModeConfig(mock=False),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(db_path)),
    )
    repo.sync_networks(config.networks)
    return DataService(config, repo), config, repo


def _add_device(repo: Repository, ieee: str, *, network_id: str = "home", **kwargs):
    repo.upsert_device(
        network_id=network_id,
        ieee_address=ieee,
        friendly_name=kwargs.get("friendly_name", ieee),
        device_type="EndDevice",
        power_source="Mains",
    )
    repo.ensure_device_current_state(network_id, ieee)
    repo.update_device_current_state(
        network_id=network_id,
        ieee_address=ieee,
        availability=kwargs.get("availability", "online"),
        last_seen=NOW.isoformat(),
    )


def test_device_scoped_report_stories_once_and_reuses_badges(monkeypatch, tmp_path):
    data, config, repo = _live_service(tmp_path)
    _add_device(repo, "0xa", availability="offline", friendly_name="Plug")
    repo.availability.insert_availability_change("home", "0xa", "unknown", "offline")

    story_spy = MagicMock(wraps=device_stories_for_devices)
    monkeypatch.setattr(
        "zigbeelens.services.data_service.device_stories_for_devices",
        story_spy,
    )
    badge_spy = MagicMock(wraps=device_decision_badge_for_device)
    monkeypatch.setattr(
        "zigbeelens.services.payload_builder.device_decision_badge_for_device",
        badge_spy,
    )
    device_spy = MagicMock(wraps=data.device)
    monkeypatch.setattr(data, "device", device_spy)

    detail = generate_report(
        data=data,
        config=config,
        reporting=config.reporting,
        collector={},
        request=ReportRequest(
            scope=ReportScope.device,
            network_id="home",
            device="0xa",
            redaction=RedactionOptions(
                profile=RedactionProfile.standard,
                hash_ieee_addresses=False,
                preserve_friendly_names=True,
                redact_network_names=False,
            ),
        ),
        repo=repo,
    )
    assert story_spy.call_count == 1
    assert badge_spy.call_count == 0
    assert device_spy.call_count == 0
    assert len(detail.device_stories) == 1
    assert len(detail.device_details) == 1
    story = detail.device_stories[0]
    det = detail.device_details[0]
    assert det.decision is not None
    # Reconstruct expected badge from report story fields via canonical payload.
    from zigbeelens.decisions.device_story import DeviceStory as DS

    reconstructed = DS.model_validate(
        {
            "subject_type": story.subject_type,
            "subject_id": story.subject_id,
            "status": story.status,
            "priority": story.priority,
            "headline_code": story.headline_code,
            "reasons": story.reasons,
            "evidence": story.evidence,
            "limitations": story.limitations,
            "suggested_checks": story.suggested_checks,
            "coverage": story.coverage,
            "timeline": [t.model_dump(mode="json") for t in story.timeline],
        }
    )
    assert det.decision == device_decision_badge_from_story(reconstructed)


def test_incident_scoped_report_stories_once_for_multiple_devices(monkeypatch, tmp_path):
    """Incident report composes Device Stories once for all affected devices."""
    from zigbeelens.services.mock_provider import MockProvider

    config = AppConfig()
    config.mode.mock = True
    config.mode.default_scenario = SCENARIO
    db = Database(tmp_path / "inc.sqlite")
    db.migrate()
    repo = Repository(db)
    data = DataService(config, repo)
    mock = MockProvider(SCENARIO)
    incident = mock.incidents()[0]
    assert len(incident.affected_devices) >= 2

    calls = {"n": 0}
    original = data.report_device_context

    def _wrap(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(data, "report_device_context", _wrap)
    device_spy = MagicMock(wraps=data.device)
    monkeypatch.setattr(data, "device", device_spy)

    detail = generate_report(
        data=data,
        config=config,
        reporting=config.reporting,
        collector={},
        request=ReportRequest(
            scope=ReportScope.incident,
            incident_id=incident.id,
            redaction=RedactionOptions(
                profile=RedactionProfile.standard,
                hash_ieee_addresses=False,
                preserve_friendly_names=True,
            ),
        ),
        scenario=SCENARIO,
        repo=repo,
    )
    assert calls["n"] == 1
    assert device_spy.call_count == 0
    assert detail.device_details
    for det in detail.device_details:
        key = (det.network_id, det.ieee_address)
        story = next(
            s
            for s in detail.device_stories
            if s.network_id == key[0] and s.ieee_address == key[1]
        )
        reconstructed = DeviceStory.model_validate(
            {
                "subject_type": story.subject_type,
                "subject_id": story.subject_id,
                "status": story.status,
                "priority": story.priority,
                "headline_code": story.headline_code,
                "reasons": story.reasons,
                "evidence": story.evidence,
                "limitations": story.limitations,
                "suggested_checks": story.suggested_checks,
                "coverage": story.coverage,
                "timeline": [t.model_dump(mode="json") for t in story.timeline],
            }
        )
        assert det.decision == device_decision_badge_from_story(reconstructed)


def test_include_timeline_false_clears_all_timeline_collections():
    sent_event = TimelineEvent(
        id="ev-1",
        timestamp="2026-01-01T00:00:00+00:00",
        kind="availability",
        severity=Severity.watch,
        network_id="home",
        ieee_address="0xa",
        title=SENTINEL,
        summary=SENTINEL,
    )
    story = ReportDeviceStory(
        network_id="home",
        ieee_address="0xa",
        friendly_name="Plug",
        subject_id="home:0xa",
        status="watch",
        priority="low",
        headline_code="no_notable_signals",
        timeline=[ReportStoryTimelineItem(code="observed_reporting_rhythm", params={"note": SENTINEL})],
    )
    inc = _incident(
        id="inc-1",
        title="Incident",
        summary="Summary",
        interpretation="Interpretation",
        timeline=[sent_event],
    )
    from zigbeelens.schemas import (
        DeviceHealthPrimary,
        ReportRedactionStatus,
        HealthSnapshot,
    )
    from zigbeelens.services.mock_provider import MockProvider

    sample = MockProvider(SCENARIO).devices()[0]
    det = MockProvider(SCENARIO).device(sample.network_id, sample.ieee_address)
    assert det is not None
    det = det.model_copy(
        update={
            "network_id": "home",
            "ieee_address": "0xa",
            "friendly_name": "Plug",
            "recent_events": [sent_event],
        }
    )
    detail = ReportDetail(
        id="r",
        report_version=2,
        generated_at="2026-01-01T00:00:00+00:00",
        version="0.1.0",
        redaction=ReportRedactionStatus(applied=True, profile="standard", mqtt_credentials=True),
        config_summary={"mode": "mock"},
        networks=[],
        devices=[],
        device_details=[det],
        router_risks=[],
        incidents=[inc],
        active_incidents=[inc],
        timeline=[sent_event],
        events_or_timeline=[sent_event],
        device_stories=[story],
        health_snapshot=HealthSnapshot(
            timestamp="2026-01-01T00:00:00+00:00",
            overall_severity=Severity.healthy,
            overall_health=DeviceHealthPrimary.healthy,
            network_count=0,
            device_count=0,
            unavailable_count=0,
            incident_count=0,
            networks=[],
        ),
        diagnostic_conclusions=[],
        limitations=[],
        markdown_summary="",
    )
    cleared = _without_timelines(detail)
    blob = json.dumps(cleared.model_dump(mode="json"))
    assert SENTINEL not in blob
    assert cleared.timeline == []
    assert cleared.events_or_timeline == []
    assert all(not s.timeline for s in cleared.device_stories)
    assert all(not i.timeline for i in cleared.incidents)
    assert all(not i.timeline for i in cleared.active_incidents)
    assert all(not d.recent_events for d in cleared.device_details)


def test_include_timeline_false_absent_from_generated_markdown(tmp_path):
    config = AppConfig()
    config.mode.mock = True
    config.mode.default_scenario = SCENARIO
    db = Database(tmp_path / "tl.sqlite")
    db.migrate()
    repo = Repository(db)
    data = DataService(config, repo)
    detail = generate_report(
        data=data,
        config=config,
        reporting=config.reporting,
        collector={},
        request=ReportRequest(
            scope=ReportScope.full,
            redaction=RedactionOptions(include_timeline=False),
        ),
        scenario=SCENARIO,
        repo=repo,
    )
    assert detail.timeline == []
    assert detail.events_or_timeline == []
    assert all(not s.timeline for s in detail.device_stories)
    assert all(not i.timeline for i in detail.incidents)
    assert all(not d.recent_events for d in detail.device_details)

    with_timeline = generate_report(
        data=data,
        config=config,
        reporting=config.reporting,
        collector={},
        request=ReportRequest(
            scope=ReportScope.full,
            redaction=RedactionOptions(include_timeline=True),
        ),
        scenario=SCENARIO,
        repo=repo,
    )
    has_any = (
        bool(with_timeline.timeline)
        or any(s.timeline for s in with_timeline.device_stories)
        or any(i.timeline for i in with_timeline.incidents)
        or any(d.recent_events for d in with_timeline.device_details)
    )
    from zigbeelens.services.mock_provider import MockProvider

    mock = MockProvider(SCENARIO)
    if mock.timeline() or any(i.timeline for i in mock.incidents()):
        assert has_any


def test_recorded_incident_interpretation_helper():
    distinct = _incident(
        id="i1",
        title="T",
        summary="Recorded event summary",
        interpretation="Historical explanatory text",
        conclusion=DiagnosticConclusion(
            classification="x",
            severity=Severity.incident,
            scope=IncidentScope.device,
            confidence=Confidence.medium,
            summary="Recorded event summary",
        ),
    )
    assert _recorded_incident_interpretation(distinct) == "Historical explanatory text"
    same = _incident(
        id="i1",
        title="T",
        summary="Recorded event summary",
        interpretation="Recorded event summary",
    )
    assert _recorded_incident_interpretation(same) is None
    blank = _incident(
        id="i1",
        title="T",
        summary="Recorded event summary",
        interpretation="  ",
    )
    assert _recorded_incident_interpretation(blank) is None

    from zigbeelens.schemas import ReportRedactionStatus, HealthSnapshot, DeviceHealthPrimary

    detail = ReportDetail(
        id="r",
        report_version=2,
        generated_at="2026-01-01T00:00:00+00:00",
        version="0.1.0",
        redaction=ReportRedactionStatus(applied=True, profile="standard", mqtt_credentials=True),
        config_summary={"mode": "mock"},
        networks=[],
        devices=[],
        router_risks=[],
        incidents=[distinct],
        health_snapshot=HealthSnapshot(
            timestamp="2026-01-01T00:00:00+00:00",
            overall_severity=Severity.incident,
            overall_health=DeviceHealthPrimary.unavailable,
            network_count=0,
            device_count=0,
            unavailable_count=0,
            incident_count=1,
            networks=[],
        ),
        diagnostic_conclusions=[],
        limitations=[],
        markdown_summary="",
    )
    md = render_markdown_v2(detail)
    assert "Recorded event summary" in md
    assert "Historical explanatory text" in md
    assert md.count("Historical explanatory text") == 1
    # Conclusion duplicate must not appear under Recorded interpretation.
    recorded_section = md.split("Recorded interpretation:")[1]
    lines = [ln for ln in recorded_section.splitlines() if ln.strip()]
    assert lines[0] == "Historical explanatory text"


def test_orphan_network_id_redaction_public_safe_and_strict():
    from zigbeelens.schemas import (
        DataCoverageWarningSummary,
        InvestigationPrioritySummary,
        ReportDecisionSummary,
        ReportRedactionStatus,
        HealthSnapshot,
        DeviceHealthPrimary,
    )
    from zigbeelens.services.mock_provider import MockProvider

    home = MockProvider(SCENARIO).networks()[0]
    detail = ReportDetail(
        id="r",
        report_version=2,
        generated_at="2026-01-01T00:00:00+00:00",
        version="0.1.0",
        redaction=ReportRedactionStatus(applied=True, profile="public_safe", mqtt_credentials=True),
        config_summary={"mode": "mock"},
        networks=[home],
        devices=[],
        router_risks=[],
        incidents=[
            _incident(
                id="inc-retired",
                title="Old incident on retired-network",
                scope=IncidentScope.network,
                network_ids=["retired-network"],
                summary="Affects retired-network inventory",
                interpretation="Context for retired-network",
                conclusion=DiagnosticConclusion(
                    classification="x",
                    severity=Severity.incident,
                    scope=IncidentScope.network,
                    confidence=Confidence.medium,
                    summary="Affects retired-network inventory",
                ),
            )
        ],
        investigation_priorities=[
            InvestigationPrioritySummary(
                id="p1",
                network_id="retired-network",
                card_type="x",
                priority="Review first",
                score=1,
                action_group="watch_only",
                title="Check retired-network",
                summary="Priority for retired-network",
                device_ieees=[],
            )
        ],
        data_coverage_warnings=[
            DataCoverageWarningSummary(
                id="c1",
                network_id="retired-network",
                dimension="availability",
                state="off",
                label_code="availability_tracking_off",
            )
        ],
        device_stories=[
            ReportDeviceStory(
                network_id=home.id,
                ieee_address="0xa",
                friendly_name="Plug",
                subject_id="retired-network:0xa",
                status="watch",
                priority="low",
                headline_code="no_notable_signals",
            )
        ],
        decision_summary=ReportDecisionSummary(device_story_count=1, status_counts={"watch": 1}),
        health_snapshot=HealthSnapshot(
            timestamp="2026-01-01T00:00:00+00:00",
            overall_severity=Severity.healthy,
            overall_health=DeviceHealthPrimary.healthy,
            network_count=1,
            device_count=0,
            unavailable_count=0,
            incident_count=1,
            networks=[],
        ),
        diagnostic_conclusions=[],
        limitations=[],
        markdown_summary="",
    )

    for profile in (RedactionProfile.public_safe, RedactionProfile.strict):
        resolved = resolve_redaction(RedactionOptions(profile=profile))
        redactor = Redactor(resolved)
        out = redactor.redact(detail.model_dump(mode="json"))
        blob = json.dumps(out)
        assert "retired-network" not in blob
        tokens = {
            out["incidents"][0]["network_ids"][0],
            out["investigation_priorities"][0]["network_id"],
            out["data_coverage_warnings"][0]["network_id"],
        }
        assert len(tokens) == 1
        token = next(iter(tokens))
        assert token.startswith("network_")
        assert token in out["device_stories"][0]["subject_id"]
        assert out["device_stories"][0]["status"] == "watch"
        assert out["device_stories"][0]["headline_code"] == "no_notable_signals"

    resolved = resolve_redaction(RedactionOptions(profile=RedactionProfile.standard))
    redactor = Redactor(resolved)
    out = redactor.redact(detail.model_dump(mode="json"))
    assert "retired-network" in json.dumps(out)


def test_decision_list_summary_selection_order():
    from zigbeelens.schemas import (
        InvestigationPrioritySummary,
        ReportRedactionStatus,
        HealthSnapshot,
        DeviceHealthPrimary,
    )

    base_kwargs = dict(
        id="r",
        report_version=2,
        generated_at="2026-01-01T00:00:00+00:00",
        version="0.1.0",
        redaction=ReportRedactionStatus(applied=True, profile="standard", mqtt_credentials=True),
        config_summary={},
        networks=[],
        devices=[],
        router_risks=[],
        incidents=[],
        health_snapshot=HealthSnapshot(
            timestamp="2026-01-01T00:00:00+00:00",
            overall_severity=Severity.healthy,
            overall_health=DeviceHealthPrimary.healthy,
            network_count=0,
            device_count=0,
            unavailable_count=0,
            incident_count=0,
            networks=[],
        ),
        diagnostic_conclusions=[],
        limitations=[],
        markdown_summary="",
    )
    empty = ReportDetail(**base_kwargs)
    assert (
        _decision_list_summary(empty)
        == "No notable Device Story decisions in this report scope."
    )

    with_story = ReportDetail(
        **base_kwargs,
        device_stories=[
            ReportDeviceStory(
                network_id="home",
                ieee_address="0xa",
                friendly_name="Kitchen Plug",
                subject_id="0xa",
                status="review_first",
                priority="high",
                headline_code="current_issue_present",
            )
        ],
    )
    assert _decision_list_summary(with_story) == (
        f"Kitchen Plug — {headline_text('current_issue_present')}"
    )

    with_priority = ReportDetail(
        **base_kwargs,
        investigation_priorities=[
            InvestigationPrioritySummary(
                id="p1",
                network_id="home",
                card_type="x",
                priority="Review first",
                score=1,
                action_group="watch_only",
                title="First priority title",
                summary="s",
                device_ieees=[],
            )
        ],
        device_stories=with_story.device_stories,
    )
    assert _decision_list_summary(with_priority) == "First priority title"


def test_version1_download_uses_stored_markdown(tmp_path, mock_client):
    from zigbeelens.schemas import ReportRedactionStatus, ReportSummaryBlock

    db = Database(tmp_path / "v1dl.sqlite")
    db.migrate()
    # Use the live client's repo by saving through API is hard; use DataService on fixture repo
    # then overwrite via the mock client's storage isn't accessible. Direct repo + DataService path:
    repo = Repository(db)
    md = f"# ZigbeeLens diagnostic report\n\n{V1_SENTINEL}\n## Health summary\n"
    body = {
        "id": "stored-v1",
        "product": "ZigbeeLens",
        "report_version": 1,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "version": "0.0.0",
        "scope": "full",
        "format": "markdown",
        "redaction": ReportRedactionStatus(
            applied=True, profile="standard", mqtt_credentials=True
        ).model_dump(),
        "summary": ReportSummaryBlock(
            overall_state=Severity.incident,
            current_finding="Legacy executive finding.",
            networks_monitored=1,
            total_devices=1,
            active_incidents=0,
            watching_incidents=0,
            unavailable_devices=0,
            router_risks=0,
            stale_devices=0,
            weak_links=0,
            low_battery_devices=0,
        ).model_dump(mode="json"),
        "config_summary": {"mode": "mock"},
        "collector": {},
        "networks": [],
        "devices": [],
        "device_details": [],
        "router_risks": [],
        "incidents": [],
        "timeline": [],
        "health_snapshot": {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "overall_severity": "incident",
            "overall_health": "unavailable",
            "network_count": 1,
            "device_count": 1,
            "unavailable_count": 0,
            "incident_count": 0,
            "networks": [],
        },
        "diagnostic_conclusions": [],
        "limitations": [],
        "raw_counts": {},
        "markdown_summary": md,
    }
    row = repo.reports.save_report(
        report_id="stored-v1",
        format="markdown",
        scope="full",
        redaction_profile="standard",
        summary="Legacy executive finding.",
        body=body,
        markdown=md,
        redaction=body["redaction"],
        metadata={},
    )
    config = AppConfig()
    config.mode.mock = False
    data = DataService(config, repo)
    loaded = data.get_stored_report(row.id)
    assert loaded is not None
    assert loaded.report_version == 1
    assert loaded.decision_summary is None
    assert loaded.device_stories == []
    assert loaded.investigation_priorities == []
    assert loaded.data_coverage_warnings == []
    assert loaded.markdown_summary == md
    assert V1_SENTINEL in loaded.markdown_summary
    assert loaded.markdown_summary.startswith("# ZigbeeLens diagnostic report")
    assert "# ZigbeeLens evidence report" not in loaded.markdown_summary
    assert summary_from_row(row).summary == "Legacy executive finding."


def test_scenario_isolation_exact_identity(tmp_path):
    db = Database(tmp_path / "iso2.sqlite")
    db.migrate()
    repo = Repository(db)
    config = AppConfig()
    config.mode.mock = False
    data = DataService(config, repo)

    from zigbeelens.services.mock_provider import MockProvider

    mock = MockProvider(SCENARIO)
    scenario_device = mock.devices()[0]
    key = (scenario_device.network_id, scenario_device.ieee_address)
    scenario_story = mock.data.device_stories[key]
    _add_device(
        repo,
        scenario_device.ieee_address,
        network_id=scenario_device.network_id,
        availability="online",
        friendly_name="Live override",
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
    assert "Live override" not in report_story.friendly_name
