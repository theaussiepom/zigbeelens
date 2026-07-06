import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { ScenarioProvider } from "@/context/ScenarioContext";
import { OverviewPage } from "@/pages/OverviewPage";
import { IncidentsPage, IncidentDetailPage } from "@/pages/IncidentsPage";
import { NetworksPage, NetworkDetailPage } from "@/pages/NetworksPage";
import { RoutersPage } from "@/pages/RoutersPage";
import { DevicesPage, DeviceDetailPage } from "@/pages/DevicesPage";
import { TimelinePage } from "@/pages/TimelinePage";
import { ReportsPage } from "@/pages/ReportsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { TopologyPage } from "@/pages/TopologyPage";
import { TopologyGraphPage } from "@/pages/TopologyGraphPage";
import { MonitoringGuidePage } from "@/pages/MonitoringGuidePage";
import { detectRouterBasename } from "@/lib/base";
import "./index.css";

const basename = detectRouterBasename();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter basename={basename}>
      <ScenarioProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<OverviewPage />} />
            <Route path="incidents" element={<IncidentsPage />} />
            <Route path="incidents/:incidentId" element={<IncidentDetailPage />} />
            <Route path="monitoring" element={<MonitoringGuidePage />} />
            <Route path="networks" element={<NetworksPage />} />
            <Route path="networks/:networkId" element={<NetworkDetailPage />} />
            <Route path="routers" element={<RoutersPage />} />
            <Route path="topology" element={<TopologyPage />} />
            <Route path="topology/:networkId" element={<TopologyPage />} />
            <Route path="topology/:networkId/graph" element={<TopologyGraphPage />} />
            <Route path="devices" element={<DevicesPage />} />
            <Route path="devices/:networkId/:ieeeAddress" element={<DeviceDetailPage />} />
            <Route path="timeline" element={<TimelinePage />} />
            <Route path="reports" element={<ReportsPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </ScenarioProvider>
    </BrowserRouter>
  </StrictMode>,
);
