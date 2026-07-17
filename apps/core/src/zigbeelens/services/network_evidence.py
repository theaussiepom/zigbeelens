"""Request-local network evidence capabilities and immutable context (Track 3G).

One NetworkEvidenceContext owns stored facts (and optionally derived evidence)
for one network at one reference_now. Capabilities distinguish loaded-empty
from not-loaded; consumers must not treat a missing capability as "no evidence".

NetworkEvidenceCapability.devices always means the complete factual device
inventory for that network — never a response subject subset.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, fields, replace
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
    NetworkEvidenceCapability.snapshot_history: frozenset(
        {
            NetworkEvidenceCapability.latest_topology,
            NetworkEvidenceCapability.devices,
            NetworkEvidenceCapability.earliest_availability,
        }
    ),
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


def require_mapped_network_evidence_context(
    contexts: Mapping[str, NetworkEvidenceContext],
    network_id: str,
) -> NetworkEvidenceContext:
    """Return the context for ``network_id`` from an explicitly supplied mapping.

    A supplied mapping is authoritative: a missing key is an error, never a
    signal to fall back to repository-owned construction.
    """
    try:
        return contexts[network_id]
    except KeyError as exc:
        raise ValueError(
            f"network_evidence_contexts has no entry for network_id {network_id!r}"
        ) from exc


def _freeze_row(row: Mapping[str, Any] | dict[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({key: _deep_freeze(value) for key, value in dict(row).items()})


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


def _deep_freeze(value: Any) -> Any:
    """Recursively freeze plain evidence structures for request-local safety."""
    if value is None or isinstance(value, (str, bytes, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_deep_freeze(item) for item in value)
    if hasattr(value, "model_copy"):
        # Keep a deep private copy; accessors project defensive copies.
        return value.model_copy(deep=True)
    if dataclasses_is_dataclass(value):
        return replace(value)
    return deepcopy(value)


def dataclasses_is_dataclass(value: Any) -> bool:
    from dataclasses import is_dataclass

    return is_dataclass(value) and not isinstance(value, type)


@dataclass(frozen=True)
class _OwnedDeviceRow:
    """Context-owned immutable device inventory row."""

    network_id: str
    ieee_address: str
    friendly_name: str
    device_type: str
    power_source: str
    manufacturer: str | None
    model: str | None
    interview_state: str
    availability: str = "unknown"
    last_seen: str | None = None
    last_payload_at: str | None = None
    linkquality: int | None = None
    battery: int | None = None

    def as_device_row(self) -> DeviceRow:
        return DeviceRow(
            network_id=self.network_id,
            ieee_address=self.ieee_address,
            friendly_name=self.friendly_name,
            device_type=self.device_type,
            power_source=self.power_source,
            manufacturer=self.manufacturer,
            model=self.model,
            interview_state=self.interview_state,
            availability=self.availability,
            last_seen=self.last_seen,
            last_payload_at=self.last_payload_at,
            linkquality=self.linkquality,
            battery=self.battery,
        )


@dataclass(frozen=True)
class _OwnedNetworkRow:
    """Context-owned immutable network row."""

    id: str
    name: str
    base_topic: str
    bridge_state: str

    def as_network_row(self) -> NetworkRow:
        return NetworkRow(
            id=self.id,
            name=self.name,
            base_topic=self.base_topic,
            bridge_state=self.bridge_state,
        )


def _own_device_row(row: DeviceRow) -> _OwnedDeviceRow:
    return _OwnedDeviceRow(
        **{f.name: getattr(row, f.name) for f in fields(DeviceRow)}
    )


def _own_network_row(row: NetworkRow) -> _OwnedNetworkRow:
    return _OwnedNetworkRow(**{f.name: getattr(row, f.name) for f in fields(NetworkRow)})


def _copy_device_row(row: DeviceRow | _OwnedDeviceRow) -> DeviceRow:
    if isinstance(row, _OwnedDeviceRow):
        return row.as_device_row()
    return replace(row)


def _copy_network_row(row: NetworkRow | _OwnedNetworkRow) -> NetworkRow:
    if isinstance(row, _OwnedNetworkRow):
        return row.as_network_row()
    return replace(row)


def _freeze_derived(value: Any) -> Any:
    """Defensive copy for context-owned derived evidence."""
    return _deep_freeze(value)


def _unfreeze_for_projection(value: Any) -> Any:
    """Convert frozen storage into ordinary mutable Python containers/DTOs."""
    if value is None or isinstance(value, (str, bytes, int, float, bool)):
        return value
    if isinstance(value, MappingProxyType) or (
        isinstance(value, Mapping) and not isinstance(value, dict)
    ):
        return {key: _unfreeze_for_projection(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_unfreeze_for_projection(item) for item in value]
    if isinstance(value, list):
        return [_unfreeze_for_projection(item) for item in value]
    if isinstance(value, frozenset):
        return {_unfreeze_for_projection(item) for item in value}
    if hasattr(value, "model_copy"):
        return value.model_copy(deep=True)
    if dataclasses_is_dataclass(value):
        return replace(value)
    return deepcopy(value)


def _project_derived(value: Any) -> Any:
    """Defensive projection copy for consumers that need mutable DTOs."""
    return _unfreeze_for_projection(value)


def _normalize_ieee(device_ieee: str) -> str:
    return str(device_ieee or "").strip().lower()


@dataclass(frozen=True)
class NetworkEvidenceContext:
    """Immutable request-local evidence for one network at one reference time."""

    network_id: str
    reference_now: datetime
    loaded_capabilities: frozenset[NetworkEvidenceCapability]
    _network_row: _OwnedNetworkRow | None = field(default=None, repr=False)
    # Raw inventory (complete network inventory when devices capability loaded)
    _device_rows: tuple[_OwnedDeviceRow, ...] | None = field(default=None, repr=False)
    _devices_by_ieee: Mapping[str, _OwnedDeviceRow] | None = field(
        default=None, repr=False
    )
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
    _historical_evidence: Mapping[str, Any] | None = field(default=None, repr=False)
    _last_known_links: Mapping[str, Any] | None = field(default=None, repr=False)
    _snapshot_history_context: Any | None = field(default=None, repr=False)
    _passive_hints: Mapping[str, Any] | None = field(default=None, repr=False)
    _shared_availability: Any | None = field(default=None, repr=False)
    _model_patterns: Any | None = field(default=None, repr=False)
    _router_areas: Any | None = field(default=None, repr=False)
    _device_stats: Mapping[str, Any] | None = field(default=None, repr=False)
    _investigations: Mapping[str, Any] | None = field(default=None, repr=False)
    _network_topology_facts: Any | None = field(default=None, repr=False)
    _network_topology_coverage: Any | None = field(default=None, repr=False)

    @property
    def network_row(self) -> NetworkRow | None:
        if self._network_row is None:
            return None
        return self._network_row.as_network_row()

    @property
    def device_rows(self) -> tuple[DeviceRow, ...] | None:
        if self._device_rows is None:
            return None
        return tuple(row.as_device_row() for row in self._device_rows)

    @property
    def devices_by_ieee(self) -> Mapping[str, DeviceRow] | None:
        if self._devices_by_ieee is None:
            return None
        return MappingProxyType(
            {ieee: row.as_device_row() for ieee, row in self._devices_by_ieee.items()}
        )

    @property
    def historical_evidence(self) -> Mapping[str, Any] | None:
        return _project_derived(self._historical_evidence)

    @property
    def last_known_links(self) -> Mapping[str, Any] | None:
        return _project_derived(self._last_known_links)

    @property
    def snapshot_history_context(self) -> Any | None:
        return _project_derived(self._snapshot_history_context)

    @property
    def passive_hints(self) -> Mapping[str, Any] | None:
        return _project_derived(self._passive_hints)

    @property
    def shared_availability(self) -> Any | None:
        return _project_derived(self._shared_availability)

    @property
    def model_patterns(self) -> Any | None:
        return _project_derived(self._model_patterns)

    @property
    def router_areas(self) -> Any | None:
        return _project_derived(self._router_areas)

    @property
    def device_stats(self) -> Mapping[str, Any] | None:
        return _project_derived(self._device_stats)

    @property
    def investigations(self) -> Mapping[str, Any] | None:
        return _project_derived(self._investigations)

    @property
    def network_topology_facts(self) -> Any | None:
        return _project_derived(self._network_topology_facts)

    @property
    def network_topology_coverage(self) -> Any | None:
        return _project_derived(self._network_topology_coverage)

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

    def get_device_row(self, device_ieee: str) -> DeviceRow | None:
        """Return a defensive copy of one complete-inventory row, or None."""
        self.require(NetworkEvidenceCapability.devices)
        assert self._devices_by_ieee is not None
        owned = self._devices_by_ieee.get(_normalize_ieee(device_ieee))
        if owned is None:
            return None
        return owned.as_device_row()

    def projected_device_rows(self) -> tuple[DeviceRow, ...]:
        """Defensive copies of complete inventory rows."""
        self.require(NetworkEvidenceCapability.devices)
        assert self._device_rows is not None
        return tuple(row.as_device_row() for row in self._device_rows)


def build_network_evidence_context(
    *,
    network_id: str,
    reference_now: datetime,
    loaded_capabilities: frozenset[NetworkEvidenceCapability],
    network_row: NetworkRow | None = None,
    device_rows: tuple[DeviceRow, ...] | None = None,
    topology_snapshots: tuple[Mapping[str, Any], ...] | None = None,
    complete_topology_snapshots: tuple[Mapping[str, Any], ...] | None = None,
    latest_usable_snapshot: Mapping[str, Any] | None = None,
    nodes_by_snapshot_id: Mapping[str, tuple[Mapping[str, Any], ...]] | None = None,
    links_by_snapshot_id: Mapping[str, tuple[Mapping[str, Any], ...]] | None = None,
    latest_nodes: tuple[Mapping[str, Any], ...] | None = None,
    latest_links: tuple[Mapping[str, Any], ...] | None = None,
    availability_changes: tuple[Mapping[str, Any], ...] | None = None,
    earliest_availability_at: str | None = None,
    availability_tracking_enabled: bool | None = None,
    network_has_usable_ha_areas: bool | None = None,
    stale_after_hours: int | None = None,
    historical_evidence: Mapping[str, Any] | None = None,
    last_known_links: Mapping[str, Any] | None = None,
    snapshot_history_context: Any | None = None,
    passive_hints: Mapping[str, Any] | None = None,
    shared_availability: Any | None = None,
    model_patterns: Any | None = None,
    router_areas: Any | None = None,
    device_stats: Mapping[str, Any] | None = None,
    investigations: Mapping[str, Any] | None = None,
    network_topology_facts: Any | None = None,
    network_topology_coverage: Any | None = None,
) -> NetworkEvidenceContext:
    """Construct one NetworkEvidenceContext with owned immutable storage."""
    owned_devices = (
        tuple(_own_device_row(row) for row in device_rows)
        if device_rows is not None
        else None
    )
    devices_by_ieee = (
        MappingProxyType(
            {row.ieee_address.lower(): row for row in owned_devices}
        )
        if owned_devices is not None
        else None
    )
    return NetworkEvidenceContext(
        network_id=network_id,
        reference_now=reference_now,
        loaded_capabilities=loaded_capabilities,
        _network_row=_own_network_row(network_row) if network_row is not None else None,
        _device_rows=owned_devices,
        _devices_by_ieee=devices_by_ieee,
        topology_snapshots=topology_snapshots,
        complete_topology_snapshots=complete_topology_snapshots,
        latest_usable_snapshot=latest_usable_snapshot,
        nodes_by_snapshot_id=nodes_by_snapshot_id,
        links_by_snapshot_id=links_by_snapshot_id,
        latest_nodes=latest_nodes,
        latest_links=latest_links,
        availability_changes=availability_changes,
        earliest_availability_at=earliest_availability_at,
        availability_tracking_enabled=availability_tracking_enabled,
        network_has_usable_ha_areas=network_has_usable_ha_areas,
        stale_after_hours=stale_after_hours,
        _historical_evidence=_freeze_derived(historical_evidence),
        _last_known_links=_freeze_derived(last_known_links),
        _snapshot_history_context=_freeze_derived(snapshot_history_context),
        _passive_hints=_freeze_derived(passive_hints),
        _shared_availability=_freeze_derived(shared_availability),
        _model_patterns=_freeze_derived(model_patterns),
        _router_areas=_freeze_derived(router_areas),
        _device_stats=_freeze_derived(device_stats),
        _investigations=_freeze_derived(investigations),
        _network_topology_facts=_freeze_derived(network_topology_facts),
        _network_topology_coverage=_freeze_derived(network_topology_coverage),
    )
