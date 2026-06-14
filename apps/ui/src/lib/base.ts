/** React Router basename for Home Assistant Ingress (`/api/hassio_ingress/<token>`). */
export function detectRouterBasename(): string {
  const match = window.location.pathname.match(/^(\/api\/hassio_ingress\/[^/]+)/);
  if (match) return match[1];
  const base = import.meta.env.BASE_URL ?? "/";
  if (base === "./" || base === "." || base === "/") return "";
  return base.replace(/\/$/, "");
}

/**
 * Resolve API/asset base URL for dev, Docker, and Home Assistant Ingress.
 *
 * Anchored to the app root (origin + router basename), NOT the current page
 * directory. Resolving relative to `window.location.href` breaks nested routes
 * like `/devices/<net>/<ieee>`, where the base would wrongly become
 * `/devices/<net>/` and API calls would hit the SPA fallback (HTML, not JSON).
 */
export function resolveApiBase(): string {
  const configured = import.meta.env.VITE_API_BASE;
  if (configured) return configured.endsWith("/") ? configured : `${configured}/`;
  const basename = detectRouterBasename();
  return `${window.location.origin}${basename}/`;
}
