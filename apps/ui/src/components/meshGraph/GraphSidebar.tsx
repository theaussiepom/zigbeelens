import { useState } from "react";
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
  GRAPH_VIEW_DRAW_MORE_LINKS,
  GRAPH_VIEW_GROUP_LABEL,
  GRAPH_VIEW_PRESET_COPY,
  GRAPH_VIEW_PRESET_CUSTOM_LABEL,
} from "@/lib/meshGraphCopy";
import type { ConnectionControls } from "@/lib/meshGraphDense";
import {
  GRAPH_VIEW_PRESET_IDS,
  type GraphViewPresetId,
} from "@/lib/meshGraphPresets";
import type {
  ConnectionHistoryPresentationViewModel,
} from "@/viewModels/topology/connectionHistoryPresentationViewModel";

export function GraphSidebar({
  investigations,
  activeInvestigationId,
  onFocusInvestigation,
  onClearInvestigationFocus,
  canOpenPrimaryDevice,
  onOpenPrimaryDevice,
  hasPassiveHints,
  hasLastKnownLinks,
  hasRouteHints,
  hasOldUncertainLinks,
  hasRecentMissingLinks,
  historyPresentation,
  controls,
  activePreset,
  setControl,
  setPreset,
  resetConnectionChoices,
}: {
  investigations: InvestigationCard[];
  activeInvestigationId: string | null;
  onFocusInvestigation: (card: InvestigationCard) => void;
  onClearInvestigationFocus: () => void;
  canOpenPrimaryDevice?: (card: InvestigationCard) => boolean;
  onOpenPrimaryDevice?: (card: InvestigationCard) => void;
  hasPassiveHints: boolean;
  hasLastKnownLinks: boolean;
  hasRouteHints: boolean;
  hasOldUncertainLinks: boolean;
  hasRecentMissingLinks: boolean;
  historyPresentation: ConnectionHistoryPresentationViewModel;
  controls: ConnectionControls;
  activePreset: GraphViewPresetId;
  setControl: (key: keyof ConnectionControls) => (value: boolean) => void;
  setPreset: (preset: GraphViewPresetId) => void;
  resetConnectionChoices: () => void;
}) {
  const [drawMoreOpen, setDrawMoreOpen] = useState(false);
  const presetCopy =
    activePreset === "custom"
      ? GRAPH_VIEW_PRESET_COPY.custom
      : GRAPH_VIEW_PRESET_COPY[activePreset];

  return (
    <div className="space-y-4">
      <Card>
        <InvestigationPanel
          investigations={investigations}
          activeInvestigationId={activeInvestigationId}
          onFocus={onFocusInvestigation}
          onClearFocus={onClearInvestigationFocus}
          canOpenPrimaryDevice={canOpenPrimaryDevice}
          onOpenPrimaryDevice={onOpenPrimaryDevice}
        />
      </Card>
      <Card>
        <GraphLegend hasPassiveHints={hasPassiveHints} hasLastKnownLinks={hasLastKnownLinks} />
      </Card>
      <Card>
        <div role="group" aria-label={GRAPH_VIEW_GROUP_LABEL} className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-zl-muted">
            {GRAPH_VIEW_GROUP_LABEL}
          </h3>
          <label className="block space-y-1">
            <span className="text-[11px] font-medium text-zl-text">View preset</span>
            <select
              aria-label="Graph view preset"
              value={activePreset}
              onChange={(event) => setPreset(event.target.value as GraphViewPresetId)}
              className="w-full rounded-lg border border-zl-border bg-zl-surface px-2 py-1.5 text-sm text-zl-text"
            >
              {GRAPH_VIEW_PRESET_IDS.map((preset) => (
                <option key={preset} value={preset}>
                  {GRAPH_VIEW_PRESET_COPY[preset].label}
                </option>
              ))}
              {activePreset === "custom" ? (
                <option value="custom">{GRAPH_VIEW_PRESET_CUSTOM_LABEL}</option>
              ) : null}
            </select>
          </label>
          <p className="text-[11px] leading-snug text-zl-muted">{presetCopy.description}</p>

          <button
            type="button"
            aria-expanded={drawMoreOpen}
            onClick={() => setDrawMoreOpen((open) => !open)}
            className="text-[11px] font-medium text-zl-accent hover:underline"
          >
            {GRAPH_VIEW_DRAW_MORE_LINKS}
          </button>

          {drawMoreOpen ? (
            <div
              role="group"
              aria-label={CONNECTIONS_GROUP_LABEL}
              className="space-y-3 border-t border-zl-border pt-3"
            >
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
                helper={historyPresentation.recentMissingLinks.helper}
                checked={hasRecentMissingLinks && controls.recentMissingLinks}
                disabled={!hasRecentMissingLinks}
                onChange={setControl("recentMissingLinks")}
              />
              <ConnectionCheckbox
                label={CONNECTION_CONTROL_COPY.lastKnownLinks.label}
                helper={historyPresentation.lastKnownLinks.helper}
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
          ) : null}
        </div>
      </Card>
    </div>
  );
}
