# Decision Engine Phase 0 governance

This document contains the operational detail for Phase 0 of the ZigbeeLens decision-engine programme.

It is deliberately concrete. It defines what must be inventoried, owned, preserved, demoted, tested and measured before implementation work begins.

Related documents:

- [decision-engine.md](decision-engine.md)
- [ux-pruning.md](ux-pruning.md)
- [decision-engine-migration.md](decision-engine-migration.md)
- [ubiquitous-language.md](ubiquitous-language.md)

## Phase 0 purpose

Phase 0 prevents the decision-engine programme from becoming a loose set of refactors.

It defines:

- current surfaces;
- decision ownership;
- data-source usefulness;
- UX pruning decisions;
- cross-repo impact;
- compatibility rules;
- performance budgets;
- golden fixtures;
- copy hierarchy; and
- rollout gates.

## 0D — Surface inventory

| Surface | Type | Current purpose | Target purpose | Disposition |
|---|---|---|---|---|
| Overview dashboard | UI | High-level status and counts. | What needs attention now, recent changes, data coverage warnings, top decision priorities. | Keep primary; migrate to decision engine. |
| Network summary / topology overview | UI/API | Show topology availability and latest snapshot summary. | Entry point to Mesh and advanced snapshot support. | Keep supporting; reduce diagnostic authority. |
| Mesh evidence graph | UI/API | Visualize latest topology, recent history, last-known links, passive hints and investigation cards. | Main investigation workspace. | Keep primary; migrate first. |
| Device search | UI | Find/select graph devices. | Command-like search and filter over decision outputs. | Keep; strengthen later. |
| Device details panel | UI | Show device summary, status, stats, topology, snapshot history, passive hints, open issues. | Main device story and decision surface. | Keep primary; migrate early. |
| Snapshot history | UI/API | Device-led comparison with earlier snapshots. | ViewModel-backed section and decision-engine input. | Keep; migrate early. |
| Raw topology snapshots | UI/API | Snapshot list/detail/debug. | Advanced snapshot history. | Demote to Advanced. |
| Whole-network snapshot compare | API/debug | Compare two topology snapshots at network level. | Debug/support only unless a concrete user workflow appears. | Keep endpoint; no primary UX. |
| Connection controls | UI | Toggle edge classes and rendering subsets. | Presets first; detailed toggles behind `Draw more links`. | Keep but demote. |
| Graph legend | UI | Explain edge/node styles. | Contextual/collapsed reference. | Keep but secondary. |
| Investigation cards | UI/API | Backend-ranked topology/passive investigation cards. | Action-grouped decision output. | Keep; migrate to decisions. |
| Devices page | UI/API | Inventory and current device statuses. | Inventory/search/filter with decision badges. | Keep primary; remove independent diagnostic prose. |
| Device detail API/page | API/UI | Per-device facts. | Device story / decision source. | Keep; migrate. |
| Incidents page | UI/API | Open/watching/resolved incidents. | Decision/event history tied to device story and reports. | Keep supporting; align language. |
| Reports page | UI/API | Preview/create/store/download reports. | Saved report/export history. Contextual creation lives on device/investigation/mesh surfaces. | Keep supporting; demote creation workflow. |
| Report download formats | API | JSON/YAML/Markdown report output. | Same decisions as UI, rendered as evidence summaries. | Keep; migrate to decision-backed sections. |
| Config/status endpoints | API | Service configuration and operational status. | Advanced/status support. | Keep; not diagnostic product surface. |
| Health endpoint | API | Runtime health and subsystem state. | Operational status only. | Keep. |
| MQTT Discovery summary entities | HA/MQTT | Optional HA summary entities. | Minimal read-only summary only. | Keep; do not expand without explicit phase. |
| HA enrichment endpoint | API | Accept HA area/name enrichment. | Evidence source for area-led decisions. | Keep; make more useful later. |
| HACS integration | HA | Companion panel/entities/diagnostics. | Display shared decision statuses after Core is consistent. | Keep later; must not create separate decision language. |
| Add-on config / docs | Deployment | HAOS packaging/config. | Must reflect decision-engine docs where user-facing. | Update during release phases. |
| Docker examples | Deployment | Standalone deployment. | Must preserve local/read-only defaults. | Update only when needed. |

