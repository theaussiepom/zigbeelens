-- Phase 6: first-class diagnostic reports.
-- Extend the reports table with scope, redaction profile, and metadata so
-- stored reports can be listed and downloaded without re-parsing the body.

ALTER TABLE reports ADD COLUMN scope TEXT NOT NULL DEFAULT 'full';
ALTER TABLE reports ADD COLUMN redaction_profile TEXT NOT NULL DEFAULT 'standard';
ALTER TABLE reports ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_reports_generated_at ON reports (generated_at DESC);
