# Decision engine migration roadmap

This document defines the master phases and sub-phases for moving ZigbeeLens from a dashboard/graph product to a shared decision-engine investigation product.

It exists to prevent the work being watered down as it is split across many PRs.

## Programme statement

ZigbeeLens is evolving from:

```text
dashboard + graph + reports
```

to:

```text
decision engine + investigation workspace + consistent reports
```

The destination is not more data on screen. The destination is consistent, reusable diagnostic decisions across the whole product.

## Phase naming

Use master phases and sub-phases:

```text
0A, 0B, 0C...
1A, 1B, 1C...
```

Each implementation PR should reference the phase it serves.

Example:

```text
Phase: 3B — Snapshot history ViewModel
```

## Phase gates

Every phase must preserve:

- read-only operation;
- evidence-first wording;
- no causal overclaiming;
- no unknown-as-zero;
- no topology-as-live-route claim;
- explicit data coverage;
- one shared decision meaning across screens;
- reports matching UI decisions; and
- user usefulness over information volume.

## Master Phase 0 — Product and architecture contract

Phase 0 is documentation and alignment. It defines the destination before code moves.

### Phase 0A — Decision Engine Charter

Output:

- `docs/decision-engine.md`

Purpose:

- define the decision engine;
- define evidence facts, decisions, reasons, limitations, suggested checks and data coverage;
- define backend and frontend ownership rules;
- define the PR checklist for future phases.

Acceptance criteria:

- screens must not independently decide diagnostic meaning;
- backend routes must not own product judgement;
- ViewModels own UI-ready meaning;
- raw counts do not lead diagnostic surfaces;
- data coverage labels are specific and actionable.

### Phase 0B — UX Pruning Contract

Output:

- `docs/ux-pruning.md`

Purpose:

- define which surfaces are primary workflows;
- define what is supporting/advanced;
- define what should be demoted, merged or removed later.

Acceptance criteria:

- Mesh / topology is the main investigation workspace;
- Device details is the main decision surface;
- Devices is inventory/search, not a parallel diagnostic engine;
- Reports are contextual exports first and saved history second;
- raw snapshots and whole-network compare are advanced/debug;
- router-risk UX moves into router-area intelligence.

### Phase 0C — Migration Map

Output:

- this document;
- future updates as phases complete.

Purpose:

- make migration state visible;
- prevent half-MVVM / half-decision-engine surfaces becoming permanent.

Acceptance criteria:

- every major surface is listed;
- each surface has a current state, target state and migration phase;
- no ambiguous "later tidy" bucket.

### Phase 0D — Surface Inventory

Output:

- `docs/decision-engine-phase-0.md` surface inventory section.

Purpose:

- identify every current product/API/reporting surface before pruning or migration.

Acceptance criteria:

- each surface is classified as primary, supporting, advanced, merged, or deprecated-later;
- replacement workflows are recorded.

### Phase 0E — Decision Ownership Matrix

Output:

- `docs/decision-engine-phase-0.md` ownership matrix section.

Purpose:

- define which layer owns each decision or label.

Acceptance criteria:

- diagnostic statuses belong to the decision engine;
- display labels belong to ViewModels/presenters;
- components render only;
- reports consume the same decisions as UI.

### Phase 0F — Data Inventory and Usefulness Audit

Output:

- `docs/decision-engine-phase-0.md` data inventory section.

Purpose:

- identify what every stored data source can support;
- record what it cannot prove;
- define coverage caveats.

Acceptance criteria:

- all current persisted evidence tables are covered;
- topology, metrics, availability, incidents and HA enrichment are treated as evidence inputs;
- no data source is assumed to be useful merely because it exists.

### Phase 0G — Deprecation Register

Output:

- `docs/decision-engine-phase-0.md` deprecation register.

Purpose:

- track pruning deliberately.

Acceptance criteria:

- every demoted surface has a replacement workflow;
- nothing is silently removed;
- debug/support surfaces remain available where useful.

### Phase 0H — Cross-repo Impact Map

Output:

- `docs/decision-engine-phase-0.md` cross-repo impact section.

Purpose:

- identify which later phases affect core/UI, add-on, HACS, docs, MQTT Discovery and deployment examples.

Acceptance criteria:

- add-on/HACS compatibility risks are named early;
- docs/screenshots are treated as release work, not afterthoughts.

### Phase 0I — Compatibility and Migration Rules

Output:

- `docs/decision-engine-phase-0.md` compatibility section.

Purpose:

- define API, SQLite, localStorage, reports and debug endpoint compatibility expectations.

Acceptance criteria:

- old endpoints are not casually broken;
- saved layout/connection-control keys are handled deliberately;
- report schemas are migrated or versioned deliberately.

