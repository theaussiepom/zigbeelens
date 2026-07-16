from __future__ import annotations

import json

# Track 3A pre-transaction commit totals (historical). Do not overwrite.
TRACK_3A_COMMIT_TOTALS: dict[str, int] = {
    "payload_ingestion": 8,
    "availability_ingestion": 11,
    "inventory_ingestion_compact": 50,
    "inventory_ingestion_beast": 357
}

# Track 3B atomic-ingestion phase snapshots (historical). Do not overwrite.
TRACK_3B_PHASE_BASELINES: dict[str, dict[str, int]] = {
    "payload_ingestion": {
        "ingestion_execute_count": 7,
        "ingestion_commit_count": 1,
        "ingestion_rollback_count": 0,
        "post_commit_execute_count": 83,
        "post_commit_commit_count": 2,
        "post_commit_rollback_count": 0,
        "total_execute_count": 90,
        "total_commit_count": 3,
        "total_rollback_count": 0
    },
    "availability_ingestion": {
        "ingestion_execute_count": 6,
        "ingestion_commit_count": 1,
        "ingestion_rollback_count": 0,
        "post_commit_execute_count": 94,
        "post_commit_commit_count": 7,
        "post_commit_rollback_count": 0,
        "total_execute_count": 100,
        "total_commit_count": 8,
        "total_rollback_count": 0
    },
    "inventory_ingestion_compact": {
        "ingestion_execute_count": 43,
        "ingestion_commit_count": 1,
        "ingestion_rollback_count": 0,
        "post_commit_execute_count": 93,
        "post_commit_commit_count": 8,
        "post_commit_rollback_count": 0,
        "total_execute_count": 136,
        "total_commit_count": 9,
        "total_rollback_count": 0
    },
    "inventory_ingestion_beast": {
        "ingestion_execute_count": 334,
        "ingestion_commit_count": 2,
        "ingestion_rollback_count": 0,
        "post_commit_execute_count": 629,
        "post_commit_commit_count": 25,
        "post_commit_rollback_count": 0,
        "total_execute_count": 963,
        "total_commit_count": 27,
        "total_rollback_count": 0
    }
}

# Track 3B total execute/commit snapshots for MQTT write paths (historical).
TRACK_3B_OPERATION_TOTALS: dict[str, dict[str, int]] = {
    "payload_ingestion": {
        "execute_count": 90,
        "commit_count": 3
    },
    "availability_ingestion": {
        "execute_count": 100,
        "commit_count": 8
    },
    "inventory_ingestion_compact": {
        "execute_count": 136,
        "commit_count": 9
    },
    "inventory_ingestion_beast": {
        "execute_count": 963,
        "commit_count": 27
    }
}

# Track 3C read-surface execute totals (historical) before bulk composition.
TRACK_3C_READ_EXECUTE_TOTALS: dict[str, int] = {
    "dashboard": 328,
    "dashboard_beast": 3467,
    "devices": 355,
    "devices_beast": 4169,
    "incident_list": 97,
    "incident_detail": 62,
    "device_detail": 57,
    "report_full": 798,
    "report_network": 798,
    "report_incident": 639,
    "report_device": 510,
    "evidence_graph": 99
}

