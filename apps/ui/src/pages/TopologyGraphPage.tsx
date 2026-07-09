import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import {
  api,
  type InvestigationCard,
  type SnapshotCompareChange,
  type SnapshotCompareDetail,
} from "@/lib/api";
import { Badge, Card, ErrorState, LoadingState, MetricPill } from "@/components/ui";
import { GraphLegend } from "@/components/meshGraph/GraphLegend";
import { InvestigationPanel } from "@/components/meshGraph/InvestigationPanel";
import {
  MeshEvidenceGraph,
  type InvestigationFocus,
} from "@/components/meshGraph/MeshEvidenceGraph";
import { DeviceSearch } from "@/components/meshGraph/DeviceSearch";
import { EvidenceReportMenu } from "@/components/meshGraph/EvidenceReportMenu";
import { EdgeDrawer } from "@/components/meshGraph/EdgeDrawer";
import { NodeDrawer } from "@/components/meshGraph/NodeDrawer";
import { SnapshotComparePanel } from "@/components/meshGraph/SnapshotComparePanel";
import { TopologyViewTabs } from "@/components/meshGraph/TopologyViewTabs";
import { buildLiveMeshEvidence } from "@/lib/meshEvidenceLive";
import { relativeTime } from "@/lib/format";
import { topologyStatusLabel } from "@/lib/topologyLabels";
import { type MeshEvidenceDevice, type MeshEvidenceEdge } from "@/lib/meshEvidence";
import {
  COMPARE_BUTTON_LABEL,
  CONNECTION_CONTROL_COPY,
  CONNECTIONS_EXPLAINER,
  CONNECTIONS_EXPLAINER_TOGGLE,
  CONNECTIONS_FOOTNOTE,
  CONNECTIONS_GROUP_LABEL,
  GRAPH_SAFETY_COPY_LIVE,
} from "@/lib/meshGraphCopy";
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
import { buildMeshEvidenceReport } from "@/lib/meshEvidenceReport";

/** Plain-language explainer for connection evidence types. */
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
        {CONNECTIONS_EXPLAINER_TOGGLE}
      </button>
      {open && (
        <div
          className="mt-2 space-y-2 rounded-lg border border-zl-border bg-zl-surface-2 p-2 text-[11px] leading-snug text-zl-muted"
          data-testid="connections-explainer"
        >
          <p>
            <span className="font-semibold text-zl-text">
              {CONNECTION_CONTROL_COPY.bestNeighbourLinks.label}
            </span>{" "}
            {CONNECTIONS_EXPLAINER.bestNeighbourLinks.replace(
              /^Best neighbour links come from /,
              "come from ",
            )}
          </p>
          <p>
            <span className="font-semibold text-zl-text">
              {CONNECTION_CONTROL_COPY.routeHints.label}
            </span>{" "}
            {CONNECTIONS_EXPLAINER.routeHints.replace(/^Route hints come from /, "come from ")}
          </p>
          <p>{CONNECTIONS_EXPLAINER.summary}</p>
          <p>
            <span className="font-semibold text-zl-text">
              {CONNECTION_CONTROL_COPY.recentMissingLinks.label}
            </span>{" "}
            {CONNECTIONS_EXPLAINER.recentMissingLinks.replace(/^Recent missing links /, "")}
          </p>
          <p>
            <span className="font-semibold text-zl-text">
              {CONNECTION_CONTROL_COPY.lastKnownLinks.label}
            </span>{" "}
            {CONNECTIONS_EXPLAINER.lastKnownLinks.replace(/^Last known links /, "")}
          </p>
          <p>{CONNECTIONS_EXPLAINER.allNeighbourLinks}</p>
          <p>
            <span className="font-semibold text-zl-text">
              {CONNECTION_CONTROL_COPY.suggestedInvestigationLinks.label}
            </span>{" "}
            {CONNECTIONS_EXPLAINER.suggestedInvestigationLinks.replace(
              /^Suggested investigation links /,
              "",
            )}
          </p>
        </div>
      )}
    </div>
  );
}

