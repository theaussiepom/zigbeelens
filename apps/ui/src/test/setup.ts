import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// jsdom does not implement EventSource; provide a no-op stub so modules that
// open a live connection during render do not crash under test.
class StubEventSource {
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  addEventListener() {}
  removeEventListener() {}
  close() {}
}
// @ts-expect-error - assigning a minimal stub for jsdom
globalThis.EventSource = StubEventSource;

afterEach(() => cleanup());
