-- Batch 4: distinguish governance breaches from engineering signals.
-- Existing incidents were created by the pre-Batch-4 lifecycle==active path,
-- so the contract default is the honest backfill.
ALTER TABLE dq_incidents ADD COLUMN kind TEXT NOT NULL DEFAULT 'consumer_contract';

-- Notification rules can optionally route by artifact kind. Empty = wildcard,
-- preserving all existing rule behaviour.
ALTER TABLE dq_notification_rules ADD COLUMN match_kind TEXT DEFAULT '';
