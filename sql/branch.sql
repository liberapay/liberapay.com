ALTER TABLE paydays
    ADD COLUMN stage int,
    ALTER COLUMN stage SET DEFAULT 1;
