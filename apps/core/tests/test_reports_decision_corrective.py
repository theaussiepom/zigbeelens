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
    render_markdown_v3,
    summary_from_row,
)
from zigbeelens.storage.repository import Repository

from report_v3_helpers import (
    minimal_report_v3,
    report_device_details,
    report_networks,
    report_timeline,
)

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
        "zigbeelens.services.report_composition.device_stories_for_devices",
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
    assert len(report_device_details(detail)) == 1
    story = detail.device_stories[0]
    det = report_device_details(detail)[0]
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
    incident = mock.data.incidents[0]
    assert len(incident.affected_devices) >= 2

    calls = {"n": 0}
    original = data.compose_report_scope

    def _wrap(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(data, "compose_report_scope", _wrap)
    device_spy = MagicMock(wraps=data.device)
    monkeypatch.setattr(data, "device", device_spy)
    dashboard_spy = MagicMock(wraps=data.dashboard)
    monkeypatch.setattr(data, "dashboard", dashboard_spy)

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
    assert dashboard_spy.call_count == 0
    assert report_device_details(detail)
    for det in report_device_details(detail):
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
    from zigbeelens.schemas import ReportDomainDetailsV3
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
    detail = minimal_report_v3(
        incidents=[inc],
        events_or_timeline=[sent_event],
        device_stories=[story],
        domain_details=ReportDomainDetailsV3(device_details=[det]),
    )
    cleared = _without_timelines(detail)
    blob = json.dumps(cleared.model_dump(mode="json"))
    assert SENTINEL not in blob
    assert cleared.events_or_timeline == []
    assert all(not s.timeline for s in cleared.device_stories)
    assert all(not i.timeline for i in cleared.incidents)
    assert all(not d.recent_events for d in cleared.domain_details.device_details)


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
    assert report_timeline(detail) == []
    assert detail.events_or_timeline == []
    assert all(not s.timeline for s in detail.device_stories)
    assert all(not i.timeline for i in detail.incidents)
    assert all(not d.recent_events for d in report_device_details(detail))

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
        bool(with_timeline.events_or_timeline)
        or any(s.timeline for s in with_timeline.device_stories)
        or any(i.timeline for i in with_timeline.incidents)
        or any(d.recent_events for d in with_timeline.device_details)
    )
    from zigbeelens.services.mock_provider import MockProvider

    mock = MockProvider(SCENARIO)
    if mock.timeline() or any(i.timeline for i in mock.data.incidents):
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

    detail = minimal_report_v3(incidents=[distinct])
    md = render_markdown_v3(detail)
    assert "Recorded event summary" in md
    # Distinct historical interpretation remains available via the helper;
    # current v3 Markdown presents the incident summary without a separate
    # "Recorded interpretation" legacy section.
    assert _recorded_incident_interpretation(distinct) == "Historical explanatory text"
    assert "Status: open" in md
    assert "Severity: incident" in md


