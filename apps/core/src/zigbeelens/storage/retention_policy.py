"""Pure storage retention policy, cutoffs, and ownership matrix (Track 6).

Retention ownership (disposition):

Permanent metadata / identity — never age-purge:
  schema_migrations, settings, networks, devices

Current-state projections — never age-purge:
  device_current_state, collector_status, ha_device_enrichment,
  ha_enrichment_status

Telemetry history — storage.retention_days:
  metric_samples, availability_changes, device_snapshots, bridge_snapshots,
  health_snapshots, events, unresolved_device_messages,
  terminal topology snapshots (+ children)

Incidents:
  open / watching — never age-purge
  resolved — storage.resolved_incident_retention_days (default 90; null = keep)

Reports:
  storage.report_retention_days (default null = until manual delete)

Topology pending captures are not ordinary history; abandoned pending rows are
terminalized before age/count retention applies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Mapping

from zigbeelens.config.models import AppConfig, StorageConfig, TopologyConfig

POLICY_VERSION = 2
MAINTENANCE_BATCH_SIZE = 500
MAINTENANCE_STATUS_KEY = "storage_maintenance_status_v1"
ABANDONED_TOPOLOGY_ERROR = "Topology capture was interrupted before completion"

# Deterministic category order for preview and deletion.
TELEMETRY_CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("unresolved_device_messages", "received_at", "id"),
    ("metric_samples", "sampled_at", "id"),
    ("availability_changes", "changed_at", "id"),
    ("device_snapshots", "captured_at", "id"),
    ("bridge_snapshots", "captured_at", "id"),
    ("health_snapshots", "captured_at", "id"),
    ("events", "occurred_at", "id"),
)

NEVER_AGE_PURGE_TABLES: frozenset[str] = frozenset(
    {
        "schema_migrations",
        "settings",
        "networks",
        "devices",
        "device_current_state",
        "collector_status",
        "ha_device_enrichment",
        "ha_enrichment_status",
    }
)


@dataclass(frozen=True)
class StorageRetentionPolicy:
    telemetry_retention_days: int
    resolved_incident_retention_days: int | None
    report_retention_days: int | None
    maintenance_interval_hours: int
    topology_max_snapshots_per_network: int

    @classmethod
    def from_storage(
        cls,
        storage: StorageConfig,
        *,
        topology_max_snapshots_per_network: int = 30,
    ) -> StorageRetentionPolicy:
        return cls(
            telemetry_retention_days=storage.retention_days,
            resolved_incident_retention_days=storage.resolved_incident_retention_days,
            report_retention_days=storage.report_retention_days,
            maintenance_interval_hours=storage.maintenance_interval_hours,
            topology_max_snapshots_per_network=topology_max_snapshots_per_network,
        )

    @classmethod
    def from_config(cls, config: AppConfig) -> StorageRetentionPolicy:
        topology: TopologyConfig = config.topology
        return cls.from_storage(
            config.storage,
            topology_max_snapshots_per_network=topology.max_snapshots_per_network,
        )


@dataclass(frozen=True)
class StorageRetentionCutoffs:
    telemetry: datetime
    resolved_incident: datetime | None
    report: datetime | None

    def telemetry_iso(self) -> str:
        return _cutoff_iso(self.telemetry)

    def resolved_incident_iso(self) -> str | None:
        return None if self.resolved_incident is None else _cutoff_iso(self.resolved_incident)

    def report_iso(self) -> str | None:
        return None if self.report is None else _cutoff_iso(self.report)


@dataclass(frozen=True)
class CategoryEligibility:
    eligible: int = 0
    malformed_timestamps: int = 0
    future_timestamps: int = 0


@dataclass(frozen=True)
class StorageRetentionPreview:
    cutoffs: StorageRetentionCutoffs
    by_category: Mapping[str, CategoryEligibility]
    topology_count_cap_candidates: int = 0
    abandoned_pending_topology: int = 0
    more_work_pending: bool = False

    @property
    def total_eligible(self) -> int:
        return sum(item.eligible for item in self.by_category.values()) + (
            self.topology_count_cap_candidates + self.abandoned_pending_topology
        )


@dataclass
class StorageMaintenancePlan:
    policy: StorageRetentionPolicy
    cutoffs: StorageRetentionCutoffs
    batch_size: int = MAINTENANCE_BATCH_SIZE
    dry_run: bool = False


@dataclass
class StorageMaintenanceResult:
    policy_version: int = POLICY_VERSION
    success: bool = True
    error_code: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int = 0
    rows_deleted_by_category: dict[str, int] = field(default_factory=dict)
    malformed_timestamps_by_category: dict[str, int] = field(default_factory=dict)
    future_timestamps_by_category: dict[str, int] = field(default_factory=dict)
    more_work_pending: bool = False
    telemetry_cutoff: str | None = None
    resolved_incident_cutoff: str | None = None
    report_cutoff: str | None = None
    wal_checkpoint: dict[str, int | bool | None] = field(default_factory=dict)

    @property
    def total_rows_deleted(self) -> int:
        return sum(self.rows_deleted_by_category.values())


def normalize_reference_now(reference_now: datetime) -> datetime:
    if reference_now.tzinfo is None:
        return reference_now.replace(tzinfo=timezone.utc)
    return reference_now.astimezone(timezone.utc)


def compute_cutoffs(
    policy: StorageRetentionPolicy,
    reference_now: datetime,
) -> StorageRetentionCutoffs:
    now = normalize_reference_now(reference_now).replace(microsecond=0)
    telemetry = now - timedelta(days=policy.telemetry_retention_days)
    resolved = (
        None
        if policy.resolved_incident_retention_days is None
        else now - timedelta(days=policy.resolved_incident_retention_days)
    )
    report = (
        None
        if policy.report_retention_days is None
        else now - timedelta(days=policy.report_retention_days)
    )
    return StorageRetentionCutoffs(
        telemetry=telemetry,
        resolved_incident=resolved,
        report=report,
    )


def build_maintenance_plan(
    policy: StorageRetentionPolicy,
    reference_now: datetime,
    *,
    dry_run: bool = False,
    batch_size: int = MAINTENANCE_BATCH_SIZE,
) -> StorageMaintenancePlan:
    return StorageMaintenancePlan(
        policy=policy,
        cutoffs=compute_cutoffs(policy, reference_now),
        batch_size=batch_size,
        dry_run=dry_run,
    )


def _cutoff_iso(value: datetime) -> str:
    return normalize_reference_now(value).replace(microsecond=0).isoformat()


# Shared SQL fragment: absolute-time comparison via julianday.
# Rows with unparseable timestamps yield NULL julianday and are never eligible.
JD_LT = "julianday({column}) < julianday(?)"
JD_MALFORMED = "({column} IS NOT NULL AND julianday({column}) IS NULL)"
JD_FUTURE = "julianday({column}) > julianday(?)"
