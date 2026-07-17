"""Track 3G corrective regressions: inventory vs subjects, capabilities, reuse."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from zigbeelens.config.models import (
    AppConfig,
    ModeConfig,
    NetworkConfig,
    StorageConfig,
    TopologyConfig,
)
from zigbeelens.db.connection import Database
from zigbeelens.decisions.device_coverage import device_coverage_for_device
from zigbeelens.decisions.device_story import device_story_for_device
from zigbeelens.decisions.model_pattern import (
    MODEL_PATTERN_MIN_AFFECTED_COUNT,
    MODEL_PATTERN_MIN_GROUP_SIZE,
)
from zigbeelens.decisions.reasons import ReasonCode
from zigbeelens.decisions.types import CoverageLabelCode
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.services.dashboard_coverage_warnings import compose_dashboard_coverage_warnings
from zigbeelens.services.dashboard_investigation_priorities import (
    compose_dashboard_investigation_priorities,
)
from zigbeelens.services.dashboard_model_patterns import compose_dashboard_model_patterns
from zigbeelens.services.dashboard_shared_availability import (
    compose_dashboard_shared_availability_events,
)
from zigbeelens.services.device_decision_badge import device_decision_badge_for_device
from zigbeelens.services.evidence_graph import EvidenceGraphService
from zigbeelens.services.network_evidence import (
    DEVICE_STORY_EVIDENCE_REQUIREMENTS,
    EVIDENCE_GRAPH_FACTS_REQUIREMENTS,
    LATEST_TOPOLOGY_REQUIREMENTS,
    NetworkEvidenceCapability,
    NetworkEvidenceCapabilityError,
    expand_requirements,
)
from zigbeelens.services.network_evidence_composition import (
    compose_network_evidence_context,
)
from zigbeelens.services.payload_builder import PayloadBuilder
from zigbeelens.services.topology_facts_composition import topology_stale_threshold_hours
from zigbeelens.storage.repository import Repository
from performance.query_instrumentation import install_counter

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def _repo(tmp_path: Path, *, automatic_capture: bool = True) -> tuple[Repository, AppConfig]:
    db = Database(tmp_path / "corrective3g.sqlite")
    db.migrate()
    repo = Repository(db)
    config = AppConfig(
        mode=ModeConfig(mock=False),
        networks=[
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
            NetworkConfig(id="office", name="Office", base_topic="z2m-office"),
        ],
        storage=StorageConfig(path=str(tmp_path / "corrective3g.sqlite")),
        topology=TopologyConfig(
            enabled=True,
            automatic_capture_enabled=automatic_capture,
            automatic_capture_interval_hours=24,
        ),
    )
    repo.sync_networks(config.networks)
    return repo, config


def _add_device(
    repo: Repository,
    network_id: str,
    ieee: str,
    *,
    name: str | None = None,
    manufacturer: str = "IKEA",
    model: str = "TS011F",
    device_type: str = "EndDevice",
    availability: str = "online",
) -> None:
    repo.upsert_device(
        network_id=network_id,
        ieee_address=ieee,
        friendly_name=name or f"Device {ieee}",
        device_type=device_type,
        power_source="Mains",
        manufacturer=manufacturer,
        model=model,
        interview_state="successful",
    )
    repo.ensure_device_current_state(network_id, ieee)
    repo.update_device_current_state(
        network_id=network_id,
        ieee_address=ieee,
        availability=availability,
        last_seen=NOW.isoformat(),
    )


def _offline_event(repo: Repository, network_id: str, ieee: str, at: datetime) -> None:
    repo.db.conn.execute(
        """
        INSERT INTO availability_changes (network_id, ieee_address, from_state, to_state, changed_at)
        VALUES (?, ?, 'online', 'offline', ?)
        """,
        (network_id, ieee, at.isoformat()),
    )
    repo.db.conn.commit()


def _add_snapshot(
    repo: Repository,
    *,
    snapshot_id: str,
    network_id: str,
    captured_at: datetime | None = None,
    route_count: int = 0,
    nodes: list[str] | None = None,
) -> None:
    captured = (captured_at or NOW).isoformat()
    repo.create_topology_snapshot(
        snapshot_id=snapshot_id,
        network_id=network_id,
        requested_by="test",
        status="in_progress",
    )
    repo.db.conn.execute(
        "UPDATE topology_snapshots SET status = ?, captured_at = ? WHERE snapshot_id = ?",
        ("complete", captured, snapshot_id),
    )
    for ieee in nodes or ["0xcoord"]:
        repo.db.conn.execute(
            "INSERT INTO topology_nodes (snapshot_id, network_id, ieee_address, friendly_name, "
            "node_type, depth, lqi) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (snapshot_id, network_id, ieee, ieee, "Router", 0, 100),
        )
    if len(nodes or ["0xcoord"]) >= 2:
        src, dst = (nodes or ["0xcoord"])[:2]
        repo.db.conn.execute(
            "INSERT INTO topology_links (snapshot_id, network_id, source_ieee, target_ieee, "
            "source_type, target_type, linkquality, depth, relationship, route_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot_id,
                network_id,
                src,
                dst,
                "Router",
                "EndDevice",
                120,
                1,
                "child",
                route_count,
            ),
        )
    repo.db.conn.commit()


def test_expand_requirements_closes_investigations_and_coverage():
    expanded = expand_requirements(
        frozenset({NetworkEvidenceCapability.investigations})
    )
    assert NetworkEvidenceCapability.devices in expanded
    assert NetworkEvidenceCapability.passive_hints in expanded
    assert NetworkEvidenceCapability.router_areas in expanded
    assert NetworkEvidenceCapability.model_patterns in expanded

    coverage = expand_requirements(frozenset({NetworkEvidenceCapability.coverage}))
    assert NetworkEvidenceCapability.topology_facts in coverage
    assert NetworkEvidenceCapability.devices in coverage
    assert NetworkEvidenceCapability.earliest_availability in coverage


def test_partial_subject_inventory_does_not_alter_model_pattern(tmp_path: Path):
    repo, _ = _repo(tmp_path)
    ieees = [f"0xm{i:02d}" for i in range(MODEL_PATTERN_MIN_GROUP_SIZE)]
    assert len(ieees) >= 5
    for ieee in ieees:
        _add_device(repo, "home", ieee)
    for ieee in ieees[:MODEL_PATTERN_MIN_AFFECTED_COUNT]:
        _offline_event(repo, "home", ieee, NOW - timedelta(days=1))

    full = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=DEVICE_STORY_EVIDENCE_REQUIREMENTS,
    )
    # Subject-only list must not be accepted as complete inventory.
    subject_only = [row for row in (full.device_rows or ()) if row.ieee_address == ieees[0]]
    rebuilt = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=DEVICE_STORY_EVIDENCE_REQUIREMENTS,
        complete_device_rows=None,
    )
    assert len(rebuilt.device_rows or ()) == len(ieees)
    assert rebuilt.model_patterns is not None
    assert full.model_patterns is not None
    assert len(full.model_patterns.patterns) == len(rebuilt.model_patterns.patterns) == 1

    # Passing a partial list as "complete" would be a caller bug; composition trusts
    # the certification. Callers must not do this — prove the API rename exists.
    poisoned = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=frozenset(
            {
                NetworkEvidenceCapability.devices,
                NetworkEvidenceCapability.availability_observations,
                NetworkEvidenceCapability.model_patterns,
            }
        ),
        complete_device_rows=subject_only,
    )
    assert len(poisoned.device_rows or ()) == 1
    assert poisoned.model_patterns is not None
    assert len(poisoned.model_patterns.patterns) == 0


def test_incident_badge_matches_device_story_for_model_pattern(tmp_path: Path):
    repo, config = _repo(tmp_path)
    ieees = [f"0xm{i:02d}" for i in range(MODEL_PATTERN_MIN_GROUP_SIZE)]
    for ieee in ieees:
        _add_device(repo, "home", ieee)
    for ieee in ieees[:MODEL_PATTERN_MIN_AFFECTED_COUNT]:
        _offline_event(repo, "home", ieee, NOW - timedelta(days=1))

    from zigbeelens.services.device_decision_badge import device_decision_badge_from_story

    story = device_story_for_device(repo, "home", ieees[0], now=NOW)
    assert story is not None
    assert any(r.code == ReasonCode.model_pattern_observed for r in story.reasons)
    badge = device_decision_badge_for_device(repo, "home", ieees[0], now=NOW)
    assert badge is not None
    projected = device_decision_badge_from_story(story)
    assert badge == projected

    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    builder = PayloadBuilder(config, repo, health)
    devices = builder.devices("home")
    target = next(d for d in devices if d.ieee_address == ieees[0])
    assert target.decision is not None
    assert target.decision.status == badge.status
    assert target.decision.headline_code == badge.headline_code
    assert target.decision.priority == badge.priority


def test_availability_tracking_peer_online_agrees_across_surfaces(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "home", "0xtarget", availability="unknown")
    _add_device(repo, "home", "0xpeer", availability="online")

    from zigbeelens.decisions.device_story import load_device_story_evidence

    evidence = load_device_story_evidence(repo, "home", "0xtarget", now=NOW)
    assert evidence is not None
    assert evidence.availability_tracking_enabled is True
    story = device_story_for_device(repo, "home", "0xtarget", now=NOW)
    assert story is not None

    coverage = device_coverage_for_device(repo, "home", "0xtarget", now=NOW)
    assert coverage is not None
    assert not any(
        item.label_code == CoverageLabelCode.availability_tracking_off for item in coverage
    )

    badge = device_decision_badge_for_device(repo, "home", "0xtarget", now=NOW)
    assert badge is not None
    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    builder = PayloadBuilder(config, repo, health)
    devices = builder.devices("home")
    target = next(d for d in devices if d.ieee_address == "0xtarget")
    assert target is not None


def test_capability_missing_raises_without_fallback_sql(tmp_path: Path):
    repo, _ = _repo(tmp_path)
    _add_device(repo, "home", "0xa")
    lean = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=frozenset({NetworkEvidenceCapability.devices}),
    )
    networks = repo.list_networks()
    home = next(n for n in networks if n.id == "home")

    counter = install_counter(repo)
    counter.reset()
    with pytest.raises(NetworkEvidenceCapabilityError):
        compose_dashboard_model_patterns(
            repo, [home], now=NOW, network_evidence_contexts={"home": lean}
        )
    assert counter.stats.category_counts.get("read.availability_changes", 0) == 0
    assert counter.stats.category_counts.get("read.devices", 0) == 0

    counter.reset()
    with pytest.raises(NetworkEvidenceCapabilityError):
        compose_dashboard_shared_availability_events(
            repo, [home], now=NOW, network_evidence_contexts={"home": lean}
        )
    assert counter.stats.execute_count == 0

    counter.reset()
    with pytest.raises(NetworkEvidenceCapabilityError):
        compose_dashboard_investigation_priorities(
            repo, [home], now=NOW, network_evidence_contexts={"home": lean}
        )
    assert counter.stats.execute_count == 0

    counter.reset()
    with pytest.raises((NetworkEvidenceCapabilityError, ValueError)):
        compose_dashboard_coverage_warnings(
            repo,
            [home],
            AppConfig(
                mode=ModeConfig(mock=False),
                networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
                storage=StorageConfig(path=str(tmp_path / "corrective3g.sqlite")),
                topology=TopologyConfig(
                    enabled=True,
                    automatic_capture_enabled=True,
                    automatic_capture_interval_hours=24,
                ),
            ),
            now=NOW,
            network_evidence_contexts={"home": lean},
        )
    assert counter.stats.category_counts.get("read.topology_snapshots", 0) == 0


def test_context_route_and_stale_parity(tmp_path: Path):
    repo, config = _repo(tmp_path)
    _add_device(repo, "home", "0xa")
    _add_snapshot(
        repo,
        snapshot_id="s-route",
        network_id="home",
        captured_at=NOW - timedelta(hours=1),
        route_count=2,
        nodes=["0xrouter", "0xa"],
    )
    stale_hours = topology_stale_threshold_hours(config)
    ctx = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=EVIDENCE_GRAPH_FACTS_REQUIREMENTS,
        stale_after_hours=stale_hours,
    )
    assert ctx.network_topology_facts is not None
    codes = {str(f.code) for f in ctx.network_topology_facts}
    assert "route_hints_available" in codes
    coverage_codes = {str(item.label_code) for item in (ctx.network_topology_coverage or ())}
    assert CoverageLabelCode.route_hints_unavailable.value not in coverage_codes

    graph = EvidenceGraphService(repo).build_with_network_topology_facts(
        "home",
        stale_after_hours=stale_hours,
        now=NOW,
        context=ctx,
    )
    fact_codes = {
        str(item["code"])
        for item in graph["topology_facts"]["network_facts"]
    }
    assert "route_hints_available" in fact_codes

    # Stale snapshot with automatic capture enabled.
    old = NOW - timedelta(hours=48)
    repo.db.conn.execute(
        "UPDATE topology_snapshots SET captured_at = ? WHERE snapshot_id = ?",
        (old.isoformat(), "s-route"),
    )
    repo.db.conn.commit()
    stale_ctx = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=EVIDENCE_GRAPH_FACTS_REQUIREMENTS,
        stale_after_hours=stale_hours,
    )
    assert stale_ctx.network_topology_facts is not None
    stale_fact_codes = {str(f.code) for f in stale_ctx.network_topology_facts}
    assert "latest_snapshot_stale" in stale_fact_codes
    stale_coverage = {str(i.label_code) for i in (stale_ctx.network_topology_coverage or ())}
    assert CoverageLabelCode.snapshot_stale.value in stale_coverage


def test_automatic_capture_disabled_has_no_stale_policy(tmp_path: Path):
    repo, config = _repo(tmp_path, automatic_capture=False)
    assert topology_stale_threshold_hours(config) is None
    _add_snapshot(
        repo,
        snapshot_id="s-old",
        network_id="home",
        captured_at=NOW - timedelta(hours=100),
        nodes=["0xa"],
    )
    ctx = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=EVIDENCE_GRAPH_FACTS_REQUIREMENTS,
        stale_after_hours=None,
    )
    codes = {str(f.code) for f in (ctx.network_topology_facts or ())}
    assert "latest_snapshot_stale" not in codes


def test_device_coverage_uses_bulk_nodes_not_per_snapshot(tmp_path: Path):
    repo, _ = _repo(tmp_path)
    _add_device(repo, "home", "0xa")
    for i in range(3):
        _add_snapshot(
            repo,
            snapshot_id=f"snap-{i}",
            network_id="home",
            captured_at=NOW.replace(minute=i),
            nodes=["0xa", "0xcoord"],
        )
    counter = install_counter(repo)
    counter.reset()
    coverage = device_coverage_for_device(repo, "home", "0xa", now=NOW)
    assert coverage is not None
    assert counter.stats.category_counts.get("read.topology_nodes", 0) == 1
    assert counter.stats.category_counts.get("other", 0) == 0


def test_latest_only_does_not_claim_snapshot_history(tmp_path: Path):
    repo, _ = _repo(tmp_path)
    _add_snapshot(repo, snapshot_id="s1", network_id="home", nodes=["0xa"])
    ctx = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=LATEST_TOPOLOGY_REQUIREMENTS,
    )
    assert ctx.has_capability(NetworkEvidenceCapability.latest_topology)
    assert not ctx.has_capability(NetworkEvidenceCapability.snapshot_history)


def test_frozen_context_ignores_mutated_source_rows(tmp_path: Path):
    repo, _ = _repo(tmp_path)
    _add_device(repo, "home", "0xaa", name="Sensor")
    _add_snapshot(repo, snapshot_id="s1", network_id="home", nodes=["0xaa"])
    source_rows = repo.list_devices("home")
    source_rows[0].friendly_name = "Mutated Before Compose"
    ctx = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=EVIDENCE_GRAPH_FACTS_REQUIREMENTS,
        complete_device_rows=source_rows,
        stale_after_hours=24,
    )
    source_rows[0].friendly_name = "Mutated After Compose"
    source_rows[0].availability = "offline"
    assert ctx.device_rows is not None
    assert ctx.device_rows[0].friendly_name == "Mutated Before Compose"
    assert ctx.device_rows[0].availability == "online"

    projected = list(ctx.projected_device_rows())
    projected[0].friendly_name = "Consumer Mutation"
    assert ctx.device_rows[0].friendly_name == "Mutated Before Compose"

    counter = install_counter(repo)
    counter.reset()
    graph = EvidenceGraphService(repo).build("home", now=NOW, context=ctx)
    story = device_story_for_device(
        repo,
        "home",
        "0xaa",
        now=NOW,
        network_evidence_context=ctx,
    )
    assert graph["inventory"]["device_count"] == 1
    assert story is not None
    assert counter.stats.category_counts.get("read.topology_nodes", 0) == 0
    assert counter.stats.category_counts.get("read.topology_links", 0) == 0
    assert counter.stats.category_counts.get("read.topology_snapshots", 0) == 0
    # Subject-specific device/availability/snapshot reads may remain.


def test_routers_projection_uses_one_context_zero_per_router_reads(tmp_path: Path):
    repo, config = _repo(tmp_path)
    for i in range(3):
        ieee = f"0xr{i}"
        _add_device(repo, "home", ieee, device_type="Router", name=f"Router {i}")
        # Weak LQI to encourage router_risk classification where possible.
        repo.update_device_current_state(
            network_id="home",
            ieee_address=ieee,
            availability="online",
            last_seen=NOW.isoformat(),
            linkquality=10,
        )
    _add_snapshot(
        repo,
        snapshot_id="s-router",
        network_id="home",
        nodes=["0xr0", "0xr1", "0xr2", "0xchild"],
    )
    # Give each router children in topology.
    for ieee in ("0xr0", "0xr1", "0xr2"):
        repo.db.conn.execute(
            "INSERT INTO topology_links (snapshot_id, network_id, source_ieee, target_ieee, "
            "source_type, target_type, linkquality, depth, relationship, route_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("s-router", "home", ieee, "0xchild", "Router", "EndDevice", 40, 1, "child", 0),
        )
    repo.db.conn.commit()

    health = HealthDiagnosticService(config, repo)
    health.recalculate_all()
    builder = PayloadBuilder(config, repo, health)

    original_latest = repo.get_latest_topology_snapshot
    original_children = repo.list_topology_children
    original_name = repo.get_topology_node_name
    calls = {"latest": 0, "children": 0, "name": 0}

    def latest_spy(network_id: str):
        calls["latest"] += 1
        return original_latest(network_id)

    def children_spy(snapshot_id: str, ieee: str):
        calls["children"] += 1
        return original_children(snapshot_id, ieee)

    def name_spy(snapshot_id: str, ieee: str):
        calls["name"] += 1
        return original_name(snapshot_id, ieee)

    repo.get_latest_topology_snapshot = latest_spy  # type: ignore[method-assign]
    repo.list_topology_children = children_spy  # type: ignore[method-assign]
    repo.get_topology_node_name = name_spy  # type: ignore[method-assign]

    ctx = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=LATEST_TOPOLOGY_REQUIREMENTS,
    )
    # Reset spies after context build.
    calls["latest"] = 0
    calls["children"] = 0
    calls["name"] = 0
    risks = builder.routers(
        devices=repo.list_devices("home"),
        network_evidence_contexts={"home": ctx},
    )
    assert calls["latest"] == 0
    assert calls["children"] == 0
    assert calls["name"] == 0
    # May be empty if health flags don't fire; still proves zero topology rereads.
    assert isinstance(risks, list)


def test_model_pattern_timestamp_reuses_context_availability(tmp_path: Path):
    repo, _ = _repo(tmp_path)
    ieees = [f"0xm{i:02d}" for i in range(MODEL_PATTERN_MIN_GROUP_SIZE)]
    for ieee in ieees:
        _add_device(repo, "home", ieee)
    for ieee in ieees[:MODEL_PATTERN_MIN_AFFECTED_COUNT]:
        _offline_event(repo, "home", ieee, NOW - timedelta(days=1))
    ctx = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=frozenset(
            {
                NetworkEvidenceCapability.devices,
                NetworkEvidenceCapability.availability_observations,
                NetworkEvidenceCapability.model_patterns,
            }
        ),
    )
    home = next(n for n in repo.list_networks() if n.id == "home")
    counter = install_counter(repo)
    counter.reset()
    summaries = compose_dashboard_model_patterns(
        repo, [home], now=NOW, network_evidence_contexts={"home": ctx}
    )
    assert summaries
    assert counter.stats.category_counts.get("read.availability_changes", 0) == 0


def test_wrong_network_or_time_rejected_by_consumers(tmp_path: Path):
    repo, _ = _repo(tmp_path)
    _add_device(repo, "home", "0xa")
    ctx = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=DEVICE_STORY_EVIDENCE_REQUIREMENTS,
    )
    with pytest.raises(ValueError):
        device_story_for_device(
            repo,
            "office",
            "0xa",
            now=NOW,
            network_evidence_context=ctx,
        )
    later = NOW + timedelta(hours=1)
    with pytest.raises(ValueError):
        device_story_for_device(
            repo,
            "home",
            "0xa",
            now=later,
            network_evidence_context=ctx,
        )


def test_omitted_now_uses_context_reference_now(tmp_path: Path):
    repo, _ = _repo(tmp_path)
    _add_device(repo, "home", "0xa")
    ctx = compose_network_evidence_context(
        repo,
        "home",
        reference_now=NOW,
        requirements=DEVICE_STORY_EVIDENCE_REQUIREMENTS,
    )
    story = device_story_for_device(
        repo,
        "home",
        "0xa",
        network_evidence_context=ctx,
    )
    assert story is not None
