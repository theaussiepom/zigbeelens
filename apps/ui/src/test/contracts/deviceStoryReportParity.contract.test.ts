/**
 * Core API Device Story → UI ViewModel → ReportDetailV3 semantic parity.
 * Replaces obsolete client-only MeshEvidenceReport authority (Phase 6D/7B).
 *
 * Note: Core Device Story API wire shape omits network_id/ieee/friendly_name;
 * ReportDeviceStory includes those identity fields. parseDeviceStory validates
 * the report wire shape (used by validateReportDetailV3). API stories are
 * consumed as DeviceStoryDto without that identity key set.
 */
import { describe, expect, it } from "vitest";
import type { DeviceStoryDto } from "@/types/devices";
import { validateReportDetailV3 } from "@/lib/decisionContract";
import { buildDeviceStoryViewModel } from "@/viewModels/topology/deviceStoryViewModel";
import { buildReportDecisionViewModel } from "@/viewModels/reports/reportDecisionViewModel";
import { allOracleScenarios } from "@/test/contracts/oracleFixture";

function codes(items: Array<{ code: string }>): string[] {
  return items.map((item) => item.code);
}

function assertSemanticParity(
  apiStory: DeviceStoryDto,
  reportStory: {
    status: string;
    priority: string;
    headline_code: string;
    reasons: Array<{ code: string; params?: Record<string, unknown> }>;
    limitations: Array<{ code: string; params?: Record<string, unknown> }>;
    suggested_checks: Array<{ code: string; params?: Record<string, unknown> }>;
    coverage: Array<{
      dimension: string;
      state: string;
      label_code: string;
    }>;
  },
) {
  expect(reportStory.status).toBe(apiStory.status);
  expect(reportStory.priority).toBe(apiStory.priority);
  expect(reportStory.headline_code).toBe(apiStory.headline_code);
  expect(codes(reportStory.reasons)).toEqual(codes(apiStory.reasons));
  expect(codes(reportStory.limitations)).toEqual(codes(apiStory.limitations));
  expect(codes(reportStory.suggested_checks)).toEqual(
    codes(apiStory.suggested_checks),
  );
  expect(
    reportStory.coverage.map((item) => [
      item.dimension,
      item.state,
      item.label_code,
    ]),
  ).toEqual(
    apiStory.coverage.map((item) => [
      item.dimension,
      item.state,
      item.label_code,
    ]),
  );
}

describe("Core → UI → ReportDetailV3 Device Story parity", () => {
  it.each(allOracleScenarios())(
    "representative subjects stay semantically aligned for %s",
    (scenarioId, scenario) => {
      validateReportDetailV3(scenario.report);
      const reportByKey = new Map(
        scenario.report.device_stories.map((story) => [
          `${story.network_id}|${story.ieee_address}`,
          story,
        ]),
      );
      const reportVm = buildReportDecisionViewModel(scenario.report);
      expect(reportVm.isLegacyFormat).toBe(false);
      expect(reportVm.reportVersion).toBe(3);

      for (const subject of scenario.representative_subjects) {
        const rawKey = `${subject.network_id}|${subject.ieee_address}`;
        const apiStory = scenario.device_stories[
          rawKey as keyof typeof scenario.device_stories
        ] as DeviceStoryDto;
        expect(apiStory, `${scenarioId}:${rawKey}`).toBeTruthy();

        const reportKey = subject.report_story_key;
        const reportStory = reportByKey.get(reportKey);
        expect(reportStory, `${scenarioId}:${reportKey}`).toBeTruthy();
        assertSemanticParity(apiStory, reportStory!);

        const apiVm = buildDeviceStoryViewModel(apiStory);
        const reportItem = reportVm.deviceStories.find(
          (item) =>
            item.networkId === reportStory!.network_id &&
            item.ieeeAddress === reportStory!.ieee_address,
        );
        expect(reportItem, `${scenarioId} report VM`).toBeTruthy();
        expect(reportItem!.story.statusPill?.label).toBe(apiVm.statusPill?.label);
        expect(reportItem!.story.headline).toBe(apiVm.headline);
        expect(reportItem!.story.reasons).toEqual(apiVm.reasons);
        expect(reportItem!.story.limitations).toEqual(apiVm.limitations);
        expect(reportItem!.story.suggestedChecks).toEqual(apiVm.suggestedChecks);
      }
    },
  );

  it("covers required status/priority matrix from oracle corpus", () => {
    const statuses = new Set<string>();
    const priorities = new Set<string>();
    for (const [, scenario] of allOracleScenarios()) {
      for (const story of Object.values(scenario.device_stories)) {
        statuses.add(story.status);
        priorities.add(story.priority);
      }
    }
    for (const required of [
      "informational",
      "watch",
      "worth_reviewing",
      "improve_data_coverage",
    ]) {
      expect(statuses.has(required), required).toBe(true);
    }
    expect(priorities.has("low")).toBe(true);
    expect(priorities.has("medium") || priorities.has("high")).toBe(true);
  });
});
