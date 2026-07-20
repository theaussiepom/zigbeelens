import { describe, expect, it } from "vitest";
import type { SharedAvailabilityEventSummary } from "@zigbeelens/shared";
import {
  SHARED_AVAILABILITY_EVENT_LIMITATION,
  SHARED_AVAILABILITY_EVENT_TITLE,
  buildSharedAvailabilityEventViewModel,
} from "@/viewModels/overview/sharedAvailabilityEventViewModel";

const FORBIDDEN_AFFIRMATIVE_PHRASES = [
  "common cause",
  "caused by",
  "network failure",
  "coordinator failure",
  "mqtt outage",
  "broker outage",
  "power outage",
  "interference event",
  "shared route",
  "shared path",
  "parent router",
];

function makeEvent(
  overrides: Partial<SharedAvailabilityEventSummary> = {},
): SharedAvailabilityEventSummary {
  return {
    event_id: "shared-availability-test",
    network_id: "home",
    started_at: "2026-07-06T08:00:00+00:00",
    ended_at: "2026-07-06T08:22:00+00:00",
    device_count: 11,
    duration_minutes: 22,
    device_ieees: ["0xd00", "0xd01"],
    ...overrides,
  };
}

function claimText(vm: ReturnType<typeof buildSharedAvailabilityEventViewModel>): string {
  return JSON.stringify({
    title: vm.title,
    summary: vm.summary,
    timingLabel: vm.timingLabel,
    deviceCountLabel: vm.deviceCountLabel,
    suggestedChecks: vm.suggestedChecks,
    meshLinkLabel: vm.meshLinkLabel,
  }).toLowerCase();
}

describe("sharedAvailabilityEventViewModel", () => {
  it("renders duration copy for events lasting at least one minute", () => {
    const vm = buildSharedAvailabilityEventViewModel(makeEvent(), "Home");
    expect(vm.title).toBe(SHARED_AVAILABILITY_EVENT_TITLE);
    expect(vm.summary).toBe(
      "11 devices went offline during a shared availability event lasting about 22 minutes.",
    );
    expect(vm.summary).not.toContain("within 5 minutes");
  });

  it("uses singular minute wording for exactly one minute", () => {
    const vm = buildSharedAvailabilityEventViewModel(
      makeEvent({ duration_minutes: 1, device_count: 3 }),
      "Home",
    );
    expect(vm.summary).toBe(
      "3 devices went offline during a shared availability event lasting about 1 minute.",
    );
  });

  it("uses natural wording for sub-minute events", () => {
    const vm = buildSharedAvailabilityEventViewModel(
      makeEvent({
        duration_minutes: 0,
        started_at: "2026-07-06T08:00:00+00:00",
        ended_at: "2026-07-06T08:00:00+00:00",
        device_count: 11,
      }),
      "Home",
    );
    expect(vm.summary).toBe("11 devices went offline around the same time.");
    expect(vm.summary).not.toContain("0 minutes");
  });

  it("includes the explicit shared-event limitation", () => {
    const vm = buildSharedAvailabilityEventViewModel(makeEvent(), "Home");
    expect(vm.limitation).toBe(SHARED_AVAILABILITY_EVENT_LIMITATION);
    expect(vm.limitation).toMatch(/does not prove/i);
    expect(vm.limitation).toMatch(/route, path, parent, or root cause/i);
  });

  it("frames suggested checks as checks rather than causes", () => {
    const vm = buildSharedAvailabilityEventViewModel(makeEvent(), "Home");
    expect(vm.suggestedChecks.length).toBeGreaterThan(0);
    for (const check of vm.suggestedChecks) {
      expect(check.toLowerCase()).toMatch(/^check |^compare /);
      expect(check.toLowerCase()).not.toMatch(/caused|outage caused|because/);
    }
  });

  it("links to the event network mesh page", () => {
    const vm = buildSharedAvailabilityEventViewModel(
      makeEvent({ network_id: "office" }),
      "Office",
    );
    expect(vm.meshHref).toBe("/investigate/office");
    expect(vm.networkLabel).toBe("Office");
  });

  it("avoids affirmative causal wording in user-facing copy", () => {
    const vm = buildSharedAvailabilityEventViewModel(makeEvent(), "Home");
    const text = claimText(vm);
    for (const phrase of FORBIDDEN_AFFIRMATIVE_PHRASES) {
      expect(text).not.toContain(phrase);
    }
    expect(JSON.stringify(vm)).not.toContain("undefined");
    expect(JSON.stringify(vm)).not.toContain("shared_availability_event");
  });
});
