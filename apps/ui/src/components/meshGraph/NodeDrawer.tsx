import type { MeshEvidenceDevice } from "@/lib/meshEvidence";
import {
  meshHealthBucketLabel,
  meshNodeFlagLabel,
  meshRoleLabel,
} from "@/lib/meshEvidence";
import { DrawerFact, DrawerSection, DrawerShell } from "@/components/meshGraph/DrawerShell";

function availabilityCopy(device: MeshEvidenceDevice): string {
  switch (device.availability) {
    case "online":
      return "Online";
    case "offline":
      return "Offline";
    default:
      return "No availability data";
  }
}

/** Device drawer: identity, health, and how to read the evidence safely. */
export function NodeDrawer({
  device,
  onClose,
}: {
  device: MeshEvidenceDevice;
  onClose: () => void;
}) {
  return (
    <DrawerShell label="Device details" onClose={onClose}>
      <div>
        <p className="text-base font-semibold text-zl-text">{device.friendly_name}</p>
        <p className="font-mono text-xs text-zl-muted">{device.ieee_address}</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {device.flags.map((flag) => (
            <span
              key={flag}
              className="rounded-full border border-zl-border bg-zl-surface-2 px-2 py-0.5 text-[11px] text-zl-muted"
            >
              {meshNodeFlagLabel(flag)}
            </span>
          ))}
        </div>
      </div>

      <DrawerSection title="Identity">
        <dl>
          <DrawerFact label="Network" value={device.network_id} />
          <DrawerFact label="Role" value={meshRoleLabel(device.role)} />
          <DrawerFact
            label="Power"
            value={
              device.power === "battery"
                ? "Battery"
                : device.power === "mains"
                  ? "Mains"
                  : "Unknown power"
            }
          />
          <DrawerFact label="Health bucket" value={meshHealthBucketLabel(device.health_bucket)} />
          <DrawerFact label="Availability" value={availabilityCopy(device)} />
          <DrawerFact label="Inventory status" value={device.inventory_status} />
        </dl>
      </DrawerSection>

      <DrawerSection title="Diagnostic stats">
        {device.diagnostic_stats.length === 0 ? (
          <p className="text-zl-muted">
            No recorded diagnostic stats for this device yet. Stats appear as topology
            snapshots and availability data accumulate.
          </p>
        ) : (
          <dl>
            {device.diagnostic_stats.map((stat) => (
              <div
                key={stat.label}
                className="flex items-baseline justify-between gap-3 py-0.5"
              >
                <dt className="text-xs text-zl-muted">{stat.label}</dt>
                <dd className="text-right text-sm text-zl-text">
                  {stat.value}
                  {stat.detail && (
                    <span className="block text-[11px] leading-tight text-zl-muted">
                      {stat.detail}
                    </span>
                  )}
                </dd>
              </div>
            ))}
          </dl>
        )}
        <p className="mt-2 text-xs text-zl-muted">
          Recorded values only — snapshot stats are point-in-time evidence, and a missing
          link is not, by itself, evidence that this device has failed.
        </p>
      </DrawerSection>

      <DrawerSection title="Topology evidence">
        <p>{device.topology_evidence_summary}</p>
      </DrawerSection>

      {device.historical_topology_summary != null && (
        <DrawerSection title="Recent missing topology evidence">
          <p>{device.historical_topology_summary}</p>
        </DrawerSection>
      )}

      {device.passive_hint_summary != null && (
        <DrawerSection title="Suggested investigation links">
          <p>{device.passive_hint_summary}</p>
        </DrawerSection>
      )}

      <DrawerSection title="Passive observations">
        <p>{device.passive_observation_summary}</p>
      </DrawerSection>

      {device.open_issue && (
        <DrawerSection title="Open issue">
          <p className="font-medium">{device.open_issue.title}</p>
          <p className="mt-1 text-zl-muted">{device.open_issue.summary}</p>
        </DrawerSection>
      )}
    </DrawerShell>
  );
}