### Surface inventory rule

A future PR that touches a surface must state whether that surface is:

- primary;
- supporting;
- advanced/debug;
- being merged into another workflow;
- being demoted; or
- being deprecated later.

## 0E — Decision ownership matrix

| Decision / label / action | Owner | Rendered by | Notes |
|---|---|---|---|
| `Worth reviewing` | Decision engine | ViewModel/component/report presenter | Must not be invented by component. |
| `Watch` | Decision engine | ViewModel/component/report presenter | Context-specific, non-alarmist. |
| `No notable change` | Decision engine | ViewModel/component/report presenter | Not a health claim. |
| `Changed` | Decision engine | ViewModel/component/report presenter | Evidence changed, not necessarily actionable. |
| `Review first` | Decision engine | ViewModel/component/report presenter | Investigation priority, not root cause. |
| `Availability tracking off` | Coverage model | ViewModel/component/report presenter | Red/direct/actionable. |
| `Availability history building` | Coverage model | ViewModel/component/report presenter | Amber/direct/actionable. |
| `Availability status unknown` | Coverage model | ViewModel/component/report presenter | Grey/cautious. |
| `Route hints unavailable` | Coverage model / topology facts | ViewModel/component/report presenter | Must not imply route absence. |
| `HA areas not linked` | Coverage model / enrichment facts | ViewModel/component/report presenter | Action is HA enrichment, not network change. |
| Link counts | Evidence facts | ViewModel/component/report presenter | Raw counts are evidence details unless advanced/debug. |
| `Links shown` wording | ViewModel/presenter copy mapping | Component/report | Primary UI wording. |
| `Route hints` wording | ViewModel/presenter copy mapping | Component/report | Always qualified when easy to misread. |
| Suggested checks | Decision engine | ViewModel/component/report presenter | Practical, non-causal. |
| Pill colour/tone | ViewModel | Component | Component receives tone, does not decide meaning. |
| Layout/rendering controls | UI state/ViewModel | Component | Must not alter evidence meaning. |
| Report sections | Report presenter using decisions | Report output | Reports must not re-interpret independently. |
| Raw debug rows | Advanced/debug surface | Component | Must be labelled advanced/supporting. |

### Ownership rule

A diagnostic claim belongs to the decision engine or coverage model. A component may render it, not create it.

## 0F — Data inventory and usefulness audit

