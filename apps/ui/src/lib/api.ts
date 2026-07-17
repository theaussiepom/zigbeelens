import type {
  DashboardPayload,
  DeviceDetail,
  DeviceSummary,
  HealthResponse,
  IncidentCollectionQuery,
  MockScenarioId,
  NetworkSummary,
  RouterRisk,
  TimelineEvent,
  ZigbeeLensConfigStatus,
} from "@zigbeelens/shared";

export type IncidentListQuery = IncidentCollectionQuery;
import { resolveApiBase } from "@/lib/base";
import type { Paginated } from "@/types/api";
import type {
  DeviceSnapshotHistoryDetail,
  DeviceStoryDto,
} from "@/types/devices";
import type { DataCoverageDto } from "@/types/decisions";
import type { Incident } from "@/types/incidents";
import type { ReportDetail, ReportRequest, ReportSummary } from "@/types/reports";
import type {
  SnapshotCompareDetail,
  TopologyEvidenceGraphDetail,
  TopologyNetworkDetail,
  TopologyOverview,
} from "@/types/topology";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type QueryParamValue = string | number | undefined | null | ReadonlyArray<string | number>;

function buildUrl(path: string, params: Record<string, QueryParamValue> = {}): string {
  const normalized = path.startsWith("/") ? path.slice(1) : path;
  const url = new URL(normalized, resolveApiBase());
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const entry of value) {
        if (entry === undefined || entry === null || entry === "") continue;
        url.searchParams.append(key, String(entry));
      }
      continue;
    }
    url.searchParams.set(key, String(value));
  }
  return url.toString();
}

const RETRYABLE_STATUSES = new Set([0, 408, 429, 500, 502, 503, 504]);
const MAX_FETCH_RETRIES = 3;
const RETRY_BASE_MS = 400;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchJsonOnce<T>(
  path: string,
  params: Record<string, QueryParamValue> = {},
  init?: RequestInit,
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(buildUrl(path, params), init);
  } catch {
    throw new ApiError("ZigbeeLens Core is not reachable.", 0);
  }
  if (!res.ok) {
    throw new ApiError(`ZigbeeLens Core returned an error (${res.status}).`, res.status);
  }
  try {
    return (await res.json()) as T;
  } catch {
    throw new ApiError("ZigbeeLens received an unexpected response.", res.status);
  }
}

function isIdempotentRequest(init?: RequestInit): boolean {
  const method = (init?.method ?? "GET").toUpperCase();
  return method === "GET" || method === "HEAD";
}

async function fetchJson<T>(
  path: string,
  params: Record<string, QueryParamValue> = {},
  init?: RequestInit,
): Promise<T> {
  const retryable = isIdempotentRequest(init);
  let lastError: ApiError | null = null;
  for (let attempt = 0; attempt <= MAX_FETCH_RETRIES; attempt += 1) {
    try {
      return await fetchJsonOnce<T>(path, params, init);
    } catch (error) {
      if (
        retryable &&
        error instanceof ApiError &&
        RETRYABLE_STATUSES.has(error.status) &&
        attempt < MAX_FETCH_RETRIES
      ) {
        lastError = error;
        await sleep(RETRY_BASE_MS * (attempt + 1));
        continue;
      }
      throw error;
    }
  }
  throw lastError ?? new ApiError("ZigbeeLens Core returned an error.", 500);
}

export const eventStreamUrl = () => buildUrl("api/events/stream", {});

function boolParam(value?: boolean | null): string | undefined {
  if (value === null || value === undefined) return undefined;
  return value ? "true" : "false";
}

function reportParams(
  request: ReportRequest,
  scenario?: string,
): Record<string, string | undefined> {
  const r = request.redaction;
  return {
    scenario,
    scope: request.scope,
    format: request.format,
    profile: r.profile,
    network_id: request.network_id ?? undefined,
    incident_id: request.incident_id ?? undefined,
    device: request.device ?? undefined,
    preserve_friendly_names: boolParam(r.preserve_friendly_names),
    hash_ieee_addresses: boolParam(r.hash_ieee_addresses),
    redact_hostnames: boolParam(r.redact_hostnames),
    redact_ip_addresses: boolParam(r.redact_ip_addresses),
    redact_network_names: boolParam(r.redact_network_names),
    include_timeline: boolParam(r.include_timeline),
    include_raw_payloads: boolParam(r.include_raw_payloads),
  };
}

export const downloadReportUrl = (id: string, scenario?: string) =>
  buildUrl(`api/reports/${id}/download`, { scenario });

