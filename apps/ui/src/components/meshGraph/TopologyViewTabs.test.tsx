import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { TopologyViewTabs } from "@/components/meshGraph/TopologyViewTabs";

describe("TopologyViewTabs", () => {
  it("exposes Investigate and Raw snapshot as navigation links", () => {
    render(
      <MemoryRouter initialEntries={["/investigate/home"]}>
        <TopologyViewTabs networkId="home" />
      </MemoryRouter>,
    );
    expect(screen.getByRole("navigation", { name: /network investigation views/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Investigate" })).toHaveAttribute(
      "href",
      "/investigate/home",
    );
    expect(screen.getByRole("link", { name: "Raw snapshot" })).toHaveAttribute(
      "href",
      "/topology/home",
    );
  });

  it("encodes network IDs in hrefs", () => {
    render(
      <MemoryRouter initialEntries={["/investigate/Home%20Office"]}>
        <TopologyViewTabs networkId="Home Office" />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Investigate" })).toHaveAttribute(
      "href",
      "/investigate/Home%20Office",
    );
    expect(screen.getByRole("link", { name: "Raw snapshot" })).toHaveAttribute(
      "href",
      "/topology/Home%20Office",
    );
  });
});
