import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { devicePath } from "@/lib/format";
import { investigatePath, topologySnapshotPath } from "@/lib/routes";

function DecodedParamProbe({ onReady }: { onReady: (networkId: string) => void }) {
  const { networkId = "" } = useParams<{ networkId: string }>();
  onReady(networkId);
  return <div data-testid="decoded-id">{networkId}</div>;
}

function DeviceRouteProbe({
  onReady,
}: {
  onReady: (networkId: string, ieee: string) => void;
}) {
  const { networkId = "", ieeeAddress = "" } = useParams<{
    networkId: string;
    ieeeAddress: string;
  }>();
  onReady(networkId, ieeeAddress);
  return (
    <div>
      <span data-testid="decoded-network">{networkId}</span>
      <span data-testid="decoded-ieee">{ieeeAddress}</span>
    </div>
  );
}

describe("encoded network route params", () => {
  it("exposes decoded network IDs to route consumers for API calls", () => {
    const seen: string[] = [];
    const spy = vi.spyOn(api, "topologyNetwork").mockResolvedValue({} as never);
    render(
      <MemoryRouter initialEntries={[investigatePath("Home Office")]}>
        <Routes>
          <Route
            path="/investigate/:networkId"
            element={
              <DecodedParamProbe
                onReady={(networkId) => {
                  seen.push(networkId);
                  void api.topologyNetwork(networkId);
                }}
              />
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("decoded-id")).toHaveTextContent("Home Office");
    expect(seen).toEqual(["Home Office"]);
    expect(spy).toHaveBeenCalledWith("Home Office");
    expect(spy).not.toHaveBeenCalledWith("Home%20Office");
  });

  it.each([
    ["home", "/topology/home"],
    ["Home Office", "/topology/Home%20Office"],
    ["home#2", "/topology/home%232"],
    ["home?test", "/topology/home%3Ftest"],
    ["münchen", "/topology/m%C3%BCnchen"],
    ["50%mesh", "/topology/50%25mesh"],
    ["home%20office", "/topology/home%2520office"],
  ] as const)(
    "topology route yields logical id %j from %s without double decoding",
    (logicalId, path) => {
      expect(topologySnapshotPath(logicalId)).toBe(path);
      const seen: string[] = [];
      render(
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route
              path="/topology/:networkId"
              element={<DecodedParamProbe onReady={(id) => seen.push(id)} />}
            />
          </Routes>
        </MemoryRouter>,
      );
      expect(seen).toEqual([logicalId]);
      expect(screen.getByTestId("decoded-id")).toHaveTextContent(logicalId);
    },
  );

  it("Device Detail route exposes logical network and ieee values", () => {
    const seen: Array<[string, string]> = [];
    render(
      <MemoryRouter initialEntries={[devicePath("Home Office", "0xab/cd")]}>
        <Routes>
          <Route
            path="/devices/:networkId/:ieeeAddress"
            element={
              <DeviceRouteProbe
                onReady={(networkId, ieee) => {
                  seen.push([networkId, ieee]);
                }}
              />
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(seen).toEqual([["Home Office", "0xab/cd"]]);
    expect(screen.getByTestId("decoded-network")).toHaveTextContent("Home Office");
    expect(screen.getByTestId("decoded-ieee")).toHaveTextContent("0xab/cd");
  });
});
