from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.mqtt.ingestion import MqttIngestionService
from zigbeelens.mqtt.models import NormalizedMqttEvent
from zigbeelens.storage.repository import Repository

from performance.query_instrumentation import install_counter
from performance.test_performance_baselines import deterministic_fixture


def _repo(tmp_path: Path) -> tuple[Repository, AppConfig]:
    db_path = tmp_path / "tx.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    config = AppConfig(
        mode=ModeConfig(mock=False),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(db_path)),
    )
    repo.sync_networks(config.networks)
    return repo, config


def _locked(repo: Repository):
    conn = repo.db.conn
    return getattr(conn, "_wrapped", conn)


def _raw(repo: Repository) -> sqlite3.Connection:
    return repo.db._conn


def _count(repo: Repository, sql: str, params: tuple = ()) -> int:
    row = repo.db.conn.execute(sql, params).fetchone()
    return int(row[0])


def test_write_outside_transaction_commits_immediately(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    counter = install_counter(repo)
    counter.reset()

    repo.upsert_device(
        network_id="home",
        ieee_address="0x1",
        friendly_name="Plug",
        device_type="Router",
        power_source="Mains",
        manufacturer=None,
        model=None,
        interview_state="successful",
    )

    assert counter.stats.commit_count == 1
    assert repo.get_device("home", "0x1") is not None


def test_repository_transaction_defers_internal_commits_and_commits_once(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    counter = install_counter(repo)
    counter.reset()

    with repo.transaction():
        repo.upsert_device(
            network_id="home",
            ieee_address="0x1",
            friendly_name="Plug",
            device_type="Router",
            power_source="Mains",
            manufacturer=None,
            model=None,
            interview_state="successful",
        )
        repo.ensure_device_current_state("home", "0x1")
        repo.update_device_current_state(network_id="home", ieee_address="0x1", linkquality=80)
        repo.insert_device_snapshot(
            network_id="home",
            ieee_address="0x1",
            availability=None,
            last_seen=None,
            last_payload_at=None,
            linkquality=80,
            battery=None,
            payload_json="{}",
        )
        repo.insert_event(
            event_id="evt",
            network_id="home",
            ieee_address="0x1",
            event_type="device_payload_seen",
            severity="watch",
            title="Payload",
            summary="Seen",
        )

    assert counter.stats.commit_count == 1
    assert counter.stats.rollback_count == 0
    assert repo.get_device("home", "0x1").linkquality == 80  # type: ignore[union-attr]


def test_nested_exception_rolls_back_complete_outer_transaction(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    counter = install_counter(repo)
    counter.reset()

    with pytest.raises(ValueError):
        with repo.transaction():
            repo.upsert_device(
                network_id="home",
                ieee_address="0x1",
                friendly_name="Plug",
                device_type="Router",
                power_source="Mains",
                manufacturer=None,
                model=None,
                interview_state="successful",
            )
            with repo.transaction():
                repo.ensure_device_current_state("home", "0x1")
                raise ValueError("boom")

    assert counter.stats.commit_count == 0
    assert counter.stats.rollback_count == 1
    assert repo.get_device("home", "0x1") is None
    repo.upsert_device(
        network_id="home",
        ieee_address="0x2",
        friendly_name="Ok",
        device_type="Router",
        power_source="Mains",
        manufacturer=None,
        model=None,
        interview_state="successful",
    )
    assert repo.get_device("home", "0x2") is not None


def test_explicit_rollback_marks_outer_transaction_rollback_only(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    counter = install_counter(repo)
    counter.reset()

    with pytest.raises(RuntimeError, match="rolled back"):
        with repo.transaction():
            repo.upsert_device(
                network_id="home",
                ieee_address="0x1",
                friendly_name="Plug",
                device_type="Router",
                power_source="Mains",
                manufacturer=None,
                model=None,
                interview_state="successful",
            )
            repo.db.conn.rollback()

    assert counter.stats.commit_count == 0
    assert counter.stats.rollback_count == 1
    assert repo.get_device("home", "0x1") is None


def test_narrow_access_repositories_share_transaction(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    counter = install_counter(repo)
    counter.reset()

    with repo.transaction():
        repo.upsert_device(
            network_id="home",
            ieee_address="0x1",
            friendly_name="Plug",
            device_type="Router",
            power_source="Mains",
            manufacturer=None,
            model=None,
            interview_state="successful",
        )
        repo.metrics.insert_metric_sample("home", "0x1", "battery", 50.0)
        repo.availability.insert_availability_change("home", "0x1", "offline", "online")

    assert counter.stats.commit_count == 1


def test_same_connection_thread_cannot_interleave_inside_transaction(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    entered = threading.Event()
    seen: list[int] = []

    def reader() -> None:
        entered.wait()
        seen.append(repo.count_devices())

    thread = threading.Thread(target=reader)
    with repo.transaction():
        repo.upsert_device(
            network_id="home",
            ieee_address="0x1",
            friendly_name="Plug",
            device_type="Router",
            power_source="Mains",
            manufacturer=None,
            model=None,
            interview_state="successful",
        )
        thread.start()
        entered.set()
        assert seen == []
    thread.join(timeout=2)
    assert seen == [1]


def test_separate_sqlite_reader_sees_no_partial_transaction_then_complete_commit(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    other = sqlite3.connect(repo.db.path)
    try:
        with repo.transaction():
            repo.upsert_device(
                network_id="home",
                ieee_address="0x1",
                friendly_name="Plug",
                device_type="Router",
                power_source="Mains",
                manufacturer=None,
                model=None,
                interview_state="successful",
            )
            assert other.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 0
        assert other.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 1
    finally:
        other.close()


def test_physical_commit_failure_rolls_back_and_keeps_connection_usable(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    counter = install_counter(repo)
    counter.reset()

    with pytest.raises(sqlite3.IntegrityError):
        with repo.transaction():
            repo.db.conn.execute("PRAGMA defer_foreign_keys = ON").fetchone()
            repo.db.conn.execute(
                "INSERT INTO device_current_state (network_id, ieee_address) VALUES (?, ?)",
                ("home", "0xmissing"),
            ).fetchone()

    assert counter.stats.commit_count == 0
    assert counter.stats.rollback_count == 1
    assert _raw(repo).in_transaction is False
    assert _locked(repo).transaction_depth == 0
    assert _count(repo, "SELECT COUNT(*) FROM device_current_state WHERE ieee_address = ?", ("0xmissing",)) == 0

    with repo.transaction():
        repo.upsert_device(
            network_id="home",
            ieee_address="0x1",
            friendly_name="Plug",
            device_type="Router",
            power_source="Mains",
            manufacturer=None,
            model=None,
            interview_state="successful",
        )
    assert counter.stats.commit_count == 1
    assert repo.get_device("home", "0x1") is not None
    assert _raw(repo).in_transaction is False
    assert _locked(repo).transaction_depth == 0


def test_counted_query_does_not_deadlock_with_physical_commit_observer(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    counter = install_counter(repo)
    counter.reset()
    a_in_tx = threading.Event()
    b_started = threading.Event()
    release_a = threading.Event()
    errors: list[BaseException] = []
    seen: list[int] = []

    def writer() -> None:
        try:
            with repo.transaction():
                repo.upsert_device(
                    network_id="home",
                    ieee_address="0x1",
                    friendly_name="Plug",
                    device_type="Router",
                    power_source="Mains",
                    manufacturer=None,
                    model=None,
                    interview_state="successful",
                )
                a_in_tx.set()
                assert release_a.wait(timeout=5)
        except BaseException as exc:  # noqa: BLE001 - collect for assertion
            errors.append(exc)

    def reader() -> None:
        try:
            assert a_in_tx.wait(timeout=5)
            b_started.set()
            seen.append(repo.count_devices())
        except BaseException as exc:  # noqa: BLE001 - collect for assertion
            errors.append(exc)

    t_writer = threading.Thread(target=writer)
    t_reader = threading.Thread(target=reader)
    t_writer.start()
    t_reader.start()
    assert a_in_tx.wait(timeout=5)
    assert b_started.wait(timeout=5)
    release_a.set()
    t_writer.join(timeout=5)
    t_reader.join(timeout=5)
    assert not t_writer.is_alive()
    assert not t_reader.is_alive()
    assert errors == []
    assert seen == [1]
    assert counter.stats.commit_count == 1
    assert counter.stats.rollback_count == 0
    assert counter.stats.execute_count >= 1


def test_executescript_allowed_outside_rejected_inside_transaction(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    counter = install_counter(repo)
    counter.reset()

    repo.db.conn.executescript("CREATE TABLE IF NOT EXISTS tx_guard_probe (id INTEGER PRIMARY KEY)")
    assert _count(repo, "SELECT COUNT(*) FROM sqlite_master WHERE name = ?", ("tx_guard_probe",)) == 1

    with pytest.raises(RuntimeError, match="executescript is not allowed inside a repository transaction"):
        with repo.transaction():
            repo.upsert_device(
                network_id="home",
                ieee_address="0x1",
                friendly_name="Plug",
                device_type="Router",
                power_source="Mains",
                manufacturer=None,
                model=None,
                interview_state="successful",
            )
            repo.db.conn.executescript("CREATE TABLE tx_guard_inside (id INTEGER PRIMARY KEY)")

    assert counter.stats.commit_count == 0
    assert counter.stats.rollback_count == 1
    assert repo.get_device("home", "0x1") is None
    assert _count(repo, "SELECT COUNT(*) FROM sqlite_master WHERE name = ?", ("tx_guard_inside",)) == 0
    assert _locked(repo).transaction_depth == 0
    assert _raw(repo).in_transaction is False

    repo.upsert_device(
        network_id="home",
        ieee_address="0x2",
        friendly_name="Ok",
        device_type="Router",
        power_source="Mains",
        manufacturer=None,
        model=None,
        interview_state="successful",
    )
    assert repo.get_device("home", "0x2") is not None


def test_mqtt_payload_event_rolls_back_handler_writes_when_event_insert_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo, config = _repo(tmp_path)
    repo.upsert_device(
        network_id="home",
        ieee_address="0x1",
        friendly_name="Plug",
        device_type="Router",
        power_source="Mains",
        manufacturer=None,
        model=None,
        interview_state="successful",
    )
    counter = install_counter(repo)
    counter.reset()
    callbacks: list[str] = []
    svc = MqttIngestionService(
        config,
        repo,
        on_health_recalc=lambda *_: callbacks.append("health"),
        on_dashboard_update=lambda *_: callbacks.append("dashboard"),
    )

    def fail_store(_event: NormalizedMqttEvent) -> None:
        raise RuntimeError("insert failed")

    monkeypatch.setattr(svc, "_store_event", fail_store)
    event = NormalizedMqttEvent(
        event_type="device_payload_seen",
        network_id="home",
        title="payload",
        summary="payload",
        friendly_name="Plug",
        device_fields={"linkquality": 99, "battery": 77},
        raw_payload_redacted='{"linkquality":99}',
        emit_dashboard=True,
    )

    with pytest.raises(RuntimeError, match="insert failed"):
        svc.ingest(event)

    device = repo.get_device("home", "0x1")
    assert device is not None
    assert device.linkquality is None
    assert repo.list_device_snapshots("home", "0x1") == []
    assert repo.list_events("home") == []
    assert callbacks == []
    assert counter.stats.commit_count == 0
    assert counter.stats.rollback_count == 1


def test_mqtt_availability_final_event_failure_rolls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo, config = _repo(tmp_path)
    repo.upsert_device(
        network_id="home",
        ieee_address="0x1",
        friendly_name="Plug",
        device_type="Router",
        power_source="Mains",
        manufacturer=None,
        model=None,
        interview_state="successful",
    )
    repo.ensure_device_current_state("home", "0x1")
    repo.update_device_current_state(network_id="home", ieee_address="0x1", availability="online")
    counter = install_counter(repo)
    counter.reset()
    callbacks: list[str] = []
    svc = MqttIngestionService(
        config,
        repo,
        on_health_recalc=lambda *_: callbacks.append("health"),
        on_dashboard_update=lambda *_: callbacks.append("dashboard"),
    )
    monkeypatch.setattr(svc, "_store_event", lambda _e: (_ for _ in ()).throw(RuntimeError("store failed")))

    with pytest.raises(RuntimeError, match="store failed"):
        svc.ingest(
            NormalizedMqttEvent(
                event_type="device_availability_seen",
                network_id="home",
                title="availability",
                summary="availability",
                friendly_name="Plug",
                availability="offline",
                emit_dashboard=True,
            )
        )

    assert repo.get_device_availability("home", "0x1") == "online"
    assert repo.list_availability_changes("home", "0x1") == []
    assert repo.list_events("home") == []
    assert callbacks == []
    assert counter.stats.commit_count == 0
    assert counter.stats.rollback_count == 1

    monkeypatch.undo()
    counter.reset()
    callbacks.clear()
    svc = MqttIngestionService(
        config,
        repo,
        on_health_recalc=lambda *_: callbacks.append("health"),
        on_dashboard_update=lambda *_: callbacks.append("dashboard"),
    )
    svc.ingest(
        NormalizedMqttEvent(
            event_type="device_availability_seen",
            network_id="home",
            title="availability",
            summary="availability",
            friendly_name="Plug",
            availability="offline",
            emit_dashboard=True,
        )
    )
    assert repo.get_device_availability("home", "0x1") == "offline"
    assert len(repo.list_availability_changes("home", "0x1")) == 1
    assert counter.stats.commit_count == 1
    assert counter.stats.rollback_count == 0
    assert callbacks == ["health", "dashboard"]


def test_mqtt_inventory_mid_refresh_failure_rolls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    with deterministic_fixture(tmp_path, "compact") as fx:
        repo = fx.repo
        config = fx.config
        prior = {d.ieee_address: (d.friendly_name, d.manufacturer, d.model, d.interview_state) for d in repo.list_devices("home")}
        prior_events = _count(repo, "SELECT COUNT(*) FROM events")
        prior_unresolved = _count(repo, "SELECT COUNT(*) FROM unresolved_device_messages")
        prior_state = _count(repo, "SELECT COUNT(*) FROM device_current_state")
        assert len(prior) == 20

        counter = fx.counter
        counter.reset()
        callbacks: list[str] = []
        svc = MqttIngestionService(
            config,
            repo,
            on_health_recalc=lambda *_: callbacks.append("health"),
            on_dashboard_update=lambda *_: callbacks.append("dashboard"),
        )
        devices = sorted(prior.keys())
        fail_ieee = devices[len(devices) // 2]
        original = repo.upsert_device

        def flaky_upsert(**kwargs):
            if kwargs.get("ieee_address") == fail_ieee:
                raise RuntimeError(f"mid refresh fail on {fail_ieee}")
            return original(**kwargs)

        monkeypatch.setattr(repo, "upsert_device", flaky_upsert)
        payload = [
            {
                "ieee_address": ieee,
                "friendly_name": f"Refresh-{ieee[-4:]}",
                "type": "Router",
                "power_source": "Mains",
                "manufacturer": "RefreshCo",
                "model_id": "RefreshModel",
                "interview_completed": True,
            }
            for ieee in devices
        ]
        event = NormalizedMqttEvent(
            event_type="device_inventory_seen",
            network_id="home",
            title="inventory",
            summary="inventory",
            devices=payload,
            emit_dashboard=True,
        )
        with pytest.raises(RuntimeError, match="mid refresh fail"):
            svc.ingest(event)

        assert repo.count_devices() == 20
        for ieee, meta in prior.items():
            device = repo.get_device("home", ieee)
            assert device is not None
            assert (device.friendly_name, device.manufacturer, device.model, device.interview_state) == meta
        assert _count(repo, "SELECT COUNT(*) FROM events") == prior_events
        assert _count(repo, "SELECT COUNT(*) FROM unresolved_device_messages") == prior_unresolved
        assert _count(repo, "SELECT COUNT(*) FROM device_current_state") == prior_state
        assert callbacks == []
        assert counter.stats.commit_count == 0
        assert counter.stats.rollback_count == 1

        monkeypatch.setattr(repo, "upsert_device", original)
        counter.reset()
        svc.ingest(event)
        refreshed = repo.get_device("home", devices[0])
        assert refreshed is not None
        assert refreshed.manufacturer == "RefreshCo"
        assert counter.stats.commit_count == 1
        assert counter.stats.rollback_count == 0


def test_mqtt_bridge_state_final_event_failure_rolls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo, config = _repo(tmp_path)
    repo.update_network_bridge_state("home", "online")
    counter = install_counter(repo)
    counter.reset()
    callbacks: list[str] = []
    svc = MqttIngestionService(
        config,
        repo,
        on_health_recalc=lambda *_: callbacks.append("health"),
        on_dashboard_update=lambda *_: callbacks.append("dashboard"),
    )
    monkeypatch.setattr(svc, "_store_event", lambda _e: (_ for _ in ()).throw(RuntimeError("store failed")))

    with pytest.raises(RuntimeError, match="store failed"):
        svc.ingest(
            NormalizedMqttEvent(
                event_type="bridge_state_seen",
                network_id="home",
                title="bridge",
                summary="bridge",
                bridge_state="offline",
                emit_dashboard=True,
            )
        )

    assert repo.get_network("home").bridge_state == "online"  # type: ignore[union-attr]
    assert repo.list_events("home") == []
    assert callbacks == []
    assert counter.stats.commit_count == 0
    assert counter.stats.rollback_count == 1


def test_mqtt_unresolved_payload_final_event_failure_rolls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo, config = _repo(tmp_path)
    counter = install_counter(repo)
    counter.reset()
    callbacks: list[str] = []
    svc = MqttIngestionService(
        config,
        repo,
        on_health_recalc=lambda *_: callbacks.append("health"),
        on_dashboard_update=lambda *_: callbacks.append("dashboard"),
    )
    monkeypatch.setattr(svc, "_store_event", lambda _e: (_ for _ in ()).throw(RuntimeError("store failed")))

    with pytest.raises(RuntimeError, match="store failed"):
        svc.ingest(
            NormalizedMqttEvent(
                event_type="device_payload_seen",
                network_id="home",
                title="payload",
                summary="payload",
                friendly_name="Ghost",
                device_fields={"linkquality": 1},
                raw_payload_redacted='{"linkquality":1}',
                emit_dashboard=True,
            )
        )

    assert _count(repo, "SELECT COUNT(*) FROM unresolved_device_messages") == 0
    assert repo.list_events("home") == []
    assert callbacks == []
    assert counter.stats.commit_count == 0
    assert counter.stats.rollback_count == 1


def test_separate_reader_sees_only_old_state_during_and_after_rollback(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    repo.upsert_device(
        network_id="home",
        ieee_address="0x1",
        friendly_name="Plug",
        device_type="Router",
        power_source="Mains",
        manufacturer="OldCo",
        model="Old",
        interview_state="successful",
    )
    other = sqlite3.connect(str(repo.db.path))
    other.row_factory = sqlite3.Row
    blocked = threading.Event()
    may_fail = threading.Event()
    done = threading.Event()
    errors: list[BaseException] = []

    def writer() -> None:
        try:
            with pytest.raises(RuntimeError, match="forced"):
                with repo.transaction():
                    repo.upsert_device(
                        network_id="home",
                        ieee_address="0x1",
                        friendly_name="Plug",
                        device_type="Router",
                        power_source="Mains",
                        manufacturer="NewCo",
                        model="New",
                        interview_state="successful",
                    )
                    blocked.set()
                    assert may_fail.wait(timeout=5)
                    raise RuntimeError("forced")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            done.set()

    thread = threading.Thread(target=writer)
    thread.start()
    assert blocked.wait(timeout=5)
    during = other.execute(
        "SELECT manufacturer, model FROM devices WHERE network_id = ? AND ieee_address = ?",
        ("home", "0x1"),
    ).fetchone()
    assert during["manufacturer"] == "OldCo"
    assert during["model"] == "Old"
    may_fail.set()
    assert done.wait(timeout=5)
    thread.join(timeout=5)
    after = other.execute(
        "SELECT manufacturer, model FROM devices WHERE network_id = ? AND ieee_address = ?",
        ("home", "0x1"),
    ).fetchone()
    assert after["manufacturer"] == "OldCo"
    assert after["model"] == "Old"
    assert errors == []
    other.close()


def test_competing_writers_serialize_on_repository_transaction(tmp_path: Path):
    repo, _config = _repo(tmp_path)
    a_owns = threading.Event()
    b_started = threading.Event()
    release_a = threading.Event()
    order: list[str] = []
    lock = threading.Lock()
    errors: list[BaseException] = []

    def record(label: str) -> None:
        with lock:
            order.append(label)

    def writer_a() -> None:
        try:
            with repo.transaction():
                record("a_enter")
                a_owns.set()
                assert release_a.wait(timeout=5)
                repo.upsert_device(
                    network_id="home",
                    ieee_address="0xa",
                    friendly_name="A",
                    device_type="Router",
                    power_source="Mains",
                    manufacturer=None,
                    model=None,
                    interview_state="successful",
                )
                record("a_exit")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def writer_b() -> None:
        try:
            assert a_owns.wait(timeout=5)
            b_started.set()
            with repo.transaction():
                record("b_enter")
                repo.upsert_device(
                    network_id="home",
                    ieee_address="0xb",
                    friendly_name="B",
                    device_type="Router",
                    power_source="Mains",
                    manufacturer=None,
                    model=None,
                    interview_state="successful",
                )
                record("b_exit")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t_a = threading.Thread(target=writer_a)
    t_b = threading.Thread(target=writer_b)
    t_a.start()
    t_b.start()
    assert a_owns.wait(timeout=5)
    assert b_started.wait(timeout=5)
    with lock:
        assert order == ["a_enter"]
    release_a.set()
    t_a.join(timeout=5)
    t_b.join(timeout=5)
    assert not t_a.is_alive()
    assert not t_b.is_alive()
    assert errors == []
    assert order == ["a_enter", "a_exit", "b_enter", "b_exit"]
    assert repo.get_device("home", "0xa") is not None
    assert repo.get_device("home", "0xb") is not None


def test_mqtt_callbacks_run_after_commit_and_callback_failure_keeps_data(tmp_path: Path):
    repo, config = _repo(tmp_path)
    repo.upsert_device(
        network_id="home",
        ieee_address="0x1",
        friendly_name="Plug",
        device_type="Router",
        power_source="Mains",
        manufacturer=None,
        model=None,
        interview_state="successful",
    )
    seen: list[tuple[int, int]] = []

    def health(_network_id: str, _ieee: str | None) -> None:
        other = sqlite3.connect(repo.db.path)
        try:
            seen.append(
                (
                    other.execute("SELECT COUNT(*) FROM device_snapshots").fetchone()[0],
                    other.execute("SELECT COUNT(*) FROM events").fetchone()[0],
                )
            )
        finally:
            other.close()
        raise RuntimeError("post commit failure")

    svc = MqttIngestionService(config, repo, on_health_recalc=health)
    event = NormalizedMqttEvent(
        event_type="device_payload_seen",
        network_id="home",
        title="payload",
        summary="payload",
        friendly_name="Plug",
        device_fields={"linkquality": 42},
        raw_payload_redacted='{"linkquality":42}',
    )

    with pytest.raises(RuntimeError, match="post commit failure"):
        svc.ingest(event)

    assert seen == [(1, 1)]
    assert repo.get_device("home", "0x1").linkquality == 42  # type: ignore[union-attr]
    assert len(repo.list_events("home")) == 1
