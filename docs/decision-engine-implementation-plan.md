# Decision Engine implementation plan for Cursor

This document is the working implementation plan for the ZigbeeLens decision-engine programme.

It is written so Cursor can work through the remaining phases strategically without repeatedly checking back for product direction.

Use it together with:

- [decision-engine.md](decision-engine.md)
- [ux-pruning.md](ux-pruning.md)
- [decision-engine-migration.md](decision-engine-migration.md)
- [decision-engine-phase-0.md](decision-engine-phase-0.md)
- [ubiquitous-language.md](ubiquitous-language.md)
- [architecture.md](architecture.md)
- [safety-audit.md](safety-audit.md)
- [topology.md](topology.md)

## Purpose

Build a reusable ZigbeeLens decision engine and migrate product surfaces to consume it consistently.

The desired product outcome is:

```text
Here is what is worth checking.
Here is why.
Here is the evidence.
Here is what data is missing.
Here is what not to infer.
Here is the practical next step.
```

The undesired outcome is:

```text
More screens, more counts, more edge types, more summaries, more interpretation drift.
```

## Model guidance

Use Cursor Composer 2.5 by default.

Composer 2.5 is appropriate for:

- behaviour-preserving refactors;
- adding shared types;
- extracting services/hooks/ViewModels;
- writing tests;
- moving code between files;
- improving docs;
- implementing a well-scoped sub-phase from this document.

Escalate to 4.5 only for:

- broad architecture review before a major phase starts;
- diagnosing subtle cross-stack failures after tests fail;
- reviewing high-risk diff interactions across backend, UI and reports;
- deciding between competing architecture options not covered here;
- performance/debug investigations where the local evidence is confusing.

Do not use a stronger model to invent a different product. The product contract is in these docs.

## Working style for Cursor

Cursor should work one sub-phase at a time.

Do not batch multiple sub-phases into one PR unless the later sub-phase is trivial documentation caused by the first.

Each PR should leave the repo more coherent than it found it.

Preferred flow:

1. Read the relevant Phase 0 docs.
2. Inspect current code before changing it.
3. Restate the sub-phase goal in the PR plan.
4. Make the smallest coherent architecture move that completes the sub-phase.
5. Add/update tests at the correct layer.
6. Run checks.
7. Self-review the diff against the guardrails.
8. Update docs/migration status if the target state changed.
9. Open PR with the required checklist.

## Non-negotiable guardrails

Every change must preserve:

- read-only operation;
- no Zigbee control commands;
- no MQTT writes except explicitly allowed existing discovery/topology behaviours;
- no new MQTT subscriptions unless a phase explicitly says so;
- no topology scheduler change unless a phase explicitly says so;
- no Home Assistant entity churn;
- no HACS mutation behaviour;
- no causal overclaiming;
- no parent-router inference;
- no current/live route claims;
- no unknown-as-zero;
- no generic AI insight copy;
- no graph-for-graph's-sake;
- no new primary UX surface that competes with Mesh/Device details;
- reports must not drift from UI decisions.

If a change violates any of these, stop and redesign.

## Global wording guardrails

Prefer:

- `Worth reviewing`
- `Watch`
- `No notable change`
- `Links shown`
- `Route hints`
- `Recent missing links`
- `Last-known links`
- `Suggested investigation links`
- `Observed router area`
- `Availability tracking off`
- `Availability history building`
- `Route hints unavailable`
- `HA areas not linked`
- `Snapshot stale`

Avoid in primary product copy:

- `degraded` when the specific missing source is known;
- `limited` when the specific missing source is known;
- `parent router`;
- `current route`;
- `live route`;
- `actual path`;
- `caused by`;
- `failed link`;
- `broken link`;
- `disappeared`;
- `lost`;
- `AI insight`;
- `inferred route`;
- `derived neighbour`.

Technical/source terms can appear in collapsed evidence details or advanced/debug views when clearly secondary.

## Required PR body checklist

