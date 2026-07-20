"""True read-only SQLite openers for storage check and dry-run (Track 6)."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from urllib.parse import quote

from zigbeelens.db.locked_connection import LockedSQLiteConnection
from zigbeelens.db.retention_time import register_retention_sql_functions


def sqlite_readonly_uri(path: Path) -> str:
    """Build a URI-safe ``file:…?mode=ro`` connection string."""
    resolved = path.expanduser().resolve()
    return f"file:{quote(resolved.as_posix())}?mode=ro"


class ReadOnlyDatabase:
    """Existing-database reader that never creates files or enables WAL."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        if not self.path.is_file():
            raise FileNotFoundError(str(self.path))
        uri = sqlite_readonly_uri(self.path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        register_retention_sql_functions(self._conn)
        try:
            self._conn.execute("PRAGMA query_only = ON")
        except sqlite3.Error:
            pass
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._locked = LockedSQLiteConnection(self._conn, self._lock)
        self.migration_version = self._read_schema_version()
    @property
    def conn(self) -> LockedSQLiteConnection:
        return self._locked

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _read_schema_version(self) -> int:
        try:
            row = self._conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        except sqlite3.Error:
            return 0
        if row is None or row[0] is None:
            return 0
        return int(row[0])


def read_schema_version(path: Path) -> int:
    db = ReadOnlyDatabase(path)
    try:
        return db.migration_version
    finally:
        db.close()
