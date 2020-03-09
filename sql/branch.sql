ALTER TYPE blacklist_reason ADD VALUE IF NOT EXISTS 'throwaway';
ALTER TYPE blacklist_reason ADD VALUE IF NOT EXISTS 'other';

ALTER TABLE email_blacklist ADD COLUMN added_by bigint REFERENCES participants;
