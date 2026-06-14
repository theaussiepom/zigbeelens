"""Multi-network MQTT collector coordinator."""

from __future__ import annotations

import logging
from typing import Callable

from zigbeelens.config.models import AppConfig
from zigbeelens.mqtt.client import MqttClientBase, PahoMqttClient
from zigbeelens.mqtt.ingestion import MqttIngestionService
from zigbeelens.mqtt.models import MqttCollectorStatus, NetworkSubscriptionStatus, RawMqttMessage
from zigbeelens.mqtt.normalizer import normalize_message
from zigbeelens.mqtt.topics import subscription_topics
from zigbeelens.storage.repository import Repository, utc_now_iso

logger = logging.getLogger(__name__)


class MqttCollector:
    def __init__(
        self,
        config: AppConfig,
        repo: Repository,
        ingestion: MqttIngestionService,
        client: MqttClientBase | None = None,
        on_status_change: Callable[[], None] | None = None,
    ) -> None:
        self.config = config
        self.repo = repo
        self.ingestion = ingestion
        self._on_status_change = on_status_change
        self._client = client or PahoMqttClient(config.mqtt, self._handle_message)
        self._networks = config.networks

    def start(self) -> None:
        topics: list[str] = []
        include_topology = self.config.topology.enabled
        for network in self._networks:
            topics.extend(
                subscription_topics(network.base_topic, include_topology_response=include_topology)
            )
        topics = list(dict.fromkeys(topics))
        try:
            self._client.connect()
            self._client.subscribe(topics)
            self.repo.update_collector_status(
                enabled=True,
                connected=self._client.connected,
                subscribed_topics_count=len(topics),
                last_error=None,
            )
            logger.info("MQTT collector subscribed to %d topics", len(topics))
            self._notify_status()
        except Exception as exc:
            logger.exception("MQTT collector failed to start")
            self.repo.update_collector_status(
                enabled=True,
                connected=False,
                subscribed_topics_count=len(topics),
                last_error=str(exc),
            )
            self._notify_status()
            raise

    def stop(self) -> None:
        try:
            self._client.disconnect()
        finally:
            self.repo.update_collector_status(
                enabled=False,
                connected=False,
                subscribed_topics_count=0,
            )
            self._notify_status()

    def _handle_message(self, message: RawMqttMessage) -> None:
        from zigbeelens.topology.service import get_topology_service

        topology = get_topology_service()
        if topology is not None and topology.try_handle_response(message):
            self.repo.update_collector_status(
                enabled=True,
                connected=self._client.connected,
                subscribed_topics_count=len(self._client.subscribed_topics),
                last_message_at=utc_now_iso(),
            )
            self._notify_status()
            return

        events = normalize_message(
            message,
            self._networks,
            bridge_logs_enabled=self.config.features.bridge_logs,
        )
        for event in events:
            self.ingestion.ingest(event)
        self.repo.update_collector_status(
            enabled=True,
            connected=self._client.connected,
            subscribed_topics_count=len(self._client.subscribed_topics),
            last_message_at=utc_now_iso(),
        )
        self._notify_status()

    def status(self) -> MqttCollectorStatus:
        row = self.repo.get_collector_status()
        networks = [
            NetworkSubscriptionStatus(
                network_id=n.id,
                base_topic=n.base_topic,
                subscribed=self._client.connected,
            )
            for n in self._networks
        ]
        if not row:
            return MqttCollectorStatus(enabled=False, networks=networks)
        return MqttCollectorStatus(
            enabled=bool(row.get("enabled")),
            connected=bool(row.get("connected")),
            subscribed_topics_count=int(row.get("subscribed_topics_count") or 0),
            last_message_at=row.get("last_message_at"),
            last_error=row.get("last_error"),
            networks=networks,
        )

    def _notify_status(self) -> None:
        if self._on_status_change:
            self._on_status_change()


def collector_enabled(config: AppConfig) -> bool:
    if not config.features.mqtt_collector:
        return False
    if config.mode.mock:
        return False
    return bool(config.mqtt.server.strip())


def build_collector(
    config: AppConfig,
    repo: Repository,
    ingestion: MqttIngestionService,
    *,
    client: MqttClientBase | None = None,
    on_status_change: Callable[[], None] | None = None,
) -> MqttCollector:
    return MqttCollector(config, repo, ingestion, client=client, on_status_change=on_status_change)
