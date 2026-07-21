import { describe, expect, it } from "vitest";
import { getDialogFocusable } from "./dialogFocusable";

describe("getDialogFocusable", () => {
  it("excludes disabled, hidden, inert, and aria-hidden controls", () => {
    const root = document.createElement("div");
    root.innerHTML = `
      <button type="button">Visible</button>
      <button type="button" disabled>Disabled</button>
      <button type="button" hidden>Hidden attr</button>
      <div aria-hidden="true"><button type="button">Aria hidden</button></div>
      <div inert><button type="button">Inert</button></div>
    `;
    const focusable = getDialogFocusable(root).map((el) => el.textContent?.trim());
    expect(focusable).toEqual(["Visible"]);
  });

  it("excludes closed details contents but keeps the summary", () => {
    const root = document.createElement("div");
    root.innerHTML = `
      <button type="button">Before</button>
      <details>
        <summary>Advanced</summary>
        <input type="checkbox" />
      </details>
      <button type="button">After</button>
    `;
    const labels = getDialogFocusable(root).map((el) =>
      el.tagName === "SUMMARY" ? "summary" : el.textContent?.trim(),
    );
    expect(labels).toEqual(["Before", "summary", "After"]);
  });

  it("includes open details checkboxes", () => {
    const root = document.createElement("div");
    root.innerHTML = `
      <details open>
        <summary>Advanced</summary>
        <input type="checkbox" />
      </details>
    `;
    const tags = getDialogFocusable(root).map((el) => el.tagName);
    expect(tags).toEqual(["SUMMARY", "INPUT"]);
  });
});