### Phase 0J — Performance Budgets

Output:

- `docs/decision-engine-phase-0.md` performance budget section.

Purpose:

- prevent decision APIs from scanning too much data on Beast-sized networks.

Acceptance criteria:

- graph load, device details, snapshot history and decision endpoint targets are named;
- Beast-sized networks are the reference workload;
- future service PRs must state performance impact.

### Phase 0K — Golden Test Fixtures

Output:

- `docs/decision-engine-phase-0.md` golden fixtures section.

Purpose:

- define representative product scenarios that must remain correct across phases.

Acceptance criteria:

- fixtures cover healthy routers, sleepy devices, availability gaps, route hint gaps, shared events, router areas, model patterns and HA enrichment.

### Phase 0L — Copy and Visual Hierarchy Contract

Output:

- `docs/decision-engine-phase-0.md` copy hierarchy section;
- complements `docs/ubiquitous-language.md`.

Purpose:

- ensure decisions lead, raw counts follow.

Acceptance criteria:

- decision first;
- why second;
- what this means third;
- suggested checks fourth;
- evidence details last;
- no generic limited/degraded labels when specific coverage exists.

### Phase 0M — Rollout Strategy

Output:

- `docs/decision-engine-phase-0.md` rollout section.

Purpose:

- keep large migration safe without watering it down.

Acceptance criteria:

- behaviour-preserving refactor before behaviour change;
- decision-backed migration before old UX removal;
- docs and Beast validation are phase requirements.

## Master Phase 1 — Shared decision model

This phase creates shared decision and coverage types before moving product behaviour.

### Phase 1A — Backend decision types

Add shared backend decision types.

Target files:

```text
apps/core/src/zigbeelens/decisions/types.py
```

Expected concepts:

- `Decision`
- `EvidenceFact`
- `Reason`
- `Limitation`
- `SuggestedCheck`
- `DataCoverage`
- `DecisionStatus`
- `DecisionPriority`

Acceptance criteria:

- generic, not topology-only;
- reason codes supported;
- unknown stays unknown/null;
- no UI-specific component concerns.

### Phase 1B — Data coverage model

Add shared coverage evaluation.

Target file:

```text
apps/core/src/zigbeelens/decisions/coverage.py
```

Coverage dimensions:

- availability;
- last seen;
- last payload;
- battery;
- linkquality;
- topology snapshot;
- route hints;
- historical snapshots;
- passive history;
- HA enrichment;
- incidents;
- reports.

Coverage states:

- available;
- off;
- building;
- unknown;
- stale;
- not configured;
- not observed;
- sparse.

Acceptance criteria:

- explicit labels such as `Availability tracking off` and `Availability history building`;
- no vague degraded/limited headline;
- reusable by UI and reports.

### Phase 1C — Reason-code copy mapping

Move major diagnostic prose to reason-code mappings.

Acceptance criteria:

- decision services emit reason codes plus params;
- presenters/ViewModels render copy;
- reports and UI can render the same reasons.

### Phase 1D — Frontend ViewModel conventions

Create frontend ViewModel folders and conventions.

Target shape:

```text
apps/ui/src/viewModels/
apps/ui/src/viewModels/topology/
apps/ui/src/viewModels/devices/
apps/ui/src/viewModels/reports/
```

Acceptance criteria:

- ViewModels own labels, pills, sections, rows and actions;
- components render ViewModels;
- no tiny ViewModels for generic UI atoms.

## Master Phase 2 — Codebase consolidation before intelligence

This phase tidies machinery before adding the next layer of intelligence.

### Phase 2A — Extract backend EvidenceGraphService

Move evidence graph orchestration out of the FastAPI route.

Target:

```text
apps/core/src/zigbeelens/services/evidence_graph.py
```

Acceptance criteria:

- route validates network and calls service;
- response shape unchanged;
- no behaviour change;
- tests prove parity.

### Phase 2B — Split repository responsibilities

Introduce narrower access layers or interfaces.

Target concepts:

- DeviceRepository;
- TopologyRepository;
- AvailabilityRepository;
- IncidentRepository;
- ReportRepository;
- MetricRepository.

Acceptance criteria:

- the existing Repository may remain as a facade;
- new decision services depend on narrower interfaces;
- no schema behaviour change.

### Phase 2C — Split frontend API types

Move domain types out of `apps/ui/src/lib/api.ts`.

Target:

```text
apps/ui/src/types/devices.ts
apps/ui/src/types/topology.ts
apps/ui/src/types/decisions.ts
apps/ui/src/types/reports.ts
```

Acceptance criteria:

- `api.ts` mostly fetches;
- domain types live in domain files;
- whole-network compare types are labelled advanced/debug or moved out of primary flow.

### Phase 2D — Split TopologyGraphPage shell

