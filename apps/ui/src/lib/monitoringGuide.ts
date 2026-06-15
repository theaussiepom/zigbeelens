/** Static definitions for the in-app monitoring transparency guide. */

export type GuideSeverity = "healthy" | "watch" | "incident" | "critical";

export interface GuideRow {
  label: string;
  condition: string;
  result: string;
  severity: GuideSeverity;
  uiLabel: string;
}

export interface IncidentRuleRow {
  type: string;
  title: string;
  trigger: string;
  severity: GuideSeverity;
  scope: string;
  notes?: string;
}

export const SEVERITY_ROWS: Array<{ severity: GuideSeverity; label: string; meaning: string }> = [
  {
    severity: "healthy",
    label: "OK",
    meaning: "No current concern, or signals are within normal bounds.",
  },
  {
    severity: "watch",
    label: "Watch",
    meaning: "Something worth attention — not necessarily a fault. May become an incident if it persists or clusters.",
  },
  {
    severity: "incident",
    label: "Incident",
    meaning: "A correlated pattern or clear device/network problem. Opens or updates an incident record.",
  },
  {
    severity: "critical",
    label: "Critical",
    meaning: "Bridge layer is offline. Device telemetry may be incomplete until the bridge reconnects.",
  },
];

export const MQTT_SOURCES = [
  { topic: "{base_topic}/bridge/state", use: "Bridge online/offline state" },
  { topic: "{base_topic}/bridge/devices", use: "Device inventory and interview state" },
  { topic: "{base_topic}/bridge/info", use: "Coordinator metadata snapshots" },
  { topic: "{base_topic}/{friendly_name}", use: "Device payloads (linkquality, battery, sensors, …)" },
  { topic: "{base_topic}/{friendly_name}/availability", use: "Device online/offline when enabled in Z2M" },
  { topic: "Bridge/device lifecycle events", use: "Join, leave, interview started/success/failed" },
];

export const INCIDENT_PRIORITY = [
  "bridge_offline",
  "multi_network_instability",
  "network_wide_instability",
  "correlated_device_unavailability",
  "single_device_unavailable",
  "router_risk",
  "stale_reporting_cluster",
  "interview_failure",
  "low_battery_cluster",
  "unknown_pattern",
];

export function deviceHealthRows(d: Record<string, number>): GuideRow[] {
  const flapping = d.flapping_threshold ?? 3;
  const unstableHours = d.recently_unstable_window_hours ?? 24;
  const weak = d.weak_link_threshold ?? 40;
  const lowBat = d.low_battery_percent ?? 20;
  const staleDefault = d.stale_after_hours ?? 24;
  const staleMains = d.mains_stale_after_hours ?? 12;
  const staleBattery = d.battery_stale_after_hours ?? 48;

  return [
    {
      label: "unavailable",
      condition: "Zigbee2MQTT availability is `offline`",
      result: "Primary health flag; device counted as unavailable on network cards",
      severity: "incident",
      uiLabel: "Unavailable",
    },
    {
      label: "recently_unstable",
      condition: `Availability changed ≥ ${flapping} times in the last ${unstableHours} hours`,
      result: "Flapping signal — cause is not determined from MQTT alone",
      severity: "watch",
      uiLabel: "Recently unstable",
    },
    {
      label: "interview_issue",
      condition: "Inventory interview_state is `failed` or `in_progress`",
      result: "Configuration/interview problem from Zigbee2MQTT inventory",
      severity: "watch",
      uiLabel: "Interview issue",
    },
    {
      label: "stale_reporting",
      condition: `No payload/last_seen older than threshold: mains/router ${staleMains}h, battery ${staleBattery}h, other ${staleDefault}h`,
      result: "Device has not reported recently — may be normal for sleepy end devices",
      severity: "watch",
      uiLabel: "Stale",
    },
    {
      label: "weak_link",
      condition: `Latest linkquality ≤ ${weak}`,
      result: "Single LQI reading below threshold",
      severity: "watch",
      uiLabel: "Weak link",
    },
    {
      label: "low_battery",
      condition: `Latest battery ≤ ${lowBat}%`,
      result: "Maintenance signal from last reported battery value",
      severity: "watch",
      uiLabel: "Low battery",
    },
    {
      label: "router_risk",
      condition: "Device is a Router and has any of the flags above",
      result: "Router flagged as infrastructure risk candidate",
      severity: "watch",
      uiLabel: "Router risk",
    },
    {
      label: "healthy",
      condition: "No flags above; recent payload or online availability observed",
      result: "No current health concerns for this device",
      severity: "healthy",
      uiLabel: "Healthy",
    },
    {
      label: "unknown",
      condition: "In inventory but no payload observed yet",
      result: "Not enough telemetry to classify — common after startup",
      severity: "watch",
      uiLabel: "No health signal",
    },
  ];
}

