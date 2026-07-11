# UX pruning contract

This document defines how ZigbeeLens will reduce duplicated diagnostic UX while strengthening the Mesh / investigation workflow and the shared decision engine.

Pruning in this programme does not mean deleting useful evidence. It means giving each surface a clear role so users are not asked to interpret the same problem through several competing pages.

## Product direction

ZigbeeLens is moving from:

```text
many pages showing different slices of evidence
```

to:

```text
one shared decision engine surfaced through a few clear workflows
```

The Mesh / topology workspace becomes the main investigation surface. Device details becomes the main decision surface.

## Primary UX model

| Surface | Target role | Must not become |
|---|---|---|
| Overview | What needs attention now; what changed since last visit; top decision-engine priorities. | A second mesh graph or a competing health explanation engine. |
| Mesh / Investigate | Main investigation workspace: where to look first, why, relevant topology/passive/history context. | A raw topology dump or graph-for-graph's-sake surface. |
| Device details | Device story, current decision, data coverage, useful evidence and suggested checks. | A list of every fact ZigbeeLens knows. |
| Devices | Inventory, search, filtering and decision badges. | A parallel diagnostic interpretation layer. |
| Incidents | Event/issue history tied to shared decisions. | A separate truth source with different wording/statuses. |
| Reports | Contextual evidence summaries and saved report history. | A report wizard that duplicates app interpretation. |
| Settings / Advanced | Configuration, raw/debug/supporting data. | A primary investigation workflow. |

## Navigation target

Preferred future navigation:

```text
Overview
Mesh / Investigate
Devices
Incidents
Reports
Settings / Advanced
```

A more aggressive future option is:

```text
Overview
Investigate
Devices
Reports
Settings
```

The first option is safer during migration. The second may be appropriate after the decision engine owns more surfaces.

## Pruning principles

### 1. Demote raw data, do not delete it

Raw snapshots, whole-network compare, detailed edge controls and protocol-like views are valuable for debugging and support. They should move under Advanced or collapsed details, not disappear.

### 2. One decision, many presentations

If the device is `worth_reviewing`, every surface that mentions that device must derive the judgement from the same decision output.

### 3. Topology is an input, not a separate truth system

Topology should enrich decisions. It should not create a competing product language or separate diagnostic status model.

### 4. Device details is the decision centre

The selected device panel should answer:

- what is happening with this device;
- why it may or may not be worth checking;
- what data supports that;
- what data is missing;
- what not to infer; and
- what to check next.

### 5. Mesh is the investigation workspace

The graph should help users explore relationships and evidence context after the decision engine has told them where to look first.

### 6. Reports are contextual outputs

Reports should be created from the thing the user is already investigating:

- copy evidence for this device;
- copy investigation summary;
- download network evidence summary;
- export report for an incident.

Reports should not require a separate wizard to recreate the same interpretation choices.

## Surface inventory and target disposition

| Current / possible surface | Current role | Target role | Disposition |
|---|---|---|---|
| Overview dashboard | Summary counts and health. | Top decisions, recent changes, data coverage warnings. | Keep primary; migrate to decision output. |
| Devices page | Inventory and device statuses. | Inventory/search/filter with decision badges. | Keep primary; remove independent diagnostic prose. |
| Device detail endpoint/page/panel | Per-device facts. | Device story and decision surface. | Keep primary; strengthen. |
| Incidents page | Open/watching/resolved issues. | Decision/event history tied to device story and reports. | Keep supporting; avoid competing status language. |
| Reports page | Report creation/history. | Report history and saved exports. | Demote creation into contextual actions. |
| Topology overview | Snapshot list / topology summary. | Entry to Mesh plus advanced snapshot support. | Keep supporting; reduce prominence. |
| Mesh evidence graph | Evidence visualization. | Main investigation workspace. | Keep primary; centralise. |
| Snapshot history | Device-led compare. | Device story section and decision input. | Keep primary inside device details. |
| Raw topology snapshots | Debug/support. | Advanced snapshot history. | Move/demote under Advanced. |
| Whole-network snapshot compare | Network-wide diff. | Debug endpoint only unless a new real workflow appears. | Remove from primary UX. |
| Router/risk views | Router health/risk summary. | Router-area intelligence in Mesh. | Merge/demote. |
| Connection controls | Fine-grained graph rendering. | Advanced “Draw more links”; presets first. | Collapse/demote. |
| Graph legend | Style explanation. | Contextual or collapsed reference. | Keep but secondary. |
| HACS companion panel | Home Assistant entry/summary. | Same decision status as Core, minimal companion surface. | Keep later; must consume shared decisions. |
| MQTT Discovery summary entities | HA summary. | High-level read-only summary only. | Keep; do not expand into complex HA entity model without explicit plan. |
| Health/status/config endpoints | Operational support. | Advanced/status/support. | Keep; not a product diagnostic surface. |

