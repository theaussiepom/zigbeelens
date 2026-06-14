"""Tightly-scoped MQTT publisher for ZigbeeLens-owned topics only."""

from __future__ import annotations

import json
import logging
import ssl
import threading
from dataclasses import dataclass, field
from typing import Callable

from zigbeelens.config.models import AppConfig, MqttConfig
from zigbeelens.mqtt.client import parse_mqtt_server
from zigbeelens.mqtt_discovery.topics import UnsafeMqttTopicError, validate_publish_topic

logger = logging.getLogger(__name__)


@dataclass
class PublishRecord:
    topic: str
    payload: str
    retain: bool


class SafeMqttPublisher:
    """Publish only to validated ZigbeeLens-owned topics."""

    def __init__(
        self,
        config: AppConfig,
        *,
        client_id_suffix: str = "-discovery",
        on_connect: Callable[[], None] | None = None,
    ) -> None:
        import paho.mqtt.client as mqtt

        self._config = config
        self._mqtt = config.mqtt
        self._base_topics = tuple(n.base_topic for n in config.networks)
        self._records: list[PublishRecord] = []
        self._lock = threading.Lock()
        self._connected = False
        conn = parse_mqtt_server(self._mqtt.server)
        client_id = f"{self._mqtt.client_id}{client_id_suffix}"
        availability = self._availability_topic()
        self._client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
        if self._mqtt.username:
            self._client.username_pw_set(self._mqtt.username, self._mqtt.password or None)
        if conn.use_tls or self._mqtt.tls.enabled:
            self._client.tls_set(
                cert_reqs=ssl.CERT_REQUIRED if self._mqtt.tls.reject_unauthorized else ssl.CERT_NONE
            )
        self._client.will_set(availability, payload="offline", retain=True)
        self._client.on_connect = self._handle_connect
        self._client.on_disconnect = self._handle_disconnect
        self._on_connect_cb = on_connect
        self._host = conn.host
        self._port = conn.port

    def _availability_topic(self) -> str:
        prefix = self._config.mqtt_discovery.state_topic_prefix.strip("/")
        return f"{prefix}/status"

    def _handle_connect(self, _client, _userdata, _flags, rc) -> None:
        if rc == 0:
            with self._lock:
                self._connected = True
            logger.info("MQTT discovery publisher connected to %s:%s", self._host, self._port)
            if self._on_connect_cb:
                self._on_connect_cb()
        else:
            logger.error("MQTT discovery publisher connect failed rc=%s", rc)

    def _handle_disconnect(self, _client, _userdata, rc) -> None:
        with self._lock:
            self._connected = False
        logger.warning("MQTT discovery publisher disconnected rc=%s", rc)

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    @property
    def published(self) -> list[PublishRecord]:
        with self._lock:
            return list(self._records)

    def connect(self) -> None:
        self._client.connect(self._host, self._port, keepalive=60)
        self._client.loop_start()

    def disconnect(self) -> None:
        try:
            self.publish(self._availability_topic(), "offline", retain=True)
        except Exception:
            logger.debug("Failed to publish discovery offline availability", exc_info=True)
        self._client.loop_stop()
        self._client.disconnect()
        with self._lock:
            self._connected = False

    def publish(self, topic: str, payload: str, *, retain: bool = False) -> None:
        validate_publish_topic(topic, zigbee_base_topics=self._base_topics)
        with self._lock:
            self._records.append(PublishRecord(topic=topic, payload=payload, retain=retain))
        result = self._client.publish(topic, payload=payload, retain=retain, qos=0)
        if result.rc != 0:
            raise RuntimeError(f"MQTT publish failed rc={result.rc}")

    def publish_json(self, topic: str, payload: dict, *, retain: bool = False) -> None:
        self.publish(topic, json.dumps(payload, separators=(",", ":")), retain=retain)

    def delete_retained(self, topic: str) -> None:
        self.publish(topic, "", retain=True)


@dataclass
class FakeDiscoveryPublisher:
    """Test double that validates topics like the real publisher."""

    config: AppConfig
    published: list[PublishRecord] = field(default_factory=list)
    _connected: bool = False
    _base_topics: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        self._base_topics = tuple(n.base_topic for n in self.config.networks)

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        prefix = self.config.mqtt_discovery.state_topic_prefix.strip("/")
        self.publish(f"{prefix}/status", "offline", retain=True)
        self._connected = False

    def publish(self, topic: str, payload: str, *, retain: bool = False) -> None:
        validate_publish_topic(topic, zigbee_base_topics=self._base_topics)
        self.published.append(PublishRecord(topic=topic, payload=payload, retain=retain))

    def publish_json(self, topic: str, payload: dict, *, retain: bool = False) -> None:
        self.publish(topic, json.dumps(payload, separators=(",", ":")), retain=retain)

    def delete_retained(self, topic: str) -> None:
        self.publish(topic, "", retain=True)
