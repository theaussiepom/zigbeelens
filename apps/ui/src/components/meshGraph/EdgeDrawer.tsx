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
          <DrawerFact label="First seen" value={formatTime(edge.first_seen_at ?? undefined)} />
          <DrawerFact label="Last seen" value={formatTime(edge.last_seen_at ?? undefined)} />
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
        </dl>
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
        {edge.evidence_class === "passive_derived_association" && (
          <p className="mt-2 rounded-lg border border-zl-watch/30 bg-zl-watch/10 p-2 text-xs text-zl-watch">
            This is an investigation hint derived from passive observations. It is not a route and
            does not prove current live routing.
          </p>
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
