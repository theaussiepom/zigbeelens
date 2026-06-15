import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useScenario } from "@/context/ScenarioContext";
import { Badge, Card, SectionHeading } from "@/components/ui";
import {
  bridgeHealthRows,
  DASHBOARD_LABELS,
  deviceHealthRows,
  INCIDENT_PRIORITY,
  incidentRules,
  LIMITATIONS,
  MQTT_SOURCES,
  networkHealthRows,
  primaryPriority,
  SEVERITY_ROWS,
  type GuideSeverity,
} from "@/lib/monitoringGuide";
import { incidentTypeLabel, severityLabel } from "@/lib/format";

function SeverityBadge({ severity }: { severity: GuideSeverity }) {
  return <Badge severity={severity}>{severityLabel(severity)}</Badge>;
}

function GuideTable({
  headers,
  rows,
}: {
  headers: string[];
  rows: ReactNode[][];
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-zl-border">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead className="border-b border-zl-border bg-zl-surface-2/80">
          <tr>
            {headers.map((h) => (
              <th key={h} className="px-3 py-2.5 font-semibold text-zl-text">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-zl-border/60">
          {rows.map((cells, i) => (
            <tr key={i} className="align-top hover:bg-zl-surface-2/40">
              {cells.map((cell, j) => (
                <td key={j} className="px-3 py-3 text-zl-text">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const SECTIONS = [
  { id: "pipeline", label: "Pipeline" },
  { id: "severity", label: "Severity levels" },
  { id: "mqtt", label: "MQTT inputs" },
  { id: "devices", label: "Device health" },
  { id: "bridge", label: "Bridge health" },
  { id: "networks", label: "Network health" },
  { id: "incidents", label: "Incidents" },
  { id: "priority", label: "Priority & suppression" },
  { id: "dashboard", label: "Dashboard labels" },
  { id: "thresholds", label: "Your thresholds" },
  { id: "limits", label: "Limitations" },
];

export function MonitoringGuidePage() {
  const { status } = useScenario();
  const diagnostics = status?.diagnostics ?? {};
  const devices = deviceHealthRows(diagnostics);
  const bridges = bridgeHealthRows(diagnostics);
  const incidents = incidentRules(diagnostics);

  return (
    <div className="max-w-5xl space-y-8">
      <header className="space-y-3">
        <h1 className="text-2xl font-semibold tracking-tight">How monitoring works</h1>
        <p className="max-w-3xl text-zl-muted leading-relaxed">
          ZigbeeLens watches Zigbee2MQTT over MQTT, classifies device and network health, correlates
          patterns into incidents, and shows evidence with explicit limitations. Nothing here mutates
          your Zigbee network — this page documents exactly what is observed and how decisions are
          made.
        </p>
        <nav className="flex flex-wrap gap-2 pt-1" aria-label="On this page">
          {SECTIONS.map((s) => (
            <a
              key={s.id}
              href={`#${s.id}`}
              className="rounded-full border border-zl-border px-3 py-1 text-xs text-zl-muted hover:border-zl-accent/40 hover:text-zl-accent"
            >
              {s.label}
            </a>
          ))}
        </nav>
      </header>

      <section id="pipeline">
        <Card title="Monitoring pipeline" subtitle="What happens after each MQTT message">
        <ol className="space-y-3 text-sm leading-relaxed text-zl-text">
          <li>
            <strong className="font-medium">Collect</strong> — Core subscribes to each configured{" "}
            <code className="rounded bg-zl-surface-2 px-1 font-mono text-xs">base_topic</code> (read-only).
          </li>
          <li>
            <strong className="font-medium">Normalize &amp; store</strong> — Messages update SQLite
            (inventory, availability, payloads, bridge state, events).
          </li>
          <li>
            <strong className="font-medium">Classify health</strong> — Per-device, bridge, and network
            rules run (thresholds below).
          </li>
          <li>
            <strong className="font-medium">Correlate incidents</strong> — Pattern rules combine health
            signals across devices and networks.
          </li>
          <li>
            <strong className="font-medium">Present</strong> — Dashboard, incidents, timeline, and reports
            show conclusions with evidence, counter-evidence, and limitations.
          </li>
        </ol>
        <p className="mt-4 text-sm text-zl-muted">
          Health recalculates after bridge state, inventory, device payload, and availability events.
          Incidents sync immediately after each health recalculation.
        </p>
        </Card>
      </section>

      <section id="severity" className="space-y-3">
        <SectionHeading>Severity levels</SectionHeading>
        <GuideTable
          headers={["Severity", "UI label", "Meaning"]}
          rows={SEVERITY_ROWS.map((r) => [
            <SeverityBadge key="s" severity={r.severity} />,
            r.label,
            r.meaning,
          ])}
        />
      </section>

      <section id="mqtt" className="space-y-3">
        <SectionHeading>MQTT inputs (read-only)</SectionHeading>
        <GuideTable
          headers={["Topic pattern", "Used for"]}
          rows={MQTT_SOURCES.map((r) => [r.topic, r.use])}
        />
      </section>

      <section id="devices" className="space-y-4">
        <SectionHeading>Device health flags</SectionHeading>
        <p className="text-sm text-zl-muted">
          Each device gets a <strong>primary</strong> flag (first match wins) and may carry multiple
          secondary flags. Primary selection order:
        </p>
        <ol className="list-decimal space-y-1 pl-5 text-sm text-zl-muted">
          {primaryPriority().map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
        <GuideTable
          headers={["Flag", "When it applies", "Effect", "Typical severity", "UI label"]}
          rows={devices.map((r) => [
            <code key="f" className="font-mono text-xs">{r.label}</code>,
            r.condition,
            r.result,
            <SeverityBadge key="s" severity={r.severity} />,
            r.uiLabel,
          ])}
        />
      </section>

      <section id="bridge" className="space-y-3">
        <SectionHeading>Bridge health</SectionHeading>
        <GuideTable
          headers={["State", "When it applies", "Effect", "Severity", "UI / incident wording"]}
          rows={bridges.map((r) => [
            <code key="f" className="font-mono text-xs">{r.label}</code>,
            r.condition,
            r.result,
            <SeverityBadge key="s" severity={r.severity} />,
            r.uiLabel,
          ])}
        />
      </section>

      <section id="networks" className="space-y-3">
        <SectionHeading>Network health aggregation</SectionHeading>
        <p className="text-sm text-zl-muted">
          Each network card combines bridge state, device flag counts, and active incidents. Network{" "}
          <code className="rounded bg-zl-surface-2 px-1 font-mono text-xs">incident_state</code> uses
          this order:
        </p>
        <GuideTable
          headers={["State", "Condition", "Network badge", "Severity"]}
          rows={networkHealthRows().map((r) => [
            r.label,
            r.condition,
            r.result,
            <SeverityBadge key="s" severity={r.severity} />,
          ])}
        />
      </section>

      <section id="incidents" className="space-y-3">
        <SectionHeading>Incident rules</SectionHeading>
        <p className="text-sm text-zl-muted">
          Incidents are deduplicated by type + network + affected devices. They include evidence,
          counter-evidence, limitations, and a plain-language interpretation.
        </p>
        <GuideTable
          headers={["Type", "Title", "Opens when", "Severity", "Scope", "Notes"]}
          rows={incidents.map((r) => [
            r.type === "_lifecycle" ? (
              "lifecycle"
            ) : (
              <span key="t">{incidentTypeLabel(r.type)}</span>
            ),
            r.title,
            r.trigger,
            <SeverityBadge key="s" severity={r.severity} />,
            r.type === "_lifecycle" ? "—" : r.scope,
            r.notes ?? "—",
          ])}
        />
      </section>

      <section id="priority" className="space-y-3">
        <SectionHeading>Priority &amp; suppression</SectionHeading>
        <p className="text-sm text-zl-muted">
          When multiple rules match, lower index wins for <strong>Current finding</strong>. Bridge
          offline suppresses most device incidents on that network (device failures may be downstream
          of the bridge). Device unavailability incidents suppress duplicate explanations for the same
          devices in lower-priority rules.
        </p>
        <GuideTable
          headers={["Priority (high → low)", "Incident type"]}
          rows={INCIDENT_PRIORITY.map((t, i) => [
            String(i + 1),
            incidentTypeLabel(t),
          ])}
        />
        <Card title="Incident lifecycle" className="mt-4">
          <GuideTable
            headers={["State", "Meaning"]}
            rows={[
              ["Open", "Underlying signal is currently active."],
              [
                "Watching",
                "Signal cleared; incident kept visible while ZigbeeLens confirms it stays clear.",
              ],
              [
                "Resolved",
                `Watching period elapsed (${diagnostics.incident_watch_window_minutes ?? 30} min + ${diagnostics.incident_resolution_grace_minutes ?? 5} min grace) with no recurrence.`,
              ],
            ]}
          />
        </Card>
      </section>

      <section id="dashboard" className="space-y-3">
        <SectionHeading>Where dashboard labels come from</SectionHeading>
        <GuideTable
          headers={["UI surface", "Source"]}
          rows={DASHBOARD_LABELS.map((r) => [r.surface, r.source])}
        />
      </section>

      <section id="thresholds" className="space-y-3">
        <SectionHeading>Your active thresholds</SectionHeading>
        {Object.keys(diagnostics).length === 0 ? (
          <p className="text-sm text-zl-muted">
            Thresholds load from Core config. Check{" "}
            <Link to="/settings" className="text-zl-accent hover:underline">
              Settings
            </Link>{" "}
            if this section is empty.
          </p>
        ) : (
          <>
            <p className="text-sm text-zl-muted">
              Values below are from this Core instance&apos;s{" "}
              <code className="rounded bg-zl-surface-2 px-1 font-mono text-xs">diagnostics</code>{" "}
              config. Edit{" "}
              <code className="rounded bg-zl-surface-2 px-1 font-mono text-xs">config.yaml</code> and
              restart Core to change them.
            </p>
            <GuideTable
              headers={["Config key", "Value", "Used for"]}
              rows={[
                ["incident_window_seconds", diagnostics.incident_window_seconds, "Correlated offline window"],
                ["correlated_min_devices", diagnostics.correlated_min_devices, "Min devices for correlated incident"],
                ["network_wide_min_devices", diagnostics.network_wide_min_devices, "Network-wide incident device count"],
                ["network_wide_device_percent", diagnostics.network_wide_device_percent, "Network-wide incident %"],
                ["flapping_threshold", diagnostics.flapping_threshold, "Recently unstable availability changes"],
                ["recently_unstable_window_hours", diagnostics.recently_unstable_window_hours, "Flapping lookback window"],
                ["weak_link_threshold", diagnostics.weak_link_threshold, "Weak linkquality (LQI)"],
                ["low_battery_percent", diagnostics.low_battery_percent, "Low battery threshold"],
                ["stale_after_hours", diagnostics.stale_after_hours, "Default device stale threshold"],
                ["mains_stale_after_hours", diagnostics.mains_stale_after_hours, "Mains/router stale threshold"],
                ["battery_stale_after_hours", diagnostics.battery_stale_after_hours, "Battery device stale threshold"],
                ["bridge_stale_after_minutes", diagnostics.bridge_stale_after_minutes, "Bridge state quiet detection"],
                ["stale_cluster_min_devices", diagnostics.stale_cluster_min_devices, "Stale cluster incident"],
                ["low_battery_cluster_min_devices", diagnostics.low_battery_cluster_min_devices, "Low battery cluster incident"],
                ["interview_failure_min_devices", diagnostics.interview_failure_min_devices, "Interview cluster incident"],
                ["incident_watch_window_minutes", diagnostics.incident_watch_window_minutes, "Incident watching duration"],
                ["incident_resolution_grace_minutes", diagnostics.incident_resolution_grace_minutes, "Extra grace before resolve"],
              ].map(([key, value, used]) => [
                <code key="k" className="font-mono text-xs">{key}</code>,
                value ?? "—",
                used,
              ])}
            />
          </>
        )}
      </section>

      <section id="limits" className="space-y-3">
        <SectionHeading>What ZigbeeLens does not claim</SectionHeading>
        <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed text-zl-muted">
          {LIMITATIONS.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
