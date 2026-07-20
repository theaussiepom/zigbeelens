/** Shared decision-contract v2 fixtures for UI tests. */

import type {
  DashboardPayload,
  DecisionCountSummary,
  DeviceDecisionBadge,
  DeviceSummary,
  NetworkSummary,
} from "@zigbeelens/shared";

export function makeDecisionBadge(
  overrides: Partial<DeviceDecisionBadge> = {},
): DeviceDecisionBadge {
  return {
    status: "no_notable_change",
    priority: "none",
    headline_code: "device_no_notable_change",
    coverage_label_codes: [],
    ...overrides,
  };
}

export function makeDecisionSummary(
  overrides: Partial<DecisionCountSummary> = {},
): DecisionCountSummary {
  return {
    subject_count: 0,
    overall_status: "data_unavailable",
    highest_priority: "none",
    status_counts: {},
    priority_counts: {},
    coverage_warning_count: 0,
    ...overrides,
  };
}

export function makeDeviceSummary(overrides: Partial<DeviceSummary> = {}): DeviceSummary {
  return {
    network_id: "home",
    ieee_address: "0x1",
    friendly_name: "sensor",
    device_type: "EndDevice",
    power_source: "Battery",
    availability: "online",
    interview_state: "successful",
    incident_affected: false,
    decision: makeDecisionBadge(),
    ...overrides,
  };
}

export function makeNetworkSummary(overrides: Partial<NetworkSummary> = {}): NetworkSummary {
  const deviceCount = overrides.device_count ?? 0;
  const decision =
    overrides.decision ??
    (deviceCount === 0
      ? makeDecisionBadge({
          status: "data_unavailable",
          headline_code: "network_data_unavailable",
        })
      : makeDecisionBadge({
          status: "no_notable_change",
          headline_code: "network_no_notable_change",
        }));
  const decision_summary =
    overrides.decision_summary ??
    (deviceCount === 0
      ? makeDecisionSummary()
      : makeDecisionSummary({
          subject_count: deviceCount,
          overall_status: decision.status,
          highest_priority: decision.priority,
          status_counts: { [decision.status]: deviceCount },
          priority_counts: { [decision.priority]: deviceCount },
        }));
  return {
    id: "home",
    name: "Home",
    base_topic: "zigbee2mqtt",
    bridge_state: "online",
    device_count: 0,
    router_count: 0,
    end_device_count: 0,
    unavailable_count: 0,
    active_incident_severity: "healthy",
    active_incident_count: 0,
    recent_bridge_warnings: 0,
    recent_bridge_errors: 0,
    decision,
    decision_summary,
    ...overrides,
    decision: overrides.decision ?? decision,
    decision_summary: overrides.decision_summary ?? decision_summary,
  };
}

export function makeDashboardPayload(
  overrides: Partial<DashboardPayload> = {},
): DashboardPayload {
  const networks = overrides.networks ?? [makeNetworkSummary()];
  const decision_summary = overrides.decision_summary ?? makeDecisionSummary();
  return {
    generated_at: new Date().toISOString(),
    active_incident_count: 0,
    watching_incident_count: 0,
    network_count: networks.length,
    device_count: 0,
    unavailable_device_count: 0,
    networks,
    router_risks: [],
    recent_timeline: [],
    decision_summary,
    shared_availability_events: [],
    model_patterns: [],
    investigation_priorities: [],
    data_coverage_warnings: [],
    ...overrides,
    networks: overrides.networks ?? networks,
    decision_summary: overrides.decision_summary ?? decision_summary,
  };
}
