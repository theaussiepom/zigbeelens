# ZigbeeLens UI style guide

ZigbeeLens Core dashboard and the HACS companion panel are part of the **Lens family**, alongside [ThreadLens](https://github.com/theaussiepom/threadlens). They share visual language but remain separate repositories — no shared `lens-ui` package.

Family-wide principles and health vocabulary: [lens-family.md](lens-family.md).

## Design goals

- **Read-only observability** — calm, evidence-first copy; no repair or control affordances
- **Incident-first** — answer *is anything broken, where, and what does the evidence say?*
- **Honest limitations** — unavailable metrics stay null; never infer zero or causal claims
- **Mobile-first** — touch targets `min-h-11`, horizontal nav on small screens, sidebar on desktop

## Theme tokens (`zl-*`)

Defined in `apps/ui/src/index.css` via Tailwind v4 `@theme`:

| Token | Use |
|-------|-----|
| `zl-bg`, `zl-surface`, `zl-surface-2` | Page and card backgrounds |
| `zl-text`, `zl-muted` | Primary and secondary text |
| `zl-border` | Dividers and card outlines |
| `zl-accent` | Links, active nav, primary actions |
| `zl-healthy`, `zl-watch`, `zl-critical` | Severity colours |

IBM Plex Sans and Mono are bundled via `@fontsource` — no external font URLs in production assets.

## Layout shell

- App shell — sidebar (desktop) + horizontal nav (mobile) + collector/mode banner + refresh
- Router pages under `apps/ui/src/pages/`
- Device detail and network views expose drilldown technical fields (IEEE, link quality, routes)

## Primitives (`apps/ui/src/components/ui.tsx`)

Reuse these before inventing new patterns:

- `Card`, `SectionHeading`, `Badge`, `StatTile`, `KeyValue`
- `HealthBadge`, severity helpers, empty/loading/error states

Domain-specific cards live alongside page components under `apps/ui/src/components/`.

## Copy and classification

- Device health uses domain-specific `DeviceHealthPrimary` values (router risk, weak link, low battery, …)
- **Presentation layer** maps domain signals to Lens family buckets for sorting and docs — see [lens-family.md](lens-family.md)
- Bridge offline: calm **Critical** severity with limitations (“device telemetry may be incomplete”)
- Avoid “caused by” unless structured evidence supports it

## Live updates

- Prefer SSE (`/api/events/stream`) with debounced dashboard refetch
- Header connection state should be honest (live / reconnecting)

## Monitoring transparency

- In-app guide at **`/monitoring`** — `MonitoringGuidePage` + `monitoringGuide.ts`
- Documents thresholds, incident rules, and MQTT sources without requiring external wiki

## HACS companion panel

- Lightweight native summary — not a duplicate of the full Core UI
- **Open Full Dashboard** — primary escape hatch, new tab, always reliable
- **Try Embedded View** — optional; follows Lens family embed decision tree
- Mixed content (HTTPS HA + HTTP Core) → calm blocked screen + Open Full Dashboard

See [hacs-embedded-view.md](hacs-embedded-view.md).

## What not to add

- Repair, reset, permit join, or control buttons
- Causal language (“because”, “caused by”) without structured evidence
- External CDN fonts, scripts, or analytics
- Per-device MQTT entity explosion in default configs

## Related

- [lens-family.md](lens-family.md)
- [hacs-embedded-view.md](hacs-embedded-view.md)
- [mqtt-discovery.md](mqtt-discovery.md)
- ThreadLens style guide: [docs/style-guide.md](https://github.com/theaussiepom/threadlens/blob/main/docs/style-guide.md)
