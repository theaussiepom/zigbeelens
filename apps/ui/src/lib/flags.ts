/**
 * Build-time feature flags.
 *
 * The scenario (mock fixture) selector is a testing aid and must never appear
 * in the published image. It is shown only when running the Vite dev server,
 * or when a build is explicitly opted in with `VITE_ENABLE_SCENARIOS=true`.
 * The production Docker build sets neither, so the selector stays hidden.
 */
export function scenariosEnabled(): boolean {
  if (import.meta.env.VITE_ENABLE_SCENARIOS === "true") return true;
  return Boolean(import.meta.env.DEV);
}
