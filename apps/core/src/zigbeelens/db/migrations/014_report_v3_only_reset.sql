-- Pre-release report contract reset (schema 14).
-- All existing saved reports are development artifacts.
-- Only exact ReportDetailV3 reports are supported after this migration.
-- No other table is affected.
DELETE FROM reports;