def test_orphan_network_id_redaction_public_safe_and_strict():
    from zigbeelens.decisions.types import DecisionPriority, DecisionStatus
    from zigbeelens.schemas import (
        DataCoverageWarningSummary,
        DecisionCountSummary,
        InvestigationPrioritySummary,
        ReportDomainDetailsV3,
        ReportRedactionStatus,
    )
    from zigbeelens.services.mock_provider import MockProvider

    home = MockProvider(SCENARIO).networks()[0]
    detail = minimal_report_v3(
        redaction=ReportRedactionStatus(
            applied=True, profile="public_safe", mqtt_credentials=True
        ),
        domain_details=ReportDomainDetailsV3(networks=[home]),
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
                status=DecisionStatus.watch,
                priority=DecisionPriority.low,
                headline_code="no_notable_signals",
            )
        ],
        decision_summary=DecisionCountSummary(
            subject_count=1,
            overall_status=DecisionStatus.watch,
            highest_priority=DecisionPriority.low,
            status_counts={DecisionStatus.watch: 1},
            priority_counts={DecisionPriority.low: 1},
            coverage_warning_count=1,
        ),
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
    from zigbeelens.decisions.types import DecisionPriority, DecisionStatus
    from zigbeelens.schemas import InvestigationPrioritySummary

    empty = minimal_report_v3()
    assert (
        _decision_list_summary(empty)
        == "No notable Device Story decisions in this report scope."
    )

    with_story = minimal_report_v3(
        device_stories=[
            ReportDeviceStory(
                network_id="home",
                ieee_address="0xa",
                friendly_name="Kitchen Plug",
                subject_id="0xa",
                status=DecisionStatus.review_first,
                priority=DecisionPriority.high,
                headline_code="current_issue_present",
            )
        ],
    )
    assert _decision_list_summary(with_story) == (
        f"Kitchen Plug — {headline_text('current_issue_present')}"
    )

    with_priority = minimal_report_v3(
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
    from zigbeelens.schemas import ReportRedactionStatus
    from legacy_report_shapes import ReportSummaryBlock

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
    assert isinstance(loaded, dict)
    assert loaded["report_version"] == 1
    assert loaded.get("decision_summary") is None
    assert loaded.get("device_stories") in (None, [])
    assert loaded.get("investigation_priorities") in (None, [])
    assert loaded.get("data_coverage_warnings") in (None, [])
    assert loaded["markdown_summary"] == md
    assert V1_SENTINEL in loaded["markdown_summary"]
    assert loaded["markdown_summary"].startswith("# ZigbeeLens diagnostic report")
    assert "# ZigbeeLens evidence report" not in loaded["markdown_summary"]
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


HOME_PRIVATE_ID = "home-private-id"
HOME_PRIVATE_NAME = "Private Home Name"
HOME_PRIVATE_TOPIC = "zigbee2mqtt/private-home"
OFFICE_SECRET_ID = "office-secret-id"
OFFICE_SECRET_NAME = "Secret Office Name"
OFFICE_SECRET_TOPIC = "zigbee2mqtt/secret-office"

_RAW_NETWORK_VALUES = (
    HOME_PRIVATE_ID,
    HOME_PRIVATE_NAME,
    HOME_PRIVATE_TOPIC,
    OFFICE_SECRET_ID,
    OFFICE_SECRET_NAME,
    OFFICE_SECRET_TOPIC,
)


def _two_network_service(tmp_path) -> tuple[DataService, AppConfig, Repository]:
    from zigbeelens.config.models import ModeConfig, NetworkConfig, StorageConfig

    db_path = tmp_path / "two_net.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = AppConfig(
        mode=ModeConfig(mock=False),
        networks=[
            NetworkConfig(
                id=HOME_PRIVATE_ID,
                name=HOME_PRIVATE_NAME,
                base_topic=HOME_PRIVATE_TOPIC,
            ),
            NetworkConfig(
                id=OFFICE_SECRET_ID,
                name=OFFICE_SECRET_NAME,
                base_topic=OFFICE_SECRET_TOPIC,
            ),
        ],
        storage=StorageConfig(path=str(db_path)),
    )
    repo.sync_networks(config.networks)
    _add_device(
        repo,
        "0xhome1",
        network_id=HOME_PRIVATE_ID,
        friendly_name="Home Plug",
        availability="online",
    )
    return DataService(config, repo), config, repo


def _home_scoped_request(profile: RedactionProfile, *, redact_networks: bool | None = None) -> ReportRequest:
    opts = RedactionOptions(profile=profile)
    if redact_networks is False:
        opts = RedactionOptions(
            profile=profile,
            redact_network_names=False,
            hash_ieee_addresses=False,
            preserve_friendly_names=True,
        )
    return ReportRequest(
        scope=ReportScope.network,
        network_id=HOME_PRIVATE_ID,
        redaction=opts,
    )


def _assert_stable_decision_vocab(detail: ReportDetail) -> None:
    """Network text replacement must not corrupt structured Decision vocabulary."""
    for story in detail.device_stories:
        assert story.status
        assert story.priority
        assert story.headline_code
        for raw in _RAW_NETWORK_VALUES:
            assert raw not in story.status
            assert raw not in story.priority
            assert raw not in story.headline_code
            assert raw not in story.subject_id
    for card in detail.investigation_priorities:
        assert card.card_type
        assert card.action_group
        assert card.priority
        for raw in _RAW_NETWORK_VALUES:
            assert raw not in card.card_type
            assert raw not in card.action_group
            assert raw not in card.priority
    for warning in detail.data_coverage_warnings:
        assert warning.label_code
        for raw in _RAW_NETWORK_VALUES:
            assert raw not in warning.label_code
    for limitation in detail.limitations:
        payload = (
            limitation.model_dump(mode="json")
            if hasattr(limitation, "model_dump")
            else dict(limitation)
        )
        for key in ("code", "limitation_code", "reason_code", "suggested_check_code"):
            value = payload.get(key)
            if isinstance(value, str):
                for raw in _RAW_NETWORK_VALUES:
                    assert raw not in value