Break the graph page into stable units.

Target units:

- `TopologyGraphPage`;
- `GraphToolbar`;
- `GraphCanvasPanel`;
- `GraphSidebar`;
- `ConnectionControlsPanel`;
- `TopologyMetricStrip`;
- `useTopologyGraphData`;
- `useGraphSelection`;
- `useConnectionControls`.

Acceptance criteria:

- no behaviour change;
- no graph movement regression;
- connection-control persistence unchanged;
- tests updated around extracted units.

## Master Phase 3 — Topology as first decision-engine migration

Topology is first because it is the most complex and most judgement-heavy surface.

### Phase 3A — Topology decision facts

Create topology facts consumed by decisions.

Example facts:

- latest snapshot complete;
- snapshot stale;
- route hints available;
- device seen in latest snapshot;
- device has no links shown in latest snapshot;
- last-known links available;
- recent missing links available;
- passive hints available.

Acceptance criteria:

- facts are reusable by graph, device details, reports and investigations;
- facts do not contain final UI copy.

### Phase 3B — Snapshot history ViewModel

Migrate snapshot history to a ViewModel.

Acceptance criteria:

- component receives a ViewModel;
- ViewModel owns rows, status, pills, reasons, checks and evidence details;
- same behaviour as current device-led snapshot history.

### Phase 3C — Device details ViewModel

Migrate device details into a ViewModel.

Target structure:

- device story preview;
- current status;
- what looks worth checking;
- recent activity;
- snapshot history;
- data coverage;
- evidence details;
- open issue.

Acceptance criteria:

- device details becomes the main decision surface;
- empty sections omitted;
- component does not independently judge status.

### Phase 3D — Investigation cards use decision output

Migrate `Where to look first` to decision-backed action groups.

Action groups:

- Check power/reporting;
- Review router area;
- Investigate shared event;
- Improve data coverage;
- Watch only.

Acceptance criteria:

- action-led grouping;
- graph focus still works;
- no graph movement.

### Phase 3E — Data source / coverage strip

Add shared coverage strip in Mesh.

Example:

```text
Snapshot: Complete · 2h ago
Route hints: Available
Availability: History building
HA areas: Not linked
```

Acceptance criteria:

- shows what ZigbeeLens can rely on;
- direct setup action where appropriate;
- powered by coverage model.

### Phase 3F — Graph controls pruning

Introduce presets and demote detailed controls.

Presets:

- Troubleshooting;
- Router review;
- Battery devices;
- Quiet view;
- Full snapshot links.

Acceptance criteria:

- existing detailed controls remain available;
- default UX is simpler;
- no data removed;
- no graph-layout regression.

## Master Phase 4 — Device Story intelligence

This phase adds the first large product payoff from the decision engine.

### Phase 4A — DeviceStoryService backend

Create a deterministic, evidence-gated device story service.

Inputs:

- current state;
- last seen;
- last payload;
- battery;
- linkquality;
- metric samples;
- availability changes;
- device snapshots;
- incidents;
- topology snapshots;
- last-known links;
- recent missing links;
- passive hints;
- HA enrichment.

Acceptance criteria:

- outputs status, reasons, evidence, limitations and checks;
- no new collection behaviour;
- no causal claims.

### Phase 4B — Expected sleepy behaviour

Learn normal observed reporting rhythm for battery devices.

Acceptance criteria:

- requires enough observations;
- sparse data shows nothing;
- never says a sleepy device failed.

### Phase 4C — Device data coverage

Show per-device evidence coverage.

Example:

```text
Availability: building
Last seen: available
Battery history: available
LQI history: sparse
Topology history: 2 of 10 snapshots
HA area: missing
```

Acceptance criteria:

- coverage visible in device details;
- setup gaps actionable;
- no vague degraded labels.

### Phase 4D — LQI trend intelligence

Start with per-device LQI trends, not pairwise correlation.

Acceptance criteria:

- enough samples required;
- trend/window logic, not one sample;
- no RF/root-cause claims.

### Phase 4E — Availability event groups

Promote excluded network-wide availability windows into useful cards.

Acceptance criteria:

- shared events are grouped;
- pairwise hints are not created from network-wide storms;
- suggested checks mention host/Z2M/MQTT/power/maintenance as checks, not causes.

### Phase 4F — Router area intelligence

Create observed router-area decisions.

Acceptance criteria:

- uses `observed router area`, not parent/router cause;
- combines topology, issues, last-known links and passive hints;
- action-led.

### Phase 4G — Model/manufacturer pattern intelligence

Add batch/model pattern decisions.

Acceptance criteria:

- minimum group size required;
- no manufacturer blame;
- useful for battery, firmware or model patterns.

