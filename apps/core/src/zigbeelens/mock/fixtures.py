from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from zigbeelens.schemas import (
    Availability,
    BridgeState,
    Confidence,
    CoordinatorSummary,
    DashboardPayload,
    DeviceDetail,
    DeviceHealth,
    DeviceHealthPrimary,
    DeviceSummary,
    DeviceType,
    DiagnosticConclusion,
    EvidenceItem,
    HealthSnapshot,
    Incident,
    IncidentDeviceRef,
    IncidentScope,
    IncidentStatus,
    InterviewState,
    LimitationItem,
    NetworkSummary,
    PowerSource,
    ReportDetail,
    ReportRedactionStatus,
    RouterRisk,
    Severity,
    TimelineEvent,
)

NOW = datetime(2026, 6, 14, 12, 0, 0, tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def ago(**kwargs: float | int) -> str:
    return iso(NOW - timedelta(**kwargs))


def healthy_health() -> DeviceHealth:
    return DeviceHealth(
        primary=DeviceHealthPrimary.healthy,
        severity=Severity.healthy,
        confidence=Confidence.high,
        evidence=["Device is available and reporting normally"],
        limitations=["Topology route is not verified from MQTT data alone"],
    )


def device(
    network_id: str,
    ieee: str,
    name: str,
    *,
    device_type: DeviceType = DeviceType.EndDevice,
    power: PowerSource = PowerSource.Mains,
    availability: Availability = Availability.online,
    linkquality: int | None = 120,
    battery: int | None = None,
    last_seen: str | None = None,
    health: DeviceHealth | None = None,
    incident_affected: bool = False,
    sort_priority: int = 100,
    interview_state: InterviewState = InterviewState.successful,
) -> DeviceSummary:
    return DeviceSummary(
        network_id=network_id,
        ieee_address=ieee,
        friendly_name=name,
        device_type=device_type,
        power_source=power,
        availability=availability,
        last_seen=last_seen or ago(minutes=5),
        last_payload_at=ago(minutes=3),
        linkquality=linkquality,
        battery=battery,
        interview_state=interview_state,
        health=health or healthy_health(),
        incident_affected=incident_affected,
        sort_priority=sort_priority,
    )


def network(
    net_id: str,
    name: str,
    topic: str,
    *,
    bridge: BridgeState = BridgeState.online,
    devices: list[DeviceSummary],
    incident_state: Severity = Severity.healthy,
    active_incidents: int = 0,
    warnings: int = 0,
    errors: int = 0,
) -> NetworkSummary:
    routers = sum(1 for d in devices if d.device_type == DeviceType.Router)
    ends = sum(1 for d in devices if d.device_type == DeviceType.EndDevice)
    unavail = sum(1 for d in devices if d.availability == Availability.offline)
    unstable = sum(
        1 for d in devices if d.health.primary == DeviceHealthPrimary.recently_unstable
    )
    weak = sum(1 for d in devices if d.health.primary == DeviceHealthPrimary.weak_link)
    low_bat = sum(1 for d in devices if d.health.primary == DeviceHealthPrimary.low_battery)
    stale = sum(1 for d in devices if d.health.primary == DeviceHealthPrimary.stale_reporting)
    interview = sum(
        1 for d in devices if d.health.primary == DeviceHealthPrimary.interview_issue
    )
    health = DeviceHealth(
        primary=DeviceHealthPrimary.healthy if unavail == 0 else DeviceHealthPrimary.unavailable,
        severity=incident_state if incident_state != Severity.healthy else Severity.healthy,
        confidence=Confidence.high if bridge == BridgeState.online else Confidence.medium,
        evidence=[f"{unavail} unavailable devices on {name}"],
        limitations=["Per-device routing paths are not available from MQTT alone"],
    )
    if unavail == 0 and incident_state == Severity.healthy:
        health = healthy_health()

    return NetworkSummary(
        id=net_id,
        name=name,
        base_topic=topic,
        bridge_state=bridge,
        coordinator=CoordinatorSummary(
            ieee_address=f"0x00124b00{net_id[:4].ljust(4, '0')}",
            manufacturer="Texas Instruments",
            model="CC2652P",
            firmware="20240710",
            channel=15 if net_id == "home" else 20,
            pan_id=f"0x{net_id[:4].upper()}",
        ),
        device_count=len(devices),
        router_count=routers,
        end_device_count=ends,
        unavailable_count=unavail,
        recently_unstable_count=unstable,
        weak_link_count=weak,
        low_battery_count=low_bat,
        stale_count=stale,
        interview_issue_count=interview,
        incident_state=incident_state,
        active_incident_count=active_incidents,
        recent_bridge_warnings=warnings,
        recent_bridge_errors=errors,
        health=health,
    )


def conclusion(
    classification: str,
    severity: Severity,
    scope: IncidentScope,
    confidence: Confidence,
    summary: str,
    evidence: list[tuple[str, str]] | None = None,
    counter: list[tuple[str, str]] | None = None,
    limitations: list[tuple[str, str]] | None = None,
) -> DiagnosticConclusion:
    return DiagnosticConclusion(
        classification=classification,
        severity=severity,
        scope=scope,
        confidence=confidence,
        summary=summary,
        evidence=[
            EvidenceItem(id=f"ev-{i}", kind="observation", summary=s, detail=d)
            for i, (s, d) in enumerate(evidence or [])
        ],
        counter_evidence=[
            EvidenceItem(id=f"ce-{i}", kind="observation", summary=s, detail=d)
            for i, (s, d) in enumerate(counter or [])
        ],
        limitations=[
            LimitationItem(id=f"lim-{i}", summary=s, detail=d)
            for i, (s, d) in enumerate(limitations or [])
        ],
    )


def timeline_event(
    event_id: str,
    kind: str,
    title: str,
    summary: str,
    *,
    minutes_ago: float = 10,
    severity: Severity = Severity.watch,
    network_id: str | None = None,
    ieee: str | None = None,
    name: str | None = None,
    incident_id: str | None = None,
) -> TimelineEvent:
    return TimelineEvent(
        id=event_id,
        timestamp=ago(minutes=minutes_ago),
        kind=kind,
        severity=severity,
        network_id=network_id,
        ieee_address=ieee,
        friendly_name=name,
        title=title,
        summary=summary,
        incident_id=incident_id,
    )


@dataclass
class ScenarioData:
    id: str
    label: str
    dashboard: DashboardPayload
    devices: list[DeviceSummary] = field(default_factory=list)
    networks: list[NetworkSummary] = field(default_factory=list)
    incidents: list[Incident] = field(default_factory=list)
    router_risks: list[RouterRisk] = field(default_factory=list)
    timeline: list[TimelineEvent] = field(default_factory=list)


def _build_all_ok_single() -> ScenarioData:
    devices = [
        device("home", "0x00158d0001a1b2c3", "living_room_motion", power=PowerSource.Battery, battery=85),
        device("home", "0x00158d0002b3c4d5", "kitchen_switch", device_type=DeviceType.Router),
        device("home", "0x00158d0003c4d5e6", "hallway_light"),
        device("home", "0x00158d0004d5e6f7", "bedroom_sensor", power=PowerSource.Battery, battery=72),
    ]
    nets = [network("home", "Home", "zigbee2mqtt", devices=devices)]
    finding = conclusion(
        "all_clear",
        Severity.healthy,
        IncidentScope.network,
        Confidence.high,
        "All monitored devices on Home are available. No active incidents.",
        evidence=[("Bridge is online", "Last bridge state seen 30 seconds ago")],
        limitations=[("No topology map captured", "Router relationships are inferred only")],
    )
    dash = DashboardPayload(
        generated_at=iso(NOW),
        scenario="all_ok_single_network",
        overall_severity=Severity.healthy,
        current_finding=finding,
        active_incident_count=0,
        watching_incident_count=0,
        networks=nets,
        top_affected_devices=[],
        router_risks=[],
        recently_unstable=[],
        weak_links=[],
        low_batteries=[],
        stale_devices=[],
        recent_timeline=[
            timeline_event("tl-1", "bridge_state", "Bridge online", "Home bridge reported online", minutes_ago=30)
        ],
        health_snapshot=HealthSnapshot(
            timestamp=iso(NOW),
            overall_severity=Severity.healthy,
            overall_health=DeviceHealthPrimary.healthy,
            network_count=1,
            device_count=4,
            unavailable_count=0,
            incident_count=0,
            networks=[{"network_id": "home", "severity": "healthy", "unavailable_count": 0}],
        ),
    )
    return ScenarioData("all_ok_single_network", "All OK — single network", dash, devices, nets)


def _build_all_ok_multi() -> ScenarioData:
    home_devices = [
        device("home", "0x00158d0001a1b2c3", "living_room_motion", power=PowerSource.Battery, battery=85),
        device("home", "0x00158d0002b3c4d5", "kitchen_router", device_type=DeviceType.Router),
    ]
    home2_devices = [
        device("home2", "0x0017880101a1b2c3", "garage_door", power=PowerSource.Battery, battery=90),
        device("home2", "0x0017880102b3c4d5", "shed_router", device_type=DeviceType.Router),
        device("home2", "0x0017880103c4d5e6", "workshop_light"),
    ]
    nets = [
        network("home", "Home", "zigbee2mqtt", devices=home_devices),
        network("home2", "Home 2", "zigbee2mqtt-home2", devices=home2_devices),
    ]
    finding = conclusion(
        "all_clear",
        Severity.healthy,
        IncidentScope.multi_network,
        Confidence.high,
        "Both configured Zigbee2MQTT networks are healthy with no active incidents.",
    )
    dash = DashboardPayload(
        generated_at=iso(NOW),
        scenario="all_ok_multi_network",
        overall_severity=Severity.healthy,
        current_finding=finding,
        active_incident_count=0,
        watching_incident_count=0,
        networks=nets,
        top_affected_devices=[],
        router_risks=[],
        recently_unstable=[],
        weak_links=[],
        low_batteries=[],
        stale_devices=[],
        recent_timeline=[],
        health_snapshot=HealthSnapshot(
            timestamp=iso(NOW),
            overall_severity=Severity.healthy,
            overall_health=DeviceHealthPrimary.healthy,
            network_count=2,
            device_count=5,
            unavailable_count=0,
            incident_count=0,
            networks=[
                {"network_id": "home", "severity": "healthy", "unavailable_count": 0},
                {"network_id": "home2", "severity": "healthy", "unavailable_count": 0},
            ],
        ),
    )
    return ScenarioData(
        "all_ok_multi_network",
        "All OK — multi network",
        dash,
        home_devices + home2_devices,
        nets,
    )


def _build_single_device_unavailable() -> ScenarioData:
    bad_health = DeviceHealth(
        primary=DeviceHealthPrimary.unavailable,
        severity=Severity.incident,
        confidence=Confidence.high,
        evidence=["Availability reported offline"],
        limitations=["Cannot confirm physical power state"],
    )
    devices = [
        device("home", "0x00158d0001a1b2c3", "living_room_motion", power=PowerSource.Battery, battery=85),
        device(
            "home",
            "0x00158d0004d5e6f7",
            "bedroom_sensor",
            power=PowerSource.Battery,
            battery=15,
            availability=Availability.offline,
            health=bad_health,
            incident_affected=True,
            sort_priority=2,
        ),
        device("home", "0x00158d0002b3c4d5", "kitchen_router", device_type=DeviceType.Router),
    ]
    nets = [network("home", "Home", "zigbee2mqtt", devices=devices, incident_state=Severity.incident, active_incidents=1)]
    finding = conclusion(
        "single_device_unavailable",
        Severity.incident,
        IncidentScope.device,
        Confidence.high,
        "One device is unavailable on Home while the bridge remains online.",
        evidence=[
            ("bedroom_sensor went offline", "Availability changed 18 minutes ago"),
            ("Bridge stayed online", "No bridge outage in the incident window"),
        ],
        counter=[("No other devices changed state", "No correlated outage within 3 minutes")],
        limitations=[("Route through mesh is unknown", "MQTT does not prove which router was used")],
    )
    incident = Incident(
        id="inc-single-1",
        type="single_device_unavailable",
        status=IncidentStatus.open,
        severity=Severity.incident,
        scope=IncidentScope.device,
        confidence=Confidence.high,
        title="bedroom_sensor unavailable on Home",
        summary="One end device reported offline while the network bridge remained online.",
        interpretation="This looks isolated to this device. ZigbeeLens does not see wider network instability at the same time.",
        network_ids=["home"],
        affected_device_count=1,
        affected_devices=[
            IncidentDeviceRef(
                network_id="home",
                ieee_address="0x00158d0004d5e6f7",
                friendly_name="bedroom_sensor",
                health_primary=DeviceHealthPrimary.unavailable,
            )
        ],
        opened_at=ago(minutes=18),
        updated_at=ago(minutes=2),
        evidence=finding.evidence,
        counter_evidence=finding.counter_evidence,
        limitations=finding.limitations,
        timeline=[
            timeline_event(
                "tl-offline",
                "availability_changed",
                "bedroom_sensor offline",
                "Device availability changed to offline",
                minutes_ago=18,
                severity=Severity.incident,
                network_id="home",
                ieee="0x00158d0004d5e6f7",
                name="bedroom_sensor",
                incident_id="inc-single-1",
            )
        ],
        conclusion=finding,
    )
    dash = DashboardPayload(
        generated_at=iso(NOW),
        scenario="single_device_unavailable",
        overall_severity=Severity.incident,
        current_finding=finding,
        active_incident_count=1,
        watching_incident_count=0,
        networks=nets,
        top_affected_devices=[devices[1]],
        router_risks=[],
        recently_unstable=[],
        weak_links=[],
        low_batteries=[],
        stale_devices=[],
        recent_timeline=incident.timeline,
        health_snapshot=HealthSnapshot(
            timestamp=iso(NOW),
            overall_severity=Severity.incident,
            overall_health=DeviceHealthPrimary.unavailable,
            network_count=1,
            device_count=3,
            unavailable_count=1,
            incident_count=1,
            networks=[{"network_id": "home", "severity": "incident", "unavailable_count": 1}],
        ),
    )
    return ScenarioData(
        "single_device_unavailable",
        "Single device unavailable",
        dash,
        devices,
        nets,
        [incident],
        timeline=incident.timeline,
    )


def _build_four_devices_same_room() -> ScenarioData:
    affected = []
    ipees = [
        ("0x0017880101a1b2c3", "office_motion"),
        ("0x0017880102b3c4d5", "office_desk_lamp"),
        ("0x0017880103c4d5e6", "office_switch"),
        ("0x0017880104d5e6f7", "office_temp"),
    ]
    bad = DeviceHealth(
        primary=DeviceHealthPrimary.unavailable,
        severity=Severity.incident,
        confidence=Confidence.high,
        evidence=["Availability offline"],
    )
    for i, (ieee, name) in enumerate(ipees):
        affected.append(
            device(
                "home2",
                ieee,
                name,
                availability=Availability.offline,
                health=bad,
                incident_affected=True,
                sort_priority=i + 1,
                power=PowerSource.Battery if "motion" in name or "temp" in name else PowerSource.Mains,
                battery=60 if "motion" in name or "temp" in name else None,
            )
        )
    ok_devices = [
        device("home2", "0x0017880105e6f708", "shed_router", device_type=DeviceType.Router),
        device("home", "0x00158d0001a1b2c3", "living_room_motion", power=PowerSource.Battery, battery=88),
    ]
    home2_all = affected + [ok_devices[0]]
    nets = [
        network("home", "Home", "zigbee2mqtt", devices=[ok_devices[1]]),
        network(
            "home2",
            "Home 2",
            "zigbee2mqtt-home2",
            devices=home2_all,
            incident_state=Severity.incident,
            active_incidents=1,
            warnings=2,
        ),
    ]
    finding = conclusion(
        "possible_mesh_segment_issue",
        Severity.incident,
        IncidentScope.mesh_segment,
        Confidence.medium,
        "4 devices became unavailable on Home 2 within 2 minutes while the bridge stayed online.",
        evidence=[
            ("4 devices changed within 2 minutes", "office_motion, office_desk_lamp, office_switch, office_temp"),
            ("Bridge online on Home 2", "Bridge state remained online throughout"),
            ("Home network unaffected", "No devices on Home changed state"),
        ],
        limitations=[
            ("Room association is manual/inferred", "MQTT does not label rooms"),
            ("Cannot prove shared router", "Topology not captured"),
        ],
    )
    inc_devices = [
        IncidentDeviceRef(
            network_id="home2",
            ieee_address=d.ieee_address,
            friendly_name=d.friendly_name,
            health_primary=DeviceHealthPrimary.unavailable,
        )
        for d in affected
    ]
    incident = Incident(
        id="inc-mesh-1",
        type="correlated_device_unavailability",
        status=IncidentStatus.open,
        severity=Severity.incident,
        scope=IncidentScope.mesh_segment,
        confidence=Confidence.medium,
        title="4 devices unavailable on Home 2",
        summary="Multiple devices on Home 2 changed to offline within a short window.",
        interpretation="Multiple devices changed state around the same time. This may indicate a wider Zigbee network, local mesh segment, or router issue.",
        network_ids=["home2"],
        affected_device_count=4,
        affected_devices=inc_devices,
        opened_at=ago(minutes=12),
        updated_at=ago(minutes=1),
        evidence=finding.evidence,
        counter_evidence=[
            EvidenceItem(id="ce-0", kind="observation", summary="Home network is healthy"),
        ],
        limitations=finding.limitations,
        timeline=[
            timeline_event(
                f"tl-{i}",
                "availability_changed",
                f"{d.friendly_name} offline",
                "Device became unavailable",
                minutes_ago=12 - i * 0.3,
                severity=Severity.incident,
                network_id="home2",
                ieee=d.ieee_address,
                name=d.friendly_name,
                incident_id="inc-mesh-1",
            )
            for i, d in enumerate(affected)
        ],
        conclusion=finding,
    )
    dash = DashboardPayload(
        generated_at=iso(NOW),
        scenario="four_devices_same_room_unavailable",
        overall_severity=Severity.incident,
        current_finding=finding,
        active_incident_count=1,
        watching_incident_count=0,
        networks=nets,
        top_affected_devices=affected,
        router_risks=[],
        recently_unstable=[],
        weak_links=[],
        low_batteries=[],
        stale_devices=[],
        recent_timeline=incident.timeline + [
            timeline_event("tl-br", "bridge_log", "Bridge warning", "MQTT publish timeout for office_motion", minutes_ago=11, network_id="home2")
        ],
        health_snapshot=HealthSnapshot(
            timestamp=iso(NOW),
            overall_severity=Severity.incident,
            overall_health=DeviceHealthPrimary.unavailable,
            network_count=2,
            device_count=6,
            unavailable_count=4,
            incident_count=1,
            networks=[
                {"network_id": "home", "severity": "healthy", "unavailable_count": 0},
                {"network_id": "home2", "severity": "incident", "unavailable_count": 4},
            ],
        ),
    )
    return ScenarioData(
        "four_devices_same_room_unavailable",
        "Four devices same room unavailable",
        dash,
        affected + ok_devices,
        nets,
        [incident],
        timeline=dash.recent_timeline,
    )


def _build_bridge_offline() -> ScenarioData:
    devices = [
        device(
            "home",
            "0x00158d0001a1b2c3",
            "living_room_motion",
            availability=Availability.unknown,
            health=DeviceHealth(
                primary=DeviceHealthPrimary.unknown,
                severity=Severity.watch,
                confidence=Confidence.low,
                evidence=["No recent payloads"],
                limitations=["Bridge offline — device state may be stale"],
            ),
            sort_priority=50,
        ),
    ]
    nets = [
        network(
            "home",
            "Home",
            "zigbee2mqtt",
            bridge=BridgeState.offline,
            devices=devices,
            incident_state=Severity.critical,
            active_incidents=1,
            errors=3,
        )
    ]
    finding = conclusion(
        "bridge_offline",
        Severity.critical,
        IncidentScope.network,
        Confidence.high,
        "The Home Zigbee2MQTT bridge is offline. Device telemetry is not updating.",
        evidence=[("Bridge state offline", "Last online 45 minutes ago")],
        limitations=[("Device states may be stale", "Unavailable counts may under-report")],
    )
    incident = Incident(
        id="inc-bridge-1",
        type="bridge_offline",
        status=IncidentStatus.open,
        severity=Severity.critical,
        scope=IncidentScope.network,
        confidence=Confidence.high,
        title="Home bridge offline",
        summary="Zigbee2MQTT bridge stopped reporting on Home.",
        interpretation="The Zigbee2MQTT bridge for this network is offline. Device health cannot be reliably assessed until it returns.",
        network_ids=["home"],
        affected_device_count=1,
        affected_devices=[],
        opened_at=ago(minutes=45),
        updated_at=ago(minutes=1),
        evidence=finding.evidence,
        counter_evidence=[],
        limitations=finding.limitations,
        timeline=[
            timeline_event("tl-boff", "bridge_state", "Bridge offline", "Bridge state changed to offline", minutes_ago=45, severity=Severity.critical, network_id="home", incident_id="inc-bridge-1")
        ],
        conclusion=finding,
    )
    dash = DashboardPayload(
        generated_at=iso(NOW),
        scenario="bridge_offline",
        overall_severity=Severity.critical,
        current_finding=finding,
        active_incident_count=1,
        watching_incident_count=0,
        networks=nets,
        top_affected_devices=devices,
        router_risks=[],
        recently_unstable=[],
        weak_links=[],
        low_batteries=[],
        stale_devices=devices,
        recent_timeline=incident.timeline,
        health_snapshot=HealthSnapshot(
            timestamp=iso(NOW),
            overall_severity=Severity.critical,
            overall_health=DeviceHealthPrimary.unknown,
            network_count=1,
            device_count=1,
            unavailable_count=0,
            incident_count=1,
            networks=[{"network_id": "home", "severity": "critical", "unavailable_count": 0}],
        ),
    )
    return ScenarioData("bridge_offline", "Bridge offline", dash, devices, nets, [incident], timeline=incident.timeline)


def _build_one_network_incident_other_ok() -> ScenarioData:
    data = _build_four_devices_same_room()
    data.id = "one_network_incident_other_network_ok"
    data.label = "One network incident, other OK"
    data.dashboard.scenario = data.id
    data.dashboard.current_finding.summary = (
        "Home 2 has an active incident affecting 4 devices. Home remains healthy."
    )
    return data


def _build_router_risk() -> ScenarioData:
    router_health = DeviceHealth(
        primary=DeviceHealthPrimary.router_risk,
        severity=Severity.watch,
        confidence=Confidence.medium,
        evidence=["Router availability changed 3 times in 24h", "4 end devices offline nearby in time"],
        limitations=["Cannot prove routing path from MQTT"],
    )
    router = device(
        "home2",
        "0x0017880105e6f708",
        "office_router",
        device_type=DeviceType.Router,
        linkquality=35,
        health=router_health,
        sort_priority=4,
    )
    affected = [
        device(
            "home2",
            f"0x001788010{i}a1b2c3",
            f"office_device_{i}",
            availability=Availability.offline,
            health=DeviceHealth(primary=DeviceHealthPrimary.unavailable, severity=Severity.incident, confidence=Confidence.high, evidence=["Offline"]),
            incident_affected=True,
            sort_priority=i,
        )
        for i in range(1, 4)
    ]
    devices = [router] + affected
    risk = RouterRisk(
        network_id="home2",
        ieee_address=router.ieee_address,
        friendly_name=router.friendly_name,
        availability=router.availability,
        linkquality=35,
        last_seen=ago(minutes=8),
        possibly_dependent_devices=6,
        correlated_affected_devices=3,
        risk=conclusion(
            "router_risk_candidate",
            Severity.watch,
            IncidentScope.router_candidate,
            Confidence.medium,
            "office_router was unstable around the same time as several end devices.",
            evidence=[("Router linkquality low (35)", "Below weak link threshold")],
            limitations=[("Routing path not proven", "ZigbeeLens cannot confirm end devices route through this router from MQTT data alone")],
        ),
    )
    nets = [network("home2", "Home 2", "zigbee2mqtt-home2", devices=devices, incident_state=Severity.incident, active_incidents=1)]
    finding = risk.risk
    dash = DashboardPayload(
        generated_at=iso(NOW),
        scenario="router_risk_candidate",
        overall_severity=Severity.incident,
        current_finding=finding,
        active_incident_count=1,
        watching_incident_count=0,
        networks=nets,
        top_affected_devices=affected,
        router_risks=[risk],
        recently_unstable=[router],
        weak_links=[router],
        low_batteries=[],
        stale_devices=[],
        recent_timeline=[],
        health_snapshot=HealthSnapshot(
            timestamp=iso(NOW),
            overall_severity=Severity.incident,
            overall_health=DeviceHealthPrimary.router_risk,
            network_count=1,
            device_count=4,
            unavailable_count=3,
            incident_count=1,
            networks=[{"network_id": "home2", "severity": "incident", "unavailable_count": 3}],
        ),
    )
    return ScenarioData("router_risk_candidate", "Router risk candidate", dash, devices, nets, router_risks=[risk])


def _build_stale_battery() -> ScenarioData:
    stale = DeviceHealth(primary=DeviceHealthPrimary.stale_reporting, severity=Severity.watch, confidence=Confidence.medium, evidence=["No payload in 26 hours"])
    devices = [
        device("home", "0x00158d0001a1b2c3", "garden_sensor", power=PowerSource.Battery, battery=45, last_seen=ago(hours=26), health=stale, sort_priority=6),
    ]
    nets = [network("home", "Home", "zigbee2mqtt", devices=devices, incident_state=Severity.watch)]
    finding = conclusion("stale_reporting", Severity.watch, IncidentScope.device, Confidence.medium, "One battery device has stale reporting on Home.")
    dash = DashboardPayload(
        generated_at=iso(NOW),
        scenario="stale_battery_devices",
        overall_severity=Severity.watch,
        current_finding=finding,
        active_incident_count=0,
        watching_incident_count=1,
        networks=nets,
        top_affected_devices=[],
        router_risks=[],
        recently_unstable=[],
        weak_links=[],
        low_batteries=[],
        stale_devices=devices,
        recent_timeline=[],
        health_snapshot=HealthSnapshot(
            timestamp=iso(NOW),
            overall_severity=Severity.watch,
            overall_health=DeviceHealthPrimary.stale_reporting,
            network_count=1,
            device_count=1,
            unavailable_count=0,
            incident_count=0,
            networks=[{"network_id": "home", "severity": "watch", "unavailable_count": 0}],
        ),
    )
    return ScenarioData("stale_battery_devices", "Stale battery devices", dash, devices, nets)


def _build_low_battery_cluster() -> ScenarioData:
    low = DeviceHealth(primary=DeviceHealthPrimary.low_battery, severity=Severity.watch, confidence=Confidence.high, evidence=["Battery at 12%"])
    devices = [
        device("home", f"0x00158d000{i}a1b2c3", f"sensor_{i}", power=PowerSource.Battery, battery=10 + i * 2, health=low, sort_priority=7 + i)
        for i in range(1, 5)
    ]
    nets = [network("home", "Home", "zigbee2mqtt", devices=devices, incident_state=Severity.watch)]
    finding = conclusion("low_battery_cluster", Severity.watch, IncidentScope.network, Confidence.high, "4 battery devices report low battery on Home.")
    dash = DashboardPayload(
        generated_at=iso(NOW),
        scenario="low_battery_cluster",
        overall_severity=Severity.watch,
        current_finding=finding,
        active_incident_count=0,
        watching_incident_count=1,
        networks=nets,
        top_affected_devices=[],
        router_risks=[],
        recently_unstable=[],
        weak_links=[],
        low_batteries=devices,
        stale_devices=[],
        recent_timeline=[],
        health_snapshot=HealthSnapshot(
            timestamp=iso(NOW),
            overall_severity=Severity.watch,
            overall_health=DeviceHealthPrimary.low_battery,
            network_count=1,
            device_count=4,
            unavailable_count=0,
            incident_count=0,
            networks=[{"network_id": "home", "severity": "watch", "unavailable_count": 0}],
        ),
    )
    return ScenarioData("low_battery_cluster", "Low battery cluster", dash, devices, nets)


def _build_interview_failures() -> ScenarioData:
    bad = DeviceHealth(primary=DeviceHealthPrimary.interview_issue, severity=Severity.watch, confidence=Confidence.high, evidence=["Interview failed"])
    devices = [
        device("home", "0x00158d0009a1b2c3", "new_plug", interview_state=InterviewState.failed, health=bad, sort_priority=8),
    ]
    nets = [network("home", "Home", "zigbee2mqtt", devices=devices, incident_state=Severity.watch)]
    finding = conclusion("interview_failure", Severity.watch, IncidentScope.device, Confidence.high, "One device failed interview on Home.")
    dash = DashboardPayload(
        generated_at=iso(NOW),
        scenario="interview_failures",
        overall_severity=Severity.watch,
        current_finding=finding,
        active_incident_count=0,
        watching_incident_count=1,
        networks=nets,
        top_affected_devices=devices,
        router_risks=[],
        recently_unstable=[],
        weak_links=[],
        low_batteries=[],
        stale_devices=[],
        recent_timeline=[
            timeline_event("tl-int", "device_interview_failed", "Interview failed", "new_plug interview did not complete", minutes_ago=60, network_id="home", ieee="0x00158d0009a1b2c3", name="new_plug")
        ],
        health_snapshot=HealthSnapshot(
            timestamp=iso(NOW),
            overall_severity=Severity.watch,
            overall_health=DeviceHealthPrimary.interview_issue,
            network_count=1,
            device_count=1,
            unavailable_count=0,
            incident_count=0,
            networks=[{"network_id": "home", "severity": "watch", "unavailable_count": 0}],
        ),
    )
    return ScenarioData("interview_failures", "Interview failures", dash, devices, nets, timeline=dash.recent_timeline)


def _build_unknown_insufficient() -> ScenarioData:
    devices = [
        device(
            "home",
            "0x00158d0001a1b2c3",
            " mystery_device",
            availability=Availability.unknown,
            linkquality=None,
            health=DeviceHealth(primary=DeviceHealthPrimary.unknown, severity=Severity.watch, confidence=Confidence.low, evidence=[], limitations=["Insufficient telemetry"]),
            sort_priority=90,
        ),
    ]
    nets = [network("home", "Home", "zigbee2mqtt", devices=devices, incident_state=Severity.watch)]
    finding = conclusion(
        "unknown_insufficient_data",
        Severity.watch,
        IncidentScope.unknown,
        Confidence.low,
        "There is not enough recent history to classify device health confidently.",
        limitations=[("Limited MQTT payloads", "Availability topic may not be enabled")],
    )
    dash = DashboardPayload(
        generated_at=iso(NOW),
        scenario="unknown_insufficient_data",
        overall_severity=Severity.watch,
        current_finding=finding,
        active_incident_count=0,
        watching_incident_count=0,
        networks=nets,
        top_affected_devices=devices,
        router_risks=[],
        recently_unstable=[],
        weak_links=[],
        low_batteries=[],
        stale_devices=[],
        recent_timeline=[],
        health_snapshot=HealthSnapshot(
            timestamp=iso(NOW),
            overall_severity=Severity.watch,
            overall_health=DeviceHealthPrimary.unknown,
            network_count=1,
            device_count=1,
            unavailable_count=0,
            incident_count=0,
            networks=[{"network_id": "home", "severity": "watch", "unavailable_count": 0}],
        ),
    )
    return ScenarioData("unknown_insufficient_data", "Unknown / insufficient data", dash, devices, nets)


def _build_multi_unstable() -> ScenarioData:
    unstable = DeviceHealth(primary=DeviceHealthPrimary.recently_unstable, severity=Severity.incident, confidence=Confidence.medium, evidence=["4 availability changes in 24h"])
    home_d = [
        device("home", f"0x00158d000{i}a1b2c3", f"home_flap_{i}", health=unstable, sort_priority=i)
        for i in range(1, 4)
    ]
    home2_d = [
        device("home2", f"0x001788010{i}a1b2c3", f"home2_flap_{i}", health=unstable, sort_priority=i)
        for i in range(1, 3)
    ]
    nets = [
        network("home", "Home", "zigbee2mqtt", devices=home_d, incident_state=Severity.incident, active_incidents=1),
        network("home2", "Home 2", "zigbee2mqtt-home2", devices=home2_d, incident_state=Severity.incident, active_incidents=1),
    ]
    finding = conclusion(
        "multi_network_instability",
        Severity.incident,
        IncidentScope.multi_network,
        Confidence.medium,
        "Similar instability patterns detected on both Home and Home 2 within the same window.",
    )
    dash = DashboardPayload(
        generated_at=iso(NOW),
        scenario="multiple_networks_unstable",
        overall_severity=Severity.incident,
        current_finding=finding,
        active_incident_count=2,
        watching_incident_count=0,
        networks=nets,
        top_affected_devices=home_d + home2_d,
        router_risks=[],
        recently_unstable=home_d + home2_d,
        weak_links=[],
        low_batteries=[],
        stale_devices=[],
        recent_timeline=[],
        health_snapshot=HealthSnapshot(
            timestamp=iso(NOW),
            overall_severity=Severity.incident,
            overall_health=DeviceHealthPrimary.recently_unstable,
            network_count=2,
            device_count=5,
            unavailable_count=0,
            incident_count=2,
            networks=[
                {"network_id": "home", "severity": "incident", "unavailable_count": 0},
                {"network_id": "home2", "severity": "incident", "unavailable_count": 0},
            ],
        ),
    )
    return ScenarioData("multiple_networks_unstable", "Multiple networks unstable", dash, home_d + home2_d, nets)


def _build_weak_link() -> ScenarioData:
    weak = DeviceHealth(primary=DeviceHealthPrimary.weak_link, severity=Severity.watch, confidence=Confidence.high, evidence=["Linkquality 28"])
    devices = [
        device("home", "0x00158d0001a1b2c3", "far_garage_sensor", power=PowerSource.Battery, linkquality=28, health=weak, sort_priority=7),
        device("home", "0x00158d0002b3c4d5", "attic_motion", power=PowerSource.Battery, linkquality=32, health=weak, sort_priority=8),
    ]
    nets = [network("home", "Home", "zigbee2mqtt", devices=devices, incident_state=Severity.watch)]
    finding = conclusion("weak_link_devices", Severity.watch, IncidentScope.network, Confidence.high, "2 devices report weak link quality on Home.")
    dash = DashboardPayload(
        generated_at=iso(NOW),
        scenario="weak_link_devices",
        overall_severity=Severity.watch,
        current_finding=finding,
        active_incident_count=0,
        watching_incident_count=1,
        networks=nets,
        top_affected_devices=[],
        router_risks=[],
        recently_unstable=[],
        weak_links=devices,
        low_batteries=[],
        stale_devices=[],
        recent_timeline=[],
        health_snapshot=HealthSnapshot(
            timestamp=iso(NOW),
            overall_severity=Severity.watch,
            overall_health=DeviceHealthPrimary.weak_link,
            network_count=1,
            device_count=2,
            unavailable_count=0,
            incident_count=0,
            networks=[{"network_id": "home", "severity": "watch", "unavailable_count": 0}],
        ),
    )
    return ScenarioData("weak_link_devices", "Weak link devices", dash, devices, nets)


def _build_stale_cluster() -> ScenarioData:
    stale = DeviceHealth(primary=DeviceHealthPrimary.stale_reporting, severity=Severity.watch, confidence=Confidence.medium, evidence=["No payload >24h"])
    devices = [
        device("home2", f"0x001788010{i}a1b2c3", f"stale_{i}", power=PowerSource.Battery, last_seen=ago(hours=30 + i), health=stale, sort_priority=6 + i)
        for i in range(1, 4)
    ]
    nets = [network("home2", "Home 2", "zigbee2mqtt-home2", devices=devices, incident_state=Severity.watch)]
    finding = conclusion("stale_reporting_cluster", Severity.watch, IncidentScope.network, Confidence.medium, "3 devices on Home 2 have stale reporting.")
    dash = DashboardPayload(
        generated_at=iso(NOW),
        scenario="stale_reporting_cluster",
        overall_severity=Severity.watch,
        current_finding=finding,
        active_incident_count=0,
        watching_incident_count=1,
        networks=nets,
        top_affected_devices=[],
        router_risks=[],
        recently_unstable=[],
        weak_links=[],
        low_batteries=[],
        stale_devices=devices,
        recent_timeline=[],
        health_snapshot=HealthSnapshot(
            timestamp=iso(NOW),
            overall_severity=Severity.watch,
            overall_health=DeviceHealthPrimary.stale_reporting,
            network_count=1,
            device_count=3,
            unavailable_count=0,
            incident_count=0,
            networks=[{"network_id": "home2", "severity": "watch", "unavailable_count": 0}],
        ),
    )
    return ScenarioData("stale_reporting_cluster", "Stale reporting cluster", dash, devices, nets)


BUILDERS: dict[str, Callable[[], ScenarioData]] = {
    "all_ok_single_network": _build_all_ok_single,
    "all_ok_multi_network": _build_all_ok_multi,
    "single_device_unavailable": _build_single_device_unavailable,
    "four_devices_same_room_unavailable": _build_four_devices_same_room,
    "bridge_offline": _build_bridge_offline,
    "one_network_incident_other_network_ok": _build_one_network_incident_other_ok,
    "router_risk_candidate": _build_router_risk,
    "stale_battery_devices": _build_stale_battery,
    "low_battery_cluster": _build_low_battery_cluster,
    "interview_failures": _build_interview_failures,
    "unknown_insufficient_data": _build_unknown_insufficient,
    "multiple_networks_unstable": _build_multi_unstable,
    "weak_link_devices": _build_weak_link,
    "stale_reporting_cluster": _build_stale_cluster,
}

DEFAULT_SCENARIO = "four_devices_same_room_unavailable"


def get_scenario(scenario_id: str | None = None) -> ScenarioData:
    sid = scenario_id or DEFAULT_SCENARIO
    if sid not in BUILDERS:
        sid = DEFAULT_SCENARIO
    return BUILDERS[sid]()


def list_scenarios() -> list[dict[str, str]]:
    return [{"id": sid, "label": BUILDERS[sid]().label} for sid in BUILDERS]


def device_detail_from_summary(summary: DeviceSummary, scenario: ScenarioData) -> DeviceDetail:
    inc = next((i for i in scenario.incidents if any(
        d.ieee_address == summary.ieee_address and d.network_id == summary.network_id
        for d in i.affected_devices
    )), None)
    diag = inc.conclusion if inc else conclusion(
        summary.health.primary.value,
        summary.health.severity,
        IncidentScope.device,
        summary.health.confidence,
        f"{summary.friendly_name} is classified as {summary.health.primary.value}.",
        evidence=[(e, "") for e in summary.health.evidence],
        limitations=[(lim, "") for lim in summary.health.limitations],
    )
    return DeviceDetail(
        **summary.model_dump(),
        manufacturer="IKEA" if "office" in summary.friendly_name else "Aqara",
        model="TRADFRI" if "lamp" in summary.friendly_name else "SNZB-04",
        recent_availability_changes=[],
        recent_events=[e for e in scenario.timeline if e.ieee_address == summary.ieee_address],
        recent_bridge_logs=[],
        diagnostic=diag,
        trends=[],
    )


def build_report_preview(scenario: ScenarioData) -> ReportDetail:
    return ReportDetail(
        id="report-preview",
        generated_at=iso(NOW),
        version="0.1.0",
        redaction=ReportRedactionStatus(applied=True, mqtt_credentials=True),
        config_summary={
            "networks": [{"id": n.id, "name": n.name, "base_topic": n.base_topic} for n in scenario.networks],
            "retention_days": 30,
        },
        networks=scenario.networks,
        devices=scenario.devices,
        router_risks=scenario.router_risks or scenario.dashboard.router_risks,
        incidents=scenario.incidents,
        health_snapshot=scenario.dashboard.health_snapshot,
        diagnostic_conclusions=[scenario.dashboard.current_finding],
        markdown_summary=_markdown_summary(scenario),
    )


def _markdown_summary(scenario: ScenarioData) -> str:
    d = scenario.dashboard
    lines = [
        "# ZigbeeLens Support Report",
        "",
        f"Generated: {d.generated_at}",
        f"Scenario: {scenario.id}",
        "",
        "## Current finding",
        d.current_finding.summary,
        "",
        f"**Scope:** {d.current_finding.scope.value}",
        f"**Confidence:** {d.current_finding.confidence.value}",
        "",
        "## Networks",
    ]
    for n in scenario.networks:
        lines.append(f"- **{n.name}**: bridge {n.bridge_state.value}, {n.unavailable_count} unavailable")
    lines.extend(["", "## Evidence", ""])
    for ev in d.current_finding.evidence:
        lines.append(f"- {ev.summary}")
    lines.extend(["", "## Limitations", ""])
    for lim in d.current_finding.limitations:
        lines.append(f"- {lim.summary}")
    return "\n".join(lines)
