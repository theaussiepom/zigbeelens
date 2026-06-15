# Lens alignment — live deployment state

Documentation of Ben's production Lens deployments after Phase 3D closure (2026-06-16).

**Do not commit secrets.** Hostnames and image tags only.

---

## ThreadLens (Pironman)

| Field | Value |
|-------|--------|
| Host | Pironman / `192.168.100.4` |
| Compose | `~/threadlens/docker-compose.pironman.yml` |
| Image | `ghcr.io/theaussiepom/threadlens:0.2.18` |
| Tag note | Clean MQTT release published as **v0.2.18** (`v0.2.3` already existed on an older commit) |
| MQTT summary entities | **7** global |
| `per_node_entities` | `false` |
| Old retained MQTT topics | **116** old flat discovery topics cleared (2026-06-15) |
| HACS | ThreadLens companion entities **preserved** |

---

## ZigbeeLens (BenBeast)

| Field | Value |
|-------|--------|
| Host | BenBeast / `192.168.100.5` |
| Compose | `/mnt/nas/docker/automation/docker-compose.yml` (service `zigbeelens`) |
| Image at closure | `ghcr.io/theaussiepom/zigbeelens:edge` @ `23ee5fa` |
| Target after release | `ghcr.io/theaussiepom/zigbeelens:0.1.13` |
| MQTT discovery | **enabled** |
| MQTT summary entities | **6** global |
| Per-network / per-device MQTT | **none** by default |
| Old retained MQTT topics | **none** at enablement |
| HACS | ZigbeeLens companion entities **preserved** |

Config backups: `*.bak-pre-zigbeelens-mqtt-*` on NAS under `zigbeelens/`.

---

## Home Assistant (BenBeast)

| Integration | MQTT summary | HACS preserved |
|-------------|--------------|----------------|
| ThreadLens | 7 entities, `threadlens_summary` device | Yes |
| ZigbeeLens | 6 entities, `zigbeelens_core` device | Yes |

No per-device MQTT spam. No `.storage` edits for this migration.

ThreadLens canonical copy: [threadlens/docs/deployments/lens-alignment-live-state.md](https://github.com/theaussiepom/threadlens/blob/main/docs/deployments/lens-alignment-live-state.md).
