"""Track 4A corrective regressions: sanitized failures, MQTT SecretStr, URI redaction."""

from __future__ import annotations

import logging
import os
import traceback
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from zigbeelens.config import ConfigError, load_config, resolve_config_path
from zigbeelens.config.loader import format_validation_error, format_yaml_error
from zigbeelens.config.models import AppConfig, FeaturesConfig, MqttConfig, MqttDiscoveryConfig, SecurityConfig, ServerConfig
from zigbeelens.config.redaction import REDACTED, redact_dict_secrets, redact_mqtt_server
from zigbeelens.main import create_app
from zigbeelens.mqtt.client import PahoMqttClient
from zigbeelens.mqtt_discovery.publisher import SafeMqttPublisher
from zigbeelens.topology.publisher import TopologyRequestPublisher

REPO_ROOT = Path(__file__).resolve().parents[3]
VALID_TOKEN = "i" * 32
SHORT_TOKEN = "short-token-sentinel-xyz"
SESSION_BAD = "session-secret-sentinel-abc"
MQTT_SENTINEL = "mqtt-password-sentinel-leak"
QUERY_SECRET = "query-secret-sentinel"
TOKEN_QUERY = "query-token-sentinel"
FRAGMENT_SECRET = "fragment-secret-sentinel"


def _write_config(path: Path, body: str) -> None:
    path.write_text(body.strip() + "\n", encoding="utf-8")


def _assert_secret_absent(exc: BaseException, secret: str) -> None:
    assert secret not in str(exc)
    assert secret not in repr(exc)
    rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    assert secret not in rendered
    if len(secret) >= 12:
        assert secret[:12] not in rendered
    assert exc.__cause__ is None
    assert not isinstance(exc.__context__, ValidationError)


def test_short_yaml_api_token_absent_from_exception_chain(tmp_path: Path):
    cfg = tmp_path / "config.yaml"
    _write_config(
        cfg,
        f"""
mode:
  mock: true
networks: []
security:
  api_token: {SHORT_TOKEN}
""",
    )
    with pytest.raises(ConfigError) as exc_info:
        load_config(cfg)
    _assert_secret_absent(exc_info.value, SHORT_TOKEN)


def test_invalid_session_secret_absent_from_exception_chain(tmp_path: Path):
    cfg = tmp_path / "config.yaml"
    _write_config(
        cfg,
        f"""
mode:
  mock: true
networks: []
security:
  session_secret: {SESSION_BAD}
""",
    )
    with pytest.raises(ConfigError) as exc_info:
        load_config(cfg)
    _assert_secret_absent(exc_info.value, SESSION_BAD)


def test_invalid_mqtt_password_type_absent_from_exception_chain(tmp_path: Path):
    cfg = tmp_path / "config.yaml"
    _write_config(
        cfg,
        f"""
mode:
  mock: true
networks: []
mqtt:
  password:
    nested: {MQTT_SENTINEL}
""",
    )
    with pytest.raises(ConfigError) as exc_info:
        load_config(cfg)
    _assert_secret_absent(exc_info.value, MQTT_SENTINEL)


