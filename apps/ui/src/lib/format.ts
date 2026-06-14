import type {
  Availability,
  Confidence,
  DeviceHealthPrimary,
  DeviceSummary,
  Incident,
  IncidentScope,
  IncidentStatus,
  RouterRisk,
  Severity,
} from "@zigbeelens/shared";

export function severityColor(severity: Severity): string {
  switch (severity) {
    case "healthy":
      return "text-zl-healthy";
    case "watch":
      return "text-zl-watch";
    case "incident":
      return "text-zl-incident";
    case "critical":
      return "text-zl-critical";
    default:
      return "text-zl-muted";
  }
}

export function severityBg(severity: Severity): string {
  switch (severity) {
    case "healthy":
      return "bg-zl-healthy/15 text-zl-healthy border-zl-healthy/30";
    case "watch":
      return "bg-zl-watch/15 text-zl-watch border-zl-watch/30";
    case "incident":
      return "bg-zl-incident/15 text-zl-incident border-zl-incident/30";
    case "critical":
      return "bg-zl-critical/15 text-zl-critical border-zl-critical/30";
    default:
      return "bg-zl-surface-2 text-zl-muted border-zl-border";
  }
}

export function severityDot(severity: Severity): string {
  switch (severity) {
    case "healthy":
      return "bg-zl-healthy";
    case "watch":
      return "bg-zl-watch";
    case "incident":
      return "bg-zl-incident";
    case "critical":
      return "bg-zl-critical";
    default:
      return "bg-zl-muted";
  }
}

/** A calm, readable label for an overall severity state. */
export function severityLabel(severity: Severity): string {
  switch (severity) {
    case "healthy":
      return "OK";
    case "watch":
      return "Watch";
    case "incident":
      return "Incident";
    case "critical":
      return "Critical";
    default:
      return "Unknown";
  }
}

export function scopeLabel(scope: IncidentScope): string {
  const labels: Record<IncidentScope, string> = {
    device: "Single device",
    router_candidate: "Router candidate",
    mesh_segment: "Room or mesh segment",
    network: "One Zigbee2MQTT network",
    multi_network: "Multiple networks",
    unknown: "Unknown scope",
  };
  return labels[scope] ?? scope;
}

export function confidenceLabel(c: Confidence): string {
  return c.charAt(0).toUpperCase() + c.slice(1);
}

export function lifecycleLabel(status: IncidentStatus): string {
  switch (status) {
    case "open":
      return "Open";
    case "watching":
      return "Watching";
    case "resolved":
      return "Resolved";
    default:
      return status;
  }
}

/** Severity styling used for a lifecycle badge (calm for resolved/watching). */
export function lifecycleSeverity(status: IncidentStatus): Severity {
  switch (status) {
    case "open":
      return "incident";
    case "watching":
      return "watch";
    case "resolved":
      return "healthy";
    default:
      return "healthy";
  }
}

export function healthLabel(h: DeviceHealthPrimary): string {
  return titleCase(h.replace(/_/g, " "));
}

/** Map a device health primary to a severity for consistent colouring. */
export function healthSeverity(h: DeviceHealthPrimary): Severity {
  switch (h) {
    case "healthy":
      return "healthy";
    case "unavailable":
      return "incident";
    case "router_risk":
    case "recently_unstable":
    case "interview_issue":
    case "stale_reporting":
    case "weak_link":
    case "low_battery":
      return "watch";
    default:
      return "watch";
  }
}

export function availabilityLabel(a: Availability): string {
  switch (a) {
    case "online":
      return "Online";
    case "offline":
      return "Offline";
    default:
      return "Unknown";
  }
}

export function incidentTypeLabel(type: string): string {
  return titleCase(type.replace(/_/g, " "));
}

export function titleCase(text: string): string {
  return text
    .split(" ")
    .map((w) => (w ? w.charAt(0).toUpperCase() + w.slice(1) : w))
    .join(" ");
}

export function formatTime(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString();
}

/** Compact relative time such as "3m ago" with an exact title for tooltips. */
export function relativeTime(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const seconds = Math.round((Date.now() - d.getTime()) / 1000);
  const abs = Math.abs(seconds);
  const suffix = seconds >= 0 ? "ago" : "from now";
  if (abs < 45) return "just now";
  if (abs < 90) return `1m ${suffix}`;
  const minutes = Math.round(abs / 60);
  if (minutes < 60) return `${minutes}m ${suffix}`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ${suffix}`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ${suffix}`;
  return d.toLocaleDateString();
}

export function devicePath(networkId: string, ieee: string): string {
  return `/devices/${networkId}/${encodeURIComponent(ieee)}`;
}

/** Severity ranking for sorting; lower = worse / more urgent. */
export function severityRank(severity: Severity): number {
  const order: Record<Severity, number> = {
    critical: 0,
    incident: 1,
    watch: 2,
    healthy: 4,
  };
  return order[severity] ?? 3;
}

/**
 * Bad-first ordering rank for a device primary health.
 * Mirrors the Phase 5 device list ordering specification.
 */
export function healthRank(primary: DeviceHealthPrimary): number {
  const order: Record<DeviceHealthPrimary, number> = {
    unavailable: 1,
    router_risk: 2,
    recently_unstable: 3,
    interview_issue: 4,
    stale_reporting: 5,
    weak_link: 6,
    low_battery: 7,
    unknown: 8,
    healthy: 9,
  };
  return order[primary] ?? 8;
}

/** Comparator implementing bad-first device ordering. */
export function compareDevices(a: DeviceSummary, b: DeviceSummary): number {
  if (a.incident_affected !== b.incident_affected) {
    return a.incident_affected ? -1 : 1;
  }
  const rank = healthRank(a.health.primary) - healthRank(b.health.primary);
  if (rank !== 0) return rank;
  // Backend-provided priority as a secondary signal.
  if (a.sort_priority !== b.sort_priority) return a.sort_priority - b.sort_priority;
  return a.friendly_name.localeCompare(b.friendly_name);
}

export function bridgeStateSeverity(state: string): Severity {
  if (state === "online") return "healthy";
  if (state === "offline") return "critical";
  return "watch";
}

const INCIDENT_STATUS_ORDER: Record<IncidentStatus, number> = {
  open: 0,
  watching: 1,
  resolved: 2,
};

/**
 * Incident ordering: open first, then watching, then resolved; within a
 * lifecycle by severity, then most-recently updated.
 */
export function compareIncidents(a: Incident, b: Incident): number {
  if (INCIDENT_STATUS_ORDER[a.status] !== INCIDENT_STATUS_ORDER[b.status]) {
    return INCIDENT_STATUS_ORDER[a.status] - INCIDENT_STATUS_ORDER[b.status];
  }
  const sev = severityRank(a.severity) - severityRank(b.severity);
  if (sev !== 0) return sev;
  return b.updated_at.localeCompare(a.updated_at);
}

/**
 * Router ordering: unavailable first, then risk severity, then correlated
 * device count, then name.
 */
export function compareRouterRisks(a: RouterRisk, b: RouterRisk): number {
  const aOff = a.availability === "offline" ? 0 : 1;
  const bOff = b.availability === "offline" ? 0 : 1;
  if (aOff !== bOff) return aOff - bOff;
  const sev = severityRank(a.risk.severity) - severityRank(b.risk.severity);
  if (sev !== 0) return sev;
  if (a.correlated_affected_devices !== b.correlated_affected_devices) {
    return b.correlated_affected_devices - a.correlated_affected_devices;
  }
  return a.friendly_name.localeCompare(b.friendly_name);
}
