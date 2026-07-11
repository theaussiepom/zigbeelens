# Cursor model and phase guardrails

This document tightens the execution rules for the ZigbeeLens decision-engine programme.

It exists for two reasons:

1. Some phases in `decision-engine-implementation-plan.md` are intentionally strategic, but implementation should still happen in smaller PR-sized slices.
2. Cursor must guard against using the wrong model or starting with too little context.

This document is stricter than the general implementation plan. If there is a conflict, follow this document.

## Required starting prompt

Use this prompt at the start of every Cursor session for the decision-engine programme.

```text
You are working in the ZigbeeLens repository on the decision-engine programme.

Before making any edits, read these docs in full:
- docs/architecture.md
- docs/safety-audit.md
- docs/ubiquitous-language.md
- docs/topology.md
- docs/decision-engine.md
- docs/ux-pruning.md
- docs/decision-engine-migration.md
- docs/decision-engine-phase-0.md
- docs/decision-engine-implementation-plan.md
- docs/decision-engine-cursor-guardrails.md

Treat these docs as the product and architecture contract.

Your first response must include:
1. The phase/sub-phase you believe you are working on.
2. The exact docs you read.
3. The model you are using and whether it is allowed for this sub-phase.
4. The files you expect to inspect before editing.
5. The golden fixtures likely affected.
6. The checks you expect to run.
7. What this phase explicitly must not do.

Do not edit files until you have completed that context check.
Do not broaden scope beyond the named sub-phase.
Do not combine phases unless docs/decision-engine-cursor-guardrails.md explicitly allows it.

If the selected model is not allowed for the phase, stop and say which model is required and why.
```

## Required review prompt

Use this prompt after Cursor produces a diff.

```text
Review the diff against all required decision-engine docs:
- docs/architecture.md
- docs/safety-audit.md
- docs/ubiquitous-language.md
- docs/topology.md
- docs/decision-engine.md
- docs/ux-pruning.md
- docs/decision-engine-migration.md
- docs/decision-engine-phase-0.md
- docs/decision-engine-implementation-plan.md
- docs/decision-engine-cursor-guardrails.md

Return:
1. Whether the PR stayed inside the named phase/sub-phase.
2. Whether the selected model was appropriate.
3. Any must-fix issues.
4. Any should-fix issues.
5. Any safe follow-ups.
6. Guardrail status:
   - read-only behaviour
   - MQTT/Zigbee behaviour
   - topology capture behaviour
   - Home Assistant / HACS behaviour
   - unknown-as-zero
   - causal wording
   - parent/current/live route wording
   - UI/report/incident wording drift
   - raw counts leading primary UI
   - graph layout/localStorage changes
   - report compatibility
   - schema compatibility
7. Tests/checks run and missing checks.
8. Whether this PR makes ZigbeeLens more useful/actionable or merely exposes more information.
```

## Model selection rules

### Default

Composer 2.5 is the default implementation model.

Use Composer 2.5 for:

- behaviour-preserving refactors;
- shared types;
- coverage helpers;
- reason-code constants;
- ViewModel conventions;
- service extraction;
- component extraction;
- focused ViewModel migration;
- focused UI additions with existing data;
- tests;
- docs.

### Required 4.5 review

Use 4.5 for review before merging when a PR does any of the following:

- combines backend + UI + reports;
- introduces new diagnostic wording;
- introduces a new decision status or changes status meaning;
- adds a new decision service that combines more than three evidence sources;
- changes API shape used by HACS/add-on/Reports;
- changes SQLite schema or migrations;
- changes performance characteristics of graph/device/report APIs;
- touches topology capture policy, MQTT behaviour or HA/HACS behaviour;
- changes graph layout/signature/localStorage behaviour;
- implements Device Story, sleepy-device rhythm, LQI trend, router-area intelligence, model/manufacturer pattern intelligence, overview priorities, reports parity, or HACS companion decision display.

### Required 4.5 planning

Use 4.5 before implementation when:

- the phase boundary is unclear;
- implementation seems to require combining sub-phases;
- a compatibility trade-off is needed;
- report schema or API versioning is ambiguous;
- a performance budget cannot be met without redesign;
- tests show current behaviour differs from the documentation contract.

### Wrong-model guard

At the start of each session, Cursor must identify:

```text
Selected model:
Required model for implementation:
Required model for review:
Allowed to proceed now: yes/no
```

Stop if:

