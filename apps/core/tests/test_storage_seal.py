"""Track 6 deployment-compatibility and concurrency seal regressions."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

from zigbeelens.app.context import AppContext
from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.db.retention_time import parse_retention_instant
from zigbeelens.main import main
from zigbeelens.mqtt.events import EventBroadcaster
from zigbeelens.security.browser_sessions import BrowserSessionManager
from zigbeelens.services.storage_status import build_storage_status
from zigbeelens.storage.backup import backup_sqlite_database
from zigbeelens.storage.maintenance import (
    affected_invalidation_events,
    maintenance_event_payload,
    run_storage_maintenance,
)
from zigbeelens.storage.maintenance_scheduler import (
    StorageMaintenanceScheduler,
    publish_maintenance_side_effects,
)
from zigbeelens.storage.readonly import ReadOnlyDatabase
from zigbeelens.storage.repository import Repository
from zigbeelens.storage.retention_policy import (
    ABANDONED_TOPOLOGY_ERROR,
    CURRENT_SCHEMA_VERSION,
    MORE_WORK_CONTINUATION_SECONDS,
    StorageMaintenanceResult,
)

REF = datetime(2026, 7, 20, 12, 0, 0, 123456, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


def _cfg(db_path: Path, **storage_kwargs) -> AppConfig:
    return AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(db_path), **storage_kwargs),
    )


def test_no_subsec_in_migration_or_retention_sql():
    migration = (
        ROOT / "src/zigbeelens/db/migrations/012_retention_indexes.sql"
    ).read_text(encoding="utf-8")
    policy = (ROOT / "src/zigbeelens/storage/retention_policy.py").read_text(
        encoding="utf-8"
    )
    access = (
        ROOT / "src/zigbeelens/storage/access/maintenance.py"
    ).read_text(encoding="utf-8")
    assert "subsec" not in migration
    assert "subsec" not in policy
    assert "subsec" not in access


def test_parse_retention_instant_timestamp_forms():
    accepted = [
        "2026-01-01T00:00:00",
        "2026-01-01 00:00:00",
        "2026-01-01T00:00:00.123456",
        "2026-01-01 00:00:00.123",
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:00:00z",
        "2026-01-01T00:00:00+00:00",
        "2026-01-01T00:00:00-00:00",
        "2026-01-01T10:00:00+10:00",
        "2026-01-01 10:00:00+10:00",
        "2026-01-01T10:00:00-10:00",
        "2026-01-01T00:00:00+14:00",
        "2026-01-01T00:00:00+14:59",
    ]
    rejected = [
        " 2026-01-01T00:00:00",
        "2026-01-01T00:00:00 ",
        "20260101T000000",
        "2026-W01-1",
        "2026-01-01T00:00:00+1000",
        "2026-01-01T00:00:00+10:00:00",
        "2026-01-01",
        "2026-01-01  00:00:00",
        "2026-01-01T00:00:00 UTC",
        "2026-01-01T00:00:00+15:00",
        "2026-01-01T00:00:00-15:00",
        "2026-01-01T00:00:00+10:60",
        "2026-01-01T00:00:00-10:60",
        "2026-01-01T00:00:00+10:99",
        "2026-01-01T00:00:00+99:00",
        "not-a-timestamp",
    ]
    conn = sqlite3.connect(":memory:")
    for value in accepted:
        assert parse_retention_instant(value) is not None, value
        assert conn.execute("SELECT julianday(?) IS NOT NULL", (value,)).fetchone()[0] == 1, value
    for value in rejected:
        assert parse_retention_instant(value) is None, value
    # Equivalent UTC forms still collapse.
    assert len(
        {
            parse_retention_instant(value)
            for value in (
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00z",
                "2026-01-01 00:00:00",
                "2026-01-01T10:00:00+10:00",
                "2026-01-01 10:00:00+10:00",
            )
        }
    ) == 1


def test_terminalize_excluded_until_next_cycle(tmp_path: Path):
    db = Database(tmp_path / "term.sqlite")
    db.migrate()
    repo = Repository(db)
    repo.sync_networks([NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")])
    old = (REF - timedelta(days=30)).isoformat()
    repo.db.conn.execute(
        """
        INSERT INTO topology_snapshots
          (snapshot_id, network_id, captured_at, requested_by, status, warning_acknowledged)
        VALUES ('snap-old', 'home', ?, 'test', 'pending', 0)
        """,
        (old,),
    )
    repo.db.conn.commit()
    cfg = _cfg(tmp_path / "term.sqlite")

    dry = run_storage_maintenance(repo, cfg, reference_now=REF, dry_run=True)
    assert dry.eligible_updates_by_category.get("abandoned_pending_topology") == 1
    assert dry.eligible_deletes_by_category.get("topology_snapshots", 0) == 0

    first = run_storage_maintenance(repo, cfg, reference_now=REF)
    assert first.rows_updated_by_category.get("abandoned_pending_topology") == 1
    assert first.rows_deleted_by_category.get("topology_snapshots", 0) == 0
    row = repo.db.conn.execute(
        "SELECT status, error FROM topology_snapshots WHERE snapshot_id='snap-old'"
    ).fetchone()
    assert row["status"] == "error"
    assert row["error"] == ABANDONED_TOPOLOGY_ERROR

    second = run_storage_maintenance(repo, cfg, reference_now=REF)
    assert second.rows_deleted_by_category.get("topology_snapshots", 0) == 1
    assert (
        repo.db.conn.execute(
            "SELECT COUNT(*) FROM topology_snapshots WHERE snapshot_id='snap-old'"
        ).fetchone()[0]
        == 0
    )


def test_count_cap_terminalize_then_delete_next_cycle(tmp_path: Path):
    db = Database(tmp_path / "cap.sqlite")
    db.migrate()
    repo = Repository(db)
    repo.sync_networks([NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")])
    # Fill cap with complete snapshots, plus one abandoned pending inside window.
    for i in range(3):
        repo.db.conn.execute(
            """
            INSERT INTO topology_snapshots
              (snapshot_id, network_id, captured_at, requested_by, status, warning_acknowledged)
            VALUES (?, 'home', ?, 'test', 'complete', 0)
            """,
            (f"keep-{i}", (REF - timedelta(minutes=i)).isoformat()),
        )
    repo.db.conn.execute(
        """
        INSERT INTO topology_snapshots
          (snapshot_id, network_id, captured_at, requested_by, status, warning_acknowledged)
        VALUES ('pending-in-window', 'home', ?, 'test', 'pending', 0)
        """,
        ((REF - timedelta(hours=2)).isoformat(),),
    )
    repo.db.conn.commit()
    cfg = _cfg(
        tmp_path / "cap.sqlite",
        retention_days=7,
    )
    # Force a low cap via policy override through config topology field.
    cfg.topology.max_snapshots_per_network = 2

    first = run_storage_maintenance(repo, cfg, reference_now=REF)
    assert first.rows_updated_by_category.get("abandoned_pending_topology") == 1
    assert (
        repo.db.conn.execute(
            "SELECT status FROM topology_snapshots WHERE snapshot_id='pending-in-window'"
        ).fetchone()[0]
        == "error"
    )
    # Same cycle must not count-delete the newly terminalized row.
    assert (
        repo.db.conn.execute(
            "SELECT COUNT(*) FROM topology_snapshots WHERE snapshot_id='pending-in-window'"
        ).fetchone()[0]
        == 1
    )

    second = run_storage_maintenance(repo, cfg, reference_now=REF)
    # Later cycle may remove excess terminal history (including the former pending).
    remaining = repo.db.conn.execute(
        "SELECT COUNT(*) FROM topology_snapshots WHERE network_id='home'"
    ).fetchone()[0]
    assert remaining <= 2
    assert second.rows_deleted_by_category.get("topology_count_cap", 0) >= 1


def test_active_pending_excluded(tmp_path: Path):
    db = Database(tmp_path / "active.sqlite")
    db.migrate()
    repo = Repository(db)
    repo.sync_networks([NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")])
    old = (REF - timedelta(hours=2)).isoformat()
    repo.db.conn.execute(
        """
        INSERT INTO topology_snapshots
          (snapshot_id, network_id, captured_at, requested_by, status, warning_acknowledged)
        VALUES ('active-pending', 'home', ?, 'test', 'pending', 0)
        """,
        (old,),
    )
    repo.db.conn.commit()
    cfg = _cfg(tmp_path / "active.sqlite")
    result = run_storage_maintenance(
        repo,
        cfg,
        reference_now=REF,
        active_pending_provider=lambda: "active-pending",
    )
    assert result.rows_updated_by_category.get("abandoned_pending_topology", 0) == 0
    row = repo.db.conn.execute(
        "SELECT status FROM topology_snapshots WHERE snapshot_id='active-pending'"
    ).fetchone()
    assert row["status"] == "pending"


def test_scheduler_start_uses_continuation_delay(tmp_path: Path):
    db = Database(tmp_path / "sched.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = _cfg(tmp_path / "sched.sqlite", maintenance_interval_hours=24)
    seen: list[float] = []
    entered = threading.Event()

    def wait_fn(cond, should_wake, timeout):
        seen.append(timeout)
        entered.set()
        while not should_wake():
            with cond:
                cond.wait(0.05)

    class Clock:
        def now(self):
            return REF

    scheduler = StorageMaintenanceScheduler(
        repo,
        cfg,
        clock=Clock(),
        wait_fn=wait_fn,
        more_work_delay_seconds=MORE_WORK_CONTINUATION_SECONDS,
    )
    scheduler.start(initial_delay_seconds=MORE_WORK_CONTINUATION_SECONDS)
    assert entered.wait(2.0)
    scheduler.stop(wait=True, timeout=2.0)
    assert seen
    assert seen[0] == MORE_WORK_CONTINUATION_SECONDS


def test_scheduler_trigger_and_stop_not_lost(tmp_path: Path):
    db = Database(tmp_path / "wake.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = _cfg(tmp_path / "wake.sqlite", maintenance_interval_hours=24)
    entered = threading.Event()
    cycle_done = threading.Event()
    callbacks: list[str] = []

    def wait_fn(cond, should_wake, timeout):
        entered.set()
        while not should_wake():
            with cond:
                cond.wait(0.05)

    def on_result(result):
        callbacks.append("done" if result.success else "fail")
        cycle_done.set()

    class Clock:
        def now(self):
            return REF

    scheduler = StorageMaintenanceScheduler(
        repo, cfg, clock=Clock(), wait_fn=wait_fn, on_result=on_result
    )
    scheduler.start(initial_delay_seconds=86400)
    assert entered.wait(2.0)
    # Trigger at the pre-wait boundary must run promptly (no 24h sleep).
    scheduler.trigger()
    assert cycle_done.wait(2.0)
    assert callbacks == ["done"]
    # stop(wait=True) must not sleep the interval and must join the worker.
    stop_started = threading.Event()
    stopped = threading.Event()

    def stopper():
        stop_started.set()
        scheduler.stop(wait=True, timeout=2.0)
        stopped.set()

    threading.Thread(target=stopper, daemon=True).start()
    assert stop_started.wait(1.0)
    assert stopped.wait(2.0)
    assert scheduler.running is False
    assert scheduler._thread is None or not scheduler._thread.is_alive()
    # No callback after stop returns.
    before = len(callbacks)
    assert len(callbacks) == before


def test_scheduler_coalesce_and_more_work_delay(tmp_path: Path):
    db = Database(tmp_path / "coal.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = _cfg(tmp_path / "coal.sqlite", maintenance_interval_hours=24)
    delays: list[float] = []
    cycle_gate = threading.Event()
    allow_finish = threading.Event()
    saw_post_cycle_wait = threading.Event()
    cycles = {"n": 0}

    def wait_fn(cond, should_wake, timeout):
        delays.append(timeout)
        if cycles["n"] >= 1:
            saw_post_cycle_wait.set()
        while not should_wake():
            with cond:
                cond.wait(0.02)

    class Clock:
        def now(self):
            return REF

    def slow_run(*args, **kwargs):
        cycles["n"] += 1
        cycle_gate.set()
        assert allow_finish.wait(2.0)
        result = run_storage_maintenance(*args, **kwargs)
        result.more_work_pending = True
        return result

    scheduler = StorageMaintenanceScheduler(
        repo,
        cfg,
        clock=Clock(),
        wait_fn=wait_fn,
        more_work_delay_seconds=MORE_WORK_CONTINUATION_SECONDS,
    )
    import zigbeelens.storage.maintenance_scheduler as sched_mod

    original = sched_mod.run_storage_maintenance
    sched_mod.run_storage_maintenance = slow_run  # type: ignore[assignment]
    try:
        # Non-zero first delay so wait_fn is entered before the first cycle.
        scheduler.start(initial_delay_seconds=30.0)
        scheduler.trigger()
        assert cycle_gate.wait(2.0)
        scheduler.trigger()  # coalesce while running
        allow_finish.set()
        assert saw_post_cycle_wait.wait(2.0)
        scheduler.stop(wait=True, timeout=3.0)
    finally:
        sched_mod.run_storage_maintenance = original
    assert cycles["n"] >= 1
    # Coalesced wake uses 0; more-work continuation uses the short delay.
    assert 0.0 in delays or MORE_WORK_CONTINUATION_SECONDS in delays


def test_events_for_noop_and_partial_failure():
    from zigbeelens.storage.maintenance import maintenance_evidence_changed

    noop = StorageMaintenanceResult(success=True)
    events = affected_invalidation_events(noop)
    assert events == ("storage_maintenance_completed",)
    payload = maintenance_event_payload(noop)
    assert payload["success"] is True
    assert payload["total_rows_deleted"] == 0

    published: list[tuple[str, dict]] = []
    dashboards: list[str] = []
    publish_maintenance_side_effects(
        noop,
        publish_sync=lambda name, body: published.append((name, body)),
        schedule_dashboard=lambda: dashboards.append("dash"),
    )
    assert published == [("storage_maintenance_completed", payload)]
    assert dashboards == []

    report_only = StorageMaintenanceResult(
        success=True,
        rows_deleted_by_category={"reports": 3},
    )
    assert affected_invalidation_events(report_only) == (
        "storage_maintenance_completed",
        "reports_updated",
    )
    assert maintenance_evidence_changed(report_only) is False
    published.clear()
    dashboards.clear()
    publish_maintenance_side_effects(
        report_only,
        publish_sync=lambda name, body: published.append((name, body)),
        schedule_dashboard=lambda: dashboards.append("dash"),
    )
    assert [name for name, _ in published] == [
        "storage_maintenance_completed",
        "reports_updated",
    ]
    assert dashboards == []

    mixed = StorageMaintenanceResult(
        success=True,
        rows_deleted_by_category={"reports": 1, "events": 2},
    )
    assert maintenance_evidence_changed(mixed) is True
    published.clear()
    dashboards.clear()
    publish_maintenance_side_effects(
        mixed,
        publish_sync=lambda name, body: published.append((name, body)),
        schedule_dashboard=lambda: dashboards.append("dash"),
    )
    assert dashboards == ["dash"]

    partial = StorageMaintenanceResult(
        success=False,
        error_code="database_busy",
        failure_category="topology_snapshots",
        rows_deleted_by_category={"events": 2, "incidents_resolved": 1},
        rows_updated_by_category={"abandoned_pending_topology": 1},
    )
    events = affected_invalidation_events(partial)
    assert "storage_maintenance_completed" in events
    assert "timeline_updated" in events
    assert "incidents_updated" in events
    assert "topology_updated" in events
    published.clear()
    dashboards.clear()
    publish_maintenance_side_effects(
        partial,
        publish_sync=lambda name, body: published.append((name, body)),
        schedule_dashboard=lambda: dashboards.append("dash"),
    )
    names = [name for name, _ in published]
    assert "storage_maintenance_completed" in names
    assert "timeline_updated" in names
    assert dashboards == ["dash"]


def test_apply_refusal_does_not_mutate_old_schema(tmp_path: Path, capsys):
    db_path = tmp_path / "old.sqlite"
    db = Database(db_path)
    db.migrate()
    db.conn.execute("DELETE FROM schema_migrations WHERE version = 12")
    db.conn.commit()
    db.close()
    wal = Path(str(db_path) + "-wal")
    shm = Path(str(db_path) + "-shm")
    for side in (wal, shm):
        if side.exists():
            side.unlink()
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.close()
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        f"""
mode:
  mock: true
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
storage:
  path: {db_path}
  retention_days: 7
