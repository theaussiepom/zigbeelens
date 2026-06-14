# Redaction

ZigbeeLens redacts sensitive data from reports **before** they are stored or downloaded. Redaction also applies to diagnostic exports from the Home Assistant integration.

## Profiles

| Profile | When to use |
|---------|-------------|
| `standard` | Local troubleshooting — default |
| `public_safe` | GitHub issues, forums, community help |
| `strict` | Maximum caution — minimal identifiers |

Configure default in `config.yaml`:

```yaml
reports:
  default_redaction: standard
```

## What is redacted

Typical redactions include:

- MQTT passwords and tokens
- Network keys and coordinator backup data
- Raw broker credentials in connection strings
- Overly specific location identifiers when using stricter profiles
- Internal paths in strict mode

The redaction engine walks the structured report tree. Sensitive field paths are registered in `services/report_redaction.py`.

## What is kept

Diagnostic content needed for troubleshooting:

- Device friendly names (may be reduced in `strict`)
- IEEE addresses (may be truncated in `strict`)
- Health states, incident summaries, evidence text
- Timestamps and severity
- Network IDs and display names

## Report redaction status

Each report includes a `redaction` block describing:

- Profile applied
- Fields redacted count
- Warnings if aggressive truncation occurred

Check this block if a report looks unexpectedly empty.

## Sharing safely

When opening a GitHub issue:

1. Generate a report with **`public_safe`** redaction
2. Download JSON or copy Markdown
3. Do **not** paste raw `config.yaml`, MQTT payloads, or HA secrets

Use the [diagnostic report issue template](../.github/ISSUE_TEMPLATE/diagnostic_report.yml).

## Logs

MQTT passwords and tokens are not logged by Core. Config loading uses secret-safe logging helpers.

Standalone Docker on an untrusted network should still use a reverse proxy — redaction does not replace access control.

## Related

- [reports.md](reports.md)
- [security.md](security.md)
- [SECURITY.md](../SECURITY.md)
