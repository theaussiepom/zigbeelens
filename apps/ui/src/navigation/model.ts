/** Shared primary / advanced navigation model for desktop and mobile shells. */

export type PrimaryNavigationItem = {
  kind: "primary";
  to: string;
  label: string;
  /** When true, only the exact path matches (Overview). */
  end?: boolean;
  /** Match this item for the current location pathname (no basename). */
  isActive: (pathname: string) => boolean;
};

export type AdvancedNavigationItem = {
  kind: "advanced";
  to: string;
  label: string;
  isActive: (pathname: string) => boolean;
};

function startsWithPath(pathname: string, base: string): boolean {
  return pathname === base || pathname.startsWith(`${base}/`);
}

export const PRIMARY_NAVIGATION: readonly PrimaryNavigationItem[] = [
  {
    kind: "primary",
    to: "/",
    label: "Overview",
    end: true,
    isActive: (pathname) => pathname === "/",
  },
  {
    kind: "primary",
    to: "/investigate",
    label: "Mesh / Investigate",
    isActive: (pathname) => startsWithPath(pathname, "/investigate"),
  },
  {
    kind: "primary",
    to: "/devices",
    label: "Devices",
    isActive: (pathname) => startsWithPath(pathname, "/devices"),
  },
  {
    kind: "primary",
    to: "/incidents",
    label: "Incidents",
    isActive: (pathname) => startsWithPath(pathname, "/incidents"),
  },
  {
    kind: "primary",
    to: "/reports",
    label: "Reports",
    isActive: (pathname) => startsWithPath(pathname, "/reports"),
  },
  {
    kind: "primary",
    to: "/settings",
    label: "Settings",
    isActive: (pathname) => startsWithPath(pathname, "/settings"),
  },
] as const;

export const ADVANCED_NAVIGATION: readonly AdvancedNavigationItem[] = [
  {
    kind: "advanced",
    to: "/networks",
    label: "Networks",
    isActive: (pathname) => startsWithPath(pathname, "/networks"),
  },
  {
    kind: "advanced",
    to: "/timeline",
    label: "Timeline",
    isActive: (pathname) => startsWithPath(pathname, "/timeline"),
  },
  {
    kind: "advanced",
    to: "/topology",
    label: "Topology snapshots",
    isActive: (pathname) => startsWithPath(pathname, "/topology"),
  },
  {
    kind: "advanced",
    to: "/monitoring",
    label: "How it works",
    isActive: (pathname) => startsWithPath(pathname, "/monitoring"),
  },
] as const;

export function isAdvancedRoute(pathname: string): boolean {
  return ADVANCED_NAVIGATION.some((item) => item.isActive(pathname));
}
