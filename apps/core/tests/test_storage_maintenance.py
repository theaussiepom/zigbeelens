"""Track 6 maintenance executor and scheduler tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.diagnostics.clock import Clock
from zigbeelens.storage.maintenance import run_storage_maintenance
from zigbeelens.storage.maintenance_scheduler import StorageMaintenanceScheduler
from zigbeelens.storage.repository import Repository

REF = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self._value = value

    def now(self) -> datetime:
        return self._value


def _cfg(db_path: Path, **storage_kwargs) -> AppConfig:
    storage = StorageConfig(path=str(db_path), **storage_kwargs)
    return AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=storage,
    )


def test_executor_deletes_telemetry_keeps_reports_and_active(tmp_path: Path):
    db = Database(tmp_path / "m.sqlite")
    db.migrate()
    repo = Repository(db)
    old = (REF - timedelta(days=30)).isoformat()
    repo.db.conn.execute(
        """
        INSERT INTO events (id, event_type, severity, title, summary, occurred_at)
        VALUES ('evt-old', 'test', 'watch', 't', 's', ?)
        """,
        (old,),
    )
    repo.db.conn.execute(
        """
        INSERT INTO reports (id, format, redaction_json, summary, generated_at)
        VALUES ('rep-old', 'json', '{}', 'Old', ?)
        """,
        (old,),
    )
    repo.insert_incident(
        incident_id="inc-open",
        dedup_key="open:home",
        incident_type="single_device_unavailable",
        lifecycle_state="open",
        severity="incident",
        scope="device",
        confidence="high",
        title="Open",
        summary="Open",
        explanation="t",
        evidence=[],
        counter_evidence=[],
        limitations=[],
        opened_at=old,
        updated_at=old,
    )
    repo.insert_incident(
        incident_id="inc-old",
        dedup_key="old:home",
        incident_type="single_device_unavailable",
        lifecycle_state="resolved",
        severity="incident",
        scope="device",
        confidence="high",
        title="Old",
        summary="Old",
        explanation="t",
        evidence=[],
        counter_evidence=[],
        limitations=[],
        opened_at=old,
        updated_at=old,
    )
    repo.update_incident(incident_id="inc-old", resolved_at=old, updated_at=old)
    repo.db.conn.commit()

    cfg = _cfg(tmp_path / "m.sqlite")
    dry = run_storage_maintenance(repo, cfg, reference_now=REF, dry_run=True)
    assert dry.eligible_deletes_by_category["events"] == 1
    assert dry.eligible_deletes_by_category.get("reports", 0) == 0
    assert dry.eligible_deletes_by_category.get("incidents_resolved", 0) == 0
    assert dry.total_rows_deleted == 0
    assert repo.db.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1

    result = run_storage_maintenance(repo, cfg, reference_now=REF)
    assert result.success
    assert result.rows_deleted_by_category["events"] == 1
    assert result.rows_deleted_by_category.get("reports", 0) == 0
    assert {row["id"] for row in repo.list_incidents()} == {"inc-open", "inc-old"}
    status = repo.maintenance.get_maintenance_setting()
    assert status is not None
    assert status["running"] is False
    assert status["total_rows_deleted"] >= 1


def test_executor_resolved_and_report_policies(tmp_path: Path):
    db = Database(tmp_path / "pol.sqlite")
    db.migrate()
    repo = Repository(db)
    old = (REF - timedelta(days=120)).isoformat()
    repo.insert_incident(
        incident_id="inc-old",
        dedup_key="old:home",
        incident_type="single_device_unavailable",
        lifecycle_state="resolved",
        severity="incident",
        scope="device",
        confidence="high",
        title="Old",
        summary="Old",
        explanation="t",
        evidence=[],
        counter_evidence=[],
        limitations=[],
        opened_at=old,
        updated_at=old,
    )
    repo.update_incident(incident_id="inc-old", resolved_at=old, updated_at=old)
    repo.db.conn.execute(
        """
        INSERT INTO reports (id, format, redaction_json, summary, generated_at)
        VALUES ('rep-old', 'json', '{}', 'Old', ?)
        """,
        (old,),
    )
    repo.db.conn.execute(
        """
        INSERT INTO events (id, event_type, severity, title, summary, occurred_at, incident_id)
        VALUES ('evt', 'test', 'watch', 't', 's', ?, 'inc-old')
        """,
        (REF.isoformat(),),
    )
    repo.db.conn.commit()

    cfg = _cfg(
        tmp_path / "pol.sqlite",
        resolved_incident_retention_days=90,
        report_retention_days=30,
    )
    result = run_storage_maintenance(repo, cfg, reference_now=REF)
    assert result.success
    assert result.rows_deleted_by_category["incidents_resolved"] == 1
    assert result.rows_deleted_by_category["reports"] == 1
    assert repo.db.conn.execute(
        "SELECT incident_id FROM events WHERE id='evt'"
    ).fetchone()[0] is None


def test_scheduler_single_flight_and_stop(tmp_path: Path):
    db = Database(tmp_path / "sched.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = _cfg(tmp_path / "sched.sqlite", maintenance_interval_hours=1)
    clock: Clock = FixedClock(REF)
    seen: list[int] = []

    def on_result(result) -> None:
        seen.append(result.total_rows_deleted)

    scheduler = StorageMaintenanceScheduler(
        repo, cfg, clock=clock, on_result=on_result, interval_hours=1
    )
    first = scheduler.run_once(now=REF)
    assert first is not None and first.success
    scheduler.start()
    scheduler.stop(wait=True, timeout=2.0)
    assert scheduler.running is False
    assert seen  # at least one completion callback from run_once
