"""Periodic storage-maintenance scheduler (Track 6)."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from zigbeelens.config.models import AppConfig
from zigbeelens.diagnostics.clock import Clock, SystemClock
from zigbeelens.storage.maintenance import (
    StorageMaintenanceResult,
    affected_invalidation_events,
    maintenance_event_payload,
    run_storage_maintenance,
)
from zigbeelens.storage.repository import Repository

logger = logging.getLogger(__name__)

OnResult = Callable[[StorageMaintenanceResult], None]


class StorageMaintenanceScheduler:
    """Process-local single-flight periodic maintenance."""

    def __init__(
        self,
        repo: Repository,
        config: AppConfig,
        *,
        clock: Clock | None = None,
        on_result: OnResult | None = None,
        interval_hours: int | None = None,
    ) -> None:
        self.repo = repo
        self.config = config
        self.clock = clock or SystemClock()
        self._on_result = on_result
        hours = (
            interval_hours
            if interval_hours is not None
            else config.storage.maintenance_interval_hours
        )
        self.interval_seconds = float(max(1, hours) * 3600)
        self._lock = threading.Lock()
        self._idle = threading.Condition(self._lock)
        self._running = False
        self._coalesce = False
        self._timer: threading.Timer | None = None
        self._stopped = True
        self._stop_event = threading.Event()

    @property
    def running(self) -> bool:
        return not self._stopped

    def start(self) -> None:
        with self._lock:
            if not self._stopped:
                return
            self._stopped = False
            self._stop_event.clear()
            self._schedule_locked()

    def stop(self, *, wait: bool = True, timeout: float | None = None) -> None:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._idle:
            self._stopped = True
            self._stop_event.set()
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            while wait and self._running:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    break
                self._idle.wait(remaining)

    def run_once(self, *, now: datetime | None = None, dry_run: bool = False) -> StorageMaintenanceResult | None:
        with self._idle:
            if self._running:
                self._coalesce = True
                return None
            self._running = True
        return self._run_claimed(now=now, dry_run=dry_run, reschedule=False)

    def _tick(self) -> None:
        with self._idle:
            if self._stopped:
                return
            if self._running:
                self._coalesce = True
                return
            self._running = True
        self._run_claimed(now=None, dry_run=False, reschedule=True)

    def _run_claimed(
        self,
        *,
        now: datetime | None,
        dry_run: bool,
        reschedule: bool,
    ) -> StorageMaintenanceResult | None:
        result: StorageMaintenanceResult | None = None
        try:
            reference = now or self.clock.now()
            next_at = (
                (reference + timedelta(seconds=self.interval_seconds))
                .astimezone(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
            )
            result = run_storage_maintenance(
                self.repo,
                self.config,
                reference_now=reference,
                dry_run=dry_run,
                persist_status=not dry_run,
                next_scheduled_at=None if dry_run else next_at,
            )
            if self._on_result is not None and result is not None:
                self._on_result(result)
            return result
        except Exception:
            logger.exception("Storage maintenance tick failed")
            return result
        finally:
            with self._idle:
                self._running = False
                coalesce = self._coalesce
                self._coalesce = False
                self._idle.notify_all()
                if coalesce and not self._stopped:
                    # Coalesced trigger: run again promptly without waiting full interval.
                    self._timer = threading.Timer(0.0, self._tick)
                    self._timer.daemon = True
                    self._timer.start()
                elif reschedule and not self._stopped:
                    self._schedule_locked()

    def _schedule_locked(self) -> None:
        self._timer = threading.Timer(self.interval_seconds, self._tick)
        self._timer.daemon = True
        self._timer.start()


def publish_maintenance_side_effects(
    result: StorageMaintenanceResult,
    *,
    publish_sync: Callable[[str, dict], None],
    schedule_dashboard: Callable[[], None],
) -> None:
    """Publish safe invalidations after a successful destructive cycle."""
    if not result.success or result.total_rows_deleted <= 0:
        return
    for event in affected_invalidation_events(result):
        if event == "storage_maintenance_completed":
            publish_sync(event, dict(maintenance_event_payload(result)))
        else:
            publish_sync(event, {"type": event})
    schedule_dashboard()
