"""Safe storage status projection for API and Settings."""

from __future__ import annotations

from typing import Any

from zigbeelens.app.context import AppContext
from zigbeelens.db.retention_time import parse_retention_instant
from zigbeelens.storage.retention_policy import (
    KNOWN_DELETE_CATEGORIES,
    KNOWN_TIMESTAMP_CATEGORIES,
    KNOWN_UPDATE_CATEGORIES,
    POLICY_VERSION,
    TELEMETRY_CATEGORIES,
    StorageRetentionPolicy,
)

_KNOWN_ERROR_CODES = frozenset(
    {
        "interrupted",
        "database_busy",
        "integrity_check_failed",
        "maintenance_failed",
    }
)
_KNOWN_INTEGRITY_STATUSES = frozenset({"ok", "failed"})
_KNOWN_FAILURE_CATEGORIES = frozenset(
    {
        *(table for table, _column, _pk in TELEMETRY_CATEGORIES),
        "topology_snapshots",
        "topology_count_cap",
        "abandoned_pending_topology",
        "incidents_resolved",
        "reports",
        "foreign_key_check",
        "quick_check",
    }
)


def _optional_nonneg_int(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int or isinstance(value, bool) or value < 0:
        return None
    return value


def _strict_bool(value: Any, *, default: bool = False) -> bool:
    if type(value) is bool:
        return value
    return default


def _category_counts(value: Any, *, allowed: frozenset[str]) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, int] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or key not in allowed:
            continue
        if type(raw) is not int or isinstance(raw, bool) or raw < 0:
            continue
        out[key] = raw
    return out


def _optional_iso_timestamp(value: Any) -> str | None:
    if value is None or not isinstance(value, str):
        return None
    if parse_retention_instant(value) is None:
        return None
    return value


def _check_fact(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"status": None, "checked_at": None, "violation_count": None}
    status = value.get("status")
    if status is not None and status not in _KNOWN_INTEGRITY_STATUSES:
        status = None
    return {
        "status": status,
        "checked_at": _optional_iso_timestamp(value.get("checked_at")),
        "violation_count": _optional_nonneg_int(value.get("violation_count")),
    }


def _optional_error_code(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value not in _KNOWN_ERROR_CODES:
        return None
    return value


def _optional_failure_category(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value not in _KNOWN_FAILURE_CATEGORIES:
        return None
    return value


def build_storage_status(ctx: AppContext) -> dict[str, Any]:
    policy = StorageRetentionPolicy.from_config(ctx.config)
    raw = ctx.repo.maintenance.get_maintenance_setting()
    maint = raw if isinstance(raw, dict) else {}
    footprint = ctx.repo.maintenance.storage_footprint()
    integrity = maint.get("integrity") if isinstance(maint.get("integrity"), dict) else {}
    wal = maint.get("wal_checkpoint") if isinstance(maint.get("wal_checkpoint"), dict) else {}
    return {
        "policy": {
            "policy_version": POLICY_VERSION,
            "telemetry_retention_days": policy.telemetry_retention_days,
            "resolved_incident_retention_days": policy.resolved_incident_retention_days,
            "report_retention_days": policy.report_retention_days,
            "maintenance_interval_hours": policy.maintenance_interval_hours,
            "topology_max_snapshots_per_network": policy.topology_max_snapshots_per_network,
        },
        "maintenance": {
            "running": _strict_bool(maint.get("running"), default=False),
            "last_started_at": _optional_iso_timestamp(maint.get("last_started_at")),
            "last_completed_at": _optional_iso_timestamp(maint.get("last_completed_at")),
            "last_successful_at": _optional_iso_timestamp(maint.get("last_successful_at")),
            "next_scheduled_at": _optional_iso_timestamp(maint.get("next_scheduled_at")),
            "last_error_code": _optional_error_code(maint.get("last_error_code")),
            "failure_category": _optional_failure_category(
                maint.get("failure_category")
            ),
            "total_rows_deleted": (
                None
                if "total_rows_deleted" not in maint
                else _optional_nonneg_int(maint.get("total_rows_deleted"))
            ),
            "rows_deleted_by_category": _category_counts(
                maint.get("rows_deleted_by_category"),
                allowed=KNOWN_DELETE_CATEGORIES,
            ),
            "rows_updated_by_category": _category_counts(
                maint.get("rows_updated_by_category"),
                allowed=KNOWN_UPDATE_CATEGORIES,
            ),
            "malformed_timestamps_by_category": _category_counts(
                maint.get("malformed_timestamps_by_category"),
                allowed=KNOWN_TIMESTAMP_CATEGORIES,
            ),
            "future_timestamps_by_category": _category_counts(
                maint.get("future_timestamps_by_category"),
                allowed=KNOWN_TIMESTAMP_CATEGORIES,
            ),
            "more_work_pending": _strict_bool(
                maint.get("more_work_pending"), default=False
            ),
            "duration_ms": (
                None if "duration_ms" not in maint else _optional_nonneg_int(maint.get("duration_ms"))
            ),
            "telemetry_cutoff": _optional_iso_timestamp(maint.get("telemetry_cutoff")),
            "resolved_incident_cutoff": _optional_iso_timestamp(
                maint.get("resolved_incident_cutoff")
            ),
            "report_cutoff": _optional_iso_timestamp(maint.get("report_cutoff")),
            "wal_checkpoint": {
                "busy": wal.get("busy") if type(wal.get("busy")) is bool else None,
                "log_frames": _optional_nonneg_int(wal.get("log_frames")),
                "checkpointed_frames": _optional_nonneg_int(wal.get("checkpointed_frames")),
            }
            if wal
            else {},
        },
        "footprint": footprint,
        "integrity": {
            "startup_gates": "quick_and_foreign_keys",
            "quick_check": _check_fact(integrity.get("quick_check")),
            "foreign_key_check": _check_fact(integrity.get("foreign_key_check")),
        },
    }


def build_storage_policy_summary(ctx: AppContext) -> dict[str, Any]:
    status = build_storage_status(ctx)
    return {
        "retention_days": ctx.config.storage.retention_days,
        "telemetry_retention_days": status["policy"]["telemetry_retention_days"],
        "resolved_incident_retention_days": status["policy"][
            "resolved_incident_retention_days"
        ],
        "report_retention_days": status["policy"]["report_retention_days"],
        "maintenance_interval_hours": status["policy"]["maintenance_interval_hours"],
        "last_successful_at": status["maintenance"]["last_successful_at"],
        "database_bytes": status["footprint"].get("database_bytes"),
        "wal_bytes": status["footprint"].get("wal_bytes"),
        "reusable_bytes": status["footprint"].get("reusable_bytes"),
    }
