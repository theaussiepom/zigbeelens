"""Track 3F: scope-first report composition and request-local reuse."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from zigbeelens.config.models import (
    AppConfig,
    ModeConfig,
    NetworkConfig,
    ReportingConfig,
    StorageConfig,
)
from zigbeelens.db.connection import Database
from zigbeelens.decisions.device_story import device_stories_for_devices
from zigbeelens.diagnostics.incidents.models import AffectedDevice
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.schemas import (
    RedactionOptions,
    ReportRequest,
    ReportScope,
)
from zigbeelens.services.data_service import DataService
from zigbeelens.services.reports import generate_report
from zigbeelens.storage.repository import Repository
from performance.query_instrumentation import install_counter

from report_v3_helpers import (
    report_device_details,
    report_devices,
    report_networks,
    report_timeline,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
HOME_SENTINEL = "HOME_ONLY_SENTINEL_3F"
OFFICE_SENTINEL = "OFFICE_LEAK_SENTINEL_3F"
EVENT_HOME = "HOME_EVENT_SENTINEL_3F"
EVENT_OFFICE = "OFFICE_EVENT_SENTINEL_3F"


def _service(tmp_path: Path) -> tuple[DataService, AppConfig, Repository]:
    db = Database(tmp_path / "scope3f.sqlite")
    db.migrate()
    repo = Repository(db)
    config = AppConfig(
        mode=ModeConfig(mock=False),
        networks=[
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
            NetworkConfig(id="office", name="Office", base_topic="z2m-office"),
        ],
        storage=StorageConfig(path=str(tmp_path / "scope3f.sqlite")),
        reporting=ReportingConfig(max_recent_events=50),
    )
    repo.sync_networks(config.networks)
    health = HealthDiagnosticService(config, repo)
    return DataService(config, repo, health), config, repo


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


def _add_incident(
    repo: Repository,
    *,
    incident_id: str,
    incident_type: str,
    dedup_key: str,
    network_ids: list[str],
    devices: list[tuple[str, str]] | None = None,
    title: str,
) -> None:
    repo.incidents.insert_incident(
        incident_id=incident_id,
        dedup_key=dedup_key,
        incident_type=incident_type,
        lifecycle_state="open",
        severity="incident",
        scope="network" if not devices else "device",
        confidence="high",
        title=title,
        summary=title,
        explanation=title,
        evidence=[],
        counter_evidence=[],
        limitations=[],
        opened_at=NOW.isoformat(),
        updated_at=NOW.isoformat(),
    )
    if devices:
        repo.replace_incident_devices(
            incident_id,
            [AffectedDevice(nid, ieee) for nid, ieee in devices],
        )
    repo.replace_incident_networks(incident_id, network_ids)


def _seed_estate(repo: Repository) -> None:
    _add_device(repo, "home", "0xhome1", f"HomeTarget-{HOME_SENTINEL}")
    for i in range(8):
        _add_device(repo, "office", f"0xoff{i}", f"OfficeDev-{OFFICE_SENTINEL}-{i}")
    _add_device(repo, "office", "0xhome1", f"SameIeeeOffice-{OFFICE_SENTINEL}")

    _add_incident(
        repo,
        incident_id="inc-home-device",
        incident_type="single_device_unavailable",
        dedup_key="single_device_unavailable:home:0xhome1",
        network_ids=["home"],
        devices=[("home", "0xhome1")],
        title=f"HomeIncident-{HOME_SENTINEL}",
    )
    _add_incident(
        repo,
        incident_id="inc-office",
        incident_type="single_device_unavailable",
        dedup_key="single_device_unavailable:office:0xoff0",
        network_ids=["office"],
        devices=[("office", "0xoff0")],
        title=f"OfficeIncident-{OFFICE_SENTINEL}",
    )
    _add_incident(
        repo,
        incident_id="inc-bridge-home",
        incident_type="bridge_offline",
        dedup_key="bridge_offline:home",
        network_ids=["home"],
        title=f"BridgeHome-{HOME_SENTINEL}",
    )
    _add_incident(
        repo,
        incident_id="inc-multi",
        incident_type="multi_network_instability",
        dedup_key="multi_network_instability:home,office",
        network_ids=["home", "office"],
        title=f"MultiNet-{HOME_SENTINEL}",
    )
    _add_incident(
        repo,
        incident_id="inc-missing-device",
        incident_type="single_device_unavailable",
        dedup_key="single_device_unavailable:home:0xmissing",
        network_ids=["home"],
        devices=[("home", "0xmissing")],
        title=f"MissingDevice-{HOME_SENTINEL}",
    )
    repo.insert_event(
        event_id="ev-home",
        network_id="home",
        ieee_address="0xhome1",
        event_type="device_availability_changed",
        severity="watch",
        title=EVENT_HOME,
        summary=EVENT_HOME,
        incident_id="inc-home-device",
        occurred_at=NOW.isoformat(),
    )
    repo.insert_event(
        event_id="ev-office",
        network_id="office",
        ieee_address="0xoff0",
        event_type="device_availability_changed",
        severity="watch",
        title=EVENT_OFFICE,
        summary=EVENT_OFFICE,
        incident_id="inc-office",
        occurred_at=NOW.isoformat(),
    )


def _blob(detail) -> str:
    return json.dumps(detail.model_dump(mode="json"), sort_keys=True) + "\n" + detail.markdown_summary


def test_network_scope_isolates_office_sentinels(tmp_path: Path):
    data, config, repo = _service(tmp_path)
    _seed_estate(repo)
    for method in (
        "dashboard",
        "networks",
        "routers",
        "devices",
        "timeline",
    ):
        monkey = MagicMock(side_effect=AssertionError(f"{method} must not be called"))
        setattr(data, method, monkey)

    detail = generate_report(
        data=data,
        config=config,
        reporting=config.reporting,
        collector={},
        request=ReportRequest(scope=ReportScope.network, network_id="home"),
        repo=repo,
        now=NOW,
    )
    blob = _blob(detail)
    assert HOME_SENTINEL in blob
    assert OFFICE_SENTINEL not in blob
    assert EVENT_OFFICE not in blob
    assert {n.id for n in report_networks(detail)} == {"home"}
    assert all(d.network_id == "home" for d in report_devices(detail))
    assert all("office" not in i.network_ids or "home" in i.network_ids for i in detail.incidents)
    assert {i.id for i in detail.incidents} >= {
        "inc-home-device",
        "inc-bridge-home",
        "inc-multi",
        "inc-missing-device",
    }
    assert "inc-office" not in {i.id for i in detail.incidents}
    assert detail.config_summary["networks"] == [
        {"id": "home", "name": "Home", "base_topic": "zigbee2mqtt"}
    ]
    assert detail.generated_at.startswith("2026-06-01T12:00:00")


def test_device_scope_composite_isolation(tmp_path: Path):
    data, config, repo = _service(tmp_path)
    _seed_estate(repo)
    list_spy = MagicMock(wraps=repo.list_devices)
    repo.list_devices = list_spy  # type: ignore[method-assign]

    detail = generate_report(
        data=data,
        config=config,
        reporting=config.reporting,
        collector={},
        request=ReportRequest(
            scope=ReportScope.device,
            network_id="home",
            device="0xhome1",
            redaction=RedactionOptions(
                hash_ieee_addresses=False,
                preserve_friendly_names=True,
                redact_network_names=False,
            ),
        ),
        repo=repo,
        now=NOW,
    )
    assert [d.ieee_address for d in report_devices(detail)] == ["0xhome1"]
    assert all(d.network_id == "home" for d in report_devices(detail))
    assert all(d.network_id == "home" for d in report_device_details(detail))
    assert all(
        any(ref.network_id == "home" and ref.ieee_address == "0xhome1" for ref in i.affected_devices)
        for i in detail.incidents
    )
    assert OFFICE_SENTINEL not in _blob(detail)
    # Must not scan complete inventory for device scope.
    assert all(call.args != () and call.args != (None,) for call in list_spy.call_args_list) or list_spy.call_count == 0


def test_incident_scope_missing_device_and_one_story_batch(monkeypatch, tmp_path: Path):
    data, config, repo = _service(tmp_path)
    _seed_estate(repo)
    story_spy = MagicMock(wraps=device_stories_for_devices)
    monkeypatch.setattr(
        "zigbeelens.services.report_composition.device_stories_for_devices",
        story_spy,
    )
    detail = generate_report(
        data=data,
        config=config,
        reporting=config.reporting,
        collector={},
        request=ReportRequest(
            scope=ReportScope.incident,
            incident_id="inc-missing-device",
            redaction=RedactionOptions(
                hash_ieee_addresses=False,
                preserve_friendly_names=True,
                redact_network_names=False,
            ),
        ),
        repo=repo,
        now=NOW,
    )
    assert story_spy.call_count == 1
    assert len(detail.incidents) == 1
    assert detail.incidents[0].id == "inc-missing-device"
    assert any(ref.ieee_address == "0xmissing" for ref in detail.incidents[0].affected_devices)
    # Missing device has no Device Story / current decision.
    assert detail.device_stories == []
    missing_ref = next(
        ref for ref in detail.incidents[0].affected_devices if ref.ieee_address == "0xmissing"
    )
    assert missing_ref.decision is None or missing_ref.decision.status in {
        "unknown",
        "data_unavailable",
        None,
    }


def test_include_timeline_false_zero_event_reads(tmp_path: Path):
    data, config, repo = _service(tmp_path)
    _seed_estate(repo)
    counter = install_counter(repo)
    counter.reset()
    detail = generate_report(
        data=data,
        config=config,
        reporting=config.reporting,
        collector={},
        request=ReportRequest(
            scope=ReportScope.network,
            network_id="home",
            redaction=RedactionOptions(include_timeline=False),
        ),
        repo=repo,
        now=NOW,
    )
    event_reads = [
        sql
        for sql in counter.stats.statements
        if "FROM events" in sql or "from events" in sql.lower()
    ]
    assert event_reads == []
    assert report_timeline(detail) == []
    assert all(not i.timeline for i in detail.incidents)
    assert EVENT_HOME not in _blob(detail)
    assert EVENT_OFFICE not in _blob(detail)


def test_full_report_keeps_complete_history(tmp_path: Path):
    data, config, repo = _service(tmp_path)
    _seed_estate(repo)
    detail = generate_report(
        data=data,
        config=config,
        reporting=config.reporting,
        collector={},
        request=ReportRequest(scope=ReportScope.full),
        repo=repo,
        now=NOW,
    )
    ids = {i.id for i in detail.incidents}
    assert ids == {
        "inc-home-device",
        "inc-office",
        "inc-bridge-home",
        "inc-multi",
        "inc-missing-device",
    }
    assert {n.id for n in report_networks(detail)} == {"home", "office"}


def test_preview_is_read_only(tmp_path: Path):
    data, config, repo = _service(tmp_path)
    _seed_estate(repo)
    before = repo.db.conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    counter = install_counter(repo)
    counter.reset()
    generate_report(
        data=data,
        config=config,
        reporting=config.reporting,
        collector={},
        request=ReportRequest(scope=ReportScope.network, network_id="home"),
        repo=repo,
        now=NOW,
    )
    after = repo.db.conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    assert before == after == 0
    assert counter.stats.commit_count == 0
