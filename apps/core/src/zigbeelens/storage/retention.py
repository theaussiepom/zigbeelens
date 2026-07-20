"""Storage retention entrypoints (Track 6 policy-aware).

Historical bootstrap helper retained for compatibility. Prefer
``run_storage_maintenance`` once the Track 6 executor is wired.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from zigbeelens.config.models import StorageConfig
from zigbeelens.storage.retention_policy import (
    StorageRetentionPolicy,
    TELEMETRY_CATEGORIES,
    build_maintenance_plan,
)
from zigbeelens.storage.repository import Repository

logger = logging.getLogger(__name__)


def enforce_storage_retention(repo: Repository, retention_days: int) -> dict[str, int]:
    """Delete telemetry older than *retention_days*.

    Compatibility wrapper used by bootstrap before the full Track 6 executor.
    Does not delete reports or resolved incidents (those require explicit
    StorageRetentionPolicy fields).
    """
    if retention_days < 1:
        return {}
    policy = StorageRetentionPolicy.from_storage(
        StorageConfig(path=str(repo.db.path), retention_days=retention_days),
        topology_max_snapshots_per_network=30,
    )
    plan = build_maintenance_plan(policy, datetime.now(timezone.utc))
    cutoff = plan.cutoffs.telemetry_iso()
    counts = repo.purge_collected_data_before(cutoff)
    total = sum(counts.values())
    if total:
        logger.info(
            "Storage retention (telemetry %d days): purged %d rows (%s)",
            retention_days,
            total,
            ", ".join(f"{name}={count}" for name, count in sorted(counts.items()) if count),
        )
    return counts


def preview_storage_retention(
    repo: Repository,
    policy: StorageRetentionPolicy,
    *,
    reference_now: datetime | None = None,
) -> dict[str, int]:
    """Return eligible delete counts for *policy* without mutating data."""
    now = reference_now or datetime.now(timezone.utc)
    plan = build_maintenance_plan(policy, now, dry_run=True)
    preview = repo.maintenance.preview_retention(plan)
    out = {name: item.eligible for name, item in preview.by_category.items()}
    out["topology_count_cap"] = preview.topology_count_cap_candidates
    out["abandoned_pending_topology"] = preview.abandoned_pending_topology
    # Ensure telemetry category keys are always present for callers.
    for table, _column, _pk in TELEMETRY_CATEGORIES:
        out.setdefault(table, 0)
    return out
