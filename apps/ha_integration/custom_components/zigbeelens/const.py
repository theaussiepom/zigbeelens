"""Constants for the ZigbeeLens Home Assistant integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "zigbeelens"
MANUFACTURER = "ZigbeeLens"

CONF_CORE_URL = "core_url"
CONF_VERIFY_SSL = "verify_ssl"
CONF_PANEL_ENABLED = "panel_enabled"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_API_TOKEN = "api_token"
CONF_REMOVE_API_TOKEN = "remove_api_token"

DEFAULT_CORE_URL = "http://localhost:8377"
DEFAULT_SCAN_INTERVAL = 60
DEFAULT_VERIFY_SSL = False
DEFAULT_PANEL_ENABLED = True
DEFAULT_API_TOKEN = ""

CONFIG_ENTRY_VERSION = 1

PLATFORMS = ["binary_sensor", "sensor"]

API_TIMEOUT = 15

# Repair / issue identifiers
ISSUE_CORE_UNREACHABLE = "core_unreachable"
ISSUE_COLLECTOR_DISCONNECTED = "collector_disconnected"
ISSUE_NO_NETWORKS = "no_networks_configured"
ISSUE_NO_MQTT_DATA = "no_mqtt_data"
ISSUE_MOCK_MODE = "mock_mode_active"
ISSUE_INCOMPATIBLE_VERSION = "incompatible_core_version"
ISSUE_DECISION_CONTRACT_INCOMPATIBLE = "core_decision_contract_incompatible"

UPDATE_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

# Companion panel registration state (separate from per-entry runtime dicts).
DATA_FRONTEND_REGISTERED = "frontend_registered"
PANEL_STATE_KEY = "_panel_state"
