import { describe, expect, it } from "vitest";
import type { DeviceStoryDto } from "@/types/devices";
import { buildMeshEvidenceReport } from "@/lib/meshEvidenceReport";
import { buildDeviceStoryReportSection } from "@/viewModels/topology/deviceStoryReportSection";
import { buildDeviceStoryViewModel } from "@/viewModels/topology/deviceStoryViewModel";

const topologyGapStory: DeviceStoryDto = {
  subject_type: "device",
  subject_id: "0x03",
  status: "watch",
  priority: "low",
  headline_code: "topology_evidence_gap",
  reasons: [
    { code: "latest_snapshot_no_links", params: {} },
    { code: "selected_snapshot_had_links", params: { selected_snapshot_link_count: 1 } },
  ],
  evidence: [
    {
      source: "topology_snapshot",
      id: "snap-latest",
      captured_at: "2026-07-13T02:00:00Z",
      label: null,
    },
  ],
  limitations: [{ code: "absence_from_latest_not_failure", params: {} }],
  suggested_checks: [{ code: "compare_earlier_snapshot", params: {} }],
  coverage: [
    {
      dimension: "route_hints",
      state: "not_observed",
      label_code: "route_hints_unavailable",
      params: {},
    },
  ],
  timeline: [],
};

const extendedSilenceStory: DeviceStoryDto = {
  subject_type: "device",
  subject_id: "0x03",
  status: "watch",
  priority: "low",
  headline_code: "extended_reporting_silence",
  reasons: [
    {
      code: "observed_reporting_rhythm",
      params: {
        interval_minutes_p25: 60,
        interval_minutes_median: 60,
        interval_minutes_p75: 60,
        interval_minutes_max: 60,
      },
    },
    {
      code: "reporting_silence_beyond_expected",
      params: {
        silence_minutes: 240,
        extended_silence_threshold_minutes: 150,
      },
    },
  ],
  evidence: [],
  limitations: [{ code: "extended_silence_not_failure", params: {} }],
  suggested_checks: [
    { code: "confirm_powered", params: {} },
    { code: "confirm_reporting_in_z2m", params: {} },
  ],
  coverage: [],
  timeline: [],
};

describe("deviceStory report parity", () => {
  it("maps ViewModel prose into a report section without reinterpreting codes", () => {
    const viewModel = buildDeviceStoryViewModel(topologyGapStory);
    const section = buildDeviceStoryReportSection(viewModel);

    expect(section.lines.join("\n")).toContain("## Device story");
    expect(section.lines.join("\n")).toContain("**Watch** — Topology evidence gap");
    expect(section.lines.join("\n")).toContain(viewModel.reasons[0]!);
    expect(section.lines.join("\n")).toContain(viewModel.limitations[0]!);
    expect(section.lines.join("\n")).toContain(viewModel.suggestedChecks[0]!);
    expect(section.lines.join("\n")).toContain("Route hints unavailable");
    expect(section.lines.join("\n")).not.toContain("topology_evidence_gap");
    expect(section.lines.join("\n")).not.toContain("latest_snapshot_no_links");
  });

  it("keeps mesh evidence report JSON summary aligned with the ViewModel", () => {
    const viewModel = buildDeviceStoryViewModel(topologyGapStory);
    const report = buildMeshEvidenceReport({
      networkId: "home",
      generatedAt: new Date(2026, 6, 13, 12, 0),
      devices: [],
      edges: [],
      investigations: [],
      deviceStory: viewModel,
    });

    expect(report.jsonSummary.device_story).toEqual({
      status_label: "Watch",
      headline: "Topology evidence gap",
      reasons: viewModel.reasons,
      limitations: viewModel.limitations,
      suggested_checks: viewModel.suggestedChecks,
    });
    expect(report.markdown).toContain("Topology evidence gap");
    expect(report.markdown).toContain(viewModel.reasons[0]!);
  });

  it("omits device story from reports when no ViewModel is supplied", () => {
    const report = buildMeshEvidenceReport({
      networkId: "home",
      generatedAt: new Date(2026, 6, 13, 12, 0),
      devices: [],
      edges: [],
      investigations: [],
    });

    expect(report.jsonSummary.device_story).toBeNull();
    expect(report.markdown).not.toContain("## Device story");
  });

  it("keeps extended reporting silence aligned between ViewModel and report output", () => {
    const viewModel = buildDeviceStoryViewModel(extendedSilenceStory);
    const section = buildDeviceStoryReportSection(viewModel);
    const markdown = section.lines.join("\n");

    expect(markdown).toContain("**Watch** — Extended reporting silence");
    expect(markdown).toContain(viewModel.reasons[0]!);
    expect(markdown).toContain(viewModel.reasons[1]!);
    expect(markdown).toContain(viewModel.limitations[0]!);
    expect(markdown).not.toContain("extended_reporting_silence");
    expect(markdown).not.toContain("reporting_silence_beyond_expected");
    expect(markdown).not.toContain("extended-silence threshold");
    expect(markdown).not.toContain("threshold of");
    expect(markdown).not.toContain("suspicion_threshold_minutes");

    const report = buildMeshEvidenceReport({
      networkId: "home",
      generatedAt: new Date(2026, 6, 13, 12, 0),
      devices: [],
      edges: [],
      investigations: [],
      deviceStory: viewModel,
    });

    expect(report.jsonSummary.device_story).toEqual({
      status_label: "Watch",
      headline: "Extended reporting silence",
      reasons: viewModel.reasons,
      limitations: viewModel.limitations,
      suggested_checks: viewModel.suggestedChecks,
    });
    expect(report.markdown).toContain("Extended reporting silence");
  });
});