Every implementation PR in this programme must include:

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
Checks:
```

For documentation-only PRs, use `not applicable` where appropriate, but still include the headings.

## Branch naming

Use one branch per sub-phase.

Suggested prefixes:

- `refactor/decision-types`
- `refactor/coverage-model`
- `refactor/reason-codes`
- `refactor/viewmodel-conventions`
- `refactor/evidence-graph-service`
- `refactor/topology-page-shell`
- `feat/device-story-service`
- `feat/router-area-decisions`
- `fix/decision-copy-parity`

## Baseline commands

Before major code phases, identify the current project commands from `package.json`, `pyproject.toml`, scripts and CI config. Do not assume command names if they changed.

Typical checks to look for and run where relevant:

```text
pnpm install --frozen-lockfile
pnpm --filter @zigbeelens/shared build
pnpm --filter @zigbeelens/ui typecheck
pnpm --filter @zigbeelens/ui lint
pnpm --filter @zigbeelens/ui test
pnpm --filter @zigbeelens/ui build
ruff check apps/core
pytest apps/core/tests
```

If a command is not available, record what was attempted and why it could not run.

## Self-review checklist

Before opening a PR, review the diff manually.

Check:

- no new MQTT publish path except existing explicit allowlist;
- no new `/set` handling;
- no new bridge request path except existing topology capture behaviour;
- no changed topology capture schedule unless that phase explicitly targets it;
- no UI component invents diagnostic status locally;
- no unknown data rendered as zero;
- no raw counts lead primary diagnostic UI;
- no competing status wording between UI/report/incident;
- no old global compare UI returns to primary flow;
- no router-area wording implies parent/root cause;
- no report-only interpretation added;
- no layout recalculation triggered by drawer/selection/filter changes unless intended;
- no localStorage key reset without migration/reason;
- no schema change without migration.

Suggested grep checks:

```text
rg -n "parent router|current route|live route|actual path|caused by|failed link|broken link|disappeared|lost|AI insight|inferred route|derived neighbour" apps docs
rg -n "degraded|limited" apps/ui apps/core docs
rg -n "worth reviewing|Worth reviewing|Watch|No notable change|Availability tracking off|Route hints unavailable" apps/ui apps/core
```

The grep is not a blind fail rule. It is a prompt to verify context.

## Golden fixtures to preserve

Use these scenarios for tests and manual validation:

1. healthy router;
2. sleepy battery normal;
3. sleepy battery suspicious silence;
4. device with no latest links but last-known links;
5. availability tracking off;
6. availability history building;
7. availability status unknown;
8. route hints unavailable;
9. shared availability event;
10. pairwise passive instability;
11. router area with issue cluster;
12. model/manufacturer pattern;
13. HA enrichment absent;
14. HA enrichment present;
15. stale topology snapshot;
16. noisy whole-network compare;
17. report parity.

Tests do not need all fixtures in every PR. Each PR must state which fixtures it affects.

---

# Phase 1 — Shared decision model

Phase 1 creates the shared language and types. It should not change major product behaviour yet.

## Phase 1A — Backend decision types

### Goal

Add backend decision primitives that are generic enough for the whole product, not topology-only.

### Suggested branch

```text
refactor/decision-types
```

### Files to create

```text
apps/core/src/zigbeelens/decisions/__init__.py
apps/core/src/zigbeelens/decisions/types.py
apps/core/tests/test_decision_types.py
```

Adjust package exports only as needed.

### Types to add

Use dataclasses, Pydantic models or typed dictionaries consistent with current backend style. Prefer simple serialisable models.

Suggested concepts:

```text
DecisionStatus
DecisionPriority
EvidenceFact
EvidenceReference
DecisionReason
DecisionLimitation
SuggestedCheck
DataCoverage
Decision
DecisionBundle
```

Suggested status values:

```text
informational
no_notable_change
changed
watch
worth_reviewing
review_first
improve_data_coverage
data_unavailable
```

Suggested priority values:

```text
none
low
medium
high
```

Suggested shape:

```python
class DecisionReason(BaseModel):
    code: str
    params: dict[str, Any] = Field(default_factory=dict)

class EvidenceReference(BaseModel):
    source: str
    id: str | None = None
    captured_at: datetime | None = None
    label: str | None = None

class Decision(BaseModel):
    subject_type: str
    subject_id: str
    status: DecisionStatus
    priority: DecisionPriority = DecisionPriority.NONE
    reasons: list[DecisionReason] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    limitations: list[DecisionLimitation] = Field(default_factory=list)
    suggested_checks: list[SuggestedCheck] = Field(default_factory=list)
    coverage: list[DataCoverage] = Field(default_factory=list)
