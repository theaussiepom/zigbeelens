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
    ActivePendingProvider,
    StorageMaintenanceResult,
    affected_invalidation_events,
    maintenance_event_payload,
    persist_next_scheduled_at,
    run_storage_maintenance,
)
from zigbeelens.storage.retention_policy import MORE_WORK_CONTINUATION_SECONDS
from zigbeelens.storage.repository import Repository

logger = logging.getLogger(__name__)

OnResult = Callable[[StorageMaintenanceResult], None]
WaitFn = Callable[[threading.Event, float], bool]


def _default_wait(event: threading.Event, timeout: float) -> bool:
    return event.wait(timeout)


class StorageMaintenanceScheduler:
    """Process-local single-flight periodic maintenance with one joinable worker."""

    def __init__(
        self,
        repo: Repository,
        config: AppConfig,
        *,
        clock: Clock | None = None,
        on_result: OnResult | None = None,
        interval_hours: int | None = None,
        active_pending_provider: ActivePendingProvider | None = None,
        wait_fn: WaitFn | None = None,
        more_work_delay_seconds: float = MORE_WORK_CONTINUATION_SECONDS,
    ) -> None:
        self.repo = repo
        self.config = config
        self.clock = clock or SystemClock()
        self._on_result = on_result
        self._active_pending_provider = active_pending_provider
        self._wait_fn = wait_fn or _default_wait
        self._more_work_delay_seconds = float(max(1.0, more_work_delay_seconds))
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
        self._stopped = True
        self._wake = threading.Event()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._next_delay = self.interval_seconds

    @property
    def running(self) -> bool:
        return not self._stopped

    def start(self) -> None:
        with self._lock:
            if not self._stopped:
                return
            self._stopped = False
            self._stop_event.clear()
            self._wake.clear()
            self._next_delay = self.interval_seconds
            next_at = self._next_iso(self.clock.now(), self._next_delay)
            try:
                persist_next_scheduled_at(self.repo, next_at)
            except Exception:
                logger.error("Failed to persist next_scheduled_at at scheduler start")
            self._thread = threading.Thread(
                target=self._worker,
                name="storage-maintenance",
                daemon=False,
            )
            self._thread.start()

    def stop(self, *, wait: bool = True, timeout: float | None = None) -> None:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._idle:
            self._stopped = True
            self._stop_event.set()
            self._wake.set()
            while wait and self._running:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    break
                self._idle.wait(0.05 if remaining is None else min(0.05, remaining))
            thread = self._thread
        if wait and thread is not None and thread.is_alive():
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            thread.join(remaining)
        with self._lock:
            if self._thread is not None and not self._thread.is_alive():
                self._thread = None

    def run_once(
        self, *, now: datetime | None = None, dry_run: bool = False
    ) -> StorageMaintenanceResult | None:
        with self._idle:
            if self._running:
                self._coalesce = True
                return None
            self._running = True
        return self._run_claimed(now=now, dry_run=dry_run, reschedule=False)

    def trigger(self) -> None:
        """Coalesce a near-term wake without overlapping an in-flight cycle."""
        with self._idle:
            if self._stopped:
                return
            if self._running:
                self._coalesce = True
                return
            self._next_delay = 0.0
            self._wake.set()

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                if self._stopped:
                    break
                delay = self._next_delay
                self._next_delay = self.interval_seconds
            self._wake.clear()
            if delay > 0:
                self._wait_fn(self._wake, delay)
            if self._stop_event.is_set():
                break
            with self._idle:
                if self._stopped:
                    break
                if self._running:
                    self._coalesce = True
                    continue
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
            next_delay = self.interval_seconds
            next_at = self._next_iso(reference, next_delay)
            result = run_storage_maintenance(
                self.repo,
                self.config,
                reference_now=reference,
                dry_run=dry_run,
                persist_status=not dry_run,
                next_scheduled_at=None if dry_run else next_at,
                active_pending_provider=self._active_pending_provider,
            )
            if result is not None and result.more_work_pending and not dry_run:
                next_delay = self._more_work_delay_seconds
                next_at = self._next_iso(reference, next_delay)
                persist_next_scheduled_at(self.repo, next_at)
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
                if coalesce and not self._stopped:
                    self._next_delay = 0.0
                    self._wake.set()
                elif reschedule and not self._stopped:
                    if result is not None and result.more_work_pending and not dry_run:
                        self._next_delay = self._more_work_delay_seconds
                    else:
                        self._next_delay = self.interval_seconds
                self._idle.notify_all()

    @staticmethod
    def _next_iso(reference: datetime, delay_seconds: float) -> str:
        return (
            (reference + timedelta(seconds=delay_seconds))
            .astimezone(timezone.utc)
            .isoformat()
        )


def publish_maintenance_side_effects(
    result: StorageMaintenanceResult,
    *,
    publish_sync: Callable[[str, dict], None],
    schedule_dashboard: Callable[[], None],
) -> None:
    """Publish safe invalidations after a successful destructive cycle."""
    events = affected_invalidation_events(result)
    if not events:
        return
    for event in events:
        if event == "storage_maintenance_completed":
            publish_sync(event, dict(maintenance_event_payload(result)))
        else:
            publish_sync(event, {"type": event})
    schedule_dashboard()
