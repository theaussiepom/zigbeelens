"""Home Assistant add-on config generation tests."""

from __future__ import annotations

import json

import pytest
import yaml

from zigbeelens.config.addon import (
    build_mqtt_server,
    mqtt_server_uri,
    options_to_app_config,
    options_to_config_dict,
    options_to_yaml,
    safe_startup_log_lines,
)


def _sample_options(**overrides) -> dict:
    base = {
        "mqtt": {
            "host": "core-mosquitto",
            "port": 1883,
            "username": "zigbeelens",
            "password": "secret-pass",
            "tls": {"enabled": False, "reject_unauthorized": True},
        },
        "networks": [
            {"id": "home", "name": "Home", "base_topic": "zigbee2mqtt"},
            {"id": "shed", "name": "Shed", "base_topic": "zigbee2mqtt-shed"},
        ],
        "storage": {"retention_days": 14},
        "diagnostics": {"stale_after_hours": 48},
        "reporting": {"default_profile": "public_safe", "max_recent_events": 50},
        "features": {
            "mqtt_collector": True,
            "mqtt_discovery": False,
            "bridge_logs": True,
            "device_payload_history": True,
            "manual_network_map": False,
            "automatic_network_map": False,
        },
    }
    base.update(overrides)
    return base


def test_mqtt_uri_plain_and_tls():
    assert mqtt_server_uri("broker.local", 1883, tls_enabled=False) == "mqtt://broker.local:1883"
    assert mqtt_server_uri("broker.local", 8883, tls_enabled=True) == "mqtts://broker.local:8883"


def test_build_mqtt_server_from_options():
    opts = _sample_options()
    assert build_mqtt_server(opts) == "mqtt://core-mosquitto:1883"
    opts["mqtt"]["tls"]["enabled"] = True
    opts["mqtt"]["port"] = 8883
    assert build_mqtt_server(opts) == "mqtts://core-mosquitto:8883"


def test_options_to_config_dict_maps_networks_and_storage():
    cfg = options_to_config_dict(_sample_options())
    assert cfg["mode"]["mock"] is False
    assert cfg["server"]["port"] == 8377
    assert cfg["storage"]["path"] == "/data/zigbeelens/zigbeelens.sqlite"
    assert cfg["storage"]["retention_days"] == 14
    assert len(cfg["networks"]) == 2
    assert cfg["networks"][0]["base_topic"] == "zigbee2mqtt"
    assert cfg["features"]["mqtt_discovery"] is False
    assert cfg["reporting"]["default_profile"] == "public_safe"


def test_options_to_yaml_roundtrip():
    opts = _sample_options()
    parsed = yaml.safe_load(options_to_yaml(opts))
    assert parsed["mqtt"]["password"] == "secret-pass"
    assert parsed["networks"][1]["id"] == "shed"


def test_options_to_app_config_validates():
    cfg = options_to_app_config(_sample_options())
    assert cfg.mode.mock is False
    assert cfg.mqtt.password.get_secret_value() == "secret-pass"
    assert len(cfg.networks) == 2
    assert cfg.server.host == "0.0.0.0"
    assert cfg.security.mode.value == "local"
    assert cfg.security.api_token is None


def test_requires_at_least_one_network():
    with pytest.raises(ValueError, match="At least one"):
        options_to_config_dict(_sample_options(networks=[]))


def test_safe_startup_log_never_includes_password():
    logs = "\n".join(safe_startup_log_lines(_sample_options()))
    assert "secret-pass" not in logs
    assert "core-mosquitto" in logs
    assert "/data/zigbeelens/zigbeelens.sqlite" in logs
    assert "home" in logs


def test_generated_config_is_live_mode():
    cfg = options_to_config_dict(_sample_options())
    assert cfg["mode"]["mock"] is False


def test_options_json_fixture():
    raw = json.dumps(_sample_options())
    cfg = options_to_config_dict(json.loads(raw))
    assert cfg["mqtt"]["username"] == "zigbeelens"
