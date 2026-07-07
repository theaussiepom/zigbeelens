"""Dedicated publisher for topology network map requests only."""

from __future__ import annotations

import logging
import ssl
import threading
from dataclasses import dataclass, field

from zigbeelens.config.models import AppConfig
from zigbeelens.mqtt.client import parse_mqtt_server
from zigbeelens.topology.topics import validate_topology_request_topic

logger = logging.getLogger(__name__)

# Ask Zigbee2MQTT to include route-table entries in the raw map. Without
# "routes": true every link comes back with an empty routes array, which
# leaves route_count at 0 and the graph without any route-hint evidence.
NETWORKMAP_REQUEST_PAYLOAD = '{"type":"raw","routes":true}'


@dataclass
class TopologyPublishRecord:
    topic: str
    payload: str


class TopologyRequestPublisher:
    """Publish only allowlisted networkmap request topics."""

    def __init__(self, config: AppConfig) -> None:
        import paho.mqtt.client as mqtt

        self._config = config
        self._base_topics = tuple(n.base_topic for n in config.networks)
        self._records: list[TopologyPublishRecord] = []
        self._lock = threading.Lock()
        conn = parse_mqtt_server(config.mqtt.server)
        client_id = f"{config.mqtt.client_id}-topology"
        self._client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
        if config.mqtt.username:
            self._client.username_pw_set(config.mqtt.username, config.mqtt.password or None)
        if conn.use_tls or config.mqtt.tls.enabled:
            self._client.tls_set(
                cert_reqs=ssl.CERT_REQUIRED if config.mqtt.tls.reject_unauthorized else ssl.CERT_NONE
            )
        self._host = conn.host
        self._port = conn.port
        self._connected = False

    @property
    def published(self) -> list[TopologyPublishRecord]:
        with self._lock:
            return list(self._records)

    def connect(self) -> None:
        self._client.connect(self._host, self._port, keepalive=60)
        self._client.loop_start()
        self._connected = True

    def disconnect(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()
        self._connected = False

    def publish_networkmap_request(self, topic: str, payload: str = NETWORKMAP_REQUEST_PAYLOAD) -> None:
        validate_topology_request_topic(topic, allowed_base_topics=self._base_topics)
        with self._lock:
            self._records.append(TopologyPublishRecord(topic=topic, payload=payload))
        result = self._client.publish(topic, payload=payload, qos=0, retain=False)
        if result.rc != 0:
            raise RuntimeError(f"Topology request publish failed rc={result.rc}")


@dataclass
class FakeTopologyRequestPublisher:
    config: AppConfig
    published: list[TopologyPublishRecord] = field(default_factory=list)
    _base_topics: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        self._base_topics = tuple(n.base_topic for n in self.config.networks)

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def publish_networkmap_request(self, topic: str, payload: str = NETWORKMAP_REQUEST_PAYLOAD) -> None:
        validate_topology_request_topic(topic, allowed_base_topics=self._base_topics)
        self.published.append(TopologyPublishRecord(topic=topic, payload=payload))
