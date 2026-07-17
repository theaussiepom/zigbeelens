"""Track 3E incident collection pagination and repository query contract."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.diagnostics.incidents.models import AffectedDevice
from zigbeelens.storage.incident_collection import (
    IncidentCollectionCursor,
    IncidentCollectionCursorError,
    IncidentCollectionQueryError,
    build_incident_collection_query,
    canonicalize_utc_iso,
    decode_incident_collection_cursor,
    encode_incident_collection_cursor,
    normalize_updated_after,
)
from zigbeelens.storage.repository import Repository

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)


def _explain_page_plan(repo: Repository, query) -> str:
    """EXPLAIN the production page SELECT (not a narrower SELECT id surrogate)."""
    sql, params = repo._incident_collection_page_sql(
        query,
        include_cursor=bool(query.cursor),
    )
    plan_rows = repo.db.conn.execute(f"EXPLAIN QUERY PLAN {sql}", params).fetchall()
    return " | ".join(str(row[-1]) for row in plan_rows)


def _seed_history_scale(repo: Repository, *, n: int = 300) -> None:
    _seed_device(repo, "home", "0xA1")
    for index in range(n):
        state = "open" if index < 5 else ("watching" if index < 10 else "resolved")
        _seed_incident(
            repo,
            f"hist-{index:04d}",
            lifecycle=state,
            updated_at=NOW - timedelta(minutes=index),
            refs=[("home", "0xA1")] if index % 3 == 0 else [],
        )


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "collection.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
            NetworkConfig(id="office", name="Office", base_topic="z2m-office"),
        ],
        storage=StorageConfig(path=str(tmp_path / "collection.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    return repo


def _seed_device(repo: Repository, network_id: str, ieee: str) -> None:
    repo.upsert_device(
        network_id=network_id,
        ieee_address=ieee,
        friendly_name=f"Device {ieee}",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )


def _seed_incident(
    repo: Repository,
    incident_id: str,
    *,
    lifecycle: str,
    updated_at: datetime,
    refs: list[tuple[str, str]] | None = None,
) -> None:
    ts = updated_at.isoformat()
    repo.insert_incident(
        incident_id=incident_id,
        dedup_key=f"dedup:{incident_id}",
        incident_type="device_offline",
        lifecycle_state=lifecycle,
        severity="incident",
        scope="device",
        confidence="medium",
        title=f"Incident {incident_id}",
        summary=f"Summary {incident_id}",
        explanation="Explanation",
        evidence=["evidence"],
        counter_evidence=[],
        limitations=[],
        opened_at=ts,
        updated_at=ts,
    )
    if lifecycle == "resolved":
        repo.update_incident(
            incident_id=incident_id,
            lifecycle_state="resolved",
            resolved_at=ts,
            updated_at=ts,
        )
    if refs:
        repo.replace_incident_devices(
            incident_id,
            [AffectedDevice(network_id, ieee, role="primary") for network_id, ieee in refs],
        )


def _seed_standard_set(repo: Repository) -> None:
    _seed_device(repo, "home", "0xA1")
    _seed_device(repo, "home", "0xA2")
    _seed_device(repo, "office", "0xB1")
    # Equal updated_at within open — id DESC tie-break.
    _seed_incident(repo, "open-b", lifecycle="open", updated_at=NOW, refs=[("home", "0xA1")])
    _seed_incident(repo, "open-a", lifecycle="open", updated_at=NOW, refs=[("home", "0xA2")])
    _seed_incident(
        repo,
        "watch-1",
        lifecycle="watching",
        updated_at=NOW - timedelta(hours=1),
        refs=[("office", "0xB1")],
    )
    _seed_incident(
        repo,
        "res-new",
        lifecycle="resolved",
        updated_at=NOW - timedelta(hours=2),
        refs=[("home", "0xA1")],
    )
    _seed_incident(
        repo,
        "res-old",
        lifecycle="resolved",
        updated_at=NOW - timedelta(days=1),
        refs=[],
    )
    _seed_incident(
        repo,
        "multi-net",
        lifecycle="resolved",
        updated_at=NOW - timedelta(hours=3),
        refs=[("home", "0xA1"), ("office", "0xB1")],
    )


def test_default_ordering_lifecycle_then_updated_then_id(tmp_path: Path):
    repo = _repo(tmp_path)
    _seed_standard_set(repo)
    query = build_incident_collection_query(limit=20)
    page = repo.list_incidents_page(query)
    assert [row["id"] for row in page.rows] == [
        "open-b",
        "open-a",
        "watch-1",
        "res-new",
        "multi-net",
        "res-old",
    ]
    assert page.total == 6
    assert page.next_cursor is None


def test_status_filter_and_updated_after_exclusive(tmp_path: Path):
    repo = _repo(tmp_path)
    _seed_standard_set(repo)
    boundary = (NOW - timedelta(hours=2)).isoformat()
    query = build_incident_collection_query(
        status=["resolved"],
        updated_after=boundary,
        limit=20,
    )
    page = repo.list_incidents_page(query)
    # exclusive: updated_at > boundary excludes res-new (== boundary)
    assert [row["id"] for row in page.rows] == []
    assert page.total == 0

    query2 = build_incident_collection_query(
        status=["resolved"],
        updated_after=(NOW - timedelta(hours=2, seconds=1)).isoformat(),
        limit=20,
    )
    page2 = repo.list_incidents_page(query2)
    assert [row["id"] for row in page2.rows] == ["res-new"]


def test_network_and_device_filters(tmp_path: Path):
    repo = _repo(tmp_path)
    _seed_standard_set(repo)
    by_network = repo.list_incidents_page(
        build_incident_collection_query(network_id="office", limit=20)
    )
    assert {row["id"] for row in by_network.rows} == {"watch-1", "multi-net"}

    by_device = repo.list_incidents_page(
        build_incident_collection_query(
            network_id="home",
            device_ieee="0xA2",
            limit=20,
        )
    )
    assert [row["id"] for row in by_device.rows] == ["open-a"]


def test_keyset_pages_no_duplicates_or_omissions(tmp_path: Path):
    repo = _repo(tmp_path)
    _seed_standard_set(repo)
    first = repo.list_incidents_page(build_incident_collection_query(limit=2))
    assert [row["id"] for row in first.rows] == ["open-b", "open-a"]
    assert first.total == 6
    assert first.next_cursor is not None

    second = repo.list_incidents_page(
        build_incident_collection_query(limit=2, cursor=first.next_cursor)
    )
    assert [row["id"] for row in second.rows] == ["watch-1", "res-new"]
    assert second.next_cursor is not None

    third = repo.list_incidents_page(
        build_incident_collection_query(limit=2, cursor=second.next_cursor)
    )
    assert [row["id"] for row in third.rows] == ["multi-net", "res-old"]
    assert third.next_cursor is None

    seen = [row["id"] for row in (*first.rows, *second.rows, *third.rows)]
    assert seen == ["open-b", "open-a", "watch-1", "res-new", "multi-net", "res-old"]
    assert len(seen) == len(set(seen))


def test_exact_final_page_has_no_phantom_next_cursor(tmp_path: Path):
    repo = _repo(tmp_path)
    _seed_standard_set(repo)
    page = repo.list_incidents_page(build_incident_collection_query(limit=6))
    assert len(page.rows) == 6
    assert page.next_cursor is None


def test_empty_page(tmp_path: Path):
    repo = _repo(tmp_path)
    page = repo.list_incidents_page(
        build_incident_collection_query(status=["open"], limit=10)
    )
    assert page.rows == ()
    assert page.total == 0
    assert page.next_cursor is None


def test_cursor_rejects_filter_mismatch_and_tampering(tmp_path: Path):
    repo = _repo(tmp_path)
    _seed_standard_set(repo)
    first = repo.list_incidents_page(build_incident_collection_query(limit=1))
    assert first.next_cursor is not None

    with pytest.raises(IncidentCollectionCursorError):
        repo.list_incidents_page(
            build_incident_collection_query(
                status=["resolved"],
                limit=1,
                cursor=first.next_cursor,
            )
        )

    with pytest.raises(IncidentCollectionCursorError):
        decode_incident_collection_cursor(
            "not-a-cursor",
            expected_filter_signature="abc",
        )

    good = build_incident_collection_query(limit=1)
    decoded = decode_incident_collection_cursor(
        first.next_cursor,
        expected_filter_signature=good.filter_signature,
    )
    bad = encode_incident_collection_cursor(
        IncidentCollectionCursor(
            version=decoded.version,
            lifecycle_rank=9,
            updated_at=decoded.updated_at,
            incident_id=decoded.incident_id,
            filter_signature=decoded.filter_signature,
        )
    )
    with pytest.raises(IncidentCollectionCursorError):
        decode_incident_collection_cursor(
            bad,
            expected_filter_signature=good.filter_signature,
        )


def test_query_validation_rules():
    with pytest.raises(IncidentCollectionQueryError):
        build_incident_collection_query(status=["nope"])
    with pytest.raises(IncidentCollectionQueryError):
        build_incident_collection_query(limit=0)
    with pytest.raises(IncidentCollectionQueryError):
        build_incident_collection_query(limit=101)
    with pytest.raises(IncidentCollectionQueryError):
        build_incident_collection_query(device_ieee="0xA1")
    with pytest.raises(IncidentCollectionQueryError):
        build_incident_collection_query(updated_after="yesterday")


def test_explain_query_plan_uses_collection_order_index(tmp_path: Path):
    repo = _repo(tmp_path)
    _seed_history_scale(repo, n=300)

    # Seed has 5 open / 5 watching / many resolved; use small limits where needed
    # so single-lifecycle cursor continuations are exercised.
    open_q = build_incident_collection_query(status=["open"], limit=2)
    watching_q = build_incident_collection_query(status=["watching"], limit=2)
    resolved_q = build_incident_collection_query(status=["resolved"], limit=50)
    default_q = build_incident_collection_query(limit=50)
    active_q = build_incident_collection_query(status=["open", "watching"], limit=50)
    updated_q = build_incident_collection_query(
        updated_after=(NOW - timedelta(hours=2)).isoformat(),
        limit=50,
    )
    network_q = build_incident_collection_query(network_id="home", limit=50)
    device_q = build_incident_collection_query(
        network_id="home",
        device_ieee="0xA1",
        limit=50,
    )

    open_first = repo.list_incidents_page(open_q)
    watching_first = repo.list_incidents_page(watching_q)
    resolved_first = repo.list_incidents_page(resolved_q)
    assert open_first.next_cursor is not None
    assert watching_first.next_cursor is not None
    assert resolved_first.next_cursor is not None

    plans = {
        "open": _explain_page_plan(repo, open_q),
        "watching": _explain_page_plan(repo, watching_q),
        "resolved": _explain_page_plan(repo, resolved_q),
        "open_cursor": _explain_page_plan(
            repo,
            build_incident_collection_query(
                status=["open"], limit=2, cursor=open_first.next_cursor
            ),
        ),
        "watching_cursor": _explain_page_plan(
            repo,
            build_incident_collection_query(
                status=["watching"], limit=2, cursor=watching_first.next_cursor
            ),
        ),
        "resolved_cursor": _explain_page_plan(
            repo,
            build_incident_collection_query(
                status=["resolved"], limit=50, cursor=resolved_first.next_cursor
            ),
        ),
        "default": _explain_page_plan(repo, default_q),
        "active": _explain_page_plan(repo, active_q),
        "updated_after": _explain_page_plan(repo, updated_q),
        "network": _explain_page_plan(repo, network_q),
        "device": _explain_page_plan(repo, device_q),
    }

    for name, plan_text in plans.items():
        assert "idx_incidents_collection_order" in plan_text, (name, plan_text)
        assert "USE TEMP B-TREE FOR ORDER BY" not in plan_text, (name, plan_text)

    # Single-lifecycle cursor continuations progress without overlap.
    for status, first, limit in (
        ("open", open_first, 2),
        ("watching", watching_first, 2),
        ("resolved", resolved_first, 50),
    ):
        page2 = repo.list_incidents_page(
            build_incident_collection_query(
                status=[status], limit=limit, cursor=first.next_cursor
            )
        )
        assert page2.rows[0]["id"] != first.rows[0]["id"]
        assert {row["id"] for row in first.rows}.isdisjoint(
            {row["id"] for row in page2.rows}
        )


def test_updated_after_preserves_microsecond_boundaries(tmp_path: Path):
    repo = _repo(tmp_path)
    _seed_incident(
        repo,
        "at-200",
        lifecycle="open",
        updated_at=datetime(2026, 7, 16, 12, 0, 0, 200000, tzinfo=timezone.utc),
    )
    _seed_incident(
        repo,
        "at-500",
        lifecycle="open",
        updated_at=datetime(2026, 7, 16, 12, 0, 0, 500000, tzinfo=timezone.utc),
    )
    _seed_incident(
        repo,
        "at-600",
        lifecycle="open",
        updated_at=datetime(2026, 7, 16, 12, 0, 0, 600000, tzinfo=timezone.utc),
    )

    bound = normalize_updated_after("2026-07-16T12:00:00.500Z")
    assert bound == "2026-07-16T12:00:00.500000+00:00"
    assert canonicalize_utc_iso("2026-07-16T12:00:00.500+00:00") == bound

    page = repo.list_incidents_page(
        build_incident_collection_query(updated_after="2026-07-16T12:00:00.500Z", limit=20)
    )
    assert [row["id"] for row in page.rows] == ["at-600"]
    assert page.total == 1


def test_cursor_round_trips_microseconds_and_rejects_noncanonical(tmp_path: Path):
    repo = _repo(tmp_path)
    _seed_incident(
        repo,
        "with-us",
        lifecycle="open",
        updated_at=datetime(2026, 7, 16, 12, 0, 0, 123456, tzinfo=timezone.utc),
    )
    _seed_incident(
        repo,
        "no-us",
        lifecycle="open",
        updated_at=datetime(2026, 7, 16, 11, 0, 0, tzinfo=timezone.utc),
    )
    first = repo.list_incidents_page(build_incident_collection_query(limit=1))
    assert first.next_cursor is not None
    decoded = decode_incident_collection_cursor(
        first.next_cursor,
        expected_filter_signature=build_incident_collection_query(limit=1).filter_signature,
    )
    assert decoded.updated_at == "2026-07-16T12:00:00.123456+00:00"
    second = repo.list_incidents_page(
        build_incident_collection_query(limit=1, cursor=first.next_cursor)
    )
    assert [row["id"] for row in second.rows] == ["no-us"]
    assert second.next_cursor is None

    # Generated cursor without microseconds still round-trips.
    whole_dir = tmp_path / "whole"
    whole_dir.mkdir()
    repo2 = _repo(whole_dir)
    _seed_incident(
        repo2,
        "a",
        lifecycle="open",
        updated_at=datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc),
    )
    _seed_incident(
        repo2,
        "b",
        lifecycle="open",
        updated_at=datetime(2026, 7, 16, 11, 0, 0, tzinfo=timezone.utc),
    )
    whole_first = repo2.list_incidents_page(build_incident_collection_query(limit=1))
    assert whole_first.next_cursor is not None
    whole_decoded = decode_incident_collection_cursor(
        whole_first.next_cursor,
        expected_filter_signature=build_incident_collection_query(limit=1).filter_signature,
    )
    assert whole_decoded.updated_at == "2026-07-16T12:00:00+00:00"

    # Reject offset / Z forms that would break lexical equality.
    good = build_incident_collection_query(limit=1)
    bad_z = encode_incident_collection_cursor(
        IncidentCollectionCursor(
            version=decoded.version,
            lifecycle_rank=decoded.lifecycle_rank,
            updated_at="2026-07-16T12:00:00.123456Z",
            incident_id=decoded.incident_id,
            filter_signature=decoded.filter_signature,
        )
    )
    with pytest.raises(IncidentCollectionCursorError):
        decode_incident_collection_cursor(
            bad_z, expected_filter_signature=good.filter_signature
        )

    bad_offset = encode_incident_collection_cursor(
        IncidentCollectionCursor(
            version=decoded.version,
            lifecycle_rank=decoded.lifecycle_rank,
            updated_at="2026-07-16T22:00:00.123456+10:00",
            incident_id=decoded.incident_id,
            filter_signature=decoded.filter_signature,
        )
    )
    with pytest.raises(IncidentCollectionCursorError):
        decode_incident_collection_cursor(
            bad_offset, expected_filter_signature=good.filter_signature
        )

    # Trailing Base64 garbage must not be silently ignored.
    with pytest.raises(IncidentCollectionCursorError):
        decode_incident_collection_cursor(
            first.next_cursor + "??",
            expected_filter_signature=good.filter_signature,
        )
    with pytest.raises(IncidentCollectionCursorError):
        decode_incident_collection_cursor(
            first.next_cursor + "A",
            expected_filter_signature=good.filter_signature,
        )

    # Cursor/filter mismatch remains rejected.
    with pytest.raises(IncidentCollectionCursorError):
        repo.list_incidents_page(
            build_incident_collection_query(
                status=["resolved"],
                limit=1,
                cursor=first.next_cursor,
            )
        )


def test_access_layer_delegates_page_and_count(tmp_path: Path):
    repo = _repo(tmp_path)
    _seed_standard_set(repo)
    query = build_incident_collection_query(status=["open", "watching"], limit=10)
    assert repo.incidents.count_incidents(query) == repo.count_incidents(query) == 3
    via_access = repo.incidents.list_incidents_page(query)
    via_repo = repo.list_incidents_page(query)
    assert [row["id"] for row in via_access.rows] == [row["id"] for row in via_repo.rows]


def test_list_composition_skips_events_and_off_page_work(tmp_path: Path):
    from performance.query_instrumentation import install_counter
    from zigbeelens.diagnostics.service import HealthDiagnosticService
    from zigbeelens.services.payload_builder import PayloadBuilder

    repo = _repo(tmp_path)
    _seed_standard_set(repo)
    # Extra off-page resolved history should not be composed on a tiny page.
    for index in range(30):
        _seed_incident(
            repo,
            f"hist-{index:03d}",
            lifecycle="resolved",
            updated_at=NOW - timedelta(days=2, minutes=index),
            refs=[("home", "0xA1")],
        )
    # Attach an event to an off-page and on-page incident.
    repo.insert_event(
        event_id="evt-open-b",
        network_id="home",
        ieee_address="0xA1",
        event_type="incident_updated",
        severity="incident",
        title="on page",
        summary="on page",
        occurred_at=NOW.isoformat(),
        incident_id="open-b",
    )
    repo.insert_event(
        event_id="evt-hist",
        network_id="home",
        ieee_address="0xA1",
        event_type="incident_resolved",
        severity="healthy",
        title="off page",
        summary="off page",
        occurred_at=(NOW - timedelta(days=2)).isoformat(),
        incident_id="hist-000",
    )
    health = HealthDiagnosticService(
        AppConfig(
            mode=ModeConfig(mock=True),
            networks=[
                NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
                NetworkConfig(id="office", name="Office", base_topic="z2m-office"),
            ],
            storage=StorageConfig(path=str(tmp_path / "collection.sqlite")),
        ),
        repo,
    )
    builder = PayloadBuilder(
        AppConfig(
            mode=ModeConfig(mock=True),
            networks=[
                NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
                NetworkConfig(id="office", name="Office", base_topic="z2m-office"),
            ],
            storage=StorageConfig(path=str(tmp_path / "collection.sqlite")),
        ),
        repo,
        health,
    )
    counter = install_counter(repo)
    counter.reset()
    page = builder.incidents_page(build_incident_collection_query(limit=2))
    assert [inc.id for inc in page["items"]] == ["open-b", "open-a"]
    assert all(inc.timeline == [] for inc in page["items"])
    assert counter.stats.category_counts.get("read.events", 0) == 0
    # Only page incident ids should be requested for refs.
    assert counter.stats.category_counts.get("read.incident_devices", 0) == 1

    detail = builder.incident("open-b")
    assert detail is not None
    assert any(event.id == "evt-open-b" for event in detail.timeline)


def test_api_incidents_collection_contract(live_client):
    from fastapi.testclient import TestClient

    client: TestClient = live_client
    repo = client.app.state.ctx.repo
    repo.sync_networks(
        [
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
            NetworkConfig(id="office", name="Office", base_topic="z2m-office"),
        ]
    )
    _seed_standard_set(repo)

    res = client.get("/api/incidents", params={"limit": 2})
    assert res.status_code == 200
    body = res.json()
    assert body["limit"] == 2
    assert body["total"] == 6
    assert body["next_cursor"]
    assert [item["id"] for item in body["items"]] == ["open-b", "open-a"]
    assert all(item["timeline"] == [] for item in body["items"])

    res2 = client.get(
        "/api/v1/incidents",
        params={"limit": 2, "cursor": body["next_cursor"]},
    )
    assert res2.status_code == 200
    body2 = res2.json()
    assert [item["id"] for item in body2["items"]] == ["watch-1", "res-new"]

    bad = client.get("/api/incidents", params={"limit": 2, "cursor": "nope"})
    assert bad.status_code == 400
    invalid = client.get("/api/incidents", params={"status": "nope"})
    assert invalid.status_code == 422

    mock_res = client.get(
        "/api/incidents",
        params={"scenario": "single_device_unavailable", "limit": 50},
    )
    assert mock_res.status_code == 200
    mock_body = mock_res.json()
    assert "limit" in mock_body
    assert "next_cursor" in mock_body
    assert mock_body["total"] == len(mock_body["items"]) or mock_body["next_cursor"] is not None


def test_reports_still_use_complete_history(tmp_path: Path):
    from zigbeelens.schemas import ReportRequest, ReportScope
    from zigbeelens.services.data_service import DataService
    from zigbeelens.diagnostics.service import HealthDiagnosticService

    repo = _repo(tmp_path)
    _seed_standard_set(repo)
    config = AppConfig(
        mode=ModeConfig(mock=False),
        networks=[
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
            NetworkConfig(id="office", name="Office", base_topic="z2m-office"),
        ],
        storage=StorageConfig(path=str(tmp_path / "collection.sqlite")),
    )
    data = DataService(config, repo, HealthDiagnosticService(config, repo))
    history_ids = {row["id"] for row in repo.incidents.list_incidents()}
    assert history_ids == {
        "open-b",
        "open-a",
        "watch-1",
        "res-new",
        "res-old",
        "multi-net",
    }
    page = data.incidents(query=build_incident_collection_query(limit=2))
    assert len(page["items"]) == 2
    report = data.report_preview(request=ReportRequest(scope=ReportScope.full))
    assert {inc.id for inc in report.incidents} == history_ids
