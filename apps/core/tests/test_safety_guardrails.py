"""Final safety guardrail tests for release."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from zigbeelens.mqtt_discovery.topics import UnsafeMqttTopicError, validate_publish_topic
from zigbeelens.topology.topics import UnsafeTopologyTopicError, validate_topology_request_topic

REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "apps" / "core" / "src" / "zigbeelens"
MQTT_PKG = CORE_SRC / "mqtt"
UI_SRC = REPO_ROOT / "apps" / "ui" / "src"

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


def _production_ui_files(directory: Path) -> list[Path]:
    excluded_parts = {
        "__fixtures__",
        "__tests__",
        "fixtures",
        "generated",
        "test",
        "tests",
    }
    return sorted(
        path
        for path in directory.rglob("*.tsx")
        if not any(part in excluded_parts for part in path.parts)
        and not path.name.endswith((".test.tsx", ".spec.tsx"))
    )


def _assert_ui_has_no_repair_controls(directory: Path) -> None:
    assert directory.is_dir(), f"Required production UI source is missing: {directory}"
    hits: list[tuple[str, str]] = []
    for path in _production_ui_files(directory):
        text = path.read_text(encoding="utf-8").lower()
        for pattern in UNSAFE_UI_PATTERNS:
            if pattern in text:
                hits.append((str(path.relative_to(directory)), pattern))
    assert not hits, f"Unsafe UI controls found: {hits}"


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
    _assert_ui_has_no_repair_controls(UI_SRC)


def test_ui_source_path_matches_monorepo_layout():
    """The release owner must scan the production UI inside apps/ui."""
    assert UI_SRC.relative_to(REPO_ROOT) == Path("apps/ui/src")
    assert UI_SRC.is_dir(), f"Required production UI source is missing: {UI_SRC}"
    assert (UI_SRC / "main.tsx").is_file(), (
        f"Expected production UI entrypoint is missing: {UI_SRC / 'main.tsx'}"
    )


def test_ui_guard_fails_when_source_is_missing(tmp_path: Path):
    missing = tmp_path / "apps" / "ui" / "src"
    with pytest.raises(AssertionError, match="Required production UI source is missing"):
        _assert_ui_has_no_repair_controls(missing)


def test_ui_guard_rejects_deliberate_unsafe_control(tmp_path: Path):
    ui_src = tmp_path / "apps" / "ui" / "src"
    ui_src.mkdir(parents=True)
    (ui_src / "UnsafeDeviceActions.tsx").write_text(
        "<button>Remove device</button>\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="remove device"):
        _assert_ui_has_no_repair_controls(ui_src)


def test_ui_file_enumerator_excludes_test_sources(tmp_path: Path):
    ui_src = tmp_path / "apps" / "ui" / "src"
    production = ui_src / "components" / "DeviceActions.tsx"
    production.parent.mkdir(parents=True)
    production.write_text("<div>Evidence only</div>\n", encoding="utf-8")

    excluded = (
        ui_src / "test" / "authTestUtils.tsx",
        ui_src / "fixtures" / "deviceFixture.tsx",
        ui_src / "components" / "DeviceActions.test.tsx",
    )
    for path in excluded:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<button>Factory reset</button>\n", encoding="utf-8")

    assert _production_ui_files(ui_src) == [production]


def test_topology_startup_defaults_in_example_configs():
    docker_example = REPO_ROOT / "deploy" / "docker" / "config.example.yaml"
    assert docker_example.exists()
    text = docker_example.read_text(encoding="utf-8").lower()
    assert "topology:" in text
    assert "enabled: true" in text
    assert "startup_scan: true" in text
    assert "refresh_interval_seconds: 0" in text
