"""Topology snapshot capture orchestration."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from zigbeelens.config.models import AppConfig
from zigbeelens.mqtt.models import RawMqttMessage
from zigbeelens.storage.repository import utc_now_iso
from zigbeelens.topology.parser import parse_networkmap_payload
from zigbeelens.topology.publisher import FakeTopologyRequestPublisher, TopologyRequestPublisher
from zigbeelens.topology.topics import (
    CAPTURE_WARNING,
    is_networkmap_response_topic,
    networkmap_request_topic,
)

if TYPE_CHECKING:
    from zigbeelens.app.context import AppContext

logger = logging.getLogger(__name__)


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
    return bool(
        config.topology.enabled
        and config.features.automatic_network_map
        and config.topology.automatic_capture_enabled
    )


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
            if self._pending is not None:
                raise RuntimeError("Topology capture already in progress")

            snapshot_id = str(uuid.uuid4())
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

    def try_handle_response(self, message: RawMqttMessage) -> bool:
        pending = self._pending
        if pending is None:
            return False
        if not is_networkmap_response_topic(message.topic, pending.base_topic):
            return False

        parsed = parse_networkmap_payload(message.payload)
        self._repo.store_topology_parsed(
            pending.snapshot_id,
            pending.network_id,
            parsed,
            status="complete",
        )
        self._repo.enforce_topology_retention(
            pending.network_id, self._config.topology.max_snapshots_per_network
        )
        with self._lock:
            self._pending = None
        self._status.last_capture_error = None
        self._refresh_diagnostics()
        return True

    def _refresh_diagnostics(self) -> None:
        ctx = self._ctx
        ctx.health.recalculate_all()
        ctx.incidents.correlate_and_sync(ctx.health)
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
    return service


def get_topology_service() -> TopologyService | None:
    return _topology


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