## Master Phase 5 — Whole-app decision migration

Migrate non-topology surfaces to the shared engine.

### Phase 5A — Overview dashboard

Overview shows decision-engine priorities, recent changes and data coverage warnings.

### Phase 5B — Devices page

Devices page becomes inventory/search/filter with decision badges.

### Phase 5C — Incidents page

Incidents become decision/event records, not competing truth.

### Phase 5D — Reports and exports

Reports consume decision output and match UI decisions.

### Phase 5E — HACS / HA companion surfaces

HACS and HA companion surfaces display shared decisions only after Core is consistent.

## Master Phase 6 — UX pruning and navigation consolidation

Remove or demote old paths after replacements are in place.

### Phase 6A — Navigation simplification

**Status: merged (PR #96).** Primary navigation and `/investigate` routes are
canonical. Phase 6B opening commit closed remaining navigation correctness
gaps (mobile Advanced clipping, bridge-state presenter, encoded route
segments, Investigate/Raw snapshot link semantics).

### Phase 6B — Router UX consolidation

**Status: implemented on `refactor/router-area-ux` (awaiting review).**

Standalone Router diagnostics navigation and `RoutersPage` are removed.
`/routers` remains a compatibility redirect to `/investigate`. Router facts,
Core `/api/routers`, HACS/MQTT/report router projections remain.
Observed router areas are actionable in Mesh via backend
`router_neighbourhood_review` cards (`Focus router area`, optional
`Open router details` into the existing NodeDrawer). No parentage/routing/cause
claims; no layout/preset/control mutation on focus.

### Phase 6C — Snapshot UX consolidation

Completed: device-led snapshot history is primary on Device Detail; NodeDrawer
links to full device details; `/topology` is an Advanced/support landing;
`/topology/:networkId` is exact raw point-in-time detail with collapsed contents;
whole-network compare remains API/debug-only; manual capture remains.
Route params are consumed once; retained snapshots stay readable when capture is
disabled; landing status is factual; Device Detail history load/error is section-local;
background refresh failures retain last accepted history/raw detail with retry.

### Phase 6D — Reports UX consolidation

**Complete.** Report creation is contextual from Device Detail, Incident Detail,
Network Detail, and Mesh / Investigate. The Reports page is Saved reports history
with one Create full report action. All current creation uses Core
`ReportDetailV3` / stored reports. The client-only Mesh evidence export menu is
removed from production. Legacy v1/v2 stored bodies remain immutable.

## Master Phase 7 — Hardening, performance and release quality

### Phase 7A — Query/index performance

Add query-specific repository methods and indexes for Beast-sized networks.

### Phase 7B — Test architecture

Add decision, coverage, ViewModel, report parity and forbidden wording tests.

### Phase 7C — Documentation/screenshots

Update README, architecture, screenshots and safety docs.

### Phase 7D — Deployment validation

Run live Beast smoke tests covering healthy router, problem sensor, sleepy battery device, no-latest-link device, router area, availability history building, route hints and report export.

## Current migration map

| Surface | Current state | Target state | Migration phase |
|---|---|---|---|
| Overview | Dashboard summary. | Decision priorities, recent changes, data coverage. | 5A |
| Devices | Inventory/status list. | Inventory/search with decision badges. | 5B |
| Device details | Mixed facts and local sections. | Device story / decision surface. | 3C / 4A |
| Snapshot history | Device Detail primary surface. | ViewModel-backed decision section. | 3B / 6C |
| Mesh graph | Strong evidence graph, some local orchestration. | Investigation workspace consuming decisions. | 3A-3F |
| Investigation cards | Backend topology/passive-specific cards. | Shared decision/action groups. | 3D |
| Reports | Saved history + contextual Create full report. | Decision-backed contextual summaries. | 5D / 6D (done) |
| Incidents | Issue history and state. | Decision/event record tied to device story. | 5C |
| Raw snapshots | Advanced `/topology` landing + exact detail. | Support evidence only. | 6C |
| Whole-network compare | Debug endpoint after UI demotion. | Advanced/debug only. | 6C |
| Router/risk UX | Separate/implicit router risk. | Router-area review decisions. | 4F / 6B |
| HACS companion | Companion read-only surfaces. | Shared decision display. | 5E |
| MQTT Discovery entities | Summary HA entities. | Minimal high-level status only. | Later explicit phase if needed |

## Per-PR checklist

Every PR in this programme should include:

```text
Phase:
Decision-engine alignment:
UX pruning impact:
Data coverage impact:
Screens affected:
Reports affected:
Compatibility impact:
Performance impact:
Read-only guardrails:
Copy/wording guardrails:
Golden fixtures affected:
What this deliberately does not do:
```

A PR that cannot answer these questions should not be part of this programme.
