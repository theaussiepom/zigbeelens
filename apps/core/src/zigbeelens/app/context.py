"""Application bootstrap and shared runtime context."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from zigbeelens.config import AppConfig, ConfigError, load_effective_config
from zigbeelens.config.security_status import log_security_posture
from zigbeelens.db.connection import Database
from zigbeelens.diagnostics.coordinator import EvaluationCoordinator, PeriodicEvaluationScheduler
from zigbeelens.diagnostics.incidents.service import IncidentDiagnosticService
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.mqtt.events import EventBroadcaster
from zigbeelens.mqtt.lifecycle import create_broadcaster, start_collector, stop_collector
from zigbeelens.mqtt_discovery import start_discovery, stop_discovery
from zigbeelens.topology import start_topology, stop_topology
from zigbeelens.services.data_service import DataService
from zigbeelens.storage.repository import Repository
from zigbeelens.storage.retention import enforce_storage_retention

from zigbeelens.security.browser_sessions import BrowserSessionManager

if TYPE_CHECKING:
    from zigbeelens.mqtt.collector import MqttCollector
    from zigbeelens.mqtt.dashboard_scheduler import DashboardPublishScheduler
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
    session_manager: BrowserSessionManager = field(repr=False)
    evaluation: EvaluationCoordinator | None = None
    evaluation_scheduler: PeriodicEvaluationScheduler | None = None
    collector: MqttCollector | None = None
    discovery: MqttDiscoveryService | None = None
    dashboard_scheduler: DashboardPublishScheduler | None = None
    config_path: str | None = None
    started_at: float = field(default_factory=time.time)
    config_loaded: bool = True
    migration_version: int = 0

    def uptime_seconds(self) -> int:
        return int(time.time() - self.started_at)

    def close(self) -> None:
        stop_topology()
        stop_collector(self.collector, self.broadcaster)
        if self.evaluation_scheduler is not None:
            self.evaluation_scheduler.stop(wait=True)
        if self.dashboard_scheduler is not None:
            self.dashboard_scheduler.cancel()
        stop_discovery(self.discovery)
        self.db.close()


_context: AppContext | None = None


def _schedule_dashboard(ctx: AppContext, event_type: str) -> None:
    ctx.broadcaster.publish_sync(event_type, {"type": event_type})
    _schedule_dashboard_only(ctx)


def _schedule_dashboard_only(ctx: AppContext) -> None:
    if ctx.dashboard_scheduler is not None:
        ctx.dashboard_scheduler.schedule()
        return
    dashboard = ctx.data.dashboard()
    ctx.broadcaster.publish_dashboard_update(dashboard.model_dump_json())
    if ctx.discovery is not None:
        ctx.discovery.schedule_update()


def _on_health_update(ctx: AppContext, event_type: str) -> None:
    _schedule_dashboard(ctx, event_type)


def _on_incident_update(ctx: AppContext, event_type: str) -> None:
    _schedule_dashboard(ctx, event_type)


def bootstrap(config_path: str | None = None, config: AppConfig | None = None) -> AppContext:
    global _context
    if config is None:
        cfg = load_effective_config(config_path)
        path = str(config_path) if config_path else None
    else:
        cfg = config
        path = str(config_path) if config_path else None

    db = Database(cfg.storage.path)
    migration_version = db.migrate()
    repo = Repository(db)
    enforce_storage_retention(repo, cfg.storage.retention_days)
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
        session_manager=BrowserSessionManager.from_config(cfg),
        config_path=path,
        migration_version=migration_version,
    )

    incidents = IncidentDiagnosticService(cfg, repo, on_update=None)

    health = HealthDiagnosticService(cfg, repo, on_update=None)
    ctx.health = health
    ctx.incidents = incidents
    ctx.evaluation = EvaluationCoordinator(
        health,
        incidents,
        on_event=lambda event_type: ctx.broadcaster.publish_sync(event_type, {"type": event_type}),
        on_dashboard_required=lambda: _schedule_dashboard_only(ctx),
    )
    ctx.data = DataService(cfg, repo, health, incidents, ctx.evaluation)
    if repo.has_collected_data():
        ctx.evaluation.evaluate_all()

    ctx.collector = start_collector(ctx, broadcaster)
    ctx.discovery = start_discovery(ctx)
    start_topology(ctx)
    ctx.evaluation_scheduler = PeriodicEvaluationScheduler(ctx.evaluation) if ctx.evaluation else None
    if ctx.evaluation_scheduler is not None and not cfg.mode.mock:
        ctx.evaluation_scheduler.start()
    _context = ctx
    logger.info(
        "ZigbeeLens ready (mock=%s, collector=%s, db=%s, migration=%d)",
        cfg.mode.mock,
        ctx.collector is not None,
        cfg.storage.path,
        migration_version,
    )
    log_security_posture(cfg)
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
