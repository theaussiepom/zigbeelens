"""Incident diagnostic orchestration."""

from __future__ import annotations

from typing import Callable

from zigbeelens.config.models import AppConfig
from zigbeelens.diagnostics.incidents.correlator import IncidentCorrelationEngine
from zigbeelens.diagnostics.incidents.lifecycle import IncidentLifecycleManager
from zigbeelens.diagnostics.incidents.models import IncidentLifecycle
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.schemas import (
    Confidence,
    DiagnosticConclusion,
    EvidenceItem,
    IncidentScope,
    LimitationItem,
    Severity,
)
from zigbeelens.storage.repository import Repository

OnIncidentUpdate = Callable[[str], None]


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

    def correlate_and_sync(self, health: HealthDiagnosticService) -> list[str]:
        candidates = self._engine.correlate(health)
        events = self._lifecycle.sync(candidates)
        if events and self._on_update:
            for event in events:
                self._on_update(event)
        return events

    def active_incidents(self) -> list[dict]:
        return self.repo.list_incidents(status_filter=("open", "watching"))

    def current_finding(self, health: HealthDiagnosticService) -> DiagnosticConclusion | None:
        incidents = self.active_incidents()
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
                for i, item in enumerate(_json_list(top.get("evidence_json")))
            ],
            counter_evidence=[
                EvidenceItem(id=f"ce-{i}", kind="incident", summary=_summary_item(item))
                for i, item in enumerate(_json_list(top.get("counter_evidence_json")))
            ],
            limitations=[
                LimitationItem(id=f"lim-{i}", summary=_summary_item(item))
                for i, item in enumerate(_json_list(top.get("limitations_json")))
            ],
        )

    def incident_affected_keys(self) -> set[tuple[str, str]]:
        keys: set[tuple[str, str]] = set()
        for row in self.active_incidents():
            for ref in self.repo.list_incident_devices(row["id"]):
                keys.add((ref["network_id"], ref["ieee_address"]))
        return keys

    def count_by_status(self) -> tuple[int, int]:
        open_count = 0
        watching_count = 0
        for row in self.repo.list_incidents():
            if row["lifecycle_state"] == IncidentLifecycle.open.value:
                open_count += 1
            elif row["lifecycle_state"] == IncidentLifecycle.watching.value:
                watching_count += 1
        return open_count, watching_count

    def network_active_count(self, network_id: str) -> int:
        count = 0
        for row in self.active_incidents():
            refs = self.repo.list_incident_devices(row["id"])
            if any(ref["network_id"] == network_id for ref in refs):
                count += 1
                continue
            dedup = row.get("dedup_key") or ""
            if dedup.endswith(f":{network_id}") or f":{network_id}:" in dedup:
                count += 1
        return count


def _summary_item(item) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("summary", str(item))
    return str(item)


def _json_list(raw: str | None) -> list:
    import json

    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return []
