ALTER TABLE email_blacklist ADD COLUMN ignored_by bigint REFERENCES participants;
