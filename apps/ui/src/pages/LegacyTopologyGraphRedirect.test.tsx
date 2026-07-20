import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { LegacyTopologyGraphRedirect } from "@/components/LegacyTopologyGraphRedirect";

function InvestigateProbe() {
  const { networkId } = useParams<{ networkId: string }>();
  return <div>{`canonical:${networkId}`}</div>;
}

describe("LegacyTopologyGraphRedirect", () => {
  it("replace-redirects /topology/:networkId/graph to /investigate/:networkId", () => {
    render(
      <MemoryRouter initialEntries={["/topology/home/graph"]}>
        <Routes>
          <Route path="/topology/:networkId/graph" element={<LegacyTopologyGraphRedirect />} />
          <Route path="/investigate/:networkId" element={<InvestigateProbe />} />
          <Route path="/topology/:networkId" element={<div>raw snapshot</div>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("canonical:home")).toBeInTheDocument();
    expect(screen.queryByText("raw snapshot")).not.toBeInTheDocument();
  });

  it("preserves encoded network IDs through the redirect as decoded route params", () => {
    render(
      <MemoryRouter
        basename="/api/hassio_ingress/token"
        initialEntries={["/api/hassio_ingress/token/topology/Home%20Office/graph"]}
      >
        <Routes>
          <Route path="/topology/:networkId/graph" element={<LegacyTopologyGraphRedirect />} />
          <Route path="/investigate/:networkId" element={<InvestigateProbe />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("canonical:Home Office")).toBeInTheDocument();
  });
});

