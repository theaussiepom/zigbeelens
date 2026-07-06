import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import { api } from "@/lib/api";
import { Badge, Card, ErrorState, LoadingState, MetricPill } from "@/components/ui";
import { GraphLegend } from "@/components/meshGraph/GraphLegend";
import { MeshEvidenceGraph } from "@/components/meshGraph/MeshEvidenceGraph";
import { EdgeDrawer } from "@/components/meshGraph/EdgeDrawer";
import { NodeDrawer } from "@/components/meshGraph/NodeDrawer";
import { TopologyViewTabs } from "@/components/meshGraph/TopologyViewTabs";
import { meshEvidenceGraphFixture } from "@/fixtures/meshEvidenceGraph";
import { buildLiveMeshEvidence } from "@/lib/meshEvidenceLive";
import { relativeTime } from "@/lib/format";
import { topologyStatusLabel } from "@/lib/topologyLabels";
import {
  GRAPH_SAFETY_COPY,
  type MeshEvidenceDevice,
  type MeshEvidenceEdge,
} from "@/lib/meshEvidence";
import { buildStructuralLayoutEdges } from "@/lib/meshGraphLayout";
import {
  DENSE_DEFAULT_CONNECTION_CONTROLS,
  countHiddenConnectionEdges,
  isDenseGraph,
  selectBestNeighbourLinks,
  selectVisibleConnectionEdges,
  type ConnectionControls,
} from "@/lib/meshGraphDense";
import {
  DEFAULT_LAYOUT_MODE,
  MESH_LAYOUT_MODES,
  clearSavedPositions,
  type MeshLayoutMode,
} from "@/lib/meshGraphSmartLayout";

type GraphDataSource = "live" | "sample";

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

const LIMITED_LAYOUT_COPY =
  "Topology snapshot was captured, but Zigbee2MQTT did not provide usable node/link layout data. Device health still comes from passive MQTT inventory and state updates.";

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
  disabled,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label
      className={`flex min-h-0 items-center gap-2 text-sm ${
        disabled ? "cursor-not-allowed text-zl-muted/60" : "cursor-pointer text-zl-text"
      }`}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 accent-[#5b9fd4]"
      />
      {label}
    </label>
  );
}

/** Connection-type checkbox with helper copy for the dense-mode panel. */
function ConnectionCheckbox({
  label,
  helper,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  helper: string;
  checked: boolean;
  onChange?: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label
      className={`block ${disabled ? "cursor-not-allowed" : "cursor-pointer"}`}
    >
      <span className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange?.(e.target.checked)}
          className="h-4 w-4 accent-[#5b9fd4]"
        />
        <span className={`text-sm ${disabled && !checked ? "text-zl-muted/60" : "text-zl-text"}`}>
          {label}
        </span>
      </span>
      <span className="mt-0.5 block pl-6 text-[11px] leading-snug text-zl-muted">{helper}</span>
    </label>
  );
}

