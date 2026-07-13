"""Tests for observed model/manufacturer pattern facts (Phase 4G-1)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.model_pattern import (
    MODEL_PATTERN_LOOKBACK_DAYS,
    MODEL_PATTERN_MIN_AFFECTED_COUNT,
    MODEL_PATTERN_MIN_GROUP_SIZE,
    ModelPatternSignal,
    ObservedModelPatternState,
    _ModelGroup,
    _group_key,
    build_observed_model_patterns,
    observed_model_patterns_for_network,
)
from zigbeelens.storage.repository import Repository

NOW = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)

FORBIDDEN_PHRASES = [
    "bad manufacturer",
    "faulty manufacturer",
    "manufacturer is to blame",
    "caused by manufacturer",
    "caused by model",
    "root cause",
    "defective model",
]


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "model-pattern.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "model-pattern.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    return repo


def _add_device(
    repo: Repository,
    ieee: str,
    *,
    model: str | None = "TS011F",
    manufacturer: str | None = "IKEA",
) -> None:
    repo.upsert_device(
        network_id="home",
        ieee_address=ieee,
        friendly_name=f"Device {ieee}",
        device_type="EndDevice",
        power_source="Mains",
        manufacturer=manufacturer,
        model=model,
    )


def _offline_event(repo: Repository, ieee: str, at: datetime) -> None:
    repo.db.conn.execute(
        """
        INSERT INTO availability_changes (network_id, ieee_address, from_state, to_state, changed_at)
        VALUES ('home', ?, 'online', 'offline', ?)
        """,
        (ieee, at.isoformat()),
    )
    repo.db.conn.commit()


def _model_group(
  manufacturer: str | None,
  model: str,
  members: list[str],
) -> _ModelGroup:
    return _ModelGroup(
        manufacturer=manufacturer,
        model=model,
        members=frozenset(members),
    )


def test_empty_network_returns_no_patterns(tmp_path: Path):
    repo = _repo(tmp_path)
    result = observed_model_patterns_for_network(repo, "home", now=NOW)
    assert result.state is ObservedModelPatternState.no_patterns
    assert result.patterns == []


def test_tiny_group_is_suppressed(tmp_path: Path):
    repo = _repo(tmp_path)
    devices = [f"0x0{i}" for i in range(MODEL_PATTERN_MIN_GROUP_SIZE - 1)]
    for ieee in devices:
        _add_device(repo, ieee)
    base = NOW - timedelta(days=1)
    for ieee in devices[:MODEL_PATTERN_MIN_AFFECTED_COUNT]:
        _offline_event(repo, ieee, base)

    result = observed_model_patterns_for_network(repo, "home", now=NOW)
    assert result.state is ObservedModelPatternState.no_patterns


def test_insufficient_affected_count_is_suppressed(tmp_path: Path):
    repo = _repo(tmp_path)
    devices = [f"0x1{i:02d}" for i in range(MODEL_PATTERN_MIN_GROUP_SIZE)]
    for ieee in devices:
        _add_device(repo, ieee)
    base = NOW - timedelta(days=1)
    for ieee in devices[: MODEL_PATTERN_MIN_AFFECTED_COUNT - 1]:
        _offline_event(repo, ieee, base)

    result = observed_model_patterns_for_network(repo, "home", now=NOW)
    assert result.state is ObservedModelPatternState.no_patterns


def test_qualifying_offline_pattern_is_reported(tmp_path: Path):
    repo = _repo(tmp_path)
    devices = [f"0x2{i:02d}" for i in range(MODEL_PATTERN_MIN_GROUP_SIZE)]
    for ieee in devices:
        _add_device(repo, ieee)
    base = NOW - timedelta(days=1)
    for ieee in devices[:MODEL_PATTERN_MIN_AFFECTED_COUNT]:
        _offline_event(repo, ieee, base)

    result = observed_model_patterns_for_network(repo, "home", now=NOW)
    assert result.state is ObservedModelPatternState.patterns_available
    assert len(result.patterns) == 1
    pattern = result.patterns[0]
    assert pattern.signal is ModelPatternSignal.offline_in_lookback
    assert pattern.group_size == MODEL_PATTERN_MIN_GROUP_SIZE
    assert pattern.affected_count == MODEL_PATTERN_MIN_AFFECTED_COUNT
    assert pattern.model == "TS011F"
    assert pattern.manufacturer == "IKEA"
    assert pattern.params["min_group_size"] == MODEL_PATTERN_MIN_GROUP_SIZE
    assert pattern.params["min_affected_count"] == MODEL_PATTERN_MIN_AFFECTED_COUNT


def test_devices_without_model_are_excluded(tmp_path: Path):
    repo = _repo(tmp_path)
    devices = [f"0x3{i:02d}" for i in range(MODEL_PATTERN_MIN_GROUP_SIZE)]
    for ieee in devices:
        _add_device(repo, ieee, model=None)
    base = NOW - timedelta(days=1)
    for ieee in devices:
        _offline_event(repo, ieee, base)

    result = observed_model_patterns_for_network(repo, "home", now=NOW)
    assert result.state is ObservedModelPatternState.no_patterns


def test_same_model_different_manufacturers_are_separate_groups(tmp_path: Path):
    repo = _repo(tmp_path)
    ikea_devices = [f"0x4{i:02d}" for i in range(MODEL_PATTERN_MIN_GROUP_SIZE)]
    aqara_devices = [f"0x5{i:02d}" for i in range(MODEL_PATTERN_MIN_GROUP_SIZE)]
    for ieee in ikea_devices:
        _add_device(repo, ieee, manufacturer="IKEA")
    for ieee in aqara_devices:
        _add_device(repo, ieee, manufacturer="Aqara")
    base = NOW - timedelta(days=1)
    for ieee in ikea_devices[:MODEL_PATTERN_MIN_AFFECTED_COUNT]:
        _offline_event(repo, ieee, base)
    for ieee in aqara_devices[:MODEL_PATTERN_MIN_AFFECTED_COUNT]:
        _offline_event(repo, ieee, base)

    result = observed_model_patterns_for_network(repo, "home", now=NOW)
    assert result.state is ObservedModelPatternState.patterns_available
    assert len(result.patterns) == 2
    manufacturers = {pattern.manufacturer for pattern in result.patterns}
    assert manufacturers == {"IKEA", "Aqara"}


def test_offline_outside_lookback_does_not_qualify(tmp_path: Path):
    repo = _repo(tmp_path)
    devices = [f"0x6{i:02d}" for i in range(MODEL_PATTERN_MIN_GROUP_SIZE)]
    for ieee in devices:
        _add_device(repo, ieee)
    base = NOW - timedelta(days=MODEL_PATTERN_LOOKBACK_DAYS + 1)
    for ieee in devices[:MODEL_PATTERN_MIN_AFFECTED_COUNT]:
        _offline_event(repo, ieee, base)

    result = observed_model_patterns_for_network(repo, "home", now=NOW)
    assert result.state is ObservedModelPatternState.no_patterns


def test_online_transition_does_not_count_as_affected(tmp_path: Path):
    repo = _repo(tmp_path)
    devices = [f"0x7{i:02d}" for i in range(MODEL_PATTERN_MIN_GROUP_SIZE)]
    for ieee in devices:
        _add_device(repo, ieee)
    base = NOW - timedelta(days=1)
    for ieee in devices[:MODEL_PATTERN_MIN_AFFECTED_COUNT]:
        repo.db.conn.execute(
            """
            INSERT INTO availability_changes (network_id, ieee_address, from_state, to_state, changed_at)
            VALUES ('home', ?, 'offline', 'online', ?)
            """,
            (ieee, base.isoformat()),
        )
    repo.db.conn.commit()

    result = observed_model_patterns_for_network(repo, "home", now=NOW)
    assert result.state is ObservedModelPatternState.no_patterns


def test_build_observed_model_patterns_is_deterministic():
    groups = {
        _group_key("IKEA", "TS011F"): _model_group(
            "IKEA",
            "TS011F",
            [f"0x8{i:02d}" for i in range(MODEL_PATTERN_MIN_GROUP_SIZE)],
        )
    }
    affected = {f"0x8{i:02d}" for i in range(MODEL_PATTERN_MIN_AFFECTED_COUNT)}

    first = build_observed_model_patterns(
        network_id="home",
        groups=groups,
        affected_ieees=affected,
    )
    second = build_observed_model_patterns(
        network_id="home",
        groups=groups,
        affected_ieees=affected,
    )
    assert first == second
    assert first.patterns[0].pattern_id == second.patterns[0].pattern_id


def _build_pattern_for_group(
    *,
    manufacturer: str | None,
    model: str,
    members: list[str] | None = None,
    affected_ieees: set[str] | None = None,
) -> str:
    members = members or [f"0xa{i:02d}" for i in range(MODEL_PATTERN_MIN_GROUP_SIZE)]
    affected_ieees = affected_ieees or {
        members[i] for i in range(MODEL_PATTERN_MIN_AFFECTED_COUNT)
    }
    groups = {
        _group_key(manufacturer, model): _model_group(manufacturer, model, members),
    }
    result = build_observed_model_patterns(
        network_id="home",
        groups=groups,
        affected_ieees=affected_ieees,
    )
    assert len(result.patterns) == 1
    return result.patterns[0].pattern_id


def test_canonical_equivalent_identities_share_pattern_id():
    pattern_ids = [
        _build_pattern_for_group(manufacturer="IKEA", model="TS011F"),
        _build_pattern_for_group(manufacturer="ikea", model="ts011f"),
        _build_pattern_for_group(manufacturer="IKEA", model="TS011F"),
    ]
    assert len(set(pattern_ids)) == 1

    display_result = build_observed_model_patterns(
        network_id="home",
        groups={
            _group_key("IKEA", "TS011F"): _model_group(
                "IKEA",
                "TS011F",
                [f"0xb{i:02d}" for i in range(MODEL_PATTERN_MIN_GROUP_SIZE)],
            )
        },
        affected_ieees={f"0xb{i:02d}" for i in range(MODEL_PATTERN_MIN_AFFECTED_COUNT)},
    )
    pattern = display_result.patterns[0]
    assert pattern.manufacturer == "IKEA"
    assert pattern.model == "TS011F"


def test_different_model_identities_have_different_pattern_ids():
    ikea_ts011f = _build_pattern_for_group(manufacturer="IKEA", model="TS011F")
    aqara_ts011f = _build_pattern_for_group(
        manufacturer="Aqara",
        model="TS011F",
        members=[f"0xc{i:02d}" for i in range(MODEL_PATTERN_MIN_GROUP_SIZE)],
    )
    ikea_ts0121 = _build_pattern_for_group(
        manufacturer="IKEA",
        model="TS0121",
        members=[f"0xd{i:02d}" for i in range(MODEL_PATTERN_MIN_GROUP_SIZE)],
    )
    assert len({ikea_ts011f, aqara_ts011f, ikea_ts0121}) == 3


def test_unknown_manufacturer_canonical_identity_is_stable():
    none_id = _build_pattern_for_group(manufacturer=None, model="TS011F")
    empty_id = _build_pattern_for_group(manufacturer="  ", model="ts011f")
    known_id = _build_pattern_for_group(manufacturer="IKEA", model="TS011F")
    assert none_id == empty_id
    assert none_id != known_id


def test_module_has_no_manufacturer_blame_phrases():
    module_path = Path(__file__).resolve().parents[1] / "src/zigbeelens/decisions/model_pattern.py"
    source = module_path.read_text(encoding="utf-8").lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in source


def test_pattern_payload_is_json_serializable(tmp_path: Path):
    repo = _repo(tmp_path)
    devices = [f"0x9{i:02d}" for i in range(MODEL_PATTERN_MIN_GROUP_SIZE)]
    for ieee in devices:
        _add_device(repo, ieee)
    base = NOW - timedelta(days=1)
    for ieee in devices[:MODEL_PATTERN_MIN_AFFECTED_COUNT]:
        _offline_event(repo, ieee, base)

    result = observed_model_patterns_for_network(repo, "home", now=NOW)
    json.dumps(result.model_dump(mode="json"))
