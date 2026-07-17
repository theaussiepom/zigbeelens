"""SQLite connection and migration runner."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator
from importlib import resources
from pathlib import Path

from zigbeelens.db.locked_connection import LockedSQLiteConnection


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._locked = LockedSQLiteConnection(self._conn, self._lock)
        self.migration_version = 0

    @property
    def conn(self) -> LockedSQLiteConnection:
        return self._locked

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Own one repository write transaction using BEGIN IMMEDIATE."""
        with self._locked.transaction():
            yield

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def migrate(self) -> int:
        """Apply pending migrations idempotently. Returns latest schema version."""
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            applied = self._applied_versions_unlocked()
            migrations = self._load_migrations()
            newly_applied: set[int] = set()
            for version, sql in migrations:
                if version in applied:
                    continue
                self._conn.executescript(sql)
                self._conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES (?)",
                    (version,),
                )
                self._conn.commit()
                applied.add(version)
                newly_applied.add(version)
            if 11 in newly_applied or (
                11 in applied
                and self._needs_incident_networks_multi_backfill_unlocked()
            ):
                from zigbeelens.diagnostics.incidents.network_identity import (
                    backfill_incident_networks_from_dedup_keys,
                )

                backfill_incident_networks_from_dedup_keys(self._conn)
                self._conn.commit()
            self.migration_version = max(applied, default=0)
            return self.migration_version

    def _needs_incident_networks_multi_backfill_unlocked(self) -> bool:
        """True when multi-network incidents may still lack incident_networks rows."""
        try:
            cur = self._conn.execute(
                """
                SELECT 1
                FROM incidents i
                WHERE i.incident_type = 'multi_network_instability'
                  AND NOT EXISTS (
                    SELECT 1 FROM incident_networks n WHERE n.incident_id = i.id
                  )
                LIMIT 1
                """
            )
        except sqlite3.OperationalError:
            return False
        return cur.fetchone() is not None

    def _applied_versions_unlocked(self) -> set[int]:
        cur = self._conn.execute("SELECT version FROM schema_migrations")
        return {int(row[0]) for row in cur.fetchall()}

    def _load_migrations(self) -> list[tuple[int, str]]:
        files: list[tuple[int, str]] = []
        migrations_pkg = resources.files("zigbeelens.db.migrations")
        for item in sorted(migrations_pkg.iterdir()):
            if item.name.endswith(".sql"):
                version = int(item.name.split("_")[0])
                files.append((version, item.read_text(encoding="utf-8")))
        files.sort(key=lambda x: x[0])
        return files

    def ping(self) -> bool:
        try:
            with self._lock:
                self._conn.execute("SELECT 1")
            return True
        except sqlite3.Error:
            return False
