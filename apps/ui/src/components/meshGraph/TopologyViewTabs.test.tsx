import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { TopologyViewTabs } from "@/components/meshGraph/TopologyViewTabs";

describe("TopologyViewTabs", () => {
  it("links Investigate and Raw snapshot to canonical routes", () => {
    render(
      <MemoryRouter initialEntries={["/investigate/home"]}>
        <TopologyViewTabs networkId="home" />
      </MemoryRouter>,
    );
    expect(screen.getByRole("tab", { name: "Investigate" })).toHaveAttribute(
      "href",
      "/investigate/home",
    );
    expect(screen.getByRole("tab", { name: "Raw snapshot" })).toHaveAttribute(
      "href",
      "/topology/home",
    );
  });
});
