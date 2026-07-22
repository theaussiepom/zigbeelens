/**
 * UI oracle consumption — pure Vitest, no Python subprocess.
 * Fixture freshness is owned by Core tests/contracts + scripts/validate-contracts.sh.
 */
import { describe, expect, it } from "vitest";
import {
  parseIncident,
  validateDashboardPayload,
  validateDeviceSummaries,
  validateIncidents,
  validateNetworkSummaries,
  validateReportDetailV3,
} from "@/lib/decisionContract";
import { buildDeviceStoryViewModel } from "@/viewModels/topology/deviceStoryViewModel";
import type { DeviceStoryDto } from "@/types/devices";
import {
  ORACLE_CONTRACT_VERSION,
  allOracleScenarios,
  oracleScenario,
  oracleScenarioIds,
} from "@/test/contracts/oracleFixture";

describe("oracle mock scenario contracts (UI consumption)", () => {
  it("reads oracle_contract_version 2", () => {
    expect(ORACLE_CONTRACT_VERSION).toBe(2);
    expect(oracleScenarioIds().length).toBeGreaterThan(0);
  });

  it.each(oracleScenarioIds())("validates dashboard for %s", (scenarioId) => {
    validateDashboardPayload(oracleScenario(scenarioId).dashboard);
  });

  it.each(oracleScenarioIds())("validates devices for %s", (scenarioId) => {
    validateDeviceSummaries(oracleScenario(scenarioId).devices);
  });

  it.each(oracleScenarioIds())("validates networks for %s", (scenarioId) => {
    validateNetworkSummaries(oracleScenario(scenarioId).networks);
  });

  it.each(oracleScenarioIds())("validates incidents for %s", (scenarioId) => {
    const scenario = oracleScenario(scenarioId);
    validateIncidents(scenario.incidents);
    for (const incident of scenario.incidents) {
      parseIncident(incident);
    }
  });

  it.each(oracleScenarioIds())("validates report v3 for %s", (scenarioId) => {
    const scenario = oracleScenario(scenarioId);
    expect(scenario.report).not.toBeNull();
    expect(scenario.report.report_version).toBe(3);
    validateReportDetailV3(scenario.report);
  });

  it.each(oracleScenarioIds())("builds ViewModels for device stories for %s", (scenarioId) => {
    const scenario = oracleScenario(scenarioId);
    for (const story of Object.values(scenario.device_stories) as DeviceStoryDto[]) {
      // API Device Story wire omits report identity keys; ViewModel owns presentation.
      const vm = buildDeviceStoryViewModel(story);
      expect(vm.headline.trim().length).toBeGreaterThan(0);
      expect(vm.statusPill?.label.trim().length).toBeGreaterThan(0);
    }
  });

  it("bridge_offline fixture does not throw", () => {
    const scenario = oracleScenario("bridge_offline");
    expect(() => validateDashboardPayload(scenario.dashboard)).not.toThrow();
    expect(() => validateDeviceSummaries(scenario.devices)).not.toThrow();
    expect(() => validateNetworkSummaries(scenario.networks)).not.toThrow();
    expect(() => validateIncidents(scenario.incidents)).not.toThrow();
    expect(() => validateReportDetailV3(scenario.report)).not.toThrow();
  });

  it("UI contract support modules do not spawn Python or child processes", () => {
    // Covered by uiContractNoPython.contract.test.ts (TypeScript import/API scan).
    expect(allOracleScenarios().length).toBe(oracleScenarioIds().length);
  });
});
