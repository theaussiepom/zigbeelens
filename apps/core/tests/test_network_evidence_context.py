"""Track 3G: NetworkEvidenceContext construction and bulk repository reads."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.services.network_evidence import (
    DEVICE_STORY_EVIDENCE_REQUIREMENTS,
    EVIDENCE_GRAPH_REQUIREMENTS,
    NetworkEvidenceCapability,
    NetworkEvidenceCapabilityError,
    union_requirements,
)
from zigbeelens.services.network_evidence_composition import (
    compose_network_evidence_context,
    compose_network_evidence_contexts,
)
from zigbeelens.storage.repository import Repository
from performance.query_instrumentation import install_counter

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def _repo(tmp_path: Path) -> tuple[Repository, AppConfig]:
    db = Database(tmp_path / "evidence3g.sqlite")
    db.migrate()
    repo = Repository(db)
    config = AppConfig(
        mode=ModeConfig(mock=False),
        networks=[
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
            NetworkConfig(id="office", name="Office", base_topic="z2m-office"),
        ],
        storage=StorageConfig(path=str(tmp_path / "evidence3g.sqlite")),
    )
    repo.sync_networks(config.networks)
    return repo, config


def _add_device(repo: Repository, network_id: str, ieee: str, name: str) -> None:
    repo.upsert_device(
        network_id=network_id,
        ieee_address=ieee,
        friendly_name=name,
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )
    repo.ensure_device_current_state(network_id, ieee)
    repo.update_device_current_state(
        network_id=network_id,
        ieee_address=ieee,
        availability="online",
        last_seen=NOW.isoformat(),
    )


def _add_snapshot(
    repo: Repository,
    *,
    snapshot_id: str,
    network_id: str,
    status: str = "complete",
    captured_at: str | None = None,
) -> None:
    repo.create_topology_snapshot(
        snapshot_id=snapshot_id,
        network_id=network_id,
        requested_by="test",
        status="in_progress",
    )
    # Force captured_at / status for deterministic fixtures.
    repo.db.conn.execute(
        "UPDATE topology_snapshots SET status = ?, captured_at = ? WHERE snapshot_id = ?",
        (status, captured_at or NOW.isoformat(), snapshot_id),
    )
    repo.db.conn.commit()


def test_union_requirements_and_presets():
    assert NetworkEvidenceCapability.devices in DEVICE_STORY_EVIDENCE_REQUIREMENTS
    merged = union_requirements(
        DEVICE_STORY_EVIDENCE_REQUIREMENTS, EVIDENCE_GRAPH_REQUIREMENTS
    )
    assert NetworkEvidenceCapability.investigations in merged
    assert NetworkEvidenceCapability.devices in merged


def test_empty_network_ids_zero_sql(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    counter = install_counter(repo)
    counter.reset()
    contexts = compose_network_evidence_contexts(
        repo,
        [],
        reference_now=NOW,
        requirements_by_network={},
    )
    assert dict(contexts) == {}
    assert counter.stats.execute_count == 0


def test_one_context_per_network_dedupes_ids(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    _add_device(repo, "home", "0xa", "A")
    _add_device(repo, "office", "0xb", "B")
    contexts = compose_network_evidence_contexts(
        repo,
        ["home", "office", "home"],
        reference_now=NOW,
        requirements_by_network={
            "home": frozenset({NetworkEvidenceCapability.devices}),
            "office": frozenset({NetworkEvidenceCapability.devices}),
        },
    )
    assert set(contexts) == {"home", "office"}
    assert len(contexts["home"].device_rows or ()) == 1
    assert len(contexts["office"].device_rows or ()) == 1


def test_supplied_device_rows_avoid_device_reread(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    _add_device(repo, "home", "0xa", "A")
    rows = repo.list_devices("home")
    counter = install_counter(repo)
    counter.reset()
    ctx = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=frozenset({NetworkEvidenceCapability.devices}),
        device_rows=rows,
    )
    assert ctx.device_rows is not None
    assert counter.stats.category_counts.get("read.devices", 0) == 0
    assert counter.stats.category_counts.get("read.device_current_state", 0) == 0


def test_not_loaded_capability_distinct_from_loaded_empty(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    ctx = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=frozenset({NetworkEvidenceCapability.devices}),
    )
    assert ctx.has_capability(NetworkEvidenceCapability.devices)
    assert ctx.device_rows == ()
    assert not ctx.has_capability(NetworkEvidenceCapability.passive_hints)
    assert ctx.passive_hints is None
    with pytest.raises(NetworkEvidenceCapabilityError):
        ctx.require(NetworkEvidenceCapability.passive_hints)


def test_context_immutable_and_rows_copied(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    _add_snapshot(repo, snapshot_id="s1", network_id="home")
    ctx = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=frozenset(
            {
                NetworkEvidenceCapability.latest_topology,
                NetworkEvidenceCapability.snapshot_history,
            }
        ),
    )
    assert ctx.topology_snapshots is not None
    with pytest.raises(TypeError):
        ctx.topology_snapshots[0]["status"] = "mutated"  # type: ignore[index]
    with pytest.raises(AttributeError):
        ctx.network_id = "office"  # type: ignore[misc]


def test_wrong_network_device_rows_rejected(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    _add_device(repo, "office", "0xb", "B")
    office_rows = repo.list_devices("office")
    with pytest.raises(ValueError, match="does not match"):
        compose_network_evidence_context(
            repo,
            "home",
            reference_now=NOW,
            requirements=frozenset({NetworkEvidenceCapability.devices}),
            device_rows=office_rows,
        )


def test_naive_reference_now_rejected(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    with pytest.raises(ValueError, match="timezone-aware"):
        compose_network_evidence_context(
            repo,
            "home",
            reference_now=datetime(2026, 7, 15, 12, 0),
            requirements=frozenset({NetworkEvidenceCapability.devices}),
        )


def test_bulk_topology_reads_not_per_snapshot(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    for i in range(3):
        sid = f"snap-{i}"
        _add_snapshot(
            repo,
            snapshot_id=sid,
            network_id="home",
            captured_at=NOW.replace(minute=i).isoformat(),
        )
        repo.db.conn.execute(
            "INSERT INTO topology_nodes (snapshot_id, network_id, ieee_address, friendly_name, "
            "node_type, depth, lqi) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sid, "home", f"0x{i}", f"n{i}", "Router", 0, 100),
        )
        repo.db.conn.execute(
            "INSERT INTO topology_links (snapshot_id, network_id, source_ieee, target_ieee, "
            "source_type, target_type, linkquality, depth, relationship, route_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, "home", f"0x{i}", "0xcoord", "Router", "Coordinator", 120, 1, "child", 0),
        )
    repo.db.conn.commit()

    counter = install_counter(repo)
    counter.reset()
    ctx = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=frozenset(
            {
                NetworkEvidenceCapability.latest_topology,
                NetworkEvidenceCapability.snapshot_history,
                NetworkEvidenceCapability.historical_links,
                NetworkEvidenceCapability.last_known_links,
            }
        ),
    )
    # Snapshots once via bulk; nodes/links via bulk IN (?) — not once per snapshot.
    assert counter.stats.category_counts.get("read.topology_snapshots", 0) == 1
    assert counter.stats.category_counts.get("read.topology_nodes", 0) == 1
    assert counter.stats.category_counts.get("read.topology_links", 0) == 1
    assert ctx.latest_usable_snapshot is not None
    assert counter.stats.category_counts.get("other", 0) == 0
    assert counter.stats.commit_count == 0


def test_bulk_methods_empty_input_zero_sql(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    counter = install_counter(repo)
    counter.reset()
    assert repo.list_topology_snapshots_for_networks([]) == {}
    assert repo.list_topology_nodes_for_snapshots([]) == {}
    assert repo.list_topology_links_for_snapshots([]) == {}
    assert repo.list_devices_for_networks([]) == {}
    assert repo.list_availability_changes_for_networks_since([], NOW.isoformat()) == {}
    assert repo.get_earliest_availability_change_at_for_networks([]) == {}
    assert repo.network_has_usable_ha_area_assignments_for_networks([]) == {}
    assert counter.stats.execute_count == 0


def test_explain_bulk_topology_plan(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    _add_snapshot(repo, snapshot_id="s1", network_id="home")
    plan = repo.db.conn.execute(
        "EXPLAIN QUERY PLAN "
        "SELECT snapshot_id, network_id, captured_at, status "
        "FROM topology_snapshots WHERE network_id IN (?) ORDER BY network_id ASC, captured_at DESC",
        ("home",),
    ).fetchall()
    text = " ".join(" ".join(str(cell) for cell in row) for row in plan).lower()
    assert "topology_snapshots" in text


def test_reference_time_and_network_compatibility(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    ctx = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=frozenset({NetworkEvidenceCapability.devices}),
    )
    with pytest.raises(ValueError):
        ctx.require_compatible(network_id="office", reference_now=NOW)
    later = NOW.replace(hour=13)
    with pytest.raises(ValueError):
        ctx.require_compatible(network_id="home", reference_now=later)
    ctx.require_compatible(network_id="home", reference_now=NOW)


def test_frozen_context_survives_db_mutation(tmp_path: Path):
    """Projections from a frozen context ignore later temporary-DB mutations."""
    from zigbeelens.decisions.device_story import device_stories_for_devices
    from zigbeelens.services.evidence_graph import EvidenceGraphService

    repo, _config = _repo(tmp_path)
    _add_device(repo, "home", "0xaa", "Sensor")
    _add_snapshot(repo, snapshot_id="s-complete", network_id="home")
    repo.db.conn.execute(
        "INSERT INTO topology_nodes (snapshot_id, network_id, ieee_address, friendly_name, "
        "node_type, depth, lqi) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("s-complete", "home", "0xaa", "Sensor", "EndDevice", 1, 90),
    )
    repo.db.conn.commit()

    ctx = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=EVIDENCE_GRAPH_REQUIREMENTS,
        device_rows=repo.list_devices("home"),
    )
    before_nodes = len(ctx.latest_nodes or ())
    before_devices = len(ctx.device_rows or ())

    # Mutate the temporary DB after freeze.
    repo.db.conn.execute("DELETE FROM topology_nodes WHERE snapshot_id = ?", ("s-complete",))
    repo.db.conn.execute("DELETE FROM devices WHERE network_id = ? AND ieee_address = ?", ("home", "0xaa"))
    repo.db.conn.commit()

    counter = install_counter(repo)
    counter.reset()
    graph = EvidenceGraphService(repo).build("home", now=NOW, context=ctx)
    stories = device_stories_for_devices(
        repo,
        list(ctx.device_rows or ()),
        now=NOW,
        network_evidence_contexts={"home": ctx},
    )
    assert len(graph["nodes"]) == before_nodes
    assert len(stories) == before_devices
    assert ctx.investigations is not None
    assert ctx.network_topology_coverage is not None
    # No context-owned network evidence rereads while projecting.
    # Per-device availability-history / device-snapshot reads remain outside Track 3G.
    assert counter.stats.category_counts.get("read.topology_snapshots", 0) == 0
    assert counter.stats.category_counts.get("read.topology_nodes", 0) == 0
    assert counter.stats.category_counts.get("read.topology_links", 0) == 0
    assert counter.stats.category_counts.get("read.devices", 0) == 0

    # A freshly built context may observe the mutation.
    later = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=frozenset({NetworkEvidenceCapability.devices, NetworkEvidenceCapability.latest_topology}),
    )
    assert later.device_rows == ()
    assert later.latest_nodes == ()


def test_failed_latest_snapshot_uses_earlier_complete(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    _add_snapshot(
        repo,
        snapshot_id="old-complete",
        network_id="home",
        captured_at=NOW.replace(hour=10).isoformat(),
    )
    _add_snapshot(
        repo,
        snapshot_id="new-failed",
        network_id="home",
        status="failed",
        captured_at=NOW.replace(hour=11).isoformat(),
    )
    ctx = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=frozenset({NetworkEvidenceCapability.latest_topology}),
    )
    assert ctx.latest_usable_snapshot is not None
    assert ctx.latest_usable_snapshot["snapshot_id"] == "old-complete"


def test_availability_collection_feeds_derived_outputs_once(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    _add_device(repo, "home", "0xa", "A")
    _add_device(repo, "home", "0xb", "B")
    for minute, ieee in ((0, "0xa"), (1, "0xb"), (10, "0xa"), (11, "0xb")):
        repo.db.conn.execute(
            "INSERT INTO availability_changes "
            "(network_id, ieee_address, from_state, to_state, changed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "home",
                ieee,
                "online",
                "offline",
                NOW.replace(day=14, minute=minute).isoformat(),
            ),
        )
    repo.db.conn.commit()
    counter = install_counter(repo)
    counter.reset()
    ctx = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=frozenset(
            {
                NetworkEvidenceCapability.devices,
                NetworkEvidenceCapability.availability_observations,
                NetworkEvidenceCapability.passive_hints,
                NetworkEvidenceCapability.shared_availability,
                NetworkEvidenceCapability.model_patterns,
            }
        ),
        device_rows=repo.list_devices("home"),
    )
    assert counter.stats.category_counts.get("read.availability_changes", 0) == 1
    assert ctx.passive_hints is not None
    assert ctx.shared_availability is not None
    assert ctx.model_patterns is not None
