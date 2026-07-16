"""Build API payloads from persisted SQLite state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Protocol

from zigbeelens.config.models import AppConfig
from zigbeelens.diagnostics.incidents.service import (
    ActiveIncidentReadContext,
    IncidentDiagnosticService,
)
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
    DeviceDecisionBadge,
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
from zigbeelens.services.dashboard_shared_availability import (
    compose_dashboard_shared_availability_events,
)
from zigbeelens.services.dashboard_model_patterns import compose_dashboard_model_patterns
from zigbeelens.services.dashboard_investigation_priorities import (
    compose_dashboard_investigation_priorities,
)
from zigbeelens.services.dashboard_coverage_warnings import compose_dashboard_coverage_warnings
from zigbeelens.services.device_decision_badge import (
    device_decision_badge_for_device,
    device_decision_badges_for_devices,
)
from zigbeelens.services.empty_state import build_empty_dashboard, empty_finding
from zigbeelens.services.live_dashboard import (
    build_health_snapshot,
    build_network_summary,
    live_finding,
)
from zigbeelens.storage.repository import DeviceRow, NetworkRow, Repository, utc_now_iso
from zigbeelens.util.json_helpers import parse_json_list


class EvaluationAccess(Protocol):
    def evaluate_all(self, *, now: datetime | None = None) -> object: ...

    def evaluate_network(
        self,
        network_id: str,
        *,
        now: datetime | None = None,
    ) -> object: ...


@dataclass(frozen=True)
class DeviceSummaryReadContext:
    networks_by_id: Mapping[str, NetworkRow]
    ha_enrichment_by_key: Mapping[tuple[str, str], Mapping[str, Any]]
    incident_affected_keys: frozenset[tuple[str, str]]


@dataclass(frozen=True)
class DeviceCompositionReadContext:
    summary: DeviceSummaryReadContext
    related_incident_ids_by_key: Mapping[tuple[str, str], tuple[str, ...]]


@dataclass(frozen=True)
class IncidentCompositionContext:
    refs_by_incident_id: Mapping[str, tuple[dict[str, str], ...]]
    devices_by_key: Mapping[tuple[str, str], DeviceRow]
    events_by_incident_id: Mapping[str, tuple[dict[str, Any], ...]]
    decision_badges_by_key: Mapping[tuple[str, str], DeviceDecisionBadge]


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


def _timeline_from_event_rows(rows: list[dict[str, Any]]) -> list[TimelineEvent]:
    return [
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
        for row in rows
    ]


def _incident_status_counts(
    incident_context: ActiveIncidentReadContext | None,
) -> tuple[int, int]:
    if incident_context is None:
        return 0, 0
    open_count = sum(
        1 for row in incident_context.incidents if row["lifecycle_state"] == "open"
    )
    watching_count = sum(
        1 for row in incident_context.incidents if row["lifecycle_state"] == "watching"
    )
    return open_count, watching_count


def _group_devices_by_network(rows: list[DeviceRow]) -> dict[str, list[DeviceRow]]:
    grouped: dict[str, list[DeviceRow]] = {}
    for row in rows:
        grouped.setdefault(row.network_id, []).append(row)
    return grouped


class PayloadBuilder:
    def __init__(
        self,
        config: AppConfig,
        repo: Repository,
        health: HealthDiagnosticService | None = None,
        incidents: IncidentDiagnosticService | None = None,
        evaluation: EvaluationAccess | None = None,
    ) -> None:
        self.config = config
        self.repo = repo
        self.health = health
        self._incident_service = incidents
        self._evaluation = evaluation

    def _ensure_health(self) -> HealthDiagnosticService | None:
        if self.health is None:
            return None
        if self._evaluation is not None and self.repo.has_collected_data():
            network_ids = [network.id for network in self.repo.list_networks()]
            if not self.health.has_complete_network_cache(network_ids):
                self._evaluation.evaluate_all()
        return self.health

    def _device_composition_context(
        self,
        rows: list[DeviceRow],
        include_related_incidents: bool,
        incident_context: ActiveIncidentReadContext | None = None,
    ) -> DeviceCompositionReadContext:
        keys = [(row.network_id, row.ieee_address) for row in rows]
        networks_by_id = MappingProxyType(
            {network.id: network for network in self.repo.list_networks()}
        )
        ha_enrichment_by_key = MappingProxyType(
            self.repo.list_ha_device_enrichment_for_devices(keys)
        )
        if incident_context is None and self._incident_service is not None:
            incident_context = self._incident_service.active_incident_read_context()
        affected_keys = (
            incident_context.affected_keys
            if incident_context is not None
            else frozenset()
        )
        summary_context = DeviceSummaryReadContext(
            networks_by_id=networks_by_id,
            ha_enrichment_by_key=ha_enrichment_by_key,
            incident_affected_keys=affected_keys,
        )
        if include_related_incidents:
            related_map = self.repo.incidents.list_incident_ids_for_devices(keys)
            related_incident_ids_by_key = MappingProxyType(
                {key: tuple(related_map.get(key, [])) for key in keys}
            )
        else:
            related_incident_ids_by_key = MappingProxyType({})
        return DeviceCompositionReadContext(
            summary=summary_context,
            related_incident_ids_by_key=related_incident_ids_by_key,
        )

    def _incident_composition_context(
        self,
        rows: list[dict],
        *,
        now: datetime | None = None,
    ) -> IncidentCompositionContext:
        incident_ids = [row["id"] for row in rows]
        refs_map = self.repo.incidents.list_incident_devices_for_incidents(incident_ids)
        refs_by_incident_id = MappingProxyType(
            {
                incident_id: tuple(refs_map.get(incident_id, []))
                for incident_id in incident_ids
            }
        )
        keys: list[tuple[str, str]] = []
        seen_keys: set[tuple[str, str]] = set()
        for refs in refs_map.values():
            for ref in refs:
                key = (ref["network_id"], ref["ieee_address"])
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                keys.append(key)
        devices_by_key = MappingProxyType(self.repo.get_devices_by_keys(keys))
        events_map = self.repo.list_events_for_incidents(incident_ids)
        events_by_incident_id = MappingProxyType(
            {
                incident_id: tuple(events_map.get(incident_id, []))
                for incident_id in incident_ids
            }
        )
        device_rows = list(devices_by_key.values())
        decision_badges = device_decision_badges_for_devices(
            self.repo,
            device_rows,
            now=now,
        )
        return IncidentCompositionContext(
            refs_by_incident_id=refs_by_incident_id,
            devices_by_key=devices_by_key,
            events_by_incident_id=events_by_incident_id,
            decision_badges_by_key=MappingProxyType(decision_badges),
        )

    def dashboard(self) -> DashboardPayload:
        if not self.repo.has_collected_data():
            return build_empty_dashboard(self.config, self.repo.list_networks())

        health = self._ensure_health()
        if not health:
            health = self._fallback_health()
        network_rows = self.repo.list_networks()
        rows = self.repo.list_devices()
        incident_context = (
            self._incident_service.active_incident_read_context()
            if self._incident_service
            else None
        )
        composition = self._device_composition_context(
            rows,
            include_related_incidents=False,
            incident_context=incident_context,
        )
        devices = self._devices_from_rows(rows, summary_context=composition.summary)
        finding = live_finding(
            self.repo,
            self.config,
            health,
            self._incident_service,
            devices=rows,
            networks=network_rows,
        )

        open_count, watching_count = _incident_status_counts(incident_context)

        def _is_affected(d: DeviceSummary) -> bool:
            return d.health.primary not in {
                DeviceHealthPrimary.healthy,
                DeviceHealthPrimary.unknown,
            }

        top_affected = sorted(
            [d for d in devices if _is_affected(d)],
            key=lambda d: d.sort_priority,
        )[:10]

        devices_by_network = _group_devices_by_network(rows)
        network_summaries = [
            build_network_summary(
                self.repo,
                net_row,
                health,
                self._incident_service,
                devices=devices_by_network.get(net_row.id, []),
                active_incident_count=(
                    incident_context.active_count_by_network_id.get(net_row.id, 0)
                    if incident_context is not None
                    else None
                ),
                incident_context=incident_context,
            )
            for net_row in network_rows
        ]

        shared_availability_events = compose_dashboard_shared_availability_events(
            self.repo, network_rows
        )
        model_patterns = compose_dashboard_model_patterns(self.repo, network_rows)
        investigation_priorities = compose_dashboard_investigation_priorities(
            self.repo, network_rows
        )
        data_coverage_warnings = compose_dashboard_coverage_warnings(
            self.repo,
            network_rows,
            self.config,
            route_hint_relevant_network_ids={
                item.network_id
                for item in investigation_priorities
                if item.card_type == "router_neighbourhood_review"
            },
        )

        return DashboardPayload(
            generated_at=utc_now_iso(),
            scenario=None,
            overall_severity=finding.severity,
            current_finding=finding,
            active_incident_count=open_count,
            watching_incident_count=watching_count,
            networks=network_summaries,
            top_affected_devices=top_affected,
            router_risks=self.routers(
                devices=rows,
                incident_context=incident_context,
                health=health,
            ),
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
            health_snapshot=build_health_snapshot(
                self.repo,
                health,
                self._incident_service,
                networks=network_rows,
                devices=rows,
                network_summaries=network_summaries,
                incident_context=incident_context,
            ),
            shared_availability_events=shared_availability_events,
            model_patterns=model_patterns,
            investigation_priorities=investigation_priorities,
            data_coverage_warnings=data_coverage_warnings,
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
        network_rows = self.repo.list_networks()
        device_rows = self.repo.list_devices()
        incident_context = (
            self._incident_service.active_incident_read_context()
            if self._incident_service
            else None
        )
        devices_by_network = _group_devices_by_network(device_rows)
        return [
            build_network_summary(
                self.repo,
                row,
                health,
                self._incident_service,
                devices=devices_by_network.get(row.id, []),
                active_incident_count=(
                    incident_context.active_count_by_network_id.get(row.id, 0)
                    if incident_context is not None
                    else None
                ),
                incident_context=incident_context,
            )
            for row in network_rows
        ]

    def network(self, network_id: str):
        row = self.repo.get_network(network_id)
        if not row:
            return None
        health = self._ensure_health() or self._fallback_health()
        device_rows = self.repo.list_devices(network_id)
        incident_context = (
            self._incident_service.active_incident_read_context()
            if self._incident_service
            else None
        )
        return build_network_summary(
            self.repo,
            row,
            health,
            self._incident_service,
            devices=device_rows,
            active_incident_count=(
                incident_context.active_count_by_network_id.get(network_id, 0)
                if incident_context is not None
                else None
            ),
            incident_context=incident_context,
        )

    def devices(self, network_id: str | None = None) -> list[DeviceSummary]:
        rows = self.repo.list_devices(network_id)
        composition = self._device_composition_context(
            rows,
            include_related_incidents=True,
        )
        badges = device_decision_badges_for_devices(
            self.repo,
            rows,
            ha_enrichment_by_key=composition.summary.ha_enrichment_by_key,
            related_incident_ids_by_key=composition.related_incident_ids_by_key,
        )
        return self._devices_from_rows(
            rows,
            summary_context=composition.summary,
            decision_badges=badges,
        )

    def _devices_from_rows(
        self,
        rows: list[DeviceRow],
        *,
        summary_context: DeviceSummaryReadContext | None = None,
        decision_badges: dict[tuple[str, str], DeviceDecisionBadge] | None = None,
    ) -> list[DeviceSummary]:
        self._ensure_health()
        if summary_context is None:
            summary_context = self._device_composition_context(
                rows, include_related_incidents=False
            ).summary
        summaries = [
            self._device_summary(
                row,
                summary_context=summary_context,
                decision_badge=(
                    None
                    if decision_badges is None
                    else decision_badges.get((row.network_id, row.ieee_address))
                ),
            )
            for row in rows
        ]
        return sorted(summaries, key=lambda d: d.sort_priority)

    def device_detail(self, network_id: str, ieee_address: str) -> DeviceDetail | None:
        row = self.repo.get_device(network_id, ieee_address)
        if not row:
            return None
        badge = device_decision_badge_for_device(self.repo, network_id, ieee_address)
        return self._device_detail_from_row(row, decision_badge=badge)

    def _device_detail_from_row(
        self,
        row: DeviceRow,
        *,
        decision_badge: DeviceDecisionBadge | None = None,
    ) -> DeviceDetail:
        """Build DeviceDetail without composing Device Story decisions."""
        network_id = row.network_id
        ieee_address = row.ieee_address
        summary = self._device_summary(row, decision_badge=decision_badge)
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

        related_ids = self.repo.incidents.list_incidents_for_device(network_id, ieee_address)
        if related_ids and self._incident_service:
            top = self.repo.incidents.get_incident(related_ids[0])
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

        event_rows = self.repo.list_events_for_device(network_id, ieee_address, limit=20)

        return DeviceDetail(
            **summary.model_dump(),
            recent_availability_changes=availability_changes,
            recent_events=_timeline_from_event_rows(event_rows),
            recent_bridge_logs=[],
            diagnostic=finding,
            trends=trends,
        )

    def routers(
        self,
        *,
        devices: list[DeviceRow] | None = None,
        incident_context: ActiveIncidentReadContext | None = None,
        health: HealthDiagnosticService | None = None,
    ) -> list[RouterRisk]:
        health_svc = health or self._ensure_health() or self._fallback_health()
        device_rows = devices if devices is not None else self.repo.list_devices()
        if incident_context is None and self._incident_service is not None:
            incident_context = self._incident_service.active_incident_read_context()
        items: list[RouterRisk] = []
        for row in device_rows:
            if row.device_type != "Router":
                continue
            result = health_svc.get_device_health(row.network_id, row.ieee_address)
            if result is None or HealthFlag.router_risk not in result.flags:
                continue
            risk = health_result_to_router_risk(row, result, self.repo)
            if self._incident_service:
                key = (row.network_id, row.ieee_address)
                if incident_context is not None:
                    related = incident_context.incident_ids_by_device_key.get(key, ())
                else:
                    related = self.repo.incidents.list_incidents_for_device(
                        row.network_id, row.ieee_address
                    )
                risk.correlated_affected_devices = len(related)
            items.append(risk)
        return sorted(items, key=lambda r: r.risk.severity.value)

    def incidents(self) -> list[Incident]:
        rows = self.repo.incidents.list_incidents()
        composition = self._incident_composition_context(
            rows,
            now=datetime.now(timezone.utc),
        )
        return [
            inc
            for row in rows
            if (inc := self._incident_from_row(row, composition=composition)) is not None
        ]

    def incident(self, incident_id: str) -> Incident | None:
        row = self.repo.incidents.get_incident(incident_id)
        if not row:
            return None
        composition = self._incident_composition_context(
            [row],
            now=datetime.now(timezone.utc),
        )
        return self._incident_from_row(row, composition=composition)

    def _unique_device_rows_for_incidents(self, rows: list[dict]) -> list[DeviceRow]:
        """Collect existing DeviceRows for incident refs once, by (network, ieee)."""
        incident_ids = [row["id"] for row in rows]
        refs_map = self.repo.incidents.list_incident_devices_for_incidents(incident_ids)
        keys: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for refs in refs_map.values():
            for ref in refs:
                key = (ref["network_id"], ref["ieee_address"])
                if key in seen:
                    continue
                seen.add(key)
                keys.append(key)
        return list(self.repo.get_devices_by_keys(keys).values())

    def timeline(self, network_id: str | None = None) -> list[TimelineEvent]:
        return _timeline_from_event_rows(self.repo.list_events(network_id))

    def _device_summary(
        self,
        row: DeviceRow,
        *,
        summary_context: DeviceSummaryReadContext | None = None,
        decision_badge: DeviceDecisionBadge | None = None,
    ) -> DeviceSummary:
        # Batch callers ensure health once; avoid list_networks per device.
        health_svc = self.health if summary_context is not None else self._ensure_health()
        result = (
            health_svc.get_device_health(row.network_id, row.ieee_address)
            if health_svc
            else None
        )
        if result is None and health_svc and self._evaluation is not None:
            self._evaluation.evaluate_network(row.network_id)
            result = health_svc.get_device_health(row.network_id, row.ieee_address)
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
        if summary_context is not None:
            incident_affected = (
                row.network_id,
                row.ieee_address,
            ) in summary_context.incident_affected_keys
            network_row = summary_context.networks_by_id.get(row.network_id)
            ha_enrichment = summary_context.ha_enrichment_by_key.get(
                (row.network_id, row.ieee_address)
            )
        else:
            affected_keys = (
                self._incident_service.incident_affected_keys()
                if self._incident_service
                else set()
            )
            incident_affected = (row.network_id, row.ieee_address) in affected_keys
            network_row = self.repo.get_network(row.network_id)
            ha_enrichment = self.repo.get_ha_device_enrichment(
                row.network_id, row.ieee_address
            )
        bridge_state = None
        if network_row is not None and network_row.bridge_state in BridgeState.__members__:
            bridge_state = BridgeState(network_row.bridge_state)
        ha_area = None
        if ha_enrichment:
            area_name = ha_enrichment.get("area_name")
            if isinstance(area_name, str) and area_name.strip():
                ha_area = area_name.strip()
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
            decision=decision_badge,
            ha_area=ha_area,
        )
        return enrich_device_summary(summary, bridge_state=bridge_state)

    def _incident_from_row(
        self,
        row: dict,
        *,
        composition: IncidentCompositionContext | None = None,
        decision_badges: dict[tuple[str, str], DeviceDecisionBadge] | None = None,
    ) -> Incident | None:
        if not row:
            return None
        incident_id = row["id"]
        if composition is not None:
            refs = composition.refs_by_incident_id.get(incident_id, ())
            badge_source = composition.decision_badges_by_key
            event_rows = composition.events_by_incident_id.get(incident_id, ())
            devices_by_key = composition.devices_by_key
        else:
            refs = tuple(self.repo.incidents.list_incident_devices(incident_id))
            badge_source = decision_badges or {}
            event_rows = tuple(
                self.repo.list_events_for_incident(incident_id, limit=100)
            )
            devices_by_key = MappingProxyType(
                self.repo.get_devices_by_keys(
                    [(ref["network_id"], ref["ieee_address"]) for ref in refs]
                )
            )
        affected = []
        for ref in refs:
            key = (ref["network_id"], ref["ieee_address"])
            dev = devices_by_key.get(key)
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
            decision = badge_source.get(key)
            affected.append(
                IncidentDeviceRef(
                    network_id=ref["network_id"],
                    ieee_address=ref["ieee_address"],
                    friendly_name=friendly,
                    health_primary=health_primary,
                    name=friendly,
                    classification=str(bucket),
                    reason=bucket_reason or str(presentation.get("lens_bucket_label", "")),
                    decision=decision,
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
        timeline = _timeline_from_event_rows(list(event_rows))
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