# Track 3C/3D ingestion vs post-commit phase snapshots for MQTT write paths.
# Track 3D does not change these ingestion/evaluation measurements.
EXPECTED_PHASE_BASELINES: dict[str, dict[str, int]] = {
    "availability_ingestion": {
        "ingestion_commit_count": 1,
        "ingestion_execute_count": 6,
        "ingestion_rollback_count": 0,
        "post_commit_commit_count": 7,
        "post_commit_execute_count": 40,
        "post_commit_rollback_count": 0,
        "total_commit_count": 8,
        "total_execute_count": 46,
        "total_rollback_count": 0
    },
    "availability_ingestion_beast": {
        "ingestion_commit_count": 1,
        "ingestion_execute_count": 6,
        "ingestion_rollback_count": 0,
        "post_commit_commit_count": 7,
        "post_commit_execute_count": 69,
        "post_commit_rollback_count": 0,
        "total_commit_count": 8,
        "total_execute_count": 75,
        "total_rollback_count": 0
    },
    "inventory_ingestion_beast": {
        "ingestion_execute_count": 334,
        "ingestion_commit_count": 2,
        "ingestion_rollback_count": 0,
        "post_commit_execute_count": 629,
        "post_commit_commit_count": 25,
        "post_commit_rollback_count": 0,
        "total_execute_count": 963,
        "total_commit_count": 27,
        "total_rollback_count": 0
    },
    "inventory_ingestion_compact": {
        "ingestion_execute_count": 43,
        "ingestion_commit_count": 1,
        "ingestion_rollback_count": 0,
        "post_commit_execute_count": 93,
        "post_commit_commit_count": 8,
        "post_commit_rollback_count": 0,
        "total_execute_count": 136,
        "total_commit_count": 9,
        "total_rollback_count": 0
    },
    "payload_ingestion": {
        "ingestion_commit_count": 1,
        "ingestion_execute_count": 7,
        "ingestion_rollback_count": 0,
        "post_commit_commit_count": 2,
        "post_commit_execute_count": 29,
        "post_commit_rollback_count": 0,
        "total_commit_count": 3,
        "total_execute_count": 36,
        "total_rollback_count": 0
    },
    "payload_ingestion_beast": {
        "ingestion_commit_count": 1,
        "ingestion_execute_count": 7,
        "ingestion_rollback_count": 0,
        "post_commit_commit_count": 2,
        "post_commit_execute_count": 55,
        "post_commit_rollback_count": 0,
        "total_commit_count": 3,
        "total_execute_count": 62,
        "total_rollback_count": 0
    }
}

