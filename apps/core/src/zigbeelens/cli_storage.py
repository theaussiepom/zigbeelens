"""Local storage CLI commands (Track 6)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from zigbeelens.config import ConfigError, load_effective_config, resolve_config_path
from zigbeelens.db.connection import Database
from zigbeelens.storage.backup import StorageBackupError, backup_sqlite_database
from zigbeelens.storage.integrity import (
    StorageIntegrityError,
    foreign_key_check,
    full_check,
    quick_check,
)
from zigbeelens.storage.maintenance import run_storage_maintenance
from zigbeelens.storage.readonly import ReadOnlyDatabase
from zigbeelens.storage.repository import Repository
from zigbeelens.storage.retention_policy import CURRENT_SCHEMA_VERSION


def _resolve_config_path(args: argparse.Namespace) -> str:
    return getattr(args, "config", None) or str(resolve_config_path())


def _resolve_db_path(args: argparse.Namespace) -> Path:
    if getattr(args, "database", None):
        return Path(args.database).expanduser().resolve()
    cfg = load_effective_config(_resolve_config_path(args))
    return Path(cfg.storage.path).expanduser().resolve()


def _print_error(payload: dict) -> int:
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1


def cmd_storage_check(args: argparse.Namespace) -> int:
    try:
        path = _resolve_db_path(args)
    except (ConfigError, OSError, ValueError) as exc:
        return _print_error({"ok": False, "error_code": "config_error", "error": str(exc)})
    try:
        db = ReadOnlyDatabase(path)
    except FileNotFoundError:
        return _print_error(
            {"ok": False, "error_code": "missing_database", "database": path.name}
        )
    except Exception:
        return _print_error(
            {"ok": False, "error_code": "open_failed", "database": path.name}
        )
    try:
        results = []
        if args.full:
            results.append(full_check(db))  # type: ignore[arg-type]
        else:
            results.append(quick_check(db))  # type: ignore[arg-type]
        results.append(foreign_key_check(db))  # type: ignore[arg-type]
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
        return _print_error(
            {
                "database": path.name,
                "ok": False,
                "error_code": exc.kind,
                "violation_count": exc.violation_count,
            }
        )
    except Exception:
        return _print_error(
            {"database": path.name, "ok": False, "error_code": "check_failed"}
        )
    finally:
        db.close()


def cmd_storage_backup(args: argparse.Namespace) -> int:
    try:
        result = backup_sqlite_database(
            output=args.output,
            config_path=getattr(args, "config", None),
            database=args.database,
            overwrite=bool(args.overwrite),
        )
    except StorageBackupError as exc:
        return _print_error({"ok": False, "error": str(exc)})
    except (ConfigError, OSError, ValueError) as exc:
        return _print_error({"ok": False, "error_code": "config_error", "error": str(exc)})
    except Exception:
        return _print_error({"ok": False, "error_code": "backup_failed"})
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
    try:
        config_path = _resolve_config_path(args)
        cfg = load_effective_config(config_path)
        if args.database:
            cfg = cfg.model_copy(
                update={
                    "storage": cfg.storage.model_copy(
                        update={"path": str(Path(args.database).expanduser().resolve())}
                    )
                }
            )
        db_path = Path(cfg.storage.path).expanduser().resolve()
        if not db_path.is_file():
            return _print_error(
                {"ok": False, "error_code": "missing_database", "database": db_path.name}
            )

        if args.dry_run:
            db = ReadOnlyDatabase(db_path)
            try:
                if db.migration_version < CURRENT_SCHEMA_VERSION:
                    return _print_error(
                        {
                            "ok": False,
                            "error_code": "schema_too_old",
                            "schema_version": db.migration_version,
                            "required_schema_version": CURRENT_SCHEMA_VERSION,
                        }
                    )
                repo = Repository(db)  # type: ignore[arg-type]
                result = run_storage_maintenance(
                    repo,
                    cfg,
                    dry_run=True,
                    persist_status=False,
                )
                print(
                    json.dumps(
                        {
                            "ok": result.success,
                            "dry_run": True,
                            "total_rows_eligible": result.total_rows_eligible,
                            "eligible_deletes_by_category": result.eligible_deletes_by_category,
                            "eligible_updates_by_category": result.eligible_updates_by_category,
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

        # --apply: open existing DB, refuse schema drift, integrity preflight, no migrate.
        db = Database.open_existing(db_path)
        try:
            if db.migration_version != CURRENT_SCHEMA_VERSION:
                return _print_error(
                    {
                        "ok": False,
                        "error_code": "schema_mismatch",
                        "schema_version": db.migration_version,
                        "required_schema_version": CURRENT_SCHEMA_VERSION,
                    }
                )
            try:
                quick_check(db)
                foreign_key_check(db)
            except StorageIntegrityError as exc:
                return _print_error(
                    {
                        "ok": False,
                        "error_code": exc.kind,
                        "violation_count": exc.violation_count,
                    }
                )
            repo = Repository(db)
            result = run_storage_maintenance(
                repo,
                cfg,
                dry_run=False,
                persist_status=True,
            )
            print(
                json.dumps(
                    {
                        "ok": result.success,
                        "dry_run": False,
                        "total_rows_deleted": result.total_rows_deleted,
                        "rows_deleted_by_category": result.rows_deleted_by_category,
                        "rows_updated_by_category": result.rows_updated_by_category,
                        "more_work_pending": result.more_work_pending,
                        "duration_ms": result.duration_ms,
                        "error_code": result.error_code,
                        "failure_category": result.failure_category,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0 if result.success else 1
        finally:
            db.close()
    except ConfigError as exc:
        return _print_error({"ok": False, "error_code": "config_error", "error": str(exc)})
    except Exception:
        return _print_error({"ok": False, "error_code": "maintenance_failed"})


def add_storage_subparser(subparsers: argparse._SubParsersAction) -> None:
    storage = subparsers.add_parser("storage", help="Storage integrity, backup, and maintenance")
    storage_sub = storage.add_subparsers(dest="storage_command", required=True)

    check = storage_sub.add_parser("check", help="Run SQLite integrity checks (read-only)")
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