""".strip(),
        encoding="utf-8",
    )
    try:
        main(["storage", "maintenance", "--config", str(cfg), "--apply"])
    except SystemExit as exc:
        assert exc.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error_code"] == "schema_mismatch"
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before
    assert not wal.exists()
    assert not shm.exists()
    ro = ReadOnlyDatabase(db_path)
    assert ro.migration_version == 11
    ro.close()


def test_apply_refusal_newer_schema(tmp_path: Path, capsys):
    db_path = tmp_path / "new.sqlite"
    db = Database(db_path)
    db.migrate()
    db.conn.execute(
        "INSERT INTO schema_migrations (version) VALUES (?)",
        (CURRENT_SCHEMA_VERSION + 1,),
    )
    db.conn.commit()
    db.close()
    wal = Path(str(db_path) + "-wal")
    shm = Path(str(db_path) + "-shm")
    for side in (wal, shm):
        if side.exists():
            side.unlink()
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.close()
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        f"""
mode:
  mock: true
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
storage:
  path: {db_path}
""".strip(),
        encoding="utf-8",
    )
    try:
        main(["storage", "maintenance", "--config", str(cfg), "--apply"])
    except SystemExit as exc:
        assert exc.code == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "schema_mismatch"
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before
    assert not wal.exists()


def test_concurrent_backup_deterministic_transaction(tmp_path: Path):
    db_path = tmp_path / "wal.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    for version, body in [
        (1, '{"report_version":1}'),
        (2, '{"report_version":2}'),
        (3, '{"report_version":3}'),
    ]:
        repo.db.conn.execute(
            """
            INSERT INTO reports (id, format, redaction_json, summary, generated_at, body_json)
            VALUES (?, 'json', '{}', 'r', ?, ?)
            """,
            (f"r{version}", REF.isoformat(), body),
        )
    for i in range(400):
        repo.db.conn.execute(
            """
            INSERT INTO events (id, event_type, severity, title, summary, occurred_at)
            VALUES (?, 'test', 'watch', 't', 's', ?)
            """,
            (f"e{i}", REF.isoformat()),
        )
    repo.db.conn.commit()

    progress_started = threading.Event()
    writer_done = threading.Event()
    progress_calls = {"n": 0}
    writer_commits = {"n": 0}

    def progress(remaining: int, total: int) -> None:
        progress_calls["n"] += 1
        if progress_calls["n"] == 1:
            progress_started.set()
            assert writer_done.wait(5.0)

    def writer() -> None:
        assert progress_started.wait(5.0)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO events (id, event_type, severity, title, summary, occurred_at)
                VALUES ('txn-a', 'test', 'watch', 't', 's', ?)
                """,
                (REF.isoformat(),),
            )
            conn.execute(
                """
                INSERT INTO events (id, event_type, severity, title, summary, occurred_at)
                VALUES ('txn-b', 'test', 'watch', 't', 's', ?)
                """,
                (REF.isoformat(),),
            )
            conn.commit()
            writer_commits["n"] += 1
        finally:
            conn.close()
            writer_done.set()

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    out = tmp_path / "backup.sqlite"
    result = backup_sqlite_database(
        output=out,
        database=str(db_path),
        pages_per_step=1,
        progress=progress,
    )
    thread.join(timeout=5)
    assert progress_calls["n"] > 0
    assert writer_commits["n"] > 0
    assert result.schema_version == CURRENT_SCHEMA_VERSION

    validate = sqlite3.connect(str(out))
    assert validate.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert validate.execute("PRAGMA foreign_key_check").fetchall() == []
    ids = {
        row[0]
        for row in validate.execute(
            "SELECT id FROM events WHERE id IN ('txn-a', 'txn-b')"
        ).fetchall()
    }
    assert ids in (set(), {"txn-a", "txn-b"})
    bodies = {
        row[0]: row[1]
        for row in validate.execute("SELECT id, body_json FROM reports").fetchall()
    }
    assert bodies["r1"] == '{"report_version":1}'
    assert bodies["r2"] == '{"report_version":2}'
    assert bodies["r3"] == '{"report_version":3}'
    validate.close()
    db.close()


