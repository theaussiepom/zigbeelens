import type { ReactNode } from "react";
import type {
  Availability,
  Confidence,
  DeviceHealthPrimary,
  IncidentStatus,
  Severity,
} from "@zigbeelens/shared";
import {
  availabilityLabel,
  confidenceLabel,
  formatTime,
  healthLabel,
  healthSeverity,
  lifecycleLabel,
  lifecycleSeverity,
  relativeTime,
  severityBg,
  severityDot,
  severityLabel,
} from "@/lib/format";

/* ----------------------------------------------------------------------- */
/* Layout primitives                                                        */
/* ----------------------------------------------------------------------- */

export function Card({
  title,
  subtitle,
  actions,
  children,
  className = "",
}: {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-xl border border-zl-border bg-zl-surface p-5 shadow-sm ${className}`}
    >
      {(title || subtitle || actions) && (
        <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            {title && <h2 className="text-base font-semibold text-zl-text">{title}</h2>}
            {subtitle && <p className="mt-1 text-sm text-zl-muted">{subtitle}</p>}
          </div>
          {actions && <div className="shrink-0">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function SectionHeading({ children }: { children: ReactNode }) {
  return (
    <h2 className="text-xs font-semibold uppercase tracking-wide text-zl-muted">{children}</h2>
  );
}

/* ----------------------------------------------------------------------- */
/* Badges                                                                   */
/* ----------------------------------------------------------------------- */

export function Badge({
  children,
  severity,
  title,
}: {
  children: ReactNode;
  severity?: Severity;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${
        severity ? severityBg(severity) : "bg-zl-surface-2 text-zl-muted border-zl-border"
      }`}
    >
      {children}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <Badge severity={severity}>
      <span className={`h-1.5 w-1.5 rounded-full ${severityDot(severity)}`} />
      {severityLabel(severity)}
    </Badge>
  );
}

export function HealthBadge({ primary }: { primary: DeviceHealthPrimary }) {
  return <Badge severity={healthSeverity(primary)}>{healthLabel(primary)}</Badge>;
}

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  return (
    <span
      title={`ZigbeeLens confidence: ${confidenceLabel(confidence)}`}
      className="inline-flex items-center rounded-full border border-zl-border bg-zl-surface-2 px-2.5 py-0.5 text-xs font-medium text-zl-muted"
    >
      {confidenceLabel(confidence)} confidence
    </span>
  );
}

export function LifecycleBadge({ status }: { status: IncidentStatus }) {
  return <Badge severity={lifecycleSeverity(status)}>{lifecycleLabel(status)}</Badge>;
}

export function NetworkBadge({ network }: { network: string }) {
  return (
    <span className="inline-flex items-center rounded-md border border-zl-border bg-zl-bg/60 px-2 py-0.5 font-mono text-xs text-zl-muted">
      {network}
    </span>
  );
}

export function DeviceRoleBadge({ role }: { role: string }) {
  const label = role.replace(/_/g, " ");
  return (
    <span className="inline-flex items-center rounded-md border border-zl-accent/30 bg-zl-accent/10 px-2 py-0.5 text-xs font-medium text-zl-accent">
      {label}
    </span>
  );
}

export function AvailabilityBadge({ availability }: { availability: Availability }) {
  const severity: Severity =
    availability === "online" ? "healthy" : availability === "offline" ? "incident" : "watch";
  return <Badge severity={severity}>{availabilityLabel(availability)}</Badge>;
}

/* ----------------------------------------------------------------------- */
/* Metrics & inline text                                                    */
/* ----------------------------------------------------------------------- */

