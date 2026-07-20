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
        "ingestion_execute_count": 6,
        "ingestion_commit_count": 1,
        "ingestion_rollback_count": 0,
        "post_commit_execute_count": 38,
        "post_commit_commit_count": 7,
        "post_commit_rollback_count": 0,
        "total_execute_count": 44,
        "total_commit_count": 8,
        "total_rollback_count": 0
    },
    "availability_ingestion_beast": {
        "ingestion_execute_count": 6,
        "ingestion_commit_count": 1,
        "ingestion_rollback_count": 0,
        "post_commit_execute_count": 67,
        "post_commit_commit_count": 7,
        "post_commit_rollback_count": 0,
        "total_execute_count": 73,
        "total_commit_count": 8,
        "total_rollback_count": 0
    },
    "inventory_ingestion_beast": {
        "ingestion_execute_count": 334,
        "ingestion_commit_count": 2,
        "ingestion_rollback_count": 0,
        "post_commit_execute_count": 625,
        "post_commit_commit_count": 25,
        "post_commit_rollback_count": 0,
        "total_execute_count": 959,
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
        "ingestion_execute_count": 7,
        "ingestion_commit_count": 1,
        "ingestion_rollback_count": 0,
        "post_commit_execute_count": 27,
        "post_commit_commit_count": 2,
        "post_commit_rollback_count": 0,
        "total_execute_count": 34,
        "total_commit_count": 3,
        "total_rollback_count": 0
    },
    "payload_ingestion_beast": {
        "ingestion_execute_count": 7,
        "ingestion_commit_count": 1,
        "ingestion_rollback_count": 0,
        "post_commit_execute_count": 51,
        "post_commit_commit_count": 2,
        "post_commit_rollback_count": 0,
        "total_execute_count": 58,
        "total_commit_count": 3,
        "total_rollback_count": 0
    }
}


# Track 3E report execute totals (historical) before scope-first composition.
TRACK_3E_REPORT_EXECUTE_TOTALS: dict[str, int] = {
    "report_full": 262,
    "report_network": 262,
    "report_incident": 317,
    "report_device": 237,
}


# Track 3F read-surface execute totals (historical) before shared network evidence.
TRACK_3F_READ_EXECUTE_TOTALS: dict[str, int] = {
    "dashboard": 110,
    "dashboard_beast": 282,
    "devices": 83,
    "devices_beast": 405,
    "device_detail": 55,
    "incident_list": 52,
    "incident_list_history": 131,
    "evidence_graph": 99,
    "report_full": 187,
    "report_full_beast": 663,
    "report_network": 187,
    "report_network_beast": 421,
    "report_incident": 175,
    "report_device": 151
}

# Track 3G current read-surface execute totals after shared network evidence composition.
TRACK_3G_READ_EXECUTE_TOTALS: dict[str, int] = {
    "dashboard": 22,
    "dashboard_beast": 25,
    "devices": 57,
    "devices_beast": 345,
    "device_detail": 29,
    "incident_list": 27,
    "incident_list_history": 93,
    "evidence_graph": 11,
    "report_full": 67,
    "report_full_beast": 358,
    "report_network": 67,
    "report_network_beast": 267,
    "report_incident": 56,
    "report_device": 32,
    "report_incident_history": 56,
    "report_device_history": 32
}

# Track 5 tip read totals after decision-only Dashboard/Devices badge bulk prefetch.
TRACK_5_READ_EXECUTE_TOTALS: dict[str, int] = {
    "dashboard": 24,
    "dashboard_beast": 27,
    "devices": 19,
    "devices_beast": 19,
    "device_detail": 23,
    "incident_list": 19,
    "incident_list_history": 19,
    "evidence_graph": 11,
    "report_full": 29,
    "report_full_beast": 32,
    "report_network": 29,
    "report_network_beast": 29,
    "report_incident": 40,
    "report_device": 29,
    "report_incident_history": 40,
    "report_device_history": 29
}

