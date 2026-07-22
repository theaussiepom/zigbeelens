/**
 * Exact Core API Device Story ↔ ReportDetailV3 ↔ UI ViewModel parity.
 * Joins via report_story_keys for every mapped story (not representative-only).
 */
import { describe, expect, it } from "vitest";
import type { DeviceStoryDto } from "@/types/devices";
import { validateReportDetailV3 } from "@/lib/decisionContract";
import { buildDeviceStoryViewModel } from "@/viewModels/topology/deviceStoryViewModel";
import { buildReportDecisionViewModel } from "@/viewModels/reports/reportDecisionViewModel";
import {
  coverageLabel,
  decisionStatusLabel,
  headlineText,
  limitationText,
  reasonText,
  suggestedCheckText,
} from "@/viewModels/decisionCopy";
import { allOracleScenarios } from "@/test/contracts/oracleFixture";
import oracleFixture from "@/test/fixtures/oracleMockScenarios.json";

function codedItems(
  items: Array<{ code: string; params?: Record<string, unknown> }>,
): Array<{ code: string; params: Record<string, unknown> }> {
  return items.map((item) => ({
    code: item.code,
    params: (item.params ?? {}) as Record<string, unknown>,
  }));
}

describe("Core → UI → ReportDetailV3 Device Story parity", () => {
  it.each(allOracleScenarios())(
    "all report_story_keys stay exactly aligned for %s",
    (scenarioId, scenario) => {
      validateReportDetailV3(scenario.report);
      const reportByKey = new Map(
        scenario.report.device_stories.map((story) => [
          `${story.network_id}|${story.ieee_address}`,
          story,
        ]),
      );
      const reportVm = buildReportDecisionViewModel(scenario.report);
      expect(reportVm.reportVersion).toBe(3);

      for (const [rawKey, reportKey] of Object.entries(scenario.report_story_keys)) {
        const apiStory = scenario.device_stories[
          rawKey as keyof typeof scenario.device_stories
        ] as DeviceStoryDto;
        expect(apiStory, `${scenarioId}:${rawKey}`).toBeTruthy();
        const reportStory = reportByKey.get(reportKey);
        expect(reportStory, `${scenarioId}:${reportKey}`).toBeTruthy();

        expect(reportStory!.status).toBe(apiStory.status);
        expect(reportStory!.priority).toBe(apiStory.priority);
        expect(reportStory!.headline_code).toBe(apiStory.headline_code);
        expect(reportStory!.subject_type).toBe(apiStory.subject_type);
        expect(codedItems(reportStory!.reasons)).toEqual(codedItems(apiStory.reasons));
        expect(codedItems(reportStory!.limitations)).toEqual(
          codedItems(apiStory.limitations),
        );
        expect(codedItems(reportStory!.suggested_checks)).toEqual(
          codedItems(apiStory.suggested_checks),
        );
        expect(
          (reportStory!.coverage ?? []).map((item) => ({
            dimension: item.dimension,
            state: item.state,
            label_code: item.label_code,
            params: item.params ?? {},
          })),
        ).toEqual(
          (apiStory.coverage ?? []).map((item) => ({
            dimension: item.dimension,
            state: item.state,
            label_code: item.label_code,
            params: item.params ?? {},
          })),
        );
        expect(reportStory!.related_unresolved_incident_ids ?? []).toEqual(
          apiStory.related_unresolved_incident_ids ?? [],
        );
        expect(
          (reportStory!.timeline ?? []).map((item) => ({
            code: item.code,
            params: item.params ?? {},
            occurred_at: item.occurred_at ?? null,
          })),
        ).toEqual(
          (apiStory.timeline ?? []).map((item) => ({
            code: item.code,
            params: item.params ?? {},
            occurred_at: item.occurred_at ?? null,
          })),
        );

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
        expect(reportItem!.story.coverageItems.map((item) => item.label)).toEqual(
          apiVm.coverageItems.map((item) => item.label),
        );
      }
    },
  );

  it("maps every vocabulary status and primary copy code through presentation helpers", () => {
    expect(oracleFixture.vocabulary.decision_statuses.length).toBeGreaterThan(0);
    for (const status of oracleFixture.vocabulary.decision_statuses) {
      expect(decisionStatusLabel(status).trim().length).toBeGreaterThan(0);
    }
    for (const code of oracleFixture.vocabulary.headline_codes) {
      expect(headlineText(code).trim().length).toBeGreaterThan(0);
    }
    for (const code of oracleFixture.vocabulary.reason_codes) {
      expect(reasonText(code, {}).trim().length).toBeGreaterThan(0);
    }
    for (const code of oracleFixture.vocabulary.limitation_codes) {
      expect(limitationText(code, {}).trim().length).toBeGreaterThan(0);
    }
    for (const code of oracleFixture.vocabulary.suggested_check_codes) {
      expect(suggestedCheckText(code, {}).trim().length).toBeGreaterThan(0);
    }
    for (const code of oracleFixture.vocabulary.coverage_label_codes) {
      expect(coverageLabel(code, {}).trim().length).toBeGreaterThan(0);
    }
  });
});
