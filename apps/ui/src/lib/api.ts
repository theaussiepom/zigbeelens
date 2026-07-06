import type {
  DashboardPayload,
  DeviceDetail,
  DeviceSummary,
  HealthResponse,
  Incident,
  MockScenarioId,
  NetworkSummary,
  ReportDetail,
  ReportRequest,
  ReportSummary,
  RouterRisk,
  TimelineEvent,
  ZigbeeLensConfigStatus,
} from "@zigbeelens/shared";
import { resolveApiBase } from "@/lib/base";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function buildUrl(path: string, params: Record<string, string | undefined>): string {
  const normalized = path.startsWith("/") ? path.slice(1) : path;
  const url = new URL(normalized, resolveApiBase());
  for (const [key, value] of Object.entries(params)) {
    if (value) url.searchParams.set(key, value);
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
  params: Record<string, string | undefined> = {},
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
  params: Record<string, string | undefined> = {},
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

export interface Paginated<T> {
  items: T[];
  total: number;
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
  routers: (scenario?: string) => fetchJson<Paginated<RouterRisk>>("api/routers", { scenario }),
  incidents: (scenario?: string) =>
    fetchJson<Paginated<Incident>>("api/incidents", { scenario }),
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

export interface TopologyOverview {
  enabled: boolean;
  manual_capture_enabled: boolean;
  automatic_capture_enabled: boolean;
  capture_in_progress: boolean;
  last_capture_error?: string | null;
  networks: Array<{
    network_id: string;
    network_name: string;
    latest_snapshot?: {
      snapshot_id: string;
      captured_at: string;
      router_count: number;
      link_count: number;
      end_device_count: number;
    } | null;
  }>;
}

export interface TopologySnapshotSummary {
  snapshot_id: string;
  network_id: string;
  captured_at?: string | null;
  requested_by?: string | null;
  status?: string | null;
  router_count?: number | null;
  end_device_count?: number | null;
  link_count?: number | null;
  error?: string | null;
}

export interface TopologyNodeRow {
  ieee_address: string;
  friendly_name?: string | null;
  node_type?: string | null;
  depth?: number | null;
  lqi?: number | null;
}

export interface TopologyLinkRow {
  source_ieee: string;
  target_ieee: string;
  source_type?: string | null;
  target_type?: string | null;
  linkquality?: number | null;
  depth?: number | null;
  relationship?: string | null;
  /**
   * Route-table entries reported on this link by the raw network map.
   * null means routes were not reported (unknown), distinct from zero.
   */
  route_count?: number | null;
}

export interface TopologyInventoryCounts {
  device_count: number;
  router_count: number;
  end_device_count: number;
}

export interface TopologyNetworkDetail {
  network_id: string;
  network_name: string;
  latest_snapshot?: TopologySnapshotSummary | null;
  nodes: TopologyNodeRow[];
  links: TopologyLinkRow[];
  inventory?: TopologyInventoryCounts | null;
  layout_available?: boolean;
}

export type { MockScenarioId };
