"""YAML configuration loader with validation."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from pydantic import ValidationError

from zigbeelens.config.models import AppConfig

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATHS = (
    "config/config.yaml",
    "examples/config.example.yaml",
)


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


def load_config(config_path: str | Path | None = None) -> AppConfig:
    path = Path(config_path) if config_path else resolve_config_path()
    if not path.is_file():
        raise ConfigError(
            f"Configuration file not found: {path}. "
            "Set ZIGBEELENS_CONFIG or create config/config.yaml."
        )

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if raw is None:
        raw = {}

    scenario_override = os.environ.get("ZIGBEELENS_MOCK_SCENARIO")
    if scenario_override:
        raw.setdefault("mode", {})
        raw["mode"]["default_scenario"] = scenario_override

    try:
        config = AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Configuration validation failed for {path}:\n{exc}") from exc

    logger.info(
        "Loaded configuration from %s (mock=%s, networks=%d)",
        path,
        config.mode.mock,
        len(config.networks),
    )
    return config
