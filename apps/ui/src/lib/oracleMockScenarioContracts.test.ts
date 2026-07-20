import { describe, expect, it } from "vitest";
import oracleMockScenarios from "@/test/fixtures/oracleMockScenarios.json";
import {
  parseIncident,
  validateDashboardPayload,
  validateDeviceSummaries,
  validateIncidents,
  validateNetworkSummaries,
  validateReportDetailV3,
} from "@/lib/decisionContract";

const scenarioIds = Object.keys(oracleMockScenarios).sort();

describe("oracle mock scenario contracts", () => {
  it.each(scenarioIds)("validates dashboard for %s", (scenarioId) => {
    const scenario = oracleMockScenarios[scenarioId as keyof typeof oracleMockScenarios];
    validateDashboardPayload(scenario.dashboard);
  });

  it.each(scenarioIds)("validates devices for %s", (scenarioId) => {
    const scenario = oracleMockScenarios[scenarioId as keyof typeof oracleMockScenarios];
    validateDeviceSummaries(scenario.devices);
  });

  it.each(scenarioIds)("validates networks for %s", (scenarioId) => {
    const scenario = oracleMockScenarios[scenarioId as keyof typeof oracleMockScenarios];
    validateNetworkSummaries(scenario.networks);
  });

  it.each(scenarioIds)("validates incidents for %s", (scenarioId) => {
    const scenario = oracleMockScenarios[scenarioId as keyof typeof oracleMockScenarios];
    validateIncidents(scenario.incidents);
    for (const incident of scenario.incidents) {
      parseIncident(incident);
    }
  });

  it.each(scenarioIds)("validates report when present for %s", (scenarioId) => {
    const scenario = oracleMockScenarios[scenarioId as keyof typeof oracleMockScenarios];
    if (scenario.report !== null) {
      validateReportDetailV3(scenario.report);
    }
  });

  it("bridge_offline fixture does not throw", () => {
    const scenario = oracleMockScenarios.bridge_offline;
    expect(() => validateDashboardPayload(scenario.dashboard)).not.toThrow();
    expect(() => validateDeviceSummaries(scenario.devices)).not.toThrow();
    expect(() => validateNetworkSummaries(scenario.networks)).not.toThrow();
    expect(() => validateIncidents(scenario.incidents)).not.toThrow();
    for (const incident of scenario.incidents) {
      expect(() => parseIncident(incident)).not.toThrow();
    }
    if (scenario.report !== null) {
      expect(() => validateReportDetailV3(scenario.report)).not.toThrow();
    }
  });
});