| Data source | What it tells us | What it cannot prove | Useful decisions | Coverage caveats |
|---|---|---|---|---|
| `networks` | Configured Zigbee2MQTT networks and base topics. | Device health or topology quality. | Network scoping, multi-network grouping. | Configured network may have no data yet. |
| `bridge_snapshots` | Bridge state, coordinator details, channel/PAN metadata when observed. | Cause of device issues. | Network state timeline, shared event context. | Snapshot timing may be sparse. |
| `devices` | Known inventory, role, power source, model/manufacturer, interview state. | Current availability or link quality by itself. | Inventory, model/manufacturer grouping, battery vs mains logic. | Friendly names not globally unique. |
| `device_current_state` | Latest availability, last seen, last payload, LQI, battery. | Historical behaviour unless paired with snapshots/metrics. | Current device decision, data coverage, status badges. | Current unknown is not measured stability. |
| `device_snapshots` | Historical device payload/current-state observations. | Causal changes. | Device story, expected sleepy rhythm, trend evidence. | Retention and sampling frequency matter. |
| `events` | Timeline events and parsed observations. | Root cause. | `What changed since last visit`, event timeline. | Event type quality varies. |
| `metric_samples` | Historical numeric metrics such as LQI/battery. | RF cause or exact link path. | LQI trends, battery trends, model patterns. | Sparse samples should suppress decisions. |
| `availability_changes` | Online/offline transitions. | Why a device went offline. | Availability event groups, passive hints, recent instability, coverage start. | Availability tracking may be off/building/unknown. |
| `health_snapshots` | Historical health classifications. | Independent truth separate from current evidence. | Timeline/context, report history. | Must align with decision engine as migration progresses. |
| `incidents` | Open/watching/resolved issue records. | Full root cause. | Current issue signals, report sections, device story. | Language must not drift from decisions. |
| `incident_devices` | Devices involved in incidents. | Which device caused another device's issue. | Investigation grouping and device story context. | Role labels should be cautious. |
| `topology_snapshots` | Point-in-time topology captures and status. | Live routing/current connectivity. | Snapshot freshness, snapshot history, topology coverage. | Captures are point-in-time. |
| `topology_nodes` | Devices present in a topology snapshot. | Full inventory or current online state. | Seen/not seen in snapshot, topology coverage. | Sleepy end devices may be absent normally. |
| `topology_links` | Neighbour-table and route-hint evidence at capture time. | Live route, parent router, failure if absent. | Links shown, last-known links, recent missing links, router-area context. | Missing values are unknown, not zero. |
| `ha_device_enrichment` | HA names, areas and entity context. | Zigbee health. | Area-led decisions, reports, better labels. | Optional; absence should be actionable. |
| `ha_enrichment_status` | Whether HA enrichment exists and how much matched. | Completeness of all HA context. | Data coverage/setup advisor. | Matching confidence matters. |
| `reports` | Stored redacted report output. | Current state unless regenerated. | Report history and audit. | Report schema/version compatibility matters. |
| localStorage layout keys | User graph layout choices. | Evidence meaning. | Preserve graph usability. | Must migrate carefully. |
| localStorage connection controls | User rendering choices. | Evidence availability. | Preserve graph preferences. | Controls must not alter decisions. |

### Data usefulness rule

A data source must earn product surface area by supporting a decision, suggested check, data coverage label, report section or advanced/debug workflow.

Information for the sake of information is not enough.

## 0G — Deprecation register

| Surface/functionality | Current role | Target role | Replacement workflow | Phase | Risk |
|---|---|---|---|---|---|
| Primary whole-network compare UI | Network diff panel. | Debug/support only. | Device-led snapshot history. | 3B/6C | Raw endpoint may still be useful; do not delete prematurely. |
| Router-risk standalone UX | Router-specific risk view. | Router-area review decision. | Mesh investigation card + device story. | 4F/6B | Need avoid parent/router causal wording. |
| Raw topology snapshots as primary route | Snapshot inspection. | Advanced snapshot history. | Device snapshot history + advanced detail. | 6C | Support users still need raw access. |
| Report wizard as primary report creation | User chooses report options from Reports page. | Contextual exports from device/investigation/mesh. | Reports page shows history. | 5D/6D | Existing stored reports must remain readable. |
| Detailed graph toggles as primary UX | Edge-type controls always visible. | Presets first, detail behind `Draw more links`. | Troubleshooting/router/battery/quiet/full presets. | 3F | Power users still need access. |
| Duplicate device health prose on Devices page | Independent status text. | Decision badges only. | Device story/details. | 5B | Table should remain useful at a glance. |
| Incident-only diagnostic wording | Incident page explains differently from UI/report. | Incident records reference shared decisions. | Device story/report/investigation cards. | 5C | Existing incident history may use old language. |

## 0H — Cross-repo impact map

| Area/repo | Impact | Phase notes |
|---|---|---|
| `theaussiepom/zigbeelens` core/ui | Primary implementation. | All phases. |
| HAOS add-on packaging/docs | User-facing config/docs may need updates when navigation/reporting changes. | 6/7. |
| HACS integration | Should consume shared decision statuses later; must not create separate language. | 5E. |
| MQTT Discovery | Keep summary-level unless explicitly expanded. | Later explicit phase only. |
| Docker examples | Update only if config/defaults or docs change. | 7C. |
| README/screenshots | Must reflect final navigation and decision-engine positioning. | 7C. |
| Safety audit docs | Must remain aligned with read-only guardrails. | Each phase as needed. |
| Existing live Beast deployment | Reference environment for performance and smoke tests. | 7D plus major phases. |

