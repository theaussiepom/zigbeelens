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
    decode_incident_collection_cursor,
    encode_incident_collection_cursor,
)
from zigbeelens.storage.repository import Repository

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)


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
        confidence="likely",
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


def test_explain_query_plan_uses_lifecycle_updated_id_index(tmp_path: Path):
    repo = _repo(tmp_path)
    _seed_device(repo, "home", "0xA1")
    for index in range(200):
        _seed_incident(
            repo,
            f"res-{index:04d}",
            lifecycle="resolved",
            updated_at=NOW - timedelta(minutes=index),
            refs=[("home", "0xA1")] if index % 3 == 0 else [],
        )
    query = build_incident_collection_query(status=["resolved"], limit=25)
    where_sql, params = repo._incident_collection_filters(query, include_cursor=False)
    plan_rows = repo.db.conn.execute(
        f"""
        EXPLAIN QUERY PLAN
        SELECT id FROM incidents
        WHERE {where_sql}
        ORDER BY CASE lifecycle_state WHEN 'open' THEN 0 WHEN 'watching' THEN 1 ELSE 2 END ASC,
                 updated_at DESC, id DESC
        LIMIT ?
        """,
        [*params, query.limit + 1],
    ).fetchall()
    plan_text = " | ".join(str(row[-1]) for row in plan_rows)
    assert "idx_incidents_lifecycle_updated_id" in plan_text

    page = repo.list_incidents_page(query)
    assert len(page.rows) == 25
    assert page.total == 200
    assert page.next_cursor is not None
    # Cursor continuation still uses bound parameters (smoke: no exception + progresses).
    page2 = repo.list_incidents_page(
        build_incident_collection_query(
            status=["resolved"],
            limit=25,
            cursor=page.next_cursor,
        )
    )
    assert page2.rows[0]["id"] != page.rows[0]["id"]
    assert {row["id"] for row in page.rows}.isdisjoint({row["id"] for row in page2.rows})


def test_access_layer_delegates_page_and_count(tmp_path: Path):
    repo = _repo(tmp_path)
    _seed_standard_set(repo)
    query = build_incident_collection_query(status=["open", "watching"], limit=10)
    assert repo.incidents.count_incidents(query) == repo.count_incidents(query) == 3
    via_access = repo.incidents.list_incidents_page(query)
    via_repo = repo.list_incidents_page(query)
    assert [row["id"] for row in via_access.rows] == [row["id"] for row in via_repo.rows]
