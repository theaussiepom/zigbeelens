/** Report API types — Core payloads come from the shared package. */

import type { LegacyStoredReportBody, ReportDetailV3 } from "@zigbeelens/shared";

export type {
  LegacyStoredReportBody,
  ReportDetail,
  ReportDetailV3,
  ReportRequest,
  ReportSummary,
} from "@zigbeelens/shared";

/** Stored report GET may return exact v3 or an opaque legacy body. */
export type StoredReport = ReportDetailV3 | LegacyStoredReportBody;
