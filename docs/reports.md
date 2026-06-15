# Reports

ZigbeeLens generates scoped diagnostic reports from local SQLite history and current classification state.

## Lens family report structure (target)

Shared section vocabulary across Lens products. Generators may differ; new exports should converge toward this shape. See [lens-family.md](lens-family.md).

| Section | Purpose |
|---------|---------|
| `product`, `version`, `generated_at` | Report identity |
| `site`, `mode` | Deployment context (networks, mock/live) |
| **Executive summary** | One paragraph; evidence-first, no causal overclaiming |
| **Health summary** | Lens bucket or severity counts |
| **Active incidents** | Open/watching incidents with evidence and limitations |
| **Collector status** | MQTT collector, bridge visibility, enrichment |
| **Limitations** | Explicit gaps (“bridge offline — device list may be stale”) |
| **Redaction profile** | `standard`, `public_safe`, or `strict` |

ThreadLens on-demand reports: [reports.md](https://github.com/theaussiepom/threadlens/blob/main/docs/reports.md).

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

## Storage

Reports are stored **inline in SQLite** (`reports` table). They are redacted **before** storage — backups contain already-redacted content.

List stored reports: `GET /api/reports`  
Download: Reports page or API  
Delete: Reports page or `DELETE /api/reports/{id}`

See [backups.md](backups.md).

## Redaction

Every report passes through the redaction pipeline before storage and download. Choose a profile at generation time:

| Profile | Description |
|---------|-------------|
| `standard` | Default — removes secrets, keeps diagnostic detail |
| `public_safe` | Stricter — suitable for GitHub issues and forums |
| `strict` | Maximum redaction — minimal identifiers |

Details: [redaction.md](redaction.md)

## Report contents

Typical sections:

- Summary and overall severity
- Active incidents with evidence, counter-evidence, limitations
- Network and device health snapshots
- Router risk candidates
- Timeline (optional, may be truncated by limits)
- Configuration summary (redacted MQTT server)
- Topology summary (if snapshots exist)
- Explicit limitations block

Reports use **correlation language** — they describe what the evidence is consistent with, not definitive root causes.

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
- [troubleshooting.md](troubleshooting.md)
- [backups.md](backups.md)
