"""YAML configuration loader with validation and allowlisted secret sources."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Mapping

import yaml
from pydantic import ValidationError

from zigbeelens.config.models import AppConfig, ServerConfig
from zigbeelens.config.secret_validation import contains_control_characters

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATHS = (
    "config/config.yaml",
    "examples/config.example.yaml",
)

ENV_SECURITY_MODE = "ZIGBEELENS_SECURITY_MODE"
ENV_SECURITY_API_TOKEN = "ZIGBEELENS_SECURITY_API_TOKEN"
ENV_SECURITY_API_TOKEN_FILE = "ZIGBEELENS_SECURITY_API_TOKEN_FILE"
ENV_SECURITY_SESSION_SECRET = "ZIGBEELENS_SECURITY_SESSION_SECRET"
ENV_SECURITY_SESSION_SECRET_FILE = "ZIGBEELENS_SECURITY_SESSION_SECRET_FILE"
ENV_LEGACY_API_KEY = "ZIGBEELENS_API_KEY"
ENV_MQTT_USERNAME = "ZIGBEELENS_MQTT_USERNAME"
ENV_MQTT_PASSWORD = "ZIGBEELENS_MQTT_PASSWORD"
ENV_MQTT_PASSWORD_FILE = "ZIGBEELENS_MQTT_PASSWORD_FILE"
ENV_MOCK_SCENARIO = "ZIGBEELENS_MOCK_SCENARIO"
ENV_SERVER_PORT = "ZIGBEELENS_PORT"


class ConfigError(Exception):
    """Raised when configuration cannot be loaded or validated."""


def resolve_config_path(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    env_path = os.environ.get("ZIGBEELENS_CONFIG")
    if env_path:
        return Path(env_path).expanduser()
    for candidate in DEFAULT_CONFIG_PATHS:
        path = Path(candidate)
        if path.is_file():
            return path
    return Path(DEFAULT_CONFIG_PATHS[0])


def format_validation_error(exc: ValidationError) -> str:
    """Render a ValidationError without embedding rejected input values."""
    lines: list[str] = []
    for err in exc.errors(include_input=False, include_url=False):
        loc = ".".join(str(part) for part in err.get("loc", ()))
        msg = str(err.get("msg", "invalid value"))
        err_type = str(err.get("type") or "")
        if loc and err_type:
            lines.append(f"{loc}: {msg} [{err_type}]")
        elif loc:
            lines.append(f"{loc}: {msg}")
        else:
            lines.append(msg)
    return "\n".join(lines) if lines else "invalid configuration"


def format_yaml_error(exc: yaml.YAMLError) -> str:
    """Render a YAML parse failure without source excerpts or secret text."""
    mark = getattr(exc, "problem_mark", None)
    if mark is not None:
        line = getattr(mark, "line", None)
        column = getattr(mark, "column", None)
        if isinstance(line, int) and isinstance(column, int):
            return f"YAML parse error at line {line + 1}, column {column + 1}"
    return "YAML parse error"


def _ensure_mapping(raw: Any, *, path: Path) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ConfigError(
            f"Configuration root in {path} must be a mapping, not {type(raw).__name__}."
        )
    return dict(raw)


def _ensure_section(raw: dict[str, Any], key: str) -> dict[str, Any]:
    current = raw.get(key)
    if current is None:
        section: dict[str, Any] = {}
        raw[key] = section
        return section
    if not isinstance(current, Mapping):
        raise ConfigError(f"Configuration section '{key}' must be a mapping.")
    section = dict(current)
    raw[key] = section
    return section


def _read_secret_file(path_value: str) -> str:
    path = Path(path_value).expanduser()
    if not path.is_file():
        if not path.exists():
            raise ConfigError(f"Secret file not found: {path}")
        raise ConfigError(f"Secret path is not a regular readable file: {path}")

    read_error: str | None = None
    raw: bytes | None = None
    try:
        raw = path.read_bytes()
    except OSError as exc:
        detail = exc.strerror or "I/O error"
        read_error = f"Unable to read secret file {path}: {detail}"
    if read_error is not None:
        raise ConfigError(read_error)
    assert raw is not None

    decode_failed = False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        decode_failed = True
        text = ""
    if decode_failed:
        raise ConfigError(f"Secret file is not valid UTF-8: {path}")

    text = text.rstrip("\r\n")
    if not text:
        raise ConfigError(f"Secret file is empty: {path}")
    if contains_control_characters(text):
        raise ConfigError(f"Secret file contains control characters: {path}")
    return text


def _resolve_env_or_file(env_name: str, file_env_name: str) -> str | None:
    direct_set = env_name in os.environ
    file_set = file_env_name in os.environ
    if direct_set and file_set:
        raise ConfigError(
            f"Conflicting secret sources: both {env_name} and {file_env_name} are set."
        )
    if direct_set:
        return os.environ[env_name]
    if file_set:
        return _read_secret_file(os.environ[file_env_name])
    return None


def _apply_security_overrides(raw: dict[str, Any]) -> None:
    security = _ensure_section(raw, "security")

    if ENV_SECURITY_MODE in os.environ:
        security["mode"] = os.environ[ENV_SECURITY_MODE]

    canonical_token = _resolve_env_or_file(
        ENV_SECURITY_API_TOKEN,
        ENV_SECURITY_API_TOKEN_FILE,
    )
    legacy_set = ENV_LEGACY_API_KEY in os.environ
    if canonical_token is not None and legacy_set:
        raise ConfigError(
            "Conflicting API token sources: "
            f"{ENV_LEGACY_API_KEY} cannot be combined with "
            f"{ENV_SECURITY_API_TOKEN} or {ENV_SECURITY_API_TOKEN_FILE}."
        )
    if canonical_token is not None:
        security["api_token"] = canonical_token
    elif legacy_set:
        security["api_token"] = os.environ[ENV_LEGACY_API_KEY]

    session_secret = _resolve_env_or_file(
        ENV_SECURITY_SESSION_SECRET,
        ENV_SECURITY_SESSION_SECRET_FILE,
    )
    if session_secret is not None:
        security["session_secret"] = session_secret


def _apply_mqtt_overrides(raw: dict[str, Any]) -> None:
    mqtt = _ensure_section(raw, "mqtt")
    if ENV_MQTT_USERNAME in os.environ:
        mqtt["username"] = os.environ[ENV_MQTT_USERNAME]
    password = _resolve_env_or_file(ENV_MQTT_PASSWORD, ENV_MQTT_PASSWORD_FILE)
    if password is not None:
        mqtt["password"] = password


def _apply_environment_overrides(raw: dict[str, Any]) -> None:
    scenario_override = os.environ.get(ENV_MOCK_SCENARIO)
    if scenario_override:
        mode = _ensure_section(raw, "mode")
        mode["default_scenario"] = scenario_override
    _apply_security_overrides(raw)
    _apply_mqtt_overrides(raw)


def load_config(config_path: str | Path | None = None) -> AppConfig:
    path = Path(config_path) if config_path else resolve_config_path()
    if not path.is_file():
        raise ConfigError(
            f"Configuration file not found: {path}. "
            "Set ZIGBEELENS_CONFIG or create config/config.yaml."
        )

    yaml_message: str | None = None
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        yaml_message = format_yaml_error(exc)
        loaded = None
    if yaml_message is not None:
        raise ConfigError(f"Invalid YAML in {path}: {yaml_message}")

    raw = _ensure_mapping(loaded, path=path)
    _apply_environment_overrides(raw)

    validation_message: str | None = None
    config: AppConfig | None = None
    try:
        config = AppConfig.model_validate(raw)
    except ValidationError as exc:
        validation_message = format_validation_error(exc)
    if validation_message is not None:
        raise ConfigError(
            f"Configuration validation failed for {path}:\n{validation_message}"
        )
    assert config is not None

    logger.info(
        "Loaded configuration from %s (mock=%s, networks=%d)",
        path,
        config.mode.mock,
        len(config.networks),
    )
    return config


def apply_server_port_override(config: AppConfig) -> AppConfig:
    """Apply allowlisted ZIGBEELENS_PORT into typed ServerConfig when set."""
    if ENV_SERVER_PORT not in os.environ:
        return config
    raw = os.environ[ENV_SERVER_PORT]
    try:
        port = int(raw)
    except ValueError:
        raise ConfigError(
            f"Invalid {ENV_SERVER_PORT}: must be an integer between 1 and 65535."
        ) from None
    validation_message: str | None = None
    server: ServerConfig | None = None
    try:
        server = ServerConfig(host=config.server.host, port=port)
    except ValidationError as exc:
        validation_message = format_validation_error(exc)
    if validation_message is not None:
        raise ConfigError(
            f"Invalid {ENV_SERVER_PORT}:\n{validation_message}"
        )
    assert server is not None
    return config.model_copy(update={"server": server})


def load_effective_config(config_path: str | Path | None = None) -> AppConfig:
    """Load config and apply runtime bind overrides used by first-party launchers."""
    return apply_server_port_override(load_config(config_path))
