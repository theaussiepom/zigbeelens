import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { investigatePath } from "@/lib/routes";

function DecodedParamProbe({ onReady }: { onReady: (networkId: string) => void }) {
  const { networkId = "" } = useParams<{ networkId: string }>();
  onReady(networkId);
  return <div data-testid="decoded-id">{networkId}</div>;
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
});
