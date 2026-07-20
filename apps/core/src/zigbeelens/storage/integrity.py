"""SQLite integrity gates for storage maintenance (Track 6)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from zigbeelens.storage.repository import utc_now_iso


class StorageIntegrityError(RuntimeError):
    """Fixed safe integrity failure — no row contents or SQL details."""

    def __init__(self, kind: str, *, violation_count: int = 0) -> None:
        self.kind = kind
        self.violation_count = violation_count
        super().__init__(f"Storage integrity check failed ({kind})")


@dataclass(frozen=True)
class StorageIntegrityResult:
    kind: Literal["quick", "full", "foreign_keys"]
    ok: bool
    violation_count: int
    checked_at: str


class _ConnDatabase(Protocol):
    @property
    def conn(self) -> Any: ...


def quick_check(db: _ConnDatabase) -> StorageIntegrityResult:
    checked_at = utc_now_iso()
    try:
        row = db.conn.execute("PRAGMA quick_check").fetchone()
    except sqlite3.Error:
        raise StorageIntegrityError("quick_check") from None
    value = str(row[0]) if row is not None else ""
    ok = value == "ok"
    result = StorageIntegrityResult(
        kind="quick",
        ok=ok,
        violation_count=0 if ok else 1,
        checked_at=checked_at,
    )
    if not ok:
        raise StorageIntegrityError("quick_check", violation_count=1)
    return result


def foreign_key_check(db: _ConnDatabase) -> StorageIntegrityResult:
    checked_at = utc_now_iso()
    try:
        rows = db.conn.execute("PRAGMA foreign_key_check").fetchall()
    except sqlite3.Error:
        raise StorageIntegrityError("foreign_key_check") from None
    count = len(rows)
    result = StorageIntegrityResult(
        kind="foreign_keys",
        ok=count == 0,
        violation_count=count,
        checked_at=checked_at,
    )
    if count:
        raise StorageIntegrityError("foreign_key_check", violation_count=count)
    return result


def full_check(db: _ConnDatabase) -> StorageIntegrityResult:
    checked_at = utc_now_iso()
    try:
        rows = db.conn.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.Error:
        raise StorageIntegrityError("integrity_check") from None
    values = [str(row[0]) for row in rows]
    ok = values == ["ok"]
    result = StorageIntegrityResult(
        kind="full",
        ok=ok,
        violation_count=0 if ok else max(1, len(values)),
        checked_at=checked_at,
    )
    if not ok:
        raise StorageIntegrityError("integrity_check", violation_count=result.violation_count)
    return result


def run_startup_integrity_gates(db: _ConnDatabase) -> list[StorageIntegrityResult]:
    """Fast gates before any destructive retention."""
    return [quick_check(db), foreign_key_check(db)]