export function primaryPriority(): string[] {
  return [
    "unavailable",
    "router_risk (when router is unavailable or unstable)",
    "recently_unstable",
    "interview_issue",
    "stale_reporting",
    "weak_link",
    "low_battery",
    "router_risk (other router signals)",
    "healthy",
    "unknown",
  ];
}

export function bridgeHealthRows(d: Record<string, number>): GuideRow[] {
  const staleMin = d.bridge_stale_after_minutes ?? 10;
  return [
    {
      label: "offline",
      condition: "Latest `{base_topic}/bridge/state` is `offline`",
      result: "Bridge layer down — network severity becomes Critical",
      severity: "critical",
      uiLabel: "Bridge: Offline",
    },
    {
      label: "online",
      condition: `State is "online" and bridge/state updated within ${staleMin} minutes, OR state is online with recent device MQTT activity on the network`,
      result: "Bridge considered alive. Z2M only republishes bridge/state on changes, so device traffic counts as liveness proof.",
      severity: "healthy",
      uiLabel: "Bridge: Online",
    },
    {
      label: "stale (internal)",
      condition: `State is "online" but no bridge/state update for ${staleMin}+ minutes and no recent device MQTT activity`,
      result: "May open a watch-severity “Bridge state quiet” incident — bridge may still be up",
      severity: "watch",
      uiLabel: "Bridge state quiet (incident title)",
    },
    {
      label: "unknown",
      condition: "No bridge/state observed yet",
      result: "Waiting for retained or first bridge state message",
      severity: "watch",
      uiLabel: "Bridge: No bridge signal",
    },
  ];
}

export function networkHealthRows(): GuideRow[] {
  return [
    {
      label: "incident",
      condition: "Bridge offline OR one or more devices unavailable",
      result: "Network incident_state badge: Incident",
      severity: "incident",
      uiLabel: "Incident",
    },
    {
      label: "watch",
      condition: "No unavailable devices, but unstable / router risk / weak / stale / low battery flags exist",
      result: "Network incident_state badge: Watch",
      severity: "watch",
      uiLabel: "Watch",
    },
    {
      label: "ok",
      condition: "Devices present, bridge known, no concerning device flags",
      result: "Network incident_state badge: OK",
      severity: "healthy",
      uiLabel: "OK",
    },
    {
      label: "unknown",
      condition: "No devices yet, or bridge state unknown",
      result: "Network incident_state badge: Watch (unknown)",
      severity: "watch",
      uiLabel: "Unknown / waiting",
    },
  ];
}

