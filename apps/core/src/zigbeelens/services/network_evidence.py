"""Request-local network evidence capabilities and immutable context (Track 3G).

One NetworkEvidenceContext owns stored facts (and optionally derived evidence)
for one network at one reference_now. Capabilities distinguish loaded-empty
from not-loaded; consumers must not treat a missing capability as "no evidence".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from zigbeelens.storage.repository import DeviceRow, NetworkRow


class NetworkEvidenceCapabilityError(LookupError):
    """Raised when a consumer asks for a capability that was not loaded."""


class NetworkEvidenceCapability(str, Enum):
    """Evidence facets that may be loaded into a NetworkEvidenceContext."""

    devices = "devices"
    latest_topology = "latest_topology"
    snapshot_history = "snapshot_history"
    historical_links = "historical_links"
    last_known_links = "last_known_links"
    availability_observations = "availability_observations"
    earliest_availability = "earliest_availability"
    ha_areas = "ha_areas"
    passive_hints = "passive_hints"
    shared_availability = "shared_availability"
    model_patterns = "model_patterns"
    router_areas = "router_areas"
    device_stats = "device_stats"
    investigations = "investigations"
    topology_facts = "topology_facts"
    coverage = "coverage"


NetworkEvidenceRequirements = frozenset[NetworkEvidenceCapability]


# Named presets describe evidence needs, not UI products.
DEVICE_STORY_EVIDENCE_REQUIREMENTS: NetworkEvidenceRequirements = frozenset(
    {
        NetworkEvidenceCapability.devices,
        NetworkEvidenceCapability.latest_topology,
        NetworkEvidenceCapability.snapshot_history,
        NetworkEvidenceCapability.historical_links,
        NetworkEvidenceCapability.last_known_links,
        NetworkEvidenceCapability.earliest_availability,
        NetworkEvidenceCapability.ha_areas,
        NetworkEvidenceCapability.model_patterns,
    }
)

EVIDENCE_GRAPH_REQUIREMENTS: NetworkEvidenceRequirements = frozenset(
    {
        NetworkEvidenceCapability.devices,
        NetworkEvidenceCapability.latest_topology,
        NetworkEvidenceCapability.snapshot_history,
        NetworkEvidenceCapability.historical_links,
        NetworkEvidenceCapability.last_known_links,
        NetworkEvidenceCapability.availability_observations,
        NetworkEvidenceCapability.earliest_availability,
        NetworkEvidenceCapability.ha_areas,
        NetworkEvidenceCapability.passive_hints,
        NetworkEvidenceCapability.shared_availability,
        NetworkEvidenceCapability.model_patterns,
        NetworkEvidenceCapability.router_areas,
        NetworkEvidenceCapability.device_stats,
        NetworkEvidenceCapability.investigations,
        NetworkEvidenceCapability.topology_facts,
        NetworkEvidenceCapability.coverage,
    }
)

DASHBOARD_EVIDENCE_REQUIREMENTS: NetworkEvidenceRequirements = frozenset(
    {
        NetworkEvidenceCapability.devices,
        NetworkEvidenceCapability.latest_topology,
        NetworkEvidenceCapability.snapshot_history,
        NetworkEvidenceCapability.historical_links,
        NetworkEvidenceCapability.last_known_links,
        NetworkEvidenceCapability.availability_observations,
        NetworkEvidenceCapability.earliest_availability,
        NetworkEvidenceCapability.ha_areas,
        NetworkEvidenceCapability.passive_hints,
        NetworkEvidenceCapability.shared_availability,
        NetworkEvidenceCapability.model_patterns,
        NetworkEvidenceCapability.router_areas,
        NetworkEvidenceCapability.investigations,
        NetworkEvidenceCapability.topology_facts,
        NetworkEvidenceCapability.coverage,
    }
)

REPORT_EVIDENCE_REQUIREMENTS: NetworkEvidenceRequirements = frozenset(
    DEVICE_STORY_EVIDENCE_REQUIREMENTS
    | {
        NetworkEvidenceCapability.availability_observations,
        NetworkEvidenceCapability.passive_hints,
        NetworkEvidenceCapability.shared_availability,
        NetworkEvidenceCapability.investigations,
        NetworkEvidenceCapability.topology_facts,
        NetworkEvidenceCapability.coverage,
        NetworkEvidenceCapability.router_areas,
    }
)


def union_requirements(
    *groups: NetworkEvidenceRequirements | None,
) -> NetworkEvidenceRequirements:
    merged: set[NetworkEvidenceCapability] = set()
    for group in groups:
        if group:
            merged.update(group)
    return frozenset(merged)


def _freeze_row(row: Mapping[str, Any] | dict[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(row))


def _freeze_rows(
    rows: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None,
) -> tuple[Mapping[str, Any], ...] | None:
    if rows is None:
        return None
    return tuple(_freeze_row(row) for row in rows)


def _freeze_rows_by_key(
    mapping: Mapping[str, list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...]] | None,
) -> Mapping[str, tuple[Mapping[str, Any], ...]] | None:
    if mapping is None:
        return None
    return MappingProxyType(
        {key: tuple(_freeze_row(row) for row in rows) for key, rows in mapping.items()}
    )


@dataclass(frozen=True)
class NetworkEvidenceContext:
    """Immutable request-local evidence for one network at one reference time."""

    network_id: str
    reference_now: datetime
    loaded_capabilities: frozenset[NetworkEvidenceCapability]
    network_row: NetworkRow | None = None
    # Raw inventory
    device_rows: tuple[DeviceRow, ...] | None = None
    devices_by_ieee: Mapping[str, DeviceRow] | None = None
    # Topology raw
    topology_snapshots: tuple[Mapping[str, Any], ...] | None = None
    complete_topology_snapshots: tuple[Mapping[str, Any], ...] | None = None
    latest_usable_snapshot: Mapping[str, Any] | None = None
    nodes_by_snapshot_id: Mapping[str, tuple[Mapping[str, Any], ...]] | None = None
    links_by_snapshot_id: Mapping[str, tuple[Mapping[str, Any], ...]] | None = None
    latest_nodes: tuple[Mapping[str, Any], ...] | None = None
    latest_links: tuple[Mapping[str, Any], ...] | None = None
    # Availability raw
    availability_changes: tuple[Mapping[str, Any], ...] | None = None
    earliest_availability_at: str | None = None
    availability_tracking_enabled: bool | None = None
    network_has_usable_ha_areas: bool | None = None
    # Derived evidence (None means capability not loaded)
    historical_evidence: Mapping[str, Any] | None = None
    last_known_links: Mapping[str, Any] | None = None
    snapshot_history_context: Any | None = None
    passive_hints: Mapping[str, Any] | None = None
    shared_availability: Any | None = None
    model_patterns: Any | None = None
    router_areas: Any | None = None
    device_stats: Mapping[str, Any] | None = None
    investigations: Mapping[str, Any] | None = None
    network_topology_facts: Any | None = None
    network_topology_coverage: Any | None = None

    def has_capability(self, capability: NetworkEvidenceCapability) -> bool:
        return capability in self.loaded_capabilities

    def require(self, capability: NetworkEvidenceCapability) -> None:
        if capability not in self.loaded_capabilities:
            raise NetworkEvidenceCapabilityError(
                f"NetworkEvidenceContext for {self.network_id!r} did not load "
                f"capability {capability.value!r}"
            )

    def require_compatible(
        self,
        *,
        network_id: str,
        reference_now: datetime | None = None,
    ) -> None:
        if self.network_id != network_id:
            raise ValueError(
                f"NetworkEvidenceContext network_id {self.network_id!r} "
                f"does not match requested {network_id!r}"
            )
        if reference_now is not None and self.reference_now != reference_now:
            raise ValueError(
                f"NetworkEvidenceContext reference_now {self.reference_now!r} "
                f"does not match requested {reference_now!r}"
            )
