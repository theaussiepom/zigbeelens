"""Home Assistant add-on options → ZigbeeLens config YAML."""

from __future__ import annotations

from typing import Any

import yaml

from zigbeelens.config.models import AppConfig


def mqtt_server_uri(host: str, port: int, *, tls_enabled: bool) -> str:
    scheme = "mqtts" if tls_enabled else "mqtt"
    return f"{scheme}://{host}:{port}"


def build_mqtt_server(options: dict[str, Any]) -> str:
    mqtt = options.get("mqtt") or {}
    host = str(mqtt.get("host") or "core-mosquitto")
    port = int(mqtt.get("port") or 1883)
    tls = mqtt.get("tls") or {}
    return mqtt_server_uri(host, port, tls_enabled=bool(tls.get("enabled")))


def options_to_config_dict(options: dict[str, Any]) -> dict[str, Any]:
    """Map Home Assistant add-on options to a ZigbeeLens AppConfig-compatible dict."""
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
        "storage": {
            "path": "/data/zigbeelens/zigbeelens.sqlite",
            "retention_days": int(storage.get("retention_days") or 7),
        },
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


def safe_startup_log_lines(options: dict[str, Any]) -> list[str]:
    """Startup log lines that never include secrets."""
    cfg = options_to_config_dict(options)
    networks = cfg.get("networks") or []
    mqtt = cfg.get("mqtt") or {}
    features = cfg.get("features") or {}
    lines = [
        "ZigbeeLens add-on starting",
        f"MQTT server: {mqtt.get('server')}",
        f"Configured networks: {len(networks)}",
        f"Storage path: {cfg['storage']['path']}",
        f"MQTT collector: {features.get('mqtt_collector', True)}",
        f"Report profile: {cfg.get('reporting', {}).get('default_profile', 'standard')}",
    ]
    for net in networks:
        lines.append(f"  - {net['id']} ({net['name']}) topic={net['base_topic']}")
    return lines
