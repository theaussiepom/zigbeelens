import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConfidenceBadge, CounterEvidenceList, LimitationsList, SeverityBadge } from "./ui";

describe("badges", () => {
  it("renders calm severity labels", () => {
    render(<SeverityBadge severity="healthy" />);
    expect(screen.getByText("OK")).toBeInTheDocument();
  });

  it("renders incident severity label", () => {
    render(<SeverityBadge severity="incident" />);
    expect(screen.getByText("Incident")).toBeInTheDocument();
  });

  it("renders confidence with text, not colour alone", () => {
    render(<ConfidenceBadge confidence="low" />);
    expect(screen.getByText("Low confidence")).toBeInTheDocument();
  });
});

describe("evidence lists", () => {
  it("shows a calm empty state for counter-evidence", () => {
    render(<CounterEvidenceList items={[]} />);
    expect(screen.getByText("No counter-evidence has been recorded.")).toBeInTheDocument();
  });

  it("renders limitation items", () => {
    render(
      <LimitationsList
        items={["ZigbeeLens cannot prove physical route without topology data"]}
      />,
    );
    expect(
      screen.getByText("ZigbeeLens cannot prove physical route without topology data"),
    ).toBeInTheDocument();
  });
});
