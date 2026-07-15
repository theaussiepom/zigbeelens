"""Collector startup/shutdown integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from zigbeelens.mqtt.collector import MqttCollector, build_collector, collector_enabled
from zigbeelens.mqtt.dashboard_scheduler import DashboardPublishScheduler
from zigbeelens.mqtt.events import EventBroadcaster
from zigbeelens.mqtt.ingestion import MqttIngestionService

if TYPE_CHECKING:
    from zigbeelens.app.context import AppContext

logger = logging.getLogger(__name__)


def create_broadcaster() -> EventBroadcaster:
    return EventBroadcaster()


def start_collector(ctx: AppContext, broadcaster: EventBroadcaster) -> MqttCollector | None:
    if not collector_enabled(ctx.config):
        logger.info("MQTT collector disabled (mock=%s)", ctx.config.mode.mock)
        ctx.repo.update_collector_status(enabled=False, connected=False, subscribed_topics_count=0)
        return None

    dashboard_scheduler = DashboardPublishScheduler(ctx, broadcaster)
    ctx.dashboard_scheduler = dashboard_scheduler

    def on_dashboard_update(_event_type: str, _network_id: str) -> None:
        dashboard_scheduler.schedule()

    def on_health_recalc(network_id: str, ieee_address: str | None = None) -> None:
        if ctx.evaluation is None:
            return
        if ieee_address:
            ctx.evaluation.evaluate_device(network_id, ieee_address)
        elif network_id:
            ctx.evaluation.evaluate_network(network_id)
        else:
            ctx.evaluation.evaluate_all()

    ingestion = MqttIngestionService(
        ctx.config,
        ctx.repo,
        on_dashboard_update=on_dashboard_update,
        on_health_recalc=on_health_recalc,
    )
    collector = build_collector(
        ctx.config,
        ctx.repo,
        ingestion,
        on_status_change=lambda: broadcaster.publish_sync(
            "collector_status",
            {"type": "collector_status", "status": collector_status_dict(ctx)},
        ),
    )
    try:
        collector.start()
        broadcaster.publish_sync("collector_connected", {"type": "collector_connected"})
    except Exception:
        logger.exception("MQTT collector failed to start; continuing without live MQTT")
        return collector
    return collector


def stop_collector(collector: MqttCollector | None, broadcaster: EventBroadcaster) -> None:
    if collector is None:
        return
    try:
        collector.stop()
    finally:
        broadcaster.publish_sync("collector_disconnected", {"type": "collector_disconnected"})


def _public_last_error(last_error: str | None) -> str | None:
    return "[redacted]" if last_error else None


def collector_status_dict(ctx: AppContext) -> dict:
    if ctx.collector is not None:
        status = ctx.collector.status()
        return {
            "enabled": status.enabled,
            "connected": status.connected,
            "subscribed_topics_count": status.subscribed_topics_count,
            "last_message_at": status.last_message_at,
            "last_error": _public_last_error(status.last_error),
            "networks": [
                {"network_id": n.network_id, "subscribed": n.subscribed} for n in status.networks
            ],
        }
    row = ctx.repo.get_collector_status() or {}
    return {
        "enabled": bool(row.get("enabled")),
        "connected": bool(row.get("connected")),
        "subscribed_topics_count": int(row.get("subscribed_topics_count") or 0),
        "last_message_at": row.get("last_message_at"),
        "last_error": _public_last_error(row.get("last_error")),
    }
