import { useMemo } from "react";
import type { RouterRisk } from "@zigbeelens/shared";
import { api } from "@/lib/api";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import { EmptyState, ErrorState, LoadingState, NetworkBadge } from "@/components/ui";
import { RouterRiskCard } from "@/components/cards";
import { compareRouterRisks } from "@/lib/format";

const ROUTER_EVENTS = [
  "health_updated",
  "device_health_updated",
  "network_health_updated",
  "dashboard_updated",
  "incidents_updated",
  "incident_opened",
  "incident_updated",
  "incident_resolved",
];

export function RoutersPage() {
  const { scenario } = useScenario();
  const { data, error, loading, refetch } = useLiveResource(
    () => api.routers(scenario || undefined).then((r) => r.items),
    [scenario],
    { refetchOn: ROUTER_EVENTS },
  );

  const grouped = useMemo(() => {
    const byNetwork = new Map<string, RouterRisk[]>();
    for (const r of data ?? []) {
      const list = byNetwork.get(r.network_id) ?? [];
      list.push(r);
      byNetwork.set(r.network_id, list);
    }
    return [...byNetwork.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([network, routers]) => ({ network, routers: routers.sort(compareRouterRisks) }));
  }, [data]);

  if (error) return <ErrorState message={error} onRetry={refetch} />;
  if (loading) return <LoadingState />;

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Routers</h1>
        <p className="mt-1 text-zl-muted">
          Routers are infrastructure. Risk candidates use careful, evidence-backed language —
          ZigbeeLens cannot confirm dependent routes without topology data.
        </p>
      </div>

      {grouped.length === 0 ? (
        <EmptyState
          title="No router risk candidates detected"
          detail="No Zigbee routers currently show risk signals in this view."
        />
      ) : (
        grouped.map(({ network, routers }) => (
          <section key={network} className="space-y-3">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">
                Network
              </h2>
              <NetworkBadge network={network} />
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              {routers.map((r) => (
                <RouterRiskCard key={`${r.network_id}-${r.ieee_address}`} router={r} />
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
