"""ZigbeeLens Home Assistant integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ZigbeeLensApiClient
from .api_token import optional_core_api_token
from .const import (
    CONF_API_TOKEN,
    CONF_CORE_URL,
    CONF_PANEL_ENABLED,
    CONF_SCAN_INTERVAL,
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import ZigbeeLensDataUpdateCoordinator
from .exceptions import ZigbeeLensAuthError, ZigbeeLensInvalidResponseError
from .panel import async_register_panel, async_unregister_panel
from .repairs import async_clear_repairs, async_manage_repairs

_LOGGER = logging.getLogger(__name__)

_AUTH_FAILED_MESSAGE = "Core credentials need to be updated"


def _primary_entry_id(hass: HomeAssistant) -> str | None:
    """Deterministic primary entry when multiple unsupported entries exist."""
    entries = list(hass.config_entries.async_entries(DOMAIN) or [])
    if not entries:
        return None
    return sorted(entries, key=lambda item: item.entry_id)[0].entry_id


def _entry_owns_global_resources(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Only the primary entry may own the singleton panel/repair resources."""
    primary = _primary_entry_id(hass)
    # No known entries yet (or unreadable listing): treat current entry as owner.
    return primary is None or entry.entry_id == primary


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up ZigbeeLens from configuration.yaml (unused; config flow only)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ZigbeeLens from a config entry."""
    existing = hass.config_entries.async_entries(DOMAIN)
    owns_globals = _entry_owns_global_resources(hass, entry)
    if len(existing) > 1:
        # Unsupported multi-entry state (legacy/broken). Continue setup per entry
        # without touching other entries' runtime data or credentials.
        _LOGGER.error(
            "Multiple ZigbeeLens config entries are present; only one is supported"
        )
        if not owns_globals:
            _LOGGER.error(
                "ZigbeeLens entry is not the primary singleton owner; "
                "skipping panel and repair registration"
            )

    try:
        api_token = optional_core_api_token(entry.data.get(CONF_API_TOKEN, ""))
    except ValueError:
        raise ConfigEntryAuthFailed(_AUTH_FAILED_MESSAGE) from None

    session = async_get_clientsession(hass, verify_ssl=entry.data.get(CONF_VERIFY_SSL, False))
    try:
        client = ZigbeeLensApiClient(
            session,
            entry.data[CONF_CORE_URL],
            verify_ssl=entry.data.get(CONF_VERIFY_SSL, False),
            api_token=api_token,
        )
    except ZigbeeLensAuthError:
        raise ConfigEntryAuthFailed(_AUTH_FAILED_MESSAGE) from None
    except ZigbeeLensInvalidResponseError:
        # Fail closed without initiating HTTP or logging credential-bearing URLs.
        raise ConfigEntryError("Invalid ZigbeeLens Core URL") from None

    scan_interval = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    coordinator = ZigbeeLensDataUpdateCoordinator(hass, client, scan_interval, entry)

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator, "client": client}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if owns_globals:
        if entry.data.get(CONF_PANEL_ENABLED, True):
            await async_register_panel(hass, entry.entry_id, client.core_url)
        else:
            await async_unregister_panel(hass, entry.entry_id)

        async def _handle_coordinator_update() -> None:
            async_manage_repairs(hass, coordinator)

        entry.async_on_unload(coordinator.async_add_listener(_handle_coordinator_update))
        async_manage_repairs(hass, coordinator)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    owns_globals = _entry_owns_global_resources(hass, entry)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if owns_globals:
            await async_unregister_panel(hass, entry.entry_id)
            async_clear_repairs(hass)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry."""
    if entry.version == 1:
        return True
    return False
