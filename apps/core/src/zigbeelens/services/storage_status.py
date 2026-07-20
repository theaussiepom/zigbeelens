"""Safe storage status projection for API and Settings."""

from __future__ import annotations

from typing import Any

from zigbeelens.app.context import AppContext
from zigbeelens.storage.retention_policy import POLICY_VERSION, StorageRetentionPolicy


def build_storage_status(ctx: AppContext) -> dict[str, Any]:
    policy = StorageRetentionPolicy.from_config(ctx.config)
    maint = ctx.repo.maintenance.get_maintenance_setting() or {}
    footprint = ctx.repo.maintenance.storage_footprint()
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
            "total_rows_deleted": int(maint.get("total_rows_deleted") or 0),
            "more_work_pending": bool(maint.get("more_work_pending", False)),
            "duration_ms": int(maint.get("duration_ms") or 0),
            "telemetry_cutoff": maint.get("telemetry_cutoff"),
            "resolved_incident_cutoff": maint.get("resolved_incident_cutoff"),
            "report_cutoff": maint.get("report_cutoff"),
        },
        "footprint": footprint,
        "integrity": {
            "startup_gates": "quick_and_foreign_keys",
            "last_known_ok": maint.get("last_error_code") != "integrity_check_failed",
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
