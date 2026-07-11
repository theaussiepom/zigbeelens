import { useState } from "react";
import {
  CONNECTION_CONTROL_COPY,
  CONNECTIONS_EXPLAINER,
  CONNECTIONS_EXPLAINER_TOGGLE,
} from "@/lib/meshGraphCopy";

/** Plain-language explainer for connection evidence types. */
export function ConnectionsExplainer() {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="text-[11px] text-zl-accent hover:underline"
        data-testid="connections-explainer-toggle"
      >
        {CONNECTIONS_EXPLAINER_TOGGLE}
      </button>
      {open && (
        <div
          className="mt-2 space-y-2 rounded-lg border border-zl-border bg-zl-surface-2 p-2 text-[11px] leading-snug text-zl-muted"
          data-testid="connections-explainer"
        >
          <p>
            <span className="font-semibold text-zl-text">
              {CONNECTION_CONTROL_COPY.bestNeighbourLinks.label}
            </span>{" "}
            {CONNECTIONS_EXPLAINER.bestNeighbourLinks.replace(
              /^Best neighbour links come from /,
              "come from ",
            )}
          </p>
          <p>
            <span className="font-semibold text-zl-text">
              {CONNECTION_CONTROL_COPY.routeHints.label}
            </span>{" "}
            {CONNECTIONS_EXPLAINER.routeHints.replace(/^Route hints come from /, "come from ")}
          </p>
          <p>{CONNECTIONS_EXPLAINER.summary}</p>
          <p>
            <span className="font-semibold text-zl-text">
              {CONNECTION_CONTROL_COPY.recentMissingLinks.label}
            </span>{" "}
            {CONNECTIONS_EXPLAINER.recentMissingLinks.replace(/^Recent missing links /, "")}
          </p>
          <p>
            <span className="font-semibold text-zl-text">
              {CONNECTION_CONTROL_COPY.lastKnownLinks.label}
            </span>{" "}
            {CONNECTIONS_EXPLAINER.lastKnownLinks.replace(/^Last known links /, "")}
          </p>
          <p>{CONNECTIONS_EXPLAINER.allNeighbourLinks}</p>
          <p>
            <span className="font-semibold text-zl-text">
              {CONNECTION_CONTROL_COPY.suggestedInvestigationLinks.label}
            </span>{" "}
            {CONNECTIONS_EXPLAINER.suggestedInvestigationLinks.replace(
              /^Suggested investigation links /,
              "",
            )}
          </p>
        </div>
      )}
    </div>
  );
}
