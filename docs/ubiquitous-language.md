# ZigbeeLens ubiquitous language

Shared product language for the Mesh Evidence Graph and related surfaces.

ZigbeeLens should sound like a thoughtful diagnostic tool for humans: calm,
clear, evidence-first, plain-English, non-alarmist, and honest about
uncertainty when it matters. It should not sound like an AI model, a graph
theory engine, or a Zigbee protocol dump.

This document is the human-facing reference. Implementation identifiers may
differ; user-facing copy should follow the terms below.

## Voice

Prefer:

- calm, clear, evidence-first wording
- plain English a homeowner or homelab operator can act on
- practical next checks when evidence is useful
- silence when there is nothing meaningful to say

Avoid:

- AI-ish, overconfident, or root-cause language
- protocol-heavy or academic phrasing
- alarmist claims from weak evidence
- “nothing to see here” reassurance in normal views

## Principles

### 1. Evidence before interpretation

Prefer: “ZigbeeLens observed this in the latest topology snapshot.”

Not: “This device is connected to that router.”

### 2. Explain what the user can do with the information

Prefer: “This may be worth checking if the device has moved, lost power, or has weak mesh conditions.”

Not: “Historical edge detected.”

### 3. Do not turn weak evidence into strong claims

Prefer: “These devices may be worth investigating together.”

Not: “These devices are related.”

### 4. Avoid model-speak in human copy

Avoid in user-facing UI: confidence score, corroboration signal, edge class,
inference, semantic model, derived association.

Prefer: why ZigbeeLens suggested this, supporting evidence, how strong this
looks, what this does not prove.

### 5. Avoid protocol claims unless directly proven

Avoid: parent router, child device, current route, actual path, connected
through, mesh path.

Prefer: observed nearby in topology evidence, observed router neighbourhood,
route hint, latest snapshot evidence.

## Silence is better than unnecessary reassurance

Do not call out the absence of a problem unless the user explicitly asked to
inspect that category.

If there is useful evidence, show it. If there is a practical limitation,
explain it. If there is nothing meaningful to say, say nothing.

Empty states are acceptable only for explicit user intent, such as:

- a selected filter has no matching results
- a user-enabled evidence layer has no available evidence
- a required data source is unavailable
- the page cannot render because no topology snapshot exists

## Practical limitations

Show a limitation only when it changes what the user believes, checks, or
does next.

Good: explain why evidence may be incomplete, what not to infer, or what
manual check would help.

Bad: blanket disclaimers on quiet or normal states.

## Details panels

Do not use “drawer” in user-facing copy. Use:

- Device details panel
- Link details panel
- Investigation details panel
- Evidence details panel

“Drawer” may remain in component names, tests, and code comments.

### Link details panel structure

1. What this line means
2. Why ZigbeeLens drew it
3. Supporting evidence
4. What this does not prove — only when the evidence could reasonably be misread
5. Suggested checks — only when useful

### Device details panel structure

1. Device summary
2. Current ZigbeeLens status
3. Topology evidence
4. Recent missing evidence — only if present or explicitly requested
5. Suggested investigation links — only if present or explicitly requested
6. What to check next — only if useful

Only show sections that have content.

## Glossary

### Latest snapshot evidence

Evidence reported in the latest parsed Zigbee2MQTT topology snapshot.

Human-facing: **Latest snapshot evidence**

Avoid: live connection, current path, real route.

### Observed neighbour link

A neighbour relationship reported by topology evidence at capture time.

Human-facing: **Observed neighbour link**

Avoid: connected device, parent, child.

### Route hint

Route-table / next-hop evidence observed in topology data.

Human-facing: **Route hint**

Practical qualifier when needed: “This suggests possible next-hop evidence at
capture time. It does not prove current live routing.”

Avoid: current route, actual route, routed through.

### Recent missing link

A link observed in recent previous complete topology snapshots but not present
in the latest usable snapshot.

