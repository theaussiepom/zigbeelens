import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { Card } from "@/components/ui";
import { GraphLegend } from "@/components/meshGraph/GraphLegend";
import { MeshEvidenceGraph } from "@/components/meshGraph/MeshEvidenceGraph";
import { EdgeDrawer } from "@/components/meshGraph/EdgeDrawer";
import { NodeDrawer } from "@/components/meshGraph/NodeDrawer";
import { TopologyViewTabs } from "@/components/meshGraph/TopologyViewTabs";
import { meshEvidenceGraphFixture } from "@/fixtures/meshEvidenceGraph";
import {
  GRAPH_SAFETY_COPY,
  type MeshEvidenceDevice,
  type MeshEvidenceEdge,
} from "@/lib/meshEvidence";

type PassiveFilterMode = "issue_related" | "all" | "off";

interface EvidenceFilters {
  latestSnapshot: boolean;
  route: boolean;
  historical: boolean;
  passive: PassiveFilterMode;
  staleLowConfidence: boolean;
}

const DEFAULT_FILTERS: EvidenceFilters = {
  latestSnapshot: true,
  route: true,
  historical: true,
  // Passive-derived hints default to issue-related edges only.
  passive: "issue_related",
  // Stale / low-confidence evidence is off by default.
  staleLowConfidence: false,
};

function edgeVisible(edge: MeshEvidenceEdge, filters: EvidenceFilters): boolean {
  switch (edge.evidence_class) {
    case "latest_snapshot_neighbor":
      return filters.latestSnapshot;
    case "latest_snapshot_route":
      return filters.route;
    case "historical_neighbor":
    case "historical_route":
      return filters.historical;
    case "passive_derived_association":
      if (filters.passive === "off") return false;
      if (filters.passive === "all") return true;
      return Boolean(edge.issue_related);
    case "stale_low_confidence":
      return filters.staleLowConfidence;
  }
}

function FilterCheckbox({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex min-h-0 cursor-pointer items-center gap-2 text-sm text-zl-text">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 accent-[#5b9fd4]"
      />
      {label}
    </label>
  );
}

export function TopologyGraphPage() {
  const { networkId } = useParams<{ networkId?: string }>();
  const fixture = meshEvidenceGraphFixture;
  const [filters, setFilters] = useState<EvidenceFilters>(DEFAULT_FILTERS);
  const [selectedEdge, setSelectedEdge] = useState<MeshEvidenceEdge | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<MeshEvidenceDevice | null>(null);

  const visibleEdges = useMemo(
    () => fixture.edges.filter((edge) => edgeVisible(edge, filters)),
    [fixture.edges, filters],
  );

  return (
    <div className="max-w-7xl space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Mesh evidence graph</h1>
          <p className="mt-1 text-zl-muted">
            Relationship evidence gathered over time — snapshots, history and passive observations
            — for network <span className="font-mono">{networkId ?? fixture.network_id}</span>.
          </p>
        </div>
        <span className="inline-flex items-center rounded-full border border-zl-watch/40 bg-zl-watch/10 px-3 py-1 text-xs font-medium text-zl-watch">
          Prototype — sample data
        </span>
      </header>

      <TopologyViewTabs networkId={networkId ?? fixture.network_id} />

      <div
        role="note"
        aria-label="Evidence safety note"
        className="rounded-lg border border-zl-accent/40 bg-zl-accent/10 px-4 py-3 text-sm leading-relaxed text-zl-text"
      >
        {GRAPH_SAFETY_COPY}
      </div>

      <p className="text-xs text-zl-muted">
        This prototype renders fixture data to prove the evidence grammar and drawer model. It is
        not reading your live network yet.
      </p>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <Card className="!p-2">
          <div className="h-[600px]" data-testid="mesh-evidence-graph">
            <MeshEvidenceGraph
              devices={fixture.devices}
              visibleEdges={visibleEdges}
              allEdges={fixture.edges}
              selectedNodeId={selectedDevice?.ieee_address ?? null}
              onSelectEdge={(edge) => {
                setSelectedDevice(null);
                setSelectedEdge(edge);
              }}
              onSelectNode={(device) => {
                setSelectedEdge(null);
                setSelectedDevice(device);
              }}
            />
          </div>
        </Card>

        <div className="space-y-4">
          <Card>
            <GraphLegend />
          </Card>
          <Card>
            <div role="group" aria-label="Evidence filters" className="space-y-2.5">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-zl-muted">
                Show evidence
              </h3>
              <FilterCheckbox
                label="Latest snapshot evidence"
                checked={filters.latestSnapshot}
                onChange={(v) => setFilters((f) => ({ ...f, latestSnapshot: v }))}
              />
              <FilterCheckbox
                label="Route evidence"
                checked={filters.route}
                onChange={(v) => setFilters((f) => ({ ...f, route: v }))}
              />
              <FilterCheckbox
                label="Historical evidence"
                checked={filters.historical}
                onChange={(v) => setFilters((f) => ({ ...f, historical: v }))}
              />
              <label className="block text-sm text-zl-text">
                <span className="mb-1 block">Passive-derived hints</span>
                <select
                  value={filters.passive}
                  onChange={(e) =>
                    setFilters((f) => ({ ...f, passive: e.target.value as PassiveFilterMode }))
                  }
                  className="w-full rounded-lg border border-zl-border bg-zl-surface-2 px-2 py-1.5 text-sm"
                >
                  <option value="issue_related">Issue-related only (default)</option>
                  <option value="all">All passive hints</option>
                  <option value="off">Hidden</option>
                </select>
              </label>
              <FilterCheckbox
                label="Stale / low-confidence evidence"
                checked={filters.staleLowConfidence}
                onChange={(v) => setFilters((f) => ({ ...f, staleLowConfidence: v }))}
              />
              <p className="text-[11px] leading-snug text-zl-muted">
                Hiding an evidence class only hides claims — it never means the relationship is
                gone.
              </p>
            </div>
          </Card>
        </div>
      </div>

      {selectedEdge && (
        <EdgeDrawer
          edge={selectedEdge}
          devices={fixture.devices}
          onClose={() => setSelectedEdge(null)}
        />
      )}
      {selectedDevice && (
        <NodeDrawer device={selectedDevice} onClose={() => setSelectedDevice(null)} />
      )}
    </div>
  );
}
