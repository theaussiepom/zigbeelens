# Lens alignment — live deployment state

Documentation of Ben's production Lens deployments (last validated 2026-06-16).

**Do not commit secrets.** Hostnames and image tags only.

ThreadLens canonical copy: [threadlens/docs/deployments/lens-alignment-live-state.md](https://github.com/theaussiepom/threadlens/blob/main/docs/deployments/lens-alignment-live-state.md).

---

## ThreadLens (Pironman)

| Field | Value |
|-------|--------|
| Host | Pironman / `192.168.100.4` |
| Image | `ghcr.io/theaussiepom/threadlens:0.2.19` |
| `/api/v1/version` | `0.2.19` |
| MQTT | **7** clean discovery configs, **0** old flat topics |
| `per_node_entities` | `false` |
| HACS | **preserved** |

---

## ZigbeeLens (BenBeast)

| Field | Value |
|-------|--------|
| Host | BenBeast / `192.168.100.5` |
| Compose | `/mnt/nas/docker/automation/docker-compose.yml` |
| Live image channel | `ghcr.io/theaussiepom/zigbeelens:edge` (**rolling** — BenBeast tracks latest edge, not pinned semver) |
| Validated edge content | v0.1.13-era / `9a52470` |
| Semver image (available, not live channel) | `ghcr.io/theaussiepom/zigbeelens:0.1.13` |
| `/api/version`, `/api/v1/version` | `0.1.13` |
| MQTT discovery | **enabled** — **6** clean configs, **0** old flat topics |
| HACS | **preserved** |

---

## Home Assistant (BenBeast)

MQTT summary devices present for both products. HACS companion entities untouched. No `.storage` edits for Lens migration.
