# Lens family alignment — status

**Status:** Complete for the current alignment stream (Phases 1–3D, closure 2026-06-16).

ZigbeeLens and [ThreadLens](https://github.com/theaussiepom/threadlens) remain **separate repositories and runtimes**. Shared conventions: [lens-family.md](lens-family.md) → ThreadLens canonical doc.

---

## Completed (ZigbeeLens)

| Area | Release / PR |
|------|----------------|
| Shared docs / conventions | [lens-family.md](lens-family.md) stub |
| API `/api/v1` aliases, capabilities, status | PR #8 — **v0.1.13** |
| Presentation `lens_bucket` on dashboard/API | PR #9 — **v0.1.13** |
| Clean MQTT summary entities (6 global) | PR #11 — **v0.1.13** |
| Flat HA MQTT `device.identifiers` hotfix | PR #12 — **v0.1.13** |
| Release checklist | [RELEASE_CHECKLIST.md](../RELEASE_CHECKLIST.md) |
| Live deployment notes | [deployments/lens-alignment-live-state.md](deployments/lens-alignment-live-state.md) |

ThreadLens equivalent: [threadlens/docs/lens-alignment-status.md](https://github.com/theaussiepom/threadlens/blob/main/docs/lens-alignment-status.md).

---

## Intentionally deferred

- ThreadLens `/how-it-works` → `/monitoring` route rename
- HACS visual smoke / screenshot matrix
- Optional ZigbeeLens UI migration to `/api/v1` exclusively
- Optional network-level `lens_bucket`
- Shared library extraction / monorepo
- Report/export alignment — PR #10 (ZigbeeLens), PR #34 (ThreadLens) open

---

## Recommended next pass

1. Merge report-alignment PRs when ready
2. Pin BenBeast from `:edge` to `:0.1.13`
3. Optional HA entity ID cleanup
4. HACS visual smoke pass
