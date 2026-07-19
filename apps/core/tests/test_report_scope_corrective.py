"""Track 3F corrective: historical vs active, scoped health, identity, clock, reads."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from zigbeelens.config.models import (
    AppConfig,
    ModeConfig,
    NetworkConfig,
    ReportingConfig,
    StorageConfig,
)
from zigbeelens.db.connection import Database
from zigbeelens.diagnostics.coordinator import EvaluationCoordinator
from zigbeelens.diagnostics.incidents.models import AffectedDevice, IncidentCandidate, IncidentType
from zigbeelens.diagnostics.incidents.lifecycle import IncidentLifecycleManager
from zigbeelens.diagnostics.incidents.service import IncidentDiagnosticService
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.schemas import (
    Confidence,
    IncidentScope,
    InvestigationPrioritySummary,
    RedactionOptions,
    ReportFormat,
    ReportRequest,
    ReportScope,
    Severity,
)
from zigbeelens.services.data_service import DataService
from zigbeelens.services.device_decision_badge import device_decision_badge_from_story
from zigbeelens.services.reports import generate_report
from zigbeelens.storage.repository import Repository
from performance.query_instrumentation import install_counter

from report_v3_helpers import (
    report_active_incidents,
    report_device_details,
    report_devices,
    report_networks,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
TARGET = "0xtarget"
SAME_NET_OTHER = "0xsameother"
OFF_SCOPE = "0xoffscope"


def _service(tmp_path: Path) -> tuple[DataService, AppConfig, Repository, EvaluationCoordinator]:
    db = Database(tmp_path / "corrective3f.sqlite")
    db.migrate()
    repo = Repository(db)
    config = AppConfig(
        mode=ModeConfig(mock=False),
        networks=[
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
            NetworkConfig(id="office", name="Office", base_topic="z2m-office"),
        ],
        storage=StorageConfig(path=str(tmp_path / "corrective3f.sqlite")),
        reporting=ReportingConfig(max_recent_events=50),
    )
    repo.sync_networks(config.networks)
    health = HealthDiagnosticService(config, repo)
    incidents = IncidentDiagnosticService(config, repo)
    coord = EvaluationCoordinator(health, incidents)
    service = DataService(config, repo, health, incidents, coord)
    return service, config, repo, coord


def _add_device(
    repo: Repository,
    network_id: str,
    ieee: str,
    name: str,
    *,
    availability: str = "online",
    last_seen: str | None = None,
) -> None:
    repo.upsert_device(
        network_id=network_id,
        ieee_address=ieee,
        friendly_name=name,
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )
    repo.ensure_device_current_state(network_id, ieee)
    repo.update_device_current_state(
        network_id=network_id,
        ieee_address=ieee,
        availability=availability,
        last_seen=last_seen or NOW.isoformat(),
    )


def _add_incident(
    repo: Repository,
    *,
    incident_id: str,
    incident_type: str,
    dedup_key: str,
    network_ids: list[str],
    devices: list[tuple[str, str]] | None = None,
    title: str,
    lifecycle_state: str = "open",
    severity: str = "incident",
) -> None:
    repo.incidents.insert_incident(
        incident_id=incident_id,
        dedup_key=dedup_key,
        incident_type=incident_type,
        lifecycle_state=lifecycle_state,
        severity=severity,
        scope="device" if devices else "network",
        confidence="high",
        title=title,
        summary=title,
        explanation=f"interpretation:{title}",
        evidence=["evidence"],
        counter_evidence=["counter"],
        limitations=["limit"],
        opened_at=NOW.isoformat(),
        updated_at=NOW.isoformat(),
    )
    if lifecycle_state == "resolved":
        repo.db.conn.execute(
            "UPDATE incidents SET resolved_at = ? WHERE id = ?",
            (NOW.isoformat(), incident_id),
        )
        repo.db.conn.commit()
    if devices:
        repo.replace_incident_devices(
            incident_id,
            [AffectedDevice(nid, ieee) for nid, ieee in devices],
        )
    repo.replace_incident_networks(incident_id, network_ids)


def _report(
    service: DataService,
    config: AppConfig,
    request: ReportRequest,
    *,
    now: datetime = NOW,
    collector: dict | None = None,
):
    return generate_report(
        data=service,
        config=config,
        reporting=config.reporting,
        collector=collector
        or {
            "enabled": True,
            "connected": True,
            "subscribed_topics_count": 2,
            "networks": {
                "home": {"base_topic": "zigbee2mqtt"},
                "office": {"base_topic": "z2m-office"},
            },
        },
        request=request,
        now=now,
    )


def test_resolved_only_device_report_keeps_history_out_of_active(tmp_path: Path):
    service, config, repo, coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "HealthyTarget")
    _add_device(repo, "office", OFF_SCOPE, "OffScopeUnhealthy", availability="offline")
    _add_incident(
        repo,
        incident_id="inc-resolved",
        incident_type="single_device_unavailable",
        dedup_key=f"single_device_unavailable:home:{TARGET}",
        network_ids=["home"],
        devices=[("home", TARGET)],
        title="ResolvedLowBattery",
        lifecycle_state="resolved",
        severity="watch",
    )
    coord.evaluate_all(now=NOW)

    detail = _report(
        service,
        config,
        ReportRequest(
            scope=ReportScope.device,
            network_id="home",
            device=TARGET,
            format=ReportFormat.json,
            redaction=RedactionOptions(include_timeline=False),
        ),
    )
    assert len(detail.incidents) == 1
    assert detail.incidents[0].status.value == "resolved"
    assert report_active_incidents(detail) == []
    assert report_devices(detail)[0].incident_affected is False
    assert report_networks(detail)[0].unavailable_count == 0
    assert report_networks(detail)[0].active_incident_count == 0
    assert detail.decision_summary is not None
    dumped = detail.model_dump_json()
    assert OFF_SCOPE not in dumped
    assert "office" not in (detail.collector.get("networks") or {})


def test_resolved_incident_report_preserves_record_not_current_finding(tmp_path: Path):
    service, config, repo, coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "Target")
    _add_incident(
        repo,
        incident_id="inc-resolved-sel",
        incident_type="single_device_unavailable",
        dedup_key=f"single_device_unavailable:home:{TARGET}",
        network_ids=["home"],
        devices=[("home", TARGET)],
        title="ResolvedSelected",
        lifecycle_state="resolved",
        severity="critical",
    )
    coord.evaluate_all(now=NOW)

    detail = _report(
        service,
        config,
        ReportRequest(
            scope=ReportScope.incident,
            incident_id="inc-resolved-sel",
            format=ReportFormat.json,
            redaction=RedactionOptions(include_timeline=False),
        ),
    )
    assert detail.incidents[0].id == "inc-resolved-sel"
    assert detail.incidents[0].status.value == "resolved"
    assert "interpretation:ResolvedSelected" in detail.incidents[0].interpretation
    assert report_active_incidents(detail) == []
    assert detail.decision_summary is not None
    # Historical severity remains on the stored incident record.
    assert detail.incidents[0].severity == Severity.critical


def test_network_resolved_history_not_in_current_finding(tmp_path: Path):
    service, config, repo, coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "Target")
    _add_incident(
        repo,
        incident_id="inc-net-resolved",
        incident_type="bridge_offline",
        dedup_key="bridge_offline:home",
        network_ids=["home"],
        title="OldBridge",
        lifecycle_state="resolved",
        severity="critical",
    )
    coord.evaluate_all(now=NOW)

    detail = _report(
        service,
        config,
        ReportRequest(
            scope=ReportScope.network,
            network_id="home",
            format=ReportFormat.json,
            redaction=RedactionOptions(include_timeline=False),
        ),
    )
    assert any(i.id == "inc-net-resolved" for i in detail.incidents)
    assert report_active_incidents(detail) == []
    assert report_networks(detail)[0].active_incident_count == 0
    # Resolved history must not appear as an open/critical active severity.
    assert report_networks(detail)[0].active_incident_severity in {
        Severity.healthy,
        Severity.watch,
    }
    assert report_networks(detail)[0].active_incident_severity != Severity.critical
    # Historical incident titles may appear in the incidents section; they must not
    # drive the current network active-severity projection above.
    assert report_active_incidents(detail) == []


def test_open_watching_remain_current(tmp_path: Path):
    service, config, repo, coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "Target", availability="offline")
    _add_incident(
        repo,
        incident_id="inc-open",
        incident_type="single_device_unavailable",
        dedup_key=f"single_device_unavailable:home:{TARGET}",
        network_ids=["home"],
        devices=[("home", TARGET)],
        title="OpenNow",
        lifecycle_state="open",
    )
    _add_incident(
        repo,
        incident_id="inc-watch",
        incident_type="low_battery_cluster",
        dedup_key="low_battery_cluster:home",
        network_ids=["home"],
        title="WatchingNow",
        lifecycle_state="watching",
        severity="watch",
    )
    coord.evaluate_all(now=NOW)

    detail = _report(
        service,
        config,
        ReportRequest(
            scope=ReportScope.network,
            network_id="home",
            format=ReportFormat.json,
            redaction=RedactionOptions(include_timeline=False),
        ),
    )
    assert {i.id for i in report_active_incidents(detail)} == {"inc-open", "inc-watch"}
    assert report_devices(detail)[0].incident_affected is True
    assert report_networks(detail)[0].active_incident_count == 2
    open_count = sum(1 for i in report_active_incidents(detail) if i.status.value == "open")
    watch_count = sum(1 for i in report_active_incidents(detail) if i.status.value == "watching")
    assert open_count == 1
    assert watch_count == 1


def test_off_scope_unhealthy_network_does_not_leak_into_device_severity(tmp_path: Path):
    service, config, repo, coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "HealthyHome")
    for i in range(4):
        _add_device(
            repo,
            "office",
            f"0xbad{i}",
            f"BadOffice{i}",
            availability="offline",
        )
    coord.evaluate_all(now=NOW)

    plain = RedactionOptions(include_timeline=False, hash_ieee_addresses=False)
    device_detail = _report(
        service,
        config,
        ReportRequest(
            scope=ReportScope.device,
            network_id="home",
            device=TARGET,
            format=ReportFormat.json,
            redaction=plain,
        ),
    )
    full_detail = _report(
        service,
        config,
        ReportRequest(
            scope=ReportScope.full,
            format=ReportFormat.json,
            redaction=plain,
        ),
    )
    assert report_networks(device_detail)[0].device_count == 1
    assert report_networks(device_detail)[0].unavailable_count == 0
    assert len(report_devices(device_detail)) == 1
    assert device_detail.decision_summary is not None
    unavailable_full = sum(n.unavailable_count for n in report_networks(full_detail))
    assert unavailable_full >= 4
    assert "0xbad0" in full_detail.model_dump_json()
    assert "0xbad0" not in device_detail.model_dump_json()


def test_priority_device_ieees_scoped_with_same_network_sentinel(tmp_path: Path):
    service, config, repo, _coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "Target")
    _add_device(repo, "home", SAME_NET_OTHER, "SameNetOther")

    priority = InvestigationPrioritySummary(
        id="p1",
        network_id="home",
        card_type="router_neighbourhood_review",
        priority="high",
        score=10,
        action_group="",
        title="Review neighbourhood",
        summary="includes two devices",
        device_ieees=[TARGET, SAME_NET_OTHER],
        latest_supporting_evidence_at=None,
    )

    with patch(
        "zigbeelens.services.report_composition.compose_dashboard_investigation_priorities",
        return_value=[priority],
    ):
        detail = _report(
            service,
            config,
            ReportRequest(
                scope=ReportScope.device,
                network_id="home",
                device=TARGET,
                format=ReportFormat.json,
                redaction=RedactionOptions(
                    include_timeline=False, hash_ieee_addresses=False
                ),
            ),
        )
    assert len(detail.investigation_priorities) == 1
    assert detail.investigation_priorities[0].device_ieees == [TARGET]
    assert SAME_NET_OTHER not in detail.model_dump_json()


def test_collector_networks_scoped(tmp_path: Path):
    service, config, repo, _coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "Target")
    detail = _report(
        service,
        config,
        ReportRequest(
            scope=ReportScope.device,
            network_id="home",
            device=TARGET,
            format=ReportFormat.json,
            redaction=RedactionOptions(include_timeline=False),
        ),
        collector={
            "enabled": True,
            "connected": False,
            "subscribed_topics_count": 9,
            "networks": {
                "home": {"base_topic": "zigbee2mqtt"},
                "office": {"base_topic": "z2m-office", "secret": "office-only"},
            },
        },
    )
    assert detail.collector_status["enabled"] is True
    assert detail.collector_status["connected"] is False
    assert set(detail.collector_status["networks"]) == {"home"}
    assert "office" not in detail.model_dump_json()
    assert "office-only" not in detail.markdown_summary


def test_no_duplicate_selected_device_read(tmp_path: Path):
    service, config, repo, _coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "Target")
    _add_device(repo, "home", SAME_NET_OTHER, "Other")
    _add_incident(
        repo,
        incident_id="inc-target",
        incident_type="single_device_unavailable",
        dedup_key=f"single_device_unavailable:home:{TARGET}",
        network_ids=["home"],
        devices=[("home", TARGET), ("home", "0xdeleted")],
        title="WithMissingRef",
        lifecycle_state="resolved",
    )

    original = repo.get_devices_by_keys
    calls: list[list[tuple[str, str]]] = []

    def spy(keys):
        key_list = list(keys)
        calls.append(key_list)
        return original(key_list)

    with patch.object(repo, "get_devices_by_keys", side_effect=spy):
        detail = _report(
            service,
            config,
            ReportRequest(
                scope=ReportScope.device,
                network_id="home",
                device=TARGET,
                format=ReportFormat.json,
                redaction=RedactionOptions(
                    include_timeline=False, hash_ieee_addresses=False
                ),
            ),
        )
    # Initial plan load may fetch the target once; later incident-ref loads must not.
    target_calls = [call for call in calls if ("home", TARGET) in call]
    assert len(target_calls) == 1
    assert target_calls[0] == [("home", TARGET)]
    # Missing deleted ref may be fetched once without re-reading the target.
    missing_calls = [call for call in calls if ("home", "0xdeleted") in call]
    assert len(missing_calls) <= 1
    assert any(i.id == "inc-target" for i in detail.incidents)
    assert detail.incidents[0].affected_devices
    assert all(ref.ieee_address == TARGET for ref in detail.incidents[0].affected_devices)


def test_device_story_batch_once_and_badge_parity(tmp_path: Path):
    service, config, repo, coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "Target")
    coord.evaluate_all(now=NOW)

    from zigbeelens.decisions.device_story import device_stories_for_devices as real_batch

    captured: dict = {"count": 0, "stories": {}}

    def _spy(*args, **kwargs):
        captured["count"] += 1
        stories = real_batch(*args, **kwargs)
        captured["stories"] = stories
        return stories

    with patch(
        "zigbeelens.services.report_composition.device_stories_for_devices",
        side_effect=_spy,
    ):
        detail = _report(
            service,
            config,
            ReportRequest(
                scope=ReportScope.device,
                network_id="home",
                device=TARGET,
                format=ReportFormat.json,
                redaction=RedactionOptions(
                    include_timeline=True, hash_ieee_addresses=False
                ),
            ),
        )
    assert captured["count"] == 1
    story = captured["stories"][("home", TARGET)]
    expected = device_decision_badge_from_story(story)
    assert report_devices(detail)[0].decision == expected
    assert report_device_details(detail)[0].decision == expected


def test_reference_now_threaded_to_story_and_generated_at(tmp_path: Path):
    service, config, repo, _coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "Target")
    frozen = datetime(2025, 1, 15, 8, 30, tzinfo=timezone.utc)

    with patch(
        "zigbeelens.services.report_composition.device_stories_for_devices",
        return_value={},
    ) as stories_mock, patch(
        "zigbeelens.services.report_composition.compose_dashboard_investigation_priorities",
        return_value=[],
    ) as inv_mock, patch(
        "zigbeelens.services.report_composition.compose_dashboard_coverage_warnings",
        return_value=[],
    ) as cov_mock:
        detail = _report(
            service,
            config,
            ReportRequest(
                scope=ReportScope.device,
                network_id="home",
                device=TARGET,
                format=ReportFormat.json,
                redaction=RedactionOptions(include_timeline=False),
            ),
            now=frozen,
        )
    assert stories_mock.call_args.kwargs["now"] == frozen
    assert inv_mock.call_args.kwargs["now"] == frozen
    assert cov_mock.call_args.kwargs["now"] == frozen
    assert detail.generated_at.startswith("2025-01-15T08:30:00")
    assert detail.generated_at.startswith("2025-01-15T08:30:00")


def test_timeline_false_zero_event_reads(tmp_path: Path):
    service, config, repo, _coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "Target")
    _add_incident(
        repo,
        incident_id="inc-open",
        incident_type="single_device_unavailable",
        dedup_key=f"single_device_unavailable:home:{TARGET}",
        network_ids=["home"],
        devices=[("home", TARGET)],
        title="Open",
    )
    counter = install_counter(repo)
    counter.reset()
    _report(
        service,
        config,
        ReportRequest(
            scope=ReportScope.device,
            network_id="home",
            device=TARGET,
            format=ReportFormat.json,
            redaction=RedactionOptions(include_timeline=False),
        ),
    )
    event_reads = [
        sql
        for sql in counter.stats.statements
        if "FROM events" in sql or "from events" in sql.lower()
    ]
    assert event_reads == []
    assert counter.stats.category_counts.get("read.events", 0) == 0


def test_lifecycle_get_by_dedup_includes_networks_no_n_plus_one(tmp_path: Path):
    service, config, repo, _coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "Target", availability="offline")
    mgr = IncidentLifecycleManager(config, repo)
    candidate = IncidentCandidate(
        dedup_key="",
        incident_type=IncidentType.single_device_unavailable,
        severity=Severity.incident,
        scope=IncidentScope.device,
        confidence=Confidence.high,
        title="Offline",
        summary="Offline",
        explanation="Offline",
        evidence=["e"],
        counter_evidence=[],
        limitations=[],
        network_ids=["home"],
        affected_devices=[AffectedDevice("home", TARGET)],
        active=True,
    )
    mgr.sync([candidate], now=NOW)
    existing = repo.get_incident_by_dedup_key(candidate.dedup_key)
    assert existing is not None
    assert existing["network_ids"] == ("home",)

    original = repo.list_incident_networks
    calls = {"n": 0}

    def spy(incident_id):
        calls["n"] += 1
        return original(incident_id)

    updated = IncidentCandidate(
        dedup_key="",
        incident_type=IncidentType.single_device_unavailable,
        severity=Severity.incident,
        scope=IncidentScope.device,
        confidence=Confidence.high,
        title="Offline updated",
        summary="Offline updated",
        explanation="Offline updated",
        evidence=["e2"],
        counter_evidence=[],
        limitations=[],
        network_ids=["home"],
        affected_devices=[AffectedDevice("home", TARGET)],
        active=True,
    )
    with patch.object(repo, "list_incident_networks", side_effect=spy):
        with patch.object(repo.incidents, "list_incident_networks", side_effect=spy):
            mgr.sync([updated], now=NOW + timedelta(minutes=1))
    assert calls["n"] == 0


def test_preview_remains_zero_commits(tmp_path: Path):
    service, config, repo, coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "Target")
    # Warm evaluation cache so report composition does not trigger writes.
    coord.evaluate_all(now=NOW)
    counter = install_counter(repo)
    counter.reset()
    _report(
        service,
        config,
        ReportRequest(
            scope=ReportScope.full,
            format=ReportFormat.json,
            redaction=RedactionOptions(include_timeline=False),
        ),
    )
    assert counter.stats.commit_count == 0
