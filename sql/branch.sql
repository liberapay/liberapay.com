ALTER TABLE emails ALTER COLUMN participant DROP NOT NULL;
ALTER TABLE emails
    ADD COLUMN disavowed boolean,
    ADD COLUMN disavowed_time timestamptz;
ALTER TABLE emails
    ADD CONSTRAINT not_verified_and_disavowed CHECK (NOT (verified AND disavowed));
