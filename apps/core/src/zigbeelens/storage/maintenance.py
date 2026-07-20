"""Bounded, crash-safe storage maintenance executor (Track 6)."""

from __future__ import annotations

import logging
import sqlite3
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
ActivePendingProvider = Callable[[], str | None]

_PARTIAL_FAILURE_LOG = (
    "Storage maintenance stopped after a failed batch; committed earlier batches "
    "remain recorded and the failed batch was rolled back."
)
_STATUS_PERSIST_LOG = "Storage maintenance status persistence failed safely"


def _is_database_busy(exc: BaseException) -> bool:
    if isinstance(exc, sqlite3.OperationalError):
        message = str(exc).lower()
        return "locked" in message or "busy" in message
    return False


def _status_payload(
    *,
    running: bool,
    result: StorageMaintenanceResult | None = None,
    next_scheduled_at: str | None = None,
    last_error_code: str | None = None,
    previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    prev = dict(previous or {})
    payload: dict[str, Any] = {
        "policy_version": POLICY_VERSION,
        "running": running,
        "last_started_at": None if result is None else result.started_at,
        "last_completed_at": None if result is None else result.completed_at,
        "last_successful_at": prev.get("last_successful_at"),
        "next_scheduled_at": next_scheduled_at
        if next_scheduled_at is not None
        else prev.get("next_scheduled_at"),
        "last_error_code": last_error_code if result is None else result.error_code,
        "failure_category": None if result is None else result.failure_category,
        "telemetry_cutoff": None if result is None else result.telemetry_cutoff,
        "resolved_incident_cutoff": None if result is None else result.resolved_incident_cutoff,
        "report_cutoff": None if result is None else result.report_cutoff,
        "reference_now": None if result is None else result.reference_now,
        "rows_deleted_by_category": {} if result is None else dict(result.rows_deleted_by_category),
        "rows_updated_by_category": {} if result is None else dict(result.rows_updated_by_category),
        "total_rows_deleted": None if result is None else result.total_rows_deleted,
        "malformed_timestamps_by_category": (
            {} if result is None else dict(result.malformed_timestamps_by_category)
        ),
        "future_timestamps_by_category": (
            {} if result is None else dict(result.future_timestamps_by_category)
        ),
        "more_work_pending": False if result is None else result.more_work_pending,
        "duration_ms": None if result is None else result.duration_ms,
        "wal_checkpoint": {} if result is None else dict(result.wal_checkpoint),
        "integrity": dict(prev.get("integrity") or {}),
    }
    if result is not None:
        integrity = dict(prev.get("integrity") or {})
        integrity.update(result.integrity)
        payload["integrity"] = integrity
    if result is not None and result.success:
        payload["last_successful_at"] = result.completed_at
        payload["last_error_code"] = None
        payload["failure_category"] = None
    return payload


def mark_interrupted_maintenance_status(repo: Repository) -> None:
    """If a prior cycle left running=true, mark it interrupted after restart."""
    current = repo.maintenance.get_maintenance_setting()
    if not current or not current.get("running"):
        return
    current["running"] = False
    if not current.get("last_error_code"):
        current["last_error_code"] = "interrupted"
    try:
        with repo.transaction():
            repo.maintenance.set_maintenance_setting(current)
    except Exception:
        logger.error(_STATUS_PERSIST_LOG)


def persist_next_scheduled_at(repo: Repository, next_scheduled_at: str) -> None:
    """Persist scheduler wake time without starting a maintenance cycle."""
    previous = repo.maintenance.get_maintenance_setting() or {}
    previous["next_scheduled_at"] = next_scheduled_at
    previous["policy_version"] = POLICY_VERSION
    try:
        with repo.transaction():
            repo.maintenance.set_maintenance_setting(previous)
    except Exception:
        logger.error(_STATUS_PERSIST_LOG)


def run_storage_maintenance(
    repo: Repository,
    config: AppConfig,
    *,
    reference_now: datetime | None = None,
    dry_run: bool = False,
    persist_status: bool = True,
    next_scheduled_at: str | None = None,
    active_pending_snapshot_id: str | None = None,
    active_pending_provider: ActivePendingProvider | None = None,
) -> StorageMaintenanceResult:
    """Execute one bounded maintenance cycle.

    Each logical batch commits independently via Repository.transaction().
    Result accounting is updated after every successful commit.
    """
    now = reference_now or datetime.now(timezone.utc)
    exclude: set[str] = set()
    if active_pending_snapshot_id:
        exclude.add(active_pending_snapshot_id)
    if active_pending_provider is not None:
        live = active_pending_provider()
        if live:
            exclude.add(live)
    policy = StorageRetentionPolicy.from_config(config)
    plan = build_maintenance_plan(
        policy,
        now,
        dry_run=dry_run,
        exclude_topology_snapshot_ids=frozenset(exclude),
    )
    started = utc_now_iso()
    t0 = time.monotonic()
    result = StorageMaintenanceResult(
        started_at=started,
        telemetry_cutoff=plan.cutoffs.telemetry_iso(),
        resolved_incident_cutoff=plan.cutoffs.resolved_incident_iso(),
        report_cutoff=plan.cutoffs.report_iso(),
        reference_now=plan.reference_now_iso(),
    )

    previous_status: dict[str, Any] = {}
    if persist_status and not dry_run:
        try:
            previous_status = repo.maintenance.get_maintenance_setting() or {}
            with repo.transaction():
                repo.maintenance.set_maintenance_setting(
                    {
                        **previous_status,
                        "policy_version": POLICY_VERSION,
                        "running": True,
                        "last_started_at": started,
                        "last_error_code": None,
                        "failure_category": None,
                        "telemetry_cutoff": result.telemetry_cutoff,
                        "resolved_incident_cutoff": result.resolved_incident_cutoff,
                        "report_cutoff": result.report_cutoff,
                        "reference_now": result.reference_now,
                        "next_scheduled_at": next_scheduled_at
                        if next_scheduled_at is not None
                        else previous_status.get("next_scheduled_at"),
                    }
                )
        except Exception as exc:
            result.success = False
            result.error_code = "database_busy" if _is_database_busy(exc) else "maintenance_failed"
            result.completed_at = utc_now_iso()
            result.duration_ms = int((time.monotonic() - t0) * 1000)
            logger.error("Storage maintenance failed before deletion; no batches were started.")
            return result

    try:
        preview = repo.maintenance.preview_retention(plan)
        result.malformed_timestamps_by_category = dict(
            preview.malformed_timestamps_by_category
        )
        result.future_timestamps_by_category = dict(preview.future_timestamps_by_category)

        if dry_run:
            result.eligible_deletes_by_category = dict(preview.eligible_deletes_by_category)
            result.eligible_updates_by_category = dict(preview.eligible_updates_by_category)
            result.rows_deleted_by_category = {}
            result.rows_updated_by_category = {}
            result.more_work_pending = preview.more_work_pending
            result.success = True
            result.completed_at = utc_now_iso()
            result.duration_ms = int((time.monotonic() - t0) * 1000)
            return result

        _execute_deletes(repo, plan, result)
        result.more_work_pending = result.more_work_pending or _any_more_work(repo, plan)

        try:
            fk = foreign_key_check(repo.db)
            result.integrity["foreign_key_check"] = {
                "status": "ok" if fk.ok else "failed",
                "checked_at": fk.checked_at,
                "violation_count": fk.violation_count,
            }
        except StorageIntegrityError as exc:
            result.success = False
            result.error_code = "integrity_check_failed"
            result.failure_category = "foreign_key_check"
            result.integrity["foreign_key_check"] = {
                "status": "failed",
                "checked_at": utc_now_iso(),
                "violation_count": exc.violation_count,
            }
            result.more_work_pending = True
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
        result.more_work_pending = True
        logger.error(_PARTIAL_FAILURE_LOG)
        return result
    except Exception as exc:
        result.success = False
        if _is_database_busy(exc):
            result.error_code = "database_busy"
        else:
            result.error_code = result.error_code or "maintenance_failed"
        result.completed_at = utc_now_iso()
        result.duration_ms = int((time.monotonic() - t0) * 1000)
        result.more_work_pending = True
        logger.error(_PARTIAL_FAILURE_LOG)
        return result
    finally:
        if persist_status and not dry_run:
            try:
                previous = repo.maintenance.get_maintenance_setting() or previous_status
                successful_at = previous.get("last_successful_at")
                payload = _status_payload(
                    running=False,
                    result=result,
                    next_scheduled_at=next_scheduled_at,
                    previous=previous,
                )
                if result.success:
                    payload["last_successful_at"] = result.completed_at
                else:
                    payload["last_successful_at"] = successful_at
                with repo.transaction():
                    repo.maintenance.set_maintenance_setting(payload)
            except Exception:
                logger.error(_STATUS_PERSIST_LOG)


def _record_deleted(result: StorageMaintenanceResult, category: str, count: int) -> None:
    if count <= 0:
        return
    result.rows_deleted_by_category[category] = (
        result.rows_deleted_by_category.get(category, 0) + count
    )


def _record_updated(result: StorageMaintenanceResult, category: str, count: int) -> None:
    if count <= 0:
        return
    result.rows_updated_by_category[category] = (
        result.rows_updated_by_category.get(category, 0) + count
    )


def _execute_deletes(
    repo: Repository,
    plan: StorageMaintenancePlan,
    result: StorageMaintenanceResult,
) -> None:
    maint = repo.maintenance
    limit = plan.batch_size
    telemetry_iso = plan.cutoffs.telemetry_iso()
    now_iso = plan.reference_now_iso()
    exclude = plan.exclude_topology_snapshot_ids

    for table, column, pk in TELEMETRY_CATEGORIES:
        if not repo._has_table(table):
            continue
        while True:
            try:
                with repo.transaction():
                    batch = maint.purge_telemetry_batch(
                        table, column, pk, telemetry_iso, limit=limit
                    )
            except Exception:
                result.failure_category = table
                raise
            _record_deleted(result, table, batch)
            if batch < limit:
                break

    while True:
        try:
            with repo.transaction():
                abandoned = maint.terminalize_abandoned_topology_captures(
                    reference_now_iso=now_iso,
                    limit=limit,
                    exclude_ids=exclude,
                )
        except Exception:
            result.failure_category = "abandoned_pending_topology"
            raise
        _record_updated(result, "abandoned_pending_topology", abandoned)
        if abandoned < limit:
            break

    while True:
        try:
            with repo.transaction():
                batch = maint.purge_topology_age_batch(
                    telemetry_iso, limit=limit, exclude_ids=exclude
                )
        except Exception:
            result.failure_category = "topology_snapshots"
            raise
        _record_deleted(result, "topology_snapshots", batch)
        if batch < limit:
            break

    while True:
        try:
            with repo.transaction():
                batch = maint.purge_topology_count_cap_batch(
                    plan.policy.topology_max_snapshots_per_network,
                    telemetry_cutoff_iso=telemetry_iso,
                    reference_now_iso=now_iso,
                    limit=limit,
                    exclude_ids=exclude,
                )
        except Exception:
            result.failure_category = "topology_count_cap"
            raise
        _record_deleted(result, "topology_count_cap", batch)
        if batch < limit:
            break

    resolved_iso = plan.cutoffs.resolved_incident_iso()
    if resolved_iso is not None:
        while True:
            try:
                with repo.transaction():
                    batch = maint.purge_resolved_incident_batch(resolved_iso, limit=limit)
            except Exception:
                result.failure_category = "incidents_resolved"
                raise
            _record_deleted(result, "incidents_resolved", batch)
            if batch < limit:
                break

    report_iso = plan.cutoffs.report_iso()
    if report_iso is not None:
        while True:
            try:
                with repo.transaction():
                    batch = maint.purge_report_batch(report_iso, limit=limit)
            except Exception:
                result.failure_category = "reports"
                raise
            _record_deleted(result, "reports", batch)
            if batch < limit:
                break


def _any_more_work(repo: Repository, plan: StorageMaintenancePlan) -> bool:
    preview = repo.maintenance.preview_retention(plan)
    return preview.total_rows_eligible > 0


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
    deleted = result.rows_deleted_by_category
    updated = result.rows_updated_by_category
    if not result.success:
        return ()
    if result.total_rows_deleted <= 0 and sum(updated.values()) <= 0:
        return ()
    events = ["storage_maintenance_completed"]
    if deleted.get("incidents_resolved", 0) > 0:
        events.append("incidents_updated")
    if deleted.get("reports", 0) > 0:
        events.append("reports_updated")
    if deleted.get("events", 0) > 0:
        events.append("timeline_updated")
    if (
        deleted.get("topology_snapshots", 0) > 0
        or deleted.get("topology_count_cap", 0) > 0
        or updated.get("abandoned_pending_topology", 0) > 0
    ):
        events.append("topology_updated")
    return tuple(events)


def maintenance_event_payload(result: StorageMaintenanceResult) -> Mapping[str, Any]:
    return {
        "type": "storage_maintenance_completed",
        "total_rows_deleted": result.total_rows_deleted,
        "rows_deleted_by_category": dict(result.rows_deleted_by_category),
        "rows_updated_by_category": dict(result.rows_updated_by_category),
        "more_work_pending": result.more_work_pending,
        "duration_ms": result.duration_ms,
    }