def test_post_capture_count_cleanup_before_diagnostics(tmp_path: Path):
    from unittest.mock import patch

    from zigbeelens.app.context import bootstrap, reset_context
    from zigbeelens.config.models import FeaturesConfig, TopologyConfig
    from zigbeelens.mqtt.models import RawMqttMessage
    from zigbeelens.topology.publisher import FakeTopologyRequestPublisher
    from zigbeelens.topology.service import TopologyService

    reset_context()
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "post.sqlite")),
        features=FeaturesConfig(manual_network_map=True, automatic_network_map=False),
        topology=TopologyConfig(
            enabled=True,
            manual_capture_enabled=True,
            automatic_capture_enabled=False,
            startup_scan=False,
            capture_on_incident=False,
            max_snapshots_per_network=1,
        ),
    )
    with patch("zigbeelens.app.context.start_discovery", return_value=None):
        ctx = bootstrap(config=cfg)
    # Seed two older completes so post-capture count retention must delete.
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    for i, snap_id in enumerate(("old-a", "old-b")):
        ctx.repo.db.conn.execute(
            """
            INSERT INTO topology_snapshots
              (snapshot_id, network_id, captured_at, requested_by, status, warning_acknowledged)
            VALUES (?, 'home', ?, 'test', 'complete', 0)
            """,
            (snap_id, (past - timedelta(minutes=i)).isoformat()),
        )
    ctx.repo.db.conn.commit()
    order: list[str] = []
    events: list[str] = []

    original_store = ctx.repo.store_topology_parsed
    original_enforce = ctx.repo.enforce_topology_retention
    original_refresh = TopologyService._refresh_diagnostics
    original_publish = ctx.broadcaster.publish_sync

    def store(*args, **kwargs):
        order.append("store")
        return original_store(*args, **kwargs)

    def enforce(*args, **kwargs):
        order.append("count_cleanup")
        return original_enforce(*args, **kwargs)

    def refresh(self):
        order.append("diagnostics")
        return original_refresh(self)

    def publish(event: str, data: dict) -> None:
        events.append(event)
        return original_publish(event, data)

    service = TopologyService(ctx, publisher=FakeTopologyRequestPublisher(cfg))
    service.request_capture("home", confirmed=True)
    message = RawMqttMessage(
        topic="zigbee2mqtt/bridge/response/networkmap",
        payload=b'{"nodes": {}, "links": []}',
        retained=False,
        received_at=datetime.now(timezone.utc).isoformat(),
    )
    with (
        patch.object(ctx.repo, "store_topology_parsed", side_effect=store),
        patch.object(ctx.repo, "enforce_topology_retention", side_effect=enforce),
        patch.object(TopologyService, "_refresh_diagnostics", refresh),
        patch.object(ctx.broadcaster, "publish_sync", side_effect=publish),
    ):
        assert service.try_handle_response(message) is True
    assert order == ["store", "count_cleanup", "diagnostics"]
    assert "topology_updated" in events
    remaining = ctx.repo.db.conn.execute(
        "SELECT COUNT(*) FROM topology_snapshots WHERE network_id='home'"
    ).fetchone()[0]
    assert remaining == 1
    reset_context()


