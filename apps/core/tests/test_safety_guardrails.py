"""Final safety guardrail tests for release."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from zigbeelens.mqtt_discovery.topics import UnsafeMqttTopicError, validate_publish_topic
from zigbeelens.topology.topics import UnsafeTopologyTopicError, validate_topology_request_topic

CORE_SRC = Path(__file__).resolve().parents[1] / "src" / "zigbeelens"
MQTT_PKG = CORE_SRC / "mqtt"
UI_SRC = Path(__file__).resolve().parents[3] / "ui" / "src"
REPO_ROOT = Path(__file__).resolve().parents[3]

UNSAFE_UI_PATTERNS = (
    "permit join",
    "permit_join",
    "remove device",
    "reset device",
    "factory reset",
    "bind device",
    "unbind device",
    "ota update",
    "change channel",
)


def _python_files(directory: Path) -> list[Path]:
    return sorted(directory.rglob("*.py"))


def _find_publish_calls_in_tree(directory: Path) -> list[tuple[str, int]]:
    hits: list[tuple[str, int]] = []
    for path in _python_files(directory):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "publish":
                    rel = path.relative_to(CORE_SRC.parents[1])
                    hits.append((str(rel), node.lineno))
    return hits


def test_collector_package_has_no_publish_calls():
    """MQTT collector package must remain subscribe-only."""
    hits = _find_publish_calls_in_tree(MQTT_PKG)
    unexpected = [h for h in hits if not h[0].endswith("mqtt/client.py")]
    assert not unexpected, f"Unexpected publish() calls in mqtt/: {unexpected}"


def test_mqtt_discovery_rejects_zigbee2mqtt_topics():
    unsafe = [
        "zigbee2mqtt/bridge/request/device/remove",
        "zigbee2mqtt/living_room/set",
        "zigbee2mqtt/bridge/state",
        "homeassistant/+/config",
    ]
    for topic in unsafe:
        with pytest.raises(UnsafeMqttTopicError):
            validate_publish_topic(topic, zigbee_base_topics=("zigbee2mqtt",))


def test_topology_rejects_non_networkmap_requests():
    with pytest.raises(UnsafeTopologyTopicError):
        validate_topology_request_topic(
            "zigbee2mqtt/bridge/request/device/remove",
            allowed_base_topics=("zigbee2mqtt",),
        )
    with pytest.raises(UnsafeTopologyTopicError):
        validate_topology_request_topic(
            "zigbee2mqtt/bridge/request/permit_join",
            allowed_base_topics=("zigbee2mqtt",),
        )


def test_topology_allows_networkmap_only():
    validate_topology_request_topic(
        "zigbee2mqtt/bridge/request/networkmap",
        allowed_base_topics=("zigbee2mqtt",),
    )


def test_ui_has_no_repair_controls():
    """UI must not expose Zigbee mutation controls."""
    if not UI_SRC.exists():
        pytest.skip("UI source not available")
    combined = ""
    for path in UI_SRC.rglob("*.tsx"):
        combined += path.read_text(encoding="utf-8").lower() + "\n"
    for pattern in UNSAFE_UI_PATTERNS:
        assert pattern not in combined, f"Unsafe UI pattern found: {pattern}"


def test_topology_startup_defaults_in_example_configs():
    docker_example = REPO_ROOT / "deploy" / "docker" / "config.example.yaml"
    assert docker_example.exists()
    text = docker_example.read_text(encoding="utf-8").lower()
    assert "topology:" in text
    assert "enabled: true" in text
    assert "startup_scan: true" in text
    assert "refresh_interval_seconds: 0" in text
