"""Diagnostic health classification models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class HealthFlag(str, Enum):
    healthy = "healthy"
    unavailable = "unavailable"
    recently_unstable = "recently_unstable"
    weak_link = "weak_link"
    low_battery = "low_battery"
    stale_reporting = "stale_reporting"
    interview_issue = "interview_issue"
    router_risk = "router_risk"
    unknown = "unknown"


class HealthSeverity(str, Enum):
    ok = "ok"
    info = "info"
    watch = "watch"
    incident = "incident"
    unknown = "unknown"


class HealthConfidence(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class NetworkHealthState(str, Enum):
    ok = "ok"
    watch = "watch"
    incident = "incident"
    unknown = "unknown"


class BridgeHealthState(str, Enum):
    online = "online"
    offline = "offline"
    stale = "stale"
    unknown = "unknown"


@dataclass
class HealthResult:
    primary: HealthFlag
    flags: list[HealthFlag] = field(default_factory=list)
    severity: HealthSeverity = HealthSeverity.unknown
    confidence: HealthConfidence = HealthConfidence.low
    summary: str = ""
    evidence: list[str] = field(default_factory=list)
    counter_evidence: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    updated_at: str = ""


@dataclass
class BridgeHealthResult:
    state: BridgeHealthState
    severity: HealthSeverity
    confidence: HealthConfidence
    summary: str
    evidence: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    updated_at: str = ""


@dataclass
class NetworkHealthResult:
    state: NetworkHealthState
    severity: HealthSeverity
    confidence: HealthConfidence
    summary: str
    evidence: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    unavailable_count: int = 0
    recently_unstable_count: int = 0
    router_risk_count: int = 0
    stale_count: int = 0
    weak_link_count: int = 0
    low_battery_count: int = 0
    unknown_count: int = 0
    updated_at: str = ""


@dataclass
class DeviceHealthContext:
    network_id: str
    ieee_address: str
    friendly_name: str
    device_type: str
    power_source: str
    interview_state: str
    availability: str
    last_seen: str | None
    last_payload_at: str | None
    linkquality: int | None
    battery: int | None
    availability_change_count: int = 0
    bridge_online: bool = True
    bridge_state: str = "unknown"
    network_updated_at: str | None = None
    topology_linked_devices: int | None = None
