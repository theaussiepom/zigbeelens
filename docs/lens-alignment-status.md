# Lens family alignment — status

**Status:** Complete (alignment stream closed 2026-06-16).

ZigbeeLens and [ThreadLens](https://github.com/theaussiepom/threadlens) remain **separate repositories and runtimes**. Shared conventions: [lens-family.md](lens-family.md) → ThreadLens canonical doc.

ThreadLens equivalent: [threadlens/docs/lens-alignment-status.md](https://github.com/theaussiepom/threadlens/blob/main/docs/lens-alignment-status.md).

---

## Complete

| Area | Notes |
|------|--------|
| Shared docs / conventions | [lens-family.md](lens-family.md) stub |
| API `/api/v1` | **v0.1.13** |
| Presentation `lens_bucket` | **v0.1.13** |
| Clean MQTT (6 global) | **edge** @ v0.1.13-era |
| Report / export alignment | PR #10 |
| Deployment hygiene | BenBeast rolling `:edge` (not pinned `:0.1.13`) |
| Live deployment notes | [deployments/lens-alignment-live-state.md](deployments/lens-alignment-live-state.md) |

---

## Still deferred

- HACS visual smoke / screenshot matrix
- ThreadLens `/how-it-works` → `/monitoring` route rename
- Optional ZigbeeLens UI migration to `/api/v1`
- Optional network-level `lens_bucket`
- Shared library extraction
- Optional HA entity ID cosmetic rename

---

## Recommended next pass

1. HACS browser visual smoke when convenient
2. Optional HA entity ID cleanup
3. Future semver tag when warranted (report alignment lands on edge via main)
