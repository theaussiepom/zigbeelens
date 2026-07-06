import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeAll, describe, expect, it } from "vitest";
import { TopologyGraphPage } from "@/pages/TopologyGraphPage";
import { meshEvidenceGraphFixture } from "@/fixtures/meshEvidenceGraph";
import { EVIDENCE_CLASSES, evidenceClassLabel, GRAPH_SAFETY_COPY } from "@/lib/meshEvidence";
import { mockReactFlow } from "@/test/mockReactFlow";

beforeAll(() => {
  mockReactFlow();
});

function renderGraphPage() {
  return render(
    <MemoryRouter initialEntries={["/topology/home/graph"]}>
      <Routes>
        <Route path="/topology/:networkId/graph" element={<TopologyGraphPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

/** Wait for the async ELK layout to finish and nodes to appear. */
async function renderGraphAndWaitForLayout() {
  const result = renderGraphPage();
  await screen.findByText("Living room plug");
  return result;
}

describe("TopologyGraphPage", () => {
  it("renders the graph page with prototype framing", async () => {
    renderGraphPage();
    expect(screen.getByRole("heading", { name: "Mesh evidence graph" })).toBeInTheDocument();
    expect(screen.getByText("Prototype — sample data")).toBeInTheDocument();
    expect(await screen.findByText("Coordinator", { selector: ".truncate" })).toBeInTheDocument();
  });

  it("renders the legend with every evidence class", () => {
    renderGraphPage();
    const legend = screen.getByRole("group", { name: /link evidence legend/i });
    for (const cls of EVIDENCE_CLASSES) {
      expect(within(legend).getByText(evidenceClassLabel(cls))).toBeInTheDocument();
    }
    expect(within(legend).getByText(/arrowheads mark directional route/i)).toBeInTheDocument();
  });

  it("renders the safety banner", () => {
    renderGraphPage();
    const note = screen.getByRole("note", { name: /evidence safety note/i });
    expect(note).toHaveTextContent(GRAPH_SAFETY_COPY);
    expect(note).toHaveTextContent(/not proof of current live routing/i);
  });

  it("renders all fixture devices as nodes", async () => {
    await renderGraphAndWaitForLayout();
    for (const device of meshEvidenceGraphFixture.devices) {
      expect(screen.getByTestId(`mesh-node-${device.ieee_address}`)).toBeInTheDocument();
    }
  });

  it("renders edges with distinct semantic evidence classes", async () => {
    const { container } = await renderGraphAndWaitForLayout();
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--latest_snapshot_neighbor")).toHaveLength(5);
    });
    expect(container.querySelectorAll(".mesh-edge--latest_snapshot_route")).toHaveLength(2);
    expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(2);
    expect(container.querySelectorAll(".mesh-edge--historical_route")).toHaveLength(1);
    // Passive hints default to issue-related edges only (2 of 3 in fixture).
    expect(container.querySelectorAll(".mesh-edge--passive_derived_association")).toHaveLength(2);
    // Stale / low-confidence evidence is off by default.
    expect(container.querySelectorAll(".mesh-edge--stale_low_confidence")).toHaveLength(0);
  });

  it("uses arrowheads only for directional route evidence", async () => {
    const { container } = await renderGraphAndWaitForLayout();
    await waitFor(() => {
      expect(container.querySelector(".mesh-edge--latest_snapshot_route")).toBeInTheDocument();
    });
    const routeEdge = container.querySelector(".mesh-edge--latest_snapshot_route path");
    const neighborEdge = container.querySelector(".mesh-edge--latest_snapshot_neighbor path");
    const routeMarkers =
      (routeEdge?.getAttribute("marker-end") ?? "") + (routeEdge?.getAttribute("marker-start") ?? "");
    expect(routeMarkers).toContain("url(");
    expect(neighborEdge?.getAttribute("marker-end")).toBeNull();
    expect(neighborEdge?.getAttribute("marker-start")).toBeNull();
  });

  it("opens the edge drawer when an edge is clicked", async () => {
    await renderGraphAndWaitForLayout();
    const edge = await screen.findByLabelText(
      "Latest snapshot neighbour evidence between Coordinator and Living room plug",
    );
    fireEvent.click(edge);
    const drawer = screen.getByRole("dialog", { name: /link evidence/i });
    expect(within(drawer).getByText("Latest snapshot neighbour evidence")).toBeInTheDocument();
    expect(within(drawer).getByText(/high confidence/i)).toBeInTheDocument();
    expect(within(drawer).getByText(/present in the latest topology snapshot/i)).toBeInTheDocument();
  });

  it("opens the node drawer when a node is clicked", async () => {
    await renderGraphAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xr2hallrepeater0"));
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    expect(within(drawer).getByText("Hallway repeater")).toBeInTheDocument();
    expect(within(drawer).getByText("Router investigation candidate")).toBeInTheDocument();
    expect(
      within(drawer).getByText(/this is not proof of routing failure/i),
    ).toBeInTheDocument();
  });

  it("frames passive-derived edges as investigation hints, never as routes", async () => {
    await renderGraphAndWaitForLayout();
    const edge = await screen.findByLabelText(
      "Passive-derived association between Hallway repeater and Kitchen motion",
    );
    fireEvent.click(edge);
    const drawer = screen.getByRole("dialog", { name: /link evidence/i });
    expect(within(drawer).getByText("Investigation hint")).toBeInTheDocument();
    expect(within(drawer).getAllByText(/is not a route/i).length).toBeGreaterThan(0);
    expect(within(drawer).queryByText(/routes via/i)).not.toBeInTheDocument();
    expect(within(drawer).queryByText(/currently connected/i)).not.toBeInTheDocument();
    expect(within(drawer).queryByText(/parent router is/i)).not.toBeInTheDocument();
  });

  it("does not claim a current route for historical evidence", async () => {
    await renderGraphAndWaitForLayout();
    const edge = await screen.findByLabelText(
      "Historically observed link between Hallway repeater and Bedroom temp sensor",
    );
    fireEvent.click(edge);
    const drawer = screen.getByRole("dialog", { name: /link evidence/i });
    expect(
      within(drawer).getAllByText(/does not prove current live routing/i).length,
    ).toBeGreaterThan(0);
    expect(
      within(drawer).getByText(/absence is not evidence of failure/i),
    ).toBeInTheDocument();
    expect(within(drawer).queryByText(/currently connected/i)).not.toBeInTheDocument();
    expect(within(drawer).queryByText(/routes via/i)).not.toBeInTheDocument();
  });

  it("shows missing evidence as not recorded, never as zero", async () => {
    const user = userEvent.setup();
    await renderGraphAndWaitForLayout();
    await user.click(screen.getByRole("checkbox", { name: /stale \/ low-confidence evidence/i }));
    const edge = await screen.findByLabelText(
      "Stale / low-confidence evidence between Garage plug and Office button",
    );
    fireEvent.click(edge);
    const drawer = screen.getByRole("dialog", { name: /link evidence/i });
    expect(within(drawer).getByText("Route observed count").nextElementSibling).toHaveTextContent(
      "Not recorded",
    );
    expect(within(drawer).getByText("LQI median").nextElementSibling).toHaveTextContent("No data");
    expect(within(drawer).queryByText("0")).not.toBeInTheDocument();
  });

  it("keeps stale evidence hidden until the filter enables it", async () => {
    const user = userEvent.setup();
    const { container } = await renderGraphAndWaitForLayout();
    expect(container.querySelectorAll(".mesh-edge--stale_low_confidence")).toHaveLength(0);
    await user.click(screen.getByRole("checkbox", { name: /stale \/ low-confidence evidence/i }));
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--stale_low_confidence")).toHaveLength(1);
    });
  });

  it("expands passive hints from issue-related to all via the filter", async () => {
    const user = userEvent.setup();
    const { container } = await renderGraphAndWaitForLayout();
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--passive_derived_association")).toHaveLength(2);
    });
    await user.selectOptions(
      screen.getByRole("combobox", { name: /passive-derived hints/i }),
      "all",
    );
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--passive_derived_association")).toHaveLength(3);
    });
  });

  it("treats a sleepy end device with no latest snapshot link as not an incident", async () => {
    await renderGraphAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xe1bedroomtemp00"));
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    expect(
      within(drawer).getByText(/this is not an incident by itself/i),
    ).toBeInTheDocument();
    expect(
      within(drawer).getByText(/missing link in this graph is not, by itself, evidence/i),
    ).toBeInTheDocument();
  });
});
