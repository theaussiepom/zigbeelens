"""PR #79: BaseException-safe SQLite lock and transaction-setup cleanup."""

from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import pytest

from zigbeelens.db.locked_connection import LockedSQLiteConnection


class _Interrupt(BaseException):
    """Deterministic BaseException sentinel (not KeyboardInterrupt)."""


class _ConnProxy:
    """Delegating connection wrapper for deterministic failure injection."""

    def __init__(
        self,
        real: sqlite3.Connection,
        *,
        on_execute: Callable[[str, Any], BaseException | Exception | None] | None = None,
        on_commit: Callable[[], BaseException | Exception | None] | None = None,
    ) -> None:
        self._real = real
        self._on_execute = on_execute
        self._on_commit = on_commit

    def execute(self, sql: str, params: Any = ()) -> Any:
        if self._on_execute is not None:
            err = self._on_execute(sql, params)
            if err is not None:
                raise err
        return self._real.execute(sql, params)

    def commit(self) -> None:
        if self._on_commit is not None:
            err = self._on_commit()
            if err is not None:
                raise err
        return self._real.commit()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def _locked(tmp_path, name: str = "lock.sqlite") -> LockedSQLiteConnection:
    conn = sqlite3.connect(tmp_path / name, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()
    return LockedSQLiteConnection(conn, threading.RLock())


def _assert_usable(locked: LockedSQLiteConnection) -> None:
    assert locked.transaction_depth == 0
    assert not locked._rollback_only()
    locked.execute("INSERT INTO items (name) VALUES (?)", ("ok",)).fetchall()
    locked.commit()
    assert int(locked.execute("SELECT COUNT(*) FROM items").fetchone()[0]) >= 1
    with locked.transaction():
        locked.execute("INSERT INTO items (name) VALUES (?)", ("tx",)).fetchall()
    assert locked.transaction_depth == 0


def _assert_other_thread_can_acquire(locked: LockedSQLiteConnection) -> None:
    acquired = threading.Event()

    def worker() -> None:
        locked._lock.acquire()
        try:
            acquired.set()
        finally:
            locked._lock.release()

    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(worker)
        fut.result(timeout=2)
    assert acquired.is_set()


def test_execute_releases_lock_on_baseexception(tmp_path):
    locked = _locked(tmp_path)
    locked._conn = _ConnProxy(
        locked._conn,
        on_execute=lambda sql, params: _Interrupt("execute-base"),
    )
    with pytest.raises(_Interrupt, match="execute-base"):
        locked.execute("SELECT 1")
    locked._conn = locked._conn._real  # type: ignore[attr-defined]
    _assert_usable(locked)
    _assert_other_thread_can_acquire(locked)


def test_execute_releases_lock_on_exception(tmp_path):
    locked = _locked(tmp_path)
    locked._conn = _ConnProxy(
        locked._conn,
        on_execute=lambda sql, params: RuntimeError("execute-exc"),
    )
    with pytest.raises(RuntimeError, match="execute-exc"):
        locked.execute("SELECT 1")
    locked._conn = locked._conn._real  # type: ignore[attr-defined]
    _assert_usable(locked)
    _assert_other_thread_can_acquire(locked)


def test_begin_immediate_baseexception_releases_lock(tmp_path):
    locked = _locked(tmp_path)
    commits = {"n": 0}
    rollbacks = {"n": 0}
    locked.set_transaction_observer(
        on_commit=lambda: commits.__setitem__("n", commits["n"] + 1),
        on_rollback=lambda: rollbacks.__setitem__("n", rollbacks["n"] + 1),
    )

    def on_execute(sql: str, params: Any) -> BaseException | None:
        if "BEGIN IMMEDIATE" in str(sql).upper():
            return _Interrupt("begin-base")
        return None

    locked._conn = _ConnProxy(locked._conn, on_execute=on_execute)
    with pytest.raises(_Interrupt, match="begin-base"):
        with locked.transaction():
            pass
    locked._conn = locked._conn._real  # type: ignore[attr-defined]
    assert locked.transaction_depth == 0
    assert not locked._rollback_only()
    assert commits["n"] == 0
    assert rollbacks["n"] == 0
    _assert_usable(locked)
    _assert_other_thread_can_acquire(locked)


def test_begin_immediate_exception_releases_lock(tmp_path):
    locked = _locked(tmp_path)

    def on_execute(sql: str, params: Any) -> Exception | None:
        if "BEGIN IMMEDIATE" in str(sql).upper():
            return RuntimeError("begin-exc")
        return None

    locked._conn = _ConnProxy(locked._conn, on_execute=on_execute)
    with pytest.raises(RuntimeError, match="begin-exc"):
        with locked.transaction():
            pass
    locked._conn = locked._conn._real  # type: ignore[attr-defined]
    assert locked.transaction_depth == 0
    assert not locked._rollback_only()
    _assert_usable(locked)
    _assert_other_thread_can_acquire(locked)


def test_setup_baseexception_after_begin_rolls_back_and_releases(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    locked = _locked(tmp_path)
    rollbacks = {"n": 0}
    locked.set_transaction_observer(
        on_rollback=lambda: rollbacks.__setitem__("n", rollbacks["n"] + 1),
    )
    real_set_depth = LockedSQLiteConnection._set_depth

    def boom_depth(self: LockedSQLiteConnection, depth: int) -> None:
        if depth == 1 and self._depth() == 0:
            raise _Interrupt("after-begin")
        return real_set_depth(self, depth)

    monkeypatch.setattr(LockedSQLiteConnection, "_set_depth", boom_depth)
    with pytest.raises(_Interrupt, match="after-begin"):
        with locked.transaction():
            pass
    monkeypatch.undo()
    assert locked.transaction_depth == 0
    assert not locked._rollback_only()
    assert rollbacks["n"] == 1
    _assert_usable(locked)
    _assert_other_thread_can_acquire(locked)


def test_no_double_release_after_execute_baseexception(tmp_path):
    locked = _locked(tmp_path)
    locked._conn = _ConnProxy(
        locked._conn,
        on_execute=lambda sql, params: _Interrupt("once"),
    )
    with pytest.raises(_Interrupt):
        locked.execute("SELECT 1")
    locked._conn = locked._conn._real  # type: ignore[attr-defined]
    assert locked._lock.acquire(blocking=False)
    locked._lock.release()
    _assert_usable(locked)


def test_begin_then_raise_detects_physical_transaction_and_rolls_back(tmp_path):
    """BEGIN that takes effect before execute() raises must still clean up."""
    locked = _locked(tmp_path)
    rollbacks = {"n": 0}
    locked.set_transaction_observer(
        on_rollback=lambda: rollbacks.__setitem__("n", rollbacks["n"] + 1),
    )
    real = locked._conn

    class _BeginThenRaise:
        def __init__(self, conn: sqlite3.Connection) -> None:
            self._real = conn

        def execute(self, sql: str, params: Any = ()) -> Any:
            if "BEGIN IMMEDIATE" in str(sql).upper():
                self._real.execute(sql, params)
                assert self._real.in_transaction
                raise _Interrupt("begin-then-raise")
            return self._real.execute(sql, params)

        def __getattr__(self, name: str) -> Any:
            return getattr(self._real, name)

    locked._conn = _BeginThenRaise(real)  # type: ignore[assignment]
    with pytest.raises(_Interrupt, match="begin-then-raise"):
        with locked.transaction():
            pass
    locked._conn = real
    assert not real.in_transaction
    assert locked.transaction_depth == 0
    assert not locked._rollback_only()
    assert rollbacks["n"] == 1
    _assert_other_thread_can_acquire(locked)
    _assert_usable(locked)


def test_failed_begin_that_never_starts_skips_rollback_observer(tmp_path):
    locked = _locked(tmp_path)
    rollbacks = {"n": 0}
    locked.set_transaction_observer(
        on_rollback=lambda: rollbacks.__setitem__("n", rollbacks["n"] + 1),
    )

    def on_execute(sql: str, params: Any) -> BaseException | None:
        if "BEGIN IMMEDIATE" in str(sql).upper():
            return _Interrupt("begin-never-started")
        return None

    locked._conn = _ConnProxy(locked._conn, on_execute=on_execute)
    with pytest.raises(_Interrupt, match="begin-never-started"):
        with locked.transaction():
            pass
    locked._conn = locked._conn._real  # type: ignore[attr-defined]
    assert not locked._conn.in_transaction
    assert locked.transaction_depth == 0
    assert not locked._rollback_only()
    assert rollbacks["n"] == 0
    _assert_usable(locked)
