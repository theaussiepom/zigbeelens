"""Debounced dashboard rebuild + SSE publish for MQTT ingestion."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zigbeelens.app.context import AppContext
    from zigbeelens.mqtt.events import EventBroadcaster

logger = logging.getLogger(__name__)

_DEBOUNCE_SECONDS = 0.25


class DashboardPublishScheduler:
    """Coalesce rapid MQTT-driven dashboard rebuilds into a single publish."""

    def __init__(self, ctx: AppContext, broadcaster: EventBroadcaster) -> None:
        self._ctx = ctx
        self._broadcaster = broadcaster
        self._lock = threading.Lock()
        self._idle = threading.Condition(self._lock)
        self._timer: threading.Timer | None = None
        self._timer_generation = 0
        self._publishing = False
        self._pending = False
        self._cancelled = False
        self._causes: set[str] = set()
        self._has_unattributed_request = False

    def schedule(self, *, cause: str | None = None) -> None:
        with self._idle:
            self._cancelled = False
            if cause is None:
                self._has_unattributed_request = True
            else:
                self._causes.add(cause)
            if self._publishing:
                self._pending = True
                return
            if self._timer is not None:
                self._timer.cancel()
            self._schedule_locked()

    def flush(self) -> None:
        with self._idle:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
                self._timer_generation += 1
            self._cancelled = False
            self._pending = False
        self._publish()

    def cancel(self, *, wait: bool = True, timeout: float | None = None) -> None:
        with self._idle:
            self._cancelled = True
            self._pending = False
            self._causes.clear()
            self._has_unattributed_request = False
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._timer_generation += 1
            if wait:
                self._idle.wait_for(lambda: not self._publishing, timeout=timeout)

    def _publish(self, timer_generation: int | None = None) -> None:
        with self._idle:
            if (
                timer_generation is not None
                and timer_generation != self._timer_generation
            ):
                return
            if timer_generation is not None:
                self._timer = None
            if self._cancelled:
                return
            if self._publishing:
                self._pending = True
                return
            self._publishing = True
            causes = tuple(sorted(self._causes))
            has_unattributed_request = self._has_unattributed_request
            self._causes.clear()
            self._has_unattributed_request = False
        try:
            dashboard = self._ctx.data.dashboard()
            if causes and not has_unattributed_request:
                self._broadcaster.publish_dashboard_update(
                    dashboard.model_dump_json(),
                    causes=causes,
                )
            else:
                self._broadcaster.publish_dashboard_update(dashboard.model_dump_json())
            if self._ctx.discovery is not None:
                self._ctx.discovery.schedule_update()
        except Exception:
            logger.error("Dashboard publish failed (category=dashboard_projection)")
        finally:
            with self._idle:
                self._publishing = False
                if self._pending and not self._cancelled:
                    self._pending = False
                    self._schedule_locked()
                self._idle.notify_all()

    def _schedule_locked(self) -> None:
        self._timer_generation += 1
        timer_generation = self._timer_generation
        self._timer = threading.Timer(
            _DEBOUNCE_SECONDS,
            lambda: self._publish(timer_generation),
        )
        self._timer.daemon = True
        self._timer.start()
