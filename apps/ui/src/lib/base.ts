/** Resolve API/asset base URL for dev, Docker, and Home Assistant Ingress. */
export function resolveApiBase(): string {
  const configured = import.meta.env.VITE_API_BASE;
  if (configured) return configured.endsWith("/") ? configured : `${configured}/`;
  // Resolve relative to the current page so HA Ingress subpaths work.
  return new URL(".", window.location.href).href;
}

/** React Router basename for Home Assistant Ingress (`/api/hassio_ingress/<token>`). */
export function detectRouterBasename(): string {
  const match = window.location.pathname.match(/^(\/api\/hassio_ingress\/[^/]+)/);
  if (match) return match[1];
  const base = import.meta.env.BASE_URL ?? "/";
  if (base === "./" || base === "." || base === "/") return "";
  return base.replace(/\/$/, "");
}
