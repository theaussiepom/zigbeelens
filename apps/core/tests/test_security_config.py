"""Track 4A typed security configuration and secret-source resolution."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

from zigbeelens.config import ConfigError, load_config
from zigbeelens.config.loader import format_validation_error
from zigbeelens.config.models import AppConfig, SecurityConfig, SecurityMode, ServerConfig
from zigbeelens.config.security_types import is_loopback_bind

VALID_TOKEN = "a" * 32
VALID_TOKEN_B = "b" * 32
SHORT_TOKEN = "short-token-value"


def _write_base_config(path: Path, extra: str = "") -> None:
    path.write_text(
        f"""
mode:
  mock: true
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
{extra}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_default_security_mode_and_host():
    config = AppConfig()
    assert config.security.mode is SecurityMode.local
    assert config.security.api_token is None
    assert config.security.session_secret is None
    assert config.server.host == "127.0.0.1"
    assert ServerConfig().host == "127.0.0.1"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("local", SecurityMode.local),
        ("authenticated", SecurityMode.authenticated),
        ("home_assistant_ingress", SecurityMode.home_assistant_ingress),
    ],
)
def test_security_modes_parse(value: str, expected: SecurityMode):
    if expected is SecurityMode.local:
        cfg = SecurityConfig(mode=value)
    elif expected is SecurityMode.home_assistant_ingress:
        cfg = SecurityConfig(
            mode=value,
            ingress_trusted_proxies=["172.30.32.2"],
        )
    else:
        cfg = SecurityConfig(mode=value, api_token=VALID_TOKEN)
    assert cfg.mode is expected


def test_invalid_security_mode_fails_safely():
    with pytest.raises(ValidationError) as exc_info:
        SecurityConfig(mode="open-to-the-world")
    text = format_validation_error(exc_info.value)
    assert "open-to-the-world" not in text


def test_authenticated_mode_requires_token():
    with pytest.raises(ValidationError, match="api_token is required"):
        SecurityConfig(mode=SecurityMode.authenticated)


def test_home_assistant_ingress_mode_requires_trusted_proxies():
    with pytest.raises(ValidationError, match="ingress_trusted_proxies"):
        SecurityConfig(mode=SecurityMode.home_assistant_ingress)


def test_home_assistant_ingress_mode_allows_optional_token():
    cfg = SecurityConfig(
        mode=SecurityMode.home_assistant_ingress,
        ingress_trusted_proxies=["172.30.32.2"],
    )
    assert cfg.api_token is None
    assert cfg.ingress_trusted_proxies == ("172.30.32.2",)
    cfg_with_token = SecurityConfig(
        mode=SecurityMode.home_assistant_ingress,
        api_token=VALID_TOKEN,
        ingress_trusted_proxies=["172.30.32.2"],
        ingress_proxy_only=True,
    )
    assert cfg_with_token.api_token is not None
    assert cfg_with_token.ingress_proxy_only is True


def test_ingress_proxies_rejected_outside_ingress_mode():
    with pytest.raises(ValidationError, match="ingress_trusted_proxies"):
        SecurityConfig(
            mode=SecurityMode.local,
            ingress_trusted_proxies=["172.30.32.2"],
        )
    with pytest.raises(ValidationError, match="ingress_proxy_only"):
        SecurityConfig(mode=SecurityMode.local, ingress_proxy_only=True)


def test_valid_token_accepted_and_masked():
    cfg = SecurityConfig(api_token=VALID_TOKEN)
    assert cfg.api_token is not None
    assert cfg.api_token.get_secret_value() == VALID_TOKEN
    assert VALID_TOKEN not in repr(cfg)
    assert VALID_TOKEN not in cfg.model_dump_json()
    assert "**********" in cfg.model_dump_json()


def test_short_token_rejected_without_echo():
    with pytest.raises(ValidationError) as exc_info:
        SecurityConfig(api_token=SHORT_TOKEN)
    rendered = format_validation_error(exc_info.value)
    assert SHORT_TOKEN not in rendered
    assert SHORT_TOKEN not in str(ConfigError(rendered))


@pytest.mark.parametrize(
    "bad",
    [
        " " + VALID_TOKEN,
        VALID_TOKEN + " ",
        "\t" + VALID_TOKEN,
        VALID_TOKEN[:31] + "\x00",
        VALID_TOKEN[:30] + "\n" + "x",
    ],
)
def test_token_whitespace_and_control_rejected(bad: str):
    with pytest.raises(ValidationError) as exc_info:
        SecurityConfig(api_token=bad)
    assert bad not in format_validation_error(exc_info.value)


def test_session_secret_validation_matches_api_token():
    with pytest.raises(ValidationError):
        SecurityConfig(session_secret=SHORT_TOKEN)
    cfg = SecurityConfig(session_secret=VALID_TOKEN)
    assert cfg.session_secret is not None
    assert VALID_TOKEN not in repr(cfg)