- the selected model is weaker than the required implementation model;
- the selected model is doing final review for a phase that requires 4.5 review;
- the selected model proposes a product direction not in the docs;
- the model wants to merge phases because it is “efficient”.

## Strict phase splitting

The phase names in `decision-engine-implementation-plan.md` are strategic. Implementation PRs must use the finer slices below where specified.

### Phase 1A — Backend decision types

Keep as one PR unless it touches existing runtime code.

Allowed PR:

```text
1A — Backend decision types
```

Do not wire routes or UI.

### Phase 1B — Data coverage model

Keep as one PR unless it starts querying real data.

Allowed PR:

```text
1B — Data coverage model primitives
```

If real data evaluation is needed, split:

```text
1B-1 Coverage types/helpers
1B-2 Coverage evaluators using repository data
```

### Phase 1C — Reason-code copy mapping

Split backend reason codes and frontend copy if both are needed.

Preferred PRs:

```text
1C-1 Backend reason-code catalogue
1C-2 Frontend decision copy mapping
```

Do not replace all existing product copy in this phase.

### Phase 1D — Frontend ViewModel conventions

Keep as one PR.

Allowed PR:

```text
1D — Frontend ViewModel conventions
```

No major component migration.

### Phase 2A — EvidenceGraphService extraction

Keep behaviour-preserving.

Allowed PR:

```text
2A — Extract EvidenceGraphService
```

Required review:

- Composer 2.5 implementation is fine.
- 4.5 review if the route/service boundary becomes unclear or if response shape changes.

### Phase 2B — Repository access layers

Must be split. Do not attempt a giant repository rewrite.

Preferred PRs:

```text
2B-1 Repository method inventory and access-layer plan
2B-2 TopologyRepository wrapper/access layer
2B-3 DeviceRepository and NetworkRepository wrappers/access layers
2B-4 AvailabilityRepository and MetricRepository wrappers/access layers
2B-5 IncidentRepository and ReportRepository wrappers/access layers
```

Each PR must keep the existing `Repository` facade working unless a later PR explicitly migrates callers.

### Phase 2C — Frontend API type split

May be one PR if typecheck stays clean and diff is mechanical.

Split if imports become noisy:

```text
2C-1 Topology/API type split
2C-2 Devices/incidents/reports type split
2C-3 Decision shared UI types alignment
```

Do not combine with ViewModel migration.

### Phase 2D — TopologyGraphPage shell split

Must be split. This page is too large and too risky for one PR.

Preferred PRs:

```text
2D-1 Extract useTopologyGraphData
2D-2 Extract useGraphSelection
2D-3 Extract useConnectionControls
2D-4 Extract GraphToolbar and TopologyMetricStrip
2D-5 Extract GraphCanvasPanel and GraphSidebar
2D-6 Final shell cleanup and parity tests
```

Rules:

- no behaviour change;
- no layout signature changes;
- no localStorage key changes;
- no control pruning;
- no ViewModel migration except private/internal prop shaping.

### Phase 3A — Topology decision facts

Split if facts touch API payloads.

Preferred PRs:

```text
3A-1 Backend topology fact builder
3A-2 EvidenceGraphService consumes topology facts internally
3A-3 Expose topology facts to UI/report payloads only if needed
```

No final UI copy in facts.

### Phase 3B — Snapshot history ViewModel

Can be one PR if well-contained.

Split if component changes become large:

```text
3B-1 SnapshotHistory ViewModel builder and tests
3B-2 SnapshotHistorySection renders ViewModel
```

Rules:

- no global compare UI;
- no hidden older usable snapshots;
- no fake online/offline for untracked periods;
- selecting rows must not move graph.

### Phase 3C — Device details ViewModel

Must be split.

Preferred PRs:

```text
3C-1 DeviceDetails ViewModel skeleton and section model
3C-2 Current status / diagnostic stats sections migrate to ViewModel
3C-3 Snapshot history integration as child ViewModel
3C-4 Passive hints / recent missing / open issue sections migrate
3C-5 Device drawer final renderer cleanup and tests
```

Do not add full Device Story in Phase 3C.

### Phase 3D — Investigation decision cards

Split backend and UI if necessary.

Preferred PRs:

```text
3D-1 Backend investigation decisions and action groups
3D-2 UI card rendering / graph focus parity
```

No new passive rules unless only required to preserve existing behaviour.

### Phase 3E — Evidence coverage strip

Split backend coverage payload and UI rendering if necessary.

Preferred PRs:

