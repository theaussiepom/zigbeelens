import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { LegacyRoutersRedirect } from "@/components/LegacyRoutersRedirect";
import { api } from "@/lib/api";

describe("LegacyRoutersRedirect", () => {
  it("replace-redirects /routers to /investigate without fetching router risks", () => {
    const routersSpy = vi.spyOn(api, "routers");
    render(
      <MemoryRouter initialEntries={["/routers"]}>
        <Routes>
          <Route path="/routers" element={<LegacyRoutersRedirect />} />
          <Route path="/investigate" element={<div>investigate landing</div>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("investigate landing")).toBeInTheDocument();
    expect(routersSpy).not.toHaveBeenCalled();
  });

  it("respects BrowserRouter basename", () => {
    render(
      <MemoryRouter
        basename="/api/hassio_ingress/token"
        initialEntries={["/api/hassio_ingress/token/routers"]}
      >
        <Routes>
          <Route path="/routers" element={<LegacyRoutersRedirect />} />
          <Route path="/investigate" element={<div>investigate landing</div>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("investigate landing")).toBeInTheDocument();
  });
});
