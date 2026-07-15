"""Clock-driven current-signal evaluation pipeline."""

from __future__ import annotations

import logging
import time
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from zigbeelens.diagnostics.clock import Clock, SystemClock
from zigbeelens.diagnostics.incidents.service import IncidentDiagnosticService
from zigbeelens.diagnostics.service import HealthDiagnosticService, NetworkEvaluationSnapshot

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvaluationResult:
    evaluated_at: datetime
    network_ids: tuple[str, ...]
    health_changed: bool
    incident_events: tuple[str, ...]
    dashboard_update_required: bool


class EvaluationCoordinator:
    def __init__(
        self,
        health: HealthDiagnosticService,
        incidents: IncidentDiagnosticService,
        *,
        clock: Clock | None = None,
        on_event: Callable[[str], None] | None = None,
        on_dashboard_required: Callable[[], None] | None = None,
    ) -> None:
        self.health = health
        self.incidents = incidents
        self.clock = clock or SystemClock()
        self._on_event = on_event
        self._on_dashboard_required = on_dashboard_required
        self._lock = threading.Lock()
        self._snapshots_by_network: dict[str, NetworkEvaluationSnapshot] = {}

    def evaluate_network(self, network_id: str, *, now: datetime | None = None) -> EvaluationResult:
        reference_now = now or self.clock.now()
        with self._lock:
            configured_ids = self._configured_network_ids()
            if network_id not in configured_ids:
                return EvaluationResult(reference_now, tuple(), False, tuple(), False)
            if not set(configured_ids).issubset(self._snapshots_by_network.keys()):
                snapshots = self.health.evaluate_all(now=reference_now)
                self._snapshots_by_network = {snapshot.network_id: snapshot for snapshot in snapshots}
                return self._finish(
                    snapshots,
                    reference_now=reference_now,
                    evaluated_network_ids=tuple(snapshot.network_id for snapshot in snapshots),
                    health_changed=any(snapshot.health_changed for snapshot in snapshots),
                )

            refreshed = self.health.evaluate_network(network_id, now=reference_now)
            if refreshed is None:
                return EvaluationResult(reference_now, tuple(), False, tuple(), False)
            self._snapshots_by_network[network_id] = refreshed
            snapshots = self._complete_snapshots(configured_ids)
            if snapshots is None:
                return EvaluationResult(
                    reference_now, (network_id,), refreshed.health_changed, tuple(), refreshed.health_changed
                )
            return self._finish(
                snapshots,
                reference_now=reference_now,
                evaluated_network_ids=(network_id,),
                health_changed=refreshed.health_changed,
            )

    def evaluate_all(self, *, now: datetime | None = None) -> EvaluationResult:
        reference_now = now or self.clock.now()
        with self._lock:
            snapshots = self.health.evaluate_all(now=reference_now)
            self._snapshots_by_network = {snapshot.network_id: snapshot for snapshot in snapshots}
            return self._finish(
                snapshots,
                reference_now=reference_now,
                evaluated_network_ids=tuple(snapshot.network_id for snapshot in snapshots),
                health_changed=any(snapshot.health_changed for snapshot in snapshots),
            )

    def _configured_network_ids(self) -> tuple[str, ...]:
        return tuple(sorted(network.id for network in self.health.repo.list_networks()))

    def _complete_snapshots(
        self, configured_ids: tuple[str, ...]
    ) -> list[NetworkEvaluationSnapshot] | None:
        if not set(configured_ids).issubset(self._snapshots_by_network.keys()):
            return None
        return [self._snapshots_by_network[network_id] for network_id in configured_ids]

    def _finish(
        self,
        snapshots: list[NetworkEvaluationSnapshot],
        *,
        reference_now: datetime,
        evaluated_network_ids: tuple[str, ...],
        health_changed: bool,
    ) -> EvaluationResult:
        events = self.incidents.correlate_and_sync(snapshots, now=reference_now)
        dashboard_required = health_changed or bool(events)
        if self._on_event:
            if health_changed:
                self._on_event("health_updated")
            for event in events:
                self._on_event(event)
        if dashboard_required and self._on_dashboard_required:
            self._on_dashboard_required()
        return EvaluationResult(
            evaluated_at=reference_now,
            network_ids=evaluated_network_ids,
            health_changed=health_changed,
            incident_events=tuple(events),
            dashboard_update_required=dashboard_required,
        )


class PeriodicEvaluationScheduler:
    def __init__(self, coordinator: EvaluationCoordinator, interval_seconds: float = 300.0) -> None:
        self.coordinator = coordinator
        self.interval_seconds = interval_seconds
        self._lock = threading.Lock()
        self._idle = threading.Condition(self._lock)
        self._running = False
        self._timer: threading.Timer | None = None
        self._stopped = True

    @property
    def running(self) -> bool:
        return not self._stopped

    def start(self) -> None:
        with self._lock:
            if not self._stopped:
                return
            self._stopped = False
            self._schedule_locked()

    def stop(self, *, wait: bool = True, timeout: float | None = None) -> None:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._idle:
            self._stopped = True
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            while wait and self._running:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    break
                self._idle.wait(remaining)

    def run_once(self, *, now: datetime | None = None) -> EvaluationResult | None:
        with self._idle:
            if self._running:
                return None
            self._running = True
        return self._run_claimed(now=now, reschedule=False)

    def _tick(self) -> None:
        with self._idle:
            if self._stopped or self._running:
                return
            self._running = True
        self._run_claimed(now=None, reschedule=True)

    def _run_claimed(
        self, *, now: datetime | None, reschedule: bool
    ) -> EvaluationResult | None:
        try:
            return self.coordinator.evaluate_all(now=now)
        except Exception:
            logger.exception("Periodic evaluation tick failed")
            return None
        finally:
            with self._idle:
                self._running = False
                self._idle.notify_all()
                if reschedule and not self._stopped:
                    self._schedule_locked()

    def _schedule_locked(self) -> None:
        self._timer = threading.Timer(self.interval_seconds, self._tick)
        self._timer.daemon = True
        self._timer.start()
