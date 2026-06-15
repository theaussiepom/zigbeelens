# Lens family

ZigbeeLens and [ThreadLens](https://github.com/theaussiepom/threadlens) are **sibling products** in the Lens family of read-only home-network observability tools. They share UX conventions and documentation patterns but remain **separate repositories and runtimes**.

```text
ZigbeeLens  = Zigbee / Zigbee2MQTT observability
ThreadLens  = Thread / Matter-over-Thread observability
Shared      = Lens family conventions (this document)
```

There is no shared npm or Python package in Phase 1. Conventions are documented here so both products feel like related tools without coupling releases.

---

## Shared principles

| Principle | Meaning |
|-------------|---------|
| **Read-only observability** | Watch and explain; do not repair, reset, commission, or mutate network state |
| **Evidence-first diagnostics** | Show what was observed, when, and from which source |
| **No causal overclaiming** | Avoid “caused by” unless directly observed; prefer “may indicate”, “correlated with” |
| **Honest unknowns** | Use `unknown`, `null`, or explicit limitations — never infer zero or guess parentage |
| **Friendly default UI** | Overview answers “is anything wrong?”; drilldowns show technical detail |
| **Home Assistant companion** | Native panel + optional embed; not a replacement for HA or the underlying stack |
| **No entity spam by default** | MQTT Discovery publishes **global summary** entities unless explicitly configured otherwise |
| **Reports safe to share after redaction** | Use redaction profiles before posting to forums or support channels |

Product-specific safety audits and scope limits remain in each repo’s security and architecture docs.

---

## Shared health vocabulary (presentation layer)

Lens products use a **shared vocabulary for UI grouping, incident summaries, reports, HACS panels, and MQTT summary entities**. Domain health engines stay separate; reason codes stay domain-specific.

| Lens term | When to use |
|-----------|-------------|
| **Healthy** | No current concern; signals within normal bounds |
| **Recently unstable** | Flapping or repeated transitions; not hard down |
| **Needs attention** | Clear problem pattern, repeated failures, or elevated risk |
| **Unavailable** | Known down, unreachable, or bridge/collector gap blocks observation |
| **Diagnostics limited** | Cannot observe further (unsupported probe, missing path, bridge offline) |
| **Informational** | Environmental or context signal — not a fault |
| **Unknown** | Insufficient evidence to classify |

### Mapping examples (ZigbeeLens)

| Domain signal | Typical Lens bucket |
|---------------|---------------------|
| Router risk candidate | **Needs attention** |
| Bridge/coordinator offline | **Unavailable** or **Needs attention** (depends on evidence scope) |
| Repeated availability changes | **Recently unstable** |
| Low battery, weak link, interview issue | **Needs attention** (domain chip may still show specific reason) |
| Stale reporting with bridge online | **Needs attention** or **Recently unstable** |
| Metric not available from MQTT | **Unknown** or omitted — not zero |

### Mapping examples (ThreadLens)

| Domain signal | Typical Lens bucket |
|---------------|---------------------|
| Safe read probe failed recently | **Recently unstable** or **Needs attention** (threshold-dependent) |
| Read probe path unsupported | **Diagnostics limited** |
| Matter node unavailable | **Unavailable** |
| Foreign TREL / observed-other network | **Informational** |
| OTBR unreachable | **Unavailable** or **Needs attention** |

Do not force identical classification logic between products. Align **labels and sort order** in dashboards, docs, and summary MQTT entities.

---

## Shared UI and style

See [style-guide.md](style-guide.md) for ZigbeeLens-specific paths and components.

- Dark diagnostic UI with **`zl-*` design tokens** (shared palette name across Lens products)
- **IBM Plex** Sans and Mono via bundled fonts — no production CDN dependencies
- **Mobile-first** cards, `min-h-11` touch targets, horizontal nav on small screens
- **Calm incident language** — evidence bullets, limitations callouts
- **Overview** hides raw technical IDs where possible (friendly names, network labels)
- **Drilldown** may show IEEE addresses, routes, probe paths, node IDs, collector details
- No repair/control affordances in Core or companion panel

---

## Home Assistant embedded view

See [hacs-embedded-view.md](hacs-embedded-view.md) for ZigbeeLens setup. The Lens family decision tree is identical across products:

1. **Native companion panel first** — status, incidents, summary counts
2. **Optional embedded Core dashboard** when browser security allows (matching HTTP/HTTPS scheme)
3. **If embedding blocked** — native panel + **Open Full Dashboard** (always works in a new tab)
4. **Keep HA menu/burger usable** — do not trap navigation in iframe-only UX
5. **No mutation/control buttons** in companion panel

---

## MQTT summary conventions

See [mqtt-discovery.md](mqtt-discovery.md) for ZigbeeLens configuration. Shared rules:

- **Global summary entities by default** — overall health, counts, collector status
- **Avoid per-device entity spam** unless explicitly enabled
- **`unknown` for unobserved/unavailable** values in entity state where applicable
- **`0` only for observed zero** — never infer zero from missing data
- **Entity names describe diagnostics**, not control (“health”, “unavailable count”, not “fix network”)
- **Availability topic** uses `online` / `offline` for Core or product liveness
- **No secrets** in discovery payloads or retained state

---

## Report conventions (target structure)

Report generators differ today; both products aim for this **shared section vocabulary** in exports and docs:

| Section | Purpose |
|---------|---------|
| `product`, `version`, `generated_at` | Identity and freshness |
| `site`, `mode` | Deployment context |
| **Executive summary** | One paragraph; no causal overclaiming |
| **Health summary** | Lens bucket or severity counts |
| **Active incidents** | Evidence-backed findings |
| **Collector status** | What was and was not observable |
| **Limitations** | Explicit gaps in evidence |
| **Redaction profile** | e.g. `public_safe`, `standard` |

See [reports.md](reports.md) and [redaction.md](redaction.md) for ZigbeeLens specifics.

---

## Release and readiness language

Both products follow a similar release posture:

- **No built-in authentication** in early versions — document and acknowledge before tagging
- **CI green** before merge; container image published via GitHub Actions
- **Redaction spot-check** on real or fixture data before release
- **HACS / companion panel smoke** on HTTP and, if used, HTTPS embed matrix
- **CHANGELOG** and GitHub Release notes for tagged versions

ZigbeeLens: [RELEASE_CHECKLIST.md](../RELEASE_CHECKLIST.md), [docs/release.md](release.md)  
ThreadLens: [RELEASE.md](https://github.com/theaussiepom/threadlens/blob/main/RELEASE.md)

---

## Related docs

- [style-guide.md](style-guide.md)
- [hacs-embedded-view.md](hacs-embedded-view.md)
- [mqtt-discovery.md](mqtt-discovery.md)
- [reports.md](reports.md)
- ThreadLens lens family doc: [docs/lens-family.md](https://github.com/theaussiepom/threadlens/blob/main/docs/lens-family.md)
