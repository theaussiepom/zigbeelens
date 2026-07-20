"""Local storage CLI commands (Track 6)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from zigbeelens.config import load_effective_config, resolve_config_path
from zigbeelens.db.connection import Database
from zigbeelens.storage.backup import StorageBackupError, backup_sqlite_database
from zigbeelens.storage.integrity import (
    StorageIntegrityError,
    foreign_key_check,
    full_check,
    quick_check,
)
from zigbeelens.storage.maintenance import run_storage_maintenance
from zigbeelens.storage.repository import Repository


def _open_db_readonlyish(path: Path) -> Database:
    """Open an existing database without running migrations."""
    if not path.exists():
        raise FileNotFoundError(str(path))
    return Database(path)


def _resolve_db_path(args: argparse.Namespace) -> Path:
    if getattr(args, "database", None):
        return Path(args.database).expanduser().resolve()
    config_path = args.config or str(resolve_config_path())
    cfg = load_effective_config(config_path)
    return Path(cfg.storage.path).expanduser().resolve()


def cmd_storage_check(args: argparse.Namespace) -> int:
    path = _resolve_db_path(args)
    db = _open_db_readonlyish(path)
    try:
        results = []
        if args.full:
            results.append(full_check(db))
        else:
            results.append(quick_check(db))
        results.append(foreign_key_check(db))
        payload = {
            "database": path.name,
            "ok": all(item.ok for item in results),
            "checks": [
                {
                    "kind": item.kind,
                    "ok": item.ok,
                    "violation_count": item.violation_count,
                    "checked_at": item.checked_at,
                }
                for item in results
            ],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["ok"] else 1
    except StorageIntegrityError as exc:
        print(
            json.dumps(
                {
                    "database": path.name,
                    "ok": False,
                    "error_code": exc.kind,
                    "violation_count": exc.violation_count,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    finally:
        db.close()


def cmd_storage_backup(args: argparse.Namespace) -> int:
    try:
        result = backup_sqlite_database(
            output=args.output,
            config_path=args.config,
            database=args.database,
            overwrite=bool(args.overwrite),
        )
    except StorageBackupError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "destination": result.destination,
                "bytes": result.bytes,
                "schema_version": result.schema_version,
                "created_at": result.created_at,
                "checksum_sha256": result.checksum_sha256,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def cmd_storage_maintenance(args: argparse.Namespace) -> int:
    if not args.dry_run and not args.apply:
        print("error: require --dry-run or --apply", file=sys.stderr)
        return 2
    config_path = args.config or str(resolve_config_path())
    cfg = load_effective_config(config_path)
    if args.database:
        cfg = cfg.model_copy(
            update={"storage": cfg.storage.model_copy(update={"path": str(Path(args.database))})}
        )
    db = Database(cfg.storage.path)
    # Do not migrate here for dry-run/apply against an existing DB; assume migrated.
    # Opening via Database is fine; callers should use a Core-managed DB.
    try:
        # Ensure schema present for tests; migrate is safe/idempotent.
        db.migrate()
        repo = Repository(db)
        result = run_storage_maintenance(
            repo,
            cfg,
            dry_run=bool(args.dry_run),
            persist_status=bool(args.apply),
        )
        print(
            json.dumps(
                {
                    "ok": result.success,
                    "dry_run": bool(args.dry_run),
                    "total_rows_deleted": result.total_rows_deleted,
                    "rows_deleted_by_category": result.rows_deleted_by_category,
                    "more_work_pending": result.more_work_pending,
                    "duration_ms": result.duration_ms,
                    "error_code": result.error_code,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if result.success else 1
    finally:
        db.close()


def add_storage_subparser(subparsers: argparse._SubParsersAction) -> None:
    storage = subparsers.add_parser("storage", help="Storage integrity, backup, and maintenance")
    storage_sub = storage.add_subparsers(dest="storage_command", required=True)

    check = storage_sub.add_parser("check", help="Run SQLite integrity checks")
    check.add_argument("--config", dest="config", default=None)
    check.add_argument("--database", dest="database", default=None)
    check.add_argument("--full", action="store_true", help="Run full integrity_check")
    check.set_defaults(func=cmd_storage_check)

    backup = storage_sub.add_parser("backup", help="Create an online SQLite backup")
    backup.add_argument("--config", dest="config", default=None)
    backup.add_argument("--database", dest="database", default=None)
    backup.add_argument("--output", required=True, help="Destination .sqlite path")
    backup.add_argument("--overwrite", action="store_true")
    backup.set_defaults(func=cmd_storage_backup)

    maintenance = storage_sub.add_parser("maintenance", help="Preview or apply retention")
    maintenance.add_argument("--config", dest="config", default=None)
    maintenance.add_argument("--database", dest="database", default=None)
    mode = maintenance.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    maintenance.set_defaults(func=cmd_storage_maintenance)
