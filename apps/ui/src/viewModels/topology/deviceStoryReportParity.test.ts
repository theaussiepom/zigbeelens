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

const modelPatternAffectedStory: DeviceStoryDto = {
  subject_type: "device",
  subject_id: "0xm00",
  status: "informational",
  priority: "none",
  headline_code: "no_notable_signals",
  reasons: [
    {
      code: "model_pattern_observed",
      params: {
        pattern_id: "model-pattern-test",
        manufacturer: "IKEA",
        model: "TS011F",
        group_size: 5,
        affected_count: 3,
        lookback_days: 7,
        current_device_affected: true,
      },
    },
  ],
  evidence: [],
  limitations: [{ code: "model_pattern_not_causal", params: {} }],
  suggested_checks: [
    { code: "review_same_model_availability_history", params: {} },
    { code: "compare_same_model_device_context", params: {} },
  ],
  coverage: [],
  timeline: [],
};

const modelPatternContextStory: DeviceStoryDto = {
  ...modelPatternAffectedStory,
  subject_id: "0xm04",
  reasons: [
    {
      code: "model_pattern_observed",
      params: {
        pattern_id: "model-pattern-test",
        manufacturer: "IKEA",
        model: "TS011F",
        group_size: 5,
        affected_count: 3,
        lookback_days: 7,
        current_device_affected: false,
      },
    },
  ],
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

  it("keeps affected model-pattern Device Story aligned between ViewModel and report", () => {
    const viewModel = buildDeviceStoryViewModel(modelPatternAffectedStory);
    const section = buildDeviceStoryReportSection(viewModel);
    const markdown = section.lines.join("\n");

    expect(markdown).toContain(
      "This device is one of 3 of 5 devices with the same model that went offline in the last 7 days.",
    );
    expect(markdown).toContain(viewModel.limitations[0]!);
    expect(markdown).not.toContain("model_pattern_observed");
    expect(markdown.toLowerCase()).not.toContain("likely model defect");

    const report = buildMeshEvidenceReport({
      networkId: "home",
      generatedAt: new Date(2026, 6, 13, 12, 0),
      devices: [],
      edges: [],
      investigations: [],
      deviceStory: viewModel,
    });
    expect(report.jsonSummary.device_story?.reasons).toEqual(viewModel.reasons);
    expect(report.jsonSummary.device_story?.limitations).toEqual(viewModel.limitations);
  });

  it("keeps unaffected same-group model-pattern context non-escalating in reports", () => {
    const viewModel = buildDeviceStoryViewModel(modelPatternContextStory);
    const section = buildDeviceStoryReportSection(viewModel);
    const markdown = section.lines.join("\n");

    expect(markdown).toContain(
      "Other devices with the same model show a recent availability pattern: 3 of 5 went offline in the last 7 days.",
    );
    expect(markdown).toContain("**Informational**");
    expect(markdown.toLowerCase()).not.toContain("worth reviewing");
    expect(markdown.toLowerCase()).not.toContain("manufacturer is to blame");
    expect(markdown).toContain("does not prove a model defect");
  });
});
