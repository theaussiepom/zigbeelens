import { describe, expect, it } from "vitest";
import type { RedactionProfile, ReportFormat } from "@zigbeelens/shared";
import {
  CONTEXTUAL_REPORT_PROFILE_DEFAULTS,
  buildContextualReportRequest,
  contextualRequestKey,
  contextualTargetIdentity,
  type ContextualReportOptions,
  type ContextualReportTarget,
} from "./contextualReportTarget";

const formats: ReportFormat[] = ["json", "yaml", "markdown"];
const profiles: RedactionProfile[] = ["standard", "public_safe", "strict"];

function options(
  format: ReportFormat,
  profile: RedactionProfile,
): ContextualReportOptions {
  return { format, profile, ...CONTEXTUAL_REPORT_PROFILE_DEFAULTS[profile] };
}

describe("buildContextualReportRequest", () => {
  it("maps full targets without subject IDs", () => {
    const target: ContextualReportTarget = {
      scope: "full",
      subjectLabel: "Full ZigbeeLens evidence",
    };
    for (const format of formats) {
      for (const profile of profiles) {
        const request = buildContextualReportRequest(target, options(format, profile));
        expect(request).toEqual({
          format,
          scope: "full",
          network_id: null,
          incident_id: null,
          device: null,
          redaction: {
            profile,
            preserve_friendly_names: CONTEXTUAL_REPORT_PROFILE_DEFAULTS[profile].preserveFriendly,
            hash_ieee_addresses: CONTEXTUAL_REPORT_PROFILE_DEFAULTS[profile].hashIeee,
            redact_hostnames: CONTEXTUAL_REPORT_PROFILE_DEFAULTS[profile].redactHostnames,
            redact_ip_addresses: CONTEXTUAL_REPORT_PROFILE_DEFAULTS[profile].redactIp,
            redact_network_names: CONTEXTUAL_REPORT_PROFILE_DEFAULTS[profile].redactNetworkNames,
            include_timeline: CONTEXTUAL_REPORT_PROFILE_DEFAULTS[profile].includeTimeline,
            include_raw_payloads: CONTEXTUAL_REPORT_PROFILE_DEFAULTS[profile].includeRaw,
          },
        });
      }
    }
  });

  it("maps network targets with logical network ID only", () => {
    const request = buildContextualReportRequest(
      { scope: "network", networkId: "Home Office", subjectLabel: "Home Office" },
      options("json", "standard"),
    );
    expect(request.scope).toBe("network");
    expect(request.network_id).toBe("Home Office");
    expect(request.incident_id).toBeNull();
    expect(request.device).toBeNull();
  });

  it("maps device targets with logical network and IEEE", () => {
    const request = buildContextualReportRequest(
      {
        scope: "device",
        networkId: "home#2",
        deviceIeee: "0xab/cd",
        subjectLabel: "Kitchen Plug",
      },
      options("markdown", "public_safe"),
    );
    expect(request).toMatchObject({
      scope: "device",
      network_id: "home#2",
      device: "0xab/cd",
      incident_id: null,
      format: "markdown",
    });
    expect(request.network_id).not.toContain("%");
    expect(request.device).not.toContain("%");
  });

  it("maps incident targets with logical incident ID only", () => {
    const request = buildContextualReportRequest(
      { scope: "incident", incidentId: "inc-42", subjectLabel: "Cluster offline" },
      options("yaml", "strict"),
    );
    expect(request).toMatchObject({
      scope: "incident",
      incident_id: "inc-42",
      network_id: null,
      device: null,
      format: "yaml",
    });
  });

  it("does not encode path segments into ReportRequest fields", () => {
    const request = buildContextualReportRequest(
      {
        scope: "device",
        networkId: "50%mesh",
        deviceIeee: "0xabc",
        subjectLabel: "Sensor",
      },
      options("json", "standard"),
    );
    expect(request.network_id).toBe("50%mesh");
    expect(request.network_id).not.toBe("50%25mesh");
  });

  it("canonical target identity ignores object-literal identity", () => {
    const a: ContextualReportTarget = {
      scope: "device",
      networkId: "home",
      deviceIeee: "0x1",
      subjectLabel: "Plug",
    };
    const b: ContextualReportTarget = { ...a };
    expect(contextualTargetIdentity(a)).toBe(contextualTargetIdentity(b));
    expect(contextualTargetIdentity({ scope: "full", subjectLabel: "A" })).toBe(
      contextualTargetIdentity({ scope: "full", subjectLabel: "B" }),
    );
  });

  it("canonical request key is stable for the same semantic inputs", () => {
    const target: ContextualReportTarget = {
      scope: "network",
      networkId: "home",
      subjectLabel: "Home",
    };
    const keyA = contextualRequestKey({ ...target }, "s1", options("json", "standard"));
    const keyB = contextualRequestKey(target, "s1", options("json", "standard"));
    expect(keyA).toBe(keyB);
    expect(contextualRequestKey(target, "s2", options("json", "standard"))).not.toBe(keyA);
    expect(contextualRequestKey(target, "s1", options("yaml", "standard"))).not.toBe(keyA);
  });
});
