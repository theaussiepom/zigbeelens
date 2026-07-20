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
    maintenance_evidence_changed,
    persist_next_scheduled_at,
    run_storage_maintenance,
)
from zigbeelens.storage.retention_policy import MORE_WORK_CONTINUATION_SECONDS
from zigbeelens.storage.repository import Repository

logger = logging.getLogger(__name__)

OnResult = Callable[[StorageMaintenanceResult], None]
# Called while holding the scheduler Condition. should_wake() is true when a
# newer generation/stop has been requested.
WaitFn = Callable[[threading.Condition, Callable[[], bool], float], None]


def _default_wait(
    cond: threading.Condition,
    should_wake: Callable[[], bool],
    timeout: float,
) -> None:
    deadline = time.monotonic() + timeout
    while not should_wake():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        cond.wait(remaining)


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
        self._idle = threading.Condition()
        self._running = False
        self._coalesce = False
        self._stopped = True
        self._generation = 0
        self._thread: threading.Thread | None = None
        self._next_delay = self.interval_seconds

    @property
    def running(self) -> bool:
        return not self._stopped

    def start(self, *, initial_delay_seconds: float | None = None) -> None:
        with self._idle:
            if not self._stopped:
                return
            self._stopped = False
            self._generation += 1
            if initial_delay_seconds is None:
                self._next_delay = self.interval_seconds
            else:
                self._next_delay = float(max(0.0, initial_delay_seconds))
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
            self._generation += 1
            self._idle.notify_all()
            while wait and self._running:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    break
                self._idle.wait(0.05 if remaining is None else min(0.05, remaining))
            thread = self._thread
        if wait and thread is not None and thread.is_alive():
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            thread.join(remaining)
        with self._idle:
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
            self._generation += 1
            self._idle.notify_all()

    def _worker(self) -> None:
        while True:
            with self._idle:
                if self._stopped:
                    return
                delay = self._next_delay
                self._next_delay = self.interval_seconds
                gen = self._generation

                def should_wake() -> bool:
                    return self._stopped or self._generation != gen

                if delay > 0:
                    self._wait_fn(self._idle, should_wake, delay)
                if self._stopped:
                    return
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
            # Tentative next schedule; overwritten from post-cycle clock below.
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
            if not dry_run:
                scheduled_from = self.clock.now()
                if result is not None and result.more_work_pending:
                    next_delay = self._more_work_delay_seconds
                else:
                    next_delay = self.interval_seconds
                next_at = self._next_iso(scheduled_from, next_delay)
                persist_next_scheduled_at(self.repo, next_at)
                with self._idle:
                    if reschedule and not self._stopped:
                        self._next_delay = next_delay
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
                    self._generation += 1
                    self._idle.notify_all()
                elif reschedule and not self._stopped:
                    self._idle.notify_all()
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
    """Publish status + collection invalidations for any terminal cycle."""
    for event in affected_invalidation_events(result):
        if event == "storage_maintenance_completed":
            publish_sync(event, dict(maintenance_event_payload(result)))
        else:
            publish_sync(event, {"type": event})
    if maintenance_evidence_changed(result):
        schedule_dashboard()
