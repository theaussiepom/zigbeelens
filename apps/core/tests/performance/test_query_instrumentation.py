from __future__ import annotations

import sqlite3
import threading

from .query_instrumentation import CountingConnection, classify_sql, measure_queries, normalize_sql


def test_counting_connection_counts_and_preserves_behavior():
    raw = sqlite3.connect(":memory:", check_same_thread=False)
    conn = CountingConnection(raw)
    conn.execute("CREATE TABLE devices (id TEXT, payload_json TEXT)")
    conn.execute("INSERT INTO devices VALUES (?, ?)", ("0xsecret", '{"token":"hidden"}'))
    assert (
        conn.execute("SELECT id FROM devices WHERE id = ?", ("0xsecret",)).fetchone()[0]
        == "0xsecret"
    )
    conn.commit()
    snap = conn.snapshot()
    assert snap.execute_count == 3
    assert snap.commit_count == 1
    assert all("0xsecret" not in stmt and "hidden" not in stmt for stmt in snap.statements)


def test_normalize_sql_collapses_values_without_parameters():
    assert (
        normalize_sql(" SELECT  *\nFROM devices WHERE ieee_address = ? ")
        == "SELECT * FROM devices WHERE ieee_address = ?"
    )
    assert "0x" not in normalize_sql("INSERT INTO events VALUES ('0xabc', 'payload')")


def test_classification_representative_shapes():
    cases = {
        "SELECT * FROM networks": "read.networks",
        "INSERT INTO devices(id) VALUES (?)": "write.devices",
        "UPDATE device_current_state SET battery=?": "write.device_current_state",
        "DELETE FROM incident_devices WHERE incident_id=?": "write.incident_devices",
        "SELECT * FROM topology_links": "read.topology_links",
        "BEGIN IMMEDIATE": "transaction.control",
        "COMMIT": "transaction.control",
        "ROLLBACK": "transaction.control",
        "SELECT 1": "other",
    }
    for sql, category in cases.items():
        assert classify_sql(sql) == category


def test_begin_immediate_excluded_from_execute_count():
    raw = sqlite3.connect(":memory:")
    conn = CountingConnection(raw)
    conn.execute("CREATE TABLE devices (id TEXT)")
    conn.reset()
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("INSERT INTO devices VALUES (?)", ("1",))
    snap = conn.snapshot()
    assert snap.execute_count == 1
    assert snap.category_counts.get("transaction.control", 0) == 0
    assert snap.category_counts.get("other", 0) == 0
    assert snap.category_counts["write.devices"] == 1


def test_executemany_commit_rollback_reset_and_delta_scope():
    raw = sqlite3.connect(":memory:")
    conn = CountingConnection(raw)
    conn.execute("CREATE TABLE metric_samples (v INTEGER)")
    conn.reset()
    with measure_queries(conn.stats) as box:
        conn.executemany("INSERT INTO metric_samples VALUES (?)", [(1,), (2,)])
        conn.rollback()
    measurement = box["measurement"]
    assert measurement.executemany_count == 1
    assert measurement.rollback_count == 1
    assert measurement.category_counts["write.metric_samples"] == 1
    conn.reset()
    assert conn.snapshot().execute_count == 0


def test_thread_safety_counts_all_calls():
    raw = sqlite3.connect(":memory:", check_same_thread=False)
    conn = CountingConnection(raw)
    conn.execute("CREATE TABLE events (id INTEGER)")

    def worker(offset: int):
        for idx in range(10):
            conn.execute("INSERT INTO events VALUES (?)", (offset + idx,))

    threads = [threading.Thread(target=worker, args=(i * 10,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert conn.snapshot().execute_count == 41
