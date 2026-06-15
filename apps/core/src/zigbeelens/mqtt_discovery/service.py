from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Protocol

from zigbeelens import __version__
from zigbeelens.config.models import AppConfig
from zigbeelens.mqtt_discovery.models import MqttDiscoveryStatus
from zigbeelens.mqtt_discovery.payloads import (
    all_discovery_entities,
    attributes_payload,
    build_discovery_device,
    build_states_from_dashboard,
    discovery_config_payload,
    discovery_topic_for_entity,
    state_payload,
)
from zigbeelens.mqtt_discovery.publisher import FakeDiscoveryPublisher, SafeMqttPublisher
from zigbeelens.mqtt_discovery.topics import (
    LEGACY_DISCOVERY_TOPICS,
    availability_topic,
    summary_attributes_topic,
    summary_state_topic,
)
from zigbeelens.storage.repository import utc_now_iso

if TYPE_CHECKING:
    from zigbeelens.app.context import AppContext

logger = logging.getLogger(__name__)

_DEBOUNCE_SECONDS = 2.0


class PublisherProtocol(Protocol):
    connected: bool

    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def publish(self, topic: str, payload: str, *, retain: bool = False) -> None: ...
    def publish_json(self, topic: str, payload: dict, *, retain: bool = False) -> None: ...
    def delete_retained(self, topic: str) -> None: ...


def discovery_enabled(config: AppConfig) -> bool:
    return bool(config.features.mqtt_discovery and config.mqtt_discovery.enabled)


class MqttDiscoveryService:
    """Publish Lens-family summary entities via Home Assistant MQTT Discovery."""

    def __init__(
        self,
        ctx: AppContext,
        *,
        publisher: PublisherProtocol | None = None,
    ) -> None:
        self._ctx = ctx
        self._config = ctx.config
        self._status = MqttDiscoveryStatus(enabled=True)
        self._publisher = publisher or SafeMqttPublisher(ctx.config)
        self._published_topics: set[str] = set()
        self._discovery_topics: set[str] = set()
        self._lock = threading.Lock()
        self._debounce_timer: threading.Timer | None = None
        self._pending_update = False

    @property
    def status(self) -> MqttDiscoveryStatus:
        self._status.connected = self._publisher.connected
        return self._status

    def start(self) -> None:
        if not discovery_enabled(self._config):
            self._status.enabled = False
            return
        try:
            self._publisher.connect()
            self._publish_availability("online")
            self._publish_all(force_discovery=True)
        except Exception as err:
            self._status.last_error = "Discovery publisher failed to start"
            logger.exception("MQTT discovery failed to start: %s", err)

    def stop(self) -> None:
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
            self._debounce_timer = None
        try:
            self._publish_availability("offline")
        except Exception:
            logger.debug("Failed to publish discovery offline", exc_info=True)
        try:
            self._publisher.disconnect()
        except Exception:
            logger.debug("Discovery publisher disconnect error", exc_info=True)

    def schedule_update(self) -> None:
        with self._lock:
            self._pending_update = True
            if self._debounce_timer is not None:
                return
            self._debounce_timer = threading.Timer(_DEBOUNCE_SECONDS, self._run_debounced_update)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _run_debounced_update(self) -> None:
        with self._lock:
            self._debounce_timer = None
            if not self._pending_update:
                return
            self._pending_update = False
        try:
            self._publish_all(force_discovery=False)
        except Exception as err:
            self._status.last_error = "Discovery publish failed"
            logger.exception("MQTT discovery update failed: %s", err)

    def cleanup_discovery_configs(self) -> None:
        for topic in list(self._discovery_topics):
            try:
                self._publisher.delete_retained(topic)
            except Exception:
                logger.debug("Failed to delete discovery topic %s", topic, exc_info=True)
        self._discovery_topics.clear()

    def cleanup_legacy_discovery_configs(self) -> None:
        """Publish empty retained payloads for known legacy discovery topics."""
        for topic in LEGACY_DISCOVERY_TOPICS:
            try:
                self._publisher.delete_retained(topic)
            except Exception:
                logger.debug("Failed to delete legacy discovery topic %s", topic, exc_info=True)

    def _publish_availability(self, state: str) -> None:
        topic = availability_topic(self._config.mqtt_discovery.state_topic_prefix)
        retain = self._config.mqtt_discovery.retain
        self._publisher.publish(topic, state, retain=retain)
        self._published_topics.add(topic)

    def _publish_all(self, *, force_discovery: bool) -> None:
        dashboard = self._ctx.data.dashboard()
        collector = self._collector_connected()
        if collector.get("last_error"):
            collector = {**collector, "last_error": "[redacted]"}

        device = build_discovery_device(
            device_name=self._config.mqtt_discovery.device_name,
            core_version=__version__,
        )
        availability = availability_topic(self._config.mqtt_discovery.state_topic_prefix)
        entities = all_discovery_entities(
            topic_prefix=self._config.mqtt_discovery.topic_prefix,
            state_topic_prefix=self._config.mqtt_discovery.state_topic_prefix,
            object_id_prefix=self._config.mqtt_discovery.object_id_prefix,
            availability=availability,
            device=device,
            dashboard=dashboard,
        )
        retain = self._config.mqtt_discovery.retain

        if force_discovery:
            for entity in entities:
                topic = discovery_topic_for_entity(self._config.mqtt_discovery.topic_prefix, entity)
                payload = discovery_config_payload(entity, availability, device)
                self._publisher.publish_json(topic, payload, retain=True)
                self._discovery_topics.add(topic)
                self._published_topics.add(topic)

        states = build_states_from_dashboard(
            dashboard,
            core_version=__version__,
            collector_connected=bool(collector.get("connected")),
            mock_mode=bool(self._config.mode.mock),
        )
        prefix = self._config.mqtt_discovery.state_topic_prefix
        for entity_key, published in states.items():
            state_topic = summary_state_topic(prefix, entity_key)
            attributes_topic = summary_attributes_topic(prefix, entity_key)
            self._publisher.publish(state_topic, state_payload(published), retain=retain)
            self._publisher.publish(
                attributes_topic,
                attributes_payload(published),
                retain=retain,
            )
            self._published_topics.add(state_topic)
            self._published_topics.add(attributes_topic)

        self._status.published_entities_count = len(entities)
        self._status.last_publish_at = utc_now_iso()
        self._status.last_error = None

    def _collector_connected(self) -> dict:
        from zigbeelens.mqtt.lifecycle import collector_status_dict

        return collector_status_dict(self._ctx)


_discovery: MqttDiscoveryService | None = None


def start_discovery(ctx: AppContext, *, publisher: PublisherProtocol | None = None) -> MqttDiscoveryService | None:
    global _discovery
    if not discovery_enabled(ctx.config):
        return None
    service = MqttDiscoveryService(ctx, publisher=publisher)
    service.start()
    _discovery = service
    return service


def stop_discovery(service: MqttDiscoveryService | None) -> None:
    global _discovery
    if service is not None:
        service.stop()
    _discovery = None


def get_discovery_service() -> MqttDiscoveryService | None:
    return _discovery


def discovery_status_dict(ctx: AppContext) -> dict:
    enabled = discovery_enabled(ctx.config)
    service = get_discovery_service()
    if service is None:
        return MqttDiscoveryStatus(enabled=enabled).as_dict()
    status = service.status
    status.enabled = enabled
    return status.as_dict()


def build_fake_publisher(config: AppConfig) -> FakeDiscoveryPublisher:
    return FakeDiscoveryPublisher(config=config)
