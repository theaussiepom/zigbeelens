"""Device inventory and current-state read/write access."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zigbeelens.storage.repository import DeviceRow

if TYPE_CHECKING:
    from zigbeelens.storage.repository import Repository


class DeviceRepository:
    """Narrow access layer for devices and device_current_state."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    def upsert_device(
        self,
        *,
        network_id: str,
        ieee_address: str,
        friendly_name: str,
        device_type: str,
        power_source: str,
        manufacturer: str | None = None,
        model: str | None = None,
        interview_state: str = "unknown",
    ) -> None:
        self._repo.upsert_device(
            network_id=network_id,
            ieee_address=ieee_address,
            friendly_name=friendly_name,
            device_type=device_type,
            power_source=power_source,
            manufacturer=manufacturer,
            model=model,
            interview_state=interview_state,
        )

    def ensure_device_current_state(self, network_id: str, ieee_address: str) -> None:
        self._repo.ensure_device_current_state(network_id, ieee_address)

    def update_device_current_state(
        self,
        *,
        network_id: str,
        ieee_address: str,
        availability: str | None = None,
        last_seen: str | None = None,
        last_payload_at: str | None = None,
        linkquality: int | None = None,
        battery: int | None = None,
    ) -> None:
        self._repo.update_device_current_state(
            network_id=network_id,
            ieee_address=ieee_address,
            availability=availability,
            last_seen=last_seen,
            last_payload_at=last_payload_at,
            linkquality=linkquality,
            battery=battery,
        )

    def get_device_availability(self, network_id: str, ieee_address: str) -> str | None:
        return self._repo.get_device_availability(network_id, ieee_address)

    def insert_device_snapshot(
        self,
        *,
        network_id: str,
        ieee_address: str,
        availability: str | None,
        last_seen: str | None,
        last_payload_at: str | None,
        linkquality: int | None,
        battery: int | None,
        payload_json: str | None,
    ) -> None:
        self._repo.insert_device_snapshot(
            network_id=network_id,
            ieee_address=ieee_address,
            availability=availability,
            last_seen=last_seen,
            last_payload_at=last_payload_at,
            linkquality=linkquality,
            battery=battery,
            payload_json=payload_json,
        )

    def get_devices_by_friendly_name_in_network(
        self, network_id: str, friendly_name: str
    ) -> list[DeviceRow]:
        return self._repo.get_devices_by_friendly_name_in_network(network_id, friendly_name)

    def list_devices(self, network_id: str | None = None) -> list[DeviceRow]:
        return self._repo.list_devices(network_id)

    def get_device(self, network_id: str, ieee_address: str) -> DeviceRow | None:
        return self._repo.get_device(network_id, ieee_address)

    def get_devices_by_friendly_name(self, friendly_name: str) -> list[DeviceRow]:
        return self._repo.get_devices_by_friendly_name(friendly_name)

    def find_devices_by_ieee(self, ieee_address: str) -> list[DeviceRow]:
        return self._repo.find_devices_by_ieee(ieee_address)

    def get_device_by_friendly_name(
        self, network_id: str, friendly_name: str
    ) -> DeviceRow | None:
        return self._repo.get_device_by_friendly_name(network_id, friendly_name)

    def count_devices(self) -> int:
        return self._repo.count_devices()

    def count_devices_for_network(self, network_id: str) -> int:
        return self._repo.count_devices_for_network(network_id)

    def count_unavailable_for_network(self, network_id: str) -> int:
        return self._repo.count_unavailable_for_network(network_id)
