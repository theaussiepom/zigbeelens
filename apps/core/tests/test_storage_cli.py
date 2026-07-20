"""Track 6 storage CLI and online backup tests."""

from __future__ import annotations

import json
import stat
from pathlib import Path

from zigbeelens.config.models import NetworkConfig
from zigbeelens.db.connection import Database
from zigbeelens.main import main
from zigbeelens.storage.backup import backup_sqlite_database
from zigbeelens.storage.repository import Repository


def _seed_db(path: Path) -> None:
    db = Database(path)
    db.migrate()
    repo = Repository(db)
    repo.sync_networks([NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")])
    repo.db.conn.execute(
        """
        INSERT INTO reports (id, format, redaction_json, summary, generated_at, body_json)
        VALUES ('rep-1', 'json', '{}', 'Report', '2026-07-01T00:00:00+00:00', '{"report_version":3}')
        """
    )
    repo.db.conn.commit()
    db.close()


def test_storage_check_and_backup_cli(tmp_path: Path, capsys):
    db_path = tmp_path / "live.sqlite"
    _seed_db(db_path)
    out = tmp_path / "backup.sqlite"

    try:
        main(["storage", "check", "--database", str(db_path)])
    except SystemExit as exc:
        assert exc.code == 0
    check_payload = json.loads(capsys.readouterr().out)
    assert check_payload["ok"] is True

    try:
        main(
            [
                "storage",
                "backup",
                "--database",
                str(db_path),
                "--output",
                str(out),
            ]
        )
    except SystemExit as exc:
        assert exc.code == 0
    backup_payload = json.loads(capsys.readouterr().out)
    assert backup_payload["ok"] is True
    assert out.exists()
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    assert backup_payload["schema_version"] >= 12

    # Source unchanged and still readable.
    db = Database(db_path)
    assert db.conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 1
    db.close()
    validate = Database(out)
    assert validate.conn.execute("SELECT id FROM reports").fetchone()[0] == "rep-1"
    validate.close()


def test_backup_refuses_existing_without_overwrite(tmp_path: Path):
    from zigbeelens.storage.backup import StorageBackupError

    db_path = tmp_path / "live.sqlite"
    _seed_db(db_path)
    out = tmp_path / "backup.sqlite"
    backup_sqlite_database(output=out, database=str(db_path))
    try:
        backup_sqlite_database(output=out, database=str(db_path))
        raised = False
    except StorageBackupError:
        raised = True
    assert raised


def test_storage_maintenance_dry_run_cli(tmp_path: Path, capsys):
    db_path = tmp_path / "live.sqlite"
    _seed_db(db_path)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        f"""
mode:
  mock: true
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
storage:
  path: {db_path}
  retention_days: 7
""".strip(),
        encoding="utf-8",
    )
    try:
        main(["storage", "maintenance", "--config", str(cfg_path), "--dry-run"])
    except SystemExit as exc:
        assert exc.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    # Reports remain under default policy.
    db = Database(db_path)
    assert db.conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 1
    db.close()