# Exact Track 5 total-operation snapshots. They are not product budgets.
EXPECTED_BASELINES: dict[str, dict[str, object]] = json.loads(r'''{
  "availability_ingestion": {
    "fixture": "compact",
    "state": "warm",
    "execute_count": 44,
    "executemany_count": 0,
    "commit_count": 8,
    "rollback_count": 0,
    "category_counts": {
      "read.networks": 3,
      "read.devices": 2,
      "read.incidents": 3,
      "read.incident_devices": 2,
      "read.schema": 3,
      "read.topology_snapshots": 1,
      "read.topology_nodes": 2,
      "read.topology_links": 3,
      "read.device_current_state": 2,
      "write.device_current_state": 2,
      "write.availability_changes": 1,
      "write.events": 3,
      "transaction.commit": 8,
      "read.availability_changes": 2,
      "read.health_snapshots": 3,
      "write.health_snapshots": 2,
      "read.ha_enrichment": 2,
      "write.incidents": 2,
      "write.incident_devices": 4,
      "write.incident_networks": 2
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 3
      },
      {
        "statement": "INSERT INTO events ( id, network_id, ieee_address, event_type, severity, title, summary, incident_id, payload_json, occurred_at ) VALUES (?)",
        "count": 3
      },
      {
        "statement": "SELECT source_ieee FROM topology_links WHERE snapshot_id = ? AND target_ieee = ? LIMIT ?",
        "count": 3
      },
      {
        "statement": "INSERT INTO incident_devices (incident_id, network_id, ieee_address, role) VALUES (?)",
        "count": 3
      },
      {
        "statement": "SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ? ORDER BY network_id, ieee_address, role",
        "count": 2
      }
    ]
  },
  "availability_ingestion_beast": {
    "fixture": "beast",
    "state": "warm",
    "execute_count": 73,
    "executemany_count": 0,
    "commit_count": 8,
    "rollback_count": 0,
    "category_counts": {
      "read.networks": 3,
      "read.devices": 2,
      "read.incidents": 10,
      "read.incident_devices": 9,
      "read.schema": 5,
      "read.topology_snapshots": 3,
      "read.topology_nodes": 4,
      "read.topology_links": 5,
      "read.device_current_state": 2,
      "write.device_current_state": 2,
      "write.availability_changes": 1,
      "write.events": 3,
      "transaction.commit": 8,
      "read.availability_changes": 3,
      "read.health_snapshots": 3,
      "write.health_snapshots": 2,
      "read.ha_enrichment": 2,
      "write.incidents": 2,
      "write.incident_devices": 10,
      "write.incident_networks": 2
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ? ORDER BY network_id, ieee_address, role",
        "count": 9
      },
      {
        "statement": "WITH selected AS ( SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE dedup_key = ? AND lifecycle_state IN (?) ORDER BY updated_at DESC LIMIT ? ) SELECT s.id, s.incident_type, s.lifecycle_state, s.severity, s.scope, s.confidence, s.title, s.summary, s.explanation, s.evidence_json, s.counter_evidence_json, s.limitations_json, s.opened_at, s.updated_at, s.resolved_at, s.dedup_key, n.network_id FROM selected s LEFT JOIN incident_networks n ON n.incident_id = s.id ORDER BY n.network_id",
        "count": 9
      },
      {
        "statement": "INSERT INTO incident_devices (incident_id, network_id, ieee_address, role) VALUES (?)",
        "count": 9
      },
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 5
      },
      {
        "statement": "SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?",
        "count": 3
      }
    ]
  },
  "dashboard": {
    "fixture": "compact",
    "state": "warm",
    "execute_count": 24,
    "executemany_count": 0,
    "commit_count": 0,
    "rollback_count": 0,
    "category_counts": {
      "read.networks": 3,
      "read.devices": 3,
      "read.events": 1,
      "read.incidents": 1,
      "read.incident_devices": 1,
      "read.schema": 3,
      "read.topology_snapshots": 1,
      "read.topology_nodes": 1,
      "read.topology_links": 1,
      "read.incident_networks": 1,
      "read.ha_enrichment": 3,
      "read.availability_changes": 3,
      "read.device_snapshots": 1,
      "read.bridge_snapshots": 1
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name",
        "count": 3
      },
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 3
      },
      {
        "statement": "SELECT COUNT(*) FROM devices",
        "count": 2
      },
      {
        "statement": "WITH requested(network_id, ieee_address) AS (VALUES (?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?)) SELECT h.network_id, h.ieee_address, h.ha_device_id, h.ha_device_name, h.area_id, h.area_name, h.entity_id, h.match_confidence, h.updated_at FROM requested r JOIN ha_device_enrichment h ON h.network_id = r.network_id AND h.ieee_address = r.ieee_address ORDER BY h.network_id, h.ieee_address",
        "count": 2
      },
      {
        "statement": "SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM devices d LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address ORDER BY d.network_id, d.friendly_name",
        "count": 1
      }
    ]
  },
  "dashboard_beast": {
    "fixture": "beast",
    "state": "warm",
    "execute_count": 27,
    "executemany_count": 0,
    "commit_count": 0,
    "rollback_count": 0,
    "category_counts": {
      "read.networks": 3,
      "read.devices": 3,
      "read.events": 1,
      "read.incidents": 1,
      "read.incident_devices": 1,
      "read.schema": 4,
      "read.topology_snapshots": 1,
      "read.topology_nodes": 1,
      "read.topology_links": 1,
      "read.incident_networks": 1,
      "read.ha_enrichment": 4,
      "read.availability_changes": 3,
      "read.device_snapshots": 1,
      "read.bridge_snapshots": 2
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 4
      },
      {
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name",
        "count": 3
      },
      {
        "statement": "SELECT COUNT(*) FROM devices",
        "count": 2
      },
      {
        "statement": "WITH requested(network_id, ieee_address) AS (VALUES (?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?)) SELECT h.network_id, h.ieee_address, h.ha_device_id, h.ha_device_name, h.area_id, h.area_name, h.entity_id, h.match_confidence, h.updated_at FROM requested r JOIN ha_device_enrichment h ON h.network_id = r.network_id AND h.ieee_address = r.ieee_address ORDER BY h.network_id, h.ieee_address",
        "count": 2
      },
      {
        "statement": "SELECT coordinator_ieee, channel, pan_id, extended_pan_id, payload_json, captured_at FROM bridge_snapshots WHERE network_id = ? ORDER BY captured_at DESC LIMIT ?",
        "count": 2
      }
    ]
  },
  "device_detail": {
    "fixture": "compact",
    "state": "warm",
    "execute_count": 23,
    "executemany_count": 0,
    "commit_count": 0,
    "rollback_count": 0,
    "category_counts": {
      "read.networks": 1,
      "read.devices": 2,
      "read.events": 1,
      "read.incidents": 2,
      "read.incident_devices": 1,
      "read.schema": 3,
      "read.topology_snapshots": 1,
      "read.topology_nodes": 1,
      "read.topology_links": 1,
      "read.availability_changes": 4,
      "read.ha_enrichment": 3,
      "read.device_snapshots": 1,
      "read.incident_networks": 1,
      "read.metric_samples": 1
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 3
      },
      {
        "statement": "SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?",
        "count": 2
      },
      {
        "statement": "SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?",
        "count": 2
      },
      {
        "statement": "SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM devices d LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address WHERE d.network_id = ? AND d.ieee_address = ?",
        "count": 1
      },
      {
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks WHERE id IN (?)",
        "count": 1
      }
    ]
  },
  "devices": {
    "fixture": "compact",
    "state": "warm",
    "execute_count": 19,
    "executemany_count": 0,
    "commit_count": 0,
    "rollback_count": 0,
    "category_counts": {
      "read.networks": 3,
      "read.devices": 2,
      "read.incidents": 1,
      "read.incident_devices": 1,
      "read.schema": 2,
      "read.topology_snapshots": 1,
      "read.topology_nodes": 1,
      "read.topology_links": 1,
      "read.incident_networks": 1,
      "read.ha_enrichment": 2,
      "read.availability_changes": 3,
      "read.device_snapshots": 1
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name",
        "count": 2
      },
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 2
      },
      {
        "statement": "SELECT COUNT(*) FROM devices",
        "count": 1
      },
      {
        "statement": "SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM devices d LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address ORDER BY d.network_id, d.friendly_name",
        "count": 1
      },
      {
        "statement": "SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE lifecycle_state IN (?) ORDER BY CASE lifecycle_state WHEN ? THEN ? WHEN ? THEN ? ELSE ? END, updated_at DESC, id DESC",
        "count": 1
      }
    ]
  },
  "devices_beast": {
    "fixture": "beast",
    "state": "warm",
    "execute_count": 19,
    "executemany_count": 0,
    "commit_count": 0,
    "rollback_count": 0,
    "category_counts": {
      "read.networks": 3,
      "read.devices": 2,
      "read.incidents": 1,
      "read.incident_devices": 1,
      "read.schema": 2,
      "read.topology_snapshots": 1,
      "read.topology_nodes": 1,
      "read.topology_links": 1,
      "read.incident_networks": 1,
      "read.ha_enrichment": 2,
      "read.availability_changes": 3,
      "read.device_snapshots": 1
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name",
        "count": 2
      },
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 2
      },
      {
        "statement": "SELECT COUNT(*) FROM devices",
        "count": 1
      },
      {
        "statement": "SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM devices d LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address ORDER BY d.network_id, d.friendly_name",
        "count": 1
      },
      {
        "statement": "SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE lifecycle_state IN (?) ORDER BY CASE lifecycle_state WHEN ? THEN ? WHEN ? THEN ? ELSE ? END, updated_at DESC, id DESC",
        "count": 1
      }
    ]
  },
  "evidence_graph": {
    "fixture": "compact",
    "state": "warm",
    "execute_count": 11,
    "executemany_count": 0,
    "commit_count": 0,
    "rollback_count": 0,
    "category_counts": {
      "read.networks": 1,
      "read.devices": 1,
      "read.schema": 2,
      "read.topology_snapshots": 1,
      "read.topology_nodes": 1,
      "read.topology_links": 1,
      "read.availability_changes": 2,
      "read.ha_enrichment": 2
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 2
      },
      {
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks WHERE id = ?",
        "count": 1
      },
      {
        "statement": "SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM devices d LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address WHERE d.network_id IN (?) ORDER BY d.network_id ASC, d.friendly_name ASC",
        "count": 1
      },
      {
        "statement": "SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id IN (?) ORDER BY network_id ASC, captured_at DESC",
        "count": 1
      },
      {
        "statement": "SELECT snapshot_id, source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id IN (?) ORDER BY snapshot_id ASC",
        "count": 1
      }
    ]
  },
  "incident_detail": {
    "fixture": "compact",
    "state": "warm",
    "execute_count": 19,
    "executemany_count": 0,
    "commit_count": 0,
    "rollback_count": 0,
    "category_counts": {
      "read.networks": 1,
      "read.devices": 2,
      "read.events": 1,
      "read.incidents": 2,
      "read.incident_devices": 1,
      "read.schema": 2,
      "read.topology_snapshots": 1,
      "read.topology_nodes": 1,
      "read.topology_links": 1,
      "read.incident_networks": 1,
      "read.availability_changes": 3,
      "read.ha_enrichment": 2,
      "read.device_snapshots": 1
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 2
      },
      {
        "statement": "SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE id = ?",
        "count": 1
      },
      {
        "statement": "SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id IN (?) ORDER BY incident_id, network_id, ieee_address, role",
        "count": 1
      },
      {
        "statement": "WITH requested(network_id, ieee_address) AS (VALUES (?),(?, ?),(?, ?)) SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM requested r JOIN devices d ON d.network_id = r.network_id AND d.ieee_address = r.ieee_address LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address ORDER BY d.network_id, d.ieee_address",
        "count": 1
      },
      {
        "statement": "SELECT id, network_id, ieee_address, event_type, severity, title, summary, incident_id, occurred_at FROM ( SELECT id, network_id, ieee_address, event_type, severity, title, summary, incident_id, occurred_at, ROW_NUMBER() OVER ( PARTITION BY incident_id ORDER BY occurred_at DESC, id DESC ) AS rn FROM events WHERE incident_id IN (?) ) WHERE rn <= ? ORDER BY incident_id, occurred_at DESC, id DESC",
        "count": 1
      }
    ]
  },
  "incident_list": {
    "fixture": "compact",
    "state": "warm",
    "execute_count": 19,
    "executemany_count": 0,
    "commit_count": 0,
    "rollback_count": 0,
    "category_counts": {
      "read.networks": 1,
      "read.devices": 2,
      "read.incidents": 3,
      "read.incident_devices": 1,
      "read.schema": 2,
      "read.topology_snapshots": 1,
      "read.topology_nodes": 1,
      "read.topology_links": 1,
      "read.incident_networks": 1,
      "read.availability_changes": 3,
      "read.ha_enrichment": 2,
      "read.device_snapshots": 1
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 2
      },
      {
        "statement": "SELECT COUNT(*) AS n FROM incidents WHERE lifecycle_state IN (?)",
        "count": 1
      },
      {
        "statement": "SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE CASE lifecycle_state WHEN ? THEN ? WHEN ? THEN ? ELSE ? END IN (?) ORDER BY CASE lifecycle_state WHEN ? THEN ? WHEN ? THEN ? ELSE ? END ASC, updated_at DESC, id DESC LIMIT ?",
        "count": 1
      },
      {
        "statement": "SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id IN (?) ORDER BY incident_id, network_id, ieee_address, role",
        "count": 1
      },
      {
        "statement": "WITH requested(network_id, ieee_address) AS (VALUES (?),(?, ?),(?, ?),(?, ?),(?, ?)) SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM requested r JOIN devices d ON d.network_id = r.network_id AND d.ieee_address = r.ieee_address LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address ORDER BY d.network_id, d.ieee_address",
        "count": 1
      }
    ]
  },
  "incident_list_history": {
    "fixture": "history",
    "state": "warm",
    "execute_count": 19,
    "executemany_count": 0,
    "commit_count": 0,
    "rollback_count": 0,
    "category_counts": {
      "read.incidents": 3,
      "read.incident_devices": 1,
      "read.devices": 2,
      "read.incident_networks": 1,
      "read.networks": 1,
      "read.topology_snapshots": 1,
      "read.topology_links": 1,
      "read.topology_nodes": 1,
      "read.availability_changes": 3,
      "read.schema": 2,
      "read.ha_enrichment": 2,
      "read.device_snapshots": 1
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 2
      },
      {
        "statement": "SELECT COUNT(*) AS n FROM incidents WHERE lifecycle_state IN (?)",
        "count": 1
      },
      {
        "statement": "SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE CASE lifecycle_state WHEN ? THEN ? WHEN ? THEN ? ELSE ? END IN (?) ORDER BY CASE lifecycle_state WHEN ? THEN ? WHEN ? THEN ? ELSE ? END ASC, updated_at DESC, id DESC LIMIT ?",
        "count": 1
      },
      {
        "statement": "SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id IN (?) ORDER BY incident_id, network_id, ieee_address, role",
        "count": 1
      },
      {
        "statement": "WITH requested(network_id, ieee_address) AS (VALUES (?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?)) SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM requested r JOIN devices d ON d.network_id = r.network_id AND d.ieee_address = r.ieee_address LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address ORDER BY d.network_id, d.ieee_address",
        "count": 1
      }
    ]
  },
  "inventory_ingestion_beast": {
    "fixture": "beast",
    "state": "warm",
    "execute_count": 959,
    "executemany_count": 0,
    "commit_count": 27,
    "rollback_count": 0,
    "category_counts": {
      "read.networks": 6,
      "read.devices": 7,
      "read.incidents": 20,
      "read.incident_devices": 18,
      "read.schema": 49,
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
      "read.ha_enrichment": 4,
      "write.incidents": 3,
      "write.incident_devices": 17,
      "write.incident_networks": 4
    },
    "top_repeated_statements": [
      {
        "statement": "INSERT INTO devices ( network_id, ieee_address, friendly_name, device_type, power_source, manufacturer, model, interview_state, created_at, updated_at ) VALUES (?) ON CONFLICT(network_id, ieee_address) DO UPDATE SET friendly_name = excluded.friendly_name, device_type = excluded.device_type, power_source = excluded.power_source, manufacturer = COALESCE(excluded.manufacturer, devices.manufacturer), model = COALESCE(excluded.model, devices.model), interview_state = excluded.interview_state, updated_at = excluded.updated_at",
        "count": 164
      },
      {
        "statement": "INSERT OR IGNORE INTO device_current_state (network_id, ieee_address) VALUES (?)",
        "count": 164
      },
      {
        "statement": "SELECT COUNT(*) FROM availability_changes WHERE network_id = ? AND ieee_address = ? AND changed_at >= ?",
        "count": 164
      },
      {
        "statement": "SELECT primary_health, severity, confidence, summary, flags_json, evidence_json, counter_evidence_json, limitations_json, captured_at FROM health_snapshots WHERE scope = ? AND network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?",
        "count": 164
      },
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 49
      }
    ]
  },
  "inventory_ingestion_compact": {
    "fixture": "compact",
    "state": "warm",
    "execute_count": 136,
    "executemany_count": 0,
    "commit_count": 9,
    "rollback_count": 0,
    "category_counts": {
      "read.networks": 3,
      "read.devices": 4,
      "read.incidents": 3,
      "read.incident_devices": 2,
      "read.schema": 7,
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
      "read.ha_enrichment": 2,
      "write.incidents": 2,
      "write.incident_devices": 3,
      "write.incident_networks": 2
    },
    "top_repeated_statements": [
      {
        "statement": "INSERT INTO devices ( network_id, ieee_address, friendly_name, device_type, power_source, manufacturer, model, interview_state, created_at, updated_at ) VALUES (?) ON CONFLICT(network_id, ieee_address) DO UPDATE SET friendly_name = excluded.friendly_name, device_type = excluded.device_type, power_source = excluded.power_source, manufacturer = COALESCE(excluded.manufacturer, devices.manufacturer), model = COALESCE(excluded.model, devices.model), interview_state = excluded.interview_state, updated_at = excluded.updated_at",
        "count": 20
      },
      {
        "statement": "INSERT OR IGNORE INTO device_current_state (network_id, ieee_address) VALUES (?)",
        "count": 20
      },
      {
        "statement": "SELECT COUNT(*) FROM availability_changes WHERE network_id = ? AND ieee_address = ? AND changed_at >= ?",
        "count": 20
      },
      {
        "statement": "SELECT primary_health, severity, confidence, summary, flags_json, evidence_json, counter_evidence_json, limitations_json, captured_at FROM health_snapshots WHERE scope = ? AND network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?",
        "count": 20
      },
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 7
      }
    ]
  },
  "payload_ingestion": {
    "fixture": "compact",
    "state": "warm",
    "execute_count": 34,
    "executemany_count": 0,
    "commit_count": 3,
    "rollback_count": 0,
    "category_counts": {
      "read.networks": 3,
      "read.devices": 2,
      "read.incidents": 3,
      "read.incident_devices": 2,
      "read.schema": 3,
      "read.topology_snapshots": 1,
      "read.topology_nodes": 2,
      "read.topology_links": 2,
      "write.device_current_state": 2,
      "write.device_snapshots": 1,
      "write.metric_samples": 2,
      "write.events": 2,
      "transaction.commit": 3,
      "read.availability_changes": 2,
      "read.device_current_state": 1,
      "read.health_snapshots": 3,
      "read.ha_enrichment": 2,
      "write.incidents": 1
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 3
      },
      {
        "statement": "SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ? ORDER BY network_id, ieee_address, role",
        "count": 2
      },
      {
        "statement": "INSERT INTO metric_samples (network_id, ieee_address, metric_name, metric_value, sampled_at) VALUES (?)",
        "count": 2
      },
      {
        "statement": "INSERT INTO events ( id, network_id, ieee_address, event_type, severity, title, summary, incident_id, payload_json, occurred_at ) VALUES (?)",
        "count": 2
      },
      {
        "statement": "SELECT primary_health, severity, confidence, summary, flags_json, evidence_json, counter_evidence_json, limitations_json, captured_at FROM health_snapshots WHERE scope = ? AND network_id = ? AND ieee_address IS NULL ORDER BY captured_at DESC LIMIT ?",
        "count": 2
      }
    ]
  },
  "payload_ingestion_beast": {
    "fixture": "beast",
    "state": "warm",
    "execute_count": 58,
    "executemany_count": 0,
    "commit_count": 3,
    "rollback_count": 0,
    "category_counts": {
      "read.networks": 3,
      "read.devices": 2,
      "read.incidents": 10,
      "read.incident_devices": 9,
      "read.schema": 5,
      "read.topology_snapshots": 3,
      "read.topology_nodes": 4,
      "read.topology_links": 5,
      "write.device_current_state": 2,
      "write.device_snapshots": 1,
      "write.metric_samples": 2,
      "write.events": 2,
      "transaction.commit": 3,
      "read.availability_changes": 3,
      "read.device_current_state": 1,
      "read.health_snapshots": 3,
      "read.ha_enrichment": 2,
      "write.incidents": 1
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ? ORDER BY network_id, ieee_address, role",
        "count": 9
      },
      {
        "statement": "WITH selected AS ( SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE dedup_key = ? AND lifecycle_state IN (?) ORDER BY updated_at DESC LIMIT ? ) SELECT s.id, s.incident_type, s.lifecycle_state, s.severity, s.scope, s.confidence, s.title, s.summary, s.explanation, s.evidence_json, s.counter_evidence_json, s.limitations_json, s.opened_at, s.updated_at, s.resolved_at, s.dedup_key, n.network_id FROM selected s LEFT JOIN incident_networks n ON n.incident_id = s.id ORDER BY n.network_id",
        "count": 9
      },
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 5
      },
      {
        "statement": "SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?",
        "count": 3
      },
      {
        "statement": "SELECT friendly_name FROM topology_nodes WHERE snapshot_id = ? AND ieee_address = ?",
        "count": 3
      }
    ]
  },
  "report_device": {
    "fixture": "compact",
    "state": "warm",
    "execute_count": 29,
    "executemany_count": 0,
    "commit_count": 0,
    "rollback_count": 0,
    "category_counts": {
      "read.networks": 2,
      "read.devices": 4,
      "read.events": 1,
      "read.incidents": 2,
      "read.schema": 4,
      "read.topology_snapshots": 3,
      "read.topology_nodes": 1,
      "read.topology_links": 1,
      "read.availability_changes": 4,
      "read.ha_enrichment": 4,
      "read.device_snapshots": 1,
      "read.metric_samples": 1,
      "read.bridge_snapshots": 1
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 4
      },
      {
        "statement": "SELECT COUNT(*) FROM topology_snapshots WHERE network_id IN (?)",
        "count": 2
      },
      {
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name",
        "count": 1
      },
      {
        "statement": "SELECT COUNT(*) FROM devices",
        "count": 1
      },
      {
        "statement": "SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM devices d LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address WHERE d.network_id = ? AND d.ieee_address = ?",
        "count": 1
      }
    ]
  },
  "report_device_history": {
    "fixture": "history",
    "state": "warm",
    "execute_count": 29,
    "executemany_count": 0,
    "commit_count": 0,
    "rollback_count": 0,
    "category_counts": {
      "read.devices": 4,
      "read.networks": 2,
      "read.incidents": 2,
      "read.topology_snapshots": 3,
      "read.topology_links": 1,
      "read.topology_nodes": 1,
      "read.availability_changes": 4,
      "read.schema": 4,
      "read.ha_enrichment": 4,
      "read.device_snapshots": 1,
      "read.metric_samples": 1,
      "read.events": 1,
      "read.bridge_snapshots": 1
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 4
      },
      {
        "statement": "SELECT COUNT(*) FROM topology_snapshots WHERE network_id IN (?)",
        "count": 2
      },
      {
        "statement": "SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM devices d LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address WHERE d.network_id = ? AND d.ieee_address = ?",
        "count": 1
      },
      {
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks WHERE id IN (?)",
        "count": 1
      },
      {
        "statement": "WITH requested(network_id, ieee_address) AS (VALUES (?)) SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM requested r JOIN devices d ON d.network_id = r.network_id AND d.ieee_address = r.ieee_address LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address ORDER BY d.network_id, d.ieee_address",
        "count": 1
      }
    ]
  },
  "report_full": {
    "fixture": "compact",
    "state": "warm",
    "execute_count": 29,
    "executemany_count": 0,
    "commit_count": 0,
    "rollback_count": 0,
    "category_counts": {
      "read.networks": 3,
      "read.devices": 2,
      "read.events": 2,
      "read.incidents": 2,
      "read.incident_devices": 1,
      "read.schema": 4,
      "read.topology_snapshots": 3,
      "read.topology_nodes": 1,
      "read.topology_links": 1,
      "read.incident_networks": 1,
      "read.availability_changes": 3,
      "read.ha_enrichment": 4,
      "read.device_snapshots": 1,
      "read.bridge_snapshots": 1
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 4
      },
      {
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name",
        "count": 3
      },
      {
        "statement": "WITH requested(network_id, ieee_address) AS (VALUES (?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?)) SELECT h.network_id, h.ieee_address, h.ha_device_id, h.ha_device_name, h.area_id, h.area_name, h.entity_id, h.match_confidence, h.updated_at FROM requested r JOIN ha_device_enrichment h ON h.network_id = r.network_id AND h.ieee_address = r.ieee_address ORDER BY h.network_id, h.ieee_address",
        "count": 2
      },
      {
        "statement": "SELECT COUNT(*) FROM topology_snapshots WHERE network_id IN (?)",
        "count": 2
      },
      {
        "statement": "SELECT COUNT(*) FROM devices",
        "count": 1
      }
    ]
  },
  "report_full_beast": {
    "fixture": "beast",
    "state": "warm",
    "execute_count": 32,
    "executemany_count": 0,
    "commit_count": 0,
    "rollback_count": 0,
    "category_counts": {
      "read.networks": 3,
      "read.devices": 2,
      "read.events": 2,
      "read.incidents": 2,
      "read.incident_devices": 1,
      "read.schema": 5,
      "read.topology_snapshots": 3,
      "read.topology_nodes": 1,
      "read.topology_links": 1,
      "read.incident_networks": 1,
      "read.availability_changes": 3,
      "read.ha_enrichment": 5,
      "read.device_snapshots": 1,
      "read.bridge_snapshots": 2
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 5
      },
      {
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name",
        "count": 3
      },
      {
        "statement": "WITH requested(network_id, ieee_address) AS (VALUES (?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?)) SELECT h.network_id, h.ieee_address, h.ha_device_id, h.ha_device_name, h.area_id, h.area_name, h.entity_id, h.match_confidence, h.updated_at FROM requested r JOIN ha_device_enrichment h ON h.network_id = r.network_id AND h.ieee_address = r.ieee_address ORDER BY h.network_id, h.ieee_address",
        "count": 2
      },
      {
        "statement": "SELECT coordinator_ieee, channel, pan_id, extended_pan_id, payload_json, captured_at FROM bridge_snapshots WHERE network_id = ? ORDER BY captured_at DESC LIMIT ?",
        "count": 2
      },
      {
        "statement": "SELECT COUNT(*) FROM topology_snapshots WHERE network_id IN (?)",
        "count": 2
      }
    ]
  },
  "report_incident": {
    "fixture": "compact",
    "state": "warm",
    "execute_count": 40,
    "executemany_count": 0,
    "commit_count": 0,
    "rollback_count": 0,
    "category_counts": {
      "read.networks": 2,
      "read.devices": 3,
      "read.events": 4,
      "read.incidents": 3,
      "read.incident_devices": 2,
      "read.schema": 4,
      "read.topology_snapshots": 3,
      "read.topology_nodes": 1,
      "read.topology_links": 1,
      "read.incident_networks": 2,
      "read.availability_changes": 6,
      "read.ha_enrichment": 4,
      "read.device_snapshots": 1,
      "read.metric_samples": 3,
      "read.bridge_snapshots": 1
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 4
      },
      {
        "statement": "SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?",
        "count": 3
      },
      {
        "statement": "SELECT metric_name, metric_value, sampled_at FROM metric_samples WHERE network_id = ? AND ieee_address = ? ORDER BY sampled_at DESC LIMIT ?",
        "count": 3
      },
      {
        "statement": "SELECT id, network_id, ieee_address, event_type, severity, title, summary, incident_id, occurred_at FROM events WHERE network_id = ? AND ieee_address = ? ORDER BY occurred_at DESC, id DESC LIMIT ?",
        "count": 3
      },
      {
        "statement": "SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE id = ?",
        "count": 2
      }
    ]
  },
  "report_incident_history": {
    "fixture": "history",
    "state": "warm",
    "execute_count": 40,
    "executemany_count": 0,
    "commit_count": 0,
    "rollback_count": 0,
    "category_counts": {
      "read.incidents": 3,
      "read.incident_networks": 2,
      "read.incident_devices": 2,
      "read.networks": 2,
      "read.devices": 3,
      "read.topology_snapshots": 3,
      "read.topology_links": 1,
      "read.topology_nodes": 1,
      "read.availability_changes": 6,
      "read.schema": 4,
      "read.ha_enrichment": 4,
      "read.device_snapshots": 1,
      "read.metric_samples": 3,
      "read.events": 4,
      "read.bridge_snapshots": 1
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 4
      },
      {
        "statement": "SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?",
        "count": 3
      },
      {
        "statement": "SELECT metric_name, metric_value, sampled_at FROM metric_samples WHERE network_id = ? AND ieee_address = ? ORDER BY sampled_at DESC LIMIT ?",
        "count": 3
      },
      {
        "statement": "SELECT id, network_id, ieee_address, event_type, severity, title, summary, incident_id, occurred_at FROM events WHERE network_id = ? AND ieee_address = ? ORDER BY occurred_at DESC, id DESC LIMIT ?",
        "count": 3
      },
      {
        "statement": "SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE id = ?",
        "count": 2
      }
    ]
  },
  "report_network": {
    "fixture": "compact",
    "state": "warm",
    "execute_count": 29,
    "executemany_count": 0,
    "commit_count": 0,
    "rollback_count": 0,
    "category_counts": {
      "read.networks": 3,
      "read.devices": 2,
      "read.events": 2,
      "read.incidents": 2,
      "read.incident_devices": 1,
      "read.schema": 4,
      "read.topology_snapshots": 3,
      "read.topology_nodes": 1,
      "read.topology_links": 1,
      "read.incident_networks": 1,
      "read.availability_changes": 3,
      "read.ha_enrichment": 4,
      "read.device_snapshots": 1,
      "read.bridge_snapshots": 1
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 4
      },
      {
        "statement": "WITH requested(network_id, ieee_address) AS (VALUES (?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?)) SELECT h.network_id, h.ieee_address, h.ha_device_id, h.ha_device_name, h.area_id, h.area_name, h.entity_id, h.match_confidence, h.updated_at FROM requested r JOIN ha_device_enrichment h ON h.network_id = r.network_id AND h.ieee_address = r.ieee_address ORDER BY h.network_id, h.ieee_address",
        "count": 2
      },
      {
        "statement": "SELECT COUNT(*) FROM topology_snapshots WHERE network_id IN (?)",
        "count": 2
      },
      {
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name",
        "count": 1
      },
      {
        "statement": "SELECT COUNT(*) FROM devices",
        "count": 1
      }
    ]
  },
  "report_network_beast": {
    "fixture": "beast",
    "state": "warm",
    "execute_count": 29,
    "executemany_count": 0,
    "commit_count": 0,
    "rollback_count": 0,
    "category_counts": {
      "read.networks": 3,
      "read.devices": 2,
      "read.events": 2,
      "read.incidents": 2,
      "read.incident_devices": 1,
      "read.schema": 4,
      "read.topology_snapshots": 3,
      "read.topology_nodes": 1,
      "read.topology_links": 1,
      "read.incident_networks": 1,
      "read.availability_changes": 3,
      "read.ha_enrichment": 4,
      "read.device_snapshots": 1,
      "read.bridge_snapshots": 1
    },
    "top_repeated_statements": [
      {
        "statement": "SELECT ? FROM sqlite_master WHERE type=? AND name=?",
        "count": 4
      },
      {
        "statement": "SELECT COUNT(*) FROM topology_snapshots WHERE network_id IN (?)",
        "count": 2
      },
      {
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name",
        "count": 1
      },
      {
        "statement": "SELECT COUNT(*) FROM devices",
        "count": 1
      },
      {
        "statement": "SELECT id, name, base_topic, bridge_state FROM networks WHERE id = ?",
        "count": 1
      }
    ]
  }
}''')
