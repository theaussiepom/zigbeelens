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

Phase 7A, Phase 7B, and Phase 7C1 are merged. Phase 7C2 is complete: PR #108
merged reviewed head `1ea2949ab09038cdfe94d1c6d6b8e5fd45d8d87f` as evidence
merge `93fb26617042ed46d8920a7b75a42e3ae9da4d62`. All S1–S9 assets retain
capture source `af04ee906b71de77ee6e0eb5d866c0647d502410`; required checks were
green, and the S4 recorded-severity `Incident` versus recorded-confidence
`High` review was resolved. Public HACS synchronization and final artifact
pairing remain pending, so Phase 7D live Beast validation remains blocked.
Historical release notes and screenshots are not evidence that deployment
gates have passed.

See:

- [api.md](api.md)
- [reports.md](reports.md)
- [mqtt-discovery.md](mqtt-discovery.md)
- [hacs.md](hacs.md)
- [decision-engine.md](decision-engine.md)

ZigbeeLens and [ThreadLens](https://github.com/theaussiepom/threadlens) remain
separate repositories and runtimes. Product naming (“ZigbeeLens”) is unrelated
to the retired `LensBucket` presentation vocabulary.
