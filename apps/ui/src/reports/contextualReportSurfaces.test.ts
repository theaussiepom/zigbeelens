import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const uiSrc = path.join(__dirname, "..");

function read(rel: string): string {
  return readFileSync(path.join(uiSrc, rel), "utf8");
}

describe("contextual report surface contracts", () => {
  it("Device Detail exposes a device-scoped action independent of snapshot history", () => {
    const source = read("pages/DevicesPage.tsx");
    expect(source).toMatch(/Create device report/);
    expect(source).toMatch(/scope:\s*"device"/);
    expect(source).toMatch(/deviceIeee:\s*device\.ieee_address/);
    expect(source).toMatch(/networkId:\s*device\.network_id/);
    expect(source).toMatch(/ContextualReportDialog/);
    const detailStart = source.indexOf("export function DeviceDetailPage");
    const detail = source.slice(detailStart);
    const historyIdx = detail.indexOf("<DeviceSnapshotHistory");
    const actionIdx = detail.indexOf("Create device report");
    expect(actionIdx).toBeGreaterThan(-1);
    expect(historyIdx).toBeGreaterThan(-1);
    expect(actionIdx).toBeLessThan(historyIdx);
  });

  it("Incident Detail exposes an incident-scoped action", () => {
    const source = read("pages/IncidentsPage.tsx");
    expect(source).toMatch(/Create incident report/);
    expect(source).toMatch(/scope:\s*"incident"/);
    expect(source).toMatch(/incidentId:\s*inc\.id/);
    expect(source).toMatch(/ContextualReportDialog/);
  });

  it("Network Detail exposes a network report while retaining Mesh investigation", () => {
    const source = read("pages/NetworksPage.tsx");
    expect(source).toMatch(/Create network report/);
    expect(source).toMatch(/Review this network in Mesh/);
    expect(source).toMatch(/scope:\s*"network"/);
    expect(source).toMatch(/networkId:\s*n\.id/);
  });

  it("does not parse rendered labels into report identifiers", () => {
    const dialog = read("components/reports/ContextualReportDialog.tsx");
    const target = read("reports/contextualReportTarget.ts");
    for (const source of [dialog, target]) {
      expect(source).not.toMatch(/split\(["']\|["']\)/);
      expect(source).not.toMatch(/decodeURIComponent/);
      expect(source).not.toMatch(/subjectLabel\.match/);
    }
  });
});
