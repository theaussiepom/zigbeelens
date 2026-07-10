# ZigbeeLens Decision Engine

This document defines the product and architecture contract for the ZigbeeLens decision engine.

It is intentionally specific. Future implementation phases should be judged against this document, not against a watered-down interpretation of it.

## North star

ZigbeeLens should help the user decide:

- what is worth checking;
- why it is worth checking;
- what evidence supports that judgement;
- what data is missing or incomplete;
- what the evidence does not prove; and
- what practical next check makes sense.

ZigbeeLens should not merely expose every fact it has collected.

Good:

> This device is worth reviewing. Latest snapshot shows no links for this device, the selected earlier snapshot showed six links, and the device currently needs attention. This does not prove the device moved, failed, or changed live route.

Bad:

> 105 new neighbour edges, 92 missing edges, 43 route hints changed.

The second example may be technically true, but it is not the product we are building.

## Scope

The decision engine is repo-wide. It is not a topology-only feature.

Topology is the first migration target because it currently contains the most evidence interpretation and the highest risk of UI-level judgement drift. However, the engine must eventually serve:

- Overview dashboard;
- Devices page;
- Device details panel;
- Incidents;
- Mesh / topology view;
- Reports and exports;
- HACS companion surfaces; and
- any future Home Assistant companion panels or repairs.

## Core pipeline

The intended architecture is:

```text
Stored evidence
  -> Evidence facts
  -> Decision engine
  -> View models / report models
  -> Screens
```

Screens render decisions. Screens do not independently decide what evidence means.

## Definitions

### Stored evidence

Raw or normalised data already collected and persisted by ZigbeeLens.

Examples:

- `devices`
- `device_current_state`
- `device_snapshots`
- `events`
- `metric_samples`
- `availability_changes`
- `health_snapshots`
- `incidents`
- `incident_devices`
- `topology_snapshots`
- `topology_nodes`
- `topology_links`
- `ha_device_enrichment`
- `reports`

Stored evidence is not itself a decision.

### Evidence fact

A neutral, typed statement derived from stored evidence.

Examples:

- latest topology snapshot is complete;
- latest topology snapshot is stale;
- device is currently reported offline;
- device has no links shown in the latest snapshot;
- device had links shown in a selected earlier snapshot;
- device has battery samples;
- device has no battery samples;
- availability history started after the selected snapshot;
- HA area enrichment is not linked;
- route hints are unavailable for this network/window.

Evidence facts must not contain root-cause claims.

### Decision

A reusable diagnostic judgement produced from evidence facts.

Examples:

- `worth_reviewing`
- `watch`
- `changed`
- `no_notable_change`
- `review_first`
- `improve_data_coverage`

A decision must include:

- status or priority;
- reason codes;
- supporting evidence references;
- limitations;
- suggested checks when useful; and
- data coverage context where it affects interpretation.

### Reason

A structured explanation for a decision.

Reasons should be represented as stable codes with optional parameters, not only as prose.

Example:

```json
{
  "code": "latest_snapshot_no_links",
  "params": {
    "selected_snapshot_link_count": 6
  }
}
```

The frontend or presenter layer maps this to user-facing copy.

### Limitation

A statement about what the evidence cannot prove or why interpretation is constrained.

Examples:

- topology snapshots are point-in-time evidence;
- route hints do not prove current live routing;
- passive-derived hints are not topology evidence;
- availability tracking was off for the selected period;
- battery history is sparse;
- HA area enrichment is not linked.

Limitations should appear only when they affect what the user should believe or do.

### Suggested check

A practical, non-causal next action.

Good suggested checks:

- confirm the device is powered;
- check whether the device is reporting in Zigbee2MQTT;
- compare with another earlier snapshot;
- check whether Zigbee2MQTT, MQTT broker, host restart, power or maintenance occurred around a shared availability event;
- enable Zigbee2MQTT availability and last-seen reporting.

Bad suggested checks from weak evidence:

- re-pair the device;
- move the router;
- replace the device;
- reboot Zigbee2MQTT;
- change channels;
- assume a parent router changed.

Those may sometimes be reasonable human actions, but ZigbeeLens should not suggest them from weak evidence alone.

### Data coverage

A structured statement about whether ZigbeeLens has enough data to support a decision.

Coverage is not a generic degraded state. It must be specific and actionable.

Examples:

- Availability tracking off
- Availability history building
- Availability status unknown
- Route hints unavailable
- HA areas not linked
- Topology snapshot stale
- Battery history sparse
- LQI history sparse

## Decision ownership rule

