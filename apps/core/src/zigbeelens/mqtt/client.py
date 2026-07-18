"""Read-only MQTT client wrapper — subscribe only, never publish."""

from __future__ import annotations

import logging
import ssl
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse

from zigbeelens.config.models import MqttConfig
from zigbeelens.mqtt.models import RawMqttMessage

logger = logging.getLogger(__name__)

MessageCallback = Callable[[RawMqttMessage], None]


@dataclass
class MqttConnectionInfo:
    host: str
    port: int
    use_tls: bool = False


def parse_mqtt_server(server: str) -> MqttConnectionInfo:
    parsed = urlparse(server)
    scheme = parsed.scheme or "mqtt"
    host = parsed.hostname or "localhost"
    port = parsed.port or (8883 if scheme == "mqtts" else 1883)
    return MqttConnectionInfo(host=host, port=port, use_tls=scheme == "mqtts")


class MqttClientBase(ABC):
    """Subscribe-only MQTT client interface."""

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def subscribe(self, topics: list[str]) -> None: ...

    @property
    @abstractmethod
    def connected(self) -> bool: ...

    @property
    @abstractmethod
    def subscribed_topics(self) -> list[str]: ...


class PahoMqttClient(MqttClientBase):
    """paho-mqtt backed client. Intentionally has no publish() method."""

    def __init__(self, config: MqttConfig, on_message: MessageCallback) -> None:
        import paho.mqtt.client as mqtt

        self._config = config
        self._on_message_cb = on_message
        self._connected = False
        self._subscribed: list[str] = []
        self._lock = threading.Lock()
        conn = parse_mqtt_server(config.server)
        self._client = mqtt.Client(client_id=config.client_id, protocol=mqtt.MQTTv311)
        if config.username:
            password_value = config.password.get_secret_value()
            self._client.username_pw_set(config.username, password_value or None)
        if conn.use_tls or config.tls.enabled:
            self._client.tls_set(cert_reqs=ssl.CERT_REQUIRED if config.tls.reject_unauthorized else ssl.CERT_NONE)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._handle_message
        self._host = conn.host
        self._port = conn.port

    def _on_connect(self, client, userdata, flags, rc):  # noqa: ARG002
        if rc == 0:
            with self._lock:
                self._connected = True
            logger.info("MQTT connected to %s:%s", self._host, self._port)
            for topic in self._subscribed:
                client.subscribe(topic)
        else:
            logger.error("MQTT connect failed rc=%s", rc)

    def _on_disconnect(self, client, userdata, rc):  # noqa: ARG002
        with self._lock:
            self._connected = False
        logger.warning("MQTT disconnected rc=%s", rc)

    def _handle_message(self, client, userdata, msg):  # noqa: ARG002
        from zigbeelens.storage.repository import utc_now_iso

        raw = RawMqttMessage(
            topic=msg.topic,
            payload=msg.payload,
            retained=bool(getattr(msg, "retain", False)),
            received_at=utc_now_iso(),
        )
        try:
            self._on_message_cb(raw)
        except Exception:
            logger.exception("Error handling MQTT message on %s", msg.topic)

    def connect(self) -> None:
        self._client.connect(self._host, self._port, keepalive=60)
        self._client.loop_start()

    def disconnect(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()
        with self._lock:
            self._connected = False

    def subscribe(self, topics: list[str]) -> None:
        with self._lock:
            self._subscribed = list(dict.fromkeys(topics))
        if self.connected:
            for topic in self._subscribed:
                self._client.subscribe(topic)

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    @property
    def subscribed_topics(self) -> list[str]:
        with self._lock:
            return list(self._subscribed)


@dataclass
class FakeMqttClient(MqttClientBase):
    """In-memory MQTT client for tests — inject messages, verify no publish."""

    on_message: MessageCallback
    published: list[tuple[str, str]] = field(default_factory=list)
    _connected: bool = False
    _subscribed: list[str] = field(default_factory=list)

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def subscribe(self, topics: list[str]) -> None:
        self._subscribed = list(dict.fromkeys(topics))

    def inject(self, topic: str, payload: str | bytes, *, retained: bool = False) -> None:
        from zigbeelens.storage.repository import utc_now_iso

        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        if not self._matches_subscription(topic):
            return
        self.on_message(
            RawMqttMessage(
                topic=topic,
                payload=payload,
                retained=retained,
                received_at=utc_now_iso(),
            )
        )

    def _matches_subscription(self, topic: str) -> bool:
        for pattern in self._subscribed:
            if self._topic_matches(pattern, topic):
                return True
        return False

    @staticmethod
    def _topic_matches(pattern: str, topic: str) -> bool:
        pattern_parts = pattern.split("/")
        topic_parts = topic.split("/")
        for i, part in enumerate(pattern_parts):
            if part == "#":
                return True
            if i >= len(topic_parts):
                return False
            if part != "+" and part != topic_parts[i]:
                return False
        return len(topic_parts) == len(pattern_parts)

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def subscribed_topics(self) -> list[str]:
        return list(self._subscribed)

    def publish(self, topic: str, payload: str) -> None:
        """Only for asserting tests never call publish from collector code paths."""
        self.published.append((topic, payload))
