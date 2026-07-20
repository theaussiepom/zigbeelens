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
from zigbeelens.storage.integrity import StorageIntegrityError, run_startup_integrity_gates
from zigbeelens.storage.maintenance import (
    mark_interrupted_maintenance_status,
    run_storage_maintenance,
)
from zigbeelens.storage.maintenance_scheduler import (
    StorageMaintenanceScheduler,
    publish_maintenance_side_effects,
)
from zigbeelens.storage.repository import Repository

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
    storage_scheduler: StorageMaintenanceScheduler | None = None
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
        # Stop storage maintenance first so its completion callback still sees a
        # coherent application context (topology/collector still available).
        if self.storage_scheduler is not None:
            self.storage_scheduler.stop(wait=True)
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


def _on_storage_maintenance(ctx: AppContext, result) -> None:
    publish_maintenance_side_effects(
        result,
        publish_sync=ctx.broadcaster.publish_sync,
        schedule_dashboard=lambda: _schedule_dashboard_only(ctx),
    )


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
    try:
        integrity_results = run_startup_integrity_gates(db)
    except StorageIntegrityError:
        db.close()
        logger.error("Storage integrity check failed; refusing destructive startup services")
        raise

    repo = Repository(db)
    mark_interrupted_maintenance_status(repo)
    try:
        previous = repo.maintenance.get_maintenance_setting() or {}
        integrity_payload = dict(previous.get("integrity") or {})
        for item in integrity_results:
            key = "quick_check" if item.kind == "quick" else "foreign_key_check"
            integrity_payload[key] = {
                "status": "ok" if item.ok else "failed",
                "checked_at": item.checked_at,
                "violation_count": item.violation_count,
            }
        previous["integrity"] = integrity_payload
        with repo.transaction():
            repo.maintenance.set_maintenance_setting(previous)
    except Exception:
        logger.error("Storage integrity status persistence failed safely")
    maintenance_result = run_storage_maintenance(repo, cfg)
    if not maintenance_result.success and maintenance_result.error_code == "integrity_check_failed":
        db.close()
        raise StorageIntegrityError("foreign_key_check")

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
    from zigbeelens.topology.service import get_topology_service

    def _active_pending_snapshot_id() -> str | None:
        service = get_topology_service()
        return None if service is None else service.active_pending_snapshot_id

    ctx.storage_scheduler = StorageMaintenanceScheduler(
        repo,
        cfg,
        on_result=lambda result: _on_storage_maintenance(ctx, result),
        active_pending_provider=_active_pending_snapshot_id,
    )
    if not cfg.mode.mock:
        ctx.storage_scheduler.start()
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