export function incidentRules(d: Record<string, number>): IncidentRuleRow[] {
  const windowSec = d.incident_window_seconds ?? 180;
  const correlatedMin = d.correlated_min_devices ?? 2;
  const networkWideMin = d.network_wide_min_devices ?? 5;
  const networkWidePct = d.network_wide_device_percent ?? 25;
  const staleCluster = d.stale_cluster_min_devices ?? 3;
  const lowBatCluster = d.low_battery_cluster_min_devices ?? 3;
  const interviewMin = d.interview_failure_min_devices ?? 2;
  const bridgeStale = d.bridge_stale_after_minutes ?? 10;
  const watchMin = d.incident_watch_window_minutes ?? 30;
  const graceMin = d.incident_resolution_grace_minutes ?? 5;

  return [
    {
      type: "bridge_offline",
      title: "Bridge offline / Bridge state quiet",
      trigger: `Bridge state offline (critical), OR online but no bridge/state for ${bridgeStale}+ min with no device MQTT activity (watch — title “Bridge state quiet”)`,
      severity: "critical",
      scope: "One network",
      notes: "Suppresses most device-level incidents on that network while bridge is truly offline.",
    },
    {
      type: "multi_network_instability",
      title: "Instability across multiple networks",
      trigger: `≥ 2 networks show bridge offline, correlated offline cluster (≥ ${correlatedMin} devices), or network-wide unavailability within the correlation window`,
      severity: "incident",
      scope: "Multiple networks",
    },
    {
      type: "network_wide_instability",
      title: "Network-wide instability",
      trigger: `≥ ${networkWideMin} unavailable devices OR ≥ ${networkWidePct}% of inventory unavailable (bridge still online)`,
      severity: "incident",
      scope: "One network",
    },
    {
      type: "correlated_device_unavailability",
      title: "Correlated device unavailability",
      trigger: `≥ ${correlatedMin} devices went offline within ${windowSec}s while bridge stayed online`,
      severity: "incident",
      scope: "Mesh segment / room",
      notes: "Topology and HA area enrichment may add evidence when enabled.",
    },
    {
      type: "single_device_unavailable",
      title: "Single device unavailable",
      trigger: `Exactly one device offline in the ${windowSec}s window; bridge online; not network-wide`,
      severity: "incident",
      scope: "Single device",
    },
    {
      type: "router_risk",
      title: "Router risk",
      trigger: "Router device has router_risk health flag",
      severity: "watch",
      scope: "Router candidate",
      notes: "Severity becomes Incident if the router itself is unavailable.",
    },
    {
      type: "stale_reporting_cluster",
      title: "Stale reporting cluster",
      trigger: `≥ ${staleCluster} devices with stale_reporting flag`,
      severity: "watch",
      scope: "Network or mesh segment",
    },
    {
      type: "interview_failure",
      title: "Interview issue",
      trigger: `≥ ${interviewMin} devices with interview issues, OR any single device with interview failed`,
      severity: "incident",
      scope: "Device or network",
      notes: "Watch severity when only in_progress without failed.",
    },
    {
      type: "low_battery_cluster",
      title: "Low battery cluster",
      trigger: `≥ ${lowBatCluster} devices below low_battery threshold`,
      severity: "watch",
      scope: "One network",
    },
    {
      type: "unknown_pattern",
      title: "Devices not reporting yet",
      trigger: "≥ 2 devices in inventory with unknown health, unknown availability, and no payload yet",
      severity: "watch",
      scope: "Unknown",
      notes: "Common shortly after Core startup.",
    },
    {
      type: "_lifecycle",
      title: "Incident lifecycle (all types)",
      trigger: `When underlying signal clears: Open → Watching → Resolved after ${watchMin}+${graceMin} min with no recurrence`,
      severity: "watch",
      scope: "—",
      notes: "Reopening if the same dedup_key becomes active again.",
    },
  ];
}

export const DASHBOARD_LABELS = [
  {
    surface: "Overview → Current finding",
    source: "Highest-priority open incident (by severity, then open before watching). Falls back to aggregated health summary if no incidents.",
  },
  {
    surface: "Overview → Overall severity badge",
    source: "Same severity as Current finding.",
  },
  {
    surface: "Network card → Bridge badge",
    source: "Raw Zigbee2MQTT bridge/state (`online` / `offline` / unknown) — not the same as a bridge incident title.",
  },
  {
    surface: "Network card → Severity badge",
    source: "Network health aggregation (offline bridge → Critical; unavailable devices → Incident; other flags → Watch).",
  },
  {
    surface: "Network card → Incidents pill",
    source: "Count of open + watching incidents linked to that network.",
  },
  {
    surface: "Device list / detail → Health badge",
    source: "Device primary health flag and mapped severity (unavailable → Incident; most others → Watch).",
  },
  {
    surface: "Timeline",
    source: "Stored MQTT and diagnostic events (availability changes, bridge state, incidents opened/updated/resolved).",
  },
];

export const LIMITATIONS = [
  "ZigbeeLens is read-only — it observes Zigbee2MQTT over MQTT and never sends Zigbee commands.",
  "Availability depends on Zigbee2MQTT availability reporting being enabled.",
  "Linkquality and battery are point-in-time readings; they can fluctuate or be reported infrequently.",
  "Router dependency and mesh segments are inferred; topology snapshots (when enabled) add suggestive evidence only.",
  "Incidents describe patterns and scope — they are not root-cause verdicts.",
  "Bridge/state is not a heartbeat; quiet state with active device traffic is treated as online.",
];
