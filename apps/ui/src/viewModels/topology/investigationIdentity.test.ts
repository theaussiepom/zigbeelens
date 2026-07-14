import { describe, expect, it } from "vitest";
import {
  buildInvestigationIdentityViewModel,
  investigationPriorityLabel,
  investigationPriorityTone,
} from "./investigationIdentity";

describe("investigationPriorityLabel", () => {
  it("preserves recognised priority labels", () => {
    expect(investigationPriorityLabel("Review first")).toBe("Review first");
    expect(investigationPriorityLabel("Worth checking")).toBe("Worth checking");
    expect(investigationPriorityLabel("Lower priority")).toBe("Lower priority");
  });

  it("hides unknown priority codes as Priority unknown with muted tone", () => {
    expect(investigationPriorityLabel("review_soon_v2")).toBe("Priority unknown");
    expect(investigationPriorityTone("review_soon_v2")).toBe("muted");
  });
});

describe("buildInvestigationIdentityViewModel", () => {
  it("does not expose unknown priority codes in user-facing identity", () => {
    const identity = buildInvestigationIdentityViewModel({
      priority: "review_soon_v2",
      actionGroup: "investigate_shared_event",
    });
    expect(identity.priorityLabel).toBe("Priority unknown");
    expect(identity.priorityTone).toBe("muted");
    expect(JSON.stringify(identity)).not.toContain("review_soon_v2");
  });
});
