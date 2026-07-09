import type { MeshEvidenceDevice } from "@/lib/meshEvidence";
import {
  meshHealthBucketLabel,
  meshNodeFlagLabel,
  meshRoleLabel,
} from "@/lib/meshEvidence";
import {
  DEVICE_DETAILS_PANEL_LABEL,
  DEVICE_SECTION_OPEN_ISSUE,
  DEVICE_SECTION_PASSIVE_HINTS,
  DEVICE_SECTION_RECENT_MISSING,
  DEVICE_SECTION_STATS,
  DEVICE_SECTION_STATUS,
  DEVICE_SECTION_SUMMARY,
  DEVICE_SECTION_TOPOLOGY,
} from "@/lib/meshGraphCopy";
import { DrawerFact, DrawerSection, DrawerShell } from "@/components/meshGraph/DrawerShell";
import { SnapshotHistorySection } from "@/components/meshGraph/SnapshotHistorySection";

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

/** Device details panel: summary, status, and recorded evidence only. */
export function NodeDrawer({
  device,
  onClose,
}: {
  device: MeshEvidenceDevice;
  onClose: () => void;
}) {
  return (
    <DrawerShell label={DEVICE_DETAILS_PANEL_LABEL} onClose={onClose}>
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

      <DrawerSection title={DEVICE_SECTION_SUMMARY}>
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
          <DrawerFact label="Inventory status" value={device.inventory_status} />
        </dl>
      </DrawerSection>

      <DrawerSection title={DEVICE_SECTION_STATUS}>
        <dl>
          <DrawerFact label="ZigbeeLens status" value={meshHealthBucketLabel(device.health_bucket)} />
          <DrawerFact label="Availability" value={availabilityCopy(device)} />
        </dl>
        {device.passive_observation_summary ? (
          <p className="mt-2 text-zl-muted">{device.passive_observation_summary}</p>
        ) : null}
      </DrawerSection>

      {device.diagnostic_stats.length > 0 && (
        <DrawerSection title={DEVICE_SECTION_STATS}>
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
        </DrawerSection>
      )}

      <DrawerSection title={DEVICE_SECTION_TOPOLOGY}>
        <p>{device.topology_evidence_summary}</p>
      </DrawerSection>

      {device.historical_topology_summary != null && (
        <DrawerSection title={DEVICE_SECTION_RECENT_MISSING}>
          <p>{device.historical_topology_summary}</p>
        </DrawerSection>
      )}

      <SnapshotHistorySection
        networkId={device.network_id}
        deviceIeee={device.ieee_address}
      />

      {device.passive_hint_summary != null && (
        <DrawerSection title={DEVICE_SECTION_PASSIVE_HINTS}>
          <p>{device.passive_hint_summary}</p>
        </DrawerSection>
      )}

      {device.open_issue && (
        <DrawerSection title={DEVICE_SECTION_OPEN_ISSUE}>
          <p className="font-medium">{device.open_issue.title}</p>
          <p className="mt-1 text-zl-muted">{device.open_issue.summary}</p>
        </DrawerSection>
      )}
    </DrawerShell>
  );
}
