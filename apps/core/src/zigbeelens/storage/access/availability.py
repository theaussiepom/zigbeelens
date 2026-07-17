"""Availability transition read/write access."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zigbeelens.storage.repository import Repository


class AvailabilityRepository:
    """Narrow access layer for availability_changes."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    def insert_availability_change(
        self, network_id: str, ieee_address: str, from_state: str, to_state: str
    ) -> None:
        self._repo.insert_availability_change(network_id, ieee_address, from_state, to_state)

    def count_availability_changes_in_window(
        self, network_id: str, ieee_address: str, window_hours: int
    ) -> int:
        return self._repo.count_availability_changes_in_window(
            network_id, ieee_address, window_hours
        )

    def list_availability_changes(
        self, network_id: str, ieee_address: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        return self._repo.list_availability_changes(network_id, ieee_address, limit)

    def get_earliest_availability_change_at(self, network_id: str) -> str | None:
        return self._repo.get_earliest_availability_change_at(network_id)

    def list_availability_changes_since(
        self, network_id: str, since_iso: str
    ) -> list[dict[str, Any]]:
        return self._repo.list_availability_changes_since(network_id, since_iso)

    def list_availability_changes_for_networks_since(self, network_ids, since_iso: str):
        return self._repo.list_availability_changes_for_networks_since(network_ids, since_iso)

    def get_earliest_availability_change_at_for_networks(self, network_ids):
        return self._repo.get_earliest_availability_change_at_for_networks(network_ids)