def test_explicit_non_loopback_hosts_retained(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(
        cfg_file,
        """
server:
  host: 0.0.0.0
  port: 8377
""",
    )
    config = load_config(cfg_file)
    assert config.server.host == "0.0.0.0"

    cfg_file.write_text(
        """
server:
  host: "::"
mode:
  mock: true
networks: []
""",
        encoding="utf-8",
    )
    assert load_config(cfg_file).server.host == "::"


@pytest.mark.parametrize(
    ("host", "loopback"),
    [
        ("127.0.0.1", True),
        ("localhost", True),
        ("LOCALHOST", True),
        ("::1", True),
        ("[::1]", True),
        ("0.0.0.0", False),
        ("::", False),
        ("192.168.1.10", False),
        ("zigbeelens.local", False),
    ],
)
def test_is_loopback_bind(host: str, loopback: bool):
    assert is_loopback_bind(host) is loopback


def test_omitted_host_defaults_to_loopback(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(cfg_file)
    assert load_config(cfg_file).server.host == "127.0.0.1"


def test_canonical_api_token_env_overrides_yaml(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(
        cfg_file,
        f"""
security:
  mode: local
  api_token: {VALID_TOKEN}
""",
    )
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN", VALID_TOKEN_B)
    config = load_config(cfg_file)
    assert config.security.api_token is not None
    assert config.security.api_token.get_secret_value() == VALID_TOKEN_B


def test_api_token_file_overrides_yaml(tmp_path: Path, monkeypatch):
    secret_file = tmp_path / "token.txt"
    secret_file.write_bytes((VALID_TOKEN_B + "\n").encode("utf-8"))
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(
        cfg_file,
        f"""
security:
  api_token: {VALID_TOKEN}
""",
    )
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN_FILE", str(secret_file))
    config = load_config(cfg_file)
    assert config.security.api_token is not None
    assert config.security.api_token.get_secret_value() == VALID_TOKEN_B


def test_secret_file_trailing_crlf_removed(tmp_path: Path, monkeypatch):
    secret_file = tmp_path / "token.txt"
    secret_file.write_bytes((VALID_TOKEN + "\r\n").encode("utf-8"))
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(cfg_file)
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN_FILE", str(secret_file))
    config = load_config(cfg_file)
    assert config.security.api_token.get_secret_value() == VALID_TOKEN


def test_empty_secret_file_fails(tmp_path: Path, monkeypatch):
    secret_file = tmp_path / "empty.txt"
    secret_file.write_text("\n", encoding="utf-8")
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(cfg_file)
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN_FILE", str(secret_file))
    with pytest.raises(ConfigError, match="empty"):
        load_config(cfg_file)


def test_missing_secret_file_fails(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(cfg_file)
    monkeypatch.setenv(
        "ZIGBEELENS_SECURITY_API_TOKEN_FILE",
        str(tmp_path / "missing-token.txt"),
    )
    with pytest.raises(ConfigError, match="not found"):
        load_config(cfg_file)


def test_directory_secret_path_fails(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(cfg_file)
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN_FILE", str(tmp_path))
    with pytest.raises(ConfigError, match="not a regular readable file"):
        load_config(cfg_file)


def test_invalid_utf8_secret_file_fails(tmp_path: Path, monkeypatch):
    secret_file = tmp_path / "bad.bin"
    secret_file.write_bytes(b"\xff\xfe" + b"a" * 32)
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(cfg_file)
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN_FILE", str(secret_file))
    with pytest.raises(ConfigError, match="UTF-8"):
        load_config(cfg_file)


def test_direct_and_file_conflict_fails(tmp_path: Path, monkeypatch):
    secret_file = tmp_path / "token.txt"
    secret_file.write_text(VALID_TOKEN, encoding="utf-8")
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(cfg_file)
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN", VALID_TOKEN)
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN_FILE", str(secret_file))
    with pytest.raises(ConfigError, match="Conflicting secret sources"):
        load_config(cfg_file)


def test_canonical_and_legacy_conflict_fails(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(cfg_file)
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN", VALID_TOKEN)
    monkeypatch.setenv("ZIGBEELENS_API_KEY", VALID_TOKEN_B)
    with pytest.raises(ConfigError, match="Conflicting API token sources"):
        load_config(cfg_file)


def test_legacy_api_key_alone_resolves(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(cfg_file)
    monkeypatch.setenv("ZIGBEELENS_API_KEY", VALID_TOKEN)
    config = load_config(cfg_file)
    assert config.security.api_token is not None
    assert config.security.api_token.get_secret_value() == VALID_TOKEN


def test_security_mode_environment_override(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(
        cfg_file,
        """
security:
  ingress_trusted_proxies:
    - 172.30.32.2
""",
    )
    monkeypatch.setenv("ZIGBEELENS_SECURITY_MODE", "home_assistant_ingress")
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN", VALID_TOKEN)
    config = load_config(cfg_file)
    assert config.security.mode is SecurityMode.home_assistant_ingress
    assert config.security.api_token is not None
    assert config.security.ingress_trusted_proxies == ("172.30.32.2",)


def test_authenticated_mode_env_without_token_fails(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(cfg_file)
    monkeypatch.setenv("ZIGBEELENS_SECURITY_MODE", "authenticated")
    with pytest.raises(ConfigError) as exc_info:
        load_config(cfg_file)
    assert "api_token" in str(exc_info.value)
    assert VALID_TOKEN not in str(exc_info.value)


def test_ingress_mode_env_without_trusted_proxies_fails(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(cfg_file)
    monkeypatch.setenv("ZIGBEELENS_SECURITY_MODE", "home_assistant_ingress")
    with pytest.raises(ConfigError) as exc_info:
        load_config(cfg_file)
    assert "ingress_trusted_proxies" in str(exc_info.value)
    assert VALID_TOKEN not in str(exc_info.value)


def test_mqtt_password_direct_and_file(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(
        cfg_file,
        """
mqtt:
  server: mqtt://broker:1883
  username: yaml-user
  password: yaml-pass
""",
    )
    monkeypatch.setenv("ZIGBEELENS_MQTT_USERNAME", "env-user")
    monkeypatch.setenv("ZIGBEELENS_MQTT_PASSWORD", "env-pass-value")
    config = load_config(cfg_file)
    assert config.mqtt.username == "env-user"
    assert config.mqtt.password.get_secret_value() == "env-pass-value"

    secret_file = tmp_path / "mqtt.pass"
    secret_file.write_text("file-pass-value\n", encoding="utf-8")
    monkeypatch.delenv("ZIGBEELENS_MQTT_PASSWORD")
    monkeypatch.setenv("ZIGBEELENS_MQTT_PASSWORD_FILE", str(secret_file))
    config = load_config(cfg_file)
    assert config.mqtt.password.get_secret_value() == "file-pass-value"


def test_mqtt_direct_and_file_conflict(tmp_path: Path, monkeypatch):
    secret_file = tmp_path / "mqtt.pass"
    secret_file.write_text("file-pass", encoding="utf-8")
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(cfg_file)
    monkeypatch.setenv("ZIGBEELENS_MQTT_PASSWORD", "direct")
    monkeypatch.setenv("ZIGBEELENS_MQTT_PASSWORD_FILE", str(secret_file))
    with pytest.raises(ConfigError, match="Conflicting secret sources"):
        load_config(cfg_file)


def test_scenario_override_unchanged(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(cfg_file)
    monkeypatch.setenv("ZIGBEELENS_MOCK_SCENARIO", "bridge_offline")
    assert load_config(cfg_file).mode.default_scenario == "bridge_offline"


def test_non_mapping_yaml_root_fails_cleanly(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="must be a mapping"):
        load_config(cfg_file)


def test_env_mutation_after_load_does_not_change_config(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(cfg_file)
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN", VALID_TOKEN)
    config = load_config(cfg_file)
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN", VALID_TOKEN_B)
    assert config.security.api_token.get_secret_value() == VALID_TOKEN


def test_secret_file_mutation_after_load_does_not_change_config(
    tmp_path: Path, monkeypatch
):
    secret_file = tmp_path / "token.txt"
    secret_file.write_text(VALID_TOKEN, encoding="utf-8")
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(cfg_file)
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN_FILE", str(secret_file))
    config = load_config(cfg_file)
    secret_file.write_text(VALID_TOKEN_B, encoding="utf-8")
    assert config.security.api_token.get_secret_value() == VALID_TOKEN


def test_short_token_absent_from_config_error_and_logs(
    tmp_path: Path, monkeypatch, caplog
):
    cfg_file = tmp_path / "config.yaml"
    _write_base_config(
        cfg_file,
        f"""
security:
  api_token: {SHORT_TOKEN}
""",
    )
    with caplog.at_level(logging.DEBUG), pytest.raises(ConfigError) as exc_info:
        load_config(cfg_file)
    assert SHORT_TOKEN not in str(exc_info.value)
    assert SHORT_TOKEN not in caplog.text


def test_appconfig_repr_and_json_mask_security_secrets():
    config = AppConfig(
        security=SecurityConfig(
            api_token=VALID_TOKEN,
            session_secret=VALID_TOKEN_B,
        ),
        mqtt={"server": "mqtt://broker", "password": "mqtt-secret-value"},
    )
    rendered = repr(config)
    dumped = config.model_dump_json()
    assert VALID_TOKEN not in rendered
    assert VALID_TOKEN_B not in rendered
    assert VALID_TOKEN not in dumped
    assert VALID_TOKEN_B not in dumped
