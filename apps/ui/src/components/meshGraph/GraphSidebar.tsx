import { Card } from "@/components/ui";
import { ConnectionCheckbox } from "@/components/meshGraph/ConnectionCheckbox";
import { ConnectionsExplainer } from "@/components/meshGraph/ConnectionsExplainer";
import { GraphLegend } from "@/components/meshGraph/GraphLegend";
import { InvestigationPanel } from "@/components/meshGraph/InvestigationPanel";
import type { InvestigationCard } from "@/lib/api";
import {
  CONNECTION_CONTROL_COPY,
  CONNECTIONS_FOOTNOTE,
  CONNECTIONS_GROUP_LABEL,
} from "@/lib/meshGraphCopy";
import type { ConnectionControls } from "@/lib/meshGraphDense";

export function GraphSidebar({
  investigations,
  activeInvestigationId,
  onFocusInvestigation,
  onClearInvestigationFocus,
  hasPassiveHints,
  hasLastKnownLinks,
  hasRouteHints,
  hasOldUncertainLinks,
  hasRecentMissingLinks,
  controls,
  setControl,
  resetConnectionChoices,
}: {
  investigations: InvestigationCard[];
  activeInvestigationId: string | null;
  onFocusInvestigation: (card: InvestigationCard) => void;
  onClearInvestigationFocus: () => void;
  hasPassiveHints: boolean;
  hasLastKnownLinks: boolean;
  hasRouteHints: boolean;
  hasOldUncertainLinks: boolean;
  hasRecentMissingLinks: boolean;
  controls: ConnectionControls;
  setControl: (key: keyof ConnectionControls) => (value: boolean) => void;
  resetConnectionChoices: () => void;
}) {
  return (
    <div className="space-y-4">
      <Card>
        <InvestigationPanel
          investigations={investigations}
          activeInvestigationId={activeInvestigationId}
          onFocus={onFocusInvestigation}
          onClearFocus={onClearInvestigationFocus}
        />
      </Card>
      <Card>
        <GraphLegend hasPassiveHints={hasPassiveHints} hasLastKnownLinks={hasLastKnownLinks} />
      </Card>
      <Card>
        <div role="group" aria-label={CONNECTIONS_GROUP_LABEL} className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-zl-muted">
            {CONNECTIONS_GROUP_LABEL}
          </h3>
          <ConnectionsExplainer />
          <ConnectionCheckbox
            label={CONNECTION_CONTROL_COPY.routeHints.label}
            helper={hasRouteHints ? undefined : CONNECTION_CONTROL_COPY.routeHints.empty}
            checked={hasRouteHints && controls.routeHints}
            disabled={!hasRouteHints}
            onChange={setControl("routeHints")}
          />
          <ConnectionCheckbox
            label={CONNECTION_CONTROL_COPY.bestNeighbourLinks.label}
            checked={controls.bestNeighbourLinks}
            onChange={setControl("bestNeighbourLinks")}
          />
          <ConnectionCheckbox
            label={CONNECTION_CONTROL_COPY.allNeighbourLinks.label}
            checked={controls.allNeighbourLinks}
            onChange={setControl("allNeighbourLinks")}
          />
          <ConnectionCheckbox
            label={CONNECTION_CONTROL_COPY.oldUncertainLinks.label}
            helper={
              hasOldUncertainLinks ? undefined : CONNECTION_CONTROL_COPY.oldUncertainLinks.empty
            }
            checked={hasOldUncertainLinks && controls.oldUncertainLinks}
            disabled={!hasOldUncertainLinks}
            onChange={setControl("oldUncertainLinks")}
          />
          <ConnectionCheckbox
            label={CONNECTION_CONTROL_COPY.recentMissingLinks.label}
            helper={
              hasRecentMissingLinks ? undefined : CONNECTION_CONTROL_COPY.recentMissingLinks.empty
            }
            checked={hasRecentMissingLinks && controls.recentMissingLinks}
            disabled={!hasRecentMissingLinks}
            onChange={setControl("recentMissingLinks")}
          />
          <ConnectionCheckbox
            label={CONNECTION_CONTROL_COPY.lastKnownLinks.label}
            helper={hasLastKnownLinks ? undefined : CONNECTION_CONTROL_COPY.lastKnownLinks.empty}
            checked={hasLastKnownLinks && controls.lastKnownLinks}
            disabled={!hasLastKnownLinks}
            onChange={setControl("lastKnownLinks")}
          />
          <ConnectionCheckbox
            label={CONNECTION_CONTROL_COPY.suggestedInvestigationLinks.label}
            helper={
              hasPassiveHints
                ? undefined
                : CONNECTION_CONTROL_COPY.suggestedInvestigationLinks.empty
            }
            checked={hasPassiveHints && controls.suggestedInvestigationLinks}
            disabled={!hasPassiveHints}
            onChange={setControl("suggestedInvestigationLinks")}
          />
          <p className="text-[11px] leading-snug text-zl-muted">{CONNECTIONS_FOOTNOTE}</p>
          <button
            type="button"
            onClick={resetConnectionChoices}
            className="text-[11px] text-zl-accent hover:underline"
          >
            Reset connection choices
          </button>
        </div>
      </Card>
    </div>
  );
}
