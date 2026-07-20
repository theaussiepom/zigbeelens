# Backups and restore

## What to back up

| Path | Contents |
|------|----------|
| `config/config.yaml` | MQTT settings, networks, diagnostics thresholds, retention policy |
| Secret files (if used) | API token / session secret files referenced by config |
| `data/zigbeelens.sqlite` (+ optional `-wal`/`-shm` only when Core is stopped) | Device history, incidents, events, **stored reports** |

Reports are stored **inline in SQLite** (JSON body + Markdown summary). There is no separate report file directory.

Redaction is applied **before** reports are stored — backups contain already-redacted report content, not raw MQTT secrets.

A database backup is sensitive. Protect it like the live database (permissions, disk encryption where confidentiality matters).

## Online SQLite backup (recommended while Core runs)

Use the local Core CLI (SQLite backup API). Do **not** copy only the main `.sqlite` file while WAL is active.

```bash
zigbeelens storage backup \
  --config config/config.yaml \
  --output backups/zigbeelens-$(date +%F).sqlite

zigbeelens storage check --database backups/zigbeelens-$(date +%F).sqlite
```

The CLI:

- copies a consistent online snapshot;
- writes a temporary `0600` file;
- validates `quick_check` + `foreign_key_check` before publish;
- atomically replaces the destination;
- refuses overwrite unless `--overwrite` is set.

There is no HTTP backup/download endpoint.

## Offline restore

Restore is always offline:

1. Stop Core / add-on / container.
2. Keep the current database as a rollback copy.
3. Run `zigbeelens storage check --database /path/to/backup.sqlite` (optionally `--full`).
4. Replace the configured database file.
5. Restore ownership/permissions (Docker: UID **1000**).
6. Start Core (migrations run normally).
7. Verify `/healthz`, `/api/health`, migration version, and `/api/storage/status`.

Database backups do **not** restore config YAML or secret files. Back those up separately.

## Docker / Compose file copy (Core stopped)

```bash
docker compose -f deploy/docker/docker-compose.example.yaml stop
tar czf zigbeelens-backup-$(date +%F).tar.gz config/ data/
docker compose -f deploy/docker/docker-compose.example.yaml start
```

## Home Assistant add-on backup

Use **Settings → System → Backups** and include the ZigbeeLens add-on. This remains the preferred add-on restore mechanism and captures `/data` inside the add-on.

## Retention policy (Track 6)

| Class | Default | Notes |
|-------|---------|-------|
| Telemetry history (`storage.retention_days`) | 7 days | Metrics, availability, snapshots, events, unresolved messages, terminal topology |
| Resolved incidents | 90 days | `storage.resolved_incident_retention_days`; `null` = keep |
| Open / watching incidents | keep | Never age-purged |
| Reports | until manually deleted | `storage.report_retention_days` default `null`; opt-in finite days |
| Inventory / current state / enrichment | keep | Never age-purged |

Maintenance runs once at startup (after migrations + integrity gates) and periodically (`storage.maintenance_interval_hours`, default 24).

```bash
zigbeelens storage maintenance --config config/config.yaml --dry-run
zigbeelens storage maintenance --config config/config.yaml --apply
```

Deleted pages become reusable inside SQLite; the main file may not shrink immediately. Track 6 does **not** run automatic `VACUUM`.

Topology count caps (`topology.max_snapshots_per_network`) apply independently to terminal snapshots.

## Settings UI

Settings shows policy and last maintenance facts only. There is no Purge / Vacuum / Backup / Restore button in the UI.
