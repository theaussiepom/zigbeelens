"""Build API payloads from persisted SQLite state."""

from __future__ import annotations

from zigbeelens.config.models import AppConfig
from zigbeelens.diagnostics.incidents.service import IncidentDiagnosticService
from zigbeelens.diagnostics.models import HealthFlag
from zigbeelens.diagnostics.service import (
    HealthDiagnosticService,
    health_result_to_device_health,
    health_result_to_diagnostic,
    health_result_to_router_risk,
    sort_priority,
)
from zigbeelens.presentation.lens_buckets import enrich_device_summary, lens_presentation_for_health
from zigbeelens.schemas import (
    Availability,
    AvailabilityChange,
    BridgeState,
    Confidence,
    DashboardPayload,
    DeviceDetail,
    DeviceHealthPrimary,
    DeviceSummary,
    DeviceTrendPoint,
    DeviceType,
    DiagnosticConclusion,
    EvidenceItem,
    Incident,
    IncidentDeviceRef,
    IncidentScope,
    IncidentStatus,
    InterviewState,
    LimitationItem,
    PowerSource,
    RouterRisk,
    Severity,
    TimelineEvent,
)
from zigbeelens.services.empty_state import build_empty_dashboard, empty_finding
from zigbeelens.services.live_dashboard import (
    build_health_snapshot,
    build_network_summary,
    live_finding,
)
from zigbeelens.storage.repository import DeviceRow, Repository, utc_now_iso
from zigbeelens.util.json_helpers import parse_json_list


def _parse_json_list(raw: str | None) -> list:
    return parse_json_list(raw)


def _device_has_flag(health, flag: DeviceHealthPrimary) -> bool:
    return flag in (health.flags or [])


def _evidence_items(raw_list: list, prefix: str = "ev") -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for i, item in enumerate(raw_list):
        if isinstance(item, str):
            summary = item
        elif isinstance(item, dict):
            summary = item.get("summary", str(item))
        else:
            summary = str(item)
        items.append(EvidenceItem(id=f"{prefix}-{i}", kind="stored", summary=summary))
    return items


def _limitation_items(raw_list: list) -> list[LimitationItem]:
    items: list[LimitationItem] = []
    for i, item in enumerate(raw_list):
        summary = item.get("summary", str(item)) if isinstance(item, dict) else str(item)
        items.append(LimitationItem(id=f"lim-{i}", summary=summary))
    return items


