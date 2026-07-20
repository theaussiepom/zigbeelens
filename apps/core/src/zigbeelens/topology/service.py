"""Topology snapshot capture orchestration."""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol

from zigbeelens.config.models import AppConfig
from zigbeelens.mqtt.models import RawMqttMessage
from zigbeelens.storage.repository import utc_now_iso
from zigbeelens.topology.parser import parse_networkmap_payload
from zigbeelens.topology.publisher import TopologyRequestPublisher
from zigbeelens.topology.scheduler import (
    periodic_capture_allowed,
    start_topology_scheduler,
    stop_topology_scheduler,
)
from zigbeelens.topology.topics import (
    CAPTURE_WARNING,
    is_networkmap_response_topic,
    networkmap_request_topic,
)

if TYPE_CHECKING:
    from zigbeelens.app.context import AppContext

logger = logging.getLogger(__name__)

# Pending captures with no MQTT response are cleared after this window.
PENDING_CAPTURE_TIMEOUT_SECONDS = 15 * 60


class RequestPublisherProtocol(Protocol):
    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def publish_networkmap_request(self, topic: str, payload: str = ...) -> None: ...


@dataclass
class PendingCapture:
    snapshot_id: str
    network_id: str
    base_topic: str
    requested_by: str
    warning_acknowledged: bool
    requested_at: str


@dataclass
class TopologyStatus:
    enabled: bool = False
    manual_capture_enabled: bool = False
    automatic_capture_enabled: bool = False
    capture_in_progress: bool = False
    last_capture_error: str | None = None
    networks: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "manual_capture_enabled": self.manual_capture_enabled,
            "automatic_capture_enabled": self.automatic_capture_enabled,
            "capture_in_progress": self.capture_in_progress,
            "last_capture_error": self.last_capture_error,
            "networks": self.networks,
        }


def manual_capture_allowed(config: AppConfig) -> bool:
    return bool(
        config.topology.enabled
        and config.features.manual_network_map
        and config.topology.manual_capture_enabled
    )


def automatic_capture_allowed(config: AppConfig) -> bool:
    return periodic_capture_allowed(config)


