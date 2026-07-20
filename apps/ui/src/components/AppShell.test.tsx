import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/AppShell";
import { PRIMARY_NAVIGATION } from "@/navigation/model";

vi.mock("@/context/BrowserAuthContext", () => ({
  useAuth: () => ({
    authMethod: "trusted_local",
    expiresAt: null,
    logout: vi.fn(),
    logoutBusy: false,
    logoutError: null,
  }),
}));

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({
    scenario: "",
    setScenario: vi.fn(),
    scenarios: [],
    status: { data_mode: "mock", version: "0.1.13" },
    dataMode: "mock",
    isScenarioMode: true,
    mqttConnected: false,
  }),
}));

vi.mock("@/hooks/useConnection", () => ({
  useConnection: () => "disconnected",
}));

vi.mock("@/lib/flags", () => ({
  scenariosEnabled: () => false,
}));

function renderShell(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="*" element={<div>page</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("AppShell navigation", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders the same six primary items on desktop and mobile from one model", () => {
    renderShell("/");
    const navs = screen.getAllByRole("navigation", { name: /main navigation/i });
    expect(navs).toHaveLength(2);
    for (const nav of navs) {
      const labels = within(nav)
        .getAllByRole("link")
        .map((el) => el.textContent)
        .filter((label) => PRIMARY_NAVIGATION.some((item) => item.label === label));
      expect(labels).toEqual(PRIMARY_NAVIGATION.map((item) => item.label));
    }
    expect(screen.queryByRole("link", { name: "Networks" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Routers" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Topology" })).not.toBeInTheDocument();
  });

  it("marks Mesh / Investigate current for investigation detail routes", () => {
    renderShell("/investigate/home");
    const links = screen.getAllByRole("link", { name: "Mesh / Investigate" });
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) {
      expect(link).toHaveAttribute("aria-current", "page");
    }
  });

  it("exposes Advanced & support routes without writing localStorage", async () => {
    const user = userEvent.setup();
    renderShell("/devices");
    expect(localStorage.length).toBe(0);
    const desktopToggle = screen.getByRole("button", { name: /advanced & support/i });
    await user.click(desktopToggle);
    expect(screen.getByRole("link", { name: "Networks" })).toHaveAttribute("href", "/networks");
    expect(screen.queryByRole("link", { name: "Router diagnostics" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Timeline" })).toHaveAttribute("href", "/timeline");
    expect(screen.getByRole("link", { name: "Topology snapshots" })).toHaveAttribute(
      "href",
      "/topology",
    );
    expect(screen.getByRole("link", { name: "How it works" })).toHaveAttribute(
      "href",
      "/monitoring",
    );
    expect(localStorage.length).toBe(0);
  });

  it("opens advanced disclosure for supporting deep links", () => {
    renderShell("/topology/home");
    expect(screen.getByRole("button", { name: /advanced & support/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    const topologyLinks = screen.getAllByRole("link", { name: "Topology snapshots" });
    expect(topologyLinks.length).toBeGreaterThan(0);
    for (const link of topologyLinks) {
      expect(link).toHaveAttribute("aria-current", "page");
    }
  });

  it("supports keyboard Escape on the mobile Advanced menu", async () => {
    const user = userEvent.setup();
    renderShell("/");
    const mobileToggle = screen.getByRole("button", {
      name: /advanced and support navigation/i,
    });
    await user.click(mobileToggle);
    expect(screen.getByRole("link", { name: "Networks" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("link", { name: "Networks" })).not.toBeInTheDocument();
  });

  it("keeps the mobile Advanced popup outside the overflow-x-auto scroller", async () => {
    const user = userEvent.setup();
    renderShell("/");
    const scroller = screen.getByTestId("mobile-primary-nav-scroller");
    expect(scroller.className).toContain("overflow-x-auto");
    const mobileToggle = screen.getByRole("button", {
      name: /advanced and support navigation/i,
    });
    expect(scroller.contains(mobileToggle)).toBe(false);
    await user.click(mobileToggle);
    const popup = screen.getByRole("link", { name: "Networks" }).closest("[id]");
    expect(popup).toBeTruthy();
    expect(scroller.contains(popup)).toBe(false);
    expect(screen.getByTestId("mobile-nav-shell").contains(mobileToggle)).toBe(true);
  });
});

