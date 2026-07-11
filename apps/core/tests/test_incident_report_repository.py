"""IncidentRepository and ReportRepository access-layer tests."""

from __future__ import annotations

from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.storage.repository import Repository


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "incident-report-access.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "incident-report-access.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    return repo


def test_incident_repository_delegates_insert_and_list(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    now = "2026-07-06T12:00:00+00:00"
    repo.incidents.insert_incident(
        incident_id="inc-1",
        dedup_key="dedup-1",
        incident_type="device_offline",
        lifecycle_state="open",
        severity="warning",
        scope="device",
        confidence="medium",
        title="Sensor offline",
        summary="Sensor went offline",
        explanation="Observed offline transition",
        evidence=["availability change"],
        counter_evidence=[],
        limitations=[],
        opened_at=now,
        updated_at=now,
    )

    via_repo = repo.list_incidents(status_filter=("open",))
    via_access = repo.incidents.list_incidents(status_filter=("open",))

    assert via_access == via_repo
    assert via_access[0]["id"] == "inc-1"


def test_incident_repository_delegates_device_lookup(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.upsert_device(
        network_id="home",
        ieee_address="0x01",
        friendly_name="Sensor",
        device_type="EndDevice",
        power_source="Battery",
    )
    now = "2026-07-06T12:00:00+00:00"
    repo.incidents.insert_incident(
        incident_id="inc-1",
        dedup_key="dedup-1",
        incident_type="device_offline",
        lifecycle_state="open",
        severity="warning",
        scope="device",
        confidence="medium",
        title="Sensor offline",
        summary="Sensor went offline",
        explanation="Observed offline transition",
        evidence=[],
        counter_evidence=[],
        limitations=[],
        opened_at=now,
        updated_at=now,
    )
    from zigbeelens.diagnostics.incidents.models import AffectedDevice

    repo.incidents.replace_incident_devices(
        "inc-1",
        [AffectedDevice(network_id="home", ieee_address="0x01", role="subject")],
    )

    assert repo.incidents.list_incidents_for_device("home", "0x01") == repo.list_incidents_for_device(
        "home", "0x01"
    )
    assert repo.incidents.get_incident("inc-1") == repo.get_incident("inc-1")


def test_incident_repository_cached_on_repository_instance(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert repo.incidents is repo.incidents


def test_report_repository_delegates_save_list_and_delete(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    saved = repo.reports.save_report(
        report_id="rep-1",
        format="json",
        summary="Test report",
        body={"ok": True},
        markdown="# Test",
        redaction={"fields": []},
    )

    via_repo = repo.list_reports()
    via_access = repo.reports.list_reports()

    assert via_access == via_repo
    assert saved.id == "rep-1"
    assert repo.reports.get_report("rep-1") == repo.get_report("rep-1")
    assert repo.reports.delete_report("rep-1") is True
    assert repo.reports.list_reports() == []


def test_report_repository_cached_on_repository_instance(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert repo.reports is repo.reports