```text
3E-1 Backend evidence coverage payload
3E-2 Mesh coverage strip ViewModel/UI
3E-3 Device details coverage reuse
```

Reports reuse comes later unless trivial.

### Phase 3F — Graph view presets

Must be split if localStorage changes.

Preferred PRs:

```text
3F-1 Preset model and mapping tests
3F-2 UI preset selector with existing controls still available
3F-3 Detailed controls collapse behind Draw more links
3F-4 Persistence/localStorage migration if needed
```

Required 4.5 review if layout signature or localStorage behaviour changes.

### Phase 4A — DeviceStoryService

Must be split. Do not implement backend, API and UI in one PR.

Required PRs:

```text
4A-1 Backend DeviceStoryService core rules
4A-2 Device Story API DTO / endpoint wiring
4A-3 Device Story UI ViewModel and device drawer section
4A-4 Device Story report-readiness hook or TODO parity tests
```

4.5 review required for each PR from 4A onwards that introduces or changes diagnostic wording.

### Phase 4B — Expected sleepy behaviour

Must be split.

Preferred PRs:

```text
4B-1 Reporting rhythm calculation service and tests
4B-2 Device Story integration
4B-3 UI/report wording integration
```

4.5 review required for threshold/wording decisions.

### Phase 4C — Device data coverage

Can be one or two PRs.

Preferred PRs:

```text
4C-1 Device-level coverage evaluator
4C-2 Device details coverage rendering
```

### Phase 4D — LQI trend intelligence

Must be split.

Preferred PRs:

```text
4D-1 LQI trend calculation and tests
4D-2 Decision integration
4D-3 UI/report rendering
```

4.5 review required for thresholds and wording.

### Phase 4E — Availability event groups

Must be split.

Preferred PRs:

```text
4E-1 Shared availability event grouping service
4E-2 Investigation/overview decision integration
4E-3 UI/report rendering
```

Do not create pairwise hints from broad shared events.

### Phase 4F — Router area intelligence

Must be split.

Preferred PRs:

```text
4F-1 Router-area evidence aggregation
4F-2 Router-area decision rules
4F-3 Mesh/UI rendering and focus behaviour
4F-4 Report integration
```

4.5 review required for wording and evidence-source weighting.

### Phase 4G — Model/manufacturer pattern intelligence

Must be split.

Preferred PRs:

```text
4G-1 Model/manufacturer grouping and thresholds
4G-2 Decision integration
4G-3 UI/report rendering
```

4.5 review required for thresholds and wording.

### Phase 5A — Overview dashboard migration

Must be split.

Preferred PRs:

```text
5A-1 Overview decision summary API/service
5A-2 Overview ViewModel and UI migration
5A-3 Recent changes / data coverage integration
```

4.5 review required because this changes the main product entry point.

### Phase 5B — Devices page migration

Preferred PRs:

```text
5B-1 Device decision badges API/ViewModel
5B-2 Devices table/filter migration
5B-3 Remove/demote duplicate diagnostic prose
```

### Phase 5C — Incidents page migration

Preferred PRs:

```text
5C-1 Incident-to-decision mapping
5C-2 Incidents UI language alignment
5C-3 Existing incident compatibility tests
```

### Phase 5D — Reports and exports migration

Must be split.

Preferred PRs:

```text
5D-1 Report presenter consumes decision bundles
5D-2 Device/investigation report sections
5D-3 Report parity tests with UI/ViewModels
5D-4 Contextual export actions
```

4.5 review required for schema/versioning and parity.

### Phase 5E — HACS / HA companion surfaces

Must be split and reviewed carefully.

Preferred PRs:

```text
5E-1 API compatibility/version contract for companion decisions
5E-2 HACS companion decision display
5E-3 HA/add-on docs and compatibility validation
```

4.5 review required before implementation and before merge.

### Phase 6A — Navigation simplification

Preferred PRs:

```text
6A-1 Navigation target route map
6A-2 UI navigation changes
6A-3 Docs/screenshots update
```

### Phase 6B — Router UX consolidation

Preferred PRs:

```text
6B-1 Router UX inventory and replacement confirmation
6B-2 Demote/remove standalone router-risk UX
6B-3 Router-area links/docs update
```

### Phase 6C — Snapshot UX consolidation

Preferred PRs:

```text
6C-1 Raw snapshot route moves under Advanced
6C-2 Whole-network compare debug-only docs/link cleanup
6C-3 Device snapshot history primary path validation
```

### Phase 6D — Reports UX consolidation

