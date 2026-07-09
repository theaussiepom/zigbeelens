import type { ReactNode } from "react";

/**
 * Right-hand slide-over used by device and link details panels.
 * User-facing copy says “details panel”; “drawer” is implementation-only.
 */
export function DrawerShell({
  label,
  onClose,
  children,
}: {
  label: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div
      role="dialog"
      aria-label={label}
      className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-zl-border bg-zl-surface shadow-2xl"
    >
      <div className="flex items-center justify-between border-b border-zl-border px-5 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">{label}</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close details panel"
          className="rounded-lg border border-zl-border px-3 py-1 text-sm text-zl-muted hover:bg-zl-surface-2 hover:text-zl-text"
        >
          Close
        </button>
      </div>
      <div className="flex-1 space-y-5 overflow-y-auto p-5">{children}</div>
    </div>
  );
}

export function DrawerSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-zl-muted">
        {title}
      </h3>
      <div className="text-sm leading-relaxed text-zl-text">{children}</div>
    </section>
  );
}

export function DrawerFact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-0.5">
      <dt className="text-xs text-zl-muted">{label}</dt>
      <dd className="text-right text-sm text-zl-text">{value}</dd>
    </div>
  );
}
