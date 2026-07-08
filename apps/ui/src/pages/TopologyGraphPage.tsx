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
import { buildLiveMeshEvidence } from "@/lib/meshEvidenceLive";
import { relativeTime } from "@/lib/format";
import { topologyStatusLabel } from "@/lib/topologyLabels";
import {
  GRAPH_SAFETY_COPY_LIVE,
  type MeshEvidenceDevice,
  type MeshEvidenceEdge,
} from "@/lib/meshEvidence";
import {
  DEFAULT_CONNECTION_CONTROLS,
  clearConnectionControls,
  collectIssueDeviceIds,
  collectRouteCoveredPairs,
  loadConnectionControls,
  saveConnectionControls,
  selectAdaptiveBestNeighbourLinks,
  selectPassiveHintEdges,
  selectRecentMissingEdges,
  selectVisibleConnectionEdges,
  type ConnectionControls,
} from "@/lib/meshGraphDense";
import {
  DEFAULT_LAYOUT_MODE,
  MESH_LAYOUT_MODES,
  clearSavedPositions,
  type MeshLayoutMode,
} from "@/lib/meshGraphSmartLayout";

const ROUTE_HINTS_HELPER =
  "Route-table evidence from the latest snapshot. This suggests possible next-hop evidence at capture time, not guaranteed live routing.";
const NO_ROUTE_HINTS_COPY =
  "No route-table entries in the latest snapshot. ZigbeeLens requests route tables during topology capture, so capture a new snapshot; if routes stay empty, your Zigbee2MQTT adapter may not report routing tables.";

const RECENT_MISSING_HELPER =
  "Draw recent links observed in previous topology snapshots but not present in the latest usable snapshot.";
const NO_RECENT_MISSING_COPY = "No recent missing links in the selected history window.";

const SUGGESTED_INVESTIGATION_HELPER =
  "Draw cautious investigation hints suggested by passive observations. These are not topology links or proof of live routing.";
const NO_PASSIVE_HINTS_COPY = "None from recent passive observations.";

/** Plain-language explainer for the two latest-snapshot evidence types. */
function ConnectionsExplainer() {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="text-[11px] text-zl-accent hover:underline"
        data-testid="connections-explainer-toggle"
      >
        What do these mean?
      </button>
      {open && (
        <div
          className="mt-2 space-y-2 rounded-lg border border-zl-border bg-zl-surface-2 p-2 text-[11px] leading-snug text-zl-muted"
          data-testid="connections-explainer"
        >
          <p>
            <span className="font-semibold text-zl-text">Best neighbour links</span> come from
            each device&apos;s neighbour table: the other devices it could hear over the radio,
            with a link quality (LQI) reading. They show which connections are possible.
            ZigbeeLens draws a focused set of the strongest links per device so dense networks
            stay readable; “All neighbour links” draws every one.
          </p>
          <p>
            <span className="font-semibold text-zl-text">Route hints</span> come from each
            router&apos;s routing table: the next-hop entries it reported at the moment the
            snapshot was captured. They are closer to how the mesh was operating than radio
            audibility alone, but Zigbee routes change frequently — this is capture-time
            evidence, not proof of current live routing.
          </p>
          <p>
            In short: neighbour links show what is possible, route hints show what was being
            used at capture time. Where a device pair has both, only the route hint is drawn —
            one line per pair. The neighbour evidence is never removed: select a device to see
            its full evidence neighbourhood.
          </p>
        </div>
      )}
    </div>
  );
}

const LIMITED_LAYOUT_COPY =
  "Topology snapshot was captured, but Zigbee2MQTT did not provide usable node/link layout data. Device health still comes from passive MQTT inventory and state updates.";

