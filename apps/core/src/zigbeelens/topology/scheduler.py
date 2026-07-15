"""Startup and optional periodic topology capture scheduling."""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Callable

from zigbeelens.config.models import AppConfig

if TYPE_CHECKING:
    from zigbeelens.app.context import AppContext
    from zigbeelens.topology.service import TopologyService

logger = logging.getLogger(__name__)

SleepFn = Callable[[float], None]


def periodic_capture_interval_seconds(config: AppConfig) -> int:
    topo = config.topology
    if topo.refresh_interval_seconds > 0:
        return topo.refresh_interval_seconds
    if (
        topo.enabled
        and config.features.automatic_network_map
        and topo.automatic_capture_enabled
    ):
        return topo.automatic_capture_interval_hours * 3600
    return 0


def periodic_capture_allowed(config: AppConfig) -> bool:
    return periodic_capture_interval_seconds(config) > 0


def startup_scan_allowed(config: AppConfig) -> bool:
    return bool(
        config.topology.enabled
        and config.topology.startup_scan
        and not config.mode.mock
        and config.features.mqtt_collector
        and bool(config.mqtt.server.strip())
        and bool(config.networks)
    )


def collector_ready(ctx: AppContext) -> bool:
    if ctx.collector is None:
        return False
    status = ctx.collector.status()
    return bool(status.enabled and status.connected)


def bridges_ready(ctx: AppContext) -> bool:
    for network in ctx.config.networks:
        row = ctx.repo.get_network(network.id)
        if row is None or row.bridge_state != "online":
            return False
    return True


class TopologyScheduler:
    """Runs one startup topology scan per network, then optional periodic refresh."""

    def __init__(
        self,
        ctx: AppContext,
        service: TopologyService,
        *,
        sleep: SleepFn = time.sleep,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._ctx = ctx
        self._service = service
        self._config = ctx.config
        self._sleep = sleep
        self._poll_interval_seconds = poll_interval_seconds
        self._stop = threading.Event()
        self._startup_completed = False
        self._startup_networks_done: set[str] = set()
        self._stable_since: float | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not startup_scan_allowed(self._config) and not periodic_capture_allowed(self._config):
            return
        self._thread = threading.Thread(
            target=self._run,
            name="topology-scheduler",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, wait: bool = True, timeout: float | None = None) -> None:
        self._stop.set()
        if wait and self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout)

    def tick_startup(self) -> bool:
        """Advance startup scan state once (for tests). Returns True when startup finished."""
        if not startup_scan_allowed(self._config):
            self._startup_completed = True
            return True
        return self._advance_startup()

    def _run(self) -> None:
        try:
            if startup_scan_allowed(self._config):
                while not self._stop.is_set() and not self._advance_startup():
                    self._wait_interval(self._poll_interval_seconds)

            interval = periodic_capture_interval_seconds(self._config)
            if interval <= 0:
                return

            while not self._stop.is_set():
                self._wait_interval(interval)
                if self._stop.is_set():
                    return
                if not collector_ready(self._ctx) or not bridges_ready(self._ctx):
                    continue
                self._capture_all_networks(requested_by="periodic_refresh")
        except Exception:
            logger.exception("Topology scheduler stopped due to error")

    def _wait_interval(self, interval: float) -> None:
        if self._sleep is time.sleep:
            self._stop.wait(interval)
        else:
            self._sleep(interval)

    def _advance_startup(self) -> bool:
        if self._startup_completed:
            return True

        if not collector_ready(self._ctx) or not bridges_ready(self._ctx):
            self._stable_since = None
            return False

        now = time.monotonic()
        if self._stable_since is None:
            self._stable_since = now

        delay = self._config.topology.startup_stable_delay_seconds
        if now - self._stable_since < delay:
            return False

        pending = [
            network.id
            for network in self._config.networks
            if network.id not in self._startup_networks_done
        ]
        if not pending:
            self._startup_completed = True
            return True

        if self._service.status.capture_in_progress:
            return False

        network_id = pending[0]
        try:
            self._service.request_system_capture(network_id, requested_by="startup_scan")
            self._startup_networks_done.add(network_id)
        except Exception:
            logger.exception("Startup topology capture failed for network %s", network_id)
            return False

        if len(self._startup_networks_done) >= len(self._config.networks):
            self._startup_completed = True
            return True
        return False

    def _capture_all_networks(self, *, requested_by: str) -> None:
        for network in self._config.networks:
            if self._stop.is_set():
                return
            while self._service.status.capture_in_progress and not self._stop.is_set():
                self._wait_interval(self._poll_interval_seconds)
            if self._stop.is_set():
                return
            try:
                self._service.request_system_capture(network.id, requested_by=requested_by)
            except Exception:
                logger.exception("Periodic topology capture failed for network %s", network.id)


_scheduler: TopologyScheduler | None = None


def start_topology_scheduler(ctx: AppContext, service: TopologyService) -> TopologyScheduler | None:
    global _scheduler
    scheduler = TopologyScheduler(ctx, service)
    scheduler.start()
    _scheduler = scheduler
    return scheduler


def get_topology_scheduler() -> TopologyScheduler | None:
    return _scheduler


def stop_topology_scheduler(*, wait: bool = True, timeout: float | None = None) -> None:
    global _scheduler
    scheduler = _scheduler
    _scheduler = None
    if scheduler is not None:
        scheduler.stop(wait=wait, timeout=timeout)