class PayloadBuilder:
    def __init__(
        self,
        config: AppConfig,
        repo: Repository,
        health: HealthDiagnosticService | None = None,
        incidents: IncidentDiagnosticService | None = None,
    ) -> None:
        self.config = config
        self.repo = repo
        self.health = health
        self._incident_service = incidents

    def _ensure_health(self) -> HealthDiagnosticService | None:
        if self.health is None:
            return None
        if not self.health.all_device_health() and self.repo.has_collected_data():
            self.health.recalculate_all()
        return self.health

    def dashboard(self) -> DashboardPayload:
        if not self.repo.has_collected_data():
            return build_empty_dashboard(self.config, self.repo.list_networks())

        health = self._ensure_health()
        if not health:
            health = self._fallback_health()
        devices = self.devices()
        finding = live_finding(self.repo, self.config, health, self._incident_service)

        open_count, watching_count = (
            self._incident_service.count_by_status() if self._incident_service else (0, 0)
        )

        def _is_affected(d: DeviceSummary) -> bool:
            return d.health.primary not in {
                DeviceHealthPrimary.healthy,
                DeviceHealthPrimary.unknown,
            }

        top_affected = sorted(
            [d for d in devices if _is_affected(d)],
            key=lambda d: d.sort_priority,
        )[:10]

        return DashboardPayload(
            generated_at=utc_now_iso(),
            scenario=None,
            overall_severity=finding.severity,
            current_finding=finding,
            active_incident_count=open_count,
            watching_incident_count=watching_count,
            networks=self.networks(),
            top_affected_devices=top_affected,
            router_risks=self.routers(),
            recently_unstable=[
                d
                for d in devices
                if _device_has_flag(d.health, DeviceHealthPrimary.recently_unstable)
            ],
            weak_links=[
                d for d in devices if _device_has_flag(d.health, DeviceHealthPrimary.weak_link)
            ],
            low_batteries=[
                d for d in devices if _device_has_flag(d.health, DeviceHealthPrimary.low_battery)
            ],
            stale_devices=[
                d
                for d in devices
                if _device_has_flag(d.health, DeviceHealthPrimary.stale_reporting)
            ],
            recent_timeline=self.timeline()[:12],
            health_snapshot=build_health_snapshot(self.repo, health, self._incident_service),
        )

    def _fallback_health(self) -> HealthDiagnosticService:
        from zigbeelens.diagnostics.service import HealthDiagnosticService

        svc = HealthDiagnosticService(self.config, self.repo)
        svc.recalculate_all()
        return svc

    def networks(self):
        health = self._ensure_health()
        if not health:
            health = self._fallback_health()
        return [
            build_network_summary(self.repo, row, health, self._incident_service)
            for row in self.repo.list_networks()
        ]

    def network(self, network_id: str):
        row = self.repo.get_network(network_id)
        if not row:
            return None
        health = self._ensure_health() or self._fallback_health()
        return build_network_summary(self.repo, row, health, self._incident_service)

    def devices(self, network_id: str | None = None) -> list[DeviceSummary]:
        rows = self.repo.list_devices(network_id)
        summaries = [self._device_summary(row) for row in rows]
        return sorted(summaries, key=lambda d: d.sort_priority)

    def device_detail(self, network_id: str, ieee_address: str) -> DeviceDetail | None:
        row = self.repo.get_device(network_id, ieee_address)
        if not row:
            return None
        summary = self._device_summary(row)
        health_svc = self._ensure_health()
        result = (
            health_svc.get_device_health(network_id, ieee_address) if health_svc else None
        )
        finding = (
            health_result_to_diagnostic(result, row.friendly_name)
            if result
            else DiagnosticConclusion(
                classification=summary.health.primary.value,
                severity=summary.health.severity,
                scope=IncidentScope.device,
                confidence=summary.health.confidence,
                summary=summary.health.evidence[0] if summary.health.evidence else "",
                evidence=[
                    EvidenceItem(id=f"ev-{i}", kind="health", summary=e)
                    for i, e in enumerate(summary.health.evidence)
                ],
                limitations=[
                    LimitationItem(id=f"lim-{i}", summary=lim)
                    for i, lim in enumerate(summary.health.limitations)
                ],
            )
        )

        related_ids = self.repo.list_incidents_for_device(network_id, ieee_address)
        if related_ids and self._incident_service:
            top = self.repo.get_incident(related_ids[0])
            if top:
                finding = DiagnosticConclusion(
                    classification=top["incident_type"],
                    severity=Severity(top["severity"]),
                    scope=IncidentScope(top["scope"]),
                    confidence=Confidence(top["confidence"]),
                    summary=top["explanation"],
                    evidence=_evidence_items(_parse_json_list(top.get("evidence_json"))),
                    counter_evidence=_evidence_items(
                        _parse_json_list(top.get("counter_evidence_json")), prefix="ce"
                    ),
                    limitations=_limitation_items(_parse_json_list(top.get("limitations_json"))),
                )

        availability_changes = [
            AvailabilityChange(
                timestamp=ch["changed_at"],
                **{"from": Availability(ch["from_state"]) if ch["from_state"] in Availability.__members__ else Availability.unknown},
                to=Availability(ch["to_state"]) if ch["to_state"] in Availability.__members__ else Availability.unknown,
            )
            for ch in self.repo.availability.list_availability_changes(network_id, ieee_address)
        ]

        samples = self.repo.metrics.list_metric_samples(network_id, ieee_address, limit=30)
        trends: list[DeviceTrendPoint] = []
        for sample in reversed(samples):
            point = DeviceTrendPoint(timestamp=sample["sampled_at"])
            if sample["metric_name"] == "linkquality":
                point.linkquality = int(sample["metric_value"])
            elif sample["metric_name"] == "battery":
                point.battery = int(sample["metric_value"])
            trends.append(point)

        return DeviceDetail(
            **summary.model_dump(),
            recent_availability_changes=availability_changes,
            recent_events=[
                TimelineEvent(
                    id=e["id"],
                    timestamp=e["occurred_at"],
                    kind=e["event_type"],
                    severity=Severity(e["severity"]),
                    network_id=e.get("network_id"),
                    ieee_address=e.get("ieee_address"),
                    title=e["title"],
                    summary=e["summary"],
                )
                for e in self.repo.list_events(network_id, limit=20)
                if e.get("ieee_address") == ieee_address
            ],
            recent_bridge_logs=[],
            diagnostic=finding,
            trends=trends,
        )

    def routers(self) -> list[RouterRisk]:
        health = self._ensure_health() or self._fallback_health()
        items: list[RouterRisk] = []
        for row in self.repo.list_devices():
            if row.device_type != "Router":
                continue
            result = health.get_device_health(row.network_id, row.ieee_address)
            if result is None or HealthFlag.router_risk not in result.flags:
                continue
            risk = health_result_to_router_risk(row, result, self.repo)
            if self._incident_service:
                related = self.repo.list_incidents_for_device(row.network_id, row.ieee_address)
                risk.correlated_affected_devices = len(related)
            items.append(risk)
        return sorted(items, key=lambda r: r.risk.severity.value)

    def incidents(self) -> list[Incident]:
        return [
            inc
            for row in self.repo.list_incidents()
            if (inc := self._incident_from_row(row)) is not None
        ]

    def incident(self, incident_id: str) -> Incident | None:
        row = self.repo.get_incident(incident_id)
        return self._incident_from_row(row) if row else None

    def timeline(self, network_id: str | None = None) -> list[TimelineEvent]:
        events: list[TimelineEvent] = []
        for row in self.repo.list_events(network_id):
            events.append(
                TimelineEvent(
                    id=row["id"],
                    timestamp=row["occurred_at"],
                    kind=row["event_type"],
                    severity=Severity(row["severity"]),
                    network_id=row.get("network_id"),
                    ieee_address=row.get("ieee_address"),
                    friendly_name=None,
                    title=row["title"],
                    summary=row["summary"],
                    incident_id=row.get("incident_id"),
                )
            )
        return events

    def _device_summary(self, row: DeviceRow) -> DeviceSummary:
        health_svc = self._ensure_health()
        result = (
            health_svc.get_device_health(row.network_id, row.ieee_address)
            if health_svc
            else None
        )
        if result is None and health_svc:
            result = health_svc.recalculate_device(row.network_id, row.ieee_address)
        device_health = health_result_to_device_health(result) if result else None

        if device_health is None:
            from zigbeelens.diagnostics.device_health import classify_device
            from zigbeelens.diagnostics.models import DeviceHealthContext

            ctx = DeviceHealthContext(
                network_id=row.network_id,
                ieee_address=row.ieee_address,
                friendly_name=row.friendly_name,
                device_type=row.device_type,
                power_source=row.power_source,
                interview_state=row.interview_state,
                availability=row.availability,
                last_seen=row.last_seen,
                last_payload_at=row.last_payload_at,
                linkquality=row.linkquality,
                battery=row.battery,
            )
            device_health = health_result_to_device_health(
                classify_device(ctx, self.config.diagnostics)
            )

        availability = (
            Availability(row.availability)
            if row.availability in Availability.__members__
            else Availability.unknown
        )
        affected_keys = (
            self._incident_service.incident_affected_keys() if self._incident_service else set()
        )
        incident_affected = (row.network_id, row.ieee_address) in affected_keys
        network_row = self.repo.get_network(row.network_id)
        bridge_state = None
        if network_row is not None and network_row.bridge_state in BridgeState.__members__:
            bridge_state = BridgeState(network_row.bridge_state)
        summary = DeviceSummary(
            network_id=row.network_id,
            ieee_address=row.ieee_address,
            friendly_name=row.friendly_name,
            device_type=DeviceType(row.device_type)
            if row.device_type in DeviceType.__members__
            else DeviceType.Unknown,
            power_source=PowerSource(row.power_source)
            if row.power_source in PowerSource.__members__
            else PowerSource.Unknown,
            availability=availability,
            last_seen=row.last_seen,
            last_payload_at=row.last_payload_at,
            linkquality=row.linkquality,
            battery=row.battery,
            manufacturer=row.manufacturer,
            model=row.model,
            interview_state=InterviewState(row.interview_state)
            if row.interview_state in InterviewState.__members__
            else InterviewState.unknown,
            health=device_health,
            incident_affected=incident_affected,
            sort_priority=sort_priority(result) if result else 100,
        )
        return enrich_device_summary(summary, bridge_state=bridge_state)

    def _incident_from_row(self, row: dict) -> Incident | None:
        if not row:
            return None
        refs = self.repo.list_incident_devices(row["id"])
        affected = []
        for ref in refs:
            dev = self.repo.get_device(ref["network_id"], ref["ieee_address"])
            health_primary = DeviceHealthPrimary.unknown
            device_health = None
            if self.health:
                hr = self.health.get_device_health(ref["network_id"], ref["ieee_address"])
                if hr:
                    health_primary = DeviceHealthPrimary(hr.primary.value)
                    device_health = health_result_to_device_health(hr)
            availability = Availability.unknown
            if dev:
                availability = (
                    Availability(dev.availability)
                    if dev.availability in Availability.__members__
                    else Availability.unknown
                )
            presentation = (
                lens_presentation_for_health(
                    device_health,
                    availability=availability,
                    incident_affected=True,
                )
                if device_health
                else {}
            )
            friendly = dev.friendly_name if dev else ref["ieee_address"]
            bucket = presentation.get("lens_bucket", "unknown")
            bucket_reason = presentation.get("lens_bucket_reason", "")
            affected.append(
                IncidentDeviceRef(
                    network_id=ref["network_id"],
                    ieee_address=ref["ieee_address"],
                    friendly_name=friendly,
                    health_primary=health_primary,
                    name=friendly,
                    classification=str(bucket),
                    reason=bucket_reason or str(presentation.get("lens_bucket_label", "")),
                    **presentation,
                )
            )
        evidence = _evidence_items(_parse_json_list(row["evidence_json"]))
        counter = _evidence_items(_parse_json_list(row["counter_evidence_json"]), prefix="ce")
        limitations = _limitation_items(_parse_json_list(row["limitations_json"]))
        conclusion = DiagnosticConclusion(
            classification=row["incident_type"],
            severity=Severity(row["severity"]),
            scope=IncidentScope(row["scope"]),
            confidence=Confidence(row["confidence"]),
            summary=row["summary"],
            evidence=evidence,
            counter_evidence=counter,
            limitations=limitations,
        )
        timeline = [
            TimelineEvent(
                id=e["id"],
                timestamp=e["occurred_at"],
                kind=e["event_type"],
                severity=Severity(e["severity"]),
                network_id=e.get("network_id"),
                ieee_address=e.get("ieee_address"),
                title=e["title"],
                summary=e["summary"],
                incident_id=e.get("incident_id"),
            )
            for e in self.repo.list_events(limit=100)
            if e.get("incident_id") == row["id"]
        ]
        return Incident(
            id=row["id"],
            type=row["incident_type"],
            status=IncidentStatus(row["lifecycle_state"]),
            severity=Severity(row["severity"]),
            scope=IncidentScope(row["scope"]),
            confidence=Confidence(row["confidence"]),
            title=row["title"],
            summary=row["summary"],
            interpretation=row["explanation"],
            network_ids=sorted({r["network_id"] for r in refs}),
            affected_device_count=len(affected),
            affected_devices=affected,
            opened_at=row["opened_at"],
            updated_at=row["updated_at"],
            resolved_at=row.get("resolved_at"),
            evidence=evidence,
            counter_evidence=counter,
            limitations=limitations,
            timeline=timeline,
            conclusion=conclusion,
        )

    def report_source_dashboard(self):
        return self.dashboard()

    def empty_report_finding(self) -> DiagnosticConclusion:
        return empty_finding()