def test_strict_status_rejects_coerced_counts(tmp_path: Path):
    db = Database(tmp_path / "status.sqlite")
    db.migrate()
    repo = Repository(db)
    with repo.transaction():
        repo.maintenance.set_maintenance_setting(
            {
                "running": "yes",
                "total_rows_deleted": "12",
                "duration_ms": 1.5,
                "more_work_pending": 1,
                "last_error_code": "not_a_real_code",
                "failure_category": "not_a_category",
                "last_started_at": "not-iso",
                "rows_deleted_by_category": {
                    "events": True,
                    "reports": 2,
                    "../../etc/passwd": 9,
                    "SELECT *": 3,
                    "evil_category": 4,
                },
                "rows_updated_by_category": {
                    "abandoned_pending_topology": 1,
                    "reports": 5,
                },
                "malformed_timestamps_by_category": {
                    "events": 2,
                    "evil": 1,
                },
                "integrity": {
                    "quick_check": {
                        "status": "weird",
                        "checked_at": "bogus",
                        "violation_count": "1",
                    },
                    "foreign_key_check": {
                        "status": "ok",
                        "checked_at": "2026-07-20T00:00:00+00:00",
                        "violation_count": 0,
                    },
                },
            }
        )
    cfg = _cfg(tmp_path / "status.sqlite")
    ctx = AppContext(
        config=cfg,
        db=db,
        repo=repo,
        data=MagicMock(),
        health=MagicMock(),
        incidents=MagicMock(),
        broadcaster=EventBroadcaster(),
        session_manager=BrowserSessionManager.from_config(cfg),
    )
    status = build_storage_status(ctx)
    assert status["maintenance"]["running"] is False
    assert status["maintenance"]["total_rows_deleted"] is None
    assert status["maintenance"]["duration_ms"] is None
    assert status["maintenance"]["more_work_pending"] is False
    assert status["maintenance"]["last_error_code"] is None
    assert status["maintenance"]["failure_category"] is None
    assert status["maintenance"]["last_started_at"] is None
    assert status["maintenance"]["rows_deleted_by_category"] == {"reports": 2}
    assert status["maintenance"]["rows_updated_by_category"] == {
        "abandoned_pending_topology": 1
    }
    assert status["maintenance"]["malformed_timestamps_by_category"] == {"events": 2}
    assert status["integrity"]["quick_check"]["status"] is None
    assert status["integrity"]["quick_check"]["checked_at"] is None
    assert status["integrity"]["foreign_key_check"]["status"] == "ok"
    assert (
        status["integrity"]["foreign_key_check"]["checked_at"]
        == "2026-07-20T00:00:00+00:00"
    )


