/**
 * Report types — exact ReportDetailV3 only after the pre-release v3-only reset.
 */

import type { ReportDetailV3 } from "@zigbeelens/shared";

export type {
  ReportDetail,
  ReportDetailV3,
  ReportDomainDetailsV3,
  ReportFormat,
  ReportRedactionStatus,
  ReportRequest,
  ReportScope,
  ReportSummary,
  StoredReport,
} from "@zigbeelens/shared";

export type StoredReportBody = ReportDetailV3;
