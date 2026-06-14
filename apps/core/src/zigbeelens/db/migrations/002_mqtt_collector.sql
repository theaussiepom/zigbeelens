-- Phase 2: MQTT collector support

CREATE TABLE IF NOT EXISTS device_current_state (
    network_id TEXT NOT NULL,
    ieee_address TEXT NOT NULL,
    availability TEXT NOT NULL DEFAULT 'unknown',
    last_seen TEXT,
    last_payload_at TEXT,
    linkquality INTEGER,
    battery INTEGER,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (network_id, ieee_address),
    FOREIGN KEY (network_id, ieee_address) REFERENCES devices(network_id, ieee_address) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS unresolved_device_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    network_id TEXT NOT NULL,
    friendly_name TEXT NOT NULL,
    message_kind TEXT NOT NULL,
    payload_json TEXT,
    received_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_unresolved_device ON unresolved_device_messages(network_id, friendly_name);

CREATE TABLE IF NOT EXISTS collector_status (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 0,
    connected INTEGER NOT NULL DEFAULT 0,
    subscribed_topics_count INTEGER NOT NULL DEFAULT 0,
    last_message_at TEXT,
    last_error TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO collector_status (id) VALUES (1);
