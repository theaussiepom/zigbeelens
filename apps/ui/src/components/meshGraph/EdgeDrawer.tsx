import type { MeshEvidenceDevice, MeshEvidenceEdge } from "@/lib/meshEvidence";
import {
  evidenceClassDescription,
  evidenceClassLabel,
  evidenceClassShortLabel,
  formatEvidenceCount,
  formatLqi,
} from "@/lib/meshEvidence";
import {
  LINK_DETAILS_PANEL_LABEL,
  LINK_SECTION_CHECKS,
  LINK_SECTION_DOES_NOT_PROVE,
  LINK_SECTION_SUPPORTING,
  LINK_SECTION_WHAT_IT_MEANS,
  LINK_SECTION_WHY_DRAWN,
  SUGGESTED_INVESTIGATION_PANEL_LABEL,
  confidenceExplanation,
  linkDoesNotProveCopy,
  linkNeedsDoesNotProve,
  passiveRuleReason,
} from "@/lib/meshGraphCopy";
import { formatTime } from "@/lib/format";
import { DrawerFact, DrawerSection, DrawerShell } from "@/components/meshGraph/DrawerShell";

function formatPresence(value: boolean | null | undefined): string {
  if (value == null) return "Not recorded";
  return value ? "Yes" : "No";
}

function deviceName(devices: MeshEvidenceDevice[], ieee: string): string {
  return devices.find((d) => d.ieee_address === ieee)?.friendly_name ?? ieee;
}

function whyDrawnCopy(edge: MeshEvidenceEdge): string {
  switch (edge.evidence_class) {
    case "latest_snapshot_neighbor":
      return "ZigbeeLens drew this line because the latest topology snapshot reported a neighbour relationship between these devices.";
    case "latest_snapshot_route":
      return "ZigbeeLens drew this line because the latest topology snapshot included route-table / next-hop evidence between these devices.";
    case "historical_neighbor":
      return "ZigbeeLens drew this line because the link was observed in recent previous topology snapshots but is not present in the latest usable snapshot.";
    case "historical_route":
      return "ZigbeeLens drew this line because route-table evidence was observed in a recent previous topology snapshot and is not present in the latest usable snapshot.";
    case "last_known_link":
      return "ZigbeeLens drew this line because the device has no links in the latest snapshot, so the most recent stored link evidence is shown instead.";
    case "passive_derived_association":
      return "ZigbeeLens drew this line as a cautious investigation hint from passive observations, not from topology evidence.";
    case "stale_low_confidence":
      return "ZigbeeLens drew this line as older or weakly supported evidence that may help investigation.";
  }
}

/**
 * Link details panel for a passive-derived investigation hint.
 * Meaning and limits come first; raw fields stay secondary.
 */
