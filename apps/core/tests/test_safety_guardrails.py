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
        "contract",
        "contracts",
        "fixture",
        "fixtures",
        "generated",
        "test",
        "tests",
    }
    files: list[Path] = []
    for path in directory.rglob("*"):
        if not path.is_file() or path.suffix not in {".ts", ".tsx"}:
            continue
        relative = path.relative_to(directory)
        if any(part in excluded_parts for part in relative.parts[:-1]):
            continue
        if path.name.endswith(
            (".d.ts", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")
        ):
            continue
        files.append(path)
    return sorted(files)


def _assert_ui_has_no_repair_controls(directory: Path) -> None:
    assert directory.is_dir(), f"Required production UI source is missing: {directory}"
    files = _production_ui_files(directory)
    assert files, (
        f"UI safety guard discovered zero production .ts/.tsx files under {directory}"
    )
    hits: list[tuple[str, str]] = []
    for path in files:
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
    """The release owner must scan production TS and TSX inside apps/ui."""
    assert UI_SRC.relative_to(REPO_ROOT) == Path("apps/ui/src")
    assert UI_SRC.is_dir(), f"Required production UI source is missing: {UI_SRC}"
    files = set(_production_ui_files(UI_SRC))
    expected = (
        UI_SRC / "main.tsx",
        UI_SRC / "navigation" / "model.ts",
    )
    for path in expected:
        assert path.is_file(), f"Expected production UI source is missing: {path}"
        assert path in files, (
            f"Production UI source was excluded from the safety corpus: {path}"
        )


def test_ui_guard_fails_when_source_is_missing(tmp_path: Path):
    missing = tmp_path / "apps" / "ui" / "src"
    with pytest.raises(AssertionError, match="Required production UI source is missing"):
        _assert_ui_has_no_repair_controls(missing)


def test_ui_guard_fails_when_production_corpus_is_empty(tmp_path: Path):
    ui_src = tmp_path / "apps" / "ui" / "src"
    ui_src.mkdir(parents=True)
    with pytest.raises(
        AssertionError,
        match=r"UI safety guard discovered zero production \.ts/\.tsx files",
    ):
        _assert_ui_has_no_repair_controls(ui_src)


@pytest.mark.parametrize(
    ("filename", "source"),
    (
        ("UnsafeDeviceActions.ts", 'export const deviceActionLabel = "Remove device";\n'),
        ("UnsafeDeviceActions.tsx", "<button>Remove device</button>\n"),
    ),
)
def test_ui_guard_rejects_deliberate_unsafe_control(
    tmp_path: Path,
    filename: str,
    source: str,
):
    ui_src = tmp_path / "apps" / "ui" / "src"
    ui_src.mkdir(parents=True)
    (ui_src / filename).write_text(source, encoding="utf-8")
    with pytest.raises(AssertionError, match="remove device"):
        _assert_ui_has_no_repair_controls(ui_src)


def test_ui_file_enumerator_excludes_test_sources(tmp_path: Path):
    ui_src = tmp_path / "apps" / "ui" / "src"
    production_ts = ui_src / "navigation" / "model.ts"
    production_ts.parent.mkdir(parents=True)
    production_ts.write_text(
        'export const deviceActionLabel = "Evidence only";\n',
        encoding="utf-8",
    )
    production_tsx = ui_src / "components" / "DeviceActions.tsx"
    production_tsx.parent.mkdir(parents=True)
    production_tsx.write_text("<div>Evidence only</div>\n", encoding="utf-8")

    excluded = (
        ui_src / "test" / "authTestUtils.tsx",
        ui_src / "tests" / "authTestUtils.ts",
        ui_src / "contract" / "unsafe.ts",
        ui_src / "contracts" / "unsafe.tsx",
        ui_src / "fixture" / "deviceFixture.ts",
        ui_src / "fixtures" / "deviceFixture.tsx",
        ui_src / "__tests__" / "unsafe.ts",
        ui_src / "__fixtures__" / "unsafe.tsx",
        ui_src / "generated" / "unsafe.ts",
        ui_src / "components" / "DeviceActions.test.ts",
        ui_src / "components" / "DeviceActions.test.tsx",
        ui_src / "components" / "DeviceActions.spec.ts",
        ui_src / "components" / "DeviceActions.spec.tsx",
        ui_src / "components" / "types.d.ts",
    )
    for path in excluded:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('export const unsafe = "Factory reset";\n', encoding="utf-8")

    assert _production_ui_files(ui_src) == [production_tsx, production_ts]


def test_ui_file_enumerator_ignores_excluded_checkout_ancestors(tmp_path: Path):
    ui_src = tmp_path / "tests" / "generated" / "checkout" / "apps" / "ui" / "src"
    production = ui_src / "components" / "DeviceActions.tsx"
    production.parent.mkdir(parents=True)
    production.write_text("<div>Evidence only</div>\n", encoding="utf-8")

    assert _production_ui_files(ui_src) == [production]
    _assert_ui_has_no_repair_controls(ui_src)


def test_topology_startup_defaults_in_example_configs():
    docker_example = REPO_ROOT / "deploy" / "docker" / "config.example.yaml"
    assert docker_example.exists()
    text = docker_example.read_text(encoding="utf-8").lower()
    assert "topology:" in text
    assert "enabled: true" in text
    assert "startup_scan: true" in text
    assert "refresh_interval_seconds: 0" in text