# Exact Track 3D total-operation snapshots. They are not product budgets.
EXPECTED_BASELINES: dict[str, dict[str, object]] = json.loads(r'''{
  "availability_ingestion": {
    "category_counts": {
      "read.availability_changes": 2,
      "read.device_current_state": 2,
      "read.devices": 2,
      "read.ha_enrichment": 4,
      "read.health_snapshots": 3,
      "read.incident_devices": 2,
      "read.incidents": 3,
      "read.networks": 3,
      "read.schema": 5,
      "read.topology_links": 3,
      "read.topology_nodes": 2,
      "read.topology_snapshots": 1,
      "transaction.commit": 8,
      "write.availability_changes": 1,
      "write.device_current_state": 2,
      "write.events": 3,
      "write.health_snapshots": 2,
      "write.incident_devices": 4,
      "write.incidents": 2
    },
    "commit_count": 8,
    "execute_count": 46,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 5,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 3,
        "statement": "INSERT INTO events ( id, network_id, ieee_address, event_type, severity, title, summary, incident_id, payload_json, occurred_at ) VALUES (?)"
      },
      {
        "count": 3,
        "statement": "SELECT source_ieee FROM topology_links WHERE snapshot_id = ? AND target_ieee = ? LIMIT ?"
      },
      {
        "count": 3,
        "statement": "SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?"
      },
      {
        "count": 3,
        "statement": "INSERT INTO incident_devices (incident_id, network_id, ieee_address, role) VALUES (?)"
      }
    ]
  },
  "availability_ingestion_beast": {
    "category_counts": {
      "read.availability_changes": 3,
      "read.device_current_state": 2,
      "read.devices": 2,
      "read.ha_enrichment": 4,
      "read.health_snapshots": 3,
      "read.incident_devices": 9,
      "read.incidents": 10,
      "read.networks": 3,
      "read.schema": 7,
      "read.topology_links": 5,
      "read.topology_nodes": 4,
      "read.topology_snapshots": 3,
      "transaction.commit": 8,
      "write.availability_changes": 1,
      "write.device_current_state": 2,
      "write.events": 3,
      "write.health_snapshots": 2,
      "write.incident_devices": 10,
      "write.incidents": 2
    },
    "commit_count": 8,
    "execute_count": 75,
    "executemany_count": 0,
    "fixture": "beast",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 9,
        "statement": "SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ? ORDER BY network_id, ieee_address, role"
      },
      {
        "count": 9,
        "statement": "SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE dedup_key = ? AND lifecycle_state IN (?) ORDER BY updated_at DESC LIMIT ?"
      },
      {
        "count": 9,
        "statement": "INSERT INTO incident_devices (incident_id, network_id, ieee_address, role) VALUES (?)"
      },
      {
        "count": 7,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 3,
        "statement": "SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?"
      }
    ]
  },
  "dashboard": {
    "category_counts": {
      "read.availability_changes": 7,
      "read.bridge_snapshots": 1,
      "read.devices": 11,
      "read.events": 1,
      "read.ha_enrichment": 25,
      "read.incident_devices": 1,
      "read.incidents": 1,
      "read.networks": 4,
      "read.schema": 30,
      "read.topology_links": 17,
      "read.topology_nodes": 4,
      "read.topology_snapshots": 7
    },
    "commit_count": 0,
    "execute_count": 109,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 30,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 23,
        "statement": "SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?"
      },
      {
        "count": 17,
        "statement": "SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?"
      },
      {
        "count": 8,
        "statement": "SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM devices d LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address WHERE d.network_id = ? ORDER BY d.friendly_name"
      },
      {
        "count": 6,
        "statement": "SELECT ieee_address, from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND changed_at >= ? ORDER BY changed_at ASC"
      }
    ]
  },
  "dashboard_beast": {
    "category_counts": {
      "read.availability_changes": 28,
      "read.bridge_snapshots": 2,
      "read.devices": 19,
      "read.events": 1,
      "read.ha_enrichment": 75,
      "read.incident_devices": 1,
      "read.incidents": 1,
      "read.networks": 6,
      "read.schema": 87,
      "read.topology_links": 36,
      "read.topology_nodes": 10,
      "read.topology_snapshots": 16
    },
    "commit_count": 0,
    "execute_count": 282,
    "executemany_count": 0,
    "fixture": "beast",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 87,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 72,
        "statement": "SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?"
      },
      {
        "count": 34,
        "statement": "SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?"
      },
      {
        "count": 26,
        "statement": "SELECT ieee_address, from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND changed_at >= ? ORDER BY changed_at ASC"
      },
      {
        "count": 16,
        "statement": "SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM devices d LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address WHERE d.network_id = ? ORDER BY d.friendly_name"
      }
    ]
  },
  "device_detail": {
    "category_counts": {
      "read.availability_changes": 4,
      "read.device_snapshots": 1,
      "read.devices": 5,
      "read.events": 1,
      "read.ha_enrichment": 3,
      "read.incident_devices": 1,
      "read.incidents": 3,
      "read.metric_samples": 1,
      "read.networks": 3,
      "read.schema": 6,
      "read.topology_links": 10,
      "read.topology_nodes": 12,
      "read.topology_snapshots": 4
    },
    "commit_count": 0,
    "execute_count": 54,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 12,
        "statement": "SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address"
      },
      {
        "count": 10,
        "statement": "SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?"
      },
      {
        "count": 6,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 3,
        "statement": "SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?"
      },
      {
        "count": 2,
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name"
      }
    ]
  },
  "devices": {
    "category_counts": {
      "read.availability_changes": 22,
      "read.device_snapshots": 20,
      "read.devices": 3,
      "read.ha_enrichment": 2,
      "read.incident_devices": 1,
      "read.incidents": 1,
      "read.networks": 2,
      "read.schema": 5,
      "read.topology_links": 10,
      "read.topology_nodes": 12,
      "read.topology_snapshots": 4
    },
    "commit_count": 0,
    "execute_count": 82,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 20,
        "statement": "SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?"
      },
      {
        "count": 20,
        "statement": "SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?"
      },
      {
        "count": 12,
        "statement": "SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address"
      },
      {
        "count": 10,
        "statement": "SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?"
      },
      {
        "count": 5,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      }
    ]
  },
  "devices_beast": {
    "category_counts": {
      "read.availability_changes": 168,
      "read.device_snapshots": 164,
      "read.devices": 4,
      "read.ha_enrichment": 3,
      "read.incident_devices": 1,
      "read.incidents": 1,
      "read.networks": 3,
      "read.schema": 9,
      "read.topology_links": 20,
      "read.topology_nodes": 24,
      "read.topology_snapshots": 8
    },
    "commit_count": 0,
    "execute_count": 405,
    "executemany_count": 0,
    "fixture": "beast",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 164,
        "statement": "SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?"
      },
      {
        "count": 164,
        "statement": "SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?"
      },
      {
        "count": 24,
        "statement": "SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address"
      },
      {
        "count": 20,
        "statement": "SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?"
      },
      {
        "count": 9,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      }
    ]
  },
  "evidence_graph": {
    "category_counts": {
      "read.availability_changes": 5,
      "read.devices": 6,
      "read.ha_enrichment": 23,
      "read.networks": 1,
      "read.schema": 27,
      "read.topology_links": 26,
      "read.topology_nodes": 4,
      "read.topology_snapshots": 7
    },
    "commit_count": 0,
    "execute_count": 99,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 27,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 26,
        "statement": "SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?"
      },
      {
        "count": 23,
        "statement": "SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?"
      },
      {
        "count": 6,
        "statement": "SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM devices d LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address WHERE d.network_id = ? ORDER BY d.friendly_name"
      },
      {
        "count": 5,
        "statement": "SELECT ieee_address, from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND changed_at >= ? ORDER BY changed_at ASC"
      }
    ]
  },
  "incident_detail": {
    "category_counts": {
      "read.availability_changes": 5,
      "read.device_snapshots": 3,
      "read.devices": 2,
      "read.events": 1,
      "read.ha_enrichment": 2,
      "read.incident_devices": 1,
      "read.incidents": 2,
      "read.schema": 5,
      "read.topology_links": 10,
      "read.topology_nodes": 12,
      "read.topology_snapshots": 4
    },
    "commit_count": 0,
    "execute_count": 47,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 12,
        "statement": "SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address"
      },
      {
        "count": 10,
        "statement": "SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?"
      },
      {
        "count": 5,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 3,
        "statement": "SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?"
      },
      {
        "count": 3,
        "statement": "SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?"
      }
    ]
  },
  "incident_list": {
    "category_counts": {
      "read.availability_changes": 7,
      "read.device_snapshots": 5,
      "read.devices": 2,
      "read.events": 1,
      "read.ha_enrichment": 2,
      "read.incident_devices": 1,
      "read.incidents": 2,
      "read.schema": 5,
      "read.topology_links": 10,
      "read.topology_nodes": 12,
      "read.topology_snapshots": 4
    },
    "commit_count": 0,
    "execute_count": 51,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 12,
        "statement": "SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address"
      },
      {
        "count": 10,
        "statement": "SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?"
      },
      {
        "count": 5,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 5,
        "statement": "SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?"
      },
      {
        "count": 5,
        "statement": "SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?"
      }
    ]
  },
  "inventory_ingestion_beast": {
    "category_counts": {
      "read.availability_changes": 168,
      "read.device_current_state": 2,
      "read.devices": 7,
      "read.ha_enrichment": 8,
      "read.health_snapshots": 168,
      "read.incident_devices": 18,
      "read.incidents": 20,
      "read.networks": 6,
      "read.schema": 53,
      "read.topology_links": 49,
      "read.topology_nodes": 47,
      "read.topology_snapshots": 45,
      "read.unresolved": 2,
      "transaction.commit": 27,
      "write.device_current_state": 164,
      "write.devices": 164,
      "write.events": 5,
      "write.health_snapshots": 17,
      "write.incident_devices": 17,
      "write.incidents": 3
    },
    "commit_count": 27,
    "execute_count": 963,
    "executemany_count": 0,
    "fixture": "beast",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 164,
        "statement": "INSERT INTO devices ( network_id, ieee_address, friendly_name, device_type, power_source, manufacturer, model, interview_state, created_at, updated_at ) VALUES (?) ON CONFLICT(network_id, ieee_address) DO UPDATE SET friendly_name = excluded.friendly_name, device_type = excluded.device_type, power_source = excluded.power_source, manufacturer = COALESCE(excluded.manufacturer, devices.manufacturer), model = COALESCE(excluded.model, devices.model), interview_state = excluded.interview_state, updated_at = excluded.updated_at"
      },
      {
        "count": 164,
        "statement": "INSERT OR IGNORE INTO device_current_state (network_id, ieee_address) VALUES (?)"
      },
      {
        "count": 164,
        "statement": "SELECT COUNT(*) FROM availability_changes WHERE network_id = ? AND ieee_address = ? AND changed_at >= ?"
      },
      {
        "count": 164,
        "statement": "SELECT primary_health, severity, confidence, summary, flags_json, evidence_json, counter_evidence_json, limitations_json, captured_at FROM health_snapshots WHERE scope = ? AND network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?"
      },
      {
        "count": 53,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      }
    ]
  },
  "inventory_ingestion_compact": {
    "category_counts": {
      "read.availability_changes": 21,
      "read.device_current_state": 1,
      "read.devices": 4,
      "read.ha_enrichment": 3,
      "read.health_snapshots": 22,
      "read.incident_devices": 2,
      "read.incidents": 3,
      "read.networks": 3,
      "read.schema": 8,
      "read.topology_links": 6,
      "read.topology_nodes": 6,
      "read.topology_snapshots": 5,
      "read.unresolved": 1,
      "transaction.commit": 9,
      "write.device_current_state": 20,
      "write.devices": 20,
      "write.events": 3,
      "write.health_snapshots": 3,
      "write.incident_devices": 3,
      "write.incidents": 2
    },
    "commit_count": 9,
    "execute_count": 136,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 20,
        "statement": "INSERT INTO devices ( network_id, ieee_address, friendly_name, device_type, power_source, manufacturer, model, interview_state, created_at, updated_at ) VALUES (?) ON CONFLICT(network_id, ieee_address) DO UPDATE SET friendly_name = excluded.friendly_name, device_type = excluded.device_type, power_source = excluded.power_source, manufacturer = COALESCE(excluded.manufacturer, devices.manufacturer), model = COALESCE(excluded.model, devices.model), interview_state = excluded.interview_state, updated_at = excluded.updated_at"
      },
      {
        "count": 20,
        "statement": "INSERT OR IGNORE INTO device_current_state (network_id, ieee_address) VALUES (?)"
      },
      {
        "count": 20,
        "statement": "SELECT COUNT(*) FROM availability_changes WHERE network_id = ? AND ieee_address = ? AND changed_at >= ?"
      },
      {
        "count": 20,
        "statement": "SELECT primary_health, severity, confidence, summary, flags_json, evidence_json, counter_evidence_json, limitations_json, captured_at FROM health_snapshots WHERE scope = ? AND network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?"
      },
      {
        "count": 8,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      }
    ]
  },
  "payload_ingestion": {
    "category_counts": {
      "read.availability_changes": 2,
      "read.device_current_state": 1,
      "read.devices": 2,
      "read.ha_enrichment": 3,
      "read.health_snapshots": 3,
      "read.incident_devices": 2,
      "read.incidents": 3,
      "read.networks": 3,
      "read.schema": 4,
      "read.topology_links": 2,
      "read.topology_nodes": 2,
      "read.topology_snapshots": 1,
      "transaction.commit": 3,
      "write.device_current_state": 2,
      "write.device_snapshots": 1,
      "write.events": 2,
      "write.incidents": 1,
      "write.metric_samples": 2
    },
    "commit_count": 3,
    "execute_count": 36,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 4,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 2,
        "statement": "SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ? ORDER BY network_id, ieee_address, role"
      },
      {
        "count": 2,
        "statement": "INSERT INTO metric_samples (network_id, ieee_address, metric_name, metric_value, sampled_at) VALUES (?)"
      },
      {
        "count": 2,
        "statement": "INSERT INTO events ( id, network_id, ieee_address, event_type, severity, title, summary, incident_id, payload_json, occurred_at ) VALUES (?)"
      },
      {
        "count": 2,
        "statement": "SELECT primary_health, severity, confidence, summary, flags_json, evidence_json, counter_evidence_json, limitations_json, captured_at FROM health_snapshots WHERE scope = ? AND network_id = ? AND ieee_address IS NULL ORDER BY captured_at DESC LIMIT ?"
      }
    ]
  },
  "payload_ingestion_beast": {
    "category_counts": {
      "read.availability_changes": 3,
      "read.device_current_state": 1,
      "read.devices": 2,
      "read.ha_enrichment": 4,
      "read.health_snapshots": 3,
      "read.incident_devices": 9,
      "read.incidents": 10,
      "read.networks": 3,
      "read.schema": 7,
      "read.topology_links": 5,
      "read.topology_nodes": 4,
      "read.topology_snapshots": 3,
      "transaction.commit": 3,
      "write.device_current_state": 2,
      "write.device_snapshots": 1,
      "write.events": 2,
      "write.incidents": 1,
      "write.metric_samples": 2
    },
    "commit_count": 3,
    "execute_count": 62,
    "executemany_count": 0,
    "fixture": "beast",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 9,
        "statement": "SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ? ORDER BY network_id, ieee_address, role"
      },
      {
        "count": 9,
        "statement": "SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE dedup_key = ? AND lifecycle_state IN (?) ORDER BY updated_at DESC LIMIT ?"
      },
      {
        "count": 7,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 3,
        "statement": "SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?"
      },
      {
        "count": 3,
        "statement": "SELECT friendly_name FROM topology_nodes WHERE snapshot_id = ? AND ieee_address = ?"
      }
    ]
  },
  "report_device": {
    "category_counts": {
      "read.availability_changes": 18,
      "read.bridge_snapshots": 2,
      "read.device_snapshots": 6,
      "read.devices": 22,
      "read.events": 4,
      "read.ha_enrichment": 32,
      "read.incident_devices": 6,
      "read.incidents": 9,
      "read.metric_samples": 1,
      "read.networks": 12,
      "read.schema": 43,
      "read.topology_links": 37,
      "read.topology_nodes": 28,
      "read.topology_snapshots": 17
    },
    "commit_count": 0,
    "execute_count": 237,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 43,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 37,
        "statement": "SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?"
      },
      {
        "count": 28,
        "statement": "SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address"
      },
      {
        "count": 24,
        "statement": "SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?"
      },
      {
        "count": 11,
        "statement": "SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?"
      }
    ]
  },
  "report_full": {
    "category_counts": {
      "read.availability_changes": 36,
      "read.bridge_snapshots": 2,
      "read.device_snapshots": 25,
      "read.devices": 20,
      "read.events": 3,
      "read.ha_enrichment": 31,
      "read.incident_devices": 5,
      "read.incidents": 7,
      "read.networks": 9,
      "read.schema": 42,
      "read.topology_links": 37,
      "read.topology_nodes": 28,
      "read.topology_snapshots": 17
    },
    "commit_count": 0,
    "execute_count": 262,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 42,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 37,
        "statement": "SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?"
      },
      {
        "count": 28,
        "statement": "SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address"
      },
      {
        "count": 25,
        "statement": "SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?"
      },
      {
        "count": 25,
        "statement": "SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?"
      }
    ]
  },
  "report_incident": {
    "category_counts": {
      "read.availability_changes": 27,
      "read.bridge_snapshots": 2,
      "read.device_snapshots": 11,
      "read.devices": 28,
      "read.events": 7,
      "read.ha_enrichment": 36,
      "read.incident_devices": 9,
      "read.incidents": 18,
      "read.metric_samples": 3,
      "read.networks": 18,
      "read.schema": 50,
      "read.topology_links": 47,
      "read.topology_nodes": 40,
      "read.topology_snapshots": 21
    },
    "commit_count": 0,
    "execute_count": 317,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 50,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 47,
        "statement": "SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?"
      },
      {
        "count": 40,
        "statement": "SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address"
      },
      {
        "count": 26,
        "statement": "SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?"
      },
      {
        "count": 14,
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name"
      }
    ]
  },
  "report_network": {
    "category_counts": {
      "read.availability_changes": 36,
      "read.bridge_snapshots": 2,
      "read.device_snapshots": 25,
      "read.devices": 20,
      "read.events": 3,
      "read.ha_enrichment": 31,
      "read.incident_devices": 5,
      "read.incidents": 7,
      "read.networks": 9,
      "read.schema": 42,
      "read.topology_links": 37,
      "read.topology_nodes": 28,
      "read.topology_snapshots": 17
    },
    "commit_count": 0,
    "execute_count": 262,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 42,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 37,
        "statement": "SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?"
      },
      {
        "count": 28,
        "statement": "SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address"
      },
      {
        "count": 25,
        "statement": "SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?"
      },
      {
        "count": 25,
        "statement": "SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?"
      }
    ]
  }
}''')
