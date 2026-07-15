from __future__ import annotations

import json

# Track 3A pre-transaction commit totals (historical). Do not overwrite.
TRACK_3A_COMMIT_TOTALS: dict[str, int] = {
    "payload_ingestion": 8,
    "availability_ingestion": 11,
    "inventory_ingestion_compact": 50,
    "inventory_ingestion_beast": 357,
}

# Track 3B ingestion vs post-commit phase snapshots for MQTT write paths.
EXPECTED_PHASE_BASELINES: dict[str, dict[str, int]] = {
    "payload_ingestion": {
        "ingestion_execute_count": 7,
        "ingestion_commit_count": 1,
        "ingestion_rollback_count": 0,
        "post_commit_execute_count": 83,
        "post_commit_commit_count": 2,
        "post_commit_rollback_count": 0,
        "total_execute_count": 90,
        "total_commit_count": 3,
        "total_rollback_count": 0,
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
        "total_rollback_count": 0,
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
        "total_rollback_count": 0,
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
        "total_rollback_count": 0,
    },
}

# Exact Track 3B total-operation snapshots. They are not product budgets.
EXPECTED_BASELINES: dict[str, dict[str, object]] = json.loads(r'''{
  "availability_ingestion": {
    "category_counts": {
      "read.networks": 3,
      "read.devices": 2,
      "read.incidents": 3,
      "read.incident_devices": 2,
      "read.schema": 9,
      "read.topology_snapshots": 5,
      "read.topology_nodes": 6,
      "read.topology_links": 7,
      "read.device_current_state": 2,
      "write.device_current_state": 2,
      "write.availability_changes": 1,
      "write.events": 3,
      "transaction.commit": 8,
      "read.availability_changes": 21,
      "read.health_snapshots": 22,
      "write.health_snapshots": 2,
      "read.ha_enrichment": 4,
      "write.incidents": 2,
      "write.incident_devices": 4
    },
    "commit_count": 8,
    "execute_count": 100,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 20,
        "statement": "SELECT COUNT(*) FROM availability_changes WHERE network_id = ? AND ieee_address = ? AND changed_at >= ?"
      },
      {
        "count": 20,
        "statement": "SELECT primary_health, severity, confidence, summary, flags_json, evidence_json, counter_evidence_json, limitations_json, captured_at FROM health_snapshots WHERE scope = ? AND network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?"
      },
      {
        "count": 9,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 5,
        "statement": "SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?"
      },
      {
        "count": 4,
        "statement": "SELECT target_ieee FROM topology_links WHERE snapshot_id = ? AND source_ieee = ?"
      }
    ]
  },
  "dashboard": {
    "category_counts": {
      "read.availability_changes": 7,
      "read.bridge_snapshots": 2,
      "read.devices": 37,
      "read.events": 1,
      "read.ha_enrichment": 44,
      "read.incident_devices": 88,
      "read.incidents": 25,
      "read.networks": 47,
      "read.schema": 49,
      "read.topology_links": 17,
      "read.topology_nodes": 4,
      "read.topology_snapshots": 7
    },
    "commit_count": 0,
    "execute_count": 328,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 88,
        "statement": "SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?"
      },
      {
        "count": 49,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 43,
        "statement": "SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?"
      },
      {
        "count": 26,
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name"
      },
      {
        "count": 24,
        "statement": "SELECT COUNT(*) FROM devices"
      }
    ]
  },
  "dashboard_beast": {
    "category_counts": {
      "read.availability_changes": 28,
      "read.bridge_snapshots": 4,
      "read.devices": 191,
      "read.events": 1,
      "read.ha_enrichment": 238,
      "read.incident_devices": 2184,
      "read.incidents": 173,
      "read.networks": 336,
      "read.schema": 250,
      "read.topology_links": 36,
      "read.topology_nodes": 10,
      "read.topology_snapshots": 16
    },
    "commit_count": 0,
    "execute_count": 3467,
    "executemany_count": 0,
    "fixture": "beast",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 2184,
        "statement": "SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?"
      },
      {
        "count": 250,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 236,
        "statement": "SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?"
      },
      {
        "count": 170,
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name"
      },
      {
        "count": 169,
        "statement": "SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE lifecycle_state IN (?) ORDER BY CASE lifecycle_state WHEN ? THEN ? WHEN ? THEN ? ELSE ? END, updated_at DESC"
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
      "read.incident_devices": 4,
      "read.incidents": 3,
      "read.metric_samples": 1,
      "read.networks": 3,
      "read.schema": 6,
      "read.topology_links": 10,
      "read.topology_nodes": 12,
      "read.topology_snapshots": 4
    },
    "commit_count": 0,
    "execute_count": 57,
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
        "count": 4,
        "statement": "SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?"
      },
      {
        "count": 3,
        "statement": "SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?"
      }
    ]
  },
  "devices": {
    "category_counts": {
      "read.availability_changes": 22,
      "read.device_snapshots": 20,
      "read.devices": 42,
      "read.ha_enrichment": 41,
      "read.incident_devices": 80,
      "read.incidents": 40,
      "read.networks": 40,
      "read.schema": 44,
      "read.topology_links": 10,
      "read.topology_nodes": 12,
      "read.topology_snapshots": 4
    },
    "commit_count": 0,
    "execute_count": 355,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 80,
        "statement": "SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?"
      },
      {
        "count": 44,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 40,
        "statement": "SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?"
      },
      {
        "count": 20,
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name"
      },
      {
        "count": 20,
        "statement": "SELECT COUNT(*) FROM devices"
      }
    ]
  },
  "devices_beast": {
    "category_counts": {
      "read.availability_changes": 168,
      "read.device_snapshots": 164,
      "read.devices": 331,
      "read.ha_enrichment": 330,
      "read.incident_devices": 2132,
      "read.incidents": 328,
      "read.networks": 328,
      "read.schema": 336,
      "read.topology_links": 20,
      "read.topology_nodes": 24,
      "read.topology_snapshots": 8
    },
    "commit_count": 0,
    "execute_count": 4169,
    "executemany_count": 0,
    "fixture": "beast",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 2132,
        "statement": "SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?"
      },
      {
        "count": 336,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 328,
        "statement": "SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?"
      },
      {
        "count": 164,
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name"
      },
      {
        "count": 164,
        "statement": "SELECT COUNT(*) FROM devices"
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
      "read.devices": 10,
      "read.events": 1,
      "read.ha_enrichment": 4,
      "read.incident_devices": 2,
      "read.incidents": 4,
      "read.schema": 7,
      "read.topology_links": 10,
      "read.topology_nodes": 12,
      "read.topology_snapshots": 4
    },
    "commit_count": 0,
    "execute_count": 62,
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
        "count": 9,
        "statement": "SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM devices d LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address WHERE d.network_id = ? AND d.ieee_address = ?"
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
  "incident_list": {
    "category_counts": {
      "read.availability_changes": 7,
      "read.device_snapshots": 5,
      "read.devices": 23,
      "read.events": 5,
      "read.ha_enrichment": 6,
      "read.incident_devices": 10,
      "read.incidents": 6,
      "read.schema": 9,
      "read.topology_links": 10,
      "read.topology_nodes": 12,
      "read.topology_snapshots": 4
    },
    "commit_count": 0,
    "execute_count": 97,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 22,
        "statement": "SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM devices d LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address WHERE d.network_id = ? AND d.ieee_address = ?"
      },
      {
        "count": 12,
        "statement": "SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address"
      },
      {
        "count": 10,
        "statement": "SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?"
      },
      {
        "count": 10,
        "statement": "SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?"
      },
      {
        "count": 9,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      }
    ]
  },
  "inventory_ingestion_beast": {
    "category_counts": {
      "read.networks": 6,
      "read.devices": 7,
      "read.incidents": 20,
      "read.incident_devices": 18,
      "read.schema": 53,
      "read.topology_snapshots": 45,
      "read.topology_nodes": 47,
      "read.topology_links": 49,
      "write.devices": 164,
      "write.device_current_state": 164,
      "read.unresolved": 2,
      "write.events": 5,
      "transaction.commit": 27,
      "read.availability_changes": 168,
      "read.device_current_state": 2,
      "read.health_snapshots": 168,
      "write.health_snapshots": 17,
      "read.ha_enrichment": 8,
      "write.incidents": 3,
      "write.incident_devices": 17
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
      "read.networks": 3,
      "read.devices": 4,
      "read.incidents": 3,
      "read.incident_devices": 2,
      "read.schema": 8,
      "read.topology_snapshots": 5,
      "read.topology_nodes": 6,
      "read.topology_links": 6,
      "write.devices": 20,
      "write.device_current_state": 20,
      "read.unresolved": 1,
      "write.events": 3,
      "transaction.commit": 9,
      "read.availability_changes": 21,
      "read.device_current_state": 1,
      "read.health_snapshots": 22,
      "write.health_snapshots": 3,
      "read.ha_enrichment": 3,
      "write.incidents": 2,
      "write.incident_devices": 3
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
      "read.networks": 3,
      "read.devices": 2,
      "read.incidents": 3,
      "read.incident_devices": 2,
      "read.schema": 8,
      "read.topology_snapshots": 5,
      "read.topology_nodes": 6,
      "read.topology_links": 6,
      "write.device_current_state": 2,
      "write.device_snapshots": 1,
      "write.metric_samples": 2,
      "write.events": 2,
      "transaction.commit": 3,
      "read.availability_changes": 21,
      "read.device_current_state": 1,
      "read.health_snapshots": 22,
      "read.ha_enrichment": 3,
      "write.incidents": 1
    },
    "commit_count": 3,
    "execute_count": 90,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
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
      },
      {
        "count": 5,
        "statement": "SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?"
      },
      {
        "count": 5,
        "statement": "SELECT friendly_name FROM topology_nodes WHERE snapshot_id = ? AND ieee_address = ?"
      }
    ]
  },
  "report_device": {
    "category_counts": {
      "read.availability_changes": 18,
      "read.bridge_snapshots": 3,
      "read.device_snapshots": 6,
      "read.devices": 70,
      "read.events": 8,
      "read.ha_enrichment": 55,
      "read.incident_devices": 110,
      "read.incidents": 36,
      "read.metric_samples": 1,
      "read.networks": 55,
      "read.schema": 66,
      "read.topology_links": 37,
      "read.topology_nodes": 28,
      "read.topology_snapshots": 17
    },
    "commit_count": 0,
    "execute_count": 510,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 110,
        "statement": "SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?"
      },
      {
        "count": 66,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 51,
        "statement": "SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?"
      },
      {
        "count": 37,
        "statement": "SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?"
      },
      {
        "count": 32,
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name"
      }
    ]
  },
  "report_full": {
    "category_counts": {
      "read.availability_changes": 36,
      "read.bridge_snapshots": 3,
      "read.device_snapshots": 25,
      "read.devices": 106,
      "read.events": 7,
      "read.ha_enrichment": 92,
      "read.incident_devices": 182,
      "read.incidents": 72,
      "read.networks": 90,
      "read.schema": 103,
      "read.topology_links": 37,
      "read.topology_nodes": 28,
      "read.topology_snapshots": 17
    },
    "commit_count": 0,
    "execute_count": 798,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 182,
        "statement": "SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?"
      },
      {
        "count": 103,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 88,
        "statement": "SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?"
      },
      {
        "count": 49,
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name"
      },
      {
        "count": 46,
        "statement": "SELECT COUNT(*) FROM devices"
      }
    ]
  },
  "report_incident": {
    "category_counts": {
      "read.availability_changes": 27,
      "read.bridge_snapshots": 3,
      "read.device_snapshots": 11,
      "read.devices": 88,
      "read.events": 11,
      "read.ha_enrichment": 65,
      "read.incident_devices": 128,
      "read.incidents": 51,
      "read.metric_samples": 3,
      "read.networks": 65,
      "read.schema": 79,
      "read.topology_links": 47,
      "read.topology_nodes": 40,
      "read.topology_snapshots": 21
    },
    "commit_count": 0,
    "execute_count": 639,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 128,
        "statement": "SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?"
      },
      {
        "count": 79,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 60,
        "statement": "SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?"
      },
      {
        "count": 47,
        "statement": "SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?"
      },
      {
        "count": 40,
        "statement": "SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address"
      }
    ]
  },
  "report_network": {
    "category_counts": {
      "read.availability_changes": 36,
      "read.bridge_snapshots": 3,
      "read.device_snapshots": 25,
      "read.devices": 106,
      "read.events": 7,
      "read.ha_enrichment": 92,
      "read.incident_devices": 182,
      "read.incidents": 72,
      "read.networks": 90,
      "read.schema": 103,
      "read.topology_links": 37,
      "read.topology_nodes": 28,
      "read.topology_snapshots": 17
    },
    "commit_count": 0,
    "execute_count": 798,
    "executemany_count": 0,
    "fixture": "compact",
    "rollback_count": 0,
    "state": "warm",
    "top_repeated_statements": [
      {
        "count": 182,
        "statement": "SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?"
      },
      {
        "count": 103,
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?"
      },
      {
        "count": 88,
        "statement": "SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?"
      },
      {
        "count": 49,
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name"
      },
      {
        "count": 46,
        "statement": "SELECT COUNT(*) FROM devices"
      }
    ]
  }
}''')
