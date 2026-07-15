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
        self._publishing = False
        self._pending = False
        self._cancelled = False

    def schedule(self) -> None:
        with self._idle:
            self._cancelled = False
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
            self._cancelled = False
            self._pending = False
        self._publish()

    def cancel(self, *, wait: bool = True, timeout: float | None = None) -> None:
        with self._idle:
            self._cancelled = True
            self._pending = False
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if wait:
                self._idle.wait_for(lambda: not self._publishing, timeout=timeout)

    def _publish(self) -> None:
        with self._idle:
            self._timer = None
            if self._cancelled:
                return
            if self._publishing:
                self._pending = True
                return
            self._publishing = True
        try:
            dashboard = self._ctx.data.dashboard()
            self._broadcaster.publish_dashboard_update(dashboard.model_dump_json())
            if self._ctx.discovery is not None:
                self._ctx.discovery.schedule_update()
        except Exception:
            logger.exception("Debounced dashboard publish failed")
        finally:
            with self._idle:
                self._publishing = False
                if self._pending and not self._cancelled:
                    self._pending = False
                    self._schedule_locked()
                self._idle.notify_all()

    def _schedule_locked(self) -> None:
        self._timer = threading.Timer(_DEBOUNCE_SECONDS, self._publish)
        self._timer.daemon = True
        self._timer.start()
