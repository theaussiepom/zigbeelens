import { Navigate } from "react-router-dom";

/** Preserve bookmarks to the removed standalone routers page. */
export function LegacyRoutersRedirect() {
  return <Navigate to="/investigate" replace />;
}