def test_malformed_yaml_with_token_on_line_is_sanitized(tmp_path: Path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"security:\n  api_token: {VALID_TOKEN}:\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as exc_info:
        load_config(cfg)
    text = str(exc_info.value)
    assert VALID_TOKEN not in text
    assert VALID_TOKEN[:16] not in text
    assert "line" in text.lower()
    assert "column" in text.lower()
    assert exc_info.value.__cause__ is None


def test_format_yaml_error_never_includes_source_excerpt():
    try:
        yaml.safe_load(f"security:\n  api_token: {VALID_TOKEN}:\n")
    except yaml.YAMLError as exc:
        rendered = format_yaml_error(exc)
    else:
        raise AssertionError("expected YAMLError")
    assert VALID_TOKEN not in rendered
    assert "api_token" not in rendered
    assert "line" in rendered


def test_create_app_invalid_config_does_not_emit_secret(tmp_path: Path, monkeypatch, caplog):
    cfg = tmp_path / "config.yaml"
    _write_config(
        cfg,
        f"""
mode:
  mock: true
storage:
  path: {tmp_path / "bad.sqlite"}
networks: []
security:
  api_token: {SHORT_TOKEN}
""",
    )
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    app = create_app(str(cfg))
    with caplog.at_level(logging.DEBUG), pytest.raises(ConfigError) as exc_info:
        with TestClient(app):
            pass
    _assert_secret_absent(exc_info.value, SHORT_TOKEN)
    assert SHORT_TOKEN not in caplog.text


def test_mqtt_password_masked_in_repr_and_json():
    cfg = MqttConfig(password=MQTT_SENTINEL)
    app = AppConfig(mqtt=cfg)
    assert MQTT_SENTINEL not in repr(cfg)
    assert MQTT_SENTINEL not in repr(app)
    assert MQTT_SENTINEL not in cfg.model_dump_json()
    assert MQTT_SENTINEL not in app.model_dump_json()
    redacted = redact_dict_secrets(app.model_dump(mode="python"))
    assert MQTT_SENTINEL not in str(redacted)
    assert redacted["mqtt"]["password"] == "***"


def test_empty_mqtt_password_remains_valid():
    cfg = MqttConfig()
    assert cfg.password.get_secret_value() == ""
    short = MqttConfig(password="short")
    assert short.password.get_secret_value() == "short"


def test_paho_collector_receives_unwrapped_password():
    mock_client = MagicMock()
    with patch("paho.mqtt.client.Client", return_value=mock_client):
        PahoMqttClient(
            MqttConfig(server="mqtt://localhost:1883", username="u", password=MQTT_SENTINEL),
            on_message=lambda *_a, **_k: None,
        )
    mock_client.username_pw_set.assert_called_once_with("u", MQTT_SENTINEL)


def test_paho_empty_password_becomes_none():
    mock_client = MagicMock()
    with patch("paho.mqtt.client.Client", return_value=mock_client):
        PahoMqttClient(
            MqttConfig(server="mqtt://localhost:1883", username="u", password=""),
            on_message=lambda *_a, **_k: None,
        )
    mock_client.username_pw_set.assert_called_once_with("u", None)


def test_topology_and_discovery_publishers_unwrap_password():
    mock_client = MagicMock()
    app = AppConfig(
        mqtt=MqttConfig(server="mqtt://localhost:1883", username="u", password=MQTT_SENTINEL),
        features=FeaturesConfig(mqtt_discovery=True),
        mqtt_discovery=MqttDiscoveryConfig(enabled=True),
    )
    with patch("paho.mqtt.client.Client", return_value=mock_client):
        TopologyRequestPublisher(app)
    mock_client.username_pw_set.assert_called_with("u", MQTT_SENTINEL)

    mock_client.reset_mock()
    with patch("paho.mqtt.client.Client", return_value=mock_client):
        SafeMqttPublisher(app)
    mock_client.username_pw_set.assert_called_with("u", MQTT_SENTINEL)


def test_source_and_example_defaults_are_loopback(monkeypatch):
    assert ServerConfig().host == "127.0.0.1"
    assert AppConfig().server.host == "127.0.0.1"

    example = load_config(REPO_ROOT / "examples" / "config.example.yaml")
    assert example.server.host == "127.0.0.1"

    source_config = REPO_ROOT / "config" / "config.yaml"
    assert load_config(source_config).server.host == "127.0.0.1"

    monkeypatch.delenv("ZIGBEELENS_CONFIG", raising=False)
    previous = Path.cwd()
    try:
        os.chdir(REPO_ROOT)
        selected = resolve_config_path()
        assert selected.resolve() == source_config.resolve()
        assert load_config(selected).server.host == "127.0.0.1"
    finally:
        os.chdir(previous)


def test_addon_and_docker_remain_explicitly_remote_capable():
    from zigbeelens.config.addon import options_to_app_config

    addon = options_to_app_config(
        {
            "mqtt": {"host": "core-mosquitto", "port": 1883, "username": "", "password": ""},
            "networks": [{"id": "home", "name": "Home", "base_topic": "zigbee2mqtt"}],
        }
    )
    assert addon.server.host == "0.0.0.0"

    docker = load_config(REPO_ROOT / "deploy" / "docker" / "config.example.yaml")
    assert docker.server.host == "0.0.0.0"


def test_redact_mqtt_server_query_and_fragment():
    server = (
        f"mqtt://user:password@broker:1883/path"
        f"?password={QUERY_SECRET}&token={TOKEN_QUERY}&client_id=safe"
        f"#api_key={FRAGMENT_SECRET}"
    )
    redacted = redact_mqtt_server(server, username="user")
    assert QUERY_SECRET not in redacted
    assert TOKEN_QUERY not in redacted
    assert FRAGMENT_SECRET not in redacted
    assert "client_id=safe" in redacted
    assert "broker" in redacted
    assert "1883" in redacted
    assert "user:***@" in redacted


def test_redact_mqtt_server_malformed_port_is_safe():
    assert redact_mqtt_server("mqtt://broker:notaport") == REDACTED


def test_redact_mqtt_server_hostless_userinfo_is_redacted():
    sentinel = "credential-sentinel"
    assert redact_mqtt_server(f"mqtt://user:{sentinel}@") == REDACTED
    assert sentinel not in redact_mqtt_server(f"mqtt://user:{sentinel}@")

    messy = (
        f"mqtt://user:{sentinel}@/path"
        f"?password={QUERY_SECRET}&token={TOKEN_QUERY}"
        f"#api_key={FRAGMENT_SECRET}"
    )
    redacted = redact_mqtt_server(messy, username="")
    assert redacted == REDACTED
    assert sentinel not in redacted
    assert QUERY_SECRET not in redacted
    assert TOKEN_QUERY not in redacted
    assert FRAGMENT_SECRET not in redacted


def test_redact_mqtt_server_valid_userinfo_still_useful():
    redacted = redact_mqtt_server("mqtt://user:password@broker:1883", username="user")
    assert "password" not in redacted.split("@", 1)[0] or ":***@" in redacted
    assert "user:***@" in redacted
    assert "broker" in redacted
    assert "1883" in redacted


def test_config_status_redacts_uri_query_secrets(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    client_secret = "status-client-secret"
    authorization = "status-authorization"
    network_key = "status-network-key"
    install_code = "status-install-code"
    server = (
        f"mqtt://u:userinfo-pass@broker:1883/path"
        f"?password={QUERY_SECRET}&token={TOKEN_QUERY}&client_id=safe"
        f"&client_secret={client_secret}&authorization={authorization}"
        f"&network_key={network_key}&install_code={install_code}&token_count=4"
        f"#api_key={FRAGMENT_SECRET}"
    )
    _write_config(
        cfg,
        f"""
mode:
  mock: true
storage:
  path: {tmp_path / "status.sqlite"}
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
mqtt:
  server: "{server}"
  username: u
  password: {MQTT_SENTINEL}
""",
    )
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    app = create_app(str(cfg))
    with TestClient(app) as client:
        legacy = client.get("/api/config/status")
        v1 = client.get("/api/v1/config/status")
        assert legacy.status_code == 200
        assert v1.status_code == 200
        assert legacy.json() == v1.json()
        text = legacy.text
        assert QUERY_SECRET not in text
        assert TOKEN_QUERY not in text
        assert FRAGMENT_SECRET not in text
        assert MQTT_SENTINEL not in text
        assert "userinfo-pass" not in text
        assert client_secret not in text
        assert authorization not in text
        assert network_key not in text
        assert install_code not in text
        mqtt_server = legacy.json()["mqtt_server"]
        assert "client_id=safe" in mqtt_server
        assert "token_count=4" in mqtt_server


def test_config_status_malformed_port_does_not_500(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    _write_config(
        cfg,
        f"""
mode:
  mock: true
storage:
  path: {tmp_path / "badport.sqlite"}
networks: []
mqtt:
  server: "mqtt://broker:notaport"
  username: u
""",
    )
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    app = create_app(str(cfg))
    with TestClient(app) as client:
        res = client.get("/api/config/status")
        assert res.status_code == 200
        assert res.json()["mqtt_server"] == REDACTED


def test_config_status_hostless_userinfo_is_redacted(tmp_path: Path, monkeypatch):
    sentinel = "hostless-userinfo-sentinel"
    cfg = tmp_path / "config.yaml"
    _write_config(
        cfg,
        f"""
mode:
  mock: true
storage:
  path: {tmp_path / "hostless.sqlite"}
networks: []
mqtt:
  server: "mqtt://user:{sentinel}@"
  username: ""
""",
    )
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    app = create_app(str(cfg))
    with TestClient(app) as client:
        legacy = client.get("/api/config/status")
        v1 = client.get("/api/v1/config/status")
        assert legacy.status_code == 200
        assert v1.status_code == 200
        assert legacy.json() == v1.json()
        assert legacy.json()["mqtt_server"] == REDACTED
        assert sentinel not in legacy.text


@pytest.mark.parametrize(
    "field",
    ["api_tokn", "session_secert", "modee", "api_token_file"],
)
def test_unknown_security_fields_fail_closed(tmp_path: Path, field: str):
    cfg = tmp_path / "config.yaml"
    value = VALID_TOKEN if field != "modee" else "local"
    _write_config(
        cfg,
        f"""
mode:
  mock: true
networks: []
security:
  {field}: {value}
""",
    )
    with pytest.raises(ConfigError) as exc_info:
        load_config(cfg)
    message = str(exc_info.value).lower()
    assert "extra" in message or field in message
    if field != "modee":
        _assert_secret_absent(exc_info.value, VALID_TOKEN)


@pytest.mark.parametrize(
    "control",
    [
        "\x00",
        "\t",
        "\r",
        "\n",
        "\x7f",
        "\u0085",
    ],
)
def test_security_secrets_reject_unicode_controls(control: str):
    bad = ("a" * 16) + control + ("b" * 16)
    with pytest.raises(ValidationError) as exc_info:
        SecurityConfig(api_token=bad)
    assert bad not in format_validation_error(exc_info.value)


def test_secret_file_rejects_del_and_c1_controls(tmp_path: Path, monkeypatch):
    secret_file = tmp_path / "token.txt"
    secret_file.write_text(("a" * 16) + "\x7f" + ("b" * 16), encoding="utf-8")
    cfg = tmp_path / "config.yaml"
    _write_config(cfg, "mode:\n  mock: true\nnetworks: []\n")
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN_FILE", str(secret_file))
    with pytest.raises(ConfigError, match="control characters"):
        load_config(cfg)

    secret_file.write_text(("a" * 16) + "\u0085" + ("b" * 16), encoding="utf-8")
    with pytest.raises(ConfigError, match="control characters"):
        load_config(cfg)


def test_secret_file_read_errors_have_no_byte_chain(tmp_path: Path, monkeypatch):
    secret_file = tmp_path / "token.bin"
    secret_file.write_bytes(b"\xff\xfe" + MQTT_SENTINEL.encode("ascii"))
    cfg = tmp_path / "config.yaml"
    _write_config(cfg, "mode:\n  mock: true\nnetworks: []\n")
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN_FILE", str(secret_file))
    with pytest.raises(ConfigError) as exc_info:
        load_config(cfg)
    assert MQTT_SENTINEL not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
