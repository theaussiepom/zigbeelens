"""Shared read-only signals for Zigbee2MQTT availability tracking coverage."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zigbeelens.storage.repository import Repository


_UNSET = object()


def availability_tracking_enabled_now(
    repo: Repository,
    network_id: str,
    *,
    earliest_availability_at: str | None | object = _UNSET,
) -> bool:
    """Whether usable availability tracking evidence exists for a network.

    Tracking is available when either a recorded availability transition exists
    or at least one device currently reports an explicit online/offline state.
    """
    if earliest_availability_at is _UNSET:
        earliest_availability_at = repo.availability.get_earliest_availability_change_at(
            network_id
        )
    return earliest_availability_at is not None or any(
        row.availability in ("online", "offline")
        for row in repo.list_devices(network_id)
    )
