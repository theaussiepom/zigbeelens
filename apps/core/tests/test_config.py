from pathlib import Path

import pytest

from zigbeelens.config import ConfigError, load_config


def test_load_config_success(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """
mode:
  mock: true
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
""",
        encoding="utf-8",
    )
    config = load_config(cfg_file)
    assert config.mode.mock is True
    assert config.networks[0].id == "home"


def test_load_config_missing_file(tmp_path: Path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.yaml")


def test_load_config_invalid_yaml(tmp_path: Path):
    cfg_file = tmp_path / "bad.yaml"
    cfg_file.write_text("mode: [", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_config(cfg_file)


def test_duplicate_network_ids_rejected(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
  - id: home
    name: Home 2
    base_topic: zigbee2mqtt-home2
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="validation failed"):
        load_config(cfg_file)


def test_env_scenario_override(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("mode:\n  mock: true\nnetworks: []\n", encoding="utf-8")
    monkeypatch.setenv("ZIGBEELENS_MOCK_SCENARIO", "bridge_offline")
    config = load_config(cfg_file)
    assert config.mode.default_scenario == "bridge_offline"
