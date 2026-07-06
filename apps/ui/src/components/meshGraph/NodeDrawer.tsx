import type { MeshEvidenceDevice } from "@/lib/meshEvidence";
import {
  meshHealthBucketLabel,
  meshNodeFlagLabel,
  meshRoleLabel,
} from "@/lib/meshEvidence";
import { formatTime } from "@/lib/format";
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
          <DrawerFact label="Last seen" value={formatTime(device.last_seen_at ?? undefined)} />
          <DrawerFact label="Inventory status" value={device.inventory_status} />
        </dl>
      </DrawerSection>

      <DrawerSection title="Topology evidence">
        <p>{device.topology_evidence_summary}</p>
      </DrawerSection>

      <DrawerSection title="Passive observations">
        <p>{device.passive_observation_summary}</p>
      </DrawerSection>

      {device.open_issue && (
        <DrawerSection title="Open issue">
          <p className="font-medium">{device.open_issue.title}</p>
          <p className="mt-1 text-zl-muted">{device.open_issue.summary}</p>
        </DrawerSection>
      )}

      <DrawerSection title="How ZigbeeLens reads this">
        <p className="rounded-lg border border-zl-border bg-zl-bg/50 p-3 leading-relaxed">
          {device.interpretation}
        </p>
        <p className="mt-2 text-xs text-zl-muted">
          Topology links are point-in-time evidence. A missing link in this graph is not, by
          itself, evidence that this device has failed.
        </p>
      </DrawerSection>
    </DrawerShell>
  );
}
