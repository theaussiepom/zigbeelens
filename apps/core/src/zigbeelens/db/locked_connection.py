"""Thread-safe wrappers for SQLite connections used from async HTTP handlers."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Callable, Iterator


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

    __slots__ = ("_conn", "_lock", "_state", "_on_physical_commit", "_on_physical_rollback")

    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock) -> None:
        self._conn = conn
        self._lock = lock
        self._state = threading.local()
        self._on_physical_commit: Callable[[], None] | None = None
        self._on_physical_rollback: Callable[[], None] | None = None

    def set_transaction_observer(
        self,
        *,
        on_commit: Callable[[], None] | None = None,
        on_rollback: Callable[[], None] | None = None,
    ) -> None:
        self._on_physical_commit = on_commit
        self._on_physical_rollback = on_rollback

    def _depth(self) -> int:
        return int(getattr(self._state, "depth", 0))

    def _set_depth(self, depth: int) -> None:
        self._state.depth = depth

    @property
    def transaction_depth(self) -> int:
        return self._depth()

    def _rollback_only(self) -> bool:
        return bool(getattr(self._state, "rollback_only", False))

    def execute(self, sql: str, params: Any = ()) -> LockedCursor:
        # PR #79: release for Exception and BaseException so KeyboardInterrupt /
        # SystemExit / GeneratorExit cannot leave the shared RLock held.
        self._lock.acquire()
        try:
            return LockedCursor(self._conn.execute(sql, params), self._lock)
        except BaseException:
            self._lock.release()
            raise

    def executescript(self, sql_script: str) -> None:
        with self._lock:
            if self._depth() > 0:
                raise RuntimeError("executescript is not allowed inside a repository transaction")
            self._conn.executescript(sql_script)

    def commit(self) -> None:
        with self._lock:
            if self._depth() > 0:
                return
            self._conn.commit()
            if self._on_physical_commit:
                self._on_physical_commit()

    def rollback(self) -> None:
        with self._lock:
            if self._depth() > 0:
                self._state.rollback_only = True
                return
            self._conn.rollback()
            if self._on_physical_rollback:
                self._on_physical_rollback()

    def _notify_physical_rollback(self) -> None:
        if self._on_physical_rollback:
            self._on_physical_rollback()

    def _notify_physical_commit(self) -> None:
        if self._on_physical_commit:
            self._on_physical_commit()

    def _physical_rollback(self) -> None:
        self._conn.rollback()
        self._notify_physical_rollback()

    def _physical_commit_or_recover(self) -> None:
        """Attempt physical COMMIT; roll back and re-raise if COMMIT itself fails."""
        try:
            self._conn.commit()
        except BaseException as commit_exc:
            try:
                self._conn.rollback()
            except BaseException:
                pass
            try:
                self._notify_physical_rollback()
            except BaseException:
                pass
            raise commit_exc
        self._notify_physical_commit()

    def _cleanup_failed_begin(self, *, began: bool) -> None:
        """Reset TLS and release the lock after a failed outermost BEGIN/setup."""
        if began:
            try:
                self._conn.rollback()
            except BaseException:
                pass
            try:
                self._notify_physical_rollback()
            except BaseException:
                pass
        self._state.rollback_only = False
        self._set_depth(0)
        self._lock.release()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Join or own a BEGIN IMMEDIATE transaction.

        Nested contexts join the outer transaction. Repository commit() calls are
        deferred while a transaction is active. Calling rollback() in a context
        marks the outer transaction rollback-only; the outermost exit performs
        the physical rollback and raises RuntimeError.
        """
        outermost = self._depth() == 0
        if outermost:
            # One cleanup-safe setup unit: lock + rollback-only init + BEGIN + depth.
            self._lock.acquire()
            began = False
            was_in_transaction = False
            try:
                self._state.rollback_only = False
                # Detect BEGIN-then-raise: execute() may start a transaction even
                # when it re-raises before returning (PR #79 corrective).
                was_in_transaction = bool(self._conn.in_transaction)
                self._conn.execute("BEGIN IMMEDIATE")
                began = True
                self._set_depth(1)
            except BaseException:
                began_here = began or (
                    not was_in_transaction and bool(self._conn.in_transaction)
                )
                self._cleanup_failed_begin(began=began_here)
                raise
        else:
            self._lock.acquire()
            self._set_depth(self._depth() + 1)

        failed = False
        try:
            yield
        except BaseException:
            failed = True
            self._state.rollback_only = True
            raise
        finally:
            depth = self._depth() - 1
            self._set_depth(depth)
            try:
                if outermost:
                    if self._rollback_only():
                        self._physical_rollback()
                        if not failed:
                            raise RuntimeError("Transaction rolled back")
                    else:
                        self._physical_commit_or_recover()
            finally:
                if outermost:
                    self._state.rollback_only = False
                    self._set_depth(0)
                self._lock.release()

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._conn, name)
        if not callable(attr):
            return attr

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            with self._lock:
                return attr(*args, **kwargs)

        return wrapped