## 0I — Compatibility and migration rules

### API compatibility

- Additive API changes are preferred.
- Removing or repurposing existing endpoints requires an explicit deprecation note.
- Debug endpoints may remain even after primary UX removal.
- New decision APIs should include versionable shapes or clear schema boundaries.

### Report compatibility

- Stored reports must remain readable.
- If report JSON shape changes, add schema/version metadata.
- Reports must not silently reinterpret old report bodies.

### SQLite compatibility

- Schema changes require migrations.
- Migrations must preserve existing local databases.
- Retention defaults must be documented when they affect decision coverage.

### localStorage compatibility

Current known localStorage concepts include graph layout and connection controls.

Rules:

- do not reset user graph positions casually;
- do not reset connection choices casually;
- version keys when shape changes;
- preserve old keys where practical;
- provide reset controls where user preference may become confusing.

### HACS/add-on compatibility

- HACS companion surfaces must not assume new APIs until version compatibility is handled.
- Add-on docs/config must match Core defaults.
- No Home Assistant entity churn unless explicitly scoped.

### Debug endpoint policy

A debug endpoint may remain even if its UI is demoted. It must be documented as debug/supporting and must not be linked as a primary user workflow.

## 0J — Performance budgets

Beast-sized networks are the reference workload.

Initial budgets are targets, not hard CI gates yet. Future implementation PRs must state expected performance impact.

| Operation | Target | Notes |
|---|---|---|
| Initial Mesh evidence graph API | Keep current perceived performance or improve. | Must not add per-device N+1 decision work. |
| Mesh UI initial render | No noticeable regression from current graph page. | Layout must not recompute from decision-only changes. |
| Device details open | Under 300ms API time target on Beast after warm DB. | Device story may require indexed queries. |
| Snapshot history for one device | Under 200ms API time target on Beast after warm DB. | Use device-specific topology queries before scaling history. |
| Decision coverage strip | Should come from already-loaded graph/network data where possible. | Avoid extra endpoint if graph API already has facts. |
| Overview decision summary | Under 500ms API time target on Beast after warm DB. | Pre-aggregate where needed. |
| Report preview | Must not perform unbounded scans. | Scope-specific reports should bound lookbacks. |
| Availability event grouping | Bound lookback and event count. | Network-wide storm grouping must be capped. |
| LQI trend analysis | Bound samples per device/model. | Sparse samples produce no decision. |

### Performance rules

- Avoid per-device full snapshot scans in loops.
- Add repository/query methods before decision services become expensive.
- Add indexes when querying topology links by device, network, snapshot and time.
- Make lookback windows explicit.
- Unknown due to bounded data should remain unknown/limited, not zero.

## 0K — Golden test fixtures

Golden fixtures are representative scenarios used across decision, ViewModel, component and report tests.

| Fixture | Purpose | Expected product behaviour |
|---|---|---|
| Healthy router | Stable mains router with adequate data. | No noisy reassurance; appears normal unless selected. |
| Sleepy battery normal | Battery device with sparse but expected reporting. | No false incident; sleepy behaviour explained only when relevant. |
| Sleepy battery suspicious silence | Battery device silent well beyond observed rhythm. | Watch/worth reviewing depending on current issue and coverage. |
| Device no latest links but last-known links | End device absent from latest links but seen previously. | Context shown; no failure claim. |
| Availability tracking off | No availability/last-seen coverage. | Red `Availability tracking off` with enable instructions. |
| Availability history building | Tracking recently enabled. | Amber `Availability history building`, older periods not fake online/offline. |
| Availability status unknown | Some current signal but no reliable historical coverage. | Grey unknown, cautious copy. |
| Route hints unavailable | No route counts/hints. | Coverage label; no implication routes do not exist. |
| Shared availability event | Many devices offline close together. | Shared event card, not pairwise hint storm. |
| Pairwise passive instability | Two devices repeatedly offline in same small windows. | Suggested investigation link; no topology/route claim. |
| Router area with issue cluster | Several issue devices recently observed near same router area. | Router-area review card; no parent/root cause wording. |
| Model/manufacturer pattern | Multiple devices of same model show similar issue. | Pattern card if minimum group size met; no blame. |
| HA enrichment absent | No HA area data. | `HA areas not linked` coverage/action. |
| HA enrichment present | Area context available. | Area-led grouping and better report labels. |
| Snapshot stale | Latest topology snapshot older than threshold. | Snapshot stale coverage; avoid over-trusting latest links. |
| Whole-network compare noise | Many link differences across snapshots. | No primary alarm; device-led compare only. |
| Report parity | Device decision rendered in report. | Same status/reasons/limitations as UI. |

