"""Read-only summary endpoints for capabilities and service status."""

from __future__ import annotations

from typing import Any

from zigbeelens import __version__
from zigbeelens.app.context import AppContext
from zigbeelens.mqtt.collector import collector_enabled
from zigbeelens.mqtt.lifecycle import collector_status_dict
from zigbeelens.mqtt_discovery import discovery_enabled


# Stable contract version for HACS / companion decision surfaces (Phase 5E).
# Bump only when companion-facing decision fields change incompatibly.
DECISION_CONTRACT_VERSION = 1


def capabilities_dict(ctx: AppContext) -> dict[str, Any]:
    config = ctx.config
    return {
        "product": "zigbeelens",
        "version": __version__,
        "decision_contract_version": DECISION_CONTRACT_VERSION,
        "capabilities": {
            "dashboard": True,
            "sse": True,
            "reports": True,
            "mqtt_discovery": bool(config.features.mqtt_discovery),
            "home_assistant_enrichment": True,
            "topology": bool(config.topology.enabled),
            "mock_scenarios": True,
            "read_only_observability": True,
            "mqtt_collector": collector_enabled(config),
            # Coded Decision Engine payloads on dashboard / device / report APIs.
            "shared_decisions": True,
            # Companion may consume Overview-aligned decision summaries when True.
            "companion_decision_summary": True,
            # Auth surface support (not whether a token is currently configured).
            "bearer_authentication": True,
            "browser_session_authentication": True,
            "csrf_protection": True,
            "home_assistant_ingress_identity": False,
        },
        "decision_surfaces": {
            "dashboard_investigation_priorities": True,
            "dashboard_data_coverage_warnings": True,
            "device_story": True,
            "report_device_stories": True,
        },
    }


def service_status_dict(ctx: AppContext) -> dict[str, Any]:
    db_ok = ctx.db.ping()
    collector = collector_status_dict(ctx)
    networks = ctx.repo.list_networks()

    bridge_seen = any(n.bridge_state not in {"", "unknown"} for n in networks)
    coordinator_seen = any(
        (snap := ctx.repo.get_latest_bridge_snapshot(n.id)) and snap.get("coordinator_ieee")
        for n in networks
    )

    reports = ctx.repo.reports.list_reports(limit=1)
    last_generated_at = reports[0].generated_at if reports else None

    status = "ok"
    if not db_ok or not ctx.config_loaded:
        status = "degraded"
    elif (
        collector.get("enabled")
        and not collector.get("connected")
        and not ctx.config.mode.mock
    ):
        status = "degraded"

    mqtt_status: dict[str, Any] = {
        "enabled": bool(collector.get("enabled")),
        "connected": bool(collector.get("connected")),
        "last_message_at": collector.get("last_message_at"),
        "subscribed_topics_count": collector.get("subscribed_topics_count"),
        "devices_seen": ctx.repo.count_devices(),
        "events_stored": ctx.repo.count_events(),
    }

    zigbee2mqtt_status: dict[str, Any] = {
        "networks_configured": len(ctx.config.networks),
        "bridge_seen": bridge_seen,
        "coordinator_seen": coordinator_seen,
        "networks": [
            {
                "network_id": network.id,
                "bridge_state": network.bridge_state,
                "devices_seen": ctx.repo.count_devices_for_network(network.id),
            }
            for network in networks
        ],
    }

    return {
        "product": "zigbeelens",
        "version": __version__,
        "status": status,
        "data_mode": "mock" if ctx.config.mode.mock else "live",
        "uptime_seconds": ctx.uptime_seconds(),
        "collectors": {
            "mqtt": mqtt_status,
            "zigbee2mqtt": zigbee2mqtt_status,
        },
        "storage": {
            "available": db_ok,
            "ready": ctx.db.path.exists(),
        },
        "reports": {
            "available": True,
            "last_generated_at": last_generated_at,
        },
        "mqtt_discovery": {
            "enabled": discovery_enabled(ctx.config),
        },
    }