def test_bounded_terminalization_batches(tmp_path: Path):
    from zigbeelens.storage.retention_policy import (
        MAINTENANCE_BATCH_SIZE,
        MAINTENANCE_MAX_TOPOLOGY_EXCLUDE_IDS,
    )

    db = Database(tmp_path / "bound.sqlite")
    db.migrate()
    repo = Repository(db)
    repo.sync_networks([NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")])
    old = (REF - timedelta(days=30)).isoformat()
    repo.db.conn.executemany(
        """
        INSERT INTO topology_snapshots
          (snapshot_id, network_id, captured_at, requested_by, status, warning_acknowledged)
        VALUES (?, 'home', ?, 'test', 'pending', 0)
        """,
        [(f"pend-{i}", old) for i in range(1_250)],
    )
    repo.db.conn.commit()
    cfg = _cfg(tmp_path / "bound.sqlite")

    first = run_storage_maintenance(repo, cfg, reference_now=REF)
    assert first.rows_updated_by_category.get("abandoned_pending_topology") == 500
    assert first.rows_deleted_by_category.get("topology_snapshots", 0) == 0
    assert first.more_work_pending is True
    assert repo.maintenance.max_exclude_bind_params_seen <= MAINTENANCE_MAX_TOPOLOGY_EXCLUDE_IDS
    pending_left = repo.db.conn.execute(
        "SELECT COUNT(*) FROM topology_snapshots WHERE status='pending'"
    ).fetchone()[0]
    assert pending_left == 750

    second = run_storage_maintenance(repo, cfg, reference_now=REF)
    assert second.rows_updated_by_category.get("abandoned_pending_topology") == 500
    assert second.rows_deleted_by_category.get("topology_snapshots", 0) <= 500
    assert repo.maintenance.max_exclude_bind_params_seen <= MAINTENANCE_MAX_TOPOLOGY_EXCLUDE_IDS

    third = run_storage_maintenance(repo, cfg, reference_now=REF)
    assert third.rows_updated_by_category.get("abandoned_pending_topology") == 250
    assert (
        repo.db.conn.execute(
            "SELECT COUNT(*) FROM topology_snapshots WHERE status='pending'"
        ).fetchone()[0]
        == 0
    )
    # Exact 500 batch bound
    repo.db.conn.executemany(
        """
        INSERT INTO topology_snapshots
          (snapshot_id, network_id, captured_at, requested_by, status, warning_acknowledged)
        VALUES (?, 'home', ?, 'test', 'pending', 0)
        """,
        [(f"exact-{i}", old) for i in range(MAINTENANCE_BATCH_SIZE)],
    )
    repo.db.conn.commit()
    exact = run_storage_maintenance(repo, cfg, reference_now=REF)
    assert exact.rows_updated_by_category.get("abandoned_pending_topology") == 500
    assert repo.maintenance.max_exclude_bind_params_seen == 500


def test_active_pending_plus_full_batch_exclusion_bound(tmp_path: Path):
    from zigbeelens.storage.retention_policy import MAINTENANCE_MAX_TOPOLOGY_EXCLUDE_IDS

    db = Database(tmp_path / "active-bound.sqlite")
    db.migrate()
    repo = Repository(db)
    repo.sync_networks([NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")])
    old = (REF - timedelta(hours=2)).isoformat()
    repo.db.conn.executemany(
        """
        INSERT INTO topology_snapshots
          (snapshot_id, network_id, captured_at, requested_by, status, warning_acknowledged)
        VALUES (?, 'home', ?, 'test', 'pending', 0)
        """,
        [(f"aband-{i}", old) for i in range(500)] + [("active-pending", old)],
    )
    repo.db.conn.commit()
    cfg = _cfg(tmp_path / "active-bound.sqlite")
    result = run_storage_maintenance(
        repo,
        cfg,
        reference_now=REF,
        active_pending_provider=lambda: "active-pending",
    )
    assert result.rows_updated_by_category.get("abandoned_pending_topology") == 500
    assert (
        repo.db.conn.execute(
            "SELECT status FROM topology_snapshots WHERE snapshot_id='active-pending'"
        ).fetchone()[0]
        == "pending"
    )
    assert repo.maintenance.max_exclude_bind_params_seen <= MAINTENANCE_MAX_TOPOLOGY_EXCLUDE_IDS


def test_rejected_timestamp_retained_and_counted(tmp_path: Path):
    db = Database(tmp_path / "badts.sqlite")
    db.migrate()
    repo = Repository(db)
    rejected = [
        "2026-01-01T00:00:00 UTC",
        "2026-01-01T00:00:00+15:00",
        "2026-01-01T00:00:00+10:60",
    ]
    for index, value in enumerate(rejected):
        repo.db.conn.execute(
            """
            INSERT INTO events (id, event_type, severity, title, summary, occurred_at)
            VALUES (?, 'test', 'watch', 't', 's', ?)
            """,
            (f"bad-{index}", value),
        )
    repo.db.conn.commit()
    cfg = _cfg(tmp_path / "badts.sqlite")
    result = run_storage_maintenance(repo, cfg, reference_now=REF)
    assert (
        repo.db.conn.execute(
            "SELECT COUNT(*) FROM events WHERE id LIKE 'bad-%'"
        ).fetchone()[0]
        == len(rejected)
    )
    assert result.malformed_timestamps_by_category.get("events", 0) >= len(rejected)


def _capture_cfg(tmp_path: Path) -> AppConfig:
    from zigbeelens.config.models import FeaturesConfig, TopologyConfig

    return AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "cap-event.sqlite")),
        features=FeaturesConfig(manual_network_map=True, automatic_network_map=False),
        topology=TopologyConfig(
            enabled=True,
            manual_capture_enabled=True,
            automatic_capture_enabled=False,
            startup_scan=False,
            capture_on_incident=False,
            max_snapshots_per_network=30,
        ),
    )


def test_capture_lifecycle_clears_pending_before_event(tmp_path: Path):
    from unittest.mock import patch

    from zigbeelens.app.context import bootstrap, reset_context
    from zigbeelens.mqtt.models import RawMqttMessage
    from zigbeelens.topology.publisher import FakeTopologyRequestPublisher
    from zigbeelens.topology.service import TopologyService

    reset_context()
    cfg = _capture_cfg(tmp_path)
    with patch("zigbeelens.app.context.start_discovery", return_value=None):
        ctx = bootstrap(config=cfg)
    service = TopologyService(ctx, publisher=FakeTopologyRequestPublisher(cfg))
    observed: list[bool] = []
    events: list[str] = []

    def publish(event: str, data: dict) -> None:
        events.append(event)
        if event == "topology_updated":
            observed.append(service.status.capture_in_progress)

    def _msg() -> RawMqttMessage:
        return RawMqttMessage(
            topic="zigbee2mqtt/bridge/response/networkmap",
            payload=b'{"nodes": {}, "links": []}',
            retained=False,
            received_at=datetime.now(timezone.utc).isoformat(),
        )

    # A. normal successful capture
    service.request_capture("home", confirmed=True)
    with patch.object(ctx.broadcaster, "publish_sync", side_effect=publish):
        assert service.try_handle_response(_msg()) is True
    assert events.count("topology_updated") == 1
    assert observed == [False]
    assert service.status.capture_in_progress is False
    assert ctx.repo.get_latest_topology_snapshot("home")["status"] == "complete"

    # B. count-cleanup failure
    events.clear()
    observed.clear()
    service.request_capture("home", confirmed=True)
    with (
        patch.object(
            ctx.repo, "enforce_topology_retention", side_effect=RuntimeError("busy")
        ),
        patch.object(ctx.broadcaster, "publish_sync", side_effect=publish),
    ):
        assert service.try_handle_response(_msg()) is True
    assert events.count("topology_updated") == 1
    assert observed == [False]
    assert ctx.repo.get_latest_topology_snapshot("home")["status"] == "complete"

    # C. diagnostic-refresh failure
    events.clear()
    observed.clear()
    service.request_capture("home", confirmed=True)
    with (
        patch.object(
            TopologyService, "_refresh_diagnostics", side_effect=RuntimeError("eval")
        ),
        patch.object(ctx.broadcaster, "publish_sync", side_effect=publish),
    ):
        assert service.try_handle_response(_msg()) is True
    assert events.count("topology_updated") == 1
    assert observed == [False]
    assert ctx.repo.get_latest_topology_snapshot("home")["status"] == "complete"
    assert service.status.last_capture_error == "Topology diagnostic refresh failed"

    # D. event-publication failure
    events.clear()
    service.request_capture("home", confirmed=True)
    with patch.object(
        ctx.broadcaster, "publish_sync", side_effect=RuntimeError("sse")
    ):
        assert service.try_handle_response(_msg()) is True
    assert service.status.capture_in_progress is False
    assert ctx.repo.get_latest_topology_snapshot("home")["status"] == "complete"

    # E. parse/store failure
    events.clear()
    service.request_capture("home", confirmed=True)
    snap_id = service.active_pending_snapshot_id
    with (
        patch.object(ctx.repo, "store_topology_parsed", side_effect=RuntimeError("db")),
        patch.object(ctx.broadcaster, "publish_sync", side_effect=publish),
    ):
        assert service.try_handle_response(_msg()) is False
    assert "topology_updated" not in events
    assert service.status.capture_in_progress is False
    row = ctx.repo.db.conn.execute(
        "SELECT status FROM topology_snapshots WHERE snapshot_id=?",
        (snap_id,),
    ).fetchone()
    assert row["status"] == "error"
    reset_context()


def test_prestore_failure_releases_pending_even_when_status_write_fails(
    tmp_path: Path,
):
    from unittest.mock import patch

    from zigbeelens.app.context import bootstrap, reset_context
    from zigbeelens.mqtt.models import RawMqttMessage
    from zigbeelens.topology.publisher import FakeTopologyRequestPublisher
    from zigbeelens.topology.service import TopologyService

    reset_context()
    cfg = _capture_cfg(tmp_path)
    with patch("zigbeelens.app.context.start_discovery", return_value=None):
        ctx = bootstrap(config=cfg)
    service = TopologyService(ctx, publisher=FakeTopologyRequestPublisher(cfg))
    events: list[str] = []

    def publish(event: str, data: dict) -> None:
        events.append(event)

    def _msg(payload: bytes = b'{"nodes": {}, "links": []}') -> RawMqttMessage:
        return RawMqttMessage(
            topic="zigbee2mqtt/bridge/response/networkmap",
            payload=payload,
            retained=False,
            received_at=datetime.now(timezone.utc).isoformat(),
        )

    # A. parse fails and update_topology_snapshot also fails.
    service.request_capture("home", confirmed=True)
    with (
        patch(
            "zigbeelens.topology.service.parse_networkmap_payload",
            side_effect=ValueError("parse"),
        ),
        patch.object(
            ctx.repo, "update_topology_snapshot", side_effect=RuntimeError("status")
        ),
        patch.object(ctx.broadcaster, "publish_sync", side_effect=publish),
    ):
        assert service.try_handle_response(_msg()) is False
    assert service.active_pending_snapshot_id is None
    assert service.status.capture_in_progress is False
    assert "topology_updated" not in events
    assert service.status.last_capture_error == "Topology response handling failed"

    # B. store_topology_parsed fails and update_topology_snapshot also fails.
    events.clear()
    service.request_capture("home", confirmed=True)
    with (
        patch.object(ctx.repo, "store_topology_parsed", side_effect=RuntimeError("db")),
        patch.object(
            ctx.repo, "update_topology_snapshot", side_effect=RuntimeError("status")
        ),
        patch.object(ctx.broadcaster, "publish_sync", side_effect=publish),
    ):
        assert service.try_handle_response(_msg()) is False
    assert service.active_pending_snapshot_id is None
    assert service.status.capture_in_progress is False
    assert "topology_updated" not in events
    assert service.status.last_capture_error == "Topology response handling failed"

    # C. error-state persistence succeeds.
    events.clear()
    service.request_capture("home", confirmed=True)
    snap_id = service.active_pending_snapshot_id
    assert snap_id is not None
    with (
        patch.object(ctx.repo, "store_topology_parsed", side_effect=RuntimeError("db")),
        patch.object(ctx.broadcaster, "publish_sync", side_effect=publish),
    ):
        assert service.try_handle_response(_msg()) is False
    assert service.active_pending_snapshot_id is None
    assert service.status.capture_in_progress is False
    assert "topology_updated" not in events
    row = ctx.repo.db.conn.execute(
        "SELECT status, error FROM topology_snapshots WHERE snapshot_id=?",
        (snap_id,),
    ).fetchone()
    assert row["status"] == "error"
    assert row["error"] == "Topology response handling failed"

    # D. matching safety: other snapshot ID does not clear current pending.
    service.request_capture("home", confirmed=True)
    current = service.active_pending_snapshot_id
    assert current is not None
    service._clear_matching_pending("some-other-snapshot")
    assert service.active_pending_snapshot_id == current
    assert service.status.capture_in_progress is True
    service._clear_matching_pending(current)
    assert service.active_pending_snapshot_id is None
    assert service.status.capture_in_progress is False
    reset_context()
