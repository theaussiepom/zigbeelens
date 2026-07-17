"""Incident read/write access."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zigbeelens.storage.repository import Repository


class IncidentRepository:
    """Narrow access layer for incidents and incident_devices."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    def list_incidents(self, status_filter: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        return self._repo.list_incidents(status_filter=status_filter)

    def list_active_incidents(self) -> list[dict[str, Any]]:
        return self._repo.list_active_incidents()

    def count_incidents(self, query):
        return self._repo.count_incidents(query)

    def list_incidents_page(self, query):
        return self._repo.list_incidents_page(query)

    def get_incident_by_dedup_key(self, dedup_key: str) -> dict[str, Any] | None:
        return self._repo.get_incident_by_dedup_key(dedup_key)

    def insert_incident(
        self,
        *,
        incident_id: str,
        dedup_key: str,
        incident_type: str,
        lifecycle_state: str,
        severity: str,
        scope: str,
        confidence: str,
        title: str,
        summary: str,
        explanation: str,
        evidence: list[str],
        counter_evidence: list[str],
        limitations: list[str],
        opened_at: str,
        updated_at: str,
    ) -> None:
        self._repo.insert_incident(
            incident_id=incident_id,
            dedup_key=dedup_key,
            incident_type=incident_type,
            lifecycle_state=lifecycle_state,
            severity=severity,
            scope=scope,
            confidence=confidence,
            title=title,
            summary=summary,
            explanation=explanation,
            evidence=evidence,
            counter_evidence=counter_evidence,
            limitations=limitations,
            opened_at=opened_at,
            updated_at=updated_at,
        )

    def update_incident(
        self,
        *,
        incident_id: str,
        lifecycle_state: str | None = None,
        severity: str | None = None,
        scope: str | None = None,
        confidence: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        explanation: str | None = None,
        evidence: list[str] | None = None,
        counter_evidence: list[str] | None = None,
        limitations: list[str] | None = None,
        resolved_at: str | None = ...,  # type: ignore[assignment]
        updated_at: str | None = None,
    ) -> None:
        self._repo.update_incident(
            incident_id=incident_id,
            lifecycle_state=lifecycle_state,
            severity=severity,
            scope=scope,
            confidence=confidence,
            title=title,
            summary=summary,
            explanation=explanation,
            evidence=evidence,
            counter_evidence=counter_evidence,
            limitations=limitations,
            resolved_at=resolved_at,
            updated_at=updated_at,
        )

    def replace_incident_devices(self, incident_id: str, devices: Any) -> None:
        self._repo.replace_incident_devices(incident_id, devices)

    def replace_incident_networks(self, incident_id: str, network_ids: list[str]) -> None:
        self._repo.replace_incident_networks(incident_id, network_ids)

    def replace_incident_devices_and_networks(
        self, incident_id: str, devices: Any, network_ids: list[str]
    ) -> None:
        self._repo.replace_incident_devices_and_networks(
            incident_id, devices, network_ids
        )

    def list_incident_networks(self, incident_id: str) -> list[str]:
        return self._repo.list_incident_networks(incident_id)

    def list_incident_networks_for_incidents(self, incident_ids):
        return self._repo.list_incident_networks_for_incidents(incident_ids)

    def list_incident_rows_for_network_history(self, network_id: str):
        return self._repo.list_incident_rows_for_network_history(network_id)

    def list_incident_rows_for_device_history(self, network_id: str, ieee_address: str):
        return self._repo.list_incident_rows_for_device_history(network_id, ieee_address)

    def list_offline_transitions_since(self, network_id: str, since_iso: str) -> dict[str, str]:
        return self._repo.list_offline_transitions_since(network_id, since_iso)

    def list_incidents_for_device(self, network_id: str, ieee_address: str) -> list[str]:
        return self._repo.list_incidents_for_device(network_id, ieee_address)

    def list_incident_ids_for_devices(
        self,
        device_keys,
        *,
        status_filter: tuple[str, ...] = ("open", "watching"),
    ):
        return self._repo.list_incident_ids_for_devices(
            device_keys, status_filter=status_filter
        )

    def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        return self._repo.get_incident(incident_id)

    def list_incident_devices(self, incident_id: str) -> list[dict[str, str]]:
        return self._repo.list_incident_devices(incident_id)

    def list_incident_devices_for_incidents(self, incident_ids):
        return self._repo.list_incident_devices_for_incidents(incident_ids)

    def list_active_incident_device_addresses(self, network_id: str) -> list[str]:
        return self._repo.list_active_incident_device_addresses(network_id)
