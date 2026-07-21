import type {
  RedactionOptions,
  RedactionProfile,
  ReportFormat,
  ReportRequest,
} from "@zigbeelens/shared";

/** Language-neutral contextual report target fixed by the launching page. */
export type ContextualReportTarget =
  | {
      scope: "full";
      subjectLabel: string;
    }
  | {
      scope: "network";
      networkId: string;
      subjectLabel: string;
    }
  | {
      scope: "device";
      networkId: string;
      deviceIeee: string;
      subjectLabel: string;
    }
  | {
      scope: "incident";
      incidentId: string;
      subjectLabel: string;
    };

export interface ContextualReportOptions {
  format: ReportFormat;
  profile: RedactionProfile;
  preserveFriendly: boolean;
  hashIeee: boolean;
  redactHostnames: boolean;
  redactIp: boolean;
  redactNetworkNames: boolean;
  includeTimeline: boolean;
  includeRaw: boolean;
}

export const CONTEXTUAL_REPORT_PROFILE_DEFAULTS: Record<
  RedactionProfile,
  Omit<ContextualReportOptions, "format" | "profile">
> = {
  standard: {
    preserveFriendly: true,
    hashIeee: true,
    redactHostnames: false,
    redactIp: false,
    redactNetworkNames: false,
    includeTimeline: true,
    includeRaw: false,
  },
  strict: {
    preserveFriendly: false,
    hashIeee: true,
    redactHostnames: true,
    redactIp: true,
    redactNetworkNames: true,
    includeTimeline: true,
    includeRaw: false,
  },
  public_safe: {
    preserveFriendly: false,
    hashIeee: true,
    redactHostnames: true,
    redactIp: true,
    redactNetworkNames: true,
    includeTimeline: true,
    includeRaw: false,
  },
};

export function scopeLabel(scope: ContextualReportTarget["scope"]): string {
  switch (scope) {
    case "full":
      return "Full evidence";
    case "network":
      return "Network";
    case "device":
      return "Device";
    case "incident":
      return "Incident";
  }
}

/** Canonical identity from logical target facts only (not object identity). */
export function contextualTargetIdentity(target: ContextualReportTarget): string {
  switch (target.scope) {
    case "full":
      return JSON.stringify({ scope: "full" });
    case "network":
      return JSON.stringify({
        scope: "network",
        networkId: target.networkId,
        subjectLabel: target.subjectLabel,
      });
    case "device":
      return JSON.stringify({
        scope: "device",
        networkId: target.networkId,
        deviceIeee: target.deviceIeee,
        subjectLabel: target.subjectLabel,
      });
    case "incident":
      return JSON.stringify({
        scope: "incident",
        incidentId: target.incidentId,
        subjectLabel: target.subjectLabel,
      });
  }
}

/** Target + scenario ownership key for dialog context transitions. */
export function contextualDialogContextKey(
  target: ContextualReportTarget,
  scenario?: string,
): string {
  return JSON.stringify({
    target: contextualTargetIdentity(target),
    scenario: scenario ?? "",
  });
}

/**
 * Canonical request key for preview/create ownership.
 * Independent of parent object-literal identity.
 */
export function contextualRequestKey(
  target: ContextualReportTarget,
  scenario: string | undefined,
  options: ContextualReportOptions,
): string {
  return JSON.stringify({
    target: contextualTargetIdentity(target),
    scenario: scenario ?? "",
    format: options.format,
    profile: options.profile,
    preserveFriendly: options.preserveFriendly,
    hashIeee: options.hashIeee,
    redactHostnames: options.redactHostnames,
    redactIp: options.redactIp,
    redactNetworkNames: options.redactNetworkNames,
    includeTimeline: options.includeTimeline,
    includeRaw: options.includeRaw,
  });
}

/** Rebuild a stable target value from its canonical identity string. */
export function targetFromIdentity(
  identity: string,
  fallback: ContextualReportTarget,
): ContextualReportTarget {
  try {
    const parsed = JSON.parse(identity) as {
      scope: ContextualReportTarget["scope"];
      networkId?: string;
      deviceIeee?: string;
      incidentId?: string;
      subjectLabel?: string;
    };
    switch (parsed.scope) {
      case "full":
        return {
          scope: "full",
          subjectLabel: fallback.scope === "full" ? fallback.subjectLabel : "Full ZigbeeLens evidence",
        };
      case "network":
        return {
          scope: "network",
          networkId: parsed.networkId ?? "",
          subjectLabel: parsed.subjectLabel ?? "",
        };
      case "device":
        return {
          scope: "device",
          networkId: parsed.networkId ?? "",
          deviceIeee: parsed.deviceIeee ?? "",
          subjectLabel: parsed.subjectLabel ?? "",
        };
      case "incident":
        return {
          scope: "incident",
          incidentId: parsed.incidentId ?? "",
          subjectLabel: parsed.subjectLabel ?? "",
        };
    }
  } catch {
    return fallback;
  }
}

/** Pure request builder — logical IDs only; no URL encoding. */
export function buildContextualReportRequest(
  target: ContextualReportTarget,
  options: ContextualReportOptions,
): ReportRequest {
  const redaction: RedactionOptions = {
    profile: options.profile,
    preserve_friendly_names: options.preserveFriendly,
    hash_ieee_addresses: options.hashIeee,
    redact_hostnames: options.redactHostnames,
    redact_ip_addresses: options.redactIp,
    redact_network_names: options.redactNetworkNames,
    include_timeline: options.includeTimeline,
    include_raw_payloads: options.includeRaw,
  };

  switch (target.scope) {
    case "full":
      return {
        format: options.format,
        scope: "full",
        network_id: null,
        incident_id: null,
        device: null,
        redaction,
      };
    case "network":
      return {
        format: options.format,
        scope: "network",
        network_id: target.networkId,
        incident_id: null,
        device: null,
        redaction,
      };
    case "device":
      return {
        format: options.format,
        scope: "device",
        network_id: target.networkId,
        device: target.deviceIeee,
        incident_id: null,
        redaction,
      };
    case "incident":
      return {
        format: options.format,
        scope: "incident",
        incident_id: target.incidentId,
        network_id: null,
        device: null,
        redaction,
      };
  }
}
