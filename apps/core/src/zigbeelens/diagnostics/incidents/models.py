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

    def device_keys(self) -> set[tuple[str, str]]:
        return {(d.network_id, d.ieee_address) for d in self.affected_devices}
