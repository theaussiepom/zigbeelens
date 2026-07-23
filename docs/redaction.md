# Report redaction

ZigbeeLens redacts every generated report before it is previewed, stored, or
downloaded. Report redaction reduces sharing risk; it does not replace
authentication, network isolation, or a final human review.

Home Assistant integration diagnostics use a separate diagnostics-redaction
path. This page describes the Core `ReportDetailV3` report contract.

## Profiles

| Profile | Default treatment |
|---------|-------------------|
| `standard` | Removes recognised secrets and broker credentials; hashes IEEE addresses; preserves friendly/network names, usernames, hostnames, and IP addresses |
| `public_safe` | Also redacts usernames, hostnames, IP addresses, and paths; replaces friendly names, network names, network IDs, and base topics with stable labels within that report |
| `strict` | Also redacts usernames, hostnames, IP addresses, and paths; hashes friendly/network identifiers with a per-report salt |

All three profiles hash IEEE addresses by default. Hashes and labels are stable
only within one report so related entries can still be followed; they are not
stable identifiers across reports.

The API request schema defaults to `standard`. Select a profile in the report
dialog or send it as an object:

```json
{
  "redaction": {
    "profile": "public_safe"
  }
}
```

Do not use a bare profile string for `redaction`; it must be an object.

## Per-request overrides

The redaction object also accepts nullable boolean overrides:

| Field | Effect when set |
|-------|-----------------|
| `preserve_friendly_names` | Preserve names when `true`; a `false` override changes otherwise-preserved names to labels |
| `hash_ieee_addresses` | Enable or disable IEEE hashing |
| `redact_hostnames` | Redact broker hostnames and storage paths |
| `redact_ip_addresses` | Redact IPv4/IPv6 text |
| `redact_network_names` | Label network names/IDs/topics when `true`; preserve them when `false` |
| `include_timeline` | Include or clear report timeline/event collections |
| `include_raw_payloads` | Accepted by the request contract; current exact-v3 reports have no raw MQTT payload collection to add |

Overrides can relax a stricter profile. For a public issue, prefer the
`public_safe` defaults without relaxation and inspect the generated file before
uploading it.

## Always scrubbed

The structured redactor replaces recognised secret keys, including passwords,
tokens, authorization values, API keys, network keys, install codes, client
secrets, and pre-shared keys. MQTT connection strings have embedded credentials
removed before storage.

The walker also scrubs matching identifiers from free text after building its
per-report identifier maps. Categorical fields such as decision status,
priority, device type, and evidence codes are retained so redaction does not
change their meaning.

The report configuration summary can retain non-secret diagnostic context under
`standard`, including the MQTT username and broker hostname/IP. Use
`public_safe` or `strict` when that context should not leave the installation.

## Exact redaction status block

Every `ReportDetailV3` includes:

```json
{
  "redaction": {
    "applied": true,
    "profile": "public_safe",
    "mqtt_credentials": true,
    "secrets": true,
    "hostnames": true,
    "ip_addresses": true,
    "ieee_addresses_hashed": true,
    "friendly_names": "labeled",
    "network_names": "labeled"
  }
}
```

`friendly_names` and `network_names` use the modes `preserved`, `labeled`,
`hashed`, or `redacted`. The status block reports treatment, not a count of
changed fields and not a warning list.

## Local storage and sharing

Core stores the post-redaction JSON body and Markdown summary inline in SQLite.
Downloading JSON or YAML renders the validated stored v3 body; a Markdown
download returns its stored `markdown_summary`. Report backups therefore contain
the report representation after redaction, but other SQLite telemetry and
topology tables are not report exports and can still contain local device
identifiers.

Before opening a public issue:

1. Generate the correct contextual report, or a full report from Reports.
2. Choose `public_safe` without identifier-preserving overrides.
3. Download JSON/Markdown and review it.
4. Do not paste raw `config.yaml`, MQTT payloads, Core logs, or Home Assistant
   registries unless you have separately reviewed them.

Use the [diagnostic report issue template](../.github/ISSUE_TEMPLATE/diagnostic_report.yml).

## Logs

Core's own logging paths redact configured secrets and recognised secret query
parameters. That does not sanitize reverse-proxy, broker, container-platform, or
Home Assistant logs. Never put credentials in URLs.

## Related

- [reports.md](reports.md)
- [security.md](security.md)
- [SECURITY.md](../SECURITY.md)