```

Exact implementation can differ if it fits the codebase better.

### Implementation steps

1. Inspect backend model/API style.
2. Add decision models with JSON-friendly fields.
3. Keep them independent of topology modules.
4. Add unit tests for serialisation and enum values.
5. Do not wire into existing routes yet unless needed for import validation.

### Acceptance criteria

- Decision types compile/import cleanly.
- Types are generic and reusable by devices, incidents, reports and topology.
- Reason codes are supported.
- Unknown is represented as `None`/`unknown`, not `0`.
- No runtime behaviour changes.

### Tests

Add tests for:

- default empty lists are not shared mutable state;
- enum serialisation values are stable;
- a decision can include reasons, evidence, limitations, checks and coverage.

### Guardrails

- No UI changes.
- No route behaviour changes.
- No database migrations.

### Composer model

Composer 2.5 is sufficient.

## Phase 1B — Data coverage model

### Goal

Create shared backend coverage evaluation primitives and helpers.

Coverage must be specific and actionable. Do not use vague `degraded` or `limited` labels when the missing source is known.

### Suggested branch

```text
refactor/coverage-model
```

### Files to create/edit

```text
apps/core/src/zigbeelens/decisions/coverage.py
apps/core/tests/test_decision_coverage.py
```

May also update `apps/core/src/zigbeelens/decisions/types.py` if coverage types belong there.

### Coverage dimensions

Include these dimensions or equivalent stable strings:

```text
availability
last_seen
last_payload
battery
linkquality
topology_snapshot
route_hints
historical_snapshots
passive_history
ha_enrichment
incidents
reports
```

### Coverage states

Include these states or equivalent:

```text
available
off
building
unknown
stale
not_configured
not_observed
sparse
```

### Required labels

Coverage label mapping must support:

- `Availability tracking off`
- `Availability history building`
- `Availability status unknown`
- `Route hints unavailable`
- `HA areas not linked`
- `Snapshot stale`
- `Battery history sparse`
- `LQI history sparse`

### Implementation steps

1. Add `DataCoverage` model if not in 1A.
2. Add coverage helpers for common states.
3. Add stable label/copy codes, not necessarily final prose.
4. Keep helpers deterministic and side-effect-free.
5. Do not query the database directly in this phase unless a minimal fixture helper needs it.

### Acceptance criteria

- Coverage objects can be created for every required label.
- Coverage is reusable by UI and reports.
- No runtime route changes.
- No generic `degraded` primary label.

### Tests

Add tests for:

- availability off;
- availability building;
- availability unknown;
- route hints unavailable;
- HA areas not linked;
- snapshot stale;
- sparse battery/LQI.

### Guardrails

- Do not infer availability is off merely because one device has no events.
- Do not represent unknown coverage as unavailable.
- Do not render current labels in primary UI yet unless a later phase wires them.

### Composer model

Composer 2.5 is sufficient.

## Phase 1C — Reason-code copy mapping

### Goal

Create a stable reason-code system so decisions can be rendered consistently across UI and reports.

### Suggested branch

```text
refactor/decision-reason-codes
```

### Files to create/edit

Backend:

```text
apps/core/src/zigbeelens/decisions/reasons.py
apps/core/tests/test_decision_reasons.py
```

Frontend later may add:

```text
apps/ui/src/viewModels/decisionCopy.ts
apps/ui/src/viewModels/decisionCopy.test.ts
```

This phase can start backend-only if that is cleaner.

### Required reason codes to seed

Add a starting set. Do not wait until every future code is known.

Suggested codes:

```text
latest_snapshot_no_links
selected_snapshot_had_links
snapshot_link_count_changed
route_hints_changed
availability_tracking_off
availability_history_building
availability_status_unknown
route_hints_unavailable
ha_areas_not_linked
snapshot_stale
current_issue_present
battery_low
last_seen_stale
reported_lqi_low
recent_missing_links_present
last_known_links_present
passive_instability_hint_present
shared_availability_event
router_area_issue_cluster
model_pattern_observed
insufficient_history
```

### Implementation steps

1. Add reason-code constants/enums.
2. Add optional metadata for intended severity/status if useful.
3. Add tests that codes are stable and unique.
4. Do not replace all existing copy in one sweep.
5. Add docs/comments saying future diagnostic copy should use these codes.

### Acceptance criteria

- Reason codes exist and are unique.
- Codes are not topology-only.
- No broad UI rewrite yet.

### Guardrails

- Do not create final prose in backend modules where a ViewModel should own copy.
- Do not invent causal reason codes.

### Composer model

Composer 2.5 is sufficient.

## Phase 1D — Frontend ViewModel conventions

### Goal

Create frontend folders, naming conventions and a first minimal ViewModel type set without rewriting screens yet.

### Suggested branch

```text
refactor/viewmodel-conventions
```

### Files to create/edit

```text
apps/ui/src/viewModels/README.md
apps/ui/src/viewModels/types.ts
apps/ui/src/viewModels/decisionCopy.ts
apps/ui/src/viewModels/decisionCopy.test.ts
apps/ui/src/types/decisions.ts
```

### Implementation steps

1. Inspect current UI test tooling and style.
2. Add shared UI decision/ViewModel types.
3. Add copy mapping for seeded reason codes where needed.
4. Add README explaining `API DTO -> ViewModel -> Component`.
5. Do not migrate major components yet.

### Acceptance criteria

- ViewModel conventions are discoverable in code.
- Types support status pills, sections, rows, reasons, evidence details and suggested checks.
- Components are not forced to migrate yet.

### Tests

- reason code maps to expected user-facing text;
- unknown code falls back safely or is type-prevented;
- tone mapping is deterministic.

### Guardrails

- Do not add UI behaviour.
- Do not move large components in this phase.

### Composer model

Composer 2.5 is sufficient.

---

# Phase 2 — Codebase consolidation before intelligence

Phase 2 makes the existing code easier to migrate without adding clever new product behaviour.

## Phase 2A — Extract backend EvidenceGraphService

### Goal

Move evidence graph orchestration out of FastAPI routes into a service.

### Suggested branch

```text
refactor/evidence-graph-service
```

### Files likely involved

```text
apps/core/src/zigbeelens/api/routes.py
apps/core/src/zigbeelens/services/evidence_graph.py
apps/core/tests/test_topology_api.py
apps/core/tests/test_evidence_graph_service.py
```

Names may differ depending on current test structure.

### Implementation steps

1. Inspect the current topology/evidence graph route.
2. Identify all orchestration currently inside the route:
   - latest snapshot lookup;
   - topology nodes/links;
   - history windows;
   - last-known links;
   - passive hints;
   - device stats;
   - investigations;
   - counts;
   - limitations.
3. Create `EvidenceGraphService` with an explicit `build(network_id)` or similar method.
4. Move orchestration into the service without changing response shape.
5. Route should validate network, call service and return DTO.
6. Add service unit tests around the current behaviour.
7. Keep endpoint tests proving parity.

### Acceptance criteria

- API response shape unchanged.
- Route is thinner.
- Service is testable without the HTTP layer where practical.
- No topology capture behaviour changes.

### Tests

- existing API tests pass;
- service returns expected links/counts/investigations for fixture;
- missing network still handled as before;
- no route hints still explained as before.

### Guardrails

- Do not add new decision status in this phase.
- Do not change graph copy.
- Do not query more history than before.
- Do not alter snapshot retention.

### Composer model

Composer 2.5 is sufficient. Escalate to 4.5 only if route/service boundaries are unclear after inspection.

## Phase 2B — Split repository responsibilities

### Goal

Introduce narrower repository/query interfaces so decision services do not depend on a giant all-purpose repository.

### Suggested branch

```text
refactor/repository-access-layers
```

### Approach

Do not attempt a giant repository rewrite.

Prefer compatibility facade first:

```text
Repository remains for existing callers.
New services depend on narrower wrappers/interfaces.
```

Suggested access layers:

```text
DeviceRepository
TopologyRepository
AvailabilityRepository
IncidentRepository
ReportRepository
MetricRepository
NetworkRepository
```

### Implementation steps

1. Inspect current `Repository` methods and group them by domain.
2. Create access layer classes that delegate to the existing repository or share the same connection safely.
3. Move only methods needed by upcoming decision services first.
4. Avoid broad churn in old callers unless easy and safe.
5. Add tests for wrappers where useful.
6. Document the migration approach in comments or docs.

### Acceptance criteria

- New services can depend on narrower access layers.
- Existing callers keep working.
- No schema changes.
- No broad behavioural change.

### Guardrails

- Do not split every method just for purity.
- Do not duplicate SQL inconsistently.
- Do not introduce connection lifecycle bugs.

### Composer model

Composer 2.5 is sufficient for a careful first step. Use 4.5 for review if the repository is more tangled than expected.

## Phase 2C — Split frontend API types

### Goal

Move domain types out of `apps/ui/src/lib/api.ts` so API fetching and product models are easier to maintain.

### Suggested branch

```text
refactor/ui-api-types
```

### Target files

```text
apps/ui/src/types/devices.ts
apps/ui/src/types/topology.ts
apps/ui/src/types/decisions.ts
apps/ui/src/types/reports.ts
apps/ui/src/types/incidents.ts
apps/ui/src/lib/api.ts
```

### Implementation steps

1. Inspect `apps/ui/src/lib/api.ts`.
2. Identify type groups.
3. Move types into domain files.
4. Re-export where necessary to keep imports sane.
5. Update imports incrementally.
6. Label or isolate whole-network snapshot compare types as advanced/debug.
7. Run typecheck/tests.

### Acceptance criteria

- `api.ts` mostly contains fetch functions and endpoint helpers.
- Domain types live in named files.
- No runtime behaviour change.

### Guardrails

- Do not rename API fields casually.
- Do not change response parsing.
- Do not combine with ViewModel migration.

### Composer model

Composer 2.5 is sufficient.

## Phase 2D — Split TopologyGraphPage shell

### Goal

Break the graph page into coherent hooks/components without changing behaviour.

### Suggested branch

```text
refactor/topology-graph-page-shell
```

### Target extraction

```text
TopologyGraphPage
GraphToolbar
GraphCanvasPanel
GraphSidebar
ConnectionControlsPanel
TopologyMetricStrip
useTopologyGraphData
useGraphSelection
useConnectionControls
```

Use current component naming style.

### Implementation steps

1. Inspect current `TopologyGraphPage` and existing child components.
2. Extract data fetching into a hook first.
3. Extract selection state into a hook.
4. Extract connection controls into a hook/component boundary.
5. Extract purely visual sections next.
6. Keep layout signatures and React Flow keys unchanged unless a test proves safe.
7. Keep localStorage keys unchanged.
8. Update tests after each extraction.

### Acceptance criteria

- No visible behaviour change.
- No graph layout movement caused by extraction.
- No loss of persisted controls.
- No report/menu/drawer regression.
- Tests remain meaningful.

### Guardrails

- Do not introduce ViewModels yet unless scoped to internal props only.
- Do not prune controls in this phase.
- Do not add new intelligence.

### Composer model

Composer 2.5 is sufficient. Use 4.5 for review of the final diff if the page is still large.

---

# Phase 3 — Topology as first decision-engine migration

Phase 3 makes topology consume decision-engine structures and simplifies investigation UX.

## Phase 3A — Topology decision facts

### Goal

Build topology-specific evidence facts that feed decisions, reports and ViewModels.

### Suggested branch

```text
feat/topology-decision-facts
```

### Files likely involved

```text
apps/core/src/zigbeelens/decisions/topology_facts.py
apps/core/src/zigbeelens/services/evidence_graph.py
apps/core/tests/test_topology_decision_facts.py
```

### Fact examples

```text
latest_snapshot_complete
latest_snapshot_missing
latest_snapshot_stale
route_hints_available
route_hints_unavailable
device_seen_in_latest_snapshot
device_absent_from_latest_snapshot
device_has_latest_links
device_no_latest_links
device_has_selected_snapshot_links
device_latest_vs_selected_changed
last_known_links_available
recent_missing_links_available
passive_hints_available
availability_coverage_affects_snapshot_comparison
```

### Implementation steps

1. Add fact builder with no UI copy.
2. Feed it existing topology graph/snapshot history data.
3. Keep facts serialisable/testable.
4. Wire facts internally only where useful.
5. Do not change UI wording yet unless required for payload visibility.

### Acceptance criteria

- Facts are reusable by graph, device details, snapshot history and reports.
- Facts do not claim current/live routing.
- Facts do not contain final prose.
- No major UI behaviour change.

### Tests

- stale snapshot;
- no route hints;
- device no latest links but selected links;
- last-known links available;
- passive hints available;
- unavailable/unknown coverage affects comparison.

### Composer model

Composer 2.5 is sufficient.

## Phase 3B — Snapshot history ViewModel

### Goal

Move snapshot-history judgement/display shaping out of the React component into a ViewModel.

### Suggested branch

```text
refactor/snapshot-history-viewmodel
```

### Files likely involved

```text
apps/ui/src/components/topology/SnapshotHistorySection.tsx
apps/ui/src/viewModels/topology/snapshotHistoryViewModel.ts
apps/ui/src/viewModels/topology/snapshotHistoryViewModel.test.ts
```

### ViewModel should own

- selected snapshot label;
- row labels;
- row status/tone;
- availability coverage pills;
- `Why` list;
- `What this means` copy;
- suggested checks;
- collapsed evidence details model;
- empty state;
- disabled/unavailable states.

### Component should own

- rendering;
- click handlers;
- expand/collapse UI state if purely local;
- accessibility/aria state.

### Implementation steps

1. Write ViewModel tests around current expected outputs.
2. Extract copy/status logic into builder.
3. Update component to render ViewModel.
4. Preserve API calls and selection behaviour initially.
5. Ensure selecting rows does not move graph.
6. Ensure availability off/building/unknown remains explicit.

### Acceptance criteria

- Same user behaviour as current snapshot history.
- Component no longer decides `Worth reviewing`, `Watch`, `Similar`/`No notable change`.
- Tests cover the main golden snapshot cases.

### Guardrails

- Do not reintroduce global compare UI.
- Do not hide older usable snapshots.
- Do not fake online/offline for untracked periods.

### Composer model

Composer 2.5 is sufficient.

## Phase 3C — Device details ViewModel

### Goal

Make device details the main decision surface and remove ad-hoc diagnostic judgement from the component.

### Suggested branch

```text
refactor/device-details-viewmodel
```

### Files likely involved

```text
apps/ui/src/components/topology/NodeDrawer.tsx
apps/ui/src/viewModels/topology/deviceDetailsViewModel.ts
apps/ui/src/viewModels/topology/deviceDetailsViewModel.test.ts
```

### Target section order

1. Device story preview;
2. Current status;
3. What looks worth checking;
4. Recent activity;
5. Snapshot history;
6. Data coverage;
7. Evidence details;
8. Open issue;
9. Export/copy evidence actions.

Not every section exists immediately. Empty sections should be omitted.

### Implementation steps

1. Extract current display decisions into a ViewModel without changing behaviour.
2. Keep snapshot history as a child ViewModel/component.
3. Move section ordering into the ViewModel.
4. Ensure NodeDrawer becomes a renderer.
5. Add tests for issue device, no latest links, passive hints, availability coverage and open issue.

### Acceptance criteria

- Device details renders from a ViewModel.
- Component does not independently assign diagnostic status.
- Existing drawer behaviour and actions remain.
- No copy regression.

### Guardrails

- Do not add full Device Story yet.
- Do not create new backend endpoint unless necessary.
- Do not bury evidence details when already useful; collapse is okay.

### Composer model

Composer 2.5 is sufficient. Use 4.5 for review if many sections move.

## Phase 3D — Investigation cards use decision output

### Goal

Make `Where to look first` action-led and decision-backed.

### Suggested branch

```text
feat/investigation-decision-cards
```

### Action groups

```text
Check power/reporting
Review observed router area
Investigate shared event
Improve data coverage
Watch only
```

### Implementation steps

1. Add decision models for investigation cards.
2. Map existing card types into action groups.
3. Preserve current evidence and graph focus behaviour.
4. Update card copy to lead with action, then why.
5. Add tests for each action group.

### Acceptance criteria

- Cards are action-led.
- Existing useful cards are not lost.
- Graph focus still works.
- No root-cause claims.

### Guardrails

- Do not add new passive rules in this phase unless needed only to map existing cards.
- Do not make network-wide storms into pairwise links.

### Composer model

Composer 2.5 is sufficient.

## Phase 3E — Data source / coverage strip

### Goal

Add a compact evidence coverage strip to Mesh and related device/report surfaces where useful.

### Suggested branch

```text
feat/evidence-coverage-strip
```

### Required labels

- `Availability tracking off`
- `Availability history building`
- `Availability status unknown`
- `Route hints unavailable`
- `HA areas not linked`
- `Snapshot stale`

### Placement

Mesh:

- near existing network/snapshot metrics;
- compact;
- not a blocking alert unless page cannot render.

Device details:

- show relevant coverage where it affects device interpretation.

Reports later:

- reuse the same coverage output, but do not force report work into this PR.

### Implementation steps

1. Use coverage model from Phase 1B.
2. Add minimal API fields if existing graph payload lacks coverage.
3. Build ViewModel for coverage strip.
4. Add helper/tooltip text.
5. Add tests for each label.

### Acceptance criteria

- Specific labels appear where source is missing/building/stale.
- No vague degraded/limited headline.
- Route hints unavailable does not imply routes are absent.
- Snapshot stale does not trigger capture.
- HA areas not linked points to enrichment, not network change.

### Guardrails

- No MQTT writes.
- No Zigbee2MQTT setting changes.
- No topology scheduler changes.
- No automatic capture.

### Composer model

Composer 2.5 is sufficient.

## Phase 3F — Graph controls pruning

### Goal

Make graph controls simpler by default with presets, while preserving detailed controls for power users.

### Suggested branch

```text
feat/graph-view-presets
```

### Presets

```text
Troubleshooting
Router review
Battery devices
Quiet view
Full snapshot links
```

### Detailed controls

Move existing toggles behind:

```text
Draw more links
```

### Implementation steps

1. Map current control combinations to presets.
2. Preserve existing localStorage controls where practical.
3. Add preset state/versioning if needed.
4. Keep detailed toggles available.
5. Add tests for each preset and persistence.
6. Ensure graph layout does not recompute unexpectedly.

### Acceptance criteria

- Default UX is simpler.
- All existing evidence layers remain accessible.
- Presets are explainable.
- No data removed.

### Guardrails

- Do not change evidence meaning.
- Do not reset saved manual positions.
- Do not hide selected-device links.

### Composer model

Composer 2.5 is sufficient.

---

# Phase 4 — Device Story intelligence

Phase 4 is the first major product payoff from the decision engine.

## Phase 4A — DeviceStoryService backend

### Goal

Create deterministic evidence-gated device stories.

### Suggested branch

```text
feat/device-story-service
```

### Files likely involved

```text
apps/core/src/zigbeelens/decisions/device_story.py
apps/core/src/zigbeelens/api/routes.py
apps/core/tests/test_device_story.py
apps/ui/src/types/devices.ts
apps/ui/src/viewModels/topology/deviceStoryViewModel.ts
```

UI can be a later PR if backend is large enough.

### Inputs

Use existing stored evidence:

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

### Output

A story should include:

- status;
- headline;
- reasons;
- evidence;
- limitations;
- suggested checks;
- data coverage;
- optional timeline items.

### Implementation steps

1. Build backend service with bounded queries.
2. Start with a small set of deterministic story rules.
3. Add API endpoint or extend existing device endpoint carefully.
4. Add UI ViewModel/section only after backend tests pass.
5. Ensure reports can consume later, even if not wired yet.

### Initial story rules

Start with these:

- current issue present;
- no latest links but previous/last-known links exist;
- availability tracking off/building/unknown;
- stale last seen;
- low battery;
- route hints unavailable affects interpretation;
- HA areas missing affects grouping/report quality.

Do not add LQI trend or sleepy rhythm here if it makes the PR too large; those have separate sub-phases.

### Acceptance criteria

- Device story exists and is deterministic.
- No causal claims.
- Story is useful even with partial data.
- Sparse/unknown data suppresses overconfident text.

### Guardrails

- No new collection.
- No MQTT writes.
- No topology capture changes.
- No re-pair/reboot/move-router suggestions from weak evidence.

### Composer model

Composer 2.5 can implement. Use 4.5 for planning/review if service boundaries are unclear.

## Phase 4B — Expected sleepy behaviour

### Goal

Learn observed reporting rhythm for sleepy/battery devices and use it cautiously.

### Suggested branch

```text
feat/sleepy-device-rhythm
```

### Logic guidance

Only produce a rhythm when enough observations exist.

Possible approach:

- use recent device payload/device snapshot intervals;
- ignore huge gaps caused by collector downtime if detectable;
- compute median / percentile interval;
- classify current silence against expected rhythm;
- suppress if sample count too low.

### Output examples

Good:

```text
Usually reports every 40-90 minutes. Silent for 14 hours.
```

Bad:

```text
Device failed to report.
```

### Acceptance criteria

- Normal sleepy devices are not flagged.
- Suspicious silence can produce Watch/Worth reviewing when paired with current issue or strong history.
- Sparse data shows no rhythm claim.

### Tests

- enough samples normal;
- enough samples suspicious silence;
- sparse samples;
- mains device ignored or handled separately;
- collector gap does not create false rhythm if detectable.

### Composer model

Composer 2.5 likely sufficient. Use 4.5 if statistical/window logic becomes contentious.

## Phase 4C — Device data coverage

### Goal

Expose per-device evidence coverage in device details and stories.

### Suggested branch

```text
feat/device-data-coverage
```

### Coverage examples

```text
Availability: building
Last seen: available
Battery history: available
LQI history: sparse
Topology history: 2 of 10 snapshots
HA area: missing
```

### Implementation steps

1. Reuse Phase 1 coverage model.
2. Add device-level coverage evaluator.
3. Render in device details ViewModel.
4. Add tests for each key coverage state.

### Acceptance criteria

- Device details clearly names data gaps.
- Setup gaps are actionable.
- No generic degraded label.

### Composer model

Composer 2.5 is sufficient.

## Phase 4D — LQI trend intelligence

### Goal

Add cautious per-device LQI trend decisions.

### Suggested branch

```text
feat/lqi-trend-decisions
```

### Logic guidance

Start device-first, not pairwise correlation.

Require:

- enough samples;
- bounded lookback;
- trend/window comparison;
- current issue or other useful evidence before escalation.

Avoid:

- RF root-cause claims;
- single-sample decisions;
- pairwise LQI correlation initially.

### Acceptance criteria

- Trend decisions are suppressed when sparse.
- Wording says reported link quality changed/dropped, not that the network path failed.
- Decisions feed device story and reports later.

### Composer model

Composer 2.5 for implementation, 4.5 for review if trend thresholds are unclear.

## Phase 4E — Availability event groups

### Goal

Turn broad availability storms into useful shared-event cards without creating pairwise false hints.

### Suggested branch

```text
feat/availability-event-groups
```

### Logic guidance

Existing passive pair hints exclude windows touching many devices. Those windows are still useful as shared events.

A shared event card can say:

```text
7 devices went offline within 4 minutes.
This looks like a shared event rather than a pairwise device relationship.
```

Suggested checks:

```text
Check Zigbee2MQTT, MQTT broker, host restart, power or maintenance around that time.
```

### Acceptance criteria

- Network-wide windows become event groups, not pairwise links.
- No cause inferred.
- Cards appear in overview/Mesh/report when useful.

### Composer model

Composer 2.5 is sufficient.

## Phase 4F — Router area intelligence

### Goal

Add observed router-area review decisions.

### Suggested branch

```text
feat/router-area-intelligence
```

### Input evidence

- latest topology links;
- recent missing links;
- last-known links;
- route hints;
- current device issues;
- passive hints;
- HA areas when available.

### Required wording

Use:

```text
Observed router area
Review {router/area}
Devices recently observed around this router
```

Avoid:

```text
Parent router
Caused by router
Route through router
Current path
```

### Acceptance criteria

- Router-area cards are action-led.
- Router evidence appears in Mesh where investigation happens.
- No standalone router-risk truth source is required.

### Composer model

Composer 2.5 can implement. Use 4.5 for final review if many evidence sources combine.

## Phase 4G — Model/manufacturer pattern intelligence

### Goal

Detect cautious model/manufacturer patterns.

### Suggested branch

```text
feat/model-pattern-decisions
```

### Logic guidance

Require:

- minimum group size;
- minimum affected count;
- bounded lookback;
- no blame language.

Example:

```text
3 of 5 devices with this model have gone offline in the last 7 days.
```

This is a pattern to review, not proof the model is bad.

### Acceptance criteria

- Patterns are suppressed for tiny sample sizes.
- Useful in overview/reports/device story.
- No manufacturer blame.

### Composer model

Composer 2.5 is sufficient.

---

# Phase 5 — Whole-app decision migration

Phase 5 spreads the shared decision engine beyond topology.

## Phase 5A — Overview dashboard

### Goal

Overview becomes a decision-priority page, not a count dashboard.

### Target sections

- What needs attention now;
- What changed since last visit;
- Data coverage warnings;
- Recent shared events;
- Top investigation cards.

### Implementation guidance

1. Add overview decision endpoint/service if needed.
2. Reuse decisions from device story/investigations.
3. Link into Mesh/device story.
4. Keep raw counts secondary.

### Acceptance criteria

- Overview does not independently explain device health.
- It links to the correct investigation surface.
- It does not become a mini Mesh page.

### Composer model

Composer 2.5 for implementation. Use 4.5 for review if surfacing priorities is contentious.

## Phase 5B — Devices page

### Goal

Devices page becomes inventory/search/filter with decision badges.

### Target columns/fields

- device name;
- decision badge;
- availability/data coverage;
- battery/LQI summary;
- last seen;
- area/model;
- link to device story/Mesh focus.

### Acceptance criteria

- No separate device-health prose.
- Filters use decision output where possible.
- Clicking opens device story/details.

### Composer model

Composer 2.5 is sufficient.

## Phase 5C — Incidents page

### Goal

Incidents become decision/event records, not a competing truth source.

### Implementation guidance

- Incidents should reference shared decisions/reasons where possible.
- Existing incident history remains readable.
- Incident page copy should not introduce different status meaning.

### Acceptance criteria

- Device story and incidents agree.
- Reports and incidents agree.
- Existing incidents are handled safely.

### Composer model

Composer 2.5, 4.5 for review if migration of old incident language is subtle.

## Phase 5D — Reports and exports

### Goal

Reports consume decision output and match UI decisions.

### Target report sections

- Summary;
- What to check first;
- Device stories;
- Data coverage;
- Evidence;
- Limitations;
- Suggested checks.

### Implementation guidance

1. Add report presenter that consumes decision bundles.
2. Keep report schema compatibility.
3. Add report parity tests against UI/ViewModel decision outputs.
4. Move report creation toward contextual actions.

### Acceptance criteria

- Same decision/status/reasons as UI.
- No report-only interpretation.
- Stored reports remain readable.

### Composer model

Composer 2.5 can implement pieces. Use 4.5 for architecture/review.

## Phase 5E — HACS / HA companion surfaces

### Goal

Only after Core/UI decisions are consistent, expose shared decisions in HA companion surfaces.

### Guardrails

- read-only;
- no entity churn without explicit plan;
- no separate HA wording model;
- no control/mutation.

### Acceptance criteria

- HACS displays same statuses as Core.
- Compatibility handled by version/API checks.

### Composer model

Composer 2.5 if well-scoped. Use 4.5 for compatibility planning.

---

# Phase 6 — UX pruning and navigation consolidation

Phase 6 removes/demotes old paths after replacements exist.

## Phase 6A — Navigation simplification

### Status

Implemented on `refactor/navigation-consolidation` (awaiting review): shared
primary/advanced navigation model, canonical `/investigate` routes, legacy
graph redirect, Advanced & support disclosure.

### Goal

Move navigation toward:

```text
Overview
Mesh / Investigate
Devices
Incidents
Reports
Settings
```

with supporting routes under Advanced & support.

### Acceptance criteria

- No duplicate primary topology/snapshot/compare routes.
- Advanced/debug views remain reachable but secondary.
- Mesh / Investigate is clearly the investigation workspace.
- `/investigate` is a network chooser; `/investigate/:networkId` hosts the
  existing evidence graph.
- `/topology/:networkId/graph` remains compatible via client redirect.

### Composer model

Composer 2.5 is sufficient.

## Phase 6B — Router UX consolidation

### Status

Implemented on `refactor/router-area-ux` (awaiting review): standalone router
page removed; `/routers` compatibility redirect; Mesh router-area focus and
existing NodeDrawer integration; Core/API/HACS/report router facts retained.

### Goal

Fold router-risk UX into observed router-area review in Mesh / Investigate.

### Acceptance criteria

- Router data remains.
- Separate router-risk page is removed; `/routers` stays as a compatibility redirect.
- Router intelligence appears in Mesh/investigation via backend
  `router_neighbourhood_review` cards.
- Focus does not mutate layout, presets, or connection controls.

### Composer model

Composer 2.5 is sufficient.

## Phase 6C — Snapshot UX consolidation

### Goal

Make device snapshot history primary and raw snapshots advanced.

### Status

Completed on `refactor/snapshot-ux-consolidation`.

### Acceptance criteria

- Device Detail hosts first-class Snapshot history after Device Story.
- NodeDrawer no longer fetches or renders complete snapshot history; it links to full Device Detail.
- `/topology` is an Advanced/support landing without auto-redirect.
- `/topology/:networkId` is exact raw point-in-time detail with collapsed raw contents.
- Raw snapshot table/detail remains accessible for support; Overview does not promote it.
- Retained raw snapshots remain readable when `topology.enabled` is false; capture actions require enabled and manual capture.
- Landing cards and raw detail present truthful snapshot status (complete / limited / pending / error / unknown).
- Background refresh failures keep last accepted Device Detail history and raw detail visible with retry.
- Whole-network compare remains debug-only.
- No primary network-diff UX returns.
- Manual capture remains on support surfaces.
- Phase 6D contextual reports are complete.

### Composer model

Composer 2.5 is sufficient.

## Phase 6D — Reports UX consolidation

### Goal

Make report creation contextual and Reports page saved-history oriented.

### Status

**Complete.** Shared `ContextualReportDialog` + `ContextualReportTarget` request
builder; contextual actions on Device / Incident / Network / Mesh; Reports is
Saved reports + Create full report; client-only Mesh export removed from
production.

### Acceptance criteria

- Device/investigation/Mesh surfaces expose contextual export actions.
- Reports page lists saved/generated evidence summaries.
- No duplicate report wizard interpretation.

### Composer model

Composer 2.5 for implementation, 4.5 for final workflow review if needed.

---

# Phase 7 — Hardening, performance and release quality

Phase 7 makes the decision-engine product release-quality.

## Phase 7A — Query/index performance

### Goal

Make Beast-sized networks fast and predictable.

### Status

Implemented on `perf/release-query-bounds` (awaiting review; no PR until requested).

### Delivered

- additive incident `order=lifecycle|recent` with Overview `order=recent` (PR #83);
- bulk latest topology snapshots for overview/status;
- SQL-limited device snapshot-history window + bulk links;
- EXPLAIN-proven indexes in migration `013_query_performance_indexes.sql`;
- metric `sampled_at DESC, id DESC` + device-time index;
- offline-only availability read for shared-availability instability events;
- Track 5 baselines frozen; Phase 7A tip published (execute/commit cardinalities unchanged).

### Acceptance criteria

- No obvious N+1 loops.
- Device details and snapshot history remain responsive.
- Decision APIs have bounded lookbacks.

### Composer model

Composer 2.5 for indexing/query changes. Use 4.5 for performance investigation if measurements are confusing.

## Phase 7B — Test architecture

### Status

**Implemented on `test/release-quality-architecture`.** See `docs/test-architecture.md`.

### Goal

Add tests at the right layers.

### Test layers

- decision tests;
- coverage tests;
- reason-code tests;
- ViewModel tests;
- component render tests;
- report parity tests (ReportDetailV3; client Mesh exporter retired);
- forbidden wording sweeps;
- API compatibility tests (`/api` ↔ `/api/v1`);
- canonical oracle fixture corpus + freshness gate;
- fast contract lane: `scripts/validate-contracts.sh`.

### Acceptance criteria

- Same decision renders consistently in UI and reports.
- Unknown values never become zero.
- Forbidden wording does not return in primary copy.
- Ordinary UI unit tests do not spawn Core Python.
- Fixture freshness remains an explicit Core/contract validation gate.

### Composer model

Composer 2.5 is sufficient.

## Phase 7C — Documentation/screenshots

### Goal

Update docs and screenshots to match the new product.

### Work

- README positioning;
- architecture docs;
- topology docs;
- screenshots;
- safety docs;
- add-on/HACS docs if affected.

### Acceptance criteria

- Docs reflect current defaults.
- Screenshots show central workflows.
- Decision-engine wording appears in user-facing docs.

### Composer model

Composer 2.5 is sufficient.

## Phase 7D — Deployment validation

### Goal

Validate on the live Beast network.

### Smoke scenarios

- healthy router;
- problem sensor;
- battery sleepy device;
- device with no latest links;
- router area with many devices;
- availability history building;
- route hints available/unavailable;
- report export;
- graph selection/layout persistence.

### Acceptance criteria

- Decisions feel sane on real data.
- Nothing moves unexpectedly in graph.
- No accidental Zigbee/MQTT writes.
- Reports match UI.

### Composer model

Composer 2.5 for fixing issues. Use 4.5 for diagnosing unexpected cross-cutting behaviour.

---

# Cursor execution prompt

Use this prompt to start a focused sub-phase:

```text
Read these docs first:
- docs/decision-engine.md
- docs/ux-pruning.md
- docs/decision-engine-migration.md
- docs/decision-engine-phase-0.md
- docs/decision-engine-implementation-plan.md
- docs/ubiquitous-language.md
- docs/architecture.md
- docs/safety-audit.md