## Explicit pruning decisions

### Router page / router risk

Router risk should be folded into router-area intelligence.

A router is diagnostically useful when viewed with:

- devices recently observed in that router area;
- devices with current issues nearby;
- last-known links involving that router;
- route hints involving that router;
- passive instability groups around that router; and
- HA area context when available.

Target user-facing concept:

```text
Review router area
```

Avoid:

- parent router;
- responsible router;
- root cause router;
- current route via router.

### Raw topology snapshots

Raw snapshots should be advanced/supporting. The primary workflow is device-led snapshot history.

Keep:

- raw snapshot list;
- snapshot detail;
- complete/failed status;
- capture time;
- troubleshooting access.

Demote:

- raw snapshot tables as a primary navigation target;
- raw counts as leading diagnostic copy.

### Whole-network snapshot compare

Whole-network compare should remain an advanced/debug endpoint, not primary UX.

Rationale: network-level diffs can be technically true but operationally noisy on large meshes. Device-led compare is the useful product flow.

### Reports

Reports should be contextual first.

Target actions:

- `Copy evidence for this device`;
- `Copy investigation summary`;
- `Download network evidence summary`;
- `Export incident evidence`.

The Reports page becomes saved report/export history.

### Devices page

The Devices page should show decision-engine badges and sortable/filterable facts. It should not contain separate explanatory health copy.

Good:

```text
Bathroom sensor · Worth reviewing · Availability history building
```

Bad:

```text
Bathroom sensor has a topology problem because no links are shown.
```

### Incidents page

Incidents remain useful, but they must reference the same decision facts and reason codes as device details, Mesh and reports.

No incident-only language drift.

### Graph controls

Replace exposed complexity with presets first.

Presets:

- Troubleshooting;
- Router review;
- Battery devices;
- Quiet view;
- Full snapshot links.

Detailed controls move behind:

```text
Draw more links
```

Existing controls should remain available during migration but not dominate the default UX.

## Target Mesh workspace

The Mesh workspace should answer:

- where should I look first;
- what devices are involved;
- what evidence context matters;
- what changed for this device;
- what ZigbeeLens cannot know yet; and
- what practical check makes sense.

It should not start by asking the user to understand edge classes.

## Target Device details panel

The Device details panel should eventually order content as:

1. Device story summary;
2. Current status / decision;
3. Why this is worth checking or not;
4. Recent activity;
5. Snapshot history;
6. Data coverage;
7. Evidence details;
8. Open incidents/issues;
9. Export/copy evidence action.

Sections with no useful content should be omitted.

## Advanced/debug policy

Advanced/debug surfaces are allowed, but must be labelled honestly.

They may lead with raw data because that is their explicit role.

They must not be promoted as the normal investigation path.

## UX deletion/deprecation register

| Surface / functionality | Target action | Replacement workflow | Phase |
|---|---|---|---|
| Primary whole-network compare UI | Remove/demote. | Device-led snapshot history. | Phase 3 / already started. |
| Router-risk standalone UX | Merge/demote. | Router-area review decisions in Mesh. | Phase 4F / 6B. |
| Raw snapshot table as primary route | Demote. | Advanced snapshot history. | Phase 6C. |
| Report wizard as primary creation path | Demote. | Contextual report/export actions. | Phase 5D / 6D. |
| Exposed graph edge toggles as default UX | Collapse behind presets. | Troubleshooting/router/battery/quiet/full presets. | Phase 3F. |
| Duplicate device health prose on Devices page | Remove. | Decision badges and device story links. | Phase 5B. |

## Success criteria

This UX pruning is successful when:

- users know where to start;
- raw evidence remains accessible but secondary;
- Mesh is the investigation workspace;
- Device details is the decision surface;
- Reports say the same thing as the UI;
- Incidents do not use competing diagnostic language;
- Router intelligence appears where investigation happens; and
- enabling more evidence sources makes the product more useful rather than more cluttered.
