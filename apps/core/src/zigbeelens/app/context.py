"""Application bootstrap and shared runtime context."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from zigbeelens.config import AppConfig, ConfigError, load_config
from zigbeelens.db.connection import Database
from zigbeelens.diagnostics.incidents.service import IncidentDiagnosticService
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.mqtt.events import EventBroadcaster
from zigbeelens.mqtt.lifecycle import create_broadcaster, start_collector, stop_collector
from zigbeelens.mqtt_discovery import start_discovery, stop_discovery
from zigbeelens.topology import start_topology
from zigbeelens.services.data_service import DataService
from zigbeelens.storage.repository import Repository

if TYPE_CHECKING:
    from zigbeelens.mqtt.collector import MqttCollector
    from zigbeelens.mqtt_discovery.service import MqttDiscoveryService

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    config: AppConfig
    db: Database
    repo: Repository
    data: DataService
    health: HealthDiagnosticService
    incidents: IncidentDiagnosticService
    broadcaster: EventBroadcaster
    collector: MqttCollector | None = None
    discovery: MqttDiscoveryService | None = None
    config_path: str | None = None
    started_at: float = field(default_factory=time.time)
    config_loaded: bool = True
    migration_version: int = 0

    def uptime_seconds(self) -> int:
        return int(time.time() - self.started_at)

    def close(self) -> None:
        stop_discovery(self.discovery)
        stop_collector(self.collector, self.broadcaster)
        self.db.close()


_context: AppContext | None = None


def _notify_discovery(ctx: AppContext) -> None:
    if ctx.discovery is not None:
        ctx.discovery.schedule_update()


def _on_health_update(ctx: AppContext, broadcaster: EventBroadcaster, event_type: str) -> None:
    broadcaster.publish_sync(event_type, {"type": event_type})
    dashboard = ctx.data.dashboard()
    broadcaster.publish_dashboard_update(dashboard.model_dump_json())
    _notify_discovery(ctx)


def _on_incident_update(ctx: AppContext, broadcaster: EventBroadcaster, event_type: str) -> None:
    broadcaster.publish_sync(event_type, {"type": event_type})
    dashboard = ctx.data.dashboard()
    broadcaster.publish_dashboard_update(dashboard.model_dump_json())
    _notify_discovery(ctx)


def bootstrap(config_path: str | None = None, config: AppConfig | None = None) -> AppContext:
    global _context
    if config is None:
        cfg = load_config(config_path)
        path = str(config_path) if config_path else None
    else:
        cfg = config
        path = None

    db = Database(cfg.storage.path)
    migration_version = db.migrate()
    repo = Repository(db)
    repo.sync_networks(cfg.networks)

    broadcaster = create_broadcaster()
    ctx = AppContext(
        config=cfg,
        db=db,
        repo=repo,
        data=None,  # type: ignore[arg-type]
        health=None,  # type: ignore[arg-type]
        incidents=None,  # type: ignore[arg-type]
        broadcaster=broadcaster,
        config_path=path,
        migration_version=migration_version,
    )

    def incident_callback(event_type: str) -> None:
        _on_incident_update(ctx, broadcaster, event_type)

    incidents = IncidentDiagnosticService(cfg, repo, on_update=incident_callback)

    def health_callback(event_type: str) -> None:
        ctx.incidents.correlate_and_sync(ctx.health)
        _on_health_update(ctx, broadcaster, event_type)

    health = HealthDiagnosticService(cfg, repo, on_update=health_callback)
    if repo.has_collected_data():
        health.recalculate_all()
        incidents.correlate_and_sync(health)

    ctx.health = health
    ctx.incidents = incidents
    ctx.data = DataService(cfg, repo, health, incidents)
    ctx.collector = start_collector(ctx, broadcaster)
    ctx.discovery = start_discovery(ctx)
    start_topology(ctx)
    _context = ctx
    logger.info(
        "ZigbeeLens ready (mock=%s, collector=%s, db=%s, migration=%d)",
        cfg.mode.mock,
        ctx.collector is not None,
        cfg.storage.path,
        migration_version,
    )
    return ctx


def get_context() -> AppContext:
    if _context is None:
        raise RuntimeError("Application context not initialized")
    return _context


def reset_context() -> None:
    global _context
    if _context is not None:
        _context.close()
    _context = None


__all__ = ["AppContext", "ConfigError", "bootstrap", "get_context", "reset_context"]