const LIMITED_LAYOUT_COPY =
  "Topology snapshot was captured, but Zigbee2MQTT did not provide usable node/link layout data. Device health still comes from passive MQTT inventory and state updates.";

/** Connection-type checkbox. Helper copy renders only when provided (e.g. why a control is unavailable). */
function ConnectionCheckbox({
  label,
  helper,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  helper?: string;
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
      {helper && (
        <span className="mt-0.5 block pl-6 text-[11px] leading-snug text-zl-muted">{helper}</span>
      )}
    </label>
  );
}

function GraphPanel({
  devices,
  edges,
  investigations,
  signatureSeed,
  networkId,
  networkName,
  latestSnapshotCapturedAt,
  positionStorageId,
  onSelectEdge,
  onSelectNode,
  onClearSelection,
  selectedNodeId,
  selectedEdge,
}: {
  devices: MeshEvidenceDevice[];
  edges: MeshEvidenceEdge[];
  investigations: InvestigationCard[];
  signatureSeed: string;
  networkId: string;
  networkName?: string | null;
  latestSnapshotCapturedAt?: string | null;
  positionStorageId: string;
  onSelectEdge: (edge: MeshEvidenceEdge) => void;
  onSelectNode: (device: MeshEvidenceDevice) => void;
  onClearSelection: () => void;
  selectedNodeId: string | null;
  selectedEdge: MeshEvidenceEdge | null;
}) {
  // Connection choices are restored per network and persisted on change.
  const [controls, setControls] = useState<ConnectionControls>(() =>
    loadConnectionControls(positionStorageId),
  );
  const [layoutMode, setLayoutMode] = useState<MeshLayoutMode>(DEFAULT_LAYOUT_MODE);
  const [resetNonce, setResetNonce] = useState(0);
  // Investigation focus is visual only: it highlights involved devices,
  // ensures involved edges are drawn, and dims the rest. It never moves
  // nodes, never changes connection controls, never mutates saved layout.
  const [activeInvestigation, setActiveInvestigation] = useState<InvestigationCard | null>(
    null,
  );

  // Snapshot compare is a read-only overlay: it never creates evidence
  // classes, never moves nodes, and never touches connection controls.
  // Empty-state copy exists only inside the compare panel, never in the
  // normal graph view.
  const [compareOpen, setCompareOpen] = useState(false);
  const [compareData, setCompareData] = useState<SnapshotCompareDetail | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [activeCompareChange, setActiveCompareChange] =
    useState<SnapshotCompareChange | null>(null);

  useEffect(() => {
    if (!compareOpen || compareData !== null) return;
    let cancelled = false;
    setCompareLoading(true);
    setCompareError(null);
    api.topologySnapshotCompare(networkId).then(
      (data) => {
        if (cancelled) return;
        setCompareData(data);
        setCompareLoading(false);
      },
      (err: unknown) => {
        if (cancelled) return;
        setCompareError(err instanceof Error ? err.message : "Snapshot comparison failed to load.");
        setCompareLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [compareOpen, compareData, networkId]);

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
  const hasLastKnownLinks = useMemo(
    () => edges.some((edge) => edge.evidence_class === "last_known_link"),
    [edges],
  );

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

  // Investigation focus and compare focus share one visual mechanism.
  // They are mutually exclusive (activating one clears the other), so the
  // two focus sources can never fight.
  const visualFocus: InvestigationFocus | null = useMemo(() => {
    if (activeInvestigation) {
      return {
        deviceIds: new Set(activeInvestigation.device_ieees),
        edgeIds: new Set(activeInvestigation.edge_ids),
      };
    }
    if (activeCompareChange) {
      return {
        deviceIds: new Set(activeCompareChange.focus_device_ieees),
        edgeIds: new Set(activeCompareChange.focus_edge_ids),
      };
    }
    return null;
  }, [activeInvestigation, activeCompareChange]);

  // A focused investigation's / compare change's edges are drawn even when
  // they would normally sit outside the focused-view budget. Connection
  // controls are untouched, and layout does not depend on visible edges, so
  // nothing moves.
  const renderedEdges = useMemo(() => {
    if (!visualFocus) return visibleEdges;
    const present = new Set(visibleEdges.map((edge) => edge.id));
    const extras = edges.filter(
      (edge) => !present.has(edge.id) && visualFocus.edgeIds.has(edge.id),
    );
    return extras.length ? [...visibleEdges, ...extras] : visibleEdges;
  }, [visibleEdges, edges, visualFocus]);

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

  // Selecting a searched device reuses the existing selected-device
  // behaviour (highlight, evidence neighbourhood, device details panel).
  // Search never moves nodes, never recomputes layout and never touches the
  // saved connection choices. Investigation and compare focus are cleared so
  // the focus mechanisms cannot fight.
  const selectSearchedDevice = (device: MeshEvidenceDevice) => {
    setActiveInvestigation(null);
    setActiveCompareChange(null);
    onSelectNode(device);
  };

  const focusInvestigation = (card: InvestigationCard) => {
    setActiveCompareChange(null);
    setActiveInvestigation(card);
  };

  // Selecting a compare change focuses the involved devices, ensures the
  // involved evidence edges are drawn, and opens the relevant details panel
  // where the evidence exists in the current model. Layout, manual positions
  // and connection controls are untouched.
  const selectCompareChange = (change: SnapshotCompareChange) => {
    setActiveInvestigation(null);
    setActiveCompareChange(change);
    const focusEdge = edges.find((edge) => change.focus_edge_ids.includes(edge.id));
    if (focusEdge) {
      onSelectEdge(focusEdge);
      return;
    }
    const focusDevice = devices.find((device) =>
      change.device_ieees.includes(device.ieee_address),
    );
    if (focusDevice) {
      onSelectNode(focusDevice);
      return;
    }
    onClearSelection();
  };

  const clearCompare = () => {
    setCompareOpen(false);
    setActiveCompareChange(null);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <DeviceSearch
            devices={devices}
            edges={edges}
            onSelectDevice={selectSearchedDevice}
          />
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
          <button
            type="button"
            aria-label={COMPARE_BUTTON_LABEL}
            aria-pressed={compareOpen}
            onClick={() => (compareOpen ? clearCompare() : setCompareOpen(true))}
            className={`rounded-lg border px-3 py-1.5 text-sm hover:border-zl-accent/40 ${
              compareOpen
                ? "border-zl-accent bg-zl-accent/10 text-zl-accent"
                : "border-zl-border bg-zl-surface-2 text-zl-text"
            }`}
          >
            {COMPARE_BUTTON_LABEL}
          </button>
          <EvidenceReportMenu
            buildReport={() =>
              buildMeshEvidenceReport({
                networkId,
                networkName,
                latestSnapshotCapturedAt,
                generatedAt: new Date(),
                devices,
                edges,
                investigations,
                // Compare data is included only while the compare panel is
                // open, matching what the user can currently see.
                compare: compareOpen ? compareData : null,
                selectedDevice: selectedNodeId
                  ? (devices.find((device) => device.ieee_address === selectedNodeId) ??
                    null)
                  : null,
              })
            }
          />
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
            visibleEdges={renderedEdges}
            allEdges={edges}
            signatureSeed={signatureSeed}
            layoutMode={layoutMode}
            positionStorageId={positionStorageId}
            resetNonce={resetNonce}
            selectedNodeId={selectedNodeId}
            investigationFocus={visualFocus}
            onSelectEdge={onSelectEdge}
            onSelectNode={onSelectNode}
            onClearSelection={onClearSelection}
          />
        </div>
      </Card>

      <div className="space-y-4">
        {compareOpen && (
          <Card>
            <SnapshotComparePanel
              compare={compareData}
              loading={compareLoading}
              error={compareError}
              activeChangeId={activeCompareChange?.id ?? null}
              onSelectChange={selectCompareChange}
              onClearCompare={clearCompare}
            />
          </Card>
        )}
        <Card>
          <InvestigationPanel
            investigations={investigations}
            activeInvestigationId={activeInvestigation?.id ?? null}
            onFocus={focusInvestigation}
            onClearFocus={() => setActiveInvestigation(null)}
          />
        </Card>
        <Card>
          <GraphLegend
            hasPassiveHints={hasPassiveHints}
            hasLastKnownLinks={hasLastKnownLinks}
          />
        </Card>
        <Card>
          <div role="group" aria-label={CONNECTIONS_GROUP_LABEL} className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-zl-muted">
              {CONNECTIONS_GROUP_LABEL}
            </h3>
            <ConnectionsExplainer />
            <ConnectionCheckbox
              label={CONNECTION_CONTROL_COPY.routeHints.label}
              helper={hasRouteHints ? undefined : CONNECTION_CONTROL_COPY.routeHints.empty}
              checked={hasRouteHints && controls.routeHints}
              disabled={!hasRouteHints}
              onChange={setControl("routeHints")}
            />
            <ConnectionCheckbox
              label={CONNECTION_CONTROL_COPY.bestNeighbourLinks.label}
              checked={controls.bestNeighbourLinks}
              onChange={setControl("bestNeighbourLinks")}
            />
            <ConnectionCheckbox
              label={CONNECTION_CONTROL_COPY.allNeighbourLinks.label}
              checked={controls.allNeighbourLinks}
              onChange={setControl("allNeighbourLinks")}
            />
            <ConnectionCheckbox
              label={CONNECTION_CONTROL_COPY.oldUncertainLinks.label}
              helper={
                hasOldUncertainLinks ? undefined : CONNECTION_CONTROL_COPY.oldUncertainLinks.empty
              }
              checked={hasOldUncertainLinks && controls.oldUncertainLinks}
              disabled={!hasOldUncertainLinks}
              onChange={setControl("oldUncertainLinks")}
            />
            <ConnectionCheckbox
              label={CONNECTION_CONTROL_COPY.recentMissingLinks.label}
              helper={
                hasRecentMissingLinks
                  ? undefined
                  : CONNECTION_CONTROL_COPY.recentMissingLinks.empty
              }
              checked={hasRecentMissingLinks && controls.recentMissingLinks}
              disabled={!hasRecentMissingLinks}
              onChange={setControl("recentMissingLinks")}
            />
            <ConnectionCheckbox
              label={CONNECTION_CONTROL_COPY.lastKnownLinks.label}
              helper={hasLastKnownLinks ? undefined : CONNECTION_CONTROL_COPY.lastKnownLinks.empty}
              checked={hasLastKnownLinks && controls.lastKnownLinks}
              disabled={!hasLastKnownLinks}
              onChange={setControl("lastKnownLinks")}
            />
            <ConnectionCheckbox
              label={CONNECTION_CONTROL_COPY.suggestedInvestigationLinks.label}
              helper={
                hasPassiveHints
                  ? undefined
                  : CONNECTION_CONTROL_COPY.suggestedInvestigationLinks.empty
              }
              checked={hasPassiveHints && controls.suggestedInvestigationLinks}
              disabled={!hasPassiveHints}
              onChange={setControl("suggestedInvestigationLinks")}
            />
            <p className="text-[11px] leading-snug text-zl-muted">{CONNECTIONS_FOOTNOTE}</p>
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
  const clearSelection = () => {
    setSelectedEdge(null);
    setSelectedDevice(null);
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
                  description="Links seen in recent previous snapshots but not present in the latest usable snapshot."
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
              investigations={detail.data?.investigations ?? []}
              signatureSeed={liveSignatureSeed}
              networkId={networkId ?? "unknown-network"}
              networkName={detail.data?.network_name ?? null}
              latestSnapshotCapturedAt={snapshot.captured_at ?? null}
              positionStorageId={networkId ?? "unknown-network"}
              onSelectEdge={selectEdge}
              onSelectNode={selectNode}
              onClearSelection={clearSelection}
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
