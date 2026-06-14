"""Incident lifecycle: deduplication, open/update/resolve."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from zigbeelens.config.models import AppConfig
from zigbeelens.diagnostics.incidents.models import IncidentCandidate, IncidentLifecycle
from zigbeelens.storage.repository import Repository, utc_now_iso


class IncidentLifecycleManager:
    def __init__(self, config: AppConfig, repo: Repository) -> None:
        self.config = config
        self.repo = repo

    def sync(self, candidates: list[IncidentCandidate], now: datetime | None = None) -> list[str]:
        now = now or datetime.now(timezone.utc)
        events: list[str] = []
        active_keys = {c.dedup_key for c in candidates if c.active}

        for candidate in candidates:
            if not candidate.active:
                continue
            existing = self.repo.get_incident_by_dedup_key(candidate.dedup_key)
            if existing:
                if self._needs_update(existing, candidate):
                    self.repo.update_incident(
                        incident_id=existing["id"],
                        lifecycle_state=IncidentLifecycle.open.value,
                        severity=candidate.severity.value,
                        confidence=candidate.confidence.value,
                        title=candidate.title,
                        summary=candidate.summary,
                        explanation=candidate.explanation,
                        evidence=candidate.evidence,
                        counter_evidence=candidate.counter_evidence,
                        limitations=candidate.limitations,
                        resolved_at=None,
                    )
                    self.repo.replace_incident_devices(existing["id"], candidate.affected_devices)
                    self.repo.insert_event(
                        event_id=str(uuid.uuid4()),
                        network_id=candidate.network_ids[0] if candidate.network_ids else None,
                        ieee_address=None,
                        event_type="incident_updated",
                        severity=candidate.severity.value,
                        title=f"Incident updated: {candidate.title}",
                        summary=candidate.summary,
                        incident_id=existing["id"],
                    )
                    events.append("incident_updated")
                elif existing["lifecycle_state"] != IncidentLifecycle.open.value:
                    self.repo.update_incident(
                        incident_id=existing["id"],
                        lifecycle_state=IncidentLifecycle.open.value,
                        resolved_at=None,
                    )
                    events.append("incident_updated")
            else:
                incident_id = f"inc-{uuid.uuid4().hex[:12]}"
                ts = utc_now_iso()
                self.repo.insert_incident(
                    incident_id=incident_id,
                    dedup_key=candidate.dedup_key,
                    incident_type=candidate.incident_type.value,
                    lifecycle_state=IncidentLifecycle.open.value,
                    severity=candidate.severity.value,
                    scope=candidate.scope.value,
                    confidence=candidate.confidence.value,
                    title=candidate.title,
                    summary=candidate.summary,
                    explanation=candidate.explanation,
                    evidence=candidate.evidence,
                    counter_evidence=candidate.counter_evidence,
                    limitations=candidate.limitations,
                    opened_at=ts,
                    updated_at=ts,
                )
                self.repo.replace_incident_devices(incident_id, candidate.affected_devices)
                self.repo.insert_event(
                    event_id=str(uuid.uuid4()),
                    network_id=candidate.network_ids[0] if candidate.network_ids else None,
                    ieee_address=None,
                    event_type="incident_opened",
                    severity=candidate.severity.value,
                    title=f"Incident opened: {candidate.title}",
                    summary=candidate.summary,
                    incident_id=incident_id,
                )
                events.append("incident_opened")

        self._resolve_stale(active_keys, now, events)
        if events:
            events.append("incidents_updated")
        return events

    def _resolve_stale(
        self, active_keys: set[str], now: datetime, events: list[str]
    ) -> None:
        cfg = self.config.diagnostics
        watch_delta = timedelta(minutes=cfg.incident_watch_window_minutes)
        grace_delta = timedelta(minutes=cfg.incident_resolution_grace_minutes)

        for row in self.repo.list_active_incidents():
            dedup_key = row.get("dedup_key")
            if dedup_key and dedup_key in active_keys:
                if row["lifecycle_state"] == IncidentLifecycle.watching.value:
                    self.repo.update_incident(
                        incident_id=row["id"],
                        lifecycle_state=IncidentLifecycle.open.value,
                        resolved_at=None,
                    )
                continue

            updated_at = self._parse_ts(row["updated_at"])
            if not updated_at:
                continue

            if row["lifecycle_state"] == IncidentLifecycle.open.value:
                self.repo.update_incident(
                    incident_id=row["id"],
                    lifecycle_state=IncidentLifecycle.watching.value,
                )
                self.repo.insert_event(
                    event_id=str(uuid.uuid4()),
                    network_id=None,
                    ieee_address=None,
                    event_type="incident_updated",
                    severity="watch",
                    title=f"Incident watching: {row['title']}",
                    summary="Underlying signal cleared; incident is being watched.",
                    incident_id=row["id"],
                )
                events.append("incident_updated")
                continue

            if row["lifecycle_state"] == IncidentLifecycle.watching.value:
                if now - updated_at >= watch_delta + grace_delta:
                    self.repo.update_incident(
                        incident_id=row["id"],
                        lifecycle_state=IncidentLifecycle.resolved.value,
                        resolved_at=utc_now_iso(),
                    )
                    self.repo.insert_event(
                        event_id=str(uuid.uuid4()),
                        network_id=None,
                        ieee_address=None,
                        event_type="incident_resolved",
                        severity="healthy",
                        title=f"Incident resolved: {row['title']}",
                        summary="Underlying signals cleared and watch window expired.",
                        incident_id=row["id"],
                    )
                    events.append("incident_resolved")

    def _needs_update(self, existing: dict, candidate: IncidentCandidate) -> bool:
        payload = {
            "summary": candidate.summary,
            "severity": candidate.severity.value,
            "evidence": candidate.evidence,
        }
        previous = {
            "summary": existing.get("summary"),
            "severity": existing.get("severity"),
            "evidence": json.loads(existing.get("evidence_json") or "[]"),
        }
        return json.dumps(payload, sort_keys=True) != json.dumps(previous, sort_keys=True)

    @staticmethod
    def _parse_ts(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
