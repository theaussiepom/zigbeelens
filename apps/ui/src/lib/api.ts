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
  StorageStatus,
  TimelineEvent,
  ZigbeeLensConfigStatus,
} from "@zigbeelens/shared";

export type IncidentListQuery = IncidentCollectionQuery;
import { resolveApiBase } from "@/lib/base";
import { authRuntime } from "@/lib/authRuntime";
import { parseBrowserSessionStatus } from "@/lib/sessionStatus";
import {
  startCredentialedFetch,
  type RequestIntent,
} from "@/lib/sessionTransport";
import type { Paginated } from "@/types/api";
import type {
  DeviceSnapshotHistoryDetail,
  DeviceStoryDto,
} from "@/types/devices";
import type { DataCoverageDto } from "@/types/decisions";
import type { Incident } from "@/types/incidents";
import type {
  ReportDetailV3,
  ReportRequest,
  ReportSummary,
  StoredReport,
} from "@/types/reports";
import type {
  SnapshotCompareDetail,
  TopologyEvidenceGraphDetail,
  TopologyNetworkDetail,
  TopologyOverview,
} from "@/types/topology";
import {
  parseDeviceDetail,
  parseIncident,
  parseNetworkSummary,
  parseStoredReport,
  validateDashboardPayload,
  validateDeviceSummaries,
  validateIncidents,
  validateNetworkSummaries,
  validateReportDetailV3,
} from "@/lib/decisionContract";

export type { RequestIntent };

export type ApiErrorKind =
  | "authentication"
  | "csrf"
  | "origin"
  | "session_unavailable"
  | "unreachable"
  | "stale_auth_context"
  | "protocol"
  | "generic";

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
    case "stale_auth_context":
      return "Authentication context changed.";
    case "protocol":
      return "Unexpected session response from Core.";
    default:
      if (detail && detail.length < 200) return detail;
      return `ZigbeeLens Core returned an error (${status}).`;
  }
}

function staleAuthError(): ApiError {
  return new ApiError("Authentication context changed.", 0, {
    kind: "stale_auth_context",
    detail: null,
  });
}