export function MetricPill({
  label,
  value,
  severity,
}: {
  label: string;
  value: string | number;
  severity?: Severity;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs ${
        severity && severity !== "healthy"
          ? severityBg(severity)
          : "border-zl-border bg-zl-bg/50 text-zl-muted"
      }`}
    >
      <span className="uppercase tracking-wide">{label}</span>
      <span className="font-semibold text-zl-text">{value}</span>
    </span>
  );
}

export function StatTile({
  label,
  value,
  severity,
  hint,
}: {
  label: string;
  value: string | number;
  severity?: Severity;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-zl-border bg-zl-bg/50 px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-zl-muted">{label}</div>
      <div
        className={`mt-1 text-2xl font-semibold ${
          severity ? severityBg(severity).split(" ")[1] : "text-zl-text"
        }`}
      >
        {value}
      </div>
      {hint && <div className="mt-0.5 text-xs text-zl-muted">{hint}</div>}
    </div>
  );
}

export function LastSeenText({ iso, prefix }: { iso?: string; prefix?: string }) {
  return (
    <span title={formatTime(iso)} className="text-zl-muted">
      {prefix ? `${prefix} ` : ""}
      {relativeTime(iso)}
    </span>
  );
}

/* ----------------------------------------------------------------------- */
/* Evidence / limitation lists                                              */
/* ----------------------------------------------------------------------- */

function normalize(items: Array<string | { summary: string }>): string[] {
  return items.map((i) => (typeof i === "string" ? i : i.summary));
}

function EvidenceColumn({
  title,
  items,
  tone,
  emptyText,
}: {
  title: string;
  items: Array<string | { summary: string }>;
  tone: "positive" | "neutral" | "muted";
  emptyText: string;
}) {
  const list = normalize(items);
  const border =
    tone === "positive"
      ? "border-zl-healthy/20"
      : tone === "neutral"
        ? "border-zl-border"
        : "border-zl-watch/20";
  return (
    <div className={`rounded-lg border ${border} bg-zl-bg/40 p-3`}>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zl-muted">{title}</h3>
      {list.length === 0 ? (
        <p className="text-sm italic text-zl-muted">{emptyText}</p>
      ) : (
        <ul className="space-y-2">
          {list.map((item, i) => (
            <li key={i} className="text-sm leading-snug text-zl-text">
              {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function EvidenceList({
  items,
  emptyText = "No evidence recorded.",
}: {
  items: Array<string | { summary: string }>;
  emptyText?: string;
}) {
  return <EvidenceColumn title="Evidence" items={items} tone="positive" emptyText={emptyText} />;
}

export function CounterEvidenceList({
  items,
  emptyText = "No counter-evidence has been recorded.",
}: {
  items: Array<string | { summary: string }>;
  emptyText?: string;
}) {
  return (
    <EvidenceColumn title="Counter-evidence" items={items} tone="neutral" emptyText={emptyText} />
  );
}

export function LimitationsList({
  items,
  emptyText = "No limitations noted.",
}: {
  items: Array<string | { summary: string }>;
  emptyText?: string;
}) {
  return <EvidenceColumn title="Limitations" items={items} tone="muted" emptyText={emptyText} />;
}

/* ----------------------------------------------------------------------- */
/* State placeholders                                                       */
/* ----------------------------------------------------------------------- */

export function EmptyState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="rounded-xl border border-dashed border-zl-border bg-zl-surface/50 p-10 text-center">
      <p className="font-medium text-zl-text">{title}</p>
      {detail && <p className="mt-2 text-sm text-zl-muted">{detail}</p>}
    </div>
  );
}

export function LoadingState({ label = "Loading ZigbeeLens…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center p-16 text-zl-muted">
      <div className="animate-pulse">{label}</div>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const friendly =
    message.includes("(500)") || message.includes("(503)")
      ? "ZigbeeLens Core is still starting or temporarily busy. This usually clears after a moment."
      : message.includes("not reachable")
        ? "ZigbeeLens Core is not reachable from your browser."
        : message;

  return (
    <div className="rounded-xl border border-zl-critical/40 bg-zl-critical/10 p-6 text-zl-critical">
      <p>{friendly}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 min-h-11 rounded-lg border border-zl-critical/40 px-4 py-2 text-sm hover:bg-zl-critical/10 active:bg-zl-critical/15"
        >
          Try again
        </button>
      )}
    </div>
  );
}
