# Backups and restore

## What to back up

| Path | Contents |
|------|----------|
| `config/config.yaml` | MQTT settings, networks, diagnostics thresholds |
| `data/zigbeelens.sqlite` | Device history, incidents, events, **stored reports** |

Reports are stored **inline in SQLite** (JSON body + Markdown summary). There is no separate report file directory today.

Redaction is applied **before** reports are stored — backups contain already-redacted report content, not raw MQTT secrets.

## Docker / Compose backup

```bash
# Stop optional — SQLite backup is safer while stopped
docker compose -f deploy/docker/docker-compose.example.yaml stop

tar czf zigbeelens-backup-$(date +%F).tar.gz config/ data/

docker compose -f deploy/docker/docker-compose.example.yaml start
```

Or copy files directly:

```bash
cp config/config.yaml config/config.yaml.bak
cp data/zigbeelens.sqlite data/zigbeelens.sqlite.bak
```

## Home Assistant add-on backup

Use **Settings → System → Backups** and include the ZigbeeLens add-on. This captures `/data` inside the add-on.

## Restore

1. Stop ZigbeeLens (container or add-on)
2. Restore `config/config.yaml` and `data/zigbeelens.sqlite`
3. Ensure `/data` ownership is UID **1000** for Docker:
   ```bash
   sudo chown -R 1000:1000 data
   ```
4. Start ZigbeeLens

## Partial restore

- **Config only:** safe if network IDs unchanged
- **Database only:** restores history/reports; config must still point at the same `storage.path`
- **Changing network IDs after restore:** breaks identity continuity for stored devices

## Exporting reports without full backup

Use the Reports page:
- **Copy Markdown** for forum/GitHub posts
- **Download JSON/YAML** for archival

These exports are redacted snapshots suitable for sharing.

## Retention

`storage.retention_days` in config controls how long collected telemetry is kept. Reports you explicitly generate are stored until deleted from the Reports page or the database is removed.
