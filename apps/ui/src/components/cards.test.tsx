import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { DeviceSummary, DiagnosticConclusion, Incident } from "@zigbeelens/shared";
import { CurrentFindingCard, DeviceHealthCard, IncidentCard } from "./cards";

function wrap(node: React.ReactNode) {
  return render(<MemoryRouter>{node}</MemoryRouter>);
}

const finding: DiagnosticConclusion = {
  classification: "correlated_device_unavailability",
  severity: "incident",
  scope: "mesh_segment",
  confidence: "medium",
  summary: "4 devices became unavailable on Home2 within 94 seconds.",
  evidence: [{ id: "e1", kind: "availability", summary: "4 devices changed to offline" }],
  counter_evidence: [],
  limitations: [{ id: "l1", summary: "No topology snapshot is available" }],
};

const incident: Incident = {
  id: "inc-1",
  type: "correlated_device_unavailability",
  status: "open",
  severity: "incident",
  scope: "mesh_segment",
  confidence: "medium",
  title: "4 devices unavailable on Home2",
  summary: "Several devices went offline together.",
  interpretation: "This looks like a local mesh segment pattern.",
  network_ids: ["home2"],
  affected_device_count: 4,
  affected_devices: [],
  opened_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:01:00Z",
  evidence: [{ id: "e1", kind: "availability", summary: "4 devices offline within 94s" }],
  counter_evidence: [],
  limitations: [{ id: "l1", summary: "No topology snapshot is available" }],
  timeline: [],
  conclusion: finding,
};

function device(overrides: Partial<DeviceSummary> = {}): DeviceSummary {
  return {
    network_id: "home2",
    ieee_address: "0x99",
    friendly_name: "Hallway sensor",
    device_type: "EndDevice",
    power_source: "Battery",
    availability: "offline",
    interview_state: "successful",
    incident_affected: true,
    sort_priority: 1,
    lens_bucket: "unavailable",
    lens_bucket_label: "Unavailable",
    lens_bucket_reason: "Unavailable",
    lens_reasons: ["Unavailable"],
    health: {
      primary: "unavailable",
      severity: "incident",
      confidence: "high",
      evidence: [],
      counter_evidence: [],
      limitations: [],
    },
    ...overrides,
  };
}

describe("CurrentFindingCard", () => {
  it("shows the summary, evidence, limitations, and incident link", () => {
    wrap(<CurrentFindingCard finding={finding} incidentId="inc-1" />);
    expect(screen.getByText(/4 devices became unavailable/)).toBeInTheDocument();
    expect(screen.getByText("4 devices changed to offline")).toBeInTheDocument();
    expect(screen.getByText("No topology snapshot is available")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view incident detail/i })).toHaveAttribute(
      "href",
      "/incidents/inc-1",
    );
  });
});

describe("IncidentCard", () => {
  it("surfaces lifecycle, title, and affected count", () => {
    wrap(<IncidentCard incident={incident} />);
    expect(screen.getByText("Open")).toBeInTheDocument();
    expect(screen.getByText("4 devices unavailable on Home2")).toBeInTheDocument();
    expect(screen.getByText(/4 affected devices/)).toBeInTheDocument();
  });
});

describe("DeviceHealthCard", () => {
  it("flags incident-affected devices", () => {
    wrap(<DeviceHealthCard device={device()} />);
    expect(screen.getByText("In incident")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });
});
