-- add columns for TOTP-support in participants

ALTER TABLE participants
    ADD COLUMN totp_token TEXT,
    ADD COLUMN totp_verified BOOLEAN DEFAULT false;