def test_scoped_report_redacts_out_of_scope_configured_networks(tmp_path):
    """Home-scoped reports include only Home config_summary networks (Track 3F)."""
    data, config, repo = _two_network_service(tmp_path)

    for profile in (RedactionProfile.public_safe, RedactionProfile.strict):
        detail = generate_report(
            data=data,
            config=config,
            reporting=config.reporting,
            collector={},
            request=_home_scoped_request(profile),
            repo=repo,
        )
        blob = json.dumps(detail.model_dump(mode="json"), sort_keys=True)
        for raw in _RAW_NETWORK_VALUES:
            assert raw not in blob, f"{profile.value}: leaked {raw!r}"

        assert len(report_networks(detail)) == 1
        home_top = report_networks(detail)[0]
        assert home_top.id != HOME_PRIVATE_ID
        assert home_top.name != HOME_PRIVATE_NAME
        assert home_top.base_topic != HOME_PRIVATE_TOPIC
        assert home_top.id.startswith("network_")

        configured = detail.config_summary["networks"]
        assert len(configured) == 1
        configured_ids = {n["id"] for n in configured}
        configured_names = {n["name"] for n in configured}
        configured_topics = {n["base_topic"] for n in configured}
        assert HOME_PRIVATE_ID not in configured_ids
        assert OFFICE_SECRET_ID not in configured_ids
        assert HOME_PRIVATE_NAME not in configured_names
        assert OFFICE_SECRET_NAME not in configured_names
        assert HOME_PRIVATE_TOPIC not in configured_topics
        assert OFFICE_SECRET_TOPIC not in configured_topics
        assert all(str(i).startswith("network_") for i in configured_ids)

        home_cfg = configured[0]
        assert home_cfg["name"] == home_top.id
        assert home_cfg["id"] == home_top.id
        if profile == RedactionProfile.public_safe:
            assert home_top.id == "network_001"
            assert home_cfg["base_topic"].startswith("topic_")
        else:
            assert home_top.id.startswith("network_") and len(home_top.id) > len("network_")

        assert detail.markdown_summary
        for raw in _RAW_NETWORK_VALUES:
            assert raw not in detail.markdown_summary

        _assert_stable_decision_vocab(detail)
        for story in detail.device_stories:
            assert story.network_id == home_top.id

    # Standard / preserved-network control: raw configured identities remain.
    preserved = generate_report(
        data=data,
        config=config,
        reporting=config.reporting,
        collector={},
        request=_home_scoped_request(RedactionProfile.standard, redact_networks=False),
        repo=repo,
    )
    assert len(report_networks(preserved)) == 1
    assert report_networks(preserved)[0].id == HOME_PRIVATE_ID
    assert report_networks(preserved)[0].name == HOME_PRIVATE_NAME
    assert report_networks(preserved)[0].base_topic == HOME_PRIVATE_TOPIC
    assert len(preserved.config_summary["networks"]) == 1
    assert preserved.config_summary["networks"][0]["id"] == HOME_PRIVATE_ID
    assert preserved.config_summary["networks"][0]["name"] == HOME_PRIVATE_NAME
    assert preserved.config_summary["networks"][0]["base_topic"] == HOME_PRIVATE_TOPIC
    blob = json.dumps(preserved.model_dump(mode="json"), sort_keys=True)
    assert HOME_PRIVATE_ID in blob
    assert HOME_PRIVATE_NAME in blob
    assert HOME_PRIVATE_TOPIC in blob
    assert OFFICE_SECRET_ID not in blob
    assert OFFICE_SECRET_NAME not in blob
    assert OFFICE_SECRET_TOPIC not in blob
