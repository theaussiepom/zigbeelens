# Upgrading ZigbeeLens

## Docker / Compose

1. **Back up** `/data` (see [backups.md](backups.md))
2. Pull the new image:
   ```bash
   docker compose -f deploy/docker/docker-compose.example.yaml pull
   ```
3. Restart:
   ```bash
   docker compose -f deploy/docker/docker-compose.example.yaml up -d
   ```

SQLite migrations run automatically on startup. Check logs for `migration_version` if anything looks wrong.

## Home Assistant add-on

1. Back up the add-on (includes `/data`)
2. Update the add-on from the store
3. Restart

## What to keep stable

| Item | Guidance |
|------|----------|
| `config/config.yaml` | Keep across upgrades; review new options in release notes |
| `networks[].id` | **Do not rename casually** — device history uses `network_id + ieee_address` |
| `/data/zigbeelens.sqlite` | Migrated in place; back up before major version jumps |

## Version tags

Prefer pinning to a release tag in production:

```yaml
image: ghcr.io/zigbeelens/zigbeelens:0.1.0
```

Use `:latest` for convenience on trusted lab systems only.

## Rollback

1. Stop the container / add-on
2. Restore `/data` from backup if needed
3. Run the previous image tag
4. Start again

If a migration already ran forward, restoring an older database without matching code may fail — always back up before upgrading across major versions.

## Checking the upgrade

- Open the UI — dashboard should load
- `GET /api/health` → `"status": "ok"`, `"database": "ok"`
- Settings page shows expected migration version
- Mock scenarios still work in dev builds (`?scenario=`)

## MQTT downtime during upgrade

Brief collector disconnection during restart is normal. The healthcheck does not require MQTT to be connected.
