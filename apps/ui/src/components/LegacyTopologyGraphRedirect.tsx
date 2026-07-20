import { Navigate, useParams } from "react-router-dom";
import { investigatePath } from "@/lib/routes";

/** Preserve bookmarks to the former evidence-graph path. */
export function LegacyTopologyGraphRedirect() {
  const { networkId } = useParams<{ networkId: string }>();
  return <Navigate to={investigatePath(networkId ?? "")} replace />;
}