export const api = {
  health: () => fetchJson<HealthResponse>("api/health"),
  configStatus: (scenario?: string) =>
    fetchJson<ZigbeeLensConfigStatus>("api/config/status", { scenario }),
  scenarios: () => fetchJson<Array<{ id: string; label: string }>>("api/scenarios"),
  dashboard: (scenario?: string) => fetchJson<DashboardPayload>("api/dashboard", { scenario }),
  networks: (scenario?: string) =>
    fetchJson<Paginated<NetworkSummary>>("api/networks", { scenario }),
  network: (id: string, scenario?: string) =>
    fetchJson<NetworkSummary>(`api/networks/${id}`, { scenario }),
  devices: (scenario?: string, networkId?: string) =>
    fetchJson<Paginated<DeviceSummary>>("api/devices", { scenario, network_id: networkId }),
  device: (networkId: string, ieee: string, scenario?: string) =>
    fetchJson<DeviceDetail>(`api/devices/${networkId}/${encodeURIComponent(ieee)}`, { scenario }),
  deviceStory: (
    networkId: string,
    ieee: string,
    scenario?: string,
  ) =>
    fetchJson<DeviceStoryDto>(
      `api/devices/${encodeURIComponent(networkId)}/${encodeURIComponent(ieee)}/story`,
      { scenario },
    ),
  deviceCoverage: (networkId: string, ieee: string) =>
    fetchJson<DataCoverageDto[]>(
      `api/devices/${encodeURIComponent(networkId)}/${encodeURIComponent(ieee)}/coverage`,
    ),
  routers: (scenario?: string) => fetchJson<Paginated<RouterRisk>>("api/routers", { scenario }),
  incidents: (query: IncidentListQuery = {}) =>
    fetchJson<Paginated<Incident>>("api/incidents", {
      scenario: query.scenario,
      status: query.status,
      updated_after: query.updated_after,
      network_id: query.network_id,
      device_ieee: query.device_ieee,
      limit: query.limit,
      cursor: query.cursor,
    }),
  incident: (id: string, scenario?: string) =>
    fetchJson<Incident>(`api/incidents/${id}`, { scenario }),
  timeline: (scenario?: string, networkId?: string) =>
    fetchJson<Paginated<TimelineEvent>>("api/timeline", { scenario, network_id: networkId }),
  previewReport: (request: ReportRequest, scenario?: string) =>
    fetchJson<ReportDetail>("api/reports/preview", reportParams(request, scenario)),
  createReport: (request: ReportRequest, scenario?: string) =>
    fetchJson<ReportSummary>(
      "api/reports",
      { scenario },
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      },
    ),
  listReports: () => fetchJson<ReportSummary[]>("api/reports"),
  report: (id: string, scenario?: string) =>
    fetchJson<ReportDetail>(`api/reports/${id}`, { scenario }),
  deleteReport: (id: string) =>
    fetchJson<{ deleted: boolean }>(`api/reports/${id}`, {}, { method: "DELETE" }),
  topology: () => fetchJson<TopologyOverview>("api/topology"),
  topologyNetwork: (networkId: string) =>
    fetchJson<TopologyNetworkDetail>(`api/topology/${encodeURIComponent(networkId)}`),
  topologyEvidenceGraph: (networkId: string) =>
    fetchJson<TopologyEvidenceGraphDetail>(
      `api/topology/${encodeURIComponent(networkId)}/evidence-graph`,
    ),
  /** Advanced/debug whole-network snapshot compare — not a primary workflow. */
  topologySnapshotCompare: (networkId: string) =>
    fetchJson<SnapshotCompareDetail>(
      `api/topology/${encodeURIComponent(networkId)}/snapshots/compare`,
    ),
  topologyDeviceSnapshotHistory: (networkId: string, ieeeAddress: string) =>
    fetchJson<DeviceSnapshotHistoryDetail>(
      `api/topology/${encodeURIComponent(networkId)}/devices/${encodeURIComponent(
        ieeeAddress,
      )}/snapshot-history`,
    ),
  captureTopology: (networkId: string) =>
    fetchJson<{ snapshot_id: string; status: string }>(
      `api/topology/${networkId}/capture`,
      {},
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmed: true, reason: "manual_user_capture" }),
      },
    ),
};

export type { Paginated } from "@/types/api";
export type {
  AvailabilityCoverageStatus,
  DeviceDiagnosticStats,
  DeviceSnapshotCompareStatus,
  DeviceSnapshotCompareCounts,
  DeviceSnapshotComparison,
  DeviceSnapshotHistoryDetail,
  DeviceSnapshotHistoryRow,
  DeviceStatsWindow,
  DeviceStoryDto,
  DeviceStoryTimelineItemDto,
} from "@/types/devices";
export type { Incident } from "@/types/incidents";
export type { ReportDetail, ReportRequest, ReportSummary } from "@/types/reports";
export type {
  HistoricalEdgeAggregate,
  InvestigationCard,
  InvestigationCounts,
  LastKnownLinkAggregate,
  LastKnownLinkWindow,
  PassiveHintAggregate,
  PassiveHintWindow,
  SnapshotCompareChange,
  SnapshotCompareChangeType,
  SnapshotCompareChurn,
  SnapshotCompareCounts,
  SnapshotCompareDetail,
  SnapshotCompareSnapshot,
  TopologyEvidenceGraphCounts,
  TopologyEvidenceGraphDetail,
  TopologyHistoryWindow,
  TopologyInventoryCounts,
  TopologyLinkRow,
  TopologyNetworkDetail,
  TopologyNodeRow,
  TopologyOverview,
  TopologySnapshotSummary,
} from "@/types/topology";
export type { MockScenarioId };
