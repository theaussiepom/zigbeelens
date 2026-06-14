import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api } from "@/lib/api";
import type { ZigbeeLensConfigStatus } from "@zigbeelens/shared";

interface ScenarioContextValue {
  /** Selected scenario id, or "" for Core's native (live/default) data. */
  scenario: string;
  setScenario: (id: string) => void;
  scenarios: Array<{ id: string; label: string }>;
  status: ZigbeeLensConfigStatus | null;
  refreshStatus: () => Promise<void>;
  /** Core's configured data mode, independent of any scenario override. */
  dataMode: "mock" | "live";
  /** True when the UI is showing fixture data rather than live Core data. */
  isScenarioMode: boolean;
  mqttConnected: boolean;
}

const ScenarioContext = createContext<ScenarioContextValue | null>(null);

const STORAGE_KEY = "zigbeelens-scenario";

export function ScenarioProvider({ children }: { children: ReactNode }) {
  const [scenario, setScenarioState] = useState(() => localStorage.getItem(STORAGE_KEY) ?? "");
  const [scenarios, setScenarios] = useState<Array<{ id: string; label: string }>>([]);
  const [status, setStatus] = useState<ZigbeeLensConfigStatus | null>(null);

  const setScenario = useCallback((id: string) => {
    setScenarioState(id);
    if (id) localStorage.setItem(STORAGE_KEY, id);
    else localStorage.removeItem(STORAGE_KEY);
  }, []);

  const refreshStatus = useCallback(async () => {
    const s = await api.configStatus(scenario || undefined);
    setStatus(s);
  }, [scenario]);

  useEffect(() => {
    api.scenarios().then(setScenarios).catch(console.error);
  }, []);

  useEffect(() => {
    refreshStatus().catch(console.error);
  }, [refreshStatus]);

  const dataMode = status?.data_mode ?? "mock";
  const isScenarioMode = dataMode === "mock" || scenario !== "";
  const mqttConnected = Boolean(status?.mqtt_connected);

  const value = useMemo(
    () => ({
      scenario,
      setScenario,
      scenarios,
      status,
      refreshStatus,
      dataMode,
      isScenarioMode,
      mqttConnected,
    }),
    [scenario, setScenario, scenarios, status, refreshStatus, dataMode, isScenarioMode, mqttConnected],
  );

  return <ScenarioContext.Provider value={value}>{children}</ScenarioContext.Provider>;
}

export function useScenario() {
  const ctx = useContext(ScenarioContext);
  if (!ctx) throw new Error("useScenario must be used within ScenarioProvider");
  return ctx;
}
