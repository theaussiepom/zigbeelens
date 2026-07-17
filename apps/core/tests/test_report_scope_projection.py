"""Track 3F final projection corrections: collector list, severity, unknown, mock parity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zigbeelens.config.models import (
    AppConfig,
    ModeConfig,
    NetworkConfig,
    ReportingConfig,
    StorageConfig,
)
from zigbeelens.db.connection import Database
from zigbeelens.diagnostics.coordinator import EvaluationCoordinator
from zigbeelens.diagnostics.incidents.models import AffectedDevice
from zigbeelens.diagnostics.incidents.service import IncidentDiagnosticService
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.mock.fixtures import (
    ScenarioData,
    conclusion,
    device,
    network,
)
from zigbeelens.mqtt.lifecycle import collector_status_dict
from zigbeelens.mqtt.models import MqttCollectorStatus, NetworkSubscriptionStatus
from zigbeelens.schemas import (
    Availability,
    Confidence,
    DashboardPayload,
    DeviceHealth,
    DeviceHealthPrimary,
    DeviceType,
    HealthSnapshot,
    Incident,
    IncidentDeviceRef,
    IncidentScope,
    IncidentStatus,
    PowerSource,
    RedactionOptions,
    ReportFormat,
    ReportRequest,
    ReportScope,
    RouterRisk,
    Severity,
)
from zigbeelens.services.data_service import DataService
from zigbeelens.services.report_active_severity import pick_active_incident_severity
from zigbeelens.services.report_composition import (
    compose_mock_report_scope,
    project_report_detail,
)
from zigbeelens.services.reports import (
    _apply_report_compatibility_sections,
    generate_report,
)
from zigbeelens.storage.repository import Repository

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
TARGET = "0xtarget"
KNOWN = "0xknown"
UNKNOWN = "0xunknown"
HOME_ROUTER = "0xhomerouter"
OFFICE_BAD = "0xofficebad"
ISO = NOW.isoformat()


def _service(tmp_path: Path) -> tuple[DataService, AppConfig, Repository, EvaluationCoordinator]:
    db = Database(tmp_path / "projection3f.sqlite")
    db.migrate()
    repo = Repository(db)
    config = AppConfig(
        mode=ModeConfig(mock=False),
        networks=[
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
            NetworkConfig(id="office", name="Office", base_topic="z2m-office"),
        ],
        storage=StorageConfig(path=str(tmp_path / "projection3f.sqlite")),
        reporting=ReportingConfig(max_recent_events=50),
    )
    repo.sync_networks(config.networks)
    health = HealthDiagnosticService(config, repo)
    incidents = IncidentDiagnosticService(config, repo)
    coord = EvaluationCoordinator(health, incidents)
    return DataService(config, repo, health, incidents, coord), config, repo, coord


def _add_device(
    repo: Repository,
    network_id: str,
    ieee: str,
    name: str,
    *,
    availability: str = "online",
    last_seen: str | None = ISO,
    device_type: str = "EndDevice",
) -> None:
    repo.upsert_device(
        network_id=network_id,
        ieee_address=ieee,
        friendly_name=name,
        device_type=device_type,
        power_source="Battery",
        interview_state="successful",
    )
    repo.ensure_device_current_state(network_id, ieee)
    updates: dict = {"availability": availability}
    if last_seen is not None:
        updates["last_seen"] = last_seen
    repo.update_device_current_state(network_id=network_id, ieee_address=ieee, **updates)


def _add_unknown_device(repo: Repository, network_id: str, ieee: str, name: str) -> None:
    """Device with no usable telemetry → primary unknown after evaluation."""
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
        availability="unknown",
        last_seen=None,
        last_payload_at=None,
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
        opened_at=ISO,
        updated_at=ISO,
    )
    if lifecycle_state == "resolved":
        repo.db.conn.execute(
            "UPDATE incidents SET resolved_at = ? WHERE id = ?",
            (ISO, incident_id),
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
    collector: dict | None = None,
    scenario: str | None = None,
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
        scenario=scenario,
        now=NOW,
    )


PRODUCTION_COLLECTOR_LIST = {
    "enabled": True,
    "connected": True,
    "subscribed_topics_count": 4,
    "last_message_at": ISO,
    "last_error": None,
    "networks": [
        {"network_id": "home", "subscribed": True},
        {"network_id": "office", "subscribed": True},
    ],
}


def test_production_collector_list_scoped_from_home_report(tmp_path: Path):
    service, config, repo, _coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "HomeTarget")
    detail = _report(
        service,
        config,
        ReportRequest(
            scope=ReportScope.device,
            network_id="home",
            device=TARGET,
            format=ReportFormat.json,
            redaction=RedactionOptions(include_timeline=False, hash_ieee_addresses=False),
        ),
        collector=PRODUCTION_COLLECTOR_LIST,
    )
    assert detail.collector["enabled"] is True
    assert detail.collector["connected"] is True
    assert detail.collector["subscribed_topics_count"] == 4
    assert detail.collector["networks"] == [{"network_id": "home", "subscribed": True}]
    assert detail.collector_status["networks"] == [{"network_id": "home", "subscribed": True}]
    dumped = detail.model_dump_json()
    assert '"network_id":"office"' not in dumped
    assert "office" not in detail.markdown_summary.lower() or "office" not in dumped


def test_production_collector_list_via_collector_status_dict(tmp_path: Path):
    service, config, repo, _coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "HomeTarget")
    status = MqttCollectorStatus(
        enabled=True,
        connected=True,
        subscribed_topics_count=2,
        last_message_at=ISO,
        last_error=None,
        networks=[
            NetworkSubscriptionStatus("home", "zigbee2mqtt", subscribed=True),
            NetworkSubscriptionStatus("office", "z2m-office", subscribed=True),
        ],
    )
    collector = SimpleNamespace(status=lambda: status)
    ctx = SimpleNamespace(collector=collector, repo=repo)
    production = collector_status_dict(ctx)
    assert isinstance(production["networks"], list)
    assert {n["network_id"] for n in production["networks"]} == {"home", "office"}

    detail = _report(
        service,
        config,
        ReportRequest(
            scope=ReportScope.network,
            network_id="home",
            format=ReportFormat.json,
            redaction=RedactionOptions(include_timeline=False, hash_ieee_addresses=False),
        ),
        collector=production,
    )
    assert detail.collector["networks"] == [{"network_id": "home", "subscribed": True}]
    assert detail.collector_status["networks"] == [{"network_id": "home", "subscribed": True}]
    assert "office" not in detail.model_dump_json()


def test_collector_dict_shape_regression_retained(tmp_path: Path):
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
    assert set(detail.collector["networks"]) == {"home"}
    assert "office-only" not in detail.markdown_summary


def test_open_watch_severity_device_report(tmp_path: Path):
    service, config, repo, coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "BatteryTarget")
    _add_incident(
        repo,
        incident_id="inc-watch-batt",
        incident_type="low_battery_cluster",
        dedup_key="low_battery_cluster:home",
        network_ids=["home"],
        devices=[("home", TARGET)],
        title="LowBatteryWatch",
        lifecycle_state="open",
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
    # Scope-local active severity drives compatibility projections.
    assert detail.active_incidents[0].severity == Severity.watch
    assert detail.diagnostic_conclusions[0].severity == Severity.watch or (
        detail.summary is not None and detail.summary.overall_state == Severity.watch
    )
    assert detail.summary is not None
    assert detail.summary.overall_state == Severity.watch
    assert detail.networks[0].incident_state == Severity.watch
    assert detail.health_snapshot.overall_severity == Severity.watch
    assert detail.networks[0].active_incident_count == 1


def test_open_watch_severity_incident_report(tmp_path: Path):
    service, config, repo, coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "BatteryTarget")
    _add_incident(
        repo,
        incident_id="inc-watch-sel",
        incident_type="low_battery_cluster",
        dedup_key="low_battery_cluster:home:sel",
        network_ids=["home"],
        devices=[("home", TARGET)],
        title="SelectedWatch",
        lifecycle_state="open",
        severity="watch",
    )
    coord.evaluate_all(now=NOW)

    detail = _report(
        service,
        config,
        ReportRequest(
            scope=ReportScope.incident,
            incident_id="inc-watch-sel",
            format=ReportFormat.json,
            redaction=RedactionOptions(include_timeline=False),
        ),
    )
    assert detail.diagnostic_conclusions[0].severity == Severity.watch
    assert detail.summary is not None
    assert detail.summary.overall_state == Severity.watch
    assert detail.networks[0].incident_state == Severity.watch
    assert detail.health_snapshot.overall_severity == Severity.watch


def test_open_incident_severity_remains_incident(tmp_path: Path):
    service, config, repo, coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "Target", availability="offline")
    _add_incident(
        repo,
        incident_id="inc-sev-incident",
        incident_type="single_device_unavailable",
        dedup_key=f"single_device_unavailable:home:{TARGET}",
        network_ids=["home"],
        devices=[("home", TARGET)],
        title="OpenIncident",
        severity="incident",
    )
    coord.evaluate_all(now=NOW)
    detail = _report(
        service,
        config,
        ReportRequest(
            scope=ReportScope.incident,
            incident_id="inc-sev-incident",
            format=ReportFormat.json,
            redaction=RedactionOptions(include_timeline=False),
        ),
    )
    assert detail.diagnostic_conclusions[0].severity == Severity.incident
    assert detail.summary.overall_state == Severity.incident
    assert detail.networks[0].incident_state == Severity.incident
    assert detail.health_snapshot.overall_severity == Severity.incident


def test_critical_severity_remains_critical(tmp_path: Path):
    service, config, repo, coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "Target")
    _add_incident(
        repo,
        incident_id="inc-critical",
        incident_type="bridge_offline",
        dedup_key="bridge_offline:home",
        network_ids=["home"],
        title="BridgeDown",
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
    # Network complete-scope may use network health; active open critical must not be collapsed.
    assert any(i.severity == Severity.critical for i in detail.active_incidents)
    assert detail.summary.overall_state == Severity.critical or (
        detail.diagnostic_conclusions[0].severity == Severity.critical
    )


def test_watching_precedence_uses_stored_severity(tmp_path: Path):
    service, config, repo, _coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "Target")
    _add_incident(
        repo,
        incident_id="inc-open-watch",
        incident_type="low_battery_cluster",
        dedup_key="low_battery_cluster:home:open",
        network_ids=["home"],
        devices=[("home", TARGET)],
        title="OpenWatch",
        lifecycle_state="open",
        severity="watch",
    )
    _add_incident(
        repo,
        incident_id="inc-watching-incident",
        incident_type="stale_reporting_cluster",
        dedup_key="stale_reporting_cluster:home",
        network_ids=["home"],
        title="WatchingIncidentSev",
        lifecycle_state="watching",
        severity="incident",
    )
    rows = [
        {"id": "inc-open-watch", "lifecycle_state": "open", "severity": "watch"},
        {"id": "inc-watching-incident", "lifecycle_state": "watching", "severity": "incident"},
    ]
    assert pick_active_incident_severity(rows) == Severity.watch

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
    assert detail.summary.overall_state == Severity.watch
    assert detail.networks[0].incident_state == Severity.watch


def test_resolved_does_not_drive_active_severity(tmp_path: Path):
    service, config, repo, coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "Healthy")
    _add_incident(
        repo,
        incident_id="inc-resolved-crit",
        incident_type="bridge_offline",
        dedup_key="bridge_offline:home:old",
        network_ids=["home"],
        title="OldCritical",
        lifecycle_state="resolved",
        severity="critical",
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
    assert detail.active_incidents == []
    assert detail.summary.overall_state != Severity.critical
    assert detail.health_snapshot.overall_severity != Severity.critical


def test_unknown_count_one_device_report(tmp_path: Path):
    service, config, repo, _coord = _service(tmp_path)
    _add_unknown_device(repo, "home", UNKNOWN, "UnknownTarget")
    detail = _report(
        service,
        config,
        ReportRequest(
            scope=ReportScope.device,
            network_id="home",
            device=UNKNOWN,
            format=ReportFormat.json,
            redaction=RedactionOptions(include_timeline=False),
        ),
    )
    assert detail.health_snapshot.overall_health == DeviceHealthPrimary.unknown
    assert detail.health_snapshot.networks[0]["unknown_count"] == 1
    assert detail.health_snapshot.networks[0]["unavailable_count"] == 0


def test_unknown_count_two_represented_devices(tmp_path: Path):
    service, config, repo, _coord = _service(tmp_path)
    _add_device(repo, "home", KNOWN, "Known")
    _add_unknown_device(repo, "home", UNKNOWN, "Unknown")
    _add_incident(
        repo,
        incident_id="inc-two",
        incident_type="low_battery_cluster",
        dedup_key="low_battery_cluster:home:two",
        network_ids=["home"],
        devices=[("home", KNOWN), ("home", UNKNOWN)],
        title="TwoDevices",
        severity="watch",
    )
    detail = _report(
        service,
        config,
        ReportRequest(
            scope=ReportScope.incident,
            incident_id="inc-two",
            format=ReportFormat.json,
            redaction=RedactionOptions(include_timeline=False),
        ),
    )
    assert detail.health_snapshot.device_count == 2
    assert detail.health_snapshot.networks[0]["unknown_count"] == 1


def test_off_scope_unknown_does_not_affect_narrow_report(tmp_path: Path):
    service, config, repo, _coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "HealthyHome")
    _add_unknown_device(repo, "office", OFFICE_BAD, "OfficeUnknown")
    detail = _report(
        service,
        config,
        ReportRequest(
            scope=ReportScope.device,
            network_id="home",
            device=TARGET,
            format=ReportFormat.json,
            redaction=RedactionOptions(include_timeline=False, hash_ieee_addresses=False),
        ),
    )
    assert detail.health_snapshot.networks[0]["unknown_count"] == 0
    assert OFFICE_BAD not in detail.model_dump_json()


# ---------------------------------------------------------------------------
# Mock / live scope parity
# ---------------------------------------------------------------------------


def _unknown_health() -> DeviceHealth:
    return DeviceHealth(
        primary=DeviceHealthPrimary.unknown,
        severity=Severity.watch,
        confidence=Confidence.low,
        evidence=[],
        limitations=["Insufficient telemetry"],
    )


def _isolation_scenario(*, with_home_watch_incident: bool = False) -> ScenarioData:
    home_target = device("home", TARGET, "HomeTarget")
    home_router = device(
        "home",
        HOME_ROUTER,
        "HomeRouterSentinel",
        device_type=DeviceType.Router,
        power=PowerSource.Mains,
    )
    office_bad = device(
        "office",
        OFFICE_BAD,
        "OfficeUnhealthySentinel",
        availability=Availability.offline,
        health=DeviceHealth(
            primary=DeviceHealthPrimary.unavailable,
            severity=Severity.incident,
            confidence=Confidence.high,
            evidence=["offline"],
            limitations=[],
        ),
        incident_affected=True,
        sort_priority=1,
    )
    home_devices = [home_target, home_router]
    office_devices = [office_bad]
    office_finding = conclusion(
        "office_dashboard_finding_SENTINEL",
        Severity.incident,
        IncidentScope.network,
        Confidence.high,
        "OFFICE_DASHBOARD_FINDING_SENTINEL should never appear on Home-only reports.",
    )
    home_net = network(
        "home",
        "Home",
        "zigbee2mqtt",
        devices=home_devices,
        incident_state=Severity.incident,
        active_incidents=2,
    )
    office_net = network(
        "office",
        "Office",
        "z2m-office",
        devices=office_devices,
        incident_state=Severity.incident,
        active_incidents=1,
    )
    router_risk = RouterRisk(
        network_id="home",
        ieee_address=HOME_ROUTER,
        friendly_name="HomeRouterSentinel",
        availability=Availability.online,
        correlated_affected_devices=0,
        risk=conclusion(
            "router_risk_SENTINEL",
            Severity.watch,
            IncidentScope.device,
            Confidence.medium,
            "HOME_ROUTER_RISK_SENTINEL",
        ),
    )
    incidents: list[Incident] = []
    if with_home_watch_incident:
        finding = conclusion(
            "low_battery_cluster",
            Severity.watch,
            IncidentScope.device,
            Confidence.high,
            "Home watch incident for battery cluster.",
        )
        incidents.append(
            Incident(
                id="inc-home-watch",
                type="low_battery_cluster",
                status=IncidentStatus.open,
                severity=Severity.watch,
                scope=IncidentScope.device,
                confidence=Confidence.high,
                title="HomeWatchBattery",
                summary="Home watch battery cluster",
                interpretation="watch only",
                network_ids=["home"],
                affected_device_count=1,
                affected_devices=[
                    IncidentDeviceRef(
                        network_id="home",
                        ieee_address=TARGET,
                        friendly_name="HomeTarget",
                        health_primary=DeviceHealthPrimary.healthy,
                    )
                ],
                opened_at=ISO,
                updated_at=ISO,
                evidence=finding.evidence,
                counter_evidence=[],
                limitations=[],
                timeline=[],
                conclusion=finding,
            )
        )
    dash = DashboardPayload(
        generated_at=ISO,
        scenario="isolation_3f",
        overall_severity=Severity.incident,
        current_finding=office_finding,
        active_incident_count=1,
        watching_incident_count=0,
        networks=[home_net, office_net],
        top_affected_devices=[office_bad],
        router_risks=[router_risk],
        recently_unstable=[],
        weak_links=[],
        low_batteries=[],
        stale_devices=[],
        recent_timeline=[],
        health_snapshot=HealthSnapshot(
            timestamp=ISO,
            overall_severity=Severity.incident,
            overall_health=DeviceHealthPrimary.unavailable,
            network_count=2,
            device_count=3,
            unavailable_count=1,
            incident_count=1,
            networks=[
                {"network_id": "home", "severity": "incident", "unavailable_count": 0},
                {"network_id": "office", "severity": "incident", "unavailable_count": 1},
            ],
        ),
    )
    return ScenarioData(
        id="isolation_3f",
        label="Isolation 3F",
        dashboard=dash,
        devices=[home_target, home_router, office_bad],
        networks=[home_net, office_net],
        incidents=incidents,
        router_risks=[router_risk],
    )


@dataclass
class _StubMock:
    data: ScenarioData
    _timeline: list = field(default_factory=list)

    def routers(self):
        from zigbeelens.services.mock_provider import MockProvider

        # Reuse MockProvider.routers logic against our fixture without registering a scenario.
        provider = MockProvider.__new__(MockProvider)
        provider.scenario_id = self.data.id
        provider._data = self.data
        return provider.routers()

    def timeline(self, network_id: str | None = None):
        if network_id is None:
            return list(self._timeline)
        return [e for e in self._timeline if e.network_id == network_id]


def _mock_report(scenario: ScenarioData, request: ReportRequest) -> object:
    mock = _StubMock(scenario)
    ctx = compose_mock_report_scope(
        mock,
        request,
        reference_now=NOW,
        include_timeline=False,
        reporting=ReportingConfig(max_recent_events=50),
    )
    config = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
            NetworkConfig(id="office", name="Office", base_topic="z2m-office"),
        ],
    )
    detail = project_report_detail(
        ctx,
        config=config,
        collector=PRODUCTION_COLLECTOR_LIST,
        request=request,
    )
    return _apply_report_compatibility_sections(detail)


def test_mock_home_device_isolates_office_router_and_finding():
    scenario = _isolation_scenario(with_home_watch_incident=False)
    detail = _mock_report(
        scenario,
        ReportRequest(
            scope=ReportScope.device,
            network_id="home",
            device=TARGET,
            format=ReportFormat.json,
            redaction=RedactionOptions(include_timeline=False, hash_ieee_addresses=False),
        ),
    )
    dumped = detail.model_dump_json()
    assert OFFICE_BAD not in dumped
    assert HOME_ROUTER not in dumped
    assert "OFFICE_DASHBOARD_FINDING_SENTINEL" not in dumped
    assert "HOME_ROUTER_RISK_SENTINEL" not in dumped
    assert detail.router_risks == []
    assert detail.health_snapshot.device_count == 1
    assert detail.networks[0].id == "home"
    assert detail.networks[0].device_count == 1
    assert detail.networks[0].active_incident_count == 0
    assert detail.networks[0].incident_state == Severity.healthy
    assert detail.collector["networks"] == [{"network_id": "home", "subscribed": True}]


def test_mock_home_network_no_active_avoids_office_finding():
    scenario = _isolation_scenario(with_home_watch_incident=False)
    detail = _mock_report(
        scenario,
        ReportRequest(
            scope=ReportScope.network,
            network_id="home",
            format=ReportFormat.json,
            redaction=RedactionOptions(include_timeline=False, hash_ieee_addresses=False),
        ),
    )
    assert "OFFICE_DASHBOARD_FINDING_SENTINEL" not in detail.diagnostic_conclusions[0].summary
    assert "office_dashboard_finding_SENTINEL" not in detail.diagnostic_conclusions[0].classification
    assert detail.networks[0].id == "home"
    assert all(n.id == "home" for n in detail.networks)
    assert OFFICE_BAD not in detail.model_dump_json()
    assert detail.health_snapshot.network_count == 1


def test_mock_watch_incident_severity_parity():
    scenario = _isolation_scenario(with_home_watch_incident=True)
    detail = _mock_report(
        scenario,
        ReportRequest(
            scope=ReportScope.device,
            network_id="home",
            device=TARGET,
            format=ReportFormat.json,
            redaction=RedactionOptions(include_timeline=False),
        ),
    )
    assert detail.summary.overall_state == Severity.watch
    assert detail.networks[0].incident_state == Severity.watch
    assert detail.health_snapshot.overall_severity == Severity.watch
    assert detail.active_incidents[0].severity == Severity.watch


def test_mock_unknown_count_from_device_health():
    target = device(
        "home",
        UNKNOWN,
        "UnknownMock",
        health=_unknown_health(),
    )
    home_net = network("home", "Home", "zigbee2mqtt", devices=[target])
    finding = conclusion(
        "all_clear",
        Severity.healthy,
        IncidentScope.network,
        Confidence.medium,
        "ok",
    )
    dash = DashboardPayload(
        generated_at=ISO,
        scenario="unknown_mock",
        overall_severity=Severity.healthy,
        current_finding=finding,
        active_incident_count=0,
        watching_incident_count=0,
        networks=[home_net],
        top_affected_devices=[],
        router_risks=[],
        recently_unstable=[],
        weak_links=[],
        low_batteries=[],
        stale_devices=[],
        recent_timeline=[],
        health_snapshot=HealthSnapshot(
            timestamp=ISO,
            overall_severity=Severity.healthy,
            overall_health=DeviceHealthPrimary.unknown,
            network_count=1,
            device_count=1,
            unavailable_count=0,
            incident_count=0,
            networks=[{"network_id": "home", "severity": "healthy", "unavailable_count": 0}],
        ),
    )
    scenario = ScenarioData(
        id="unknown_mock",
        label="Unknown mock",
        dashboard=dash,
        devices=[target],
        networks=[home_net],
    )
    detail = _mock_report(
        scenario,
        ReportRequest(
            scope=ReportScope.device,
            network_id="home",
            device=UNKNOWN,
            format=ReportFormat.json,
            redaction=RedactionOptions(include_timeline=False),
        ),
    )
    assert detail.health_snapshot.overall_health == DeviceHealthPrimary.unknown
    assert detail.health_snapshot.networks[0]["unknown_count"] == 1
    assert detail.health_snapshot.networks[0]["unavailable_count"] == 0


def test_live_mock_parity_counts_and_severity(tmp_path: Path):
    """Stable factual fields agree for an equivalent Home device watch case."""
    service, config, repo, coord = _service(tmp_path)
    _add_device(repo, "home", TARGET, "HomeTarget")
    _add_device(repo, "home", HOME_ROUTER, "HomeRouter", device_type="Router")
    _add_device(repo, "office", OFFICE_BAD, "OfficeBad", availability="offline")
    _add_incident(
        repo,
        incident_id="inc-home-watch",
        incident_type="low_battery_cluster",
        dedup_key="low_battery_cluster:home",
        network_ids=["home"],
        devices=[("home", TARGET)],
        title="HomeWatchBattery",
        severity="watch",
    )
    coord.evaluate_all(now=NOW)
    live = _report(
        service,
        config,
        ReportRequest(
            scope=ReportScope.device,
            network_id="home",
            device=TARGET,
            format=ReportFormat.json,
            redaction=RedactionOptions(include_timeline=False, hash_ieee_addresses=False),
        ),
    )
    mock = _mock_report(
        _isolation_scenario(with_home_watch_incident=True),
        ReportRequest(
            scope=ReportScope.device,
            network_id="home",
            device=TARGET,
            format=ReportFormat.json,
            redaction=RedactionOptions(include_timeline=False, hash_ieee_addresses=False),
        ),
    )
    assert live.health_snapshot.device_count == mock.health_snapshot.device_count == 1
    assert live.health_snapshot.network_count == mock.health_snapshot.network_count == 1
    assert live.networks[0].active_incident_count == mock.networks[0].active_incident_count == 1
    assert live.summary.overall_state == mock.summary.overall_state == Severity.watch
    assert live.networks[0].incident_state == mock.networks[0].incident_state == Severity.watch
    assert {r.ieee_address for r in live.router_risks} == {
        r.ieee_address for r in mock.router_risks
    }
    assert OFFICE_BAD not in live.model_dump_json()
    assert OFFICE_BAD not in mock.model_dump_json()