### Golden fixture rule

When a phase changes decisions, ViewModels, reports or pruning, it should state which golden fixtures are affected and add/update tests accordingly.

## 0L — Copy and visual hierarchy contract

This contract complements `docs/ubiquitous-language.md`.

### Diagnostic hierarchy

When a diagnostic decision exists, show:

1. Decision;
2. Why;
3. What this means;
4. Suggested checks, only when useful;
5. Evidence details;
6. Raw/source details.

### Raw-count rule

Raw counts must not lead a diagnostic surface unless the surface is explicitly advanced/debug.

Good:

```text
Worth reviewing
Why
- Latest snapshot shows no links for this device.
- The selected snapshot showed 6 links.
```

Bad:

```text
0 latest links, 6 selected links, 4 changed links, 2 route differences.
```

### Specific coverage rule

Use specific labels where possible:

- `Availability tracking off`
- `Availability history building`
- `Availability status unknown`
- `Route hints unavailable`
- `HA areas not linked`
- `Snapshot stale`
- `Battery history sparse`
- `LQI history sparse`

Avoid generic labels when the specific missing source is known:

- degraded;
- limited;
- partial telemetry;
- low confidence;
- insufficient evidence.

Generic limitations may still appear in evidence details when there is no more specific explanation.

### Forbidden wording reminder

Primary user-facing diagnostic copy must avoid:

- parent router;
- current route;
- live route;
- actual path;
- caused by;
- failed link;
- broken link;
- disappeared;
- lost;
- AI insight;
- inferred route;
- derived neighbour.

Technical source notes may mention protocol/source terms only when clearly secondary, for example:

```text
Source: Zigbee neighbour table from topology snapshot.
```

## 0M — Rollout strategy

Every migrated surface should follow this order:

1. behaviour-preserving refactor;
2. decision-engine-backed implementation;
3. old UX demotion/removal;
4. docs/screenshots update;
5. Beast validation.

### Rollout gates

A phase is not complete until:

- tests pass;
- copy guardrails pass;
- affected golden fixtures pass;
- read-only guardrails are confirmed;
- the PR states what it deliberately did not do;
- documentation is updated where user-facing behaviour changed.

### Beast validation scenarios

Major UX/decision phases should be smoke-tested against:

- a healthy router;
- a problem sensor;
- a battery sleepy device;
- a device with no latest links;
- a router area with many devices;
- availability history building;
- availability tracking off/unknown if reproducible;
- route hints available/unavailable;
- report export;
- graph selection/layout persistence.

## Phase 0 completion criteria

Phase 0 is complete when:

- the decision engine charter exists;
- UX pruning decisions are documented;
- the master migration roadmap exists;
- current surfaces are inventoried;
- decision ownership is explicit;
- data sources are audited for usefulness and caveats;
- deprecation/demotion is tracked;
- cross-repo impacts are named;
- compatibility rules exist;
- performance budgets exist;
- golden fixtures exist;
- copy hierarchy rules exist;
- rollout gates exist; and
- future PRs have a checklist that forces alignment.

This phase deliberately does not implement runtime code.
