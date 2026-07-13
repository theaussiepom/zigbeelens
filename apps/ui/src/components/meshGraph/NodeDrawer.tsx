import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { DrawerFact, DrawerSection, DrawerShell } from "@/components/meshGraph/DrawerShell";
import { DeviceStorySection } from "@/components/meshGraph/DeviceStorySection";
import { EvidenceCoverageStrip } from "@/components/meshGraph/EvidenceCoverageStrip";
import { SnapshotHistorySection } from "@/components/meshGraph/SnapshotHistorySection";
import type { DataCoverageDto } from "@/types/decisions";
import type { MeshEvidenceDevice } from "@/lib/meshEvidence";
import {
  buildDeviceDetailsViewModel,
  type DeviceDetailsSectionViewModel,
} from "@/viewModels/topology/deviceDetailsViewModel";

function DeviceDetailsSection({ section }: { section: DeviceDetailsSectionViewModel }) {
  switch (section.id) {
    case "summary":
    case "currentStatus":
      return (
        <DrawerSection title={section.title}>
          <dl>
            {section.facts.map((fact) => (
              <DrawerFact key={fact.label} label={fact.label} value={fact.value} />
            ))}
          </dl>
          {section.id === "currentStatus" && section.passiveObservationSummary ? (
            <p className="mt-2 text-zl-muted">{section.passiveObservationSummary}</p>
          ) : null}
        </DrawerSection>
      );
    case "diagnosticStats":
      return (
        <DrawerSection title={section.title}>
          <dl>
            {section.stats.map((stat) => (
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
      );
    case "topologyEvidence":
    case "recentMissing":
    case "passiveHints":
      return (
        <DrawerSection title={section.title}>
          <p>{section.body}</p>
        </DrawerSection>
      );
    case "deviceStory":
      return (
        <DeviceStorySection
          networkId={section.networkId}
          deviceIeee={section.deviceIeee}
        />
      );
    case "snapshotHistory":
      return (
        <SnapshotHistorySection
          networkId={section.networkId}
          deviceIeee={section.deviceIeee}
        />
      );
    case "dataCoverage":
      return (
        <DrawerSection title={section.title}>
          <EvidenceCoverageStrip items={section.items} />
        </DrawerSection>
      );
    case "openIssue":
      return (
        <DrawerSection title={section.title}>
          <p className="font-medium">{section.issueTitle}</p>
          <p className="mt-1 text-zl-muted">{section.issueSummary}</p>
        </DrawerSection>
      );
    default:
      return null;
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
  const [deviceCoverage, setDeviceCoverage] = useState<DataCoverageDto[]>([]);

  useEffect(() => {
    let cancelled = false;
    setDeviceCoverage([]);
    api.deviceCoverage(device.network_id, device.ieee_address).then(
      (data) => {
        if (!cancelled) setDeviceCoverage(data);
      },
      () => {
        if (!cancelled) setDeviceCoverage([]);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [device.network_id, device.ieee_address]);

  const viewModel = useMemo(
    () => buildDeviceDetailsViewModel(device, deviceCoverage),
    [device, deviceCoverage],
  );

  return (
    <DrawerShell label={viewModel.panelLabel} onClose={onClose}>
      <div>
        <p className="text-base font-semibold text-zl-text">{viewModel.header.friendlyName}</p>
        <p className="font-mono text-xs text-zl-muted">{viewModel.header.ieeeAddress}</p>
        {viewModel.header.flagLabels.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {viewModel.header.flagLabels.map((label) => (
              <span
                key={label}
                className="rounded-full border border-zl-border bg-zl-surface-2 px-2 py-0.5 text-[11px] text-zl-muted"
              >
                {label}
              </span>
            ))}
          </div>
        )}
      </div>
      {viewModel.sections.map((section) => (
        <DeviceDetailsSection key={section.id} section={section} />
      ))}
    </DrawerShell>
  );
}
