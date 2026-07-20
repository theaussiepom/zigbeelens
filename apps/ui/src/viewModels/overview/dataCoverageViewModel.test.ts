import { describe, expect, it } from "vitest";
import type { DataCoverageWarningSummary } from "@zigbeelens/shared";
import { buildDataCoverageWarningViewModel } from "./dataCoverageViewModel";

function makeWarning(
  overrides: Partial<DataCoverageWarningSummary> = {},
): DataCoverageWarningSummary {
  return {
    id: "coverage-home-availability_tracking_off",
    network_id: "home",
    dimension: "availability",
    state: "off",
    label_code: "availability_tracking_off",
    scope_type: "network",
    params: {},
    ...overrides,
  };
}

describe("dataCoverageViewModel", () => {
  it("maps availability tracking off with Overview meaning and check", () => {
    const vm = buildDataCoverageWarningViewModel(makeWarning(), "Home");
    expect(vm.title).toBe("Availability tracking off");
    expect(vm.summary).toMatch(/not being collected for Home/i);
    expect(vm.check).toMatch(/Zigbee2MQTT availability configuration/i);
    expect(vm.meshHref).toBe("/investigate/home");
    const userFacing = [vm.title, vm.summary, vm.check, vm.networkLabel, vm.meshLinkLabel].join(" ");
    expect(userFacing).not.toContain("availability_tracking_off");
  });

  it("maps history building, status unknown, and snapshot stale copy", () => {
    expect(
      buildDataCoverageWarningViewModel(
        makeWarning({ label_code: "availability_history_building", state: "building" }),
        "Home",
      ).title,
    ).toBe("Availability history building");
    expect(
      buildDataCoverageWarningViewModel(
        makeWarning({ label_code: "availability_status_unknown", state: "unknown" }),
        "Home",
      ).title,
    ).toBe("Availability status unknown");
    expect(
      buildDataCoverageWarningViewModel(
        makeWarning({ label_code: "snapshot_stale", state: "stale", dimension: "topology_snapshot" }),
        "Home",
      ).summary,
    ).toMatch(/old enough to limit current Mesh interpretation/i);
  });

  it("fails safely for unknown coverage codes without exposing raw values", () => {
    const vm = buildDataCoverageWarningViewModel(
      makeWarning({ label_code: "future_coverage_code_v2" }),
      "Home",
    );
    expect(vm.title).toBe("Coverage status unknown");
    expect(vm.tone).toBe("muted");
    expect(JSON.stringify(vm)).not.toContain("future_coverage_code_v2");
  });

  it("uses Network fallback for unknown network names", () => {
    const vm = buildDataCoverageWarningViewModel(makeWarning({ network_id: "x" }), null);
    expect(vm.networkLabel).toBe("Network");
  });
});
