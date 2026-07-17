"""Incident lifecycle: deduplication, open/update/resolve."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from zigbeelens.config.models import AppConfig
from zigbeelens.diagnostics.clock import utc_iso
from zigbeelens.diagnostics.incidents.models import IncidentCandidate, IncidentLifecycle
from zigbeelens.storage.repository import Repository


class IncidentLifecycleManager:
    def __init__(self, config: AppConfig, repo: Repository) -> None:
        self.config = config
        self.repo = repo

    @staticmethod
    def _iso(now: datetime) -> str:
        return utc_iso(now)

    def sync(self, candidates: list[IncidentCandidate], now: datetime | None = None) -> list[str]:
        now = now or datetime.now(timezone.utc)
        ts = self._iso(now)
        events: list[str] = []
        active_keys = {c.dedup_key for c in candidates if c.active}

        for candidate in candidates:
            if not candidate.active:
                continue
            existing = self.repo.incidents.get_incident_by_dedup_key(candidate.dedup_key)
            if existing:
                if existing["lifecycle_state"] != IncidentLifecycle.open.value:
                    self._reopen_incident(existing, candidate, ts, events)
                elif self._needs_update(existing, candidate):
                    self.repo.incidents.update_incident(
                        incident_id=existing["id"],
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
                        resolved_at=None,
                        updated_at=ts,
                    )
                    self.repo.incidents.replace_incident_devices_and_networks(
                        existing["id"],
                        candidate.affected_devices,
                        list(candidate.network_ids),
                    )
                    self.repo.insert_event(
                        event_id=str(uuid.uuid4()),
                        network_id=candidate.network_ids[0] if candidate.network_ids else None,
                        ieee_address=None,
                        event_type="incident_updated",
                        severity=candidate.severity.value,
                        title=f"Incident updated: {candidate.title}",
                        summary=candidate.summary,
                        incident_id=existing["id"],
                        occurred_at=ts,
                    )
                    events.append("incident_updated")
            else:
                incident_id = f"inc-{uuid.uuid4().hex[:12]}"
                self.repo.incidents.insert_incident(
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
                self.repo.incidents.replace_incident_devices_and_networks(
                    incident_id,
                    candidate.affected_devices,
                    list(candidate.network_ids),
                )
                self.repo.insert_event(
                    event_id=str(uuid.uuid4()),
                    network_id=candidate.network_ids[0] if candidate.network_ids else None,
                    ieee_address=None,
                    event_type="incident_opened",
                    severity=candidate.severity.value,
                    title=f"Incident opened: {candidate.title}",
                    summary=candidate.summary,
                    incident_id=incident_id,
                    occurred_at=ts,
                )
                events.append("incident_opened")

        candidates_by_key = {c.dedup_key: c for c in candidates if c.active}
        self._resolve_stale(active_keys, candidates_by_key, now, events)
        if events:
            events.append("incidents_updated")
        return events

    def _resolve_stale(
        self,
        active_keys: set[str],
        candidates_by_key: dict[str, IncidentCandidate],
        now: datetime,
        events: list[str],
    ) -> None:
        cfg = self.config.diagnostics
        watch_delta = timedelta(minutes=cfg.incident_watch_window_minutes)
        grace_delta = timedelta(minutes=cfg.incident_resolution_grace_minutes)

        for row in self.repo.incidents.list_active_incidents():
            dedup_key = row.get("dedup_key")
            if dedup_key and dedup_key in active_keys:
                if row["lifecycle_state"] == IncidentLifecycle.watching.value:
                    candidate = candidates_by_key[dedup_key]
                    self._reopen_incident(row, candidate, self._iso(now), events)
                continue

            updated_at = self._parse_ts(row["updated_at"])
            if not updated_at:
                continue

            if row["lifecycle_state"] == IncidentLifecycle.open.value:
                self.repo.incidents.update_incident(
                    incident_id=row["id"],
                    lifecycle_state=IncidentLifecycle.watching.value,
                    updated_at=self._iso(now),
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
                    occurred_at=self._iso(now),
                )
                events.append("incident_updated")
                continue

            if row["lifecycle_state"] == IncidentLifecycle.watching.value:
                if now - updated_at >= watch_delta + grace_delta:
                    resolved_at = self._iso(now)
                    self.repo.incidents.update_incident(
                        incident_id=row["id"],
                        lifecycle_state=IncidentLifecycle.resolved.value,
                        resolved_at=resolved_at,
                        updated_at=resolved_at,
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
                        occurred_at=resolved_at,
                    )
                    events.append("incident_resolved")


    def _reopen_incident(
        self, existing: dict, candidate: IncidentCandidate, ts: str, events: list[str]
    ) -> None:
        self.repo.incidents.update_incident(
            incident_id=existing["id"],
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
            resolved_at=None,
            updated_at=ts,
        )
        self.repo.incidents.replace_incident_devices_and_networks(
            existing["id"],
            candidate.affected_devices,
            list(candidate.network_ids),
        )
        self.repo.insert_event(
            event_id=str(uuid.uuid4()),
            network_id=candidate.network_ids[0] if candidate.network_ids else None,
            ieee_address=None,
            event_type="incident_updated",
            severity=candidate.severity.value,
            title=f"Incident reopened: {candidate.title}",
            summary="Underlying signal returned during the watch period.",
            incident_id=existing["id"],
            occurred_at=ts,
        )
        events.append("incident_updated")

    def _needs_update(self, existing: dict, candidate: IncidentCandidate) -> bool:
        existing_devices = {
            (row["network_id"], row["ieee_address"], row.get("role") or "affected")
            for row in self.repo.incidents.list_incident_devices(existing["id"])
        }
        existing_networks = tuple(
            self.repo.incidents.list_incident_networks(existing["id"])
        )
        payload = {
            "title": candidate.title,
            "summary": candidate.summary,
            "severity": candidate.severity.value,
            "scope": candidate.scope.value,
            "confidence": candidate.confidence.value,
            "explanation": candidate.explanation,
            "evidence": candidate.evidence,
            "counter_evidence": candidate.counter_evidence,
            "limitations": candidate.limitations,
            "affected_devices": sorted(candidate.device_role_keys()),
            "network_ids": sorted(set(candidate.network_ids)),
        }
        previous = {
            "title": existing.get("title"),
            "summary": existing.get("summary"),
            "severity": existing.get("severity"),
            "scope": existing.get("scope"),
            "confidence": existing.get("confidence"),
            "explanation": existing.get("explanation"),
            "evidence": json.loads(existing.get("evidence_json") or "[]"),
            "counter_evidence": json.loads(existing.get("counter_evidence_json") or "[]"),
            "limitations": json.loads(existing.get("limitations_json") or "[]"),
            "affected_devices": sorted(existing_devices),
            "network_ids": sorted(set(existing_networks)),
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
