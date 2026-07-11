"""Network and collector operational read/write access."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from zigbeelens.config.models import NetworkConfig
from zigbeelens.storage.repository import NetworkRow

if TYPE_CHECKING:
    from zigbeelens.storage.repository import Repository


class NetworkRepository:
    """Narrow access layer for networks, bridge snapshots and collector status."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    def sync_networks(self, networks: list[NetworkConfig]) -> None:
        self._repo.sync_networks(networks)

    def list_networks(self) -> list[NetworkRow]:
        return self._repo.list_networks()

    def get_network(self, network_id: str) -> NetworkRow | None:
        return self._repo.get_network(network_id)

    def update_network_bridge_state(self, network_id: str, bridge_state: str) -> None:
        self._repo.update_network_bridge_state(network_id, bridge_state)

    def get_network_last_mqtt_activity_at(self, network_id: str) -> str | None:
        return self._repo.get_network_last_mqtt_activity_at(network_id)

    def insert_bridge_snapshot(
        self,
        *,
        network_id: str,
        bridge_state: str | None,
        coordinator_ieee: str | None = None,
        channel: int | None = None,
        pan_id: str | None = None,
        extended_pan_id: str | None = None,
        payload_json: str | None = None,
    ) -> None:
        self._repo.insert_bridge_snapshot(
            network_id=network_id,
            bridge_state=bridge_state,
            coordinator_ieee=coordinator_ieee,
            channel=channel,
            pan_id=pan_id,
            extended_pan_id=extended_pan_id,
            payload_json=payload_json,
        )

    def get_latest_bridge_snapshot(self, network_id: str) -> dict[str, Any] | None:
        return self._repo.get_latest_bridge_snapshot(network_id)

    def update_collector_status(
        self,
        *,
        enabled: bool,
        connected: bool,
        subscribed_topics_count: int,
        last_message_at: str | None = None,
        last_error: str | None = None,
    ) -> None:
        self._repo.update_collector_status(
            enabled=enabled,
            connected=connected,
            subscribed_topics_count=subscribed_topics_count,
            last_message_at=last_message_at,
            last_error=last_error,
        )

    def get_collector_status(self) -> dict[str, Any] | None:
        return self._repo.get_collector_status()