function PassiveHintPanel({
  edge,
  devices,
  onClose,
}: {
  edge: MeshEvidenceEdge;
  devices: MeshEvidenceDevice[];
  onClose: () => void;
}) {
  const sourceName = deviceName(devices, edge.source);
  const targetName = deviceName(devices, edge.target);
  const checks = edge.suggested_investigation;

  return (
    <DrawerShell label={SUGGESTED_INVESTIGATION_PANEL_LABEL} onClose={onClose}>
      <div>
        <span className="inline-flex items-center rounded-full border border-zl-watch/30 bg-zl-watch/10 px-2.5 py-0.5 text-xs font-medium text-zl-watch">
          {evidenceClassShortLabel(edge.evidence_class)}
        </span>
        <p className="mt-2 text-base font-semibold text-zl-text">
          {sourceName} ↔ {targetName}
        </p>
        <p className="text-xs text-zl-muted">Network {edge.network_id} · no direction implied</p>
      </div>

      <DrawerSection title={LINK_SECTION_WHAT_IT_MEANS}>
        <p>
          ZigbeeLens found passive observations that may make these devices worth investigating
          together. This is a suggested investigation link, not topology evidence.
        </p>
      </DrawerSection>

      <DrawerSection title={LINK_SECTION_WHY_DRAWN}>
        {edge.rules_matched?.length ? (
          <ul className="list-disc space-y-1 pl-4">
            {edge.rules_matched.map((rule) => (
              <li key={rule}>{passiveRuleReason(rule)}</li>
            ))}
          </ul>
        ) : (
          <p>{whyDrawnCopy(edge)}</p>
        )}
      </DrawerSection>

      <DrawerSection title={LINK_SECTION_SUPPORTING}>
        {edge.supporting_observations?.length ? (
          <ul className="list-disc space-y-1 pl-4 text-zl-muted">
            {edge.supporting_observations.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        ) : null}
        <dl className="mt-2">
          <DrawerFact label="How strong this looks" value={confidenceExplanation(edge.confidence)} />
          <DrawerFact label="First observed" value={formatTime(edge.first_seen_at ?? undefined)} />
          <DrawerFact label="Last observed" value={formatTime(edge.last_seen_at ?? undefined)} />
          <DrawerFact
            label="Related instability windows"
            value={formatEvidenceCount(edge.observed_count)}
          />
        </dl>
      </DrawerSection>

      {linkNeedsDoesNotProve(edge) && (
        <DrawerSection title={LINK_SECTION_DOES_NOT_PROVE}>
          <ul className="list-disc space-y-1 pl-4 text-zl-muted">
            {linkDoesNotProveCopy(edge).map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </DrawerSection>
      )}

      {checks.length > 0 && (
        <DrawerSection title={LINK_SECTION_CHECKS}>
          <ul className="list-disc space-y-1 pl-4">
            {checks.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </DrawerSection>
      )}
    </DrawerShell>
  );
}

/**
 * Link details panel for one evidence line. Meaning first, raw fields later.
 */
export function EdgeDrawer({
  edge,
  devices,
  onClose,
}: {
  edge: MeshEvidenceEdge;
  devices: MeshEvidenceDevice[];
  onClose: () => void;
}) {
  if (edge.evidence_class === "passive_derived_association") {
    return <PassiveHintPanel edge={edge} devices={devices} onClose={onClose} />;
  }

  const sourceName = deviceName(devices, edge.source);
  const targetName = deviceName(devices, edge.target);
  const hasLqiStats = edge.lqi_min != null || edge.lqi_median != null || edge.lqi_max != null;
  const isRoute =
    edge.evidence_class === "latest_snapshot_route" || edge.evidence_class === "historical_route";
  const isHistorical =
    edge.evidence_class === "historical_neighbor" || edge.evidence_class === "historical_route";
  const checks = edge.suggested_investigation;

  return (
    <DrawerShell label={LINK_DETAILS_PANEL_LABEL} onClose={onClose}>
      <div>
        <span className="inline-flex items-center rounded-full border border-zl-accent/30 bg-zl-accent/10 px-2.5 py-0.5 text-xs font-medium text-zl-accent">
          {evidenceClassShortLabel(edge.evidence_class)}
        </span>
        <p className="mt-2 text-base font-semibold text-zl-text">
          {edge.directional ? `${sourceName} → ${targetName}` : `${sourceName} ↔ ${targetName}`}
        </p>
        <p className="text-xs text-zl-muted">
          Network {edge.network_id}
          {edge.directional ? " · directional evidence" : " · no direction implied"}
        </p>
      </div>

      <DrawerSection title={LINK_SECTION_WHAT_IT_MEANS}>
        <p className="font-medium">{evidenceClassLabel(edge.evidence_class)}</p>
        <p className="mt-1 text-zl-muted">{evidenceClassDescription(edge.evidence_class)}</p>
      </DrawerSection>

      <DrawerSection title={LINK_SECTION_WHY_DRAWN}>
        <p>{whyDrawnCopy(edge)}</p>
        <p className="mt-1 text-zl-muted">{confidenceExplanation(edge.confidence)}</p>
      </DrawerSection>

      <DrawerSection title={LINK_SECTION_SUPPORTING}>
        <dl>
          {edge.captured_at != null && (
            <DrawerFact label="Captured at" value={formatTime(edge.captured_at)} />
          )}
          <DrawerFact
            label="Observed relationship"
            value={edge.observed_relationship ?? "Not recorded"}
          />
          {edge.lqi_latest != null && (
            <DrawerFact label="Link quality (latest)" value={edge.lqi_latest} />
          )}
          {isHistorical && (
            <>
              <DrawerFact label="First observed" value={formatTime(edge.first_seen_at ?? undefined)} />
              <DrawerFact label="Last observed" value={formatTime(edge.last_seen_at ?? undefined)} />
              <DrawerFact label="Times observed" value={formatEvidenceCount(edge.observed_count)} />
              <DrawerFact
                label="Snapshots with this link"
                value={formatEvidenceCount(edge.snapshot_count)}
              />
            </>
          )}
          {hasLqiStats && (
            <>
              <DrawerFact label="Link quality min" value={formatLqi(edge.lqi_min)} />
              <DrawerFact label="Link quality median" value={formatLqi(edge.lqi_median)} />
              <DrawerFact label="Link quality max" value={formatLqi(edge.lqi_max)} />
            </>
          )}
          {isRoute && (
            <>
              <DrawerFact
                label="Route-table evidence"
                value={formatPresence(edge.route_table_evidence)}
              />
              <DrawerFact
                label="Next-hop evidence"
                value={formatPresence(edge.next_hop_evidence)}
              />
              <DrawerFact
                label="Route hints observed"
                value={formatEvidenceCount(edge.route_observed_count)}
              />
              {edge.evidence_class === "historical_route" && (
                <DrawerFact
                  label="Last route hint count"
                  value={formatEvidenceCount(edge.last_route_count)}
                />
              )}
            </>
          )}
        </dl>
      </DrawerSection>

      {linkNeedsDoesNotProve(edge) && (
        <DrawerSection title={LINK_SECTION_DOES_NOT_PROVE}>
          <ul className="list-disc space-y-1 pl-4 text-zl-muted">
            {linkDoesNotProveCopy(edge).map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </DrawerSection>
      )}

      {checks.length > 0 && (
        <DrawerSection title={LINK_SECTION_CHECKS}>
          <ul className="list-disc space-y-1 pl-4">
            {checks.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </DrawerSection>
      )}
    </DrawerShell>
  );
}
