"""Tests for thread-safe SQLite access."""

from __future__ import annotations

import concurrent.futures

from zigbeelens.db.connection import Database


def test_concurrent_dashboard_reads(tmp_path):
    db_path = tmp_path / "concurrent.sqlite"
    db = Database(db_path)
    db.migrate()
    db.conn.execute(
        """
        INSERT INTO networks (id, name, base_topic, bridge_state, created_at, updated_at)
        VALUES ('home', 'Home', 'zigbee2mqtt', 'online', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """
    ).fetchall()
    db.conn.commit()

    def read_networks() -> int:
        cur = db.conn.execute("SELECT COUNT(*) FROM networks")
        return int(cur.fetchone()[0])

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: read_networks(), range(40)))

    assert all(r == 1 for r in results)


def test_concurrent_api_dashboard_and_devices(live_client):
    import concurrent.futures

    client = live_client

    def hit(path: str) -> int:
        return client.get(path).status_code

    paths = ["/api/dashboard", "/api/devices", "/api/incidents", "/api/reports"] * 5
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        codes = list(pool.map(hit, paths))

    assert all(code == 200 for code in codes)
