ALTER TABLE payins
    ADD COLUMN allowed_by bigint REFERENCES participants,
    ADD COLUMN allowed_since timestamptz,
    ADD CHECK ((allowed_since IS NULL) = (allowed_by IS NULL));
