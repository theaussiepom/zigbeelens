import type { MeshEvidenceDevice, MeshEvidenceEdge } from "@/lib/meshEvidence";
import {
  confidenceLabel,
  evidenceClassDescription,
  evidenceClassLabel,
  evidenceClassShortLabel,
  formatEvidenceCount,
  formatLqi,
  latestSnapshotStatusCopy,
} from "@/lib/meshEvidence";
import { formatTime } from "@/lib/format";
import { DrawerFact, DrawerSection, DrawerShell } from "@/components/meshGraph/DrawerShell";

function formatPresence(value: boolean | null | undefined): string {
  if (value == null) return "Not recorded";
  return value ? "Yes" : "No";
}

function deviceName(devices: MeshEvidenceDevice[], ieee: string): string {
  return devices.find((d) => d.ieee_address === ieee)?.friendly_name ?? ieee;
}

/** Human wording for the backend passive-hint rule ids. */
function passiveRuleReason(rule: string): string {
  switch (rule) {
    case "shared_instability_window":
      return "These devices repeatedly showed instability around the same time.";
    case "topology_neighbourhood_corroboration":
      return "Recent topology evidence also places these devices in a related router neighbourhood.";
    case "current_issue_relevance":
      return "One or more of these devices currently needs attention, and recent passive observations show related instability timing.";
    default:
      return rule;
  }
}

/**
 * Drawer body for a passive-derived investigation hint. The structure keeps
 * the "what this means / why / limitations" framing front and centre: a
 * hint is only "worth investigating together", never topology evidence,
 * never a route, never proof of current connectivity.
 */