function GraphPanel({
  devices,
  edges,
  filters,
  setFilters,
  liveMode,
  signatureSeed,
  positionStorageId,
  onSelectEdge,
  onSelectNode,
  selectedNodeId,
  selectedEdge,
}: {
  devices: MeshEvidenceDevice[];
  edges: MeshEvidenceEdge[];
  filters: EvidenceFilters;
  setFilters: (update: (f: EvidenceFilters) => EvidenceFilters) => void;
  liveMode: boolean;
  signatureSeed: string;
  positionStorageId: string;
  onSelectEdge: (edge: MeshEvidenceEdge) => void;
  onSelectNode: (device: MeshEvidenceDevice) => void;
  selectedNodeId: string | null;
  selectedEdge: MeshEvidenceEdge | null;
}) {
  const [controls, setControls] = useState<ConnectionControls>(
    DENSE_DEFAULT_CONNECTION_CONTROLS,
  );
  const [layoutMode, setLayoutMode] = useState<MeshLayoutMode>(DEFAULT_LAYOUT_MODE);
  const [resetNonce, setResetNonce] = useState(0);

  const filterVisibleEdges = useMemo(
    () => edges.filter((edge) => edgeVisible(edge, filters)),
    [edges, filters],
  );

  const structuralEdgeCount = useMemo(
    () => buildStructuralLayoutEdges(devices, edges).length,
    [devices, edges],
  );
  const denseMode = isDenseGraph({
    nodeCount: devices.length,
    evidenceEdgeCount: edges.length,
    structuralEdgeCount,
  });

  const bestNeighbourEdgeIds = useMemo(() => selectBestNeighbourLinks(edges), [edges]);
  const hasOldUncertainLinks = useMemo(
    () => edges.some((edge) => edge.evidence_class === "stale_low_confidence"),
    [edges],
  );

  // Dense mode changes which evidence edges are *rendered*, never which
  // evidence exists: hidden edges stay in the model/drawers and remain
  // reachable by selecting an endpoint device or "All neighbour links".
  const visibleEdges = useMemo(() => {
    if (!denseMode) return filterVisibleEdges;
    return selectVisibleConnectionEdges(edges, controls, {
      bestNeighbourEdgeIds,
      selectedNodeId,
      selectedEdge,
    });
  }, [
    denseMode,
    filterVisibleEdges,
    edges,
    controls,
    bestNeighbourEdgeIds,
    selectedNodeId,
    selectedEdge,
  ]);

  const hiddenEdgeCount = countHiddenConnectionEdges(edges, visibleEdges);

  const enabledConnectionLabels = [
    controls.routeHints ? "route hints" : null,
    controls.bestNeighbourLinks ? "best neighbour links" : null,
    "selected device links",
    controls.devicesWithIssues ? "devices with issues" : null,
    controls.oldUncertainLinks ? "old or uncertain links" : null,
  ].filter((label): label is string => label !== null);

  const setControl = (key: keyof ConnectionControls) => (value: boolean) =>
    setControls((c) => ({ ...c, [key]: value }));

  const layoutModeInfo = MESH_LAYOUT_MODES.find((m) => m.id === layoutMode);

  const resetLayout = () => {
    clearSavedPositions(positionStorageId, layoutMode);
    setResetNonce((n) => n + 1);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-sm">
            <span className="text-zl-muted" id="graph-layout-mode-label">
              Layout
            </span>
            <select
              value={layoutMode}
              onChange={(e) => setLayoutMode(e.target.value as MeshLayoutMode)}
              aria-labelledby="graph-layout-mode-label"
              className="rounded-lg border border-zl-border bg-zl-surface-2 px-2 py-1.5 text-sm"
            >
              {MESH_LAYOUT_MODES.map((mode) => (
                <option key={mode.id} value={mode.id}>
                  {mode.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={resetLayout}
            className="rounded-lg border border-zl-border bg-zl-surface-2 px-3 py-1.5 text-sm text-zl-text hover:border-zl-accent/40"
          >
            Reset layout
          </button>
        </div>
        {layoutModeInfo && (
          <p
            className="max-w-md text-[11px] leading-snug text-zl-muted"
            data-testid="layout-mode-description"
          >
            {layoutModeInfo.description}
          </p>
        )}
      </div>
      {denseMode && (
        <div
          role="note"
          aria-label="Dense graph mode"
          data-testid="dense-graph-banner"
          className="space-y-1 rounded-lg border border-zl-border bg-zl-surface px-4 py-3 text-sm"
        >
          <p className="font-medium text-zl-text">Dense graph mode</p>
          <p className="text-zl-muted" data-testid="dense-graph-counts">
            {edges.length} evidence links available · {visibleEdges.length} shown ·{" "}
            {hiddenEdgeCount} hidden for readability
          </p>
          {controls.allNeighbourLinks ? (
            <p className="text-zl-muted">
              Showing all neighbour links may be hard to read on dense networks.
            </p>
          ) : (
            <p className="text-zl-muted">
              Showing a readable subset: {enabledConnectionLabels.join(", ")}. Turn on “All
              neighbour links” to show the full snapshot evidence.
            </p>
          )}
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
      <Card className="!p-2">
        <div className="h-[600px]" data-testid="mesh-evidence-graph">
          <MeshEvidenceGraph
            devices={devices}
            visibleEdges={visibleEdges}
            allEdges={edges}
            signatureSeed={signatureSeed}
            layoutMode={layoutMode}
            positionStorageId={positionStorageId}
            resetNonce={resetNonce}
            highlightIssueDevices={controls.devicesWithIssues}
            selectedNodeId={selectedNodeId}
            onSelectEdge={onSelectEdge}
            onSelectNode={onSelectNode}
          />
        </div>
      </Card>

      <div className="space-y-4">
        <Card>
          <GraphLegend />
        </Card>
        {denseMode ? (
        <Card>
          <div role="group" aria-label="Connections to show" className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-zl-muted">
              Connections to show
            </h3>
            <ConnectionCheckbox
              label="Route hints"
              helper="Route-table evidence observed in the latest snapshot. This suggests possible next-hop evidence at capture time, not guaranteed live routing."
              checked={controls.routeHints}
              onChange={setControl("routeHints")}
            />
            <ConnectionCheckbox
              label="Best neighbour links"
              helper="A readable subset of observed neighbour links, chosen to keep dense networks understandable."
              checked={controls.bestNeighbourLinks}
              onChange={setControl("bestNeighbourLinks")}
            />
            <ConnectionCheckbox
              label="Selected device links"
              helper="Always on — selecting a device reveals its full neighbourhood."
              checked
              disabled
            />
            <ConnectionCheckbox
              label="Devices with issues"
              helper="Highlight devices already marked by ZigbeeLens as needing attention."
              checked={controls.devicesWithIssues}
              onChange={setControl("devicesWithIssues")}
            />
            <ConnectionCheckbox
              label="All neighbour links"
              helper="Show every observed neighbour link. This may be hard to read on dense networks."
              checked={controls.allNeighbourLinks}
              onChange={setControl("allNeighbourLinks")}
            />
            <ConnectionCheckbox
              label="Old or uncertain links"
              helper={
                hasOldUncertainLinks
                  ? "Show old or low-confidence evidence that may be useful for investigation but should not be treated as current."
                  : "No old or uncertain links in this snapshot."
              }
              checked={hasOldUncertainLinks && controls.oldUncertainLinks}
              disabled={!hasOldUncertainLinks}
              onChange={setControl("oldUncertainLinks")}
            />
            <ConnectionCheckbox
              label="Previously seen links"
              helper="Coming later — historical topology links observed in previous snapshots but not in the latest snapshot."
              checked={false}
              disabled
            />
            <ConnectionCheckbox
              label="Suggested investigation links"
              helper="Coming later — possible relationships suggested by passive observations. These are investigation hints, not topology evidence."
              checked={false}
              disabled
            />
            <p className="text-[11px] leading-snug text-zl-muted">
              Turning a connection type off only hides evidence for readability — it never means
              a relationship is gone. Hidden links stay reachable by selecting a device or
              turning on “All neighbour links”.
            </p>
          </div>
        </Card>
        ) : (
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
              checked={liveMode ? false : filters.historical}
              disabled={liveMode}
              onChange={(v) => setFilters((f) => ({ ...f, historical: v }))}
            />
            <label
              className={`block text-sm ${liveMode ? "text-zl-muted/60" : "text-zl-text"}`}
            >
              <span className="mb-1 block">Passive-derived hints</span>
              <select
                value={liveMode ? "off" : filters.passive}
                disabled={liveMode}
                onChange={(e) =>
                  setFilters((f) => ({ ...f, passive: e.target.value as PassiveFilterMode }))
                }
                className="w-full rounded-lg border border-zl-border bg-zl-surface-2 px-2 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-60"
              >
                <option value="issue_related">Issue-related only (default)</option>
                <option value="all">All passive hints</option>
                <option value="off">Hidden</option>
              </select>
            </label>
            <FilterCheckbox
              label="Stale / low-confidence evidence"
              checked={liveMode ? false : filters.staleLowConfidence}
              disabled={liveMode}
              onChange={(v) => setFilters((f) => ({ ...f, staleLowConfidence: v }))}
            />
            {liveMode && (
              <p className="text-[11px] leading-snug text-zl-muted">
                Historical, passive-derived and stale evidence classes are not produced from live
                snapshot data yet. They remain available in prototype sample data.
              </p>
            )}
            <p className="text-[11px] leading-snug text-zl-muted">
              Hiding an evidence class only hides claims — it never means the relationship is
              gone.
            </p>
          </div>
        </Card>
        )}
      </div>
      </div>
    </div>
  );
}

export function TopologyGraphPage() {
  const { status, scenario } = useScenario();
  const { networkId } = useParams<{ networkId?: string }>();
  const [source, setSource] = useState<GraphDataSource>("live");
  const [filters, setFilters] = useState<EvidenceFilters>(DEFAULT_FILTERS);
  const [selectedEdge, setSelectedEdge] = useState<MeshEvidenceEdge | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<MeshEvidenceDevice | null>(null);

  const liveMode = source === "live";

  const detail = useLiveResource(
    () =>
      networkId
        ? api.topologyNetwork(networkId)
        : Promise.reject(new Error("No network selected")),
    [networkId],
    { enabled: liveMode && Boolean(networkId) },
  );
  const inventory = useLiveResource(
    () => api.devices(scenario || undefined, networkId),
    [networkId, scenario],
    { enabled: liveMode && Boolean(networkId) },
  );

  const liveEvidence = useMemo(() => {
    if (!detail.data) return null;
    return buildLiveMeshEvidence(detail.data, inventory.data?.items ?? []);
  }, [detail.data, inventory.data]);

  const fixture = meshEvidenceGraphFixture;
  const snapshot = detail.data?.latest_snapshot;
  const layoutAvailable = Boolean(
    detail.data?.layout_available ??
      ((detail.data?.nodes?.length ?? 0) > 0 || (detail.data?.links?.length ?? 0) > 0),
  );
  const topologyEnabled = status?.topology?.enabled ?? true;

  // Stable data identity for layout caching: network + mode + snapshot only.
  // Refetch timestamps, filters, selection and drawer state must never be in
  // here — layout recomputes only when this (plus graph content) changes.
  const liveSignatureSeed = `live|${networkId ?? "none"}|${
    snapshot?.snapshot_id ?? snapshot?.captured_at ?? "no-snapshot"
  }`;
  const sampleSignatureSeed = `sample|${fixture.network_id}|${fixture.latest_snapshot_captured_at}`;

  const selectEdge = (edge: MeshEvidenceEdge) => {
    setSelectedDevice(null);
    setSelectedEdge(edge);
  };
  const selectNode = (device: MeshEvidenceDevice) => {
    setSelectedEdge(null);
    setSelectedDevice(device);
  };

  const changeSource = (next: GraphDataSource) => {
    setSource(next);
    setSelectedEdge(null);
    setSelectedDevice(null);
  };

  return (
    <div className="max-w-7xl space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Mesh evidence graph</h1>
          <p className="mt-1 text-zl-muted">
            {liveMode ? (
              <>
                Latest topology snapshot evidence for network{" "}
                <span className="font-mono">{networkId ?? "—"}</span>
                {detail.data?.network_name ? ` (${detail.data.network_name})` : ""}.
              </>
            ) : (
              <>Sample evidence data for design validation — not data from your network.</>
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {liveMode ? (
            <span
              data-testid="graph-mode-badge"
              className="inline-flex items-center gap-1.5 rounded-full border border-zl-healthy/40 bg-zl-healthy/10 px-3 py-1 text-xs font-medium text-zl-healthy"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-zl-healthy" aria-hidden="true" />
              Live topology snapshot
            </span>
          ) : (
            <span
              data-testid="graph-mode-badge"
              className="inline-flex items-center rounded-full border border-zl-watch/40 bg-zl-watch/10 px-3 py-1 text-xs font-medium text-zl-watch"
            >
              Prototype — sample data
            </span>
          )}
          <label className="flex items-center gap-2 text-sm">
            <span className="text-zl-muted" id="graph-source-label">
              Data source
            </span>
            <select
              value={source}
              onChange={(e) => changeSource(e.target.value as GraphDataSource)}
              aria-labelledby="graph-source-label"
              className="rounded-lg border border-zl-border bg-zl-surface-2 px-2 py-1.5 text-sm"
            >
              <option value="live">Live topology snapshot</option>
              <option value="sample">Prototype sample data</option>
            </select>
          </label>
        </div>
      </header>

      <TopologyViewTabs networkId={networkId ?? fixture.network_id} />

      <div
        role="note"
        aria-label="Evidence safety note"
        className="rounded-lg border border-zl-accent/40 bg-zl-accent/10 px-4 py-3 text-sm leading-relaxed text-zl-text"
      >
        {GRAPH_SAFETY_COPY}
      </div>

      {liveMode ? (
        !networkId ? (
          <Card title="No network selected">
            <p className="text-sm text-zl-muted">
              Open the graph from a network on the{" "}
              <Link to="/topology" className="text-zl-accent">
                Topology page
              </Link>{" "}
              to see live snapshot evidence.
            </p>
          </Card>
        ) : !topologyEnabled ? (
          <Card title="Topology disabled">
            <p className="text-sm text-zl-muted">
              Topology capture is disabled in configuration, so no live snapshot evidence is
              available. Prototype sample data remains available from the data source selector.
            </p>
          </Card>
        ) : detail.loading || (inventory.loading && !detail.data) ? (
          <LoadingState />
        ) : detail.error ? (
          <ErrorState message={detail.error} onRetry={detail.refetch} />
        ) : !snapshot ? (
          <Card title="Waiting for a topology snapshot">
            <div className="space-y-3 text-sm text-zl-muted">
              <Badge severity="watch">diagnostics limited</Badge>
              <p>
                No topology snapshot has been captured for this network yet. After startup,
                ZigbeeLens requests one network map per network once MQTT and the bridge are
                ready, then relies on passive updates.
              </p>
              <p>
                Missing topology data is not an incident by itself — it only limits mesh
                enrichment. Device health still comes from passive MQTT inventory and state
                updates.
              </p>
              <p>
                <Link to={`/topology/${networkId}`} className="text-zl-accent">
                  Open snapshot view
                </Link>{" "}
                ·{" "}
                <Link to="/devices" className="text-zl-accent">
                  Open devices
                </Link>
              </p>
            </div>
          </Card>
        ) : !layoutAvailable ? (
          <Card
            title="Topology layout limited"
            subtitle={
              snapshot.captured_at
                ? `Latest snapshot captured ${relativeTime(snapshot.captured_at)}`
                : undefined
            }
          >
            <div className="space-y-3 text-sm">
              <p className="border-l-2 border-zl-watch/40 pl-3 text-zl-muted">
                {LIMITED_LAYOUT_COPY}
              </p>
              <div className="flex flex-wrap gap-2">
                <MetricPill label="Snapshot status" value={topologyStatusLabel(snapshot.status)} />
                <MetricPill label="Observed topology nodes" value="—" />
                <MetricPill label="Observed topology links" value="—" />
                {detail.data?.inventory && (
                  <>
                    <MetricPill label="Known devices" value={detail.data.inventory.device_count} />
                    <MetricPill label="Known routers" value={detail.data.inventory.router_count} />
                    <MetricPill
                      label="Known end devices"
                      value={detail.data.inventory.end_device_count}
                    />
                  </>
                )}
              </div>
              <p className="text-zl-muted">
                Missing topology data is not an incident by itself.{" "}
                <Link to={`/topology/${networkId}`} className="text-zl-accent">
                  Open snapshot view
                </Link>{" "}
                ·{" "}
                <Link to="/devices" className="text-zl-accent">
                  Open devices
                </Link>
              </p>
            </div>
          </Card>
        ) : liveEvidence ? (
          <>
            <div className="flex flex-wrap gap-2">
              <MetricPill label="Network" value={detail.data?.network_name ?? networkId} />
              {snapshot.captured_at && (
                <MetricPill label="Captured" value={relativeTime(snapshot.captured_at)} />
              )}
              <MetricPill label="Snapshot status" value={topologyStatusLabel(snapshot.status)} />
              <MetricPill label="Observed topology nodes" value={detail.data?.nodes?.length ?? 0} />
              <MetricPill
                label="Snapshot evidence links"
                value={liveEvidence.edges.length}
              />
              {detail.data?.inventory && (
                <MetricPill label="Known devices" value={detail.data.inventory.device_count} />
              )}
            </div>
            <GraphPanel
              devices={liveEvidence.devices}
              edges={liveEvidence.edges}
              filters={filters}
              setFilters={setFilters}
              liveMode
              signatureSeed={liveSignatureSeed}
              positionStorageId={networkId ?? "unknown-network"}
              onSelectEdge={selectEdge}
              onSelectNode={selectNode}
              selectedNodeId={selectedDevice?.ieee_address ?? null}
              selectedEdge={selectedEdge}
            />
          </>
        ) : null
      ) : (
        <>
          <p className="text-xs text-zl-muted">
            This prototype sample dataset demonstrates the full evidence grammar, including
            historical, passive-derived and stale evidence classes that live snapshot data cannot
            produce yet. It does not represent network{" "}
            <span className="font-mono">{networkId ?? fixture.network_id}</span>.
          </p>
          <GraphPanel
            devices={fixture.devices}
            edges={fixture.edges}
            filters={filters}
            setFilters={setFilters}
            liveMode={false}
            signatureSeed={sampleSignatureSeed}
            positionStorageId={`sample-${fixture.network_id}`}
            onSelectEdge={selectEdge}
            onSelectNode={selectNode}
            selectedNodeId={selectedDevice?.ieee_address ?? null}
            selectedEdge={selectedEdge}
          />
        </>
      )}

      {selectedEdge && (
        <EdgeDrawer
          edge={selectedEdge}
          devices={liveMode && liveEvidence ? liveEvidence.devices : fixture.devices}
          onClose={() => setSelectedEdge(null)}
        />
      )}
      {selectedDevice && (
        <NodeDrawer device={selectedDevice} onClose={() => setSelectedDevice(null)} />
      )}
    </div>
  );
}
