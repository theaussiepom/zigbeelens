"""Narrow repository access layers (decision-engine Phase 2B).

The monolithic ``Repository`` remains the compatibility facade. Each access layer
delegates to it so existing callers keep working while decision services and
topology modules migrate to narrower interfaces incrementally.

Method inventory (Repository → planned access layer):

TopologyRepository (2B-2, done):
  create_topology_snapshot, update_topology_snapshot, store_topology_parsed,
  enforce_topology_retention, delete_topology_snapshot,
  get_latest_topology_snapshot, list_topology_snapshots, get_topology_snapshot,
  list_topology_nodes, list_topology_links, get_topology_node_name,
  list_topology_children, get_topology_parent_router

NetworkRepository (2B-3, done):
  sync_networks, list_networks, get_network, update_network_bridge_state,
  get_network_last_mqtt_activity_at, insert_bridge_snapshot,
  get_latest_bridge_snapshot, update_collector_status, get_collector_status

DeviceRepository (2B-3, done):
  upsert_device, ensure_device_current_state, update_device_current_state,
  get_device_availability, insert_device_snapshot,
  get_devices_by_friendly_name_in_network, list_devices, get_device,
  get_devices_by_friendly_name, find_devices_by_ieee, get_device_by_friendly_name,
  count_devices, count_devices_for_network, count_unavailable_for_network

AvailabilityRepository (2B-4, done):
  insert_availability_change, count_availability_changes_in_window,
  list_availability_changes, get_earliest_availability_change_at,
  list_availability_changes_since

MetricRepository (2B-4, done):
  insert_metric_sample, list_metric_samples

IncidentRepository (2B-5):
  list_incidents, list_active_incidents, get_incident_by_dedup_key,
  insert_incident, update_incident, replace_incident_devices,
  list_offline_transitions_since, list_incidents_for_device, get_incident,
  list_incident_devices, list_active_incident_device_addresses

ReportRepository (2B-5):
  save_report, get_report, list_reports, delete_report

Remaining on Repository until explicitly split:
  events, health_snapshots, HA enrichment, retention/purge, unresolved messages,
  store_unresolved, reconcile_unresolved, has_collected_data, count_events
"""

from zigbeelens.storage.access.availability import AvailabilityRepository
from zigbeelens.storage.access.devices import DeviceRepository
from zigbeelens.storage.access.metrics import MetricRepository
from zigbeelens.storage.access.network import NetworkRepository
from zigbeelens.storage.access.topology import TopologyRepository

__all__ = [
    "AvailabilityRepository",
    "DeviceRepository",
    "MetricRepository",
    "NetworkRepository",
    "TopologyRepository",
]
