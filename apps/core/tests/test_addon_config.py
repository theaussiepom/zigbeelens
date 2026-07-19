"""Home Assistant add-on config generation tests."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
import yaml

from zigbeelens.config.addon import (
    build_mqtt_server,
    extract_optional_api_token,
    install_optional_api_token_file,
    mqtt_server_uri,
    options_to_app_config,
    options_to_config_dict,
    options_to_yaml,
    safe_startup_log_lines,
)
from zigbeelens.config.ingress_trust import ADDON_SUPERVISOR_INGRESS_PEER
from zigbeelens.config.security_types import SecurityMode

VALID_TOKEN = "d" * 32


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


def test_generated_security_is_home_assistant_ingress():
    cfg = options_to_config_dict(_sample_options())
    assert cfg["security"]["mode"] == "home_assistant_ingress"
    assert cfg["security"]["ingress_trusted_proxies"] == [ADDON_SUPERVISOR_INGRESS_PEER]
    assert cfg["security"]["ingress_proxy_only"] is True
    assert "api_token" not in cfg["security"]
    assert ADDON_SUPERVISOR_INGRESS_PEER == "172.30.32.2"


def test_options_to_yaml_roundtrip_omits_api_token():
    opts = _sample_options(security={"api_token": VALID_TOKEN})
    raw = options_to_yaml(opts)
    parsed = yaml.safe_load(raw)
    assert parsed["mqtt"]["password"] == "secret-pass"
    assert parsed["networks"][1]["id"] == "shed"
    assert "api_token" not in raw
    assert VALID_TOKEN not in raw
    assert parsed["security"]["mode"] == "home_assistant_ingress"
    assert parsed["security"]["ingress_trusted_proxies"] == ["172.30.32.2"]


def test_options_to_app_config_validates_ingress():
    cfg = options_to_app_config(_sample_options())
    assert cfg.mode.mock is False
    assert cfg.mqtt.password.get_secret_value() == "secret-pass"
    assert len(cfg.networks) == 2
    assert cfg.server.host == "0.0.0.0"
    assert cfg.security.mode is SecurityMode.home_assistant_ingress
    assert cfg.security.api_token is None
    assert cfg.security.ingress_trusted_proxies == ("172.30.32.2",)
    assert cfg.security.ingress_proxy_only is True


def test_requires_at_least_one_network():
    with pytest.raises(ValueError, match="At least one"):
        options_to_config_dict(_sample_options(networks=[]))


def test_safe_startup_log_never_includes_password_or_token():
    logs = "\n".join(
        safe_startup_log_lines(
            _sample_options(security={"api_token": VALID_TOKEN}),
            bearer_fallback_configured=True,
        )
    )
    assert "secret-pass" not in logs
    assert VALID_TOKEN not in logs
    assert "core-mosquitto" in logs
    assert "/data/zigbeelens/zigbeelens.sqlite" in logs
    assert "home" in logs
    assert "Security mode: home_assistant_ingress" in logs
    assert "Ingress proxy-only: True" in logs
    assert "Direct bearer fallback configured: True" in logs
    assert "172.30.32.2" not in logs


def test_optional_api_token_file_install_and_remove(tmp_path: Path):
    secrets = tmp_path / "secrets"
    token_file = secrets / "api_token"
    opts = _sample_options(security={"api_token": VALID_TOKEN})
    assert install_optional_api_token_file(
        opts, secrets_dir=secrets, token_file=token_file
    )
    assert token_file.read_text(encoding="utf-8") == VALID_TOKEN
    mode = stat.S_IMODE(token_file.stat().st_mode)
    assert mode == 0o600

    blank = _sample_options(security={"api_token": ""})
    assert not install_optional_api_token_file(
        blank, secrets_dir=secrets, token_file=token_file
    )
    assert not token_file.exists()


def test_malformed_optional_token_rejected_without_echo():
    with pytest.raises(ValueError):
        extract_optional_api_token(
            _sample_options(security={"api_token": "short-bad-token"})
        )


def test_generated_config_is_live_mode():
    cfg = options_to_config_dict(_sample_options())
    assert cfg["mode"]["mock"] is False


def test_options_json_fixture():
    raw = json.dumps(_sample_options())
    cfg = options_to_config_dict(json.loads(raw))
    assert cfg["mqtt"]["username"] == "zigbeelens"


def test_addon_config_yaml_panel_admin_and_ingress_stream():
    addon_cfg = Path(__file__).resolve().parents[2] / "addon" / "zigbeelens" / "config.yaml"
    raw = yaml.safe_load(addon_cfg.read_text(encoding="utf-8"))
    assert raw["panel_admin"] is True
    assert raw["ingress"] is True
    assert raw["ingress_stream"] is True
    assert raw["ingress_port"] == 8377
    assert raw["ports"] == {}
    assert raw["host_network"] is False
    assert raw["hassio_api"] is False
    assert raw["homeassistant_api"] is False
    assert raw["options"]["security"]["api_token"] == ""
    assert "api_token" in raw["schema"]["security"]
