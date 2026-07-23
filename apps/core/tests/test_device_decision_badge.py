"""Device decision badge composition tests (Phase 5B-1 / 5B-1 batch fix)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.device_story import (
    device_story_for_device,
    load_device_story_evidence,
    load_device_story_network_context,
)
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.schemas import DeviceDecisionBadge
from zigbeelens.services.device_decision_badge import (
    device_decision_badge_for_device,
    device_decision_badge_from_story,
    device_decision_badges_for_devices,
)
from zigbeelens.services.payload_builder import PayloadBuilder
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.parser import parse_networkmap_payload

NOW = datetime(2026, 7, 13, 2, 0, 0, tzinfo=timezone.utc)

DEFAULT_NODES = {
    "0x01": {"type": "Coordinator"},
    "0x02": {"type": "Router"},
    "0x03": {"type": "EndDevice"},
}


def _repo(tmp_path: Path, *, networks: list[NetworkConfig] | None = None) -> tuple[Repository, AppConfig]:
    db_path = tmp_path / "device-decision-badge.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    network_cfgs = networks or [
        NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")
    ]
    config = AppConfig(
        mode=ModeConfig(mock=True),
        networks=network_cfgs,
        storage=StorageConfig(path=str(db_path)),
    )
    repo.sync_networks(config.networks)
    return repo, config


def _add_device(
    repo: Repository,
    ieee: str,
    *,
    network_id: str = "home",
    availability: str = "online",
    friendly_name: str | None = None,
) -> None:
    repo.upsert_device(
        network_id=network_id,
        ieee_address=ieee,
        friendly_name=friendly_name or f"Device {ieee}",
        device_type="EndDevice",
        power_source="Mains",
    )
    repo.ensure_device_current_state(network_id, ieee)
    repo.update_device_current_state(
        network_id=network_id,
        ieee_address=ieee,
        availability=availability,
        last_seen=NOW.isoformat(),
    )


def _enable_availability_tracking(
    repo: Repository,
    ieee: str,
    *,
    network_id: str = "home",
    changed_at: datetime,
) -> None:
    repo.availability.insert_availability_change(
        network_id, ieee, "unknown", "online"
    )
    repo.db.conn.execute(
        "UPDATE availability_changes SET changed_at = ? WHERE rowid = last_insert_rowid()",
        (changed_at.isoformat(),),
    )
    repo.db.conn.commit()


def _link_ha_area(repo: Repository, ieee: str, *, network_id: str = "home") -> None:
    repo.db.conn.execute(
        """
        INSERT INTO ha_device_enrichment (
            network_id, ieee_address, ha_device_name, entity_id, area_id, area_name,
            match_confidence, updated_at
        ) VALUES (?, ?, 'Kitchen Lamp', 'light.kitchen', 'area-1', 'Kitchen', 'high', ?)
        """,
        (network_id, ieee, NOW.isoformat()),
    )
    repo.db.conn.commit()


def _store_snapshot(
    repo: Repository,
    snapshot_id: str,
    *,
    network_id: str = "home",
    captured_at: datetime,
    links: list[dict],
    nodes: dict[str, dict] | None = None,
) -> None:
    repo.create_topology_snapshot(
        snapshot_id=snapshot_id,
        network_id=network_id,
        requested_by="test",
        status="pending",
        warning_acknowledged=True,
    )
    parsed = parse_networkmap_payload(
        {"nodes": DEFAULT_NODES if nodes is None else nodes, "links": links}
    )
    repo.store_topology_parsed(snapshot_id, network_id, parsed, status="complete")
    repo.db.conn.execute(
        "UPDATE topology_snapshots SET captured_at = ? WHERE snapshot_id = ?",
        (captured_at.isoformat(), snapshot_id),
    )
    repo.db.conn.commit()


def _store_topology_gap_fixtures(repo: Repository, ieee: str = "0x03") -> None:
    nodes = {
        "0x01": {"type": "Coordinator"},
        "0x02": {"type": "Router"},
        ieee: {"type": "EndDevice"},
    }
    _store_snapshot(
        repo,
        "snap-latest",
        captured_at=NOW,
        links=[],
        nodes=nodes,
    )
    _store_snapshot(
        repo,
        "snap-old",
        captured_at=NOW - timedelta(days=1),
        links=[{"source": "0x02", "target": ieee, "linkquality": 90}],
        nodes=nodes,
    )


def _spy_network_composers(monkeypatch):
    import zigbeelens.services.network_evidence_composition as evidence_module
    from zigbeelens.decisions.model_pattern import observed_model_patterns_for_network
    from zigbeelens.topology.history import (
        aggregate_historical_evidence,
        aggregate_last_known_links,
    )

    historical = {"count": 0}
    last_known = {"count": 0}
    model_patterns = {"count": 0}

    def _historical(*args, **kwargs):
        historical["count"] += 1
        return aggregate_historical_evidence(*args, **kwargs)

    def _last_known(*args, **kwargs):
        last_known["count"] += 1
        return aggregate_last_known_links(*args, **kwargs)

    def _model_patterns(*args, **kwargs):
        model_patterns["count"] += 1
        return observed_model_patterns_for_network(*args, **kwargs)

    monkeypatch.setattr(evidence_module, "aggregate_historical_evidence", _historical)
    monkeypatch.setattr(evidence_module, "aggregate_last_known_links", _last_known)
    monkeypatch.setattr(
        evidence_module, "observed_model_patterns_for_network", _model_patterns
    )
    return historical, last_known, model_patterns


def test_badge_matches_device_story_status_priority_and_headline(tmp_path: Path):
    repo, _ = _repo(tmp_path)
    _add_device(repo, "0xa1", availability="offline")
    story = device_story_for_device(repo, "home", "0xa1")
    assert story is not None
    badge = device_decision_badge_from_story(story)
    assert badge.status == str(story.status)
    assert badge.priority == str(story.priority)
    assert badge.headline_code == str(story.headline_code)


def test_badge_for_device_helper_matches_story(tmp_path: Path):
    repo, _ = _repo(tmp_path)
    _add_device(repo, "0xa1", availability="online")
    story = device_story_for_device(repo, "home", "0xa1")
    badge = device_decision_badge_for_device(repo, "home", "0xa1")
    assert story is not None
    assert badge is not None
    assert badge.status == str(story.status)
    assert badge.headline_code == str(story.headline_code)


def test_device_list_payload_includes_decision_badge(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "0xa1", availability="offline")
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    devices = PayloadBuilder(config, repo, health).devices()
    assert len(devices) == 1
    assert devices[0].decision is not None
    story = device_story_for_device(repo, "home", "0xa1")
    assert story is not None
    assert devices[0].decision.status == str(story.status)
    assert devices[0].decision.headline_code == str(story.headline_code)


def test_device_summary_includes_additional_ha_name_and_area_when_enriched(
    tmp_path: Path,
):
    repo, config = _repo(tmp_path)
    _add_device(repo, "0xa1", availability="online")
    _link_ha_area(repo, "0xa1")
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    devices = PayloadBuilder(config, repo, health).devices()
    assert len(devices) == 1
    assert devices[0].friendly_name == "Device 0xa1"
    assert devices[0].home_assistant_name == "Kitchen Lamp"
    assert devices[0].home_assistant_area_name == "Kitchen"
    assert devices[0].ha_area == "Kitchen"


def test_unknown_device_returns_no_badge(tmp_path: Path):
    repo, _ = _repo(tmp_path)
    assert device_decision_badge_for_device(repo, "home", "0xmissing") is None


def test_devices_list_loads_network_evidence_once(monkeypatch, tmp_path: Path):
    repo, config = _repo(tmp_path)
    for ieee in ("0xa1", "0xa2", "0xa3", "0xa4"):
        _add_device(repo, ieee, availability="online")
    historical, last_known, model_patterns = _spy_network_composers(monkeypatch)
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    devices = PayloadBuilder(config, repo, health).devices()
    assert len(devices) == 4
    assert historical["count"] == 1
    assert last_known["count"] == 1
    assert model_patterns["count"] == 1


def test_devices_list_loads_network_evidence_once_per_network(
    monkeypatch, tmp_path: Path
):
    repo, config = _repo(
        tmp_path,
        networks=[
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt/home"),
            NetworkConfig(id="cabin", name="Cabin", base_topic="zigbee2mqtt/cabin"),
        ],
    )
    _add_device(repo, "0xa1", network_id="home")
    _add_device(repo, "0xa2", network_id="home")
    _add_device(repo, "0xb1", network_id="cabin")
    _add_device(repo, "0xb2", network_id="cabin")
    historical, last_known, model_patterns = _spy_network_composers(monkeypatch)
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    devices = PayloadBuilder(config, repo, health).devices()
    assert len(devices) == 4
    assert historical["count"] == 2
    assert last_known["count"] == 2
    assert model_patterns["count"] == 2


def test_device_summary_does_not_compose_decision_badge(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "0xa1", availability="offline")
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    builder = PayloadBuilder(config, repo, health)
    row = repo.get_device("home", "0xa1")
    assert row is not None
    explicit = DeviceDecisionBadge(
        status="review_first",
        priority="high",
        headline_code="current_issue_present",
        coverage_label_codes=[],
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "zigbeelens.services.payload_builder.device_decision_badge_for_device",
            MagicMock(side_effect=AssertionError("must not compose badge")),
        )
        summary = builder._device_summary(row, decision_badge=explicit)
    assert summary.decision == explicit


def test_device_detail_still_includes_decision_badge(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "0xa1", availability="offline")
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    detail = PayloadBuilder(config, repo, health).device_detail("home", "0xa1")
    assert detail is not None
    assert detail.decision is not None
    story = device_story_for_device(repo, "home", "0xa1", now=NOW)
    assert story is not None
    assert detail.decision.status == str(story.status)


def test_wrong_network_context_raises(tmp_path: Path):
    repo, _ = _repo(
        tmp_path,
        networks=[
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt/home"),
            NetworkConfig(id="cabin", name="Cabin", base_topic="zigbee2mqtt/cabin"),
        ],
    )
    _add_device(repo, "0xa1", network_id="home")
    context = load_device_story_network_context(repo, "cabin", now=NOW)
    with pytest.raises(ValueError, match="network_id"):
        load_device_story_evidence(
            repo,
            "home",
            "0xa1",
            now=NOW,
            network_context=context,
        )


def test_batch_badges_match_device_story_semantic_parity(tmp_path: Path):
    repo, _ = _repo(tmp_path)

    # 1. Current issue / offline
    _add_device(repo, "0xoff", availability="offline", friendly_name="Offline")

    # 2. Topology evidence gap
    _add_device(repo, "0x03", availability="online", friendly_name="Topo gap")
    _enable_availability_tracking(
        repo, "0x03", changed_at=NOW - timedelta(days=3)
    )
    _link_ha_area(repo, "0x03")
    _store_topology_gap_fixtures(repo, ieee="0x03")
    repo.upsert_device(
        network_id="home",
        ieee_address="0x01",
        friendly_name="Coordinator",
        device_type="Coordinator",
        power_source="Mains",
    )
    repo.upsert_device(
        network_id="home",
        ieee_address="0x02",
        friendly_name="Router",
        device_type="Router",
        power_source="Mains",
    )

    # 3. Availability tracking off
    _add_device(repo, "0xtrk", availability="online", friendly_name="Tracking off")

    # 4. Normal / no notable signals
    _add_device(repo, "0xnrm", availability="online", friendly_name="Normal")
    _enable_availability_tracking(
        repo, "0xnrm", changed_at=NOW - timedelta(days=3)
    )
    _link_ha_area(repo, "0xnrm")
    _store_snapshot(
        repo,
        "snap-healthy",
        captured_at=NOW,
        links=[{"source": "0x02", "target": "0xnrm", "linkquality": 120}],
        nodes={
            "0x01": {"type": "Coordinator"},
            "0x02": {"type": "Router"},
            "0xnrm": {"type": "EndDevice"},
            "0x03": {"type": "EndDevice"},
        },
    )

    ieees = ("0xoff", "0x03", "0xtrk", "0xnrm")
    rows = [repo.get_device("home", ieee) for ieee in ieees]
    assert all(row is not None for row in rows)
    batch = device_decision_badges_for_devices(repo, rows, now=NOW)

    for ieee in ieees:
        story = device_story_for_device(repo, "home", ieee, now=NOW)
        assert story is not None
        expected = device_decision_badge_from_story(story)
        badge = batch[("home", ieee)]
        assert badge.status == str(story.status)
        assert badge.priority == str(story.priority)
        assert badge.headline_code == str(story.headline_code)
        assert badge == expected


def _spy_snapshot_link_loads(repo: Repository, monkeypatch):
    import zigbeelens.topology.device_compare as device_compare_module

    snapshot_calls: list[str] = []
    link_calls: list[str] = []
    tracking_calls: list[str] = []
    earliest_calls: list[str] = []

    original_list_snapshots = repo.list_topology_snapshots_for_networks
    original_list_links = repo.list_topology_links_for_snapshots
    original_earliest = repo.get_earliest_availability_change_at_for_networks
    original_tracking = device_compare_module.availability_tracking_enabled_now

    def _list_snapshots(network_ids):
        ordered = list(dict.fromkeys(nid for nid in network_ids if nid))
        snapshot_calls.extend(ordered)
        return original_list_snapshots(network_ids)

    def _list_links(snapshot_ids):
        ordered = list(dict.fromkeys(sid for sid in snapshot_ids if sid))
        link_calls.extend(ordered)
        return original_list_links(snapshot_ids)

    def _earliest(network_ids):
        ordered = list(dict.fromkeys(nid for nid in network_ids if nid))
        earliest_calls.extend(ordered)
        return original_earliest(network_ids)

    def _tracking(repo_arg, network_id: str, **kwargs):
        tracking_calls.append(network_id)
        return original_tracking(repo_arg, network_id, **kwargs)

    monkeypatch.setattr(repo, "list_topology_snapshots_for_networks", _list_snapshots)
    monkeypatch.setattr(repo, "list_topology_links_for_snapshots", _list_links)
    monkeypatch.setattr(
        repo, "get_earliest_availability_change_at_for_networks", _earliest
    )
    monkeypatch.setattr(
        device_compare_module, "availability_tracking_enabled_now", _tracking
    )
    return snapshot_calls, link_calls, tracking_calls, earliest_calls


def test_devices_list_loads_snapshot_links_once_per_snapshot(monkeypatch, tmp_path: Path):
    repo, config = _repo(tmp_path)
    for ieee in ("0xa1", "0xa2", "0xa3", "0xa4"):
        _add_device(repo, ieee)
    nodes = {
        "0x01": {"type": "Coordinator"},
        "0xa1": {"type": "EndDevice"},
        "0xa2": {"type": "EndDevice"},
        "0xa3": {"type": "EndDevice"},
        "0xa4": {"type": "EndDevice"},
    }
    for index, snapshot_id in enumerate(("snap-1", "snap-2", "snap-3")):
        _store_snapshot(
            repo,
            snapshot_id,
            captured_at=NOW - timedelta(days=2 - index),
            links=[
                {"source": "0xa1", "target": "0x01", "linkquality": 100 + index},
                {"source": "0xa2", "target": "0x01", "linkquality": 90 + index},
                {"source": "0xa3", "target": "0x01", "linkquality": 80 + index},
                {"source": "0xa4", "target": "0x01", "linkquality": 70 + index},
            ],
            nodes=nodes,
        )
    snapshot_calls, link_calls, tracking_calls, earliest_calls = _spy_snapshot_link_loads(
        repo, monkeypatch
    )
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    # Reset after health work so only devices() path is counted.
    snapshot_calls.clear()
    link_calls.clear()
    tracking_calls.clear()
    earliest_calls.clear()
    bulk_snapshot_calls: list[int] = []
    bulk_availability_calls: list[int] = []
    per_device_snapshot_calls: list[str] = []
    per_device_availability_calls: list[str] = []
    node_calls: list[str] = []
    original_bulk_snapshots = repo.devices.list_device_snapshots_for_devices
    original_bulk_availability = repo.availability.list_availability_changes_for_devices
    original_device_snapshots = repo.devices.list_device_snapshots
    original_availability_changes = repo.availability.list_availability_changes
    original_nodes = repo.list_topology_nodes

    def _bulk_snapshots(device_keys, *, limit: int = 50):
        bulk_snapshot_calls.append(len(list(device_keys)))
        return original_bulk_snapshots(device_keys, limit=limit)

    def _bulk_availability(device_keys, *, limit: int = 20):
        bulk_availability_calls.append(len(list(device_keys)))
        return original_bulk_availability(device_keys, limit=limit)

    def _device_snapshots(network_id: str, ieee_address: str, *, limit: int):
        per_device_snapshot_calls.append(ieee_address)
        return original_device_snapshots(network_id, ieee_address, limit=limit)

    def _availability_changes(network_id: str, ieee_address: str, limit: int = 20):
        per_device_availability_calls.append(ieee_address)
        return original_availability_changes(network_id, ieee_address, limit)

    def _nodes(snapshot_id: str):
        node_calls.append(snapshot_id)
        return original_nodes(snapshot_id)

    monkeypatch.setattr(repo.devices, "list_device_snapshots_for_devices", _bulk_snapshots)
    monkeypatch.setattr(
        repo.availability, "list_availability_changes_for_devices", _bulk_availability
    )
    monkeypatch.setattr(repo.devices, "list_device_snapshots", _device_snapshots)
    monkeypatch.setattr(repo.availability, "list_availability_changes", _availability_changes)
    monkeypatch.setattr(repo, "list_topology_nodes", _nodes)
    devices = PayloadBuilder(config, repo, health).devices()
    assert len(devices) == 4
    assert bulk_snapshot_calls == [4]
    assert bulk_availability_calls == [4]
    assert per_device_snapshot_calls == []
    assert per_device_availability_calls == []
    assert len(set(node_calls)) <= 3
    assert snapshot_calls == ["home"]
    assert sorted(link_calls) == ["snap-1", "snap-2", "snap-3"]
    assert link_calls.count("snap-1") == 1
    assert link_calls.count("snap-2") == 1
    assert link_calls.count("snap-3") == 1
    assert tracking_calls == ["home"]
    assert earliest_calls == ["home"]


def test_devices_list_loads_snapshot_context_once_per_network(monkeypatch, tmp_path: Path):
    repo, config = _repo(
        tmp_path,
        networks=[
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt/home"),
            NetworkConfig(id="office", name="Office", base_topic="zigbee2mqtt/office"),
        ],
    )
    for ieee in ("0xa1", "0xa2"):
        _add_device(repo, ieee, network_id="home")
    for ieee in ("0xb1", "0xb2"):
        _add_device(repo, ieee, network_id="office")

    home_nodes = {
        "0x01": {"type": "Coordinator"},
        "0xa1": {"type": "EndDevice"},
        "0xa2": {"type": "EndDevice"},
    }
    office_nodes = {
        "0x01": {"type": "Coordinator"},
        "0xb1": {"type": "EndDevice"},
        "0xb2": {"type": "EndDevice"},
    }
    for index, snapshot_id in enumerate(("home-1", "home-2", "home-3")):
        _store_snapshot(
            repo,
            snapshot_id,
            network_id="home",
            captured_at=NOW - timedelta(days=2 - index),
            links=[
                {"source": "0xa1", "target": "0x01", "linkquality": 100},
                {"source": "0xa2", "target": "0x01", "linkquality": 90},
            ],
            nodes=home_nodes,
        )
    for index, snapshot_id in enumerate(("office-1", "office-2")):
        _store_snapshot(
            repo,
            snapshot_id,
            network_id="office",
            captured_at=NOW - timedelta(days=1 - index),
            links=[
                {"source": "0xb1", "target": "0x01", "linkquality": 80},
                {"source": "0xb2", "target": "0x01", "linkquality": 70},
            ],
            nodes=office_nodes,
        )

    snapshot_calls, link_calls, tracking_calls, earliest_calls = _spy_snapshot_link_loads(
        repo, monkeypatch
    )
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    snapshot_calls.clear()
    link_calls.clear()
    tracking_calls.clear()
    earliest_calls.clear()
    devices = PayloadBuilder(config, repo, health).devices()
    assert len(devices) == 4
    assert snapshot_calls.count("home") == 1
    assert snapshot_calls.count("office") == 1
    for snapshot_id in ("home-1", "home-2", "home-3", "office-1", "office-2"):
        assert link_calls.count(snapshot_id) == 1
    assert tracking_calls.count("home") == 1
    assert tracking_calls.count("office") == 1
    assert earliest_calls.count("home") == 1
    assert earliest_calls.count("office") == 1


def test_dashboard_composes_inventory_decision_badges_once(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "0xa1", availability="offline")
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    spy = MagicMock(wraps=device_decision_badges_for_devices)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "zigbeelens.services.payload_builder.device_decision_badges_for_devices",
            spy,
        )
        dash = PayloadBuilder(config, repo, health).dashboard()
    assert spy.call_count == 1
    assert dash.decision_summary.subject_count >= 1
    assert dash.networks[0].decision.status
    assert "health_snapshot" not in dash.model_dump()


def test_devices_endpoint_composes_badges_once(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "0xa1", availability="offline")
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    spy = MagicMock(wraps=device_decision_badges_for_devices)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "zigbeelens.services.payload_builder.device_decision_badges_for_devices",
            spy,
        )
        devices = PayloadBuilder(config, repo, health).devices()
    assert spy.call_count == 1
    assert devices[0].decision is not None


def test_device_detail_composes_single_device_badge_once(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "0xa1", availability="offline")
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    spy = MagicMock(wraps=device_decision_badge_for_device)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "zigbeelens.services.payload_builder.device_decision_badge_for_device",
            spy,
        )
        mp.setattr(
            "zigbeelens.services.payload_builder.device_decision_badges_for_devices",
            MagicMock(side_effect=AssertionError("detail must not batch compose")),
        )
        detail = PayloadBuilder(config, repo, health).device_detail("home", "0xa1")
    assert detail is not None
    assert detail.decision is not None
    assert spy.call_count == 1


def test_dashboard_does_not_load_device_story_network_context(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "0xa1", availability="online")
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "zigbeelens.decisions.device_story.load_device_story_network_context",
            MagicMock(
                side_effect=AssertionError(
                    "dashboard must not compose Device Story network context"
                )
            ),
        )
        dash = PayloadBuilder(config, repo, health).dashboard()
    assert dash.generated_at
