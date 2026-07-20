import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { LegacyTopologyGraphRedirect } from "@/components/LegacyTopologyGraphRedirect";

describe("LegacyTopologyGraphRedirect", () => {
  it("replace-redirects /topology/:networkId/graph to /investigate/:networkId", () => {
    render(
      <MemoryRouter initialEntries={["/topology/home/graph"]}>
        <Routes>
          <Route path="/topology/:networkId/graph" element={<LegacyTopologyGraphRedirect />} />
          <Route path="/investigate/:networkId" element={<div>canonical investigate</div>} />
          <Route path="/topology/:networkId" element={<div>raw snapshot</div>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("canonical investigate")).toBeInTheDocument();
    expect(screen.queryByText("raw snapshot")).not.toBeInTheDocument();
  });
});