Preferred PRs:

```text
6D-1 Contextual export entry points
6D-2 Reports page becomes saved history
6D-3 Old report wizard demotion/removal
```

### Phase 7A — Query/index performance

Must be split by area.

Preferred PRs:

```text
7A-1 Baseline timings / query inventory
7A-2 Topology history indexes and query methods
7A-3 Availability/metric bounded query improvements
7A-4 Report/overview decision performance hardening
```

4.5 review required for performance trade-offs.

### Phase 7B — Test architecture

Preferred PRs:

```text
7B-1 Decision/coverage/reason test helpers
7B-2 ViewModel and component parity tests
7B-3 Report parity tests
7B-4 Forbidden wording sweeps
```

### Phase 7C — Documentation/screenshots

Preferred PRs:

```text
7C-1 README and architecture updates
7C-2 Topology / Mesh docs update
7C-3 Screenshots and add-on/HACS docs update
```

### Phase 7D — Deployment validation

Preferred PRs or release checklist entries:

```text
7D-1 Beast validation checklist
7D-2 Beast validation fixes
7D-3 Release notes / known limitations
```

## Phase entry checklist

Before starting any sub-phase, Cursor must answer:

```text
Phase:
Implementation slice:
Selected model:
Required implementation model:
Required review model:
Allowed to proceed with selected model: yes/no
Docs read:
Current code inspected:
Files likely to change:
Golden fixtures affected:
Expected checks:
Explicit non-goals:
Stop conditions for this phase:
```

## Phase exit checklist

Before opening a PR, Cursor must answer:

```text
Phase:
Implementation slice completed:
Scope stayed inside phase: yes/no
Model selection complied: yes/no
Docs updated if needed: yes/no
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
Tests/checks run:
Checks not run and why:
Self-review result:
What this deliberately does not do:
```

## Initial user prompt to Cursor

Use this when starting the programme after Phase 0 docs are merged.

```text
We are starting the ZigbeeLens decision-engine programme.

Use Composer 2.5 unless docs/decision-engine-cursor-guardrails.md says this phase requires 4.5 planning or review.

Read these docs in full before editing:
- docs/architecture.md
- docs/safety-audit.md
- docs/ubiquitous-language.md
- docs/topology.md
- docs/decision-engine.md
- docs/ux-pruning.md
- docs/decision-engine-migration.md
- docs/decision-engine-phase-0.md
- docs/decision-engine-implementation-plan.md
- docs/decision-engine-cursor-guardrails.md

Start with Phase 1A — Backend decision types.

Before editing, respond with:
1. Confirmation of every doc read.
2. Selected model and whether it is allowed for Phase 1A.
3. The phase entry checklist from docs/decision-engine-cursor-guardrails.md.
4. The current backend model/API style you inspected.
5. The exact files you intend to create/change.
6. The checks you will run.

Then implement Phase 1A only.

Do not wire the decision types into routes.
Do not change UI.
Do not change runtime behaviour.
Do not create database migrations.
Do not start Phase 1B.

When done, self-review against docs/decision-engine-cursor-guardrails.md and prepare a PR body using the required checklist.
```

## Initial 4.5 review prompt

Use this after a Composer 2.5 implementation PR is ready, when the guardrails require 4.5 review.

```text
Review this ZigbeeLens decision-engine PR as a strict architecture/product reviewer.

Read these docs first:
- docs/architecture.md
- docs/safety-audit.md
- docs/ubiquitous-language.md
- docs/topology.md
- docs/decision-engine.md
- docs/ux-pruning.md
- docs/decision-engine-migration.md
- docs/decision-engine-phase-0.md
- docs/decision-engine-implementation-plan.md
- docs/decision-engine-cursor-guardrails.md

Review the diff for the named phase only.

Return:
1. Merge / do not merge verdict.
2. Whether the PR stayed inside its named phase.
3. Whether Composer 2.5 was appropriate for implementation.
4. Whether 4.5 review was required and completed.
5. Must-fix issues.
6. Should-fix issues.
7. Safe follow-ups.
8. Guardrail violations, if any.
9. Test gaps.
10. Whether the change moves ZigbeeLens toward the decision-engine north star.
```

## Final warning for Cursor

Efficiency is not the goal. Coherence is the goal.

Do not merge phases to save time.
Do not introduce clever intelligence before the decision surfaces can consume it consistently.
Do not let a refactor phase change product behaviour.
Do not let an implementation phase create a second source of diagnostic truth.
