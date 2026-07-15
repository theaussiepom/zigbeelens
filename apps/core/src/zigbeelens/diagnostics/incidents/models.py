"""Incident correlation models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from zigbeelens.schemas import Confidence, IncidentScope, Severity


class IncidentType(str, Enum):
    single_device_unavailable = "single_device_unavailable"
    correlated_device_unavailability = "correlated_device_unavailability"
    bridge_offline = "bridge_offline"
    network_wide_instability = "network_wide_instability"
    multi_network_instability = "multi_network_instability"
    router_risk = "router_risk"
    stale_reporting_cluster = "stale_reporting_cluster"
    low_battery_cluster = "low_battery_cluster"
    interview_failure = "interview_failure"
    unknown_pattern = "unknown_pattern"


class IncidentLifecycle(str, Enum):
    open = "open"
    watching = "watching"
    resolved = "resolved"


INCIDENT_PRIORITY: list[IncidentType] = [
    IncidentType.bridge_offline,
    IncidentType.multi_network_instability,
    IncidentType.network_wide_instability,
    IncidentType.correlated_device_unavailability,
    IncidentType.single_device_unavailable,
    IncidentType.router_risk,
    IncidentType.stale_reporting_cluster,
    IncidentType.interview_failure,
    IncidentType.low_battery_cluster,
    IncidentType.unknown_pattern,
]


@dataclass
class AffectedDevice:
    network_id: str
    ieee_address: str
    role: str = "affected"


@dataclass
class IncidentCandidate:
    dedup_key: str
    incident_type: IncidentType
    scope: IncidentScope
    severity: Severity
    confidence: Confidence
    title: str
    summary: str
    explanation: str
    evidence: list[str] = field(default_factory=list)
    counter_evidence: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    affected_devices: list[AffectedDevice] = field(default_factory=list)
    network_ids: list[str] = field(default_factory=list)
    active: bool = True
    priority: int = 100

    def __post_init__(self) -> None:
        self.dedup_key = incident_identity_key(self)

    def device_keys(self) -> set[tuple[str, str]]:
        return {(d.network_id, d.ieee_address) for d in self.affected_devices}

    def device_role_keys(self) -> set[tuple[str, str, str]]:
        return {(d.network_id, d.ieee_address, d.role) for d in self.affected_devices}


def incident_identity_key(candidate: IncidentCandidate) -> str:
    """Return the stable lifecycle identity for an incident candidate.

    Identity rules by IncidentType:
    - bridge_offline: type + network_id
    - multi_network_instability: type + sorted network IDs
    - network_wide_instability: type + network_id
    - correlated_device_unavailability: type + network_id
    - single_device_unavailable: type + network_id + subject IEEE
    - router_risk: type + network_id + router IEEE
    - stale_reporting_cluster: type + network_id
    - low_battery_cluster: type + network_id
    - interview_failure: type + network_id
    - unknown_pattern: type + network_id
    """

    incident_type = candidate.incident_type
    network_ids = sorted(set(candidate.network_ids))
    primary_network = network_ids[0] if network_ids else _network_from_devices(candidate)

    if incident_type is IncidentType.multi_network_instability:
        return f"{incident_type.value}:{','.join(network_ids)}"
    if incident_type in {
        IncidentType.bridge_offline,
        IncidentType.network_wide_instability,
        IncidentType.correlated_device_unavailability,
        IncidentType.stale_reporting_cluster,
        IncidentType.low_battery_cluster,
        IncidentType.unknown_pattern,
    }:
        return f"{incident_type.value}:{primary_network}"
    if incident_type is IncidentType.single_device_unavailable:
        return f"{incident_type.value}:{primary_network}:{_single_subject(candidate)}"
    if incident_type is IncidentType.router_risk:
        return f"{incident_type.value}:{primary_network}:{_single_subject(candidate)}"
    if incident_type is IncidentType.interview_failure:
        return f"{incident_type.value}:{primary_network}"
    return candidate.dedup_key


def _network_from_devices(candidate: IncidentCandidate) -> str:
    networks = sorted({device.network_id for device in candidate.affected_devices})
    return networks[0] if networks else "unknown"


def _single_subject(candidate: IncidentCandidate) -> str:
    if candidate.affected_devices:
        return sorted(device.ieee_address for device in candidate.affected_devices)[0]
    return "unknown"