function assertAccessGeneration(start: number): void {
  if (start !== authRuntime.getAccessGeneration()) {
    throw staleAuthError();
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

export type CoreFetchOptions = {
  intent?: RequestIntent;
  /** Transient bearer for session bootstrap only — released inside transport before await. */
  bearer?: string;
  /** Expect no JSON body (e.g. 204). */
  allowEmpty?: boolean;
  /**
   * Access generation captured by the outermost logical operation.
   * Retries and nested body parsing must reuse this value — never recapture.
   */
  accessGeneration?: number;
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isIdempotentRequest(init?: RequestInit): boolean {
  const method = (init?.method ?? "GET").toUpperCase();
  return method === "GET" || method === "HEAD";
}

function resolveIntent(options: CoreFetchOptions): RequestIntent {
  if (options.intent) return options.intent;
  return "protected";
}

/**
 * Central credential-aware Core fetch. Every request uses credentials: "include".
 * CSRF is applied only inside sessionTransport.startCredentialedFetch.
 */
export async function coreFetch(
  path: string,
  params: Record<string, QueryParamValue> = {},
  init?: RequestInit,
  options: CoreFetchOptions = {},
): Promise<Response> {
  const method = (init?.method ?? "GET").toUpperCase();
  const intent = resolveIntent(options);
  const accessGenerationAtStart =
    options.accessGeneration ?? authRuntime.getAccessGeneration();
  const checkGeneration = intent === "protected" || intent === "session_logout";

  if (checkGeneration) {
    assertAccessGeneration(accessGenerationAtStart);
  }

  const started = startCredentialedFetch(buildUrl(path, params), {
    intent,
    bearer: options.bearer,
    method,
    headers: init?.headers,
    body: init?.body ?? null,
    cache: init?.cache,
  });
  // Release any remaining bearer reference on the options bag.
  options.bearer = undefined;

  if (!started.ok) {
    if (started.reason === "protocol") {
      throw new ApiError("Unexpected session credential encoding.", 0, {
        kind: "protocol",
        detail: "malformed",
      });
    }
    authRuntime.notifyRevalidate();
    throw new ApiError("Session security token is missing. Retry the action.", 403, {
      kind: "csrf",
      detail: CSRF_DETAIL,
    });
  }

  let res: Response;
  try {
    res = await started.promise;
  } catch {
    throw new ApiError("ZigbeeLens Core is not reachable.", 0, { kind: "unreachable" });
  }

  if (checkGeneration) {
    assertAccessGeneration(accessGenerationAtStart);
  }

  if (!res.ok) {
    const detail = await readErrorDetail(res);
    if (checkGeneration) {
      assertAccessGeneration(accessGenerationAtStart);
    }
    const kind = classifyError(res.status, detail);
    if (res.status === 401 && intent === "protected") {
      if (accessGenerationAtStart === authRuntime.getAccessGeneration()) {
        authRuntime.notifyUnauthorized();
      }
    }
    // session_logout CSRF is owned by BrowserAuthProvider (refresh after ownership release).
    if (res.status === 403 && kind === "csrf" && intent === "protected") {
      if (accessGenerationAtStart === authRuntime.getAccessGeneration()) {
        authRuntime.notifyRevalidate();
      }
    }
    throw new ApiError(messageFor(res.status, detail, kind), res.status, { detail, kind });
  }

  return res;
}

async function parseJsonBody<T>(
  res: Response,
  allowEmpty: boolean,
  accessGenerationAtStart: number | null,
): Promise<T> {
  if (res.status === 204 || allowEmpty) {
    const text = await res.text();
    if (accessGenerationAtStart !== null) assertAccessGeneration(accessGenerationAtStart);
    if (!text) return undefined as T;
    try {
      const parsed = JSON.parse(text) as T;
      if (accessGenerationAtStart !== null) assertAccessGeneration(accessGenerationAtStart);
      return parsed;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError("ZigbeeLens received an unexpected response.", res.status);
    }
  }
  try {
    const parsed = (await res.json()) as T;
    if (accessGenerationAtStart !== null) assertAccessGeneration(accessGenerationAtStart);
    return parsed;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError("ZigbeeLens received an unexpected response.", res.status);
  }
}

async function fetchJsonOnce<T>(
  path: string,
  params: Record<string, QueryParamValue> = {},
  init?: RequestInit,
  options: CoreFetchOptions = {},
  accessGenerationAtStart?: number,
): Promise<T> {
  const intent = resolveIntent(options);
  const accessGen = accessGenerationAtStart ?? authRuntime.getAccessGeneration();
  const res = await coreFetch(path, params, init, {
    ...options,
    accessGeneration: accessGen,
  });
  const checkGen =
    intent === "protected" || intent === "session_logout" ? accessGen : null;
  return parseJsonBody<T>(res, Boolean(options.allowEmpty), checkGen);
}

async function fetchJson<T>(
  path: string,
  params: Record<string, QueryParamValue> = {},
  init?: RequestInit,
  options: CoreFetchOptions = {},
): Promise<T> {
  const intent = resolveIntent(options);
  const accessGenerationAtStart = authRuntime.getAccessGeneration();
  const retryable =
    intent === "protected" &&
    isIdempotentRequest(init);
  let lastError: ApiError | null = null;
  for (let attempt = 0; attempt <= MAX_FETCH_RETRIES; attempt += 1) {
    if (retryable || intent === "session_logout") {
      assertAccessGeneration(accessGenerationAtStart);
    }
    try {
      return await fetchJsonOnce<T>(
        path,
        params,
        init,
        options,
        accessGenerationAtStart,
      );
    } catch (error) {
      if (
        retryable &&
        error instanceof ApiError &&
        RETRYABLE_STATUSES.has(error.status) &&
        error.kind !== "authentication" &&
        error.kind !== "stale_auth_context" &&
        attempt < MAX_FETCH_RETRIES
      ) {
        lastError = error;
        await sleep(RETRY_BASE_MS * (attempt + 1));
        assertAccessGeneration(accessGenerationAtStart);
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
  /** Access generation captured when the download began. */
  authGeneration: number;
};

export async function downloadStoredReport(
  id: string,
  scenario?: string,
): Promise<StoredReportDownload> {
  const accessGenerationAtStart = authRuntime.getAccessGeneration();
  const res = await coreFetch(
    `api/reports/${id}/download`,
    { scenario },
    undefined,
    { intent: "protected", accessGeneration: accessGenerationAtStart },
  );
  assertAccessGeneration(accessGenerationAtStart);
  const contentType = res.headers.get("content-type") ?? "application/octet-stream";
  const blob = await res.blob();
  assertAccessGeneration(accessGenerationAtStart);
  // Refuse to save a typical FastAPI error JSON envelope as a report file.
  if (contentType.includes("application/json") && blob.size < 4096) {
    try {
      const text = await blob.text();
      assertAccessGeneration(accessGenerationAtStart);
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
      const reportBlob = new Blob([text], { type: contentType });
      const filename =
        parseContentDispositionFilename(res.headers.get("Content-Disposition")) ??
        FALLBACK_REPORT_FILENAME;
      assertAccessGeneration(accessGenerationAtStart);
      return {
        blob: reportBlob,
        filename,
        contentType,
        authGeneration: accessGenerationAtStart,
      };
    } catch (e) {
      if (e instanceof ApiError) throw e;
    }
  }
  const filename =
    parseContentDispositionFilename(res.headers.get("Content-Disposition")) ??
    FALLBACK_REPORT_FILENAME;
  assertAccessGeneration(accessGenerationAtStart);
  return {
    blob,
    filename,
    contentType,
    authGeneration: accessGenerationAtStart,
  };
}

export async function triggerBrowserDownload(download: StoredReportDownload): Promise<void> {
  assertAccessGeneration(download.authGeneration);
  const objectUrl = URL.createObjectURL(download.blob);
  try {
    assertAccessGeneration(download.authGeneration);
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

/** Clipboard write gated by the access generation of the originating protected work. */
export async function writeProtectedClipboardText(
  text: string,
  accessGeneration: number,
): Promise<void> {
  assertAccessGeneration(accessGeneration);
  await navigator.clipboard.writeText(text);
  assertAccessGeneration(accessGeneration);
}

/** Public session status — never sends Authorization; never rejected for protected generation. */
export async function fetchSessionStatus(): Promise<BrowserSessionStatus> {
  const raw = await fetchJson<unknown>("api/auth/session", {}, undefined, {
    intent: "public_session_status",
  });
  const parsed = parseBrowserSessionStatus(raw);
  if (!parsed.ok) {
    throw new ApiError("Browser session status was malformed.", 0, {
      kind: "protocol",
      detail: parsed.reason,
    });
  }
  return parsed.status;
}

/**
 * Bootstrap browser session with a one-shot bearer token.
 *
 * Constructs the credentialed Request synchronously via the transport layer,
 * then awaits the response. Callers must clear their own token locals after
 * invoking this (the transport releases its bearer copy before returning the promise).
 */
export function createBrowserSession(apiToken: string): Promise<BrowserSessionStatus> {
  // Start fetch synchronously so Authorization is bound into the Request before await.
  let token: string | undefined = apiToken;
  const pending = fetchJsonOnce<unknown>(
    "api/auth/session",
    {},
    { method: "POST" },
    { intent: "session_bootstrap", bearer: token },
  );
  token = undefined;
  return pending.then((raw) => {
    const parsed = parseBrowserSessionStatus(raw);
    if (!parsed.ok) {
      throw new ApiError("Browser session bootstrap response was malformed.", 0, {
        kind: "protocol",
        detail: parsed.reason,
      });
    }
    return parsed.status;
  });
}

/** End the browser session (session auth + CSRF). Provider owns 401 outcome. */
export async function deleteBrowserSession(): Promise<void> {
  await fetchJson<void>(
    "api/auth/session",
    {},
    { method: "DELETE" },
    { allowEmpty: true, intent: "session_logout" },
  );
}

export const api = {
  health: () => fetchJson<HealthResponse>("api/health"),
  configStatus: (scenario?: string) =>
    fetchJson<ZigbeeLensConfigStatus>("api/config/status", { scenario }),
  storageStatus: () => fetchJson<StorageStatus>("api/storage/status"),
  scenarios: () => fetchJson<Array<{ id: string; label: string }>>("api/scenarios"),
  dashboard: (scenario?: string) =>
    fetchJson<DashboardPayload>("api/dashboard", { scenario }).then(validateDashboardPayload),
  networks: (scenario?: string) =>
    fetchJson<Paginated<NetworkSummary>>("api/networks", { scenario }).then((page) => ({
      ...page,
      items: validateNetworkSummaries(page.items),
    })),
  network: (id: string, scenario?: string) =>
    fetchJson<NetworkSummary>(`api/networks/${id}`, { scenario }).then(parseNetworkSummary),
  devices: (scenario?: string, networkId?: string) =>
    fetchJson<Paginated<DeviceSummary>>("api/devices", { scenario, network_id: networkId }).then(
      (page) => ({
        ...page,
        items: validateDeviceSummaries(page.items),
      }),
    ),
  device: (networkId: string, ieee: string, scenario?: string) =>
    fetchJson<DeviceDetail>(`api/devices/${networkId}/${encodeURIComponent(ieee)}`, {
      scenario,
    }).then(parseDeviceDetail),
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
    }).then((page) => ({
      ...page,
      items: validateIncidents(page.items),
    })),
  incident: (id: string, scenario?: string) =>
    fetchJson<Incident>(`api/incidents/${id}`, { scenario }).then(parseIncident),
  timeline: (scenario?: string, networkId?: string) =>
    fetchJson<Paginated<TimelineEvent>>("api/timeline", { scenario, network_id: networkId }),
  previewReport: (request: ReportRequest, scenario?: string) =>
    fetchJson<ReportDetailV3>("api/reports/preview", reportParams(request, scenario)).then(
      validateReportDetailV3,
    ),
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
    fetchJson<StoredReport>(`api/reports/${id}`, { scenario }).then(parseStoredReport),
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
      `api/topology/${encodeURIComponent(networkId)}/capture`,
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
export type {
  LegacyStoredReportBody,
  ReportDetail,
  ReportDetailV3,
  ReportRequest,
  ReportSummary,
  StoredReport,
} from "@/types/reports";
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
