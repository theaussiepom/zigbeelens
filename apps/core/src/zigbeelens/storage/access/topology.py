"""Topology snapshot and graph read/write access."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zigbeelens.storage.repository import Repository


class TopologyRepository:
    """Narrow access layer for topology_snapshots, topology_nodes and topology_links."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    def create_topology_snapshot(
        self,
        *,
        snapshot_id: str,
        network_id: str,
        requested_by: str,
        status: str,
        warning_acknowledged: bool = False,
        error: str | None = None,
    ) -> None:
        self._repo.create_topology_snapshot(
            snapshot_id=snapshot_id,
            network_id=network_id,
            requested_by=requested_by,
            status=status,
            warning_acknowledged=warning_acknowledged,
            error=error,
        )

    def update_topology_snapshot(
        self,
        snapshot_id: str,
        *,
        status: str | None = None,
        error: str | None = None,
    ) -> None:
        self._repo.update_topology_snapshot(snapshot_id, status=status, error=error)

    def store_topology_parsed(
        self, snapshot_id: str, network_id: str, parsed: Any, *, status: str
    ) -> None:
        self._repo.store_topology_parsed(snapshot_id, network_id, parsed, status=status)

    def enforce_topology_retention(self, network_id: str, max_snapshots: int) -> int:
        return self._repo.enforce_topology_retention(network_id, max_snapshots)

    def delete_topology_snapshot(self, snapshot_id: str) -> None:
        self._repo.delete_topology_snapshot(snapshot_id)

    def get_latest_topology_snapshot(self, network_id: str) -> dict[str, Any] | None:
        return self._repo.get_latest_topology_snapshot(network_id)

    def get_latest_topology_snapshots_for_networks(self, network_ids):
        return self._repo.get_latest_topology_snapshots_for_networks(network_ids)

    def list_topology_snapshots(self, network_id: str) -> list[dict[str, Any]]:
        return self._repo.list_topology_snapshots(network_id)

    def list_complete_topology_snapshots(
        self, network_id: str, *, limit: int | None = None
    ) -> list[dict[str, Any]]:
        return self._repo.list_complete_topology_snapshots(network_id, limit=limit)

    def get_topology_snapshot(
        self, network_id: str, snapshot_id: str
    ) -> dict[str, Any] | None:
        return self._repo.get_topology_snapshot(network_id, snapshot_id)

    def list_topology_nodes(self, snapshot_id: str) -> list[dict[str, Any]]:
        return self._repo.list_topology_nodes(snapshot_id)

    def list_topology_links(self, snapshot_id: str) -> list[dict[str, Any]]:
        return self._repo.list_topology_links(snapshot_id)

    def list_topology_snapshots_for_networks(self, network_ids):
        return self._repo.list_topology_snapshots_for_networks(network_ids)

    def list_topology_nodes_for_snapshots(self, snapshot_ids):
        return self._repo.list_topology_nodes_for_snapshots(snapshot_ids)

    def list_topology_links_for_snapshots(self, snapshot_ids):
        return self._repo.list_topology_links_for_snapshots(snapshot_ids)

    def list_topology_links_for_device_in_snapshots(self, snapshot_ids, ieee_address: str):
        return self._repo.list_topology_links_for_device_in_snapshots(
            snapshot_ids, ieee_address
        )

    def get_topology_node_name(self, snapshot_id: str, ieee_address: str) -> str | None:
        return self._repo.get_topology_node_name(snapshot_id, ieee_address)

    def get_topology_node(self, snapshot_id: str, ieee_address: str):
        return self._repo.get_topology_node(snapshot_id, ieee_address)

    def list_topology_children(self, snapshot_id: str, router_ieee: str) -> list[str]:
        return self._repo.list_topology_children(snapshot_id, router_ieee)

    def get_topology_parent_router(self, snapshot_id: str, ieee_address: str) -> str | None:
        return self._repo.get_topology_parent_router(snapshot_id, ieee_address)
