"""Thread-safe wrappers for SQLite connections used from async HTTP handlers."""

from __future__ import annotations

import sqlite3
import threading
from typing import Any, Iterator


class LockedCursor:
    """Cursor wrapper that holds the DB lock until results are fetched."""

    __slots__ = ("_cursor", "_lock", "_released")

    def __init__(self, cursor: sqlite3.Cursor, lock: threading.RLock) -> None:
        self._cursor = cursor
        self._lock = lock
        self._released = False

    def _release(self) -> None:
        if not self._released:
            self._released = True
            self._lock.release()

    def fetchone(self) -> sqlite3.Row | None:
        try:
            return self._cursor.fetchone()
        finally:
            self._release()

    def fetchall(self) -> list[sqlite3.Row]:
        try:
            return self._cursor.fetchall()
        finally:
            self._release()

    def fetchmany(self, size: int | None = None) -> list[sqlite3.Row]:
        try:
            if size is None:
                return self._cursor.fetchmany()
            return self._cursor.fetchmany(size)
        finally:
            self._release()

    @property
    def rowcount(self) -> int:
        try:
            return self._cursor.rowcount
        finally:
            self._release()

    def __iter__(self) -> Iterator[sqlite3.Row]:
        try:
            yield from self._cursor
        finally:
            self._release()

    def close(self) -> None:
        self._release()

    def __enter__(self) -> LockedCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        self._release()

    def __del__(self) -> None:
        self._release()


class LockedSQLiteConnection:
    """Serialize SQLite access — safe for concurrent API requests."""

    __slots__ = ("_conn", "_lock")

    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock) -> None:
        self._conn = conn
        self._lock = lock

    def execute(self, sql: str, params: Any = ()) -> LockedCursor:
        self._lock.acquire()
        try:
            return LockedCursor(self._conn.execute(sql, params), self._lock)
        except Exception:
            self._lock.release()
            raise

    def executescript(self, sql_script: str) -> None:
        with self._lock:
            self._conn.executescript(sql_script)

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._conn, name)
        if not callable(attr):
            return attr

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            with self._lock:
                return attr(*args, **kwargs)

        return wrapped
