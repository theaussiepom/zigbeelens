-- Phase 3: extended health snapshot fields

ALTER TABLE health_snapshots ADD COLUMN scope TEXT NOT NULL DEFAULT 'device';
ALTER TABLE health_snapshots ADD COLUMN flags_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE health_snapshots ADD COLUMN counter_evidence_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE health_snapshots ADD COLUMN summary TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_health_snapshots_scope ON health_snapshots(scope, network_id, ieee_address, captured_at DESC);
