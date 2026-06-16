function titleCaseWords(text: string): string {
  return text
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

/** Human-readable label for topology snapshot request source. */
export function topologyRequestedByLabel(value?: string | null): string {
  switch (value) {
    case "startup_scan":
      return "Startup scan";
    case "manual_refresh":
    case "manual_user_capture":
      return "Manual refresh";
    case "scheduled_refresh":
    case "periodic_refresh":
      return "Scheduled refresh";
    case null:
    case undefined:
    case "":
      return "Unknown";
    default:
      return titleCaseWords(value);
  }
}

/** Human-readable label for topology snapshot status. */
export function topologyStatusLabel(value?: string | null): string {
  switch (value) {
    case "complete":
      return "Complete";
    case "pending":
      return "Pending";
    case "error":
      return "Error";
    case null:
    case undefined:
    case "":
      return "Unknown";
    default:
      return titleCaseWords(value);
  }
}
