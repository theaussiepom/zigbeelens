import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
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
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const checkedInFixture = path.join(
  repoRoot,
  "apps/ui/src/test/fixtures/oracleMockScenarios.json",
);
const generator = path.join(repoRoot, "apps/core/scripts/generate_oracle_mock_fixtures.py");
const corePython = path.join(repoRoot, "apps/core/.venv/bin/python");

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

  it.each(scenarioIds)("validates report for %s", (scenarioId) => {
    const scenario = oracleMockScenarios[scenarioId as keyof typeof oracleMockScenarios];
    expect(scenario.report).not.toBeNull();
    validateReportDetailV3(scenario.report);
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
    expect(scenario.report).not.toBeNull();
    expect(() => validateReportDetailV3(scenario.report)).not.toThrow();
  });

  it("checked-in oracle fixture matches Core generation", () => {
    const tempDir = mkdtempSync(path.join(tmpdir(), "oracle-fixture-"));
    const generatedPath = path.join(tempDir, "oracleMockScenarios.json");
    try {
      execFileSync(corePython, [generator, "--output", generatedPath], {
        cwd: repoRoot,
        stdio: "pipe",
      });
      const generated = readFileSync(generatedPath, "utf8");
      const checkedIn = readFileSync(checkedInFixture, "utf8");
      expect(generated).toBe(checkedIn);
    } finally {
      rmSync(tempDir, { recursive: true, force: true });
    }
  });
});
