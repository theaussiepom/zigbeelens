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
        self._timer: threading.Timer | None = None

    def schedule(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(_DEBOUNCE_SECONDS, self._publish)
            self._timer.daemon = True
            self._timer.start()

    def flush(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        self._publish()

    def cancel(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def _publish(self) -> None:
        with self._lock:
            self._timer = None
        try:
            dashboard = self._ctx.data.dashboard()
            self._broadcaster.publish_dashboard_update(dashboard.model_dump_json())
            if self._ctx.discovery is not None:
                self._ctx.discovery.schedule_update()
        except Exception:
            logger.exception("Debounced dashboard publish failed")
