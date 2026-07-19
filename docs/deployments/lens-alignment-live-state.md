# Lens alignment — live deployment state (historical)

**Status:** Historical snapshot (last validated 2026-06-16).

This note records Ben's production Lens deployments during the earlier Lens-family
alignment stream. It is **not** a description of the current Track 5 decision
contract.

For current ZigbeeLens public contracts see:

- [api.md](../api.md) — decision contract v2
- [mqtt-discovery.md](../mqtt-discovery.md) — decision MQTT summary entities
- [hacs.md](../hacs.md) — HACS contract v2
- [lens-alignment-status.md](../lens-alignment-status.md)

**Do not commit secrets.** Hostnames and image tags only.

ThreadLens canonical historical copy:  
[threadlens/docs/deployments/lens-alignment-live-state.md](https://github.com/theaussiepom/threadlens/blob/main/docs/deployments/lens-alignment-live-state.md).

---

## ThreadLens (Pironman) — 2026-06-16

| Field | Value |
|-------|--------|
| Host | Pironman / `192.168.100.4` |
| Image | `ghcr.io/theaussiepom/threadlens:0.2.19` |
| MQTT | Clean discovery configs (Lens-era) |
| HACS | preserved |

## ZigbeeLens (BenBeast) — 2026-06-16

| Field | Value |
|-------|--------|
| Host | BenBeast / `192.168.100.5` |
| Live image channel | `ghcr.io/theaussiepom/zigbeelens:edge` (rolling) |
| MQTT | Lens-era global summary entities (superseded by Track 5 decision entities) |
| HACS | preserved |

After upgrading to Track 5 Core, expect MQTT Discovery to tombstone superseded
Lens config topics and publish decision-summary entities instead. HACS requires
decision contract v2.