/** Connection-type checkbox with helper copy. */
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
  signatureSeed,
  positionStorageId,
  onSelectEdge,
  onSelectNode,
  selectedNodeId,
  selectedEdge,
}: {
  devices: MeshEvidenceDevice[];
  edges: MeshEvidenceEdge[];
  signatureSeed: string;
  positionStorageId: string;
  onSelectEdge: (edge: MeshEvidenceEdge) => void;
  onSelectNode: (device: MeshEvidenceDevice) => void;
  selectedNodeId: string | null;
  selectedEdge: MeshEvidenceEdge | null;
}) {
  // Connection choices are restored per network and persisted on change.
  const [controls, setControls] = useState<ConnectionControls>(() =>
    loadConnectionControls(positionStorageId),
  );
  const [layoutMode, setLayoutMode] = useState<MeshLayoutMode>(DEFAULT_LAYOUT_MODE);
  const [resetNonce, setResetNonce] = useState(0);

  // Adaptive budget: the largest per-device neighbour count whose selection
  // stays within ~1.5 drawn links per node. Small graphs keep everything.
  // While route hints are drawn, pairs already covered by a route edge are
  // excluded so the neighbour allowance reaches otherwise-unconnected pairs
  // (one line per pair — never a neighbour line parallel to a route hint).
  const bestNeighbourEdgeIds = useMemo(() => {
    const excludePairs = controls.routeHints ? collectRouteCoveredPairs(edges) : undefined;
    return selectAdaptiveBestNeighbourLinks(edges, devices.length, excludePairs).edgeIds;
  }, [edges, devices.length, controls.routeHints]);
  const hasOldUncertainLinks = useMemo(
    () => edges.some((edge) => edge.evidence_class === "stale_low_confidence"),
    [edges],
  );
  const hasRouteHints = useMemo(
    () => edges.some((edge) => edge.evidence_class === "latest_snapshot_route"),
    [edges],
  );
  const recentMissingEdges = useMemo(
    () =>
      edges.filter(
        (edge) =>
          edge.evidence_class === "historical_neighbor" ||
          edge.evidence_class === "historical_route",
      ),
    [edges],
  );
  const hasRecentMissingLinks = recentMissingEdges.length > 0;
  const passiveHintEdges = useMemo(
    () => edges.filter((edge) => edge.evidence_class === "passive_derived_association"),
    [edges],
  );
  const hasPassiveHints = passiveHintEdges.length > 0;

  // Focused subset of recent missing links: relevance rules (existing issue
  // flags, endpoints without latest neighbour evidence, limited latest
  // layout) plus deterministic per-node/total caps.
  const recentMissingEdgeIds = useMemo(() => {
    const issueDeviceIds = collectIssueDeviceIds(devices);
    const devicesWithLatestNeighbourEvidence = new Set<string>();
    for (const edge of edges) {
      if (edge.evidence_class !== "latest_snapshot_neighbor") continue;
      devicesWithLatestNeighbourEvidence.add(edge.source);
      devicesWithLatestNeighbourEvidence.add(edge.target);
    }
    const latestLayoutLimited = recentMissingEdges.some(
      (edge) => edge.latest_layout_limited === true,
    );
    return selectRecentMissingEdges(edges, {
      issueDeviceIds,
      devicesWithLatestNeighbourEvidence,
      latestLayoutLimited,
    });
  }, [devices, edges, recentMissingEdges]);

  // Focused subset of passive-derived hints: selected-device hints first,
  // then issue-related, higher-confidence and recent hints, capped per node
  // and in total so hints never form a new hairball.
  const passiveHintEdgeIds = useMemo(
    () =>
      selectPassiveHintEdges(edges, {
        issueDeviceIds: collectIssueDeviceIds(devices),
        selectedNodeId,
      }),
    [edges, devices, selectedNodeId],
  );

  // Connection controls change only which evidence edges are *rendered*,
  // never which evidence exists: undrawn edges stay in the model/drawers and
  // remain reachable by selecting an endpoint device or "All neighbour links".
  const visibleEdges = useMemo(
    () =>
      selectVisibleConnectionEdges(edges, controls, {
        bestNeighbourEdgeIds,
        recentMissingEdgeIds,
        passiveHintEdgeIds,
        selectedNodeId,
        selectedEdge,
      }),
    [
      edges,
      controls,
      bestNeighbourEdgeIds,
      recentMissingEdgeIds,
      passiveHintEdgeIds,
      selectedNodeId,
      selectedEdge,
    ],
  );

  const setControl = (key: keyof ConnectionControls) => (value: boolean) =>
    setControls((c) => {
      const next = { ...c, [key]: value };
      saveConnectionControls(positionStorageId, next);
      return next;
    });

  const resetConnectionChoices = () => {
    clearConnectionControls(positionStorageId);
    setControls({ ...DEFAULT_CONNECTION_CONTROLS });
  };

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
                  {mode.label} — {mode.hint}
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
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px] lg:items-stretch">
      {/* The graph stretches to the full grid row: at least the viewport
          (minus app chrome) and never shorter than the sidebar column, so
          it always reaches the bottom of the content area. */}
      <Card className="flex !p-2">
        <div
          className="min-h-[600px] w-full lg:min-h-[calc(100dvh-13rem)]"
          data-testid="mesh-evidence-graph"
        >
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
          <GraphLegend hasPassiveHints={hasPassiveHints} />
        </Card>
        <Card>
          <div role="group" aria-label="Connections to show" className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-zl-muted">
              Connections to show
            </h3>
            <ConnectionsExplainer />
            <ConnectionCheckbox
              label="Route hints"
              helper={hasRouteHints ? ROUTE_HINTS_HELPER : NO_ROUTE_HINTS_COPY}
              checked={hasRouteHints && controls.routeHints}
              disabled={!hasRouteHints}
              onChange={setControl("routeHints")}
            />
            <ConnectionCheckbox
              label="Best neighbour links"
              helper="A focused set of observed neighbour links chosen to keep the graph understandable."
              checked={controls.bestNeighbourLinks}
              onChange={setControl("bestNeighbourLinks")}
            />
            <ConnectionCheckbox
              label="Devices with issues"
              helper="Highlight devices already marked by ZigbeeLens as needing attention."
              checked={controls.devicesWithIssues}
              onChange={setControl("devicesWithIssues")}
            />
            <ConnectionCheckbox
              label="All neighbour links"
              helper="Draw every observed neighbour link from the latest snapshot. Dense networks may become hard to read."
              checked={controls.allNeighbourLinks}
              onChange={setControl("allNeighbourLinks")}
            />
            {controls.allNeighbourLinks && (
              <p
                className="pl-6 text-[11px] leading-snug text-zl-muted"
                data-testid="all-neighbour-links-warning"
              >
                All neighbour links is on. Dense networks may become hard to read.
              </p>
            )}
            <ConnectionCheckbox
              label="Old or uncertain links"
              helper={
                hasOldUncertainLinks
                  ? "Draw stale or low-confidence evidence that may help investigation but should not be treated as current."
                  : "No old or uncertain links in this snapshot."
              }
              checked={hasOldUncertainLinks && controls.oldUncertainLinks}
              disabled={!hasOldUncertainLinks}
              onChange={setControl("oldUncertainLinks")}
            />
            <ConnectionCheckbox
              label="Recent missing links"
              helper={hasRecentMissingLinks ? RECENT_MISSING_HELPER : NO_RECENT_MISSING_COPY}
              checked={hasRecentMissingLinks && controls.recentMissingLinks}
              disabled={!hasRecentMissingLinks}
              onChange={setControl("recentMissingLinks")}
            />
            <ConnectionCheckbox
              label="Suggested investigation links"
              helper={hasPassiveHints ? SUGGESTED_INVESTIGATION_HELPER : NO_PASSIVE_HINTS_COPY}
              checked={hasPassiveHints && controls.suggestedInvestigationLinks}
              disabled={!hasPassiveHints}
              onChange={setControl("suggestedInvestigationLinks")}
            />
            <p className="text-[11px] leading-snug text-zl-muted">
              Turning a connection type off only changes what is drawn — it never means a
              relationship is gone. All evidence remains available by selecting a device or
              turning on “All neighbour links”.
            </p>
            <button
              type="button"
              onClick={resetConnectionChoices}
              className="text-[11px] text-zl-accent hover:underline"
            >
              Reset connection choices
            </button>
          </div>
        </Card>
      </div>
      </div>
    </div>
  );
}

