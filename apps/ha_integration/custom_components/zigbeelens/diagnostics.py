"""Diagnostics for ZigbeeLens integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_API_TOKEN, DOMAIN
from .coordinator import ZigbeeLensDataUpdateCoordinator
from .core_origin import InvalidCoreOrigin, canonicalize_core_origin


def _redact_url(url: str) -> str:
    """Redact userinfo from MQTT/broker URLs (not used for Core URL projection)."""
    if "@" not in url:
        return url
    scheme, _, rest = url.partition("://")
    if "@" in rest:
        _, _, hostpart = rest.rpartition("@")
        return f"{scheme}://[redacted]@{hostpart}"
    return url


def _diagnostic_core_url(raw: object) -> str:
    """Project Core URL for diagnostics: canonical origin or fixed invalid marker."""
    if not isinstance(raw, str) or not raw:
        return "[invalid]"
    try:
        return canonicalize_core_origin(raw)
    except InvalidCoreOrigin:
        return "[invalid]"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator: ZigbeeLensDataUpdateCoordinator | None = runtime.get("coordinator")
    data = coordinator.data if coordinator and coordinator.data else None

    health = dict(data.health) if data else {}
    config_status = dict(data.config_status) if data else {}
    if "mqtt_server" in config_status:
        config_status["mqtt_server"] = _redact_url(str(config_status["mqtt_server"]))

    collector = dict(health.get("collector") or {})
    if collector.get("last_error"):
        collector["last_error"] = "[redacted]"

    registry = er.async_get(hass)
    entity_count = len(er.async_entries_for_config_entry(registry, entry.entry_id))

    token = entry.data.get(CONF_API_TOKEN, "")
    api_token_configured = isinstance(token, str) and bool(token)

    return {
        "integration_version": entry.version,
        "core_url": _diagnostic_core_url(entry.data.get("core_url", "")),
        "api_token_configured": api_token_configured,
        "core_reachable": bool(coordinator and coordinator.last_update_success),
        "core_version": data.core_version if data else None,
        "decision_contract_version": data.decision_contract_version if data else 0,
        "shared_decisions_available": data.shared_decisions_available if data else False,
        "core_version_compatible": data.core_version_compatible if data else None,
        "last_update_success": coordinator.last_update_success if coordinator else False,
        "last_exception": coordinator.last_exception if coordinator else None,
        "collector_connected": data.collector_connected if data else None,
        "health": {
            "status": health.get("status"),
            "version": health.get("version"),
            "mock_mode": health.get("mock_mode"),
            "database": health.get("database"),
            "migration_version": health.get("migration_version"),
            "collector": collector,
        },
        "config_status": {
            "data_mode": config_status.get("data_mode"),
            "mock_mode": config_status.get("mock_mode"),
            "mqtt_connected": config_status.get("mqtt_connected"),
            "configured_networks": len(config_status.get("configured_networks") or []),
            "storage_ready": config_status.get("storage_ready"),
        },
        "entity_count": entity_count,
    }
