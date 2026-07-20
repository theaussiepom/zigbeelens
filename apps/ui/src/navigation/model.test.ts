import { describe, expect, it } from "vitest";
import {
  ADVANCED_NAVIGATION,
  PRIMARY_NAVIGATION,
  isAdvancedRoute,
} from "@/navigation/model";

describe("navigation model", () => {
  it("exposes exactly six primary items in order", () => {
    expect(PRIMARY_NAVIGATION.map((item) => item.label)).toEqual([
      "Overview",
      "Mesh / Investigate",
      "Devices",
      "Incidents",
      "Reports",
      "Settings",
    ]);
    expect(PRIMARY_NAVIGATION).toHaveLength(6);
  });

  it("keeps supporting routes under Advanced & support without Router diagnostics", () => {
    expect(ADVANCED_NAVIGATION.map((item) => [item.label, item.to])).toEqual([
      ["Networks", "/networks"],
      ["Timeline", "/timeline"],
      ["Topology snapshots", "/topology"],
      ["How it works", "/monitoring"],
    ]);
    expect(ADVANCED_NAVIGATION).toHaveLength(4);
    expect(ADVANCED_NAVIGATION.some((item) => item.to === "/routers")).toBe(false);
  });

  it("activates detail routes under their parent workflow", () => {
    expect(PRIMARY_NAVIGATION[1]!.isActive("/investigate/home")).toBe(true);
    expect(PRIMARY_NAVIGATION[2]!.isActive("/devices/home/0xabc")).toBe(true);
    expect(PRIMARY_NAVIGATION[3]!.isActive("/incidents/inc-1")).toBe(true);
    expect(ADVANCED_NAVIGATION[0]!.isActive("/networks/home")).toBe(true);
    expect(ADVANCED_NAVIGATION[2]!.isActive("/topology/home")).toBe(true);
  });

  it("does not treat advanced routes as primary peers", () => {
    for (const path of ["/networks", "/timeline", "/topology", "/monitoring"]) {
      expect(PRIMARY_NAVIGATION.some((item) => item.isActive(path))).toBe(false);
      expect(isAdvancedRoute(path)).toBe(true);
    }
    expect(isAdvancedRoute("/routers")).toBe(false);
  });
});
