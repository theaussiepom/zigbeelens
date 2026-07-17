"""YAML configuration loader with validation and allowlisted secret sources."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Mapping

import yaml
from pydantic import ValidationError

from zigbeelens.config.models import AppConfig

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
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ConfigError(f"Unable to read secret file {path}: {exc.strerror or exc}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"Secret file is not valid UTF-8: {path}") from exc
    text = text.rstrip("\r\n")
    if not text:
        raise ConfigError(f"Secret file is empty: {path}")
    if any(ord(ch) < 32 for ch in text):
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

    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc

    raw = _ensure_mapping(loaded, path=path)
    _apply_environment_overrides(raw)

    try:
        config = AppConfig.model_validate(raw)
    except ValidationError as exc:
        details = format_validation_error(exc)
        raise ConfigError(
            f"Configuration validation failed for {path}:\n{details}"
        ) from exc

    logger.info(
        "Loaded configuration from %s (mock=%s, networks=%d)",
        path,
        config.mode.mock,
        len(config.networks),
    )
    return config
