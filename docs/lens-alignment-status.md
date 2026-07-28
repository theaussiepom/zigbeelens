# Lens family alignment — historical note

**Status:** Historical. The active ZigbeeLens public diagnostic contract is
**decision contract v2** (Track 5), not Lens-bucket presentation fields.

Earlier Lens-family alignment (API `/api/v1`, presentation `lens_bucket`, Lens MQTT
summary entities, report compatibility sections) shipped in the v0.1.x stream and
is described in historical CHANGELOG notes.

## Current behaviour (Track 5)

| Area | Current contract |
|------|------------------|
| Public diagnostic vocabulary | Shared `DecisionStatus` / `DecisionPriority` |
| Decision contract | `decision_contract_version = 2` |
| Reports | Exact `report_version = 3` storage after migration 014 |
| MQTT Discovery | Decision summary entities; Lens configs tombstoned |
| HACS | Exact contract v2; no Health/Lens diagnostic fallback |
| Internal health engine | Retained for evaluation / incidents; not public authority |
| Operational health | `/api/health`, `/healthz` unchanged |

## Release-work boundary

Phase 7A, Phase 7B, and Phase 7C1 are merged. The prior Phase 7C2 S1–S9 set is
stale after runtime/UI corrections and must be recaptured together from one
final source. Phase 7D live Beast validation remains blocked. Historical
release notes and screenshots are not evidence that either gate has passed.

See:

- [api.md](api.md)
- [reports.md](reports.md)
- [mqtt-discovery.md](mqtt-discovery.md)
- [hacs.md](hacs.md)
- [decision-engine.md](decision-engine.md)

ZigbeeLens and [ThreadLens](https://github.com/theaussiepom/threadlens) remain
separate repositories and runtimes. Product naming (“ZigbeeLens”) is unrelated
to the retired `LensBucket` presentation vocabulary.
