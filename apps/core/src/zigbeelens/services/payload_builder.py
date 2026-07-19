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
    health_result_to_router_risk,
)
from zigbeelens.schemas import (
    Availability,
    AvailabilityChange,
    Confidence,
    DashboardPayload,
    DeviceDecisionBadge,
    DeviceDetail,
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
from zigbeelens.services.decision_summary import (
    DECISION_STATUS_ORDER,
    data_unavailable_device_badge,
    decision_count_summary_from_badges,
)
from zigbeelens.services.empty_state import empty_finding
from zigbeelens.services.device_decision_badge import (
    device_decision_badge_for_device,
    device_decision_badges_for_devices,
)
from zigbeelens.services.empty_state import build_empty_dashboard
from zigbeelens.services.live_dashboard import build_network_summary
from zigbeelens.storage.repository import DeviceRow, NetworkRow, Repository
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
    networks_by_incident_id: Mapping[str, tuple[str, ...]] = MappingProxyType({})


def _parse_json_list(raw: str | None) -> list:
    return parse_json_list(raw)


_STATUS_RANK = {status.value: index for index, status in enumerate(DECISION_STATUS_ORDER)}


def _device_decision_sort_key(device: DeviceSummary) -> tuple[int, str, str]:
    """Deterministic inventory order from decision status, then identity."""
    status = str(device.decision.status)
    return (
        _STATUS_RANK.get(status, len(_STATUS_RANK)),
        device.network_id,
        device.ieee_address,
    )


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

    def _ensure_device_health_for_rows(
        self, rows: list[DeviceRow]
    ) -> HealthDiagnosticService | None:
        """Complete network+device health for the requested rows before freezing context."""
        health = self._ensure_health()
        if health is None or self._evaluation is None or not rows:
            return health
        missing_networks: set[str] = set()
        for row in rows:
            if health.get_device_health(row.network_id, row.ieee_address) is None:
                missing_networks.add(row.network_id)
        for network_id in sorted(missing_networks):
            self._evaluation.evaluate_network(network_id)
        return health

    def _device_composition_context(
        self,
        rows: list[DeviceRow],
        include_related_incidents: bool,
        incident_context: ActiveIncidentReadContext | None = None,
        *,
        networks_by_id: Mapping[str, NetworkRow] | None = None,
        ha_enrichment_by_key: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
    ) -> DeviceCompositionReadContext:
        keys = [(row.network_id, row.ieee_address) for row in rows]
        if networks_by_id is None:
            networks_by_id = {network.id: network for network in self.repo.list_networks()}
        if ha_enrichment_by_key is None:
            ha_enrichment_by_key = self.repo.list_ha_device_enrichment_for_devices(keys)
        if incident_context is None and self._incident_service is not None:
            incident_context = self._incident_service.active_incident_read_context()
        affected_keys = (
            incident_context.affected_keys
            if incident_context is not None
            else frozenset()
        )
        summary_context = DeviceSummaryReadContext(
            networks_by_id=MappingProxyType(dict(networks_by_id)),
            ha_enrichment_by_key=MappingProxyType(dict(ha_enrichment_by_key)),
            incident_affected_keys=affected_keys,
        )
        if include_related_incidents:
            if incident_context is not None:
                related_incident_ids_by_key = MappingProxyType(
                    {
                        key: tuple(
                            incident_context.incident_ids_by_device_key.get(key, ())
                        )
                        for key in keys
                    }
                )
            else:
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
        include_events: bool = True,
        refs_by_incident_id: Mapping[str, tuple[dict[str, str], ...]] | None = None,
        devices_by_key: Mapping[tuple[str, str], DeviceRow] | None = None,
        events_by_incident_id: Mapping[str, tuple[dict[str, Any], ...]] | None = None,
        decision_badges_by_key: Mapping[tuple[str, str], DeviceDecisionBadge] | None = None,
        networks_by_incident_id: Mapping[str, tuple[str, ...]] | None = None,
    ) -> IncidentCompositionContext:
        incident_ids = [row["id"] for row in rows]
        if not incident_ids:
            return IncidentCompositionContext(
                refs_by_incident_id=MappingProxyType({}),
                devices_by_key=MappingProxyType({}),
                events_by_incident_id=MappingProxyType({}),
                decision_badges_by_key=MappingProxyType({}),
                networks_by_incident_id=MappingProxyType({}),
            )
        if refs_by_incident_id is None:
            refs_map = self.repo.incidents.list_incident_devices_for_incidents(incident_ids)
            refs_by_incident_id = MappingProxyType(
                {
                    incident_id: tuple(refs_map.get(incident_id, []))
                    for incident_id in incident_ids
                }
            )
        else:
            refs_by_incident_id = MappingProxyType(dict(refs_by_incident_id))
        if devices_by_key is None:
            keys: list[tuple[str, str]] = []
            seen_keys: set[tuple[str, str]] = set()
            for refs in refs_by_incident_id.values():
                for ref in refs:
                    key = (ref["network_id"], ref["ieee_address"])
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    keys.append(key)
            devices_by_key = MappingProxyType(self.repo.get_devices_by_keys(keys))
        else:
            devices_by_key = MappingProxyType(dict(devices_by_key))
        if events_by_incident_id is None:
            if include_events:
                events_map = self.repo.list_events_for_incidents(incident_ids)
            else:
                events_map = {incident_id: [] for incident_id in incident_ids}
            events_by_incident_id = MappingProxyType(
                {
                    incident_id: tuple(events_map.get(incident_id, []))
                    for incident_id in incident_ids
                }
            )
        else:
            events_by_incident_id = MappingProxyType(dict(events_by_incident_id))
        if networks_by_incident_id is None:
            networks_map = self.repo.incidents.list_incident_networks_for_incidents(
                incident_ids
            )
            networks_by_incident_id = MappingProxyType(
                {
                    incident_id: tuple(networks_map.get(incident_id, []))
                    for incident_id in incident_ids
                }
            )
        else:
            networks_by_incident_id = MappingProxyType(dict(networks_by_incident_id))
        if decision_badges_by_key is None:
            device_rows = list(devices_by_key.values())
            evidence_map = self._device_story_evidence_contexts(device_rows, now=now)
            decision_badges_by_key = MappingProxyType(
                device_decision_badges_for_devices(
                    self.repo,
                    device_rows,
                    now=now,
                    network_evidence_contexts=evidence_map,
                )
            )
        else:
            decision_badges_by_key = MappingProxyType(dict(decision_badges_by_key))
        return IncidentCompositionContext(
            refs_by_incident_id=refs_by_incident_id,
            devices_by_key=devices_by_key,
            events_by_incident_id=events_by_incident_id,
            decision_badges_by_key=decision_badges_by_key,
            networks_by_incident_id=networks_by_incident_id,
        )

    def dashboard(self) -> DashboardPayload:
        if not self.repo.has_collected_data():
            return build_empty_dashboard(self.config, self.repo.list_networks())

        rows = self.repo.list_devices()
        health = self._ensure_device_health_for_rows(rows)
        if not health:
            health = self._fallback_health()
        network_rows = self.repo.list_networks()
        incident_context = (
            self._incident_service.active_incident_read_context()
            if self._incident_service
            else None
        )
        composition = self._device_composition_context(
            rows,
            include_related_incidents=True,
            incident_context=incident_context,
        )

        if self._incident_service is not None:
            open_count, watching_count = self._incident_service.count_by_status(
                context=incident_context
            )
        else:
            open_count, watching_count = 0, 0

        from zigbeelens.services.network_evidence import DASHBOARD_EVIDENCE_REQUIREMENTS
        from zigbeelens.services.network_evidence_composition import (
            compose_network_evidence_contexts,
        )
        from zigbeelens.services.topology_facts_composition import (
            topology_stale_threshold_hours,
        )

        reference_now = datetime.now(timezone.utc)
        devices_by_network = _group_devices_by_network(rows)
        devices_by_network_id = {
            network.id: devices_by_network.get(network.id, []) for network in network_rows
        }
        evidence_contexts = compose_network_evidence_contexts(
            self.repo,
            [network.id for network in network_rows],
            reference_now=reference_now,
            requirements_by_network={
                network.id: DASHBOARD_EVIDENCE_REQUIREMENTS for network in network_rows
            },
            network_rows_by_id={network.id: network for network in network_rows},
            complete_device_rows_by_network=devices_by_network_id,
            stale_after_hours=topology_stale_threshold_hours(self.config),
        )
        evidence_map = dict(evidence_contexts)

        # One Device Story badge batch for the whole estate (reused for networks).
        badges = device_decision_badges_for_devices(
            self.repo,
            rows,
            now=reference_now,
            ha_enrichment_by_key=composition.summary.ha_enrichment_by_key,
            related_incident_ids_by_key=composition.related_incident_ids_by_key,
            network_evidence_contexts=evidence_map,
        )
        devices = self._devices_from_rows(
            rows,
            summary_context=composition.summary,
            decision_badges=badges,
        )

        shared_availability_events = compose_dashboard_shared_availability_events(
            self.repo,
            network_rows,
            now=reference_now,
            network_evidence_contexts=evidence_map,
        )
        model_patterns = compose_dashboard_model_patterns(
            self.repo,
            network_rows,
            now=reference_now,
            network_evidence_contexts=evidence_map,
        )
        investigation_priorities = compose_dashboard_investigation_priorities(
            self.repo,
            network_rows,
            now=reference_now,
            network_evidence_contexts=evidence_map,
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
            now=reference_now,
            network_evidence_contexts=evidence_map,
        )

        coverage_by_network: dict[str, int] = {}
        for warning in data_coverage_warnings:
            coverage_by_network[warning.network_id] = (
                coverage_by_network.get(warning.network_id, 0) + 1
            )

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
                device_decision_badges=[
                    badges[(row.network_id, row.ieee_address)]
                    for row in devices_by_network.get(net_row.id, [])
                    if (row.network_id, row.ieee_address) in badges
                ],
                coverage_warning_count=coverage_by_network.get(net_row.id, 0),
            )
            for net_row in network_rows
        ]

        decision_summary = decision_count_summary_from_badges(
            [d.decision for d in devices],
            coverage_warning_count=len(data_coverage_warnings),
        )
        unavailable_device_count = sum(
            1 for d in devices if d.availability == Availability.offline
        )

        return DashboardPayload(
            generated_at=reference_now.isoformat(),
            scenario=None,
            active_incident_count=open_count,
            watching_incident_count=watching_count,
            network_count=len(network_summaries),
            device_count=len(devices),
            unavailable_device_count=unavailable_device_count,
            networks=network_summaries,
            router_risks=self.routers(
                devices=rows,
                incident_context=incident_context,
                health=health,
                network_evidence_contexts=evidence_map,
            ),
            recent_timeline=self.timeline()[:12],
            decision_summary=decision_summary,
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

    def _network_summaries_with_decisions(
        self,
        network_rows: list[NetworkRow],
        device_rows: list[DeviceRow],
        *,
        health: HealthDiagnosticService,
        incident_context: ActiveIncidentReadContext | None,
    ) -> list:
        """Build NetworkSummary list with one Device Story badge batch."""
        reference_now = datetime.now(timezone.utc)
        composition = self._device_composition_context(
            device_rows,
            include_related_incidents=True,
            incident_context=incident_context,
        )
        evidence_map = self._device_story_evidence_contexts(
            device_rows, now=reference_now, complete_inventory=True
        )
        badges = device_decision_badges_for_devices(
            self.repo,
            device_rows,
            now=reference_now,
            ha_enrichment_by_key=composition.summary.ha_enrichment_by_key,
            related_incident_ids_by_key=composition.related_incident_ids_by_key,
            network_evidence_contexts=evidence_map,
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
                device_decision_badges=[
                    badges[(dev.network_id, dev.ieee_address)]
                    for dev in devices_by_network.get(row.id, [])
                    if (dev.network_id, dev.ieee_address) in badges
                ],
            )
            for row in network_rows
        ]

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
        return self._network_summaries_with_decisions(
            network_rows,
            device_rows,
            health=health,
            incident_context=incident_context,
        )

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
        summaries = self._network_summaries_with_decisions(
            [row],
            device_rows,
            health=health,
            incident_context=incident_context,
        )
        return summaries[0] if summaries else None

    def _device_story_evidence_contexts(
        self,
        rows: list[DeviceRow],
        *,
        now: datetime | None = None,
        complete_inventory: bool = False,
    ) -> dict[str, Any]:
        """One Device Story evidence context per represented network.

        When ``complete_inventory`` is false, ``rows`` are treated as subjects
        only and complete network inventories are loaded via bulk repository
        reads.
        """
        from zigbeelens.services.network_evidence import DEVICE_STORY_EVIDENCE_REQUIREMENTS
        from zigbeelens.services.network_evidence_composition import (
            compose_network_evidence_contexts,
        )

        if not rows:
            return {}
        reference_now = now or datetime.now(timezone.utc)
        if reference_now.tzinfo is None:
            reference_now = reference_now.replace(tzinfo=timezone.utc)
        devices_by_network = _group_devices_by_network(rows)
        network_ids = list(devices_by_network)
        return dict(
            compose_network_evidence_contexts(
                self.repo,
                network_ids,
                reference_now=reference_now,
                requirements_by_network={
                    network_id: DEVICE_STORY_EVIDENCE_REQUIREMENTS
                    for network_id in network_ids
                },
                complete_device_rows_by_network=(
                    devices_by_network if complete_inventory else None
                ),
            )
        )

    def devices(self, network_id: str | None = None) -> list[DeviceSummary]:
        rows = self.repo.list_devices(network_id)
        # Complete health for every requested device before freezing incident context.
        self._ensure_device_health_for_rows(rows)
        incident_context = (
            self._incident_service.active_incident_read_context()
            if self._incident_service
            else None
        )
        composition = self._device_composition_context(
            rows,
            include_related_incidents=True,
            incident_context=incident_context,
        )
        reference_now = datetime.now(timezone.utc)
        # Devices inventory rows are complete for each represented network.
        evidence_map = self._device_story_evidence_contexts(
            rows, now=reference_now, complete_inventory=True
        )
        badges = device_decision_badges_for_devices(
            self.repo,
            rows,
            now=reference_now,
            ha_enrichment_by_key=composition.summary.ha_enrichment_by_key,
            related_incident_ids_by_key=composition.related_incident_ids_by_key,
            network_evidence_contexts=evidence_map,
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
        if summary_context is None:
            self._ensure_device_health_for_rows(rows)
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
        return sorted(summaries, key=_device_decision_sort_key)

    def device_detail(self, network_id: str, ieee_address: str) -> DeviceDetail | None:
        row = self.repo.get_device(network_id, ieee_address)
        if not row:
            return None
        badge = device_decision_badge_for_device(self.repo, network_id, ieee_address)
        return self._device_detail_from_row(
            row,
            decision_badge=badge or data_unavailable_device_badge(),
        )

    def _device_detail_from_row(
        self,
        row: DeviceRow,
        *,
        decision_badge: DeviceDecisionBadge | None = None,
        include_events: bool = True,
        summary: DeviceSummary | None = None,
        summary_context: DeviceSummaryReadContext | None = None,
    ) -> DeviceDetail:
        """Build DeviceDetail facts/trends; judgement stays on Device Story."""
        network_id = row.network_id
        ieee_address = row.ieee_address
        if summary is None:
            summary = self._device_summary(
                row,
                summary_context=summary_context,
                decision_badge=decision_badge,
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

        if include_events:
            event_rows = self.repo.list_events_for_device(
                network_id, ieee_address, limit=20
            )
            recent_events = _timeline_from_event_rows(event_rows)
        else:
            recent_events = []

        return DeviceDetail(
            **summary.model_dump(),
            recent_availability_changes=availability_changes,
            recent_events=recent_events,
            recent_bridge_logs=[],
            trends=trends,
        )

    def routers(
        self,
        *,
        devices: list[DeviceRow] | None = None,
        incident_context: ActiveIncidentReadContext | None = None,
        health: HealthDiagnosticService | None = None,
        network_evidence_contexts: Mapping[str, Any] | None = None,
    ) -> list[RouterRisk]:
        from zigbeelens.services.network_evidence import (
            LATEST_TOPOLOGY_REQUIREMENTS,
            NetworkEvidenceCapability,
            require_mapped_network_evidence_context,
        )
        from zigbeelens.services.network_evidence_composition import (
            compose_network_evidence_contexts,
        )

        health_svc = health or self._ensure_health() or self._fallback_health()
        device_rows = devices if devices is not None else self.repo.list_devices()
        if incident_context is None and self._incident_service is not None:
            incident_context = self._incident_service.active_incident_read_context()
        network_ids = list(dict.fromkeys(row.network_id for row in device_rows))
        if network_evidence_contexts is None:
            evidence_map: dict[str, Any] = {}
            if network_ids:
                reference_now = datetime.now(timezone.utc)
                evidence_map = dict(
                    compose_network_evidence_contexts(
                        self.repo,
                        network_ids,
                        reference_now=reference_now,
                        requirements_by_network={
                            network_id: LATEST_TOPOLOGY_REQUIREMENTS
                            for network_id in network_ids
                        },
                    )
                )
        else:
            evidence_map = {}
            for network_id in network_ids:
                context = require_mapped_network_evidence_context(
                    network_evidence_contexts, network_id
                )
                context.require_compatible(network_id=network_id)
                context.require(NetworkEvidenceCapability.latest_topology)
                evidence_map[network_id] = context
        items: list[RouterRisk] = []
        for row in device_rows:
            if row.device_type != "Router":
                continue
            result = health_svc.get_device_health(row.network_id, row.ieee_address)
            if result is None or HealthFlag.router_risk not in result.flags:
                continue
            risk = health_result_to_router_risk(
                row,
                result,
                self.repo,
                network_evidence_context=evidence_map[row.network_id],
            )
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

    def incidents_page(self, query) -> dict[str, Any]:
        """Bounded incident collection for the public list API (Track 3E)."""
        page = self.repo.incidents.list_incidents_page(query)
        composition = self._incident_composition_context(
            list(page.rows),
            now=datetime.now(timezone.utc),
            include_events=False,
        )
        items = [
            inc
            for row in page.rows
            if (inc := self._incident_from_row(row, composition=composition)) is not None
        ]
        return {
            "items": items,
            "total": page.total,
            "limit": page.limit,
            "next_cursor": page.next_cursor,
        }

    def incident(self, incident_id: str) -> Incident | None:
        row = self.repo.incidents.get_incident(incident_id)
        if not row:
            return None
        composition = self._incident_composition_context(
            [row],
            now=datetime.now(timezone.utc),
            include_events=True,
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
            ha_enrichment = self.repo.get_ha_device_enrichment(
                row.network_id, row.ieee_address
            )
        ha_area = None
        if ha_enrichment:
            area_name = ha_enrichment.get("area_name")
            if isinstance(area_name, str) and area_name.strip():
                ha_area = area_name.strip()
        return DeviceSummary(
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
            incident_affected=incident_affected,
            decision=decision_badge or data_unavailable_device_badge(),
            ha_area=ha_area,
        )

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
            network_ids = list(composition.networks_by_incident_id.get(incident_id, ()))
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
            network_ids = self.repo.incidents.list_incident_networks(incident_id)
        if not network_ids:
            # Fallback for rows not yet backfilled: membership networks only.
            network_ids = sorted({r["network_id"] for r in refs})
        affected = []
        for ref in refs:
            key = (ref["network_id"], ref["ieee_address"])
            dev = devices_by_key.get(key)
            friendly = dev.friendly_name if dev else ref["ieee_address"]
            decision = badge_source.get(key) or data_unavailable_device_badge()
            affected.append(
                IncidentDeviceRef(
                    network_id=ref["network_id"],
                    ieee_address=ref["ieee_address"],
                    friendly_name=friendly,
                    decision=decision,
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
            network_ids=sorted(set(network_ids)),
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
