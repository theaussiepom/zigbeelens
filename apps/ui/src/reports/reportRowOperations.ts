export type ReportRowOperation = "download" | "copy" | "delete";

/**
 * Per-report ownership for Saved reports row mutations.
 * Concurrent operations on different report IDs are allowed; same ID is single-flight.
 */
export class ReportRowOperationRegistry {
  private readonly busy = new Map<string, ReportRowOperation>();

  begin(reportId: string, _operation: ReportRowOperation): boolean {
    if (this.busy.has(reportId)) return false;
    this.busy.set(reportId, _operation);
    return true;
  }

  end(reportId: string): void {
    this.busy.delete(reportId);
  }

  isBusy(reportId: string): boolean {
    return this.busy.has(reportId);
  }

  operation(reportId: string): ReportRowOperation | undefined {
    return this.busy.get(reportId);
  }

  snapshot(): ReadonlySet<string> {
    return new Set(this.busy.keys());
  }

  clear(): void {
    this.busy.clear();
  }
}