export function TopologyGraphPage() {
  const { status, scenario } = useScenario();
  const { networkId } = useParams<{ networkId?: string }>();
  const [selectedEdge, setSelectedEdge] = useState<MeshEvidenceEdge | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<MeshEvidenceDevice | null>(null);

  const detail = useLiveResource(
    () =>
      networkId
        ? api.topologyEvidenceGraph(networkId)
        : Promise.reject(new Error("No network selected")),
    [networkId],
    { enabled: Boolean(networkId) },
  );
  const inventory = useLiveResource(
    () => api.devices(scenario || undefined, networkId),
    [networkId, scenario],
    { enabled: Boolean(networkId) },
  );

  const liveEvidence = useMemo(() => {
    if (!detail.data) return null;
    return buildLiveMeshEvidence(detail.data, inventory.data?.items ?? []);
  }, [detail.data, inventory.data]);

  const snapshot = detail.data?.latest_snapshot;
  const layoutAvailable = Boolean(
    detail.data?.layout_available ??
      ((detail.data?.nodes?.length ?? 0) > 0 || (detail.data?.links?.length ?? 0) > 0),
  );
  const topologyEnabled = status?.topology?.enabled ?? true;

  // Stable data identity for layout caching: network + snapshot only.
  // Refetch timestamps, filters, selection and drawer state must never be in
  // here — layout recomputes only when this (plus graph content) changes.
  const liveSignatureSeed = `live|${networkId ?? "none"}|${
    snapshot?.snapshot_id ?? snapshot?.captured_at ?? "no-snapshot"
  }`;

  const selectEdge = (edge: MeshEvidenceEdge) => {
    setSelectedDevice(null);
    setSelectedEdge(edge);
  };
  const selectNode = (device: MeshEvidenceDevice) => {
    setSelectedEdge(null);
    setSelectedDevice(device);
  };

  return (
    <div className="max-w-7xl space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Mesh evidence graph</h1>
          <p className="mt-1 text-zl-muted">
            Latest topology snapshot evidence for network{" "}
            <span className="font-mono">{networkId ?? "—"}</span>
            {detail.data?.network_name ? ` (${detail.data.network_name})` : ""}.
          </p>
        </div>
        <span
          data-testid="graph-mode-badge"
          className="inline-flex items-center gap-1.5 rounded-full border border-zl-healthy/40 bg-zl-healthy/10 px-3 py-1 text-xs font-medium text-zl-healthy"
        >
          <span className="h-1.5 w-1.5 rounded-full bg-zl-healthy" aria-hidden="true" />
          Live topology snapshot
        </span>
      </header>

      {networkId && <TopologyViewTabs networkId={networkId} />}

      <div
        role="note"
        aria-label="Evidence safety note"
        className="rounded-lg border border-zl-accent/40 bg-zl-accent/10 px-4 py-3 text-sm leading-relaxed text-zl-text"
      >
        {GRAPH_SAFETY_COPY_LIVE}
      </div>

      {!networkId ? (
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
              available.
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
              <MetricPill
                label="Observed topology nodes"
                value={detail.data?.nodes?.length ?? 0}
                description="Devices present in the latest parsed topology snapshot."
              />
              <MetricPill
                label="Snapshot evidence links"
                value={
                  liveEvidence.edges.filter((edge) => edge.in_latest_snapshot).length
                }
                description="Links reported in the latest topology snapshot."
              />
              {detail.data?.counts && (
                <MetricPill
                  label="Recent missing links"
                  value={
                    detail.data.counts.historical_neighbor_edges +
                    detail.data.counts.historical_route_edges
                  }
                  description="Links seen in recent previous topology snapshots but not present in the latest usable snapshot."
                />
              )}
              {detail.data?.inventory && (
                <MetricPill
                  label="Known devices"
                  value={detail.data.inventory.device_count}
                  description="Devices ZigbeeLens knows from Zigbee2MQTT inventory."
                />
              )}
            </div>
            <GraphPanel
              // Remount per network so persisted connection choices and
              // layout state are restored for the network being viewed.
              key={networkId ?? "unknown-network"}
              devices={liveEvidence.devices}
              edges={liveEvidence.edges}
              signatureSeed={liveSignatureSeed}
              positionStorageId={networkId ?? "unknown-network"}
              onSelectEdge={selectEdge}
              onSelectNode={selectNode}
              selectedNodeId={selectedDevice?.ieee_address ?? null}
              selectedEdge={selectedEdge}
            />
          </>
      ) : null}

      {selectedEdge && (
        <EdgeDrawer
          edge={selectedEdge}
          devices={liveEvidence?.devices ?? []}
          onClose={() => setSelectedEdge(null)}
        />
      )}
      {selectedDevice && (
        <NodeDrawer device={selectedDevice} onClose={() => setSelectedDevice(null)} />
      )}
    </div>
  );
}
