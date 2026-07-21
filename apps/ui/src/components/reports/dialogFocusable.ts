/**
 * Visible keyboard-focusable controls for the contextual report dialog trap.
 * JSDOM-safe: does not rely on offsetParent / layout.
 */
export function getDialogFocusable(container: HTMLElement): HTMLElement[] {
  const nodes = container.querySelectorAll<HTMLElement>(
    'button, [href], input, select, textarea, summary, [tabindex]:not([tabindex="-1"])',
  );
  return Array.from(nodes).filter((el) => isDialogFocusable(el));
}

export function isDialogFocusable(el: HTMLElement): boolean {
  if (el.matches(":disabled") || el.hasAttribute("disabled")) return false;
  if (el.getAttribute("tabindex") === "-1") return false;
  if (el.hasAttribute("hidden") || el.getAttribute("aria-hidden") === "true") return false;
  if (el.closest("[inert]")) return false;

  const ariaHiddenAncestor = el.closest('[aria-hidden="true"]');
  if (ariaHiddenAncestor) return false;

  const hiddenAncestor = el.closest("[hidden]");
  if (hiddenAncestor) return false;

  const closedDetails = el.closest("details:not([open])");
  if (closedDetails) {
    const summary = closedDetails.querySelector(":scope > summary");
    if (el !== summary) return false;
  }

  return true;
}
