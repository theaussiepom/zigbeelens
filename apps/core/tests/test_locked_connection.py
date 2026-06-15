"""LockedCursor and DB lock release tests."""

from __future__ import annotations

import concurrent.futures
import sqlite3
import threading

from zigbeelens.db.connection import Database
from zigbeelens.db.locked_connection import LockedSQLiteConnection


def test_rowcount_releases_lock(tmp_path):
    conn = sqlite3.connect(tmp_path / "rowcount.sqlite")
    conn.row_factory = sqlite3.Row
    lock = threading.RLock()
    locked = LockedSQLiteConnection(conn, lock)
    locked.execute(
        """
        CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)
        """
    ).fetchall()
    locked.commit()

    cur = locked.execute("INSERT INTO items (name) VALUES (?)", ("a",))
    assert cur.rowcount == 1
    locked.commit()

    cur2 = locked.execute("DELETE FROM items WHERE name = ?", ("a",))
    assert cur2.rowcount == 1
    locked.commit()

    count_cur = locked.execute("SELECT COUNT(*) FROM items")
    assert int(count_cur.fetchone()[0]) == 0


def test_iteration_releases_lock(tmp_path):
    conn = sqlite3.connect(tmp_path / "iter.sqlite")
    conn.row_factory = sqlite3.Row
    lock = threading.RLock()
    locked = LockedSQLiteConnection(conn, lock)
    locked.execute("CREATE TABLE t (v INTEGER)").fetchall()
    locked.execute("INSERT INTO t (v) VALUES (1)").fetchall()
    locked.execute("INSERT INTO t (v) VALUES (2)").fetchall()
    locked.commit()

    values = [row[0] for row in locked.execute("SELECT v FROM t ORDER BY v")]
    assert values == [1, 2]
    assert int(locked.execute("SELECT COUNT(*) FROM t").fetchone()[0]) == 2


def test_delete_report_does_not_block_follow_up_queries(mock_client):
    created = mock_client.post("/api/reports", json={"format": "json"}).json()
    res = mock_client.delete(f"/api/reports/{created['id']}")
    assert res.status_code == 200
    assert res.json()["deleted"] is True
    assert mock_client.get("/api/reports").status_code == 200


def test_concurrent_reads_after_delete(tmp_path):
    db = Database(tmp_path / "after-delete.sqlite")
    db.migrate()
    db.conn.execute(
        """
        INSERT INTO networks (id, name, base_topic, bridge_state, created_at, updated_at)
        VALUES ('home', 'Home', 'zigbee2mqtt', 'online', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """
    ).fetchall()
    db.conn.commit()

    cur = db.conn.execute("DELETE FROM networks WHERE id = 'home'")
    assert cur.rowcount == 1
    db.conn.commit()

    def read_networks() -> int:
        c = db.conn.execute("SELECT COUNT(*) FROM networks")
        return int(c.fetchone()[0])

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: read_networks(), range(20)))

    assert all(r == 0 for r in results)
