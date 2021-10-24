ALTER TABLE tips ADD COLUMN secrecy_level int;
-- 0 means public, 1 means private, 2 means secret

CREATE OR REPLACE VIEW current_tips AS
    SELECT DISTINCT ON (tipper, tippee) *
      FROM tips
  ORDER BY tipper, tippee, mtime DESC;

CREATE TABLE recipient_settings
( participant           bigint   PRIMARY KEY REFERENCES participants
, patron_visibilities   int      NOT NULL CHECK (patron_visibilities > 0)
-- Three bits: 1 is for "secret", 2 is for "private", 4 is for "public".
);

SELECT 'after deployment';

ALTER TABLE tips ALTER COLUMN secrecy_level DROP DEFAULT;
