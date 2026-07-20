"""Safe storage status projection for API and Settings."""

from __future__ import annotations

from typing import Any

from zigbeelens.app.context import AppContext
from zigbeelens.storage.retention_policy import POLICY_VERSION, StorageRetentionPolicy


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dict_int(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, int] = {}
    for key, raw in value.items():
        try:
            out[str(key)] = int(raw)
        except (TypeError, ValueError):
            continue
    return out


def _check_fact(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"status": None, "checked_at": None, "violation_count": None}
    return {
        "status": value.get("status"),
        "checked_at": value.get("checked_at"),
        "violation_count": _optional_int(value.get("violation_count")),
    }


def build_storage_status(ctx: AppContext) -> dict[str, Any]:
    policy = StorageRetentionPolicy.from_config(ctx.config)
    maint = ctx.repo.maintenance.get_maintenance_setting() or {}
    footprint = ctx.repo.maintenance.storage_footprint()
    integrity = maint.get("integrity") if isinstance(maint.get("integrity"), dict) else {}
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
            "running": bool(maint.get("running", False)),
            "last_started_at": maint.get("last_started_at"),
            "last_completed_at": maint.get("last_completed_at"),
            "last_successful_at": maint.get("last_successful_at"),
            "next_scheduled_at": maint.get("next_scheduled_at"),
            "last_error_code": maint.get("last_error_code"),
            "failure_category": maint.get("failure_category"),
            "total_rows_deleted": (
                None
                if "total_rows_deleted" not in maint
                else _optional_int(maint.get("total_rows_deleted"))
            ),
            "rows_deleted_by_category": _dict_int(maint.get("rows_deleted_by_category")),
            "rows_updated_by_category": _dict_int(maint.get("rows_updated_by_category")),
            "malformed_timestamps_by_category": _dict_int(
                maint.get("malformed_timestamps_by_category")
            ),
            "future_timestamps_by_category": _dict_int(
                maint.get("future_timestamps_by_category")
            ),
            "more_work_pending": bool(maint.get("more_work_pending", False)),
            "duration_ms": (
                None if "duration_ms" not in maint else _optional_int(maint.get("duration_ms"))
            ),
            "telemetry_cutoff": maint.get("telemetry_cutoff"),
            "resolved_incident_cutoff": maint.get("resolved_incident_cutoff"),
            "report_cutoff": maint.get("report_cutoff"),
            "wal_checkpoint": (
                maint.get("wal_checkpoint")
                if isinstance(maint.get("wal_checkpoint"), dict)
                else {}
            ),
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