class TopologyService:
    def __init__(
        self,
        ctx: AppContext,
        *,
        publisher: RequestPublisherProtocol | None = None,
    ) -> None:
        self._ctx = ctx
        self._config = ctx.config
        self._repo = ctx.repo
        self._publisher = publisher
        self._pending: PendingCapture | None = None
        self._lock = threading.Lock()
        self._status = TopologyStatus(
            enabled=self._config.topology.enabled,
            manual_capture_enabled=manual_capture_allowed(self._config),
            automatic_capture_enabled=automatic_capture_allowed(self._config),
        )

    @property
    def status(self) -> TopologyStatus:
        self._status.capture_in_progress = self._pending is not None
        self._status.networks = self._network_summaries()
        return self._status

    @property
    def active_pending_snapshot_id(self) -> str | None:
        """Read-only ID of the in-memory pending capture, if any."""
        with self._lock:
            pending = self._pending
        return None if pending is None else pending.snapshot_id

    def capture_warning(self) -> str:
        return CAPTURE_WARNING

    def request_capture(
        self,
        network_id: str,
        *,
        confirmed: bool,
        requested_by: str = "manual_user_capture",
    ) -> dict:
        if not manual_capture_allowed(self._config):
            raise PermissionError("Topology capture is disabled")
        if not confirmed:
            raise ValueError(CAPTURE_WARNING)
        network = self._repo.get_network(network_id)
        if network is None:
            raise KeyError(f"Unknown network: {network_id}")
        with self._lock:
            self._clear_stale_pending_unlocked()
            if self._pending is not None:
                raise RuntimeError("Topology capture already in progress")

            snapshot_id = str(uuid.uuid4())
            requested_at = utc_now_iso()
            self._repo.create_topology_snapshot(
                snapshot_id=snapshot_id,
                network_id=network_id,
                requested_by=requested_by,
                status="pending",
                warning_acknowledged=True,
            )
            self._pending = PendingCapture(
                snapshot_id=snapshot_id,
                network_id=network_id,
                base_topic=network.base_topic,
                requested_by=requested_by,
                warning_acknowledged=True,
                requested_at=requested_at,
            )

        publisher = self._publisher or TopologyRequestPublisher(self._config)
        own_publisher = self._publisher is None
        try:
            if own_publisher:
                publisher.connect()
            topic = networkmap_request_topic(network.base_topic)
            publisher.publish_networkmap_request(topic)
            self._status.last_capture_error = None
            return {
                "snapshot_id": snapshot_id,
                "network_id": network_id,
                "status": "pending",
                "warning": CAPTURE_WARNING,
            }
        except Exception as err:
            self._repo.update_topology_snapshot(
                snapshot_id,
                status="error",
                error="Topology request failed",
            )
            with self._lock:
                self._pending = None
            self._status.last_capture_error = "Topology request failed"
            logger.exception("Topology capture request failed")
            raise RuntimeError("Topology capture request failed") from err
        finally:
            if own_publisher:
                publisher.disconnect()

    def request_system_capture(
        self,
        network_id: str,
        *,
        requested_by: str = "startup_scan",
    ) -> dict:
        if not self._config.topology.enabled:
            raise PermissionError("Topology capture is disabled")
        if requested_by == "startup_scan" and not self._config.topology.startup_scan:
            raise PermissionError("Topology startup scan is disabled")
        if requested_by == "periodic_refresh" and not periodic_capture_allowed(self._config):
            raise PermissionError("Periodic topology refresh is disabled")

        network = self._repo.get_network(network_id)
        if network is None:
            raise KeyError(f"Unknown network: {network_id}")
        with self._lock:
            self._clear_stale_pending_unlocked()
            if self._pending is not None:
                raise RuntimeError("Topology capture already in progress")

            snapshot_id = str(uuid.uuid4())
            requested_at = utc_now_iso()
            self._repo.create_topology_snapshot(
                snapshot_id=snapshot_id,
                network_id=network_id,
                requested_by=requested_by,
                status="pending",
                warning_acknowledged=True,
            )
            self._pending = PendingCapture(
                snapshot_id=snapshot_id,
                network_id=network_id,
                base_topic=network.base_topic,
                requested_by=requested_by,
                warning_acknowledged=True,
                requested_at=requested_at,
            )

        publisher = self._publisher or TopologyRequestPublisher(self._config)
        own_publisher = self._publisher is None
        try:
            if own_publisher:
                publisher.connect()
            topic = networkmap_request_topic(network.base_topic)
            publisher.publish_networkmap_request(topic)
            self._status.last_capture_error = None
            return {
                "snapshot_id": snapshot_id,
                "network_id": network_id,
                "status": "pending",
                "requested_by": requested_by,
            }
        except Exception as err:
            self._repo.update_topology_snapshot(
                snapshot_id,
                status="error",
                error="Topology request failed",
            )
            with self._lock:
                self._pending = None
            self._status.last_capture_error = "Topology request failed"
            logger.exception("Topology system capture request failed")
            raise RuntimeError("Topology capture request failed") from err
        finally:
            if own_publisher:
                publisher.disconnect()

    def try_handle_response(self, message: RawMqttMessage) -> bool:
        with self._lock:
            pending = self._pending
        if pending is None:
            return False
        if not is_networkmap_response_topic(message.topic, pending.base_topic):
            return False

        # Pre-store failures own the capture failure path. Pending release is
        # unconditional even when error-status persistence also fails.
        try:
            parsed = parse_networkmap_payload(message.payload)
            self._repo.store_topology_parsed(
                pending.snapshot_id,
                pending.network_id,
                parsed,
                status="complete",
            )
        except Exception:
            logger.exception("Topology response handling failed")
            try:
                self._repo.update_topology_snapshot(
                    pending.snapshot_id,
                    status="error",
                    error="Topology response handling failed",
                )
            except Exception:
                logger.error(
                    "Topology failure status persistence failed safely; "
                    "pending capture released"
                )
            finally:
                self._status.last_capture_error = "Topology response handling failed"
                self._clear_matching_pending(pending.snapshot_id)
            return False

        # Completed capture is authoritative; remaining work is best-effort.
        self._status.last_capture_error = None
        try:
            self._repo.enforce_topology_retention(
                pending.network_id, self._config.topology.max_snapshots_per_network
            )
        except Exception:
            logger.error(
                "Topology count retention failed safely; completed capture retained"
            )
        try:
            self._refresh_diagnostics()
        except Exception:
            logger.error(
                "Topology diagnostic refresh failed safely; completed capture retained"
            )
            self._status.last_capture_error = "Topology diagnostic refresh failed"

        # Consumers must observe capture_in_progress=false at event time.
        self._clear_matching_pending(pending.snapshot_id)
        try:
            self._ctx.broadcaster.publish_sync(
                "topology_updated", {"type": "topology_updated"}
            )
        except Exception:
            logger.error("topology_updated publish failed safely after capture")
        return True

    def _clear_matching_pending(self, snapshot_id: str) -> None:
        """Clear the in-memory pending capture only when it is still this one."""
        with self._lock:
            if self._pending is not None and self._pending.snapshot_id == snapshot_id:
                self._pending = None

    def _clear_stale_pending_unlocked(self) -> None:
        pending = self._pending
        if pending is None:
            return
        try:
            requested = datetime.fromisoformat(pending.requested_at.replace("Z", "+00:00"))
        except ValueError:
            requested = datetime.now(timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - requested).total_seconds()
        if age_seconds < PENDING_CAPTURE_TIMEOUT_SECONDS:
            return
        self._repo.update_topology_snapshot(
            pending.snapshot_id,
            status="error",
            error="Topology capture timed out",
        )
        self._pending = None
        self._status.last_capture_error = "Topology capture timed out"
        logger.warning(
            "Cleared stale topology capture for network %s (snapshot %s)",
            pending.network_id,
            pending.snapshot_id,
        )

    def _refresh_diagnostics(self) -> None:
        ctx = self._ctx
        if ctx.evaluation is not None:
            ctx.evaluation.evaluate_all()
        else:
            ctx.health.recalculate_all()
        if ctx.discovery is not None:
            ctx.discovery.schedule_update()

    def _network_summaries(self) -> list[dict]:
        summaries = []
        for network in self._repo.list_networks():
            latest = self._repo.get_latest_topology_snapshot(network.id)
            summaries.append(
                {
                    "network_id": network.id,
                    "network_name": network.name,
                    "latest_snapshot": latest,
                }
            )
        return summaries


_topology: TopologyService | None = None


def start_topology(ctx: AppContext) -> TopologyService:
    global _topology
    service = TopologyService(ctx)
    _topology = service
    start_topology_scheduler(ctx, service)
    return service


def get_topology_service() -> TopologyService | None:
    return _topology


def stop_topology() -> None:
    global _topology
    stop_topology_scheduler(wait=True)
    _topology = None


def topology_status_dict(ctx: AppContext) -> dict:
    service = get_topology_service()
    if service is None:
        return TopologyStatus(
            enabled=ctx.config.topology.enabled,
            manual_capture_enabled=manual_capture_allowed(ctx.config),
            automatic_capture_enabled=automatic_capture_allowed(ctx.config),
            networks=[
                {
                    "network_id": n.id,
                    "network_name": n.name,
                    "latest_snapshot": ctx.repo.get_latest_topology_snapshot(n.id),
                }
                for n in ctx.repo.list_networks()
            ],
        ).as_dict()
    return service.status.as_dict()
