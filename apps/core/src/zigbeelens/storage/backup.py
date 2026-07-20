"""Online SQLite backup via the SQLite backup API (Track 6)."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from zigbeelens.storage.repository import utc_now_iso

BackupProgress = Callable[[int, int], None]


@dataclass(frozen=True)
class StorageBackupResult:
    destination: str
    bytes: int
    schema_version: int
    created_at: str
    checksum_sha256: str


class StorageBackupError(RuntimeError):
    """Safe backup failure without row contents or credentials."""


def _resolve_source_path(
    *,
    config_path: str | None,
    database: str | None,
) -> Path:
    if database:
        return Path(database).expanduser().resolve()
    if config_path:
        from zigbeelens.config import load_effective_config

        cfg = load_effective_config(config_path)
        return Path(cfg.storage.path).expanduser().resolve()
    from zigbeelens.config import load_effective_config, resolve_config_path

    cfg = load_effective_config(str(resolve_config_path()))
    return Path(cfg.storage.path).expanduser().resolve()


def _sqlite_uri(path: Path, *, mode: str | None = None) -> str:
    uri = f"file:{quote(path.resolve().as_posix())}"
    if mode:
        uri = f"{uri}?mode={mode}"
    return uri


def _same_file(a: Path, b: Path) -> bool:
    try:
        a_stat = os.lstat(a)
        b_stat = os.lstat(b)
    except OSError:
        return False
    return a_stat.st_ino == b_stat.st_ino and a_stat.st_dev == b_stat.st_dev


def _destination_lexists(path: Path) -> bool:
    try:
        os.lstat(path)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return True


def _validate_backup_file(path: Path) -> int:
    """Validate temp backup without mutating journal mode or leaving WAL files."""
    conn = sqlite3.connect(_sqlite_uri(path, mode="ro"), uri=True)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        quick = conn.execute("PRAGMA quick_check").fetchone()
        if quick is None or str(quick[0]) != "ok":
            raise StorageBackupError("backup validation failed")
        fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_rows:
            raise StorageBackupError("backup validation failed")
        row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return int(row[0] or 0) if row else 0
    except StorageBackupError:
        raise
    except sqlite3.Error:
        raise StorageBackupError("backup validation failed") from None
    finally:
        conn.close()


def backup_sqlite_database(
    *,
    output: str | Path,
    config_path: str | None = None,
    database: str | None = None,
    overwrite: bool = False,
    pages_per_step: int = 64,
    progress: BackupProgress | None = None,
) -> StorageBackupResult:
    source = _resolve_source_path(config_path=config_path, database=database)
    if not source.exists():
        raise StorageBackupError("source database does not exist")

    # Resolve/canonicalize parent only; retain the requested basename.
    raw_destination = Path(output).expanduser()
    parent = raw_destination.parent
    if str(parent) in ("", "."):
        parent = Path.cwd()
    parent = parent.resolve()
    destination = parent / raw_destination.name

    forbidden = {
        source.resolve(),
        Path(str(source.resolve()) + "-wal"),
        Path(str(source.resolve()) + "-shm"),
    }
    if destination.resolve() in forbidden or any(
        _same_file(destination, item) for item in forbidden if item.exists() or _destination_lexists(item)
    ):
        raise StorageBackupError("destination must not equal the source database or WAL/SHM files")
    if _same_file(destination, source):
        raise StorageBackupError("destination must not equal the source database or WAL/SHM files")

    if _destination_lexists(destination) and not overwrite:
        raise StorageBackupError("destination exists; pass --overwrite to replace it")

    # Refuse hard-link / same-inode destinations even when overwrite is set.
    if _destination_lexists(destination) and _same_file(destination, source):
        raise StorageBackupError("destination must not equal the source database or WAL/SHM files")
    for sibling in (Path(str(source) + "-wal"), Path(str(source) + "-shm")):
        if _destination_lexists(destination) and _same_file(destination, sibling):
            raise StorageBackupError(
                "destination must not equal the source database or WAL/SHM files"
            )

    parent.mkdir(parents=True, exist_ok=True)
    created_at = utc_now_iso()
    tmp_name = f".zigbeelens-backup-{uuid.uuid4().hex}.tmp"
    tmp_path: Path | None = parent / tmp_name

    source_conn: sqlite3.Connection | None = None
    dest_conn: sqlite3.Connection | None = None
    try:
        assert tmp_path is not None
        fd = os.open(tmp_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)

        source_conn = sqlite3.connect(
            _sqlite_uri(source, mode="ro"), uri=True, check_same_thread=False
        )
        dest_conn = sqlite3.connect(str(tmp_path), check_same_thread=False)

        def _step(status: int, remaining: int, total: int) -> None:
            if progress is not None:
                progress(remaining, total)

        # Prefer progress callback when available (Python 3.11+).
        try:
            source_conn.backup(dest_conn, pages=pages_per_step, progress=_step)
        except TypeError:
            source_conn.backup(dest_conn, pages=pages_per_step)
        dest_conn.commit()
        dest_conn.close()
        dest_conn = None
        source_conn.close()
        source_conn = None

        schema_version = _validate_backup_file(tmp_path)

        with open(tmp_path, "rb") as handle:
            os.fsync(handle.fileno())

        os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)

        digest = hashlib.sha256()
        with open(tmp_path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        size = tmp_path.stat().st_size
        checksum = digest.hexdigest()

        # Atomically replace the destination entry itself (symlink-safe).
        os.replace(tmp_path, destination)
        tmp_path = None

        try:
            dir_fd = os.open(str(parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass

        return StorageBackupResult(
            destination=str(destination),
            bytes=size,
            schema_version=schema_version,
            created_at=created_at,
            checksum_sha256=checksum,
        )
    except StorageBackupError:
        raise
    except Exception:
        raise StorageBackupError("backup failed") from None
    finally:
        if source_conn is not None:
            source_conn.close()
        if dest_conn is not None:
            dest_conn.close()
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