Work on Phase <PHASE> only: <PHASE NAME>.

Do not broaden scope. Do not implement later phases. Do not change runtime behaviour unless the phase explicitly requires it.

Before editing:
1. Inspect the current code paths and tests relevant to this phase.
2. State the planned files to change.
3. Identify affected golden fixtures.
4. Identify checks to run.

While editing:
- preserve read-only guardrails;
- do not add causal claims;
- do not render unknown values as zero;
- do not add primary UX surfaces that compete with Mesh/Device details;
- keep reports aligned with UI decisions when reports are affected.

After editing:
1. Run the relevant checks.
2. Self-review the diff against docs/decision-engine-implementation-plan.md.
3. Grep for forbidden wording and review any matches in context.
4. Update docs/migration status if the phase changes the target state.
5. Prepare a PR body using the required checklist.
```

## Cursor review prompt

Use this after Cursor makes changes:

```text
Review the current diff against:
- docs/decision-engine.md
- docs/ux-pruning.md
- docs/decision-engine-migration.md
- docs/decision-engine-phase-0.md
- docs/decision-engine-implementation-plan.md
- docs/ubiquitous-language.md
- docs/safety-audit.md

Check specifically:
- Does this PR stay inside its named phase?
- Did any component start making diagnostic decisions locally?
- Did any report, incident or UI surface introduce competing wording?
- Did unknown data become zero?
- Did raw counts lead a primary diagnostic surface?
- Did any copy imply parent router, live route, current route or cause?
- Did any MQTT/Zigbee/Home Assistant mutation behaviour change?
- Did any graph layout/localStorage behaviour change unintentionally?
- Are tests added at the right layer?
- Are performance bounds still reasonable for Beast-sized networks?

Return:
1. must-fix issues;
2. should-fix issues;
3. safe follow-ups;
4. checks run and missing checks;
5. whether the PR is aligned with the decision-engine programme.
```

## Stop conditions

Cursor should stop and ask for human review if:

- a phase requires changing MQTT publish/subscription behaviour;
- a phase requires changing topology capture scheduling;
- a schema migration risks existing DB compatibility;
- a UI workflow needs product judgement not covered by these docs;
- implementation would require merging multiple phases;
- tests suggest current product behaviour differs from the docs;
- performance requires unbounded scans;
- report compatibility is unclear;
- HACS/add-on compatibility is unclear.

## Final principle

Every PR should answer:

```text
Does this make ZigbeeLens more useful and actionable,
or does it merely expose more information?
```

If it merely exposes more information, redesign it or move it to Advanced/debug.
