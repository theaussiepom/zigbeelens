"""Request-local network evidence capabilities and immutable context (Track 3G).

One NetworkEvidenceContext owns stored facts (and optionally derived evidence)
for one network at one reference_now. Capabilities distinguish loaded-empty
from not-loaded; consumers must not treat a missing capability as "no evidence".

NetworkEvidenceCapability.devices always means the complete factual device
inventory for that network — never a response subject subset.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
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

_CAPABILITY_DEPENDENCIES: Mapping[
    NetworkEvidenceCapability, frozenset[NetworkEvidenceCapability]
] = {
    NetworkEvidenceCapability.passive_hints: frozenset(
        {
            NetworkEvidenceCapability.devices,
            NetworkEvidenceCapability.availability_observations,
            NetworkEvidenceCapability.latest_topology,
        }
    ),
    NetworkEvidenceCapability.shared_availability: frozenset(
        {
            NetworkEvidenceCapability.devices,
            NetworkEvidenceCapability.availability_observations,
        }
    ),
    NetworkEvidenceCapability.model_patterns: frozenset(
        {
            NetworkEvidenceCapability.devices,
            NetworkEvidenceCapability.availability_observations,
        }
    ),
    NetworkEvidenceCapability.router_areas: frozenset(
        {
            NetworkEvidenceCapability.devices,
            NetworkEvidenceCapability.latest_topology,
            NetworkEvidenceCapability.historical_links,
            NetworkEvidenceCapability.last_known_links,
            NetworkEvidenceCapability.passive_hints,
            NetworkEvidenceCapability.ha_areas,
        }
    ),
    NetworkEvidenceCapability.device_stats: frozenset(
        {
            NetworkEvidenceCapability.snapshot_history,
            NetworkEvidenceCapability.availability_observations,
        }
    ),
    NetworkEvidenceCapability.historical_links: frozenset(
        {
            NetworkEvidenceCapability.latest_topology,
            NetworkEvidenceCapability.snapshot_history,
        }
    ),
    NetworkEvidenceCapability.last_known_links: frozenset(
        {
            NetworkEvidenceCapability.latest_topology,
            NetworkEvidenceCapability.snapshot_history,
        }
    ),
    NetworkEvidenceCapability.investigations: frozenset(
        {
            NetworkEvidenceCapability.devices,
            NetworkEvidenceCapability.latest_topology,
            NetworkEvidenceCapability.historical_links,
            NetworkEvidenceCapability.last_known_links,
            NetworkEvidenceCapability.availability_observations,
            NetworkEvidenceCapability.passive_hints,
            NetworkEvidenceCapability.shared_availability,
            NetworkEvidenceCapability.model_patterns,
            NetworkEvidenceCapability.router_areas,
        }
    ),
    NetworkEvidenceCapability.topology_facts: frozenset(
        {
            NetworkEvidenceCapability.latest_topology,
            NetworkEvidenceCapability.historical_links,
            NetworkEvidenceCapability.last_known_links,
            NetworkEvidenceCapability.passive_hints,
        }
    ),
    NetworkEvidenceCapability.coverage: frozenset(
        {
            NetworkEvidenceCapability.devices,
            NetworkEvidenceCapability.latest_topology,
            NetworkEvidenceCapability.earliest_availability,
            NetworkEvidenceCapability.ha_areas,
            NetworkEvidenceCapability.topology_facts,
        }
    ),
}


def expand_requirements(
    requirements: NetworkEvidenceRequirements,
) -> NetworkEvidenceRequirements:
    """Close requirements under capability dependencies before loading."""
    expanded: set[NetworkEvidenceCapability] = set(requirements)
    pending = list(requirements)
    while pending:
        capability = pending.pop()
        for dependency in _CAPABILITY_DEPENDENCIES.get(capability, ()):
            if dependency not in expanded:
                expanded.add(dependency)
                pending.append(dependency)
    return frozenset(expanded)


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
        NetworkEvidenceCapability.availability_observations,
    }
)

DEVICE_COVERAGE_EVIDENCE_REQUIREMENTS: NetworkEvidenceRequirements = frozenset(
    {
        NetworkEvidenceCapability.devices,
        NetworkEvidenceCapability.latest_topology,
        NetworkEvidenceCapability.snapshot_history,
        NetworkEvidenceCapability.earliest_availability,
        NetworkEvidenceCapability.ha_areas,
    }
)

LATEST_TOPOLOGY_REQUIREMENTS: NetworkEvidenceRequirements = frozenset(
    {NetworkEvidenceCapability.latest_topology}
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
    }
)

EVIDENCE_GRAPH_FACTS_REQUIREMENTS: NetworkEvidenceRequirements = frozenset(
    EVIDENCE_GRAPH_REQUIREMENTS
    | {
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


def _copy_device_row(row: DeviceRow) -> DeviceRow:
    return replace(row)


def _copy_network_row(row: NetworkRow) -> NetworkRow:
    return replace(row)


def _freeze_derived(value: Any) -> Any:
    """Defensive copy for context-owned derived evidence."""
    if value is None:
        return None
    if hasattr(value, "model_copy"):
        return value.model_copy(deep=True)
    if isinstance(value, Mapping):
        return MappingProxyType({key: deepcopy(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(deepcopy(item) for item in value)
    return deepcopy(value)


@dataclass(frozen=True)
class NetworkEvidenceContext:
    """Immutable request-local evidence for one network at one reference time."""

    network_id: str
    reference_now: datetime
    loaded_capabilities: frozenset[NetworkEvidenceCapability]
    network_row: NetworkRow | None = None
    # Raw inventory (complete network inventory when devices capability loaded)
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
    # Staleness policy used when topology_facts/coverage were built
    stale_after_hours: int | None = None
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
        stale_after_hours: int | None | object = ...,
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
        if stale_after_hours is not ... and self.stale_after_hours != stale_after_hours:
            raise ValueError(
                f"NetworkEvidenceContext stale_after_hours {self.stale_after_hours!r} "
                f"does not match requested {stale_after_hours!r}"
            )

    def projected_device_rows(self) -> tuple[DeviceRow, ...]:
        """Defensive copies of complete inventory rows."""
        self.require(NetworkEvidenceCapability.devices)
        assert self.device_rows is not None
        return tuple(_copy_device_row(row) for row in self.device_rows)
