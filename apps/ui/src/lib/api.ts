import type {
  BrowserSessionStatus,
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
import { authRuntime, CSRF_HEADER_NAME } from "@/lib/authRuntime";
import { parseBrowserSessionStatus } from "@/lib/sessionStatus";
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

export type ApiErrorKind =
  | "authentication"
  | "csrf"
  | "origin"
  | "session_unavailable"
  | "unreachable"
  | "generic";

const AUTH_DETAIL = "Authentication required.";
const CSRF_DETAIL = "CSRF validation failed.";
const ORIGIN_DETAIL = "Browser origin validation failed.";

export class ApiError extends Error {
  status: number;
  detail: string | null;
  kind: ApiErrorKind;

  constructor(
    message: string,
    status: number,
    opts: { detail?: string | null; kind?: ApiErrorKind } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = opts.detail ?? null;
    this.kind = opts.kind ?? classifyError(status, opts.detail ?? null);
  }
}

function classifyError(status: number, detail: string | null): ApiErrorKind {
  if (status === 0) return "unreachable";
  if (status === 401) return "authentication";
  if (status === 409) return "session_unavailable";
  if (status === 403) {
    if (detail === CSRF_DETAIL) return "csrf";
    if (detail === ORIGIN_DETAIL) return "origin";
  }
  return "generic";
}

function messageFor(status: number, detail: string | null, kind: ApiErrorKind): string {
  switch (kind) {
    case "authentication":
      return "Authentication required.";
    case "csrf":
      return "Session security check failed. Retry the action.";
    case "origin":
      return "Browser origin was rejected. Check cors_allowed_origins and how the UI is served.";
    case "session_unavailable":
      return "Browser sessions are not configured.";
    case "unreachable":
      return "ZigbeeLens Core is not reachable.";
    default:
      if (detail && detail.length < 200) return detail;
      return `ZigbeeLens Core returned an error (${status}).`;
  }
}

async function readErrorDetail(res: Response): Promise<string | null> {
  try {
    const contentType = res.headers.get("content-type") ?? "";
    if (!contentType.includes("application/json")) return null;
    const body: unknown = await res.json();
    if (
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      typeof (body as { detail: unknown }).detail === "string"
    ) {
      const detail = (body as { detail: string }).detail.trim();
      if (detail.length > 0 && detail.length < 200) return detail;
    }
  } catch {
    // ignore non-JSON error bodies
  }
  return null;
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
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export type CoreFetchOptions = {
  /** Transient bearer for session bootstrap only. */
  bearer?: string;
  /** Skip CSRF (session bootstrap). */
  skipCsrf?: boolean;
  /** Public session status probe — never triggers protected 401 handling. */
  isSessionStatus?: boolean;
  /** Expect no JSON body (e.g. 204). */
  allowEmpty?: boolean;
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isUnsafeMethod(method: string): boolean {
  return UNSAFE_METHODS.has(method.toUpperCase());
}

function isIdempotentRequest(init?: RequestInit): boolean {
  const method = (init?.method ?? "GET").toUpperCase();
  return method === "GET" || method === "HEAD";
}

function mergeHeaders(init?: RequestInit): Headers {
  return new Headers(init?.headers);
}

/**
 * Central credential-aware Core fetch. Every request uses credentials: "include".
 */
export async function coreFetch(
  path: string,
  params: Record<string, QueryParamValue> = {},
  init?: RequestInit,
  options: CoreFetchOptions = {},
): Promise<Response> {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers = mergeHeaders(init);
  const epochAtStart = authRuntime.getEpoch();

  if (options.bearer) {
    headers.set("Authorization", `Bearer ${options.bearer}`);
  }

  if (isUnsafeMethod(method) && !options.skipCsrf && !options.bearer) {
    if (authRuntime.isSessionAuth()) {
      const csrf = authRuntime.getCsrfToken();
      if (!csrf) {
        authRuntime.notifyRevalidate();
        throw new ApiError("Session security token is missing. Retry the action.", 403, {
          kind: "csrf",
          detail: CSRF_DETAIL,
        });
      }
      headers.set(CSRF_HEADER_NAME, csrf);
    }
  }

  const isAuthSessionPath = path.replace(/^\//, "").startsWith("api/auth/session");
  const requestInit: RequestInit = {
    ...init,
    method,
    headers,
    credentials: "include",
    cache: options.isSessionStatus || isAuthSessionPath ? "no-store" : init?.cache,
  };

  let res: Response;
  try {
    res = await fetch(buildUrl(path, params), requestInit);
  } catch {
    throw new ApiError("ZigbeeLens Core is not reachable.", 0, { kind: "unreachable" });
  }

  if (epochAtStart !== authRuntime.getEpoch()) {
    throw new ApiError("Authentication context changed.", 401, {
      kind: "authentication",
      detail: AUTH_DETAIL,
    });
  }

  if (!res.ok) {
    const detail = await readErrorDetail(res);
    const kind = classifyError(res.status, detail);
    if (
      res.status === 401 &&
      !options.isSessionStatus &&
      !isAuthSessionPath
    ) {
      authRuntime.notifyUnauthorized();
    }
    if (res.status === 403 && kind === "csrf" && !options.isSessionStatus) {
      authRuntime.notifyRevalidate();
    }
    throw new ApiError(messageFor(res.status, detail, kind), res.status, { detail, kind });
  }

  return res;
}

async function parseJsonBody<T>(res: Response, allowEmpty: boolean): Promise<T> {
  if (res.status === 204 || allowEmpty) {
    const text = await res.text();
    if (!text) return undefined as T;
    try {
      return JSON.parse(text) as T;
    } catch {
      throw new ApiError("ZigbeeLens received an unexpected response.", res.status);
    }
  }
  try {
    return (await res.json()) as T;
  } catch {
    throw new ApiError("ZigbeeLens received an unexpected response.", res.status);
  }
}

async function fetchJsonOnce<T>(
  path: string,
  params: Record<string, QueryParamValue> = {},
  init?: RequestInit,
  options: CoreFetchOptions = {},
): Promise<T> {
  const res = await coreFetch(path, params, init, options);
  return parseJsonBody<T>(res, Boolean(options.allowEmpty));
}

async function fetchJson<T>(
  path: string,
  params: Record<string, QueryParamValue> = {},
  init?: RequestInit,
  options: CoreFetchOptions = {},
): Promise<T> {
  const retryable = isIdempotentRequest(init) && !options.isSessionStatus;
  let lastError: ApiError | null = null;
  for (let attempt = 0; attempt <= MAX_FETCH_RETRIES; attempt += 1) {
    try {
      return await fetchJsonOnce<T>(path, params, init, options);
    } catch (error) {
      if (
        retryable &&
        error instanceof ApiError &&
        RETRYABLE_STATUSES.has(error.status) &&
        error.kind !== "authentication" &&
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

/** @deprecated Prefer downloadStoredReport — kept for URL construction helpers/tests. */
export const downloadReportUrl = (id: string, scenario?: string) =>
  buildUrl(`api/reports/${id}/download`, { scenario });

const FALLBACK_REPORT_FILENAME = "zigbeelens-report.json";
const MAX_FILENAME_LENGTH = 180;

export function sanitizeDownloadFilename(raw: string | null | undefined): string {
  if (!raw) return FALLBACK_REPORT_FILENAME;
  let name = raw.trim();
  try {
    name = decodeURIComponent(name);
  } catch {
    // keep raw
  }
  name = name.replace(/\\/g, "/");
  const slash = name.lastIndexOf("/");
  if (slash >= 0) name = name.slice(slash + 1);
  name = name.replace(/[\u0000-\u001f\u007f]/g, "").replace(/[/\\]/g, "");
  if (!name || name === "." || name === "..") return FALLBACK_REPORT_FILENAME;
  if (name.length > MAX_FILENAME_LENGTH) name = name.slice(0, MAX_FILENAME_LENGTH);
  return name;
}

export function parseContentDispositionFilename(header: string | null): string | null {
  if (!header) return null;
  const star = /filename\*\s*=\s*(?:UTF-8''|utf-8'')([^;]+)/i.exec(header);
  if (star?.[1]) {
    return sanitizeDownloadFilename(star[1].trim().replace(/^"|"$/g, ""));
  }
  const plain = /filename\s*=\s*("?)([^";]+)\1/i.exec(header);
  if (plain?.[2]) {
    return sanitizeDownloadFilename(plain[2].trim());
  }
  return null;
}

export type StoredReportDownload = {
  blob: Blob;
  filename: string;
  contentType: string;
};

export async function downloadStoredReport(
  id: string,
  scenario?: string,
): Promise<StoredReportDownload> {
  const res = await coreFetch(`api/reports/${id}/download`, { scenario });
  const contentType = res.headers.get("content-type") ?? "application/octet-stream";
  const blob = await res.blob();
  // Refuse to save a typical FastAPI error JSON envelope as a report file.
  if (contentType.includes("application/json") && blob.size < 4096) {
    try {
      const text = await blob.text();
      const parsed: unknown = JSON.parse(text);
      if (
        typeof parsed === "object" &&
        parsed !== null &&
        "detail" in parsed &&
        !("generated_at" in parsed) &&
        !("summary" in parsed)
      ) {
        throw new ApiError("Report download failed.", res.status, { kind: "generic" });
      }
      // Re-wrap text as blob when it was a real report JSON.
      const reportBlob = new Blob([text], { type: contentType });
      const filename =
        parseContentDispositionFilename(res.headers.get("Content-Disposition")) ??
        FALLBACK_REPORT_FILENAME;
      return { blob: reportBlob, filename, contentType };
    } catch (e) {
      if (e instanceof ApiError) throw e;
    }
  }
  const filename =
    parseContentDispositionFilename(res.headers.get("Content-Disposition")) ??
    FALLBACK_REPORT_FILENAME;
  return { blob, filename, contentType };
}

export async function triggerBrowserDownload(download: StoredReportDownload): Promise<void> {
  const objectUrl = URL.createObjectURL(download.blob);
  try {
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = download.filename;
    anchor.rel = "noopener";
    anchor.style.display = "none";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

/** Public session status — never sends Authorization. */
export async function fetchSessionStatus(): Promise<BrowserSessionStatus> {
  const raw = await fetchJson<unknown>("api/auth/session", {}, undefined, {
    isSessionStatus: true,
  });
  const parsed = parseBrowserSessionStatus(raw);
  if (!parsed.ok) {
    throw new ApiError("Browser session status was malformed.", 0, {
      kind: "generic",
      detail: parsed.reason,
    });
  }
  return parsed.status;
}

/** Bootstrap browser session with a one-shot bearer token. */
export async function createBrowserSession(apiToken: string): Promise<BrowserSessionStatus> {
  const raw = await fetchJson<unknown>(
    "api/auth/session",
    {},
    { method: "POST" },
    { bearer: apiToken, skipCsrf: true, isSessionStatus: true },
  );
  const parsed = parseBrowserSessionStatus(raw);
  if (!parsed.ok) {
    throw new ApiError("Browser session bootstrap response was malformed.", 0, {
      kind: "generic",
    });
  }
  return parsed.status;
}

/** End the browser session (session auth + CSRF). */
export async function deleteBrowserSession(): Promise<void> {
  await fetchJson<void>(
    "api/auth/session",
    {},
    { method: "DELETE" },
    { allowEmpty: true, isSessionStatus: true },
  );
}

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
  downloadStoredReport,
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

/** Test helper: every unsafe api method must go through coreFetch mutation path. */
export const __unsafeApiMethodsForTests = [
  "createReport",
  "deleteReport",
  "captureTopology",
] as const;
