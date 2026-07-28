"""Atomic topology replacement and production capture failure regressions."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import Mock

import pytest

from zigbeelens.config.models import (
    AppConfig,
    FeaturesConfig,
    ModeConfig,
    NetworkConfig,
    StorageConfig,
    TopologyConfig,
)
from zigbeelens.db.connection import Database
from zigbeelens.mqtt.models import RawMqttMessage
from zigbeelens.storage.repository import Repository, utc_now_iso
from zigbeelens.topology.parser import ParsedTopology, parse_networkmap_payload
from zigbeelens.topology.publisher import FakeTopologyRequestPublisher
from zigbeelens.topology.service import TopologyService


def _config(path: Path) -> AppConfig:
    return AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(path)),
        features=FeaturesConfig(
            manual_network_map=True,
            automatic_network_map=False,
        ),
        topology=TopologyConfig(
            enabled=True,
            manual_capture_enabled=True,
            automatic_capture_enabled=False,
            startup_scan=False,
            capture_on_incident=False,
            max_snapshots_per_network=30,
        ),
    )


def _repo(tmp_path: Path) -> tuple[Repository, AppConfig]:
    path = tmp_path / "atomic-topology.sqlite"
    config = _config(path)
    db = Database(path)
    db.migrate()
    repo = Repository(db)
    repo.sync_networks(config.networks)
    return repo, config


def _parsed(
    marker: str,
    *,
    duplicate_node: bool = False,
    duplicate_link: bool = False,
) -> ParsedTopology:
    nodes = [
        {
            "ieeeAddr": f"0x{marker}-router",
            "friendlyName": f"{marker} router",
            "type": "Router",
        },
        {
            "ieeeAddr": f"0x{marker}-end",
            "friendlyName": f"{marker} end",
            "type": "EndDevice",
        },
    ]
    if duplicate_node:
        nodes = [
            {
                "ieeeAddr": f"0x{marker}-duplicate",
                "friendlyName": "retained first",
                "type": "Router",
            },
            {
                "ieeeAddr": f"0X{marker.upper()}-DUPLICATE",
                "friendlyName": "conflicting second",
                "type": "EndDevice",
            },
        ]
    links = [
        {
            "source": nodes[0]["ieeeAddr"],
            "target": f"0x{marker}-peer",
            "linkquality": 70,
        }
    ]
    if duplicate_link:
        links.append(
            {
                "source": nodes[0]["ieeeAddr"],
                "target": f"0x{marker}-peer",
                "linkquality": 95,
                "routes": [{"destinationAddress": 0}],
            }
        )
    return parse_networkmap_payload({"nodes": nodes, "links": links, "marker": marker})


def _create_stored_snapshot(repo: Repository, snapshot_id: str = "snapshot") -> None:
    repo.create_topology_snapshot(
        snapshot_id=snapshot_id,
        network_id="home",
        requested_by="test",
        status="pending",
        warning_acknowledged=True,
    )
    repo.store_topology_parsed(
        snapshot_id,
        "home",
        _parsed("prior"),
        status="complete",
    )


def _stored_state(repo: Repository, snapshot_id: str = "snapshot") -> dict[str, Any]:
    snapshot = repo.db.conn.execute(
        """
        SELECT status, raw_redacted_json, parsed_json, router_count,
               end_device_count, link_count, error
        FROM topology_snapshots
        WHERE snapshot_id = ?
        """,
        (snapshot_id,),
    ).fetchone()
    nodes = repo.db.conn.execute(
        """
        SELECT network_id, ieee_address, friendly_name, node_type, depth, lqi,
               raw_json
        FROM topology_nodes
        WHERE snapshot_id = ?
        ORDER BY ieee_address
        """,
        (snapshot_id,),
    ).fetchall()
    links = repo.db.conn.execute(
        """
        SELECT network_id, source_ieee, target_ieee, source_type, target_type,
               linkquality, depth, relationship, route_count, raw_json
        FROM topology_links
        WHERE snapshot_id = ?
        ORDER BY source_ieee, target_ieee
        """,
        (snapshot_id,),
    ).fetchall()
    assert snapshot is not None
    return {
        "snapshot": dict(snapshot),
        "nodes": [dict(row) for row in nodes],
        "links": [dict(row) for row in links],
    }


class _ConnectionProxy:
    def __init__(
        self,
        real: sqlite3.Connection,
        *,
        before_execute: Callable[[str, Any], None] | None = None,
        fail_first_commit: bool = False,
        fail_before_first_rollback: bool = False,
        fail_after_first_rollback: bool = False,
    ) -> None:
        self._real = real
        self._before_execute = before_execute
        self._fail_first_commit = fail_first_commit
        self._failed_commit = False
        self._fail_before_first_rollback = fail_before_first_rollback
        self._fail_after_first_rollback = fail_after_first_rollback
        self._failed_rollback = False

    def execute(self, sql: str, params: Any = ()) -> Any:
        if self._before_execute is not None:
            self._before_execute(sql, params)
        return self._real.execute(sql, params)

    def commit(self) -> None:
        if self._fail_first_commit and not self._failed_commit:
            self._failed_commit = True
            raise sqlite3.OperationalError("injected physical commit failure")
        self._real.commit()

    def rollback(self) -> None:
        if self._fail_before_first_rollback and not self._failed_rollback:
            self._failed_rollback = True
            raise sqlite3.OperationalError(
                "injected failure before physical rollback"
            )
        self._real.rollback()
        if self._fail_after_first_rollback and not self._failed_rollback:
            self._failed_rollback = True
            raise sqlite3.OperationalError("injected failure after physical rollback")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def _statement_fault(stage: str) -> Callable[[str, Any], None]:
    node_inserts = 0

    def before_execute(sql: str, _params: Any) -> None:
        nonlocal node_inserts
        normalized = " ".join(sql.upper().split())
        if stage == "after_snapshot_update" and normalized.startswith("DELETE FROM TOPOLOGY_NODES"):
            raise RuntimeError(stage)
        if stage == "after_node_delete" and normalized.startswith("DELETE FROM TOPOLOGY_LINKS"):
            raise RuntimeError(stage)
        if normalized.startswith("INSERT INTO TOPOLOGY_NODES"):
            node_inserts += 1
            if stage == "after_first_node_insert" and node_inserts == 2:
                raise RuntimeError(stage)
        if stage == "during_link_insert" and normalized.startswith("INSERT INTO TOPOLOGY_LINKS"):
            raise RuntimeError(stage)

    return before_execute


def test_successful_replacement_has_one_commit_and_coherent_derived_counts(
    tmp_path: Path,
) -> None:
    repo, _ = _repo(tmp_path)
    _create_stored_snapshot(repo)
    parsed = _parsed("accepted", duplicate_link=True)
    # Persistence owns counts rather than trusting mutable producer metadata.
    parsed.router_count = 999
    parsed.end_device_count = 999
    physical: list[str] = []
    repo.db.conn.set_transaction_observer(
        on_commit=lambda: physical.append("commit"),
        on_rollback=lambda: physical.append("rollback"),
    )

    repo.store_topology_parsed(
        "snapshot",
        "home",
        parsed,
        status="complete",
    )

    state = _stored_state(repo)
    assert physical == ["commit"]
    assert [row["ieee_address"] for row in state["nodes"]] == [
        "0xaccepted-end",
        "0xaccepted-router",
    ]
    assert len(state["links"]) == 1
    assert state["links"][0]["linkquality"] == 95
    assert state["links"][0]["route_count"] == 1
    assert state["snapshot"]["router_count"] == 1
    assert state["snapshot"]["end_device_count"] == 1
    assert state["snapshot"]["link_count"] == 1
    assert state["snapshot"]["parsed_json"] is None
    assert all(row["raw_json"] == "{}" for row in state["nodes"])
    assert all(row["raw_json"] == "{}" for row in state["links"])


def test_duplicate_normalized_node_is_rejected_and_rolls_back_prior_state(
    tmp_path: Path,
) -> None:
    repo, _ = _repo(tmp_path)
    _create_stored_snapshot(repo)
    before = _stored_state(repo)
    physical: list[str] = []
    repo.db.conn.set_transaction_observer(
        on_commit=lambda: physical.append("commit"),
        on_rollback=lambda: physical.append("rollback"),
    )

    with pytest.raises(
        sqlite3.IntegrityError,
        match="topology_nodes.snapshot_id, topology_nodes.ieee_address",
    ):
        repo.store_topology_parsed(
            "snapshot",
            "home",
            _parsed("dup", duplicate_node=True),
            status="complete",
        )

    assert physical == ["rollback"]
    assert _stored_state(repo) == before
    assert repo.db.conn.transaction_depth == 0
    assert repo.db._conn.in_transaction is False


@pytest.mark.parametrize(
    "stage",
    [
        "after_snapshot_update",
        "after_node_delete",
        "after_first_node_insert",
        "during_link_insert",
    ],
)
def test_each_replacement_mutation_stage_rolls_back_byte_equivalent_state(
    tmp_path: Path,
    stage: str,
) -> None:
    repo, _ = _repo(tmp_path)
    _create_stored_snapshot(repo)
    before = _stored_state(repo)
    physical: list[str] = []
    repo.db.conn.set_transaction_observer(
        on_commit=lambda: physical.append("commit"),
        on_rollback=lambda: physical.append("rollback"),
    )
    locked = repo.db.conn
    real = locked._conn
    locked._conn = _ConnectionProxy(  # type: ignore[assignment]
        real,
        before_execute=_statement_fault(stage),
    )
    try:
        with pytest.raises(RuntimeError, match=stage):
            repo.store_topology_parsed(
                "snapshot",
                "home",
                _parsed("candidate"),
                status="complete",
            )
    finally:
        locked._conn = real

    assert physical == ["rollback"]
    assert _stored_state(repo) == before
    assert locked.transaction_depth == 0
    assert real.in_transaction is False


def test_physical_commit_failure_rolls_back_then_allows_coherent_retry(
    tmp_path: Path,
) -> None:
    repo, _ = _repo(tmp_path)
    _create_stored_snapshot(repo)
    before = _stored_state(repo)
    physical: list[str] = []
    repo.db.conn.set_transaction_observer(
        on_commit=lambda: physical.append("commit"),
        on_rollback=lambda: physical.append("rollback"),
    )
    locked = repo.db.conn
    real = locked._conn
    locked._conn = _ConnectionProxy(  # type: ignore[assignment]
        real,
        fail_first_commit=True,
    )
    try:
        with pytest.raises(
            sqlite3.OperationalError,
            match="injected physical commit failure",
        ):
            repo.store_topology_parsed(
                "snapshot",
                "home",
                _parsed("candidate"),
                status="complete",
            )
        assert _stored_state(repo) == before
        repo.store_topology_parsed(
            "snapshot",
            "home",
            _parsed("retry"),
            status="complete",
        )
    finally:
        locked._conn = real

    assert physical == ["rollback", "commit"]
    retry = _stored_state(repo)
    assert [row["ieee_address"] for row in retry["nodes"]] == [
        "0xretry-end",
        "0xretry-router",
    ]
    assert retry["snapshot"]["router_count"] == 1
    assert retry["snapshot"]["end_device_count"] == 1
    assert retry["snapshot"]["link_count"] == len(retry["links"]) == 1


def test_failure_reported_after_completed_physical_rollback_keeps_connection_usable(
    tmp_path: Path,
) -> None:
    """A post-rollback driver error propagates without resurrecting writes."""
    repo, _ = _repo(tmp_path)
    _create_stored_snapshot(repo)
    before = _stored_state(repo)
    locked = repo.db.conn
    real = locked._conn
    locked._conn = _ConnectionProxy(  # type: ignore[assignment]
        real,
        fail_after_first_rollback=True,
    )
    try:
        with pytest.raises(
            sqlite3.OperationalError,
            match="injected failure after physical rollback",
        ):
            repo.store_topology_parsed(
                "snapshot",
                "home",
                _parsed("dup", duplicate_node=True),
                status="complete",
            )
    finally:
        locked._conn = real

    assert _stored_state(repo) == before
    assert locked.transaction_depth == 0
    assert real.in_transaction is False
    repo.store_topology_parsed(
        "snapshot",
        "home",
        _parsed("recovered"),
        status="complete",
    )
    assert _stored_state(repo)["snapshot"]["status"] == "complete"


def _message(payload: dict[str, Any]) -> RawMqttMessage:
    return RawMqttMessage(
        topic="zigbee2mqtt/bridge/response/networkmap",
        payload=json.dumps(payload).encode(),
        retained=False,
        received_at=utc_now_iso(),
    )


def test_service_physical_commit_failure_records_only_error_state(
    tmp_path: Path,
) -> None:
    repo, config = _repo(tmp_path)
    broadcaster = Mock()
    context = SimpleNamespace(
        config=config,
        repo=repo,
        broadcaster=broadcaster,
        evaluation=None,
        health=Mock(),
        discovery=None,
    )
    service = TopologyService(
        context,
        publisher=FakeTopologyRequestPublisher(config),
    )
    service.request_capture("home", confirmed=True)
    snapshot_id = service.active_pending_snapshot_id
    assert snapshot_id is not None
    physical: list[str] = []
    repo.db.conn.set_transaction_observer(
        on_commit=lambda: physical.append("commit"),
        on_rollback=lambda: physical.append("rollback"),
    )
    locked = repo.db.conn
    real = locked._conn
    locked._conn = _ConnectionProxy(  # type: ignore[assignment]
        real,
        fail_first_commit=True,
    )
    try:
        assert (
            service.try_handle_response(
                _message(
                    {
                        "nodes": [
                            {"ieeeAddr": "0xrouter", "type": "Router"},
                            {"ieeeAddr": "0xend", "type": "EndDevice"},
                        ],
                        "links": [
                            {"source": "0xrouter", "target": "0xend"}
                        ],
                    }
                )
            )
            is False
        )
    finally:
        locked._conn = real

    assert physical == ["rollback", "commit"]
    failed = _stored_state(repo, snapshot_id)
    assert failed["snapshot"] == {
        "status": "error",
        "raw_redacted_json": None,
        "parsed_json": None,
        "router_count": 0,
        "end_device_count": 0,
        "link_count": 0,
        "error": "Topology response handling failed",
    }
    assert failed["nodes"] == []
    assert failed["links"] == []
    assert service.active_pending_snapshot_id is None
    assert service.status.capture_in_progress is False
    assert broadcaster.publish_sync.call_args_list == []


@pytest.mark.parametrize("fail_before_first_rollback", [False, True])
def test_service_error_commit_follows_rollback_and_retry_emits_one_event(
    tmp_path: Path,
    fail_before_first_rollback: bool,
) -> None:
    repo, config = _repo(tmp_path)
    broadcaster = Mock()
    context = SimpleNamespace(
        config=config,
        repo=repo,
        broadcaster=broadcaster,
        evaluation=None,
        health=Mock(),
        discovery=None,
    )
    service = TopologyService(
        context,
        publisher=FakeTopologyRequestPublisher(config),
    )
    service.request_capture("home", confirmed=True)
    failed_id = service.active_pending_snapshot_id
    assert failed_id is not None
    physical: list[str] = []
    repo.db.conn.set_transaction_observer(
        on_commit=lambda: physical.append("commit"),
        on_rollback=lambda: physical.append("rollback"),
    )
    locked = repo.db.conn
    real_connection = locked._conn
    if fail_before_first_rollback:
        locked._conn = _ConnectionProxy(  # type: ignore[assignment]
            real_connection,
            fail_before_first_rollback=True,
        )
    status_write_entry: list[tuple[int, bool, dict[str, Any]]] = []
    real_update = repo.update_topology_snapshot

    def observed_update(snapshot_id: str, **kwargs: Any) -> None:
        status_write_entry.append(
            (
                repo.db.conn.transaction_depth,
                repo.db._conn.in_transaction,
                _stored_state(repo, snapshot_id),
            )
        )
        real_update(snapshot_id, **kwargs)

    repo.update_topology_snapshot = observed_update  # type: ignore[method-assign]
    try:
        try:
            assert (
                service.try_handle_response(
                    _message(
                        {
                            "nodes": [
                                {"ieeeAddr": "0xdup", "type": "Router"},
                                {"ieeeAddr": "0XDUP", "type": "EndDevice"},
                            ],
                            "links": [{"source": "0xdup", "target": "0xpeer"}],
                        }
                    )
                )
                is False
            )
        finally:
            repo.update_topology_snapshot = real_update  # type: ignore[method-assign]

        assert physical == ["rollback", "commit"]
        assert len(status_write_entry) == 1
        depth, in_transaction, before_error_write = status_write_entry[0]
        assert depth == 0
        assert in_transaction is False
        assert before_error_write["snapshot"]["status"] == "pending"
        assert before_error_write["snapshot"]["raw_redacted_json"] is None
        assert before_error_write["nodes"] == []
        assert before_error_write["links"] == []
        failed = _stored_state(repo, failed_id)
        assert failed["snapshot"] == {
            "status": "error",
            "raw_redacted_json": None,
            "parsed_json": None,
            "router_count": 0,
            "end_device_count": 0,
            "link_count": 0,
            "error": "Topology response handling failed",
        }
        assert failed["nodes"] == []
        assert failed["links"] == []
        assert service.active_pending_snapshot_id is None
        assert service.status.capture_in_progress is False
        assert broadcaster.publish_sync.call_args_list == []

        service.request_capture("home", confirmed=True)
        retry_id = service.active_pending_snapshot_id
        assert retry_id is not None
        assert service.try_handle_response(
            _message(
                {
                    "nodes": [
                        {"ieeeAddr": "0xrouter", "type": "Router"},
                        {"ieeeAddr": "0xend", "type": "EndDevice"},
                    ],
                    "links": [
                        {
                            "source": "0xrouter",
                            "target": "0xend",
                            "linkquality": 88,
                        }
                    ],
                }
            )
        )

        retry = _stored_state(repo, retry_id)
        assert retry["snapshot"]["status"] == "complete"
        assert retry["snapshot"]["router_count"] == 1
        assert retry["snapshot"]["end_device_count"] == 1
        assert retry["snapshot"]["link_count"] == len(retry["links"]) == 1
        assert len(retry["nodes"]) == 2
        assert service.active_pending_snapshot_id is None
        assert service.status.capture_in_progress is False
        assert [call.args[0] for call in broadcaster.publish_sync.call_args_list] == [
            "topology_updated"
        ]
    finally:
        locked._conn = real_connection