Any UI surface that displays a diagnostic judgement, suggested check, evidence limitation, status pill, or "worth reviewing" decision must consume a ViewModel or report model backed by the decision engine.

A React component may render:

- a label;
- a pill;
- a section;
- a list of reasons;
- a suggested check;
- an evidence detail row.

A React component must not independently decide:

- whether something is worth reviewing;
- whether something should be watched;
- whether availability tracking is off;
- whether data coverage is sufficient;
- whether a reason matters;
- whether a suggested check should appear; or
- what raw facts are important enough to lead the UI.

## Backend architecture rule

Backend routes should not assemble product judgement.

Preferred flow:

```text
Repository / query layer
  -> evidence fact builder
  -> decision service
  -> presenter / API DTO builder
  -> FastAPI route
```

Routes validate inputs, call services, and return DTOs.

Routes should not directly orchestrate multiple intelligence layers when that orchestration is product logic.

## Frontend architecture rule

Preferred flow:

```text
API DTO
  -> ViewModel builder
  -> component
```

ViewModels own:

- display labels;
- pill tone;
- section order;
- row text;
- empty-state text;
- which evidence details are collapsed;
- which actions are shown; and
- whether raw counts are secondary.

Components own:

- rendering;
- layout;
- keyboard/accessibility mechanics;
- local UI affordances such as expand/collapse state where that state does not change meaning.

## Copy ownership

Backend decision services should prefer reason codes and structured data.

User-facing copy should be mapped through presenters/ViewModels and must follow `docs/ubiquitous-language.md`.

This prevents drift such as:

- graph says `Worth reviewing`;
- device page says `Needs attention`;
- report says `Watch`; and
- incident says `Diagnostics limited`.

One decision may be displayed in many places, but the diagnostic meaning must be shared.

## Decision status vocabulary

These are shared concepts. Individual screens may use narrower labels, but must not invent competing meanings.

| Status / priority | Meaning | Notes |
|---|---|---|
| `no_notable_change` | Comparison or recent history does not show anything useful to review. | Not a device-health claim. |
| `changed` | Evidence changed, but there is no strong action signal. | Useful for snapshot/device comparison. |
| `watch` | Something is worth keeping an eye on or checking if symptoms continue. | Non-alarmist. |
| `worth_reviewing` | Evidence is strong enough to inspect this device/area/context. | Not root cause. |
| `review_first` | Highest-priority investigation card. | Still not root cause. |
| `improve_data_coverage` | The useful next step is enabling or improving data sources. | Example: availability tracking off. |
| `informational` | Helpful context only. | Should not crowd primary UI. |

Forbidden as decision statuses unless separately justified by an existing health classifier:

- bad;
- broken;
- failed;
- caused by;
- parent router;
- live route;
- current route;
- actual path.

## Evidence hierarchy

When a decision exists, UI and reports should order content as:

1. decision;
2. why;
3. what this means;
4. suggested checks, only when useful;
5. evidence details;
6. raw counts / source details.

Raw counts must not lead a diagnostic surface unless the explicit purpose of the surface is advanced/debug inspection.

## Useful silence

If there is no useful decision, ZigbeeLens should often show nothing rather than reassuring filler.

Do not add empty sections just to prove data was checked.

Good empty states:

- selected filter has no matching results;
- user-enabled evidence layer has no available evidence;
- a required data source is unavailable;
- no topology snapshot exists yet;
- snapshot history has no earlier usable snapshots.

Bad empty states:

- repeating that every healthy device has no passive hints;
- showing zero counts for data that was not tracked;
- saying "limited" without naming the missing source and action.

## Guardrails

The decision engine must preserve ZigbeeLens safety boundaries:

- no Zigbee control commands;
- no MQTT writes except explicitly allowed existing discovery/topology behaviours;
- no new MQTT subscription behaviour without an explicit phase decision;
- no topology scheduler changes unless a phase explicitly targets capture policy;
- no HACS mutation behaviour;
- no Home Assistant entity churn;
- no causal diagnosis from weak evidence;
- no parent-router inference;
- no current/live route claims;
- no unknown-as-zero;
- no generic AI insight copy;
- no graph-for-graph's-sake.

## Product test

Every future PR in this programme must answer:

> Does this make ZigbeeLens more useful and actionable, or does it merely expose more information?

If it merely exposes more information, the PR is not aligned unless it is explicitly an advanced/debug support surface.

## Future PR checklist

Every implementation PR in the decision-engine programme should include:

```text
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

This checklist is part of the architecture contract, not optional PR decoration.
