ALTER TABLE statements
    ADD COLUMN id bigserial NOT NULL,
    ADD COLUMN ctime timestamptz NOT NULL DEFAULT '1970-01-01T00:00:00+00'::timestamptz,
    ADD COLUMN mtime timestamptz NOT NULL DEFAULT '1970-01-01T00:00:00+00'::timestamptz;
