"""Storage retention enforcement for collected telemetry."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from zigbeelens.storage.repository import Repository

logger = logging.getLogger(__name__)


def enforce_storage_retention(repo: Repository, retention_days: int) -> dict[str, int]:
    """Delete historical rows older than *retention_days*. Returns per-table delete counts."""
    if retention_days < 1:
        return {}

    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).replace(microsecond=0)
    cutoff_iso = cutoff.isoformat()
    counts = repo.purge_collected_data_before(cutoff_iso)
    total = sum(counts.values())
    if total:
        logger.info(
            "Storage retention (%d days): purged %d rows (%s)",
            retention_days,
            total,
            ", ".join(f"{name}={count}" for name, count in sorted(counts.items()) if count),
        )
    return counts