Human-facing: **Recent missing link**

Practical qualifier when needed: “This does not prove a failure.”

Avoid: lost link, broken link, dropped connection.

### Suggested investigation link

A passive-derived hint suggesting two devices may be worth investigating
together.

Human-facing: **Suggested investigation link**

Practical qualifier when needed: “This is not topology evidence and does not
prove the devices are connected.”

Avoid: inferred route, derived neighbour, same parent, cause.

### Focused view

A readable graph view that draws a useful subset of available evidence.

Human-facing: **Focused view**

Avoid: hidden, discarded, ignored, filtered out.

### Investigation priority

A ranked place to look first based on existing ZigbeeLens evidence.

Human-facing priorities: **Review first**, **Worth checking**, **Lower priority**

Practical qualifier when needed: “This is not a root-cause claim.”

Avoid: root cause, fault, failure, caused by.

### Limited topology evidence

The latest topology data is incomplete, limited, unavailable, or not enough to
support stronger claims.

Human-facing: **Limited topology evidence**

Practical qualifier when needed: “Limited evidence does not prove a fault.”

Avoid: missing means offline, no link means broken.

### Device search

Finding a device by name, IEEE address, model, manufacturer or status, then
focusing the evidence view around it. Search includes every device ZigbeeLens
knows about, not just devices drawn in the current graph.

Human-facing: **Search devices**

Known device without latest snapshot evidence: “Known device. Limited topology
evidence in the latest snapshot.”

Avoid: not found in mesh, missing means offline.

### Snapshot history (device-led snapshot compare)

Snapshot compare is device-led: it lives in the Device details panel as
“Snapshot history”, never as a whole-network diff. It answers “how does this
device look in the latest snapshot compared with earlier snapshots?” — a list
of recent usable snapshots (previous usable selected by default, older ones
selectable) and a comparison card that leads with an actionable status, then
why, what this means, suggested checks, and collapsed evidence details.

Comparison statuses (about the comparison only, never device health):
**No notable change** (row label “Similar”), **Changed**, **Watch**,
**Worth reviewing**.

Human-facing: **Snapshot history**, **links shown**, **links changed**,
**links only in latest snapshot**, **links only in selected snapshot**,
**route hints**, **selected snapshot**, **latest snapshot**

Availability coverage is stated directly, never as vague “limited data”:
**Availability tracking off** (red — with “Enable Zigbee2MQTT availability and
last-seen reporting…”), **Availability history building** (amber — tracking is
enabled but does not cover that period), **Availability status unknown**
(grey — coverage genuinely cannot be confirmed). Untracked periods never show
a fake online/offline state.

Technical terms like “Zigbee neighbour table” may appear in detail/help text
only, not as primary labels.

Avoid: neighbour evidence, topology-evidence churn, lost, missing,
disappeared, broken, failed, parent router, current route, currently routed,
caused by. Healthy/Unhealthy/Bad/Risk are not comparison statuses.

### Evidence summary report

A copyable/downloadable Markdown summary of the evidence the graph already
shows: counts, where to look first, and the selected device. Read-only,
generated client-side, never persisted. Empty sections are omitted — silence
is better than unnecessary reassurance.

Human-facing: **Create report**, **Copy summary**, **Download Markdown**,
**evidence summary**

Practical qualifier when needed: “This is an evidence summary, not a live
routing map.”

Avoid: AI report, diagnostic dump, export graph data dump.

## Forbidden user-facing phrases

Do not render these to users:

- hidden for readability
- ignored / discarded / irrelevant
- parent router / child device
- current route / currently routed / actual route / actual path
- connected through
- root cause / caused by / failed because
- broken link / lost link
- inferred route / derived route
- AI suggested / AI detected
- confidence score / semantic inference
- nothing to see / no problems found
- drawer

Developer-only identifiers, comments, and tests may still use some of these
words when they are not shown in the UI.
