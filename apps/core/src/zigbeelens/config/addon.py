"""Home Assistant add-on options → ZigbeeLens config YAML."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from zigbeelens.config.api_token import reject_invalid_api_token
from zigbeelens.config.ingress_trust import ADDON_SUPERVISOR_INGRESS_PEER
from zigbeelens.config.models import AppConfig

ADDON_SECRETS_DIR = Path("/data/zigbeelens/secrets")
ADDON_API_TOKEN_FILE = ADDON_SECRETS_DIR / "api_token"


def mqtt_server_uri(host: str, port: int, *, tls_enabled: bool) -> str:
    scheme = "mqtts" if tls_enabled else "mqtt"
    return f"{scheme}://{host}:{port}"


def build_mqtt_server(options: dict[str, Any]) -> str:
    mqtt = options.get("mqtt") or {}
    host = str(mqtt.get("host") or "core-mosquitto")
    port = int(mqtt.get("port") or 1883)
    tls = mqtt.get("tls") or {}
    return mqtt_server_uri(host, port, tls_enabled=bool(tls.get("enabled")))


def _addon_security_block() -> dict[str, Any]:
    return {
        "mode": "home_assistant_ingress",
        "ingress_trusted_proxies": [ADDON_SUPERVISOR_INGRESS_PEER],
        "ingress_proxy_only": True,
    }


def _addon_optional_retention_days(raw: Any) -> int | None:
    """Map add-on retention days: 0 → null (retain indefinitely / manual-only)."""
    if raw is None or raw == "":
        return None
    value = int(raw)
    if value == 0:
        return None
    return value


def _addon_storage_block(storage: dict[str, Any]) -> dict[str, Any]:
    """Map add-on storage options to typed StorageConfig fields.

    Add-on sentinel ``0`` means Core ``null`` (retain indefinitely / manual-only).
    """
    block: dict[str, Any] = {
        "path": "/data/zigbeelens/zigbeelens.sqlite",
        "retention_days": int(storage.get("retention_days") or 7),
        "maintenance_interval_hours": int(storage.get("maintenance_interval_hours") or 24),
    }
    if "resolved_incident_retention_days" in storage:
        block["resolved_incident_retention_days"] = _addon_optional_retention_days(
            storage.get("resolved_incident_retention_days")
        )
    if "report_retention_days" in storage:
        block["report_retention_days"] = _addon_optional_retention_days(
            storage.get("report_retention_days")
        )
    return block


def options_to_config_dict(options: dict[str, Any]) -> dict[str, Any]:
    """Map Home Assistant add-on options to a ZigbeeLens AppConfig-compatible dict.

    The optional security.api_token is never written into generated YAML; run.sh
    installs it via ``ZIGBEELENS_SECURITY_API_TOKEN_FILE`` when present.
    """
    mqtt = options.get("mqtt") or {}
    tls = mqtt.get("tls") or {}
    storage = options.get("storage") or {}
    diagnostics = options.get("diagnostics") or {}
    reporting = options.get("reporting") or {}
    features = options.get("features") or {}
    networks = options.get("networks") or []

    if not networks:
        raise ValueError("At least one Zigbee2MQTT network must be configured.")

    return {
        "server": {"host": "0.0.0.0", "port": 8377},
        "mode": {"mock": False},
        "security": _addon_security_block(),
        "mqtt": {
            "server": build_mqtt_server(options),
            "username": mqtt.get("username") or "",
            "password": mqtt.get("password") or "",
            "client_id": "zigbeelens",
            "tls": {
                "enabled": bool(tls.get("enabled")),
                "reject_unauthorized": bool(tls.get("reject_unauthorized", True)),
            },
        },
        "networks": [
            {
                "id": str(net["id"]),
                "name": str(net.get("name") or net["id"]),
                "base_topic": str(net["base_topic"]),
            }
            for net in networks
        ],
        "storage": _addon_storage_block(storage),
        "diagnostics": diagnostics,
        "reporting": reporting,
        "features": features,
        "mqtt_discovery": options.get("mqtt_discovery") or {},
        "topology": options.get("topology") or {},
    }


def options_to_yaml(options: dict[str, Any]) -> str:
    data = options_to_config_dict(options)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def options_to_app_config(options: dict[str, Any]) -> AppConfig:
    return AppConfig.model_validate(options_to_config_dict(options))


def extract_optional_api_token(options: dict[str, Any]) -> str:
    """Return validated token or \"\" without echoing rejected values."""
    security = options.get("security") or {}
    raw = security.get("api_token", "")
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise ValueError("security.api_token must be a string")
    if raw == "":
        return ""
    return reject_invalid_api_token(raw).get_secret_value()


def install_optional_api_token_file(
    options: dict[str, Any],
    *,
    secrets_dir: Path | None = None,
    token_file: Path | None = None,
) -> bool:
    """Atomically install or remove the optional bearer secret file.

    Creates the secrets directory with mode ``0700`` and a temporary file with
    mode ``0600`` from creation (independent of umask), then ``os.replace``s to
    the final path. Returns True when a token file is active.
    """
    import tempfile

    directory = secrets_dir or ADDON_SECRETS_DIR
    path = token_file or ADDON_API_TOKEN_FILE
    token = extract_optional_api_token(options)
    if not token:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return False

    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)

    fd: int | None = None
    tmp_name: str | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=".api_token.",
            suffix=".tmp",
            dir=str(directory),
        )
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            fd = None  # ownership transferred to the file object
            handle.write(token.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
        tmp_name = None
        os.chmod(path, 0o600)
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
    return True


def safe_startup_log_lines(
    options: dict[str, Any],
    *,
    bearer_fallback_configured: bool | None = None,
) -> list[str]:
    """Startup log lines that never include secrets."""
    cfg = options_to_config_dict(options)
    networks = cfg.get("networks") or []
    mqtt = cfg.get("mqtt") or {}
    features = cfg.get("features") or {}
    security = cfg.get("security") or {}
    if bearer_fallback_configured is None:
        try:
            bearer_fallback_configured = bool(extract_optional_api_token(options))
        except ValueError:
            bearer_fallback_configured = False
    lines = [
        "ZigbeeLens add-on starting",
        f"MQTT server: {mqtt.get('server')}",
        f"Configured networks: {len(networks)}",
        f"Storage path: {cfg['storage']['path']}",
        f"MQTT collector: {features.get('mqtt_collector', True)}",
        f"Report profile: {cfg.get('reporting', {}).get('default_profile', 'standard')}",
        f"Security mode: {security.get('mode')}",
        f"Ingress proxy-only: {security.get('ingress_proxy_only')}",
        f"Direct bearer fallback configured: {bool(bearer_fallback_configured)}",
    ]
    for net in networks:
        lines.append(f"  - {net['id']} ({net['name']}) topic={net['base_topic']}")
    return lines
