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

## Stored v1 / v2 reports

Older stored reports remain **immutable historical artifacts**.

- Detected by `report_version` (and/or legacy field shape)
- List, detail, and download return the **original stored body**
- Markdown downloads return the **original stored Markdown**
- Bodies are not rewritten on read and not re-evaluated through current decision logic
- The UI shows a legacy notice for `report_version < 3`
- Malformed legacy bodies fail safely without becoming a new report

No SQLite migration rewrites report rows.

## Formats

| Format | Use case |
|--------|----------|
| **JSON** | Tools, archival, programmatic analysis |
| **YAML** | Human-readable structured export |
| **Markdown** | Forums, GitHub issues, quick sharing |

Generate from the **Reports** page or `POST /api/reports`.

## Scopes

Reports can be scoped to:

- Full installation overview
- Single network
- Single device (`network_id` + `ieee_address`)
- Single incident

Scope controls which devices, incidents, and timeline events are included.
Composition remains scope-first and history-bounded.

## Storage

Reports are stored **inline in SQLite** (`reports` table). They are redacted
**before** storage — backups contain already-redacted content.

List stored reports: `GET /api/reports`  
Download: Reports page or API  
Delete: Reports page or `DELETE /api/reports/{id}`

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
    "scope": "overview",
    "format": "markdown",
    "redaction": "public_safe"
  }'
```

Preview without storing: `GET /api/reports/preview?redaction=public_safe`

## Related

- [redaction.md](redaction.md)
- [decision-engine.md](decision-engine.md)
- [troubleshooting.md](troubleshooting.md)
- [backups.md](backups.md)