function PassiveHintDrawer({
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

  return (
    <DrawerShell label="Suggested investigation link" onClose={onClose}>
      <div>
        <span className="inline-flex items-center rounded-full border border-zl-watch/30 bg-zl-watch/10 px-2.5 py-0.5 text-xs font-medium text-zl-watch">
          {evidenceClassShortLabel(edge.evidence_class)}
        </span>
        <p className="mt-2 text-base font-semibold text-zl-text">
          {sourceName} ↔ {targetName}
        </p>
        <p className="text-xs text-zl-muted">
          Network {edge.network_id} · no direction implied
        </p>
      </div>

      <DrawerSection title="What this means">
        <p>
          ZigbeeLens found passive observations that may make these devices worth investigating
          together. This is a passive-derived hint, not topology evidence.
        </p>
      </DrawerSection>

      <DrawerSection title="Why ZigbeeLens suggested this">
        {edge.rules_matched?.length ? (
          <ul className="list-disc space-y-1 pl-4">
            {edge.rules_matched.map((rule) => (
              <li key={rule}>{passiveRuleReason(rule)}</li>
            ))}
          </ul>
        ) : (
          <p className="text-zl-muted">No rule details were recorded for this hint.</p>
        )}
      </DrawerSection>

      <DrawerSection title="Supporting observations">
        {edge.supporting_observations?.length ? (
          <ul className="list-disc space-y-1 pl-4 text-zl-muted">
            {edge.supporting_observations.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        ) : (
          <p className="text-zl-muted">No supporting observations were recorded.</p>
        )}
        <dl className="mt-2">
          <DrawerFact label="First observed" value={formatTime(edge.first_seen_at ?? undefined)} />
          <DrawerFact label="Last observed" value={formatTime(edge.last_seen_at ?? undefined)} />
          <DrawerFact
            label="Related instability windows"
            value={formatEvidenceCount(edge.observed_count)}
          />
        </dl>
      </DrawerSection>

      <DrawerSection title="Confidence">
        <p>
          {confidenceLabel(edge.confidence)} confidence — based on how often the passive pattern
          repeated and whether independent signals corroborated it, not on live measurements.
        </p>
      </DrawerSection>

      <DrawerSection title="Limitations">
        <ul className="list-disc space-y-1 pl-4 text-zl-muted">
          {edge.limitations.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      </DrawerSection>

      <DrawerSection title="Suggested investigation">
        {edge.suggested_investigation.length === 0 ? (
          <p className="text-zl-muted">No investigation suggested for this hint.</p>
        ) : (
          <ul className="list-disc space-y-1 pl-4">
            {edge.suggested_investigation.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        )}
      </DrawerSection>
    </DrawerShell>
  );
}

/**
 * Evidence drawer for one edge. Every section presents the edge as an
 * evidence claim: what was observed, when, with what confidence, and what
 * it does not prove.
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
  // Passive-derived hints get a dedicated drawer: their evidence story is
  // "worth investigating together", not snapshot/route/LQI facts.
  if (edge.evidence_class === "passive_derived_association") {
    return <PassiveHintDrawer edge={edge} devices={devices} onClose={onClose} />;
  }

  const sourceName = deviceName(devices, edge.source);
  const targetName = deviceName(devices, edge.target);
  const passive = edge.passive_corroboration;
  const hasLqiStats = edge.lqi_min != null || edge.lqi_median != null || edge.lqi_max != null;

  return (
    <DrawerShell label="Link evidence" onClose={onClose}>
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

      <DrawerSection title="Evidence class">
        <p className="font-medium">{evidenceClassLabel(edge.evidence_class)}</p>
        <p className="mt-1 text-zl-muted">{evidenceClassDescription(edge.evidence_class)}</p>
      </DrawerSection>

      <DrawerSection title="Confidence">
        <p>
          {confidenceLabel(edge.confidence)} confidence — based on how often and how recently this
          evidence was observed, not on live measurements.
        </p>
      </DrawerSection>

      <DrawerSection title="Latest snapshot status">
        <p>{latestSnapshotStatusCopy(edge)}</p>
        <dl className="mt-2">
          {edge.captured_at != null && (
            <DrawerFact label="Captured at" value={formatTime(edge.captured_at)} />
          )}
          <DrawerFact
            label="Observed relationship"
            value={edge.observed_relationship ?? "Not recorded"}
          />
          {edge.lqi_latest != null && <DrawerFact label="LQI latest" value={edge.lqi_latest} />}
        </dl>
      </DrawerSection>

      <DrawerSection title="Historical evidence">
        <dl>
          <DrawerFact label="First observed" value={formatTime(edge.first_seen_at ?? undefined)} />
          <DrawerFact label="Last observed" value={formatTime(edge.last_seen_at ?? undefined)} />
          <DrawerFact label="Observed count" value={formatEvidenceCount(edge.observed_count)} />
          <DrawerFact label="Snapshot count" value={formatEvidenceCount(edge.snapshot_count)} />
          {hasLqiStats ? (
            <>
              <DrawerFact label="LQI min" value={formatLqi(edge.lqi_min)} />
              <DrawerFact label="LQI median" value={formatLqi(edge.lqi_median)} />
              <DrawerFact label="LQI max" value={formatLqi(edge.lqi_max)} />
            </>
          ) : edge.lqi_latest != null ? (
            <p className="mt-1 text-xs text-zl-muted">
              Historical LQI statistics are not available; only the latest snapshot LQI is shown
              above.
            </p>
          ) : (
            <p className="mt-1 text-xs text-zl-muted">
              No LQI data was recorded for this link. Missing LQI means less evidence, not a weak
              or failed link.
            </p>
          )}
        </dl>
      </DrawerSection>

      <DrawerSection title="Route evidence">
        <dl>
          <DrawerFact
            label="Route-table evidence"
            value={formatPresence(edge.route_table_evidence)}
          />
          <DrawerFact label="Next-hop evidence" value={formatPresence(edge.next_hop_evidence)} />
          <DrawerFact
            label="Route observed count"
            value={formatEvidenceCount(edge.route_observed_count)}
          />
          {edge.evidence_class === "historical_route" && (
            <DrawerFact
              label="Last route count"
              value={formatEvidenceCount(edge.last_route_count)}
            />
          )}
        </dl>
        {edge.evidence_class === "historical_route" && (
          <p className="mt-1 text-xs text-zl-muted">
            Route-table evidence was observed in a recent previous topology snapshot. This does
            not prove current live routing.
          </p>
        )}
        {!edge.route_table_evidence && (
          <p className="mt-1 text-xs text-zl-muted">
            Absence of route-table evidence does not mean this link is unused; it only means no
            route entry was observed.
          </p>
        )}
      </DrawerSection>

      <DrawerSection title="Passive evidence">
        {passive ? (
          <dl>
            <DrawerFact
              label="Correlated availability flaps"
              value={formatEvidenceCount(passive.correlated_availability_flaps)}
            />
            <DrawerFact
              label="Reporting cadence"
              value={passive.reporting_cadence ?? "Not recorded"}
            />
            <DrawerFact
              label="Stale-window overlap"
              value={passive.stale_window_overlap ?? "None observed"}
            />
            <DrawerFact label="Same-area hint" value={passive.same_area_hint ?? "None observed"} />
            <DrawerFact
              label="Nearby affected devices"
              value={
                passive.nearby_affected_devices?.length
                  ? passive.nearby_affected_devices.join(", ")
                  : "None recorded"
              }
            />
          </dl>
        ) : (
          <p className="text-zl-muted">No passive corroboration recorded for this link.</p>
        )}
      </DrawerSection>

      <DrawerSection title="Limitations">
        {edge.limitations.length === 0 ? (
          <p className="text-zl-muted">No specific limitations noted for this evidence.</p>
        ) : (
          <ul className="list-disc space-y-1 pl-4 text-zl-muted">
            {edge.limitations.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        )}
      </DrawerSection>

      <DrawerSection title="Suggested investigation">
        {edge.suggested_investigation.length === 0 ? (
          <p className="text-zl-muted">No investigation suggested for this link.</p>
        ) : (
          <ul className="list-disc space-y-1 pl-4">
            {edge.suggested_investigation.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        )}
      </DrawerSection>
    </DrawerShell>
  );
}
