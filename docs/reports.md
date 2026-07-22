# Reports

ZigbeeLens generates scoped diagnostic reports from local SQLite history and
current decision-led classification state.

## Report contract v3 (current)

Newly previewed and stored reports use **`report_version = 3`**.

Canonical fields (one representation each):

| Section | Field |
|---------|--------|
| Identity | `id`, `product`, `report_version`, `generated_at`, `version` |
| Scope / format | `scope`, `format` |
| Config | `config_summary` (includes `mode`) |
| Redaction | `redaction` (includes `profile`) |
| Decision summary | `decision_summary` (`DecisionCountSummary`) |
| Investigation | `investigation_priorities` |
| Device Stories | `device_stories` |
| Coverage | `data_coverage_warnings` |
| Incidents | `incidents` |
| Collector | `collector_status` |
| Domain facts | `domain_details` (`networks`, `devices`, `device_details`, `router_risks`, …) |
| Timeline | `events_or_timeline` (when included) |
| Limits / counts | `limitations`, `raw_counts` |
| Markdown | `markdown_summary` |

v3 bodies do **not** include Health/Lens compatibility aliases such as
`executive_summary`, `health_summary`, `health_snapshot`, `diagnostic_conclusions`,
duplicate `active_incidents` / `collector` / top-level domain arrays, or Lens
bucket tables.

Markdown is generated from the canonical decision sections (identity → decision
summary → priorities → Device Stories → coverage → incidents → factual scope →
timeline → limitations → redaction note).

## Pre-release v3-only stored reports

ZigbeeLens is still in initial development. There is **no** stored-report v1/v2
compatibility promise.

Migration **014** (`DELETE FROM reports`) clears every existing saved report once
when upgrading schema 13 → 14. That reset is intentional: development-era bodies
are discarded so the product starts from a clean exact-`ReportDetailV3` state.

After migration 014:

- every new report write uses exact integer `report_version: 3`;
- every stored report read validates exact `ReportDetailV3`;
- missing/non-integer/non-3/malformed bodies fail closed (not displayed or downloaded);
- there is one parser, one ViewModel path, and one current report contract suite.

No legacy notice, upgrade converter, or opaque historical body path remains.

## Formats

| Format | Use case |
|--------|----------|
| **JSON** | Tools, archival, programmatic analysis |
| **YAML** | Human-readable structured export |
| **Markdown** | Forums, GitHub issues, quick sharing |

Current report creation uses Core `ReportDetailV3` via `POST /api/reports`.
Creation is **contextual** (Phase 6D): the launching page fixes the target.

| Surface | Action | Scope |
|---------|--------|-------|
| Device Detail | Create device report | `device` (`network_id` + IEEE) |
| Incident Detail | Create incident report | `incident` |
| Network Detail | Create network report | `network` |
| Mesh / Investigate | Create network report | `network` (route network; not graph layout) |
| Reports | Create full report | `full` |

The **Reports** page is primarily **Saved reports** history. It does not host a
device/incident/network target wizard. Opening Create full report uses the same
shared dialog as the other surfaces (format, redaction profile, compact preview,
Save / Save and download).

The former client-only Mesh `MeshEvidenceReport` export path is removed from
production UI.

## Scopes

Reports can be scoped to:

- Full installation overview
- Single network
- Single device (`network_id` + `ieee_address`)
- Single incident

Scope controls which devices, incidents, and timeline events are included.
Composition remains scope-first and history-bounded. The contextual dialog cannot
change scope or target — only format and redaction options.

## Storage

Reports are stored **inline in SQLite** (`reports` table). They are redacted
**before** storage — backups contain already-redacted content.

List stored reports: `GET /api/reports`  
Download: Saved reports on the Reports page or API  
Delete: Saved reports on the Reports page or `DELETE /api/reports/{id}`

See [backups.md](backups.md).

## Redaction

Every report passes through the redaction pipeline before storage and download.
Choose a profile at generation time:

| Profile | Description |
|---------|-------------|
| `standard` | Default — removes secrets, keeps diagnostic detail |
| `public_safe` | Stricter — suitable for GitHub issues and forums |
| `strict` | Maximum redaction — minimal identifiers |

Details: [redaction.md](redaction.md)

## Report contents

Typical v3 sections:

- Decision summary (status / priority counts, coverage warning count)
- Investigation priorities and Device Stories
- Data coverage warnings
- Factual incidents with evidence, counter-evidence, limitations
- Domain details (networks, devices, router risks, topology snapshot count)
- Timeline (optional, may be truncated by limits)
- Configuration summary (redacted MQTT server)
- Explicit limitations block

Reports use **correlation language** — they describe what the evidence is
consistent with, not definitive root causes.

## Limits

Configure in `config.yaml` under `reports.*`:

- Maximum timeline events
- Maximum devices listed
- Default redaction profile

Large networks may produce large reports — use narrower scopes for sharing.

## API example

```bash
curl -X POST http://localhost:8377/api/reports \
  -H 'Content-Type: application/json' \
  -d '{
    "scope": "full",
    "format": "markdown",
    "redaction": { "profile": "public_safe" }
  }'
```

Preview without storing: `GET /api/reports/preview?profile=public_safe`

## Related

- [redaction.md](redaction.md)
- [decision-engine.md](decision-engine.md)
- [troubleshooting.md](troubleshooting.md)
- [backups.md](backups.md)
