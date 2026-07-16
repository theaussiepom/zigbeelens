"""Incident diagnostic orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping

from zigbeelens.config.models import AppConfig
from zigbeelens.diagnostics.incidents.correlator import IncidentCorrelationEngine
from zigbeelens.diagnostics.incidents.lifecycle import IncidentLifecycleManager
from zigbeelens.diagnostics.incidents.models import IncidentLifecycle
from zigbeelens.diagnostics.service import HealthDiagnosticService, NetworkEvaluationSnapshot
from zigbeelens.schemas import (
    Confidence,
    DiagnosticConclusion,
    EvidenceItem,
    IncidentScope,
    LimitationItem,
    Severity,
)
from zigbeelens.storage.repository import Repository
from zigbeelens.util.json_helpers import parse_json_list

OnIncidentUpdate = Callable[[str], None]


@dataclass(frozen=True)
class ActiveIncidentReadContext:
    incidents: tuple[dict[str, Any], ...]
    incidents_by_id: Mapping[str, dict[str, Any]]
    refs_by_incident_id: Mapping[str, tuple[dict[str, str], ...]]
    affected_keys: frozenset[tuple[str, str]]
    incident_ids_by_device_key: Mapping[tuple[str, str], tuple[str, ...]]
    active_count_by_network_id: Mapping[str, int]


def build_active_incident_read_context(repo: Repository) -> ActiveIncidentReadContext:
    incidents = tuple(repo.incidents.list_incidents(status_filter=("open", "watching")))
    incident_ids = [row["id"] for row in incidents]
    refs_map = repo.incidents.list_incident_devices_for_incidents(incident_ids)
    refs_by_incident_id = MappingProxyType(
        {incident_id: tuple(refs_map.get(incident_id, [])) for incident_id in incident_ids}
    )
    incidents_by_id = MappingProxyType({row["id"]: row for row in incidents})

    affected: set[tuple[str, str]] = set()
    incident_ids_by_device: dict[tuple[str, str], list[str]] = {}
    active_count_by_network: dict[str, int] = {}
    network_ids: list[str] | None = None

    for row in incidents:
        refs = refs_by_incident_id[row["id"]]
        networks_for_incident: set[str] = set()
        for ref in refs:
            key = (ref["network_id"], ref["ieee_address"])
            affected.add(key)
            incident_ids_by_device.setdefault(key, []).append(row["id"])
            networks_for_incident.add(ref["network_id"])
        if not networks_for_incident:
            dedup = row.get("dedup_key") or ""
            if network_ids is None:
                network_ids = [network.id for network in repo.list_networks()]
            for network_id in network_ids:
                if dedup.endswith(f":{network_id}") or f":{network_id}:" in dedup:
                    networks_for_incident.add(network_id)
        for network_id in networks_for_incident:
            active_count_by_network[network_id] = active_count_by_network.get(network_id, 0) + 1

    return ActiveIncidentReadContext(
        incidents=incidents,
        incidents_by_id=incidents_by_id,
        refs_by_incident_id=refs_by_incident_id,
        affected_keys=frozenset(affected),
        incident_ids_by_device_key=MappingProxyType(
            {key: tuple(ids) for key, ids in incident_ids_by_device.items()}
        ),
        active_count_by_network_id=MappingProxyType(active_count_by_network),
    )


class IncidentDiagnosticService:
    def __init__(
        self,
        config: AppConfig,
        repo: Repository,
        on_update: OnIncidentUpdate | None = None,
    ) -> None:
        self.config = config
        self.repo = repo
        self._on_update = on_update
        self._engine = IncidentCorrelationEngine(config, repo)
        self._lifecycle = IncidentLifecycleManager(config, repo)

    def correlate_and_sync(self, snapshots: list[NetworkEvaluationSnapshot], *, now) -> list[str]:
        candidates = self._engine.correlate(snapshots, now=now)
        events = self._lifecycle.sync(candidates, now=now)
        if events and self._on_update:
            for event in events:
                self._on_update(event)
        return events

    def active_incidents(self) -> list[dict]:
        return self.repo.incidents.list_incidents(status_filter=("open", "watching"))

    def active_incident_read_context(self) -> ActiveIncidentReadContext:
        return build_active_incident_read_context(self.repo)

    def current_finding(
        self,
        health: HealthDiagnosticService,
        *,
        context: ActiveIncidentReadContext | None = None,
    ) -> DiagnosticConclusion | None:
        incidents = list(context.incidents) if context is not None else self.active_incidents()
        if not incidents:
            return None
        top = sorted(
            incidents,
            key=lambda row: (
                0 if row["lifecycle_state"] == IncidentLifecycle.open.value else 1,
                {"critical": 0, "incident": 1, "watch": 2, "healthy": 3}.get(row["severity"], 9),
            ),
        )[0]
        return DiagnosticConclusion(
            classification=top["incident_type"],
            severity=Severity(top["severity"]),
            scope=IncidentScope(top["scope"]),
            confidence=Confidence(top["confidence"]),
            summary=top["summary"],
            evidence=[
                EvidenceItem(id=f"ev-{i}", kind="incident", summary=_summary_item(item))
                for i, item in enumerate(parse_json_list(top.get("evidence_json")))
            ],
            counter_evidence=[
                EvidenceItem(id=f"ce-{i}", kind="incident", summary=_summary_item(item))
                for i, item in enumerate(parse_json_list(top.get("counter_evidence_json")))
            ],
            limitations=[
                LimitationItem(id=f"lim-{i}", summary=_summary_item(item))
                for i, item in enumerate(parse_json_list(top.get("limitations_json")))
            ],
        )

    def network_active_count(
        self,
        network_id: str,
        *,
        context: ActiveIncidentReadContext | None = None,
    ) -> int:
        ctx = context or self.active_incident_read_context()
        return int(ctx.active_count_by_network_id.get(network_id, 0))

    def incident_affected_keys(
        self,
        *,
        context: ActiveIncidentReadContext | None = None,
    ) -> set[tuple[str, str]]:
        ctx = context or self.active_incident_read_context()
        return set(ctx.affected_keys)

    def count_by_status(
        self,
        *,
        context: ActiveIncidentReadContext | None = None,
    ) -> tuple[int, int]:
        if context is not None:
            open_count = sum(
                1 for row in context.incidents if row["lifecycle_state"] == IncidentLifecycle.open.value
            )
            watching_count = sum(
                1
                for row in context.incidents
                if row["lifecycle_state"] == IncidentLifecycle.watching.value
            )
            return open_count, watching_count
        open_count = 0
        watching_count = 0
        for row in self.repo.incidents.list_incidents(
            status_filter=(
                IncidentLifecycle.open.value,
                IncidentLifecycle.watching.value,
            )
        ):
            if row["lifecycle_state"] == IncidentLifecycle.open.value:
                open_count += 1
            elif row["lifecycle_state"] == IncidentLifecycle.watching.value:
                watching_count += 1
        return open_count, watching_count


def _summary_item(item) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("summary", str(item))
    return str(item)


__all__ = [
    "ActiveIncidentReadContext",
    "IncidentDiagnosticService",
    "build_active_incident_read_context",
]
