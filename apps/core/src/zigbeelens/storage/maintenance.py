"""Bounded, crash-safe storage maintenance executor (Track 6)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from zigbeelens.config.models import AppConfig
from zigbeelens.storage.integrity import StorageIntegrityError, foreign_key_check
from zigbeelens.storage.retention_policy import (
    POLICY_VERSION,
    StorageMaintenancePlan,
    StorageMaintenanceResult,
    StorageRetentionPolicy,
    TELEMETRY_CATEGORIES,
    build_maintenance_plan,
)
from zigbeelens.storage.repository import Repository, utc_now_iso

logger = logging.getLogger(__name__)

OnComplete = Callable[[StorageMaintenanceResult], None]


def _status_payload(
    *,
    running: bool,
    result: StorageMaintenanceResult | None = None,
    next_scheduled_at: str | None = None,
    last_error_code: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "policy_version": POLICY_VERSION,
        "running": running,
        "last_started_at": None if result is None else result.started_at,
        "last_completed_at": None if result is None else result.completed_at,
        "last_successful_at": None,
        "next_scheduled_at": next_scheduled_at,
        "last_error_code": last_error_code if result is None else result.error_code,
        "telemetry_cutoff": None if result is None else result.telemetry_cutoff,
        "resolved_incident_cutoff": None if result is None else result.resolved_incident_cutoff,
        "report_cutoff": None if result is None else result.report_cutoff,
        "rows_deleted_by_category": {} if result is None else dict(result.rows_deleted_by_category),
        "total_rows_deleted": 0 if result is None else result.total_rows_deleted,
        "malformed_timestamps_by_category": (
            {} if result is None else dict(result.malformed_timestamps_by_category)
        ),
        "future_timestamps_by_category": (
            {} if result is None else dict(result.future_timestamps_by_category)
        ),
        "more_work_pending": False if result is None else result.more_work_pending,
        "duration_ms": 0 if result is None else result.duration_ms,
        "wal_checkpoint": {} if result is None else dict(result.wal_checkpoint),
    }
    if result is not None and result.success:
        payload["last_successful_at"] = result.completed_at
        payload["last_error_code"] = None
    return payload


def mark_interrupted_maintenance_status(repo: Repository) -> None:
    """If a prior cycle left running=true, mark it interrupted after restart."""
    current = repo.maintenance.get_maintenance_setting()
    if not current or not current.get("running"):
        return
    current["running"] = False
    if not current.get("last_error_code"):
        current["last_error_code"] = "interrupted"
    with repo.transaction():
        repo.maintenance.set_maintenance_setting(current)


def run_storage_maintenance(
    repo: Repository,
    config: AppConfig,
    *,
    reference_now: datetime | None = None,
    dry_run: bool = False,
    persist_status: bool = True,
    next_scheduled_at: str | None = None,
) -> StorageMaintenanceResult:
    """Execute one bounded maintenance cycle.

    Each logical batch commits independently via Repository.transaction().
    """
    now = reference_now or datetime.now(timezone.utc)
    policy = StorageRetentionPolicy.from_config(config)
    plan = build_maintenance_plan(policy, now, dry_run=dry_run)
    started = utc_now_iso()
    t0 = time.monotonic()
    result = StorageMaintenanceResult(
        started_at=started,
        telemetry_cutoff=plan.cutoffs.telemetry_iso(),
        resolved_incident_cutoff=plan.cutoffs.resolved_incident_iso(),
        report_cutoff=plan.cutoffs.report_iso(),
    )

    if persist_status and not dry_run:
        with repo.transaction():
            previous = repo.maintenance.get_maintenance_setting() or {}
            repo.maintenance.set_maintenance_setting(
                {
                    **previous,
                    "policy_version": POLICY_VERSION,
                    "running": True,
                    "last_started_at": started,
                    "last_error_code": None,
                    "telemetry_cutoff": result.telemetry_cutoff,
                    "resolved_incident_cutoff": result.resolved_incident_cutoff,
                    "report_cutoff": result.report_cutoff,
                    "next_scheduled_at": next_scheduled_at,
                }
            )

    try:
        preview = repo.maintenance.preview_retention(plan)
        result.malformed_timestamps_by_category = {
            name: item.malformed_timestamps
            for name, item in preview.by_category.items()
            if item.malformed_timestamps
        }
        result.future_timestamps_by_category = {
            name: item.future_timestamps
            for name, item in preview.by_category.items()
            if item.future_timestamps
        }

        if dry_run:
            result.rows_deleted_by_category = {
                name: item.eligible for name, item in preview.by_category.items()
            }
            result.rows_deleted_by_category["topology_count_cap"] = (
                preview.topology_count_cap_candidates
            )
            result.rows_deleted_by_category["abandoned_pending_topology"] = (
                preview.abandoned_pending_topology
            )
            result.more_work_pending = preview.more_work_pending
            result.success = True
            result.completed_at = utc_now_iso()
            result.duration_ms = int((time.monotonic() - t0) * 1000)
            return result

        deleted = _execute_deletes(repo, plan)
        result.rows_deleted_by_category = deleted
        result.more_work_pending = _any_more_work(repo, plan)

        try:
            foreign_key_check(repo.db)
        except StorageIntegrityError:
            result.success = False
            result.error_code = "integrity_check_failed"
            raise

        result.wal_checkpoint = _post_maintenance_housekeeping(repo)
        result.success = True
        result.completed_at = utc_now_iso()
        result.duration_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "Storage maintenance completed: deleted=%d duration_ms=%d more_work_pending=%s",
            result.total_rows_deleted,
            result.duration_ms,
            str(result.more_work_pending).lower(),
        )
        return result
    except StorageIntegrityError:
        result.success = False
        result.error_code = result.error_code or "integrity_check_failed"
        result.completed_at = utc_now_iso()
        result.duration_ms = int((time.monotonic() - t0) * 1000)
        logger.error("Storage maintenance failed safely; no active batch was committed.")
        return result
    except Exception:
        result.success = False
        result.error_code = "maintenance_failed"
        result.completed_at = utc_now_iso()
        result.duration_ms = int((time.monotonic() - t0) * 1000)
        logger.error("Storage maintenance failed safely; no active batch was committed.")
        return result
    finally:
        if persist_status and not dry_run:
            previous = repo.maintenance.get_maintenance_setting() or {}
            successful_at = previous.get("last_successful_at")
            payload = _status_payload(
                running=False,
                result=result,
                next_scheduled_at=next_scheduled_at,
            )
            if result.success:
                payload["last_successful_at"] = result.completed_at
            else:
                payload["last_successful_at"] = successful_at
            with repo.transaction():
                repo.maintenance.set_maintenance_setting(payload)


def _execute_deletes(repo: Repository, plan: StorageMaintenancePlan) -> dict[str, int]:
    maint = repo.maintenance
    deleted: dict[str, int] = {}
    limit = plan.batch_size
    telemetry_iso = plan.cutoffs.telemetry_iso()

    for table, column, pk in TELEMETRY_CATEGORIES:
        if not repo._has_table(table):
            deleted[table] = 0
            continue
        total = 0
        while True:
            with repo.transaction():
                batch = maint.purge_telemetry_batch(
                    table, column, pk, telemetry_iso, limit=limit
                )
            total += batch
            if batch < limit:
                break
        deleted[table] = total

    with repo.transaction():
        abandoned = maint.terminalize_abandoned_topology_captures()
    deleted["abandoned_pending_topology"] = abandoned

    topology_age = 0
    while True:
        with repo.transaction():
            batch = maint.purge_topology_age_batch(telemetry_iso, limit=limit)
        topology_age += batch
        if batch < limit:
            break
    deleted["topology_snapshots"] = topology_age

    topology_cap = 0
    while True:
        with repo.transaction():
            batch = maint.purge_topology_count_cap_batch(
                plan.policy.topology_max_snapshots_per_network,
                limit=limit,
            )
        topology_cap += batch
        if batch < limit:
            break
    deleted["topology_count_cap"] = topology_cap

    resolved_iso = plan.cutoffs.resolved_incident_iso()
    resolved = 0
    if resolved_iso is not None:
        while True:
            with repo.transaction():
                batch = maint.purge_resolved_incident_batch(resolved_iso, limit=limit)
            resolved += batch
            if batch < limit:
                break
    deleted["incidents_resolved"] = resolved

    report_iso = plan.cutoffs.report_iso()
    reports = 0
    if report_iso is not None:
        while True:
            with repo.transaction():
                batch = maint.purge_report_batch(report_iso, limit=limit)
            reports += batch
            if batch < limit:
                break
    deleted["reports"] = reports
    return deleted


def _any_more_work(repo: Repository, plan: StorageMaintenancePlan) -> bool:
    preview = repo.maintenance.preview_retention(plan)
    return preview.total_eligible > 0


def _post_maintenance_housekeeping(repo: Repository) -> dict[str, int | bool | None]:
    try:
        repo.db.conn.execute("PRAGMA optimize")
    except Exception:
        pass
    busy: bool | None = None
    log_frames: int | None = None
    checkpointed: int | None = None
    try:
        row = repo.db.conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
        if row is not None:
            # busy, log, checkpointed
            busy = bool(row[0])
            log_frames = int(row[1])
            checkpointed = int(row[2])
    except Exception:
        pass
    return {
        "busy": busy,
        "log_frames": log_frames,
        "checkpointed_frames": checkpointed,
    }


def affected_invalidation_events(result: StorageMaintenanceResult) -> tuple[str, ...]:
    """Safe collection invalidation event names after a successful cycle."""
    if not result.success or result.total_rows_deleted <= 0:
        return ()
    events = ["storage_maintenance_completed"]
    deleted = result.rows_deleted_by_category
    if deleted.get("incidents_resolved", 0) > 0:
        events.append("incidents_collection_updated")
    if deleted.get("reports", 0) > 0:
        events.append("reports_updated")
    if deleted.get("events", 0) > 0 or deleted.get("topology_snapshots", 0) > 0:
        events.append("timeline_updated")
    return tuple(events)


def maintenance_event_payload(result: StorageMaintenanceResult) -> Mapping[str, Any]:
    return {
        "type": "storage_maintenance_completed",
        "total_rows_deleted": result.total_rows_deleted,
        "rows_deleted_by_category": dict(result.rows_deleted_by_category),
        "more_work_pending": result.more_work_pending,
        "duration_ms": result.duration_ms,
    }
